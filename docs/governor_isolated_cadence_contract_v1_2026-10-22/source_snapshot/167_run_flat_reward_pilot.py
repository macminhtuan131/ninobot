#!/usr/bin/env python3
"""Prepare an isolated value-scale/impact profile; training requires --run."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'rl_runs/flat_targeted_actor_pilot_v1/train/20261010-002632-975129/nino_ppo_final.zip'


def replace_once(code, before, after):
    if code.count(before) != 1:
        raise ValueError('Unexpected frozen source while preparing reward profile')
    return code.replace(before, after)


def make_snapshot(output):
    overlay = output / 'python'
    if not overlay.exists():
        with tempfile.TemporaryDirectory(prefix='snapshot-preparation-', dir=output) as temporary:
            directory = Path(temporary) / 'python'
            package = directory / 'nino_rl'
            shutil.copytree(ROOT / 'src/nino_rl/nino_rl', package, ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(Path(__file__).with_name('flat_reward_alignment.py'), package / 'alignment_helpers.py')
            path = package / 'control_v2.py'
            code = replace_once(path.read_text(), '    reward = float(sum(terms.values()))',
                '    if cfg.get("impact_mode") is not None:\n'
                '        from nino_rl.alignment_helpers import aligned_reward\n'
                '        return aligned_reward(terms, imu, cfg)\n'
                '    reward = float(sum(terms.values()))')
            path.write_text(code)
            path = package / 'ros_env.py'
            path.write_text(replace_once(path.read_text(), '        self.vertical_square_integral += imu["square_integral"]',
                '        imu["previous_episode_peak"] = self.peak_vertical_acceleration\n'
                '        self.vertical_square_integral += imu["square_integral"]'))
            path = package / 'train.py'
            code = replace_once(path.read_text(), '        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))',
                '        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))\n'
                '        from nino_rl.alignment_helpers import scaled_environment\n'
                '        learning_env = scaled_environment(monitored, config["training_reward_scale"])')
            code = replace_once(code, '                monitored,\n                learning_rate=',
                '                learning_env,\n                learning_rate=')
            code = replace_once(code, '            model.set_env(monitored)', '            model.set_env(learning_env)')
            code = replace_once(code, '        def _on_rollout_end(self) -> None:\n',
                '        def _on_rollout_end(self) -> None:\n'
                '            from nino_rl.alignment_helpers import record_value_diagnostics\n'
                '            record_value_diagnostics(self)\n')
            path.write_text(code)
            path = package / 'training_contract.py'
            code = replace_once(path.read_text(), '    return contract\n',
                '    if "training_reward_scale" in config:\n'
                '        contract["revision"] = 38\n'
                '        contract["learner_reward_units"] = {"fixed_multiplier": config["training_reward_scale"],\n'
                '            "raw_metrics_preserved": True, "impact_mode": config["reward_v2"].get("impact_mode", "clipped_fourth_v1")}\n'
                '    return contract\n')
            path.write_text(code)
            for file in package.glob('*.py'):
                compile(file.read_text(), str(file), 'exec')
            directory.rename(overlay)
    if (overlay / 'nino_rl/alignment_helpers.py').read_bytes() != Path(__file__).with_name('flat_reward_alignment.py').read_bytes():
        raise ValueError('Prepared helper changed; preserve snapshot and use a new output directory')
    return overlay


def prepare(args):
    sys.path.insert(0, str(ROOT / 'src/nino_rl'))
    from nino_rl.core import load_config
    from nino_rl.evaluation import benchmark_id, prepare_evaluation_config
    from nino_rl.tuning_trials import assert_trial_inputs, digest, audit_actor_initialization
    from nino_rl.tuning_objective import make_objective_contract
    from flat_reward_alignment import validate_scale, REVISION
    import yaml
    config = load_config(args.config)
    scale = validate_scale(config['training_reward_scale'])
    if config['reward_v2'].get('impact_mode') not in (None, REVISION):
        raise ValueError('Unsupported impact profile')
    old = load_config(SOURCE.parent / 'ppo.yaml')
    invariant = lambda c: {k: v for k, v in c.items() if k not in
        ('reward_v2', 'ppo', 'training_reward_scale', 'flat_targeted_pilot')}
    if invariant(old) != invariant(config) or old['ppo'] != config['ppo']:
        raise ValueError('This correction must preserve task/controller/estimator/actions/PPO update settings')
    if args.timesteps <= 0 or args.timesteps % int(config['ppo']['n_steps']):
        raise ValueError('Budget must cover whole positive PPO rollouts')
    study = json.loads((ROOT / 'rl_runs/flat_focused_optuna_v1/trial_plan.json').read_text())['trials']
    assert_trial_inputs(study)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    overlay = make_snapshot(output)
    assets = {str(path): digest(path) for path in sorted((overlay / 'nino_rl').glob('*.py'))}
    initialization = audit_actor_initialization(config, SOURCE)
    experiment = dict(revision='flat_reward_units_energy_v1', configuration=str(args.config.resolve()),
        configuration_sha256=digest(args.config), source_actor=str(SOURCE), source_actor_sha256=digest(SOURCE),
        snapshot_assets=assets, initialization=initialization, actor='copied without head resets',
        critic='fresh', optimizer='fresh', training_counter=0, training_reward_scale=scale,
        raw_episode_metrics_preserved=True, training_steps=args.timesteps)
    config['reward_alignment_experiment'] = experiment
    evaluation = deepcopy(config)
    evaluation.pop('training_reward_scale'); evaluation.pop('reward_alignment_experiment')
    old_report = json.loads((ROOT / 'rl_runs/flat_targeted_actor_pilot_v1/comparison.json').read_text())['pi']['report']
    if benchmark_id(prepare_evaluation_config(evaluation)) != old_report['benchmark_id']:
        raise ValueError('Correction changed physical benchmark conditions')
    objective = make_objective_contract(evaluation, ROOT / 'src/nino_rl/config/optuna_objective.yaml',
                                       course='flat', episodes=24, seed=64000)
    plan = dict(experiment=experiment, source_trial_contract=study['sha256'],
        evaluation_objective=objective, evaluation_seeds=list(range(64000, 64024)),
        promotion_gates=dict(arrivals=24, mean_completion_seconds=18.5, physical_rmse_ratio_max=1.05,
                             comfort_or_slip_ratio_max=.90, other_metric_ratio_max=1.0),
        interpretation='Single-seed pilot, no new Optuna history import or automatic next-stage promotion')
    path = output / 'pilot_plan.json'
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError('Prepared contract changed; preserve results and use a new output directory')
    path.write_text(json.dumps(plan, indent=2) + '\n')
    for name, settings in [('pilot.yaml', config), ('evaluation.yaml', evaluation)]:
        (output / name).write_text(yaml.safe_dump(settings, sort_keys=False))
    print('Prepared revision-38 learner contract:', path, flush=True)
    print('Copied actor; fresh critic/optimizer; raw task metrics preserved; learner reward multiplier:', scale, flush=True)
    return output, overlay, study, plan


def run(args, output, overlay, study, plan):
    from nino_rl.tuning_trials import assert_trial_inputs
    from nino_rl.tuning_objective import read_episode_rows, score_episodes
    from nino_rl.evaluation import compare_summaries
    from train_rough_curriculum import Processes, assert_isolated, complete_evaluation, checkpoint_steps
    os.environ.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(overlay) + os.pathsep + str(ROOT / 'src/nino_rl') + os.pathsep + env.get('PYTHONPATH', '')
    assert_isolated(79, 'nino_flat_79')
    processes = Processes(env, pi_integrator_profile='conditional_v1')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    def launch(directory, config):
        assert_trial_inputs(study)
        processes.world = processes.start(['ros2', 'launch', 'nino_rl', 'training_sim.launch.py',
            f'world:={study["world"]}', 'world_name:=combined_flat_section', 'headless:=true',
            'pi_integrator_profile:=conditional_v1'], directory / 'gazebo.log')
        processes.run(['ros2', 'run', 'nino_rl', 'wait_for_sim'], directory / 'readiness.log', timeout=90)
        assert_trial_inputs(study, live=True)
        processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
            '--config', config, '--timeout', 60], directory / 'profile.log', timeout=65)

    try:
        models = list((output / 'train').glob('*/nino_ppo_final.zip'))
        if len(models) > 1:
            raise ValueError('Ambiguous pilot models')
        if not models:
            if list((output / 'train').glob('*/nino_ppo_interrupted.zip')):
                raise ValueError('Interrupted pilot saved; inspect checkpoint before continuing')
            launch(output / 'train', output / 'pilot.yaml')
            processes.run(['ros2', 'run', 'nino_rl', 'train', '--config', output / 'pilot.yaml',
                '--device', 'cuda', '--init-model', SOURCE, '--timesteps', args.timesteps,
                '--checkpoint-every', 10240, '--preflight-timeout', 60,
                '--output', output / 'train'], output / 'train/training.log')
            processes.close()
            models = list((output / 'train').glob('*/nino_ppo_final.zip'))
        if len(models) != 1 or checkpoint_steps(models[0]) != args.timesteps:
            raise ValueError('Frozen pilot budget not completed')
        result = {}
        for label in ('ppo', 'pi'):
            directory = output / label
            cached = complete_evaluation(directory, 24)
            if cached is None:
                launch(directory, output / 'evaluation.yaml')
                command = ['ros2', 'run', 'nino_rl', 'evaluate_baseline' if label == 'pi' else 'evaluate',
                    '--config', output / 'evaluation.yaml', '--seeds', *plan['evaluation_seeds'], '--output', directory]
                command += ['--baseline-speed-scale', 1.] if label == 'pi' else ['--model', models[0], '--device', 'cuda']
                processes.run(command, directory / 'evaluation.log')
                processes.close()
                cached = complete_evaluation(directory, 24)
            if cached is None or cached[1]['evaluation_seeds'] != plan['evaluation_seeds']:
                raise ValueError('Incomplete or incompatible pilot evaluation')
            paths = [p for p in directory.glob('*/summary.json') if json.loads(p.read_text()) == cached[1]]
            if len(paths) != 1:
                raise ValueError('Ambiguous evaluation evidence')
            result[label] = dict(summary=str(paths[0]), report=cached[1],
                objective=score_episodes(read_episode_rows(paths[0].parent / 'episodes.csv'), plan['evaluation_objective']))
        result['comparison'] = compare_summaries(result['pi']['report'], result['ppo']['report'])
        metrics = result['comparison']['metrics']
        ratio = lambda name: metrics[name]['candidate'] / metrics[name]['baseline']
        vibration, slip = ratio('rms_vertical_acceleration_m_s2'), ratio('rms_wheel_slip')
        result['gates'] = dict(physical_arrival=result['ppo']['report']['success_rate'] == 1.,
            completion=metrics['time_seconds']['candidate'] <= 18.5,
            tracking=ratio('truth_path_rmse_m') <= 1.05,
            quality=(vibration <= .9 and slip <= 1.) or (slip <= .9 and vibration <= 1.),
            vibration_ratio=vibration, slip_ratio=slip)
        result['promote'] = all(result['gates'][key] for key in ('physical_arrival', 'completion', 'tracking', 'quality'))
        (output / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        print('Completed corrected pilot:', output / 'comparison.json', flush=True)
        print(json.dumps(result['gates'], indent=2), flush=True)
    finally:
        processes.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'src/nino_rl/config/combined_flat_energy_scaled_pilot.yaml')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timesteps', type=int, default=20480)
    parser.add_argument('--run', action='store_true', help='Explicitly start training and matching PI evaluation; default only prepares')
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.output is None:
        name = 'flat_energy_scaled_pilot_v1' if 'energy' in args.config.name else 'flat_value_scaled_pilot_v1'
        args.output = ROOT / 'rl_runs' / name
    output, overlay, study, plan = prepare(args)
    if args.run:
        run(args, output, overlay, study, plan)
    else:
        print('Prepared only: no Gazebo or training started. Add --run to execute.', flush=True)


if __name__ == '__main__':
    main()
