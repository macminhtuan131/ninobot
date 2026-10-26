#!/usr/bin/env python3
"""Audit trial 8, compare held-out E1, and gate a bounded fixed-route curriculum."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'rl_runs/rough_e1_v16_optuna_v1/trial_0008/train/20261010-030720-658073/nino_ppo_final.zip'
OUTPUT = ROOT / 'rl_runs/rough_trial8_validation_v1'
SEEDS = list(range(12000, 12020))
PROBE_SEEDS = [11000, 11001, 11002]
STEPS = 20480


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def numerical_gate(audit):
    """Require measured weak fit plus critic dominance, not merely a big MSE."""
    import numpy as np
    raw = audit['raw_units']
    ratios = [batch['critic_gradient_norm'] / max(batch['actor_gradient_norm'], 1e-12)
              for batch in raw['batches']]
    retained = [batch['clip_retained_fraction'] for batch in raw['batches']]
    dominance = float(np.median(ratios))
    fraction = float(np.median(retained))
    confirmed = raw['explained_variance'] < .1 and dominance >= 5. and fraction <= .01
    eligible = []
    for label, candidate in audit['fresh_critic_candidates'].items():
        ratio = float(np.median([batch['critic_gradient_norm'] / max(batch['actor_gradient_norm'], 1e-12)
                                 for batch in candidate['batches']]))
        clip = float(np.median([batch['clip_retained_fraction'] for batch in candidate['batches']]))
        if ratio <= 3. and clip >= 2. * fraction:
            eligible.append(float(label))
    scale = max(eligible) if confirmed and eligible else None
    return dict(confirmed=bool(confirmed), raw_median_critic_actor_ratio=dominance,
                raw_median_clip_retained_fraction=fraction, selected_scale=scale,
                selection='Largest tested multiplier reducing critic/actor norm ratio to <=3 and doubling retained gradient fraction',
                limitation='Small frozen-policy probe; not original training minibatches or a convergence guarantee')


def route_readiness(rows, config, minimum):
    """Independent arrival, route gates, localization, tracking and stall checks."""
    import numpy as np
    if len(rows) != minimum:
        raise ValueError('Route-PI readiness requires a complete seed batch')
    success = [str(row['success']).lower() in ('true', '1', '1.0') for row in rows]
    error = float(np.mean([float(row['truth_path_rmse_m']) for row in rows]))
    pose_error = max(float(row['odom_truth_position_error_m']) for row in rows)
    physical = all(not arrived or (float(row['truth_endpoint_error_m']) <= config['goal_tolerance_m'] + 1e-6
        and int(float(row['route_gates_passed'])) == int(float(row['route_gates_total'])))
        for arrived, row in zip(success, rows))
    rollovers = sum(row['termination'] == 'rollover' for row in rows)
    rate = float(np.mean(success))
    gate = config['rough_curriculum']['gate']
    return dict(passed=bool(rate >= gate['success_rate'] and error <= gate['max_truth_path_rmse_m']
                            and pose_error <= .10 and physical and rollovers == 0),
                episodes=minimum, physical_arrival_rate=rate, truth_path_rmse_m=error,
                max_episode_mean_pose_disagreement_m=pose_error,
                physical_success_consistent=physical, rollovers=rollovers)


def corrected_snapshot(output, original, scale):
    """Clone v16; only learner reward units, diagnostics and resume contract change."""
    from run_flat_reward_pilot import replace_once
    overlay = output / 'python'
    if not overlay.exists():
        with tempfile.TemporaryDirectory(prefix='rough-value-snapshot-', dir=output) as temporary:
            directory = Path(temporary) / 'python'
            shutil.copytree(original / 'python', directory, ignore=shutil.ignore_patterns('__pycache__'))
            package = directory / 'nino_rl'
            shutil.copyfile(Path(__file__).with_name('flat_reward_alignment.py'), package / 'alignment_helpers.py')
            path = package / 'train.py'
            code = replace_once(path.read_text(), '        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))',
                '        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))\n'
                '        from nino_rl.alignment_helpers import scaled_environment\n'
                '        learning_env = scaled_environment(monitored, config["training_reward_scale"])')
            code = replace_once(code, '                monitored,\n                learning_rate=', '                learning_env,\n                learning_rate=')
            code = replace_once(code, '            model.set_env(monitored)', '            model.set_env(learning_env)')
            code = replace_once(code, '        def _on_rollout_end(self) -> None:\n',
                '        def _on_rollout_end(self) -> None:\n'
                '            from nino_rl.alignment_helpers import record_value_diagnostics\n'
                '            record_value_diagnostics(self)\n')
            path.write_text(code)
            path = package / 'training_contract.py'
            path.write_text(replace_once(path.read_text(), '    return contract\n',
                '    if "training_reward_scale" in config:\n'
                '        contract["revision"] = 39\n'
                '        contract["learner_reward_units"] = {"fixed_multiplier": config["training_reward_scale"],\n'
                '            "raw_metrics_preserved": True, "profile": "rough_value_units_v1"}\n'
                '    return contract\n'))
            for file in package.glob('*.py'):
                compile(file.read_text(), str(file), 'exec')
            directory.rename(overlay)
    return overlay


class Validation:
    def __init__(self, output):
        from tune_rough_e1_v16 import bootstrap
        self.original = bootstrap()
        # Load the frozen package before Processes imports the live source path.
        from nino_rl.core import load_config
        from nino_rl.tuning_trials import digest, assert_trial_inputs
        from rough_localized_processes import ReliableRoughProcesses
        self.digest, self.assert_inputs = digest, assert_trial_inputs
        self.old_contract = read(ROOT / 'rl_runs/rough_e1_v16_optuna_v1/study_contract.json')
        self.assert_inputs(self.old_contract['comparable_trials'])
        self.config = load_config(SOURCE.parent / 'ppo.yaml')
        self.output = output
        self.world = ROOT / 'rl_runs/rough_terrain_bank_v1/worlds/original.sdf'
        self.processes = ReliableRoughProcesses(os.environ.copy(), pi_integrator_profile='conditional_v1')
        self.state = dict(pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat(), stage='preparing')
        self.plan = dict(revision='rough_trial8_audit_fixed_routes_v1', source_model=str(SOURCE),
            source_sha256=digest(SOURCE), source_config_sha256=digest(SOURCE.parent / 'ppo.yaml'),
            original_trial_contract=self.old_contract['comparable_trials']['sha256'],
            probe_seeds=PROBE_SEEDS, heldout_seeds=SEEDS,
            speed_matched_pi_scale=.70, duration_match_relative_tolerance=.05,
            possible_correction_steps=STEPS, numerical_gate=dict(max_explained_variance=.1,
                minimum_critic_actor_ratio=5., maximum_clip_retained_fraction=.01,
                candidate_multipliers=[.1, .03, .01]),
            route_pi_screen_episodes=3, route_pi_confirmation_episodes=20,
            curriculum=dict(fixed_map=True, stages=[['E1','N1'], ['E1','N1','S1']],
                steps_per_stage=STEPS, max_additional_steps=2*STEPS,
                gate=deepcopy(self.config['rough_curriculum']['gate'])),
            physical_scoring='unchanged independent physical arrival and ordered route gates',
            old_studies='preserved; no historical score import or Optuna started')
        path = output / 'validation_plan.json'
        if path.exists() and read(path) != self.plan:
            raise ValueError('Validation plan changed; use a new output directory')
        write(path, self.plan)
        helpers = [Path(__file__)] + [Path(__file__).with_name(name) for name in
            ('inspect_flat_critic.py', 'flat_reward_alignment.py', 'run_flat_reward_pilot.py', 'run_flat_reward_validation.py')]
        fingerprints = {str(path): digest(path) for path in helpers}
        assets_path = output / 'workflow_assets.json'
        if assets_path.exists() and read(assets_path) != fingerprints:
            raise ValueError('Validation implementation changed; preserve evidence and use a new output directory')
        write(assets_path, fingerprints)
        self.base_env = self.processes.env.copy()

    def state_at(self, stage, **extra):
        self.state.update(stage=stage, updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
        write(self.output / 'status.json', self.state)
        with (self.output / 'status_history.jsonl').open('a') as stream:
            stream.write(json.dumps(self.state, allow_nan=False) + '\n')
        self.report()
        print(stage, flush=True)

    def report(self):
        lines = ['# Rough trial 8 validation', '', '**Stage:** ' + self.state['stage'], '',
                 'Source: `' + str(SOURCE) + '`.',
                 'Fixed original terrain, three existing actions, independent physical arrival scoring.', '',
                 '## Critic audit', '']
        path = self.output / 'critic_probe/audit.json'
        if path.exists():
            audit = read(path)
            raw = audit['raw_units']
            lines += [f"- Frozen-policy samples: {audit['samples']}; training updates: 0.",
                      f"- Raw explained variance: {raw['explained_variance']:.6f}.",
                      '- Measured decision: `' + json.dumps(audit['decision']) + '`.']
        else:
            lines.append('Live gradient probe pending; saved value logs alone do not establish gradient dominance.')
        lines += ['', '## E1 matching evaluations', '']
        path = self.output / 'heldout_comparison.json'
        if path.exists():
            data = read(path)
            lines += ['| Profile | Physical arrival | Time (s) | Truth RMSE (m) | RMS vertical acceleration | Slip | Fixed score |',
                      '|---|---:|---:|---:|---:|---:|---:|']
            for name, result in data['reports'].items():
                metrics = result['report']['metrics_all_episodes']
                lines.append(f"| {name} | {round(result['report']['success_rate']*20)}/20 | " +
                    ' | '.join(f"{metrics[key]['mean']:.5f}" for key in
                        ('time_seconds','truth_path_rmse_m','rms_vertical_acceleration_m_s2','rms_wheel_slip')) +
                    f" | {result['objective']['score']:.5f} |")
            lines.append(f"PI duration matched within 5%: {data['duration_matched_within_5_percent']}.")
        else:
            lines.append('Trial-8/full-PI/0.70-PI evaluations pending on seeds 12000–12019.')
        lines += ['', 'These are unused reset seeds on the same fixed map with domain randomization disabled.',
                  'They do not test unseen terrain or establish generalization across physical parameters.', '',
                  '## Conditional correction', '']
        path = self.output / 'correction_comparison.json'
        if path.exists():
            corrected = read(path)
            lines.append('Independent E1 gate: `' + json.dumps(corrected['physical_gate']) + '`.')
            lines.append('Final logged critic metrics: `' + json.dumps(corrected['critic_diagnostics']['last']) + '`.')
        else:
            lines.append('A 20,480-step pilot is allowed only after the measured numerical gate confirms imbalance.')
        lines += ['', '## Route PI and curriculum', '']
        path = self.output / 'route_pi_gate.json'
        if path.exists():
            readiness = read(path)
            for route, result in readiness['routes'].items():
                gate = result.get('confirmation_gate', result['screen_gate'])
                lines.append('- ' + route + ': `' + json.dumps(gate) + '`.')
        else:
            lines.append('E1/N1/S1 PI readiness pending; arriving with >0.05 m mean physical path RMSE does not admit a route.')
        path = self.output / 'curriculum_result.json'
        if path.exists():
            for block in read(path)['history']:
                lines.append('- Stage ' + str(block['stage_index']) + ': `' + json.dumps(block['gate']) + '`.')
        lines += ['', 'Replay is balanced E1/N1, then E1/N1/S1; terrain remains fixed.',
                  'At most 20,480 additional steps per route stage; no automatic extension of failed stages.',
                  'Saved models, old Optuna observations and physical timing/scoring checks are preserved.',
                  'No Optuna worker is launched by this workflow.', '']
        (self.output / 'REPORT.md').write_text('\n'.join(lines))

    def check(self, overlay=None):
        self.assert_inputs(self.old_contract['comparable_trials'])
        for path, expected in read(self.output / 'workflow_assets.json').items():
            if self.digest(path) != expected:
                raise ValueError('Validation implementation changed: ' + path)
        if self.digest(SOURCE) != self.plan['source_sha256']:
            raise ValueError('Trial-8 checkpoint changed')
        if overlay is not None:
            contract = read(self.output / 'correction_contract.json')
            for path, expected in contract['snapshot_assets'].items():
                if self.digest(path) != expected:
                    raise ValueError('Corrected snapshot changed: ' + path)

    def launch(self, directory, config, overlay=None):
        from train_rough_curriculum import assert_isolated
        self.check(overlay)
        self.processes.close()
        assert_isolated(78, 'nino_rough_78')
        self.processes.env = self.base_env.copy()
        if overlay is not None:
            self.processes.env['PYTHONPATH'] = str(overlay) + os.pathsep + self.base_env.get('PYTHONPATH', '')
        self.processes.launch(self.world, directory, False)
        self.assert_inputs(self.old_contract['comparable_trials'], live=True)
        self.processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
            '--config', config, '--timeout', 60], directory / 'profile.log', timeout=65)

    def capture(self):
        import numpy as np
        import torch
        from stable_baselines3 import PPO
        from nino_rl.evaluation import prepare_evaluation_config
        from nino_rl.ros_env import NinoGazeboEnv
        from inspect_flat_critic import gradient_audit, fresh_scaled_critic_audit
        import yaml
        directory = self.output / 'critic_probe'
        audit_path = directory / 'audit.json'
        if audit_path.exists():
            audit = read(audit_path)
            if audit['source_sha256'] != self.plan['source_sha256']:
                raise ValueError('Probe has a different actor')
            return audit
        directory.mkdir(exist_ok=True)
        cfg = prepare_evaluation_config(self.config, route='E1')
        path = directory / 'config.yaml'
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        model = PPO.load(SOURCE, device='cuda')
        model.policy.set_training_mode(False)
        samples = directory / 'probe.npz'
        episodes_path = directory / 'episodes.json'
        if samples.exists() and episodes_path.exists():
            data = dict(np.load(samples))
            episodes = read(episodes_path)
        else:
            data = {name: [] for name in ('observations', 'actions', 'values', 'log_probs',
                                          'rewards', 'raw_rewards', 'dones', 'seeds')}
            episodes, environment = [], None
            try:
                self.launch(directory, path)
                environment = NinoGazeboEnv(cfg, total_training_steps=1)
                for seed in PROBE_SEEDS:
                    torch.manual_seed(seed)
                    observation, _ = environment.reset(seed=seed)
                    while True:
                        with torch.no_grad():
                            action, value, logp = model.policy(torch.as_tensor(observation[None], device=model.device))
                        action = action.cpu().numpy()[0]
                        data['observations'].append(observation.copy()); data['actions'].append(action.copy())
                        data['values'].append(float(value.item())); data['log_probs'].append(float(logp.item()))
                        data['seeds'].append(seed)
                        observation, reward, terminated, truncated, info = environment.step(np.clip(action, -1., 1.))
                        data['raw_rewards'].append(reward)
                        if truncated and not terminated:
                            raise RuntimeError('Truncated probe requires terminal-value bootstrap; preserve logs and inspect before gradient audit')
                        data['rewards'].append(reward); data['dones'].append(terminated or truncated)
                        if terminated or truncated:
                            episodes.append(info['episode_metrics'])
                            print('Read-only rough probe', seed, info['episode_metrics']['termination'], flush=True)
                            break
            finally:
                if environment is not None:
                    environment.close()
                self.processes.close()
            data = {name: np.asarray(value) for name, value in data.items()}
            np.savez_compressed(samples, **data)
            write(episodes_path, episodes)
        self.check()
        audit = dict(source_sha256=self.plan['source_sha256'], source_model=str(SOURCE),
            samples=len(data['rewards']), seeds=PROBE_SEEDS, training_updates=0,
            raw_units=gradient_audit(model, data), episodes=episodes,
            fresh_critic_candidates={str(scale): fresh_scaled_critic_audit(model, data, self.config, scale)
                                     for scale in (.1, .03, .01)})
        audit['decision'] = numerical_gate(audit)
        write(audit_path, audit)
        return audit

    def evaluate(self, name, config, *, model=None, speed_scale=1., seeds=SEEDS,
                 route='E1', overlay=None, control_trace=False):
        from train_rough_curriculum import complete_evaluation
        import yaml
        directory = self.output / name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'input_config.yaml'
        text = yaml.safe_dump(config, sort_keys=False)
        if path.exists() and path.read_text() != text:
            raise ValueError('Saved evaluation input changed: ' + str(path))
        path.write_text(text)
        cached = complete_evaluation(directory, len(seeds))
        if cached is None:
            try:
                self.launch(directory, path, overlay)
                command = ['ros2', 'run', 'nino_rl', 'evaluate' if model else 'evaluate_baseline',
                    '--config', path, '--route', route, '--seeds', *seeds, '--output', directory]
                command += ['--model', model, '--device', 'cuda'] if model else ['--baseline-speed-scale', speed_scale]
                if control_trace:
                    command.append('--control-trace')
                self.processes.run(command, directory / 'evaluation.log')
            finally:
                self.processes.close()
            cached = complete_evaluation(directory, len(seeds))
        if cached is None:
            raise ValueError('Evaluation did not complete: ' + name)
        rows, summary = cached
        if summary['evaluation_seeds'] != seeds or summary['model'] != (str(model) if model else None):
            raise ValueError('Evaluation seed/model mismatch')
        if model is None and summary['baseline_speed_scale'] != speed_scale:
            raise ValueError('PI speed scale mismatch')
        paths = [p for p in directory.glob('*/summary.json') if read(p) == summary]
        if len(paths) != 1:
            raise ValueError('Ambiguous completed evaluation')
        return dict(rows=rows, report=summary, summary=str(paths[0]))

    def benchmark(self):
        from nino_rl.evaluation import compare_summaries
        from rough_e1_optuna_objective import read_report, make_contract
        fixed = deepcopy(self.config)
        fixed['routes']['fixed_route'] = 'E1'
        objective = make_contract(fixed, ROOT / 'src/nino_rl/config/rough_e1_v16_optuna_objective.yaml',
                                  episodes=len(SEEDS), seed=SEEDS[0])
        write(self.output / 'heldout_objective.json', objective)
        reports = {}
        for label, model, scale in (('trial8', SOURCE, 1.), ('pi_full', None, 1.), ('pi_matched', None, .70)):
            self.state_at('heldout_' + label)
            reports[label] = self.evaluate('heldout/' + label, self.config, model=model, speed_scale=scale)
            _, reports[label]['objective'] = read_report(Path(reports[label]['summary']), objective)
        result = dict(reports=reports,
            versus_full_pi=compare_summaries(reports['pi_full']['report'], reports['trial8']['report']),
            versus_matched_pi=compare_summaries(reports['pi_matched']['report'], reports['trial8']['report']))
        time_of = lambda label: reports[label]['report']['metrics_all_episodes']['time_seconds']['mean']
        gap = abs(time_of('pi_matched') - time_of('trial8')) / time_of('trial8')
        result.update(duration_relative_gap=gap, duration_matched_within_5_percent=gap <= .05,
                      interpretation='Unseen scenario seeds on the fixed E1 map, not unseen terrain; repeat training seeds before generalization claims')
        write(self.output / 'heldout_comparison.json', result)
        return result

    def prepare_correction(self, scale):
        import yaml
        overlay = corrected_snapshot(self.output, self.original, scale)
        cfg = deepcopy(self.config)
        cfg['training_reward_scale'] = scale
        contract = dict(revision='rough_value_units_v1', training_contract_revision=39,
            source_model=str(SOURCE), source_sha256=self.plan['source_sha256'], training_reward_scale=scale,
            actor='unchanged complete actor', critic='fresh', optimizer='fresh', training_counter=0,
            training_steps=STEPS, task_rewards='unchanged', physical_scoring='unchanged',
            snapshot_assets={str(path): self.digest(path) for path in sorted((overlay / 'nino_rl').glob('*.py'))})
        path = self.output / 'correction_contract.json'
        if path.exists() and read(path) != contract:
            raise ValueError('Correction contract changed')
        write(path, contract)
        (self.output / 'correction.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False))
        return cfg, overlay

    def train(self, name, config, source, overlay=None, resume=False):
        import yaml
        from train_rough_curriculum import checkpoint_steps
        directory = self.output / name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'input_config.yaml'
        text = yaml.safe_dump(config, sort_keys=False)
        if path.exists() and path.read_text() != text:
            raise ValueError('Training contract changed: ' + name)
        path.write_text(text)
        target = checkpoint_steps(source) + STEPS if resume else STEPS
        models = list((directory / 'train').glob('*/nino_ppo_final.zip'))
        if not models:
            if list((directory / 'train').glob('*/nino_ppo_interrupted.zip')):
                raise RuntimeError('Interrupted corrected run preserved; audit before resuming')
            try:
                self.launch(directory, path, overlay)
                self.processes.run(['ros2', 'run', 'nino_rl', 'train', '--config', path,
                    '--device', 'cuda', '--timesteps', STEPS, '--checkpoint-every', 10240,
                    '--preflight-timeout', 60, '--output', directory / 'train',
                    '--resume' if resume else '--init-model', source], directory / 'training.log')
            finally:
                self.processes.close()
            models = list((directory / 'train').glob('*/nino_ppo_final.zip'))
        if len(models) != 1 or checkpoint_steps(models[0]) != target:
            raise ValueError('Exact correction/curriculum training budget not completed')
        if not resume:
            transfer = read(models[0].with_name('actor_transfer.json'))
            if transfer['source_sha256'] != self.plan['source_sha256'] or any(transfer[k] != value for k, value in
                    (('critic','fresh'), ('optimizer','fresh'), ('training_counter',0))):
                raise ValueError('Incorrect fresh critic/optimizer transfer')
        return models[0]

    def route_pi(self, config, overlay=None):
        from run_rough_localized import longest_commanded_stall
        results = {}
        all_pass = True
        for route, index in (('E1', 0), ('N1', 1), ('S1', 2)):
            cfg = deepcopy(config)
            cfg.pop('training_reward_scale', None)
            cfg['rough_runtime']['stage_index'] = index
            self.state_at('route_pi_' + route)
            screen = self.evaluate('route_pi/' + route + '/screen', cfg, route=route,
                                   seeds=[13000,13001,13002], overlay=overlay, control_trace=True)
            gate = route_readiness(screen['rows'], cfg, 3)
            result = dict(screen=screen, screen_gate=gate)
            if gate['passed']:
                full = self.evaluate('route_pi/' + route + '/confirmation', cfg, route=route,
                                     seeds=list(range(13100,13120)), overlay=overlay, control_trace=True)
                gate = route_readiness(full['rows'], cfg, 20)
                result.update(confirmation=full, confirmation_gate=gate)
            evidence = result.get('confirmation', screen)
            stalls = [longest_commanded_stall(Path(evidence['summary']).parent / f'episode-{i:03d}/control_trace.csv')
                      for i in range(1, len(evidence['rows'])+1)]
            gate['longest_commanded_stall_seconds'] = max(stalls)
            gate['passed'] = gate['passed'] and max(stalls) <= 2.
            result['passed'] = gate['passed']
            all_pass = all_pass and gate['passed']
            results[route] = result
            write(self.output / 'route_pi_gate.json', dict(passed=all_pass and len(results)==3, routes=results))
        return dict(passed=all_pass, routes=results)

    def curriculum(self, config, source, overlay=None):
        from nino_rl.rough_curriculum import evaluation_gate
        history = []
        for index in (1, 2):
            cfg = deepcopy(config)
            cfg['rough_runtime']['stage_index'] = index
            routes = cfg['rough_curriculum']['stages'][index]['route_ids']
            self.state_at('curriculum_train_' + str(index), active_routes=routes)
            source = self.train('curriculum/stage_' + str(index), cfg, source, overlay, resume=True)
            self.state['latest_model'] = str(source)
            rows, reports = [], {}
            evaluation_cfg = deepcopy(cfg)
            evaluation_cfg.pop('training_reward_scale', None)
            for route in routes:
                self.state_at('curriculum_evaluate_' + str(index) + '_' + route)
                report = self.evaluate('curriculum/stage_' + str(index) + '/eval/' + route,
                    evaluation_cfg, model=source, route=route, seeds=list(range(14000,14020)), overlay=overlay)
                rows += report['rows']
                reports[route] = report
            gate = evaluation_gate(rows, routes, cfg)
            history.append(dict(stage_index=index, active_routes=routes, gate=gate,
                                reports=reports, model=str(source), fixed_terrain=True))
            write(self.output / 'curriculum_result.json', dict(history=history))
            if not gate['passed']:
                self.state_at('held_curriculum', failed_gate=gate)
                return False
        return True

    def run(self, wait_for_flat):
        from nino_rl.rough_curriculum import evaluation_gate
        from nino_rl.evaluation import compare_summaries
        if wait_for_flat:
            self.state_at('waiting_for_flat')
            from run_flat_reward_validation import process_identity
            identity = process_identity(wait_for_flat)
            if identity and 'run_flat_reward_validation.py' not in identity[0]:
                raise ValueError('Wait PID does not belong to the flat validation supervisor')
            while identity is not None and process_identity(wait_for_flat) == identity:
                time.sleep(2.)
        self.state_at('critic_probe')
        audit = self.capture()
        self.state['numerical_audit'] = audit['decision']
        heldout = self.benchmark()
        cfg, overlay, model = deepcopy(self.config), None, SOURCE
        if audit['decision']['confirmed']:
            if audit['decision']['selected_scale'] is None:
                self.state_at('held_numerical_correction', reason='None of the tested reward units resolved gradient imbalance')
                return
            cfg, overlay = self.prepare_correction(audit['decision']['selected_scale'])
            self.state_at('correction_training', training_reward_scale=cfg['training_reward_scale'])
            model = self.train('corrected_pilot', cfg, SOURCE, overlay)
            evaluation_cfg = deepcopy(cfg)
            evaluation_cfg.pop('training_reward_scale')
            self.state_at('correction_evaluation')
            corrected = self.evaluate('corrected_pilot/eval', evaluation_cfg, model=model, overlay=overlay)
            gate = evaluation_gate(corrected['rows'], ['E1'], cfg)
            from run_flat_reward_validation import critic_summary
            from rough_e1_optuna_objective import read_report
            _, scored = read_report(Path(corrected['summary']), read(self.output / 'heldout_objective.json'))
            result = dict(physical_gate=gate, corrected=corrected,
                critic_diagnostics=critic_summary(model.parent), fixed_objective=scored,
                versus_trial8=compare_summaries(heldout['reports']['trial8']['report'], corrected['report']),
                versus_full_pi=compare_summaries(heldout['reports']['pi_full']['report'], corrected['report']),
                versus_matched_pi=compare_summaries(heldout['reports']['pi_matched']['report'], corrected['report']))
            write(self.output / 'correction_comparison.json', result)
            if not gate['passed']:
                self.state_at('held_corrected_arrival', failed_gate=gate)
                return
        else:
            gate = evaluation_gate(heldout['reports']['trial8']['rows'], ['E1'], cfg)
            if not gate['passed']:
                self.state_at('held_trial8_arrival', failed_gate=gate)
                return
        pi_gate = self.route_pi(cfg, overlay)
        if not pi_gate['passed']:
            self.state_at('held_route_pi', reason='Route PI failed strict tracking/arrival/stall checks; N1/S1 training not started')
            return
        if self.curriculum(cfg, model, overlay):
            self.state_at('complete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--wait-for-flat-pid', type=int)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'worker.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runner = Validation(output)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            if args.prepare_only:
                runner.state_at('prepared')
            else:
                runner.run(args.wait_for_flat_pid)
        except KeyboardInterrupt:
            runner.state_at('cancelled')
            raise
        except Exception as error:
            runner.state_at('failed', error=str(error))
            raise
        finally:
            runner.processes.close()


if __name__ == '__main__':
    main()
