#!/usr/bin/env python3
"""Isolated, contract-checked E1 Optuna study using the validated v16 snapshot."""
from copy import deepcopy
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'rl_runs/rough_e1_v16_optuna_v1'
PILOT = ROOT / 'rl_runs/rough_wall_recovery_v16/curriculum/blocks/block_0000/train/20261009-101753-653623'
REWARD_RANGES = {
    'time_penalty': (0.03, 0.50), 'lateral_weight': (0.25, 0.80),
    'heading_weight': (0.15, 0.55), 'impact_weight': (0.02, 0.12),
    'body_rate_weight': (0.02, 0.10), 'slip_weight': (0.05, 0.40),
}


def bootstrap():
    from run_rough_localized import EXPERIMENT, verify
    verify()
    overlay = str(EXPERIMENT / 'python')
    sys.path.insert(0, overlay)
    os.environ['PYTHONPATH'] = overlay + os.pathsep + os.environ.get('PYTHONPATH', '')
    os.environ.update(ROS_DOMAIN_ID='78', NINO_ROS_DOMAIN_ID='78', GZ_PARTITION='nino_rough_78',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    return EXPERIMENT


def sample_config(trial, base):
    config = deepcopy(base)
    for name, (low, high) in REWARD_RANGES.items():
        config['reward_v2'][name] = trial.suggest_float('reward_v2.' + name, low, high,
                                                     log=name == 'time_penalty')
    ppo = config['ppo']
    ppo['learning_rate'] = trial.suggest_float('learning_rate', 1e-5, 1e-4, log=True)
    ppo['ent_coef'] = trial.suggest_float('ent_coef', 1e-4, 3e-3, log=True)
    ppo['n_steps'] = trial.suggest_categorical('n_steps', [1024, 2048])
    ppo['batch_size'] = trial.suggest_categorical('batch_size', [128, 256, 512])
    ppo['n_epochs'] = trial.suggest_categorical('n_epochs', [3, 5, 8])
    ppo['clip_range'] = trial.suggest_float('clip_range', 0.10, 0.25)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-study', action='store_true', help='Create study and queue current settings; no Gazebo/training')
    parser.add_argument('--trials', type=int, default=8, help='Additional trials on each invocation')
    parser.add_argument('--timesteps', type=int, default=20480)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    args = parser.parse_args()
    if args.trials < 1 or args.timesteps < 2048:
        parser.error('Use positive trials and at least 2048 steps')
    os.chdir(ROOT)
    experiment = bootstrap()
    import optuna
    import yaml
    from nino_rl.core import load_config
    from nino_rl.tuning_trials import (make_trial_contract, write_trial_plan, digest,
        assert_trial_inputs, validate_trial_config, train_command, verify_training_result)
    from nino_rl.tuning_history import current_candidate
    from train_rough_curriculum import assert_isolated
    from rough_localized_processes import ReliableRoughProcesses
    from rough_e1_optuna_objective import make_contract, read_report, record

    base = load_config(PILOT / 'ppo.yaml')
    source = PILOT / 'nino_ppo_final.zip'
    world = ROOT / 'rl_runs/rough_terrain_bank_v1/worlds/original.sdf'
    settings = ROOT / 'src/nino_rl/config/rough_e1_v16_optuna_objective.yaml'
    objective = make_contract(base, settings)
    comparable = make_trial_contract(ROOT, base, world_path=world, model_path=source,
        rollouts=[1024, 2048], requested_steps=args.timesteps, device=args.device, tuner_path=Path(__file__))
    # Fingerprint the package actually imported, sensor/launch snapshot and all
    # helper implementations used to own Gazebo and validate trials.
    used = list((experiment / 'python/nino_rl').glob('*.py'))
    used += [experiment / name for name in ('manifest.json', 'imu_bridge.yaml', 'config.yaml',
                                          'training_sim.launch.py', 'sim.launch.py', 'nino_cloud.urdf')
             if (experiment / name).exists()]
    used += [Path(__file__).with_name(name) for name in ('rough_e1_optuna_objective.py',
        'run_rough_localized.py', 'rough_localized_processes.py', 'train_rough_curriculum.py',
        'wait_for_drive_profile.py')]
    used += [settings, PILOT / 'ppo.yaml']
    manifest = json.loads((experiment / 'manifest.json').read_text())
    used += [experiment / name for name in manifest['snapshot_files']]
    for path in used:
        comparable['assets'][str(path.resolve())] = digest(path)
    comparable.pop('sha256')
    comparable['sha256'] = hashlib.sha256(json.dumps(comparable, sort_keys=True).encode()).hexdigest()
    candidate = current_candidate(base, lambda trial: sample_config(trial, base))
    references = []
    for path in (
        experiment / 'curriculum/baselines/stage_0/original/20261009-113412-803772/summary.json',
        experiment / 'speed_matched_pi_0.70/20261009-120037-129118/summary.json'):
        summary, scored = read_report(path, objective)
        if summary['controller'] != 'path_pi_baseline' or summary.get('model') is not None:
            raise ValueError('Expected PI reference, not a historical PPO trial')
        references.append(dict(summary=str(path), speed_scale=summary['baseline_speed_scale'],
            objective=scored, role='reference only; never an Optuna observation',
            files={str(f): digest(f) for f in (path, path.parent / 'episodes.csv', path.parent / 'config.yaml')}))
    comparable['assets'].update({k: v for ref in references for k, v in ref['files'].items()})
    comparable.pop('sha256')
    comparable['sha256'] = hashlib.sha256(json.dumps(comparable, sort_keys=True).encode()).hexdigest()
    contract = dict(revision='rough_e1_v16_optuna_v1', comparable_trials=comparable,
        objective=objective, starting_candidate=candidate, pi_references=references,
        sampler={'name': 'TPE', 'seed': 42, 'n_startup_trials': 4},
        histories='No historical scores imported; previous studies are preserved')
    output = args.output.expanduser().resolve()
    if output == experiment.resolve() or output.exists() and not (output / 'trial_plan.json').exists() and any(output.iterdir()):
        raise ValueError('Use a new dedicated output directory')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('This study already has a worker') from error
        write_trial_plan(output, comparable, objective)
        path = output / 'study_contract.json'
        if path.exists() and json.loads(path.read_text()) != contract:
            raise ValueError('Study contract changed; use a new output directory')
        path.write_text(json.dumps(contract, indent=2, allow_nan=False) + '\n')
        (output / 'base.yaml').write_text(yaml.safe_dump(base, sort_keys=False))
        assert_trial_inputs(comparable)
        study = optuna.create_study(study_name='rough_e1_v16_quality_v1', direction='maximize',
            storage='sqlite:///' + str(output / 'study.db'), load_if_exists=True,
            sampler=optuna.samplers.TPESampler(seed=42, n_startup_trials=4))
        saved = study.user_attrs.get('contract')
        if saved != contract and (saved is not None or study.trials):
            raise ValueError('Database does not match the study contract')
        study.set_user_attr('contract', contract)
        study.set_user_attr('evaluation_objective', objective)
        study.set_user_attr('pi_references', references)
        study.set_user_attr('starting_candidate', candidate)
        (output / 'evaluation_objective.json').write_text(json.dumps(objective, indent=2) + '\n')
        # Queue once; never fabricate a score from the source actor's old run.
        if not study.trials:
            study.enqueue_trial(candidate['params'], user_attrs={'candidate_kind': 'current_configuration', 'inherited_score': False})
        if args.prepare_study:
            print(f'Prepared {study.study_name}: {output}. Actor-only audit passed; no training started.')
            print('PI reference scores:', [(r['speed_scale'], round(r['objective']['score'], 3)) for r in references])
            return
        if any(t.state == optuna.trial.TrialState.RUNNING for t in study.trials):
            raise RuntimeError('Abandoned RUNNING trial found: inspect its saved artifacts before continuation')
        assert_isolated(78, 'nino_rough_78')
        processes = ReliableRoughProcesses(os.environ.copy(), pi_integrator_profile='conditional_v1')
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

        def run_trial(trial):
            assert_trial_inputs(comparable)
            directory = output / f'trial_{trial.number:04d}'
            directory.mkdir(exist_ok=False)
            cfg = sample_config(trial, base)
            validate_trial_config(cfg, comparable)
            config_path = directory / 'trial.yaml'
            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
            trial.set_user_attr('directory', str(directory))
            try:
                assert_isolated(78, 'nino_rough_78')
                processes.launch(world, directory, False)
                assert_trial_inputs(comparable, live=True)
                processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
                    '--config', config_path, '--timeout', 60], directory / 'profile.log', timeout=65)
                command = train_command(comparable, config_path, directory / 'train')
                command += ['--preflight-timeout', '60']
                processes.run(command, directory / 'train.log')
                models = list((directory / 'train').glob('*/nino_ppo_final.zip'))
                if len(models) != 1:
                    raise RuntimeError('Expected exactly one completed trial model')
                model = models[0]
                trial.set_user_attr('comparable_training', verify_training_result(model, cfg, comparable))
                trial.set_user_attr('model', str(model))
                assert_trial_inputs(comparable, live=True)
                seeds = [s['seed'] for s in objective['scenarios']]
                processes.run(['ros2', 'run', 'nino_rl', 'evaluate', '--config', model.parent / 'ppo.yaml',
                    '--model', model, '--device', args.device, '--seeds', *seeds,
                    '--output', directory / 'eval'], directory / 'evaluation.log')
                summaries = list((directory / 'eval').glob('*/summary.json'))
                if len(summaries) != 1:
                    raise RuntimeError('Expected one complete trial evaluation')
                assert_trial_inputs(comparable, live=True)
                return record(trial, summaries[0], objective)
            except Exception as error:
                trial.set_user_attr('execution_error', f'{type(error).__name__}: {error}')
                raise
            finally:
                processes.close()

        def export_best(study, _trial=None):
            complete = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
            qualified = [t for t in complete if t.user_attrs.get('arrival_feasible')]
            if not qualified:
                (output / 'best_infeasible.json').write_text(json.dumps(
                    {'reason': 'No arrival-qualified completed trial yet'}, indent=2) + '\n')
                return
            best = max(qualified, key=lambda t: t.value)
            (output / 'best_trial.yaml').write_text((Path(best.user_attrs['directory']) / 'trial.yaml').read_text())
            (output / 'best_model.txt').write_text(best.user_attrs['model'] + '\n')
            (output / 'best.json').write_text(json.dumps(dict(trial=best.number, score=best.value,
                objective=best.user_attrs['evaluation_objective'], model=best.user_attrs['model'],
                pi_reference_scores=[r['objective']['score'] for r in references]), indent=2) + '\n')
            (output / 'best_infeasible.json').unlink(missing_ok=True)

        try:
            study.optimize(run_trial, n_trials=args.trials, n_jobs=1, callbacks=[export_best])
        finally:
            processes.close()
            export_best(study)
        print(f'Study finished: {output}. Validate selected settings on held-out seeds before long training.')


if __name__ == '__main__':
    main()
