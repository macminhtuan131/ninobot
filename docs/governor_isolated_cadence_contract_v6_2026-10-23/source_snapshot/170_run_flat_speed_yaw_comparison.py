#!/usr/bin/env python3
"""Isolate the selected flat actor's speed/yaw, without changing study code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]


def reference_action(action, mode):
    """Override only the executed component; observations retain executed history."""
    import numpy as np
    result = np.array(action, dtype=np.float32, copy=True)
    if result.shape != (2,) or not np.isfinite(result).all():
        raise ValueError('Reference ablation requires two finite speed/yaw actions')
    if mode == 'speed':
        result[1] = 0.0
    elif mode == 'yaw':
        result[0] = 1.0
    else:
        raise ValueError('Select speed or yaw')
    return result


def snapshot(output):
    package = output / 'python/nino_rl'
    source = ROOT / 'src/nino_rl/nino_rl'
    if not package.exists():
        shutil.copytree(source, package, ignore=shutil.ignore_patterns('__pycache__'))
        path = package / 'evaluation.py'
        code = path.read_text()
        changes = [
            ('parser.add_argument("--speed-only", action="store_true",',
             'parser.add_argument("--reference-ablation", choices=("speed", "yaw"), required=True)\n        parser.add_argument("--speed-only", action="store_true",'),
            ('action = baseline_action(config) if baseline else model.predict(observation, deterministic=True)[0]',
             'action = baseline_action(config) if baseline else model.predict(observation, deterministic=True)[0]\n                if not baseline:\n                    from flat_reference_ablation import reference_action\n                    action = reference_action(action, args.reference_ablation)'),
            ('"action_ablation": "speed_only" if speed_only else "none",',
             '"action_ablation": args.reference_ablation if not baseline else "none",'),
        ]
        for before, after in changes:
            if code.count(before) != 1:
                raise ValueError('Unexpected evaluator source; snapshot not usable')
            code = code.replace(before, after)
        path.write_text(code)
        shutil.copyfile(Path(__file__), package.parent / 'flat_reference_ablation.py')
    return package.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'rl_runs/flat_speed_yaw_ablation_v1')
    args = parser.parse_args()
    os.chdir(ROOT)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'src/nino_rl'))
    from nino_rl.core import load_config
    from nino_rl.evaluation import compare_summaries
    from nino_rl.tuning_trials import assert_trial_inputs, digest
    from nino_rl.tuning_objective import read_episode_rows, score_episodes
    from train_rough_curriculum import Processes, assert_isolated, complete_evaluation

    previous = json.loads((ROOT / 'rl_runs/flat_optuna_holdout_v1/comparison.json').read_text())
    holdout = json.loads((ROOT / 'rl_runs/flat_optuna_holdout_v1/validation_plan.json').read_text())
    study = json.loads((ROOT / 'rl_runs/flat_focused_optuna_v1/trial_plan.json').read_text())['trials']
    assert_trial_inputs(study)
    model = Path(holdout['model'])
    if digest(model) != holdout['model_sha256']:
        raise ValueError('Selected actor changed')
    config_path = model.parent / 'ppo.yaml'
    config = load_config(config_path)
    if config['action_mode'] != 'speed_yaw_reference':
        raise ValueError('This diagnostic requires the two-action reference policy')
    overlay = snapshot(output)
    assets = {str(path): digest(path) for path in sorted(overlay.rglob('*.py'))}
    contract = dict(revision='flat_reference_ablation_v1', model=str(model),
        model_sha256=digest(model), config_sha256=digest(config_path),
        source_contract=study['sha256'], snapshot_assets=assets,
        seeds=holdout['scenarios'], evaluation_objective=holdout['evaluation_objective'],
        modes={'speed': 'PPO speed; yaw residual zero; estimated-pose PI steering',
               'yaw': 'speed scale one; PPO yaw residual'},
        reused_reports={label: previous[label]['summary'] for label in ('pi', 'ppo')})
    path = output / 'comparison_plan.json'
    if path.exists() and json.loads(path.read_text()) != contract:
        raise ValueError('Diagnostic contract changed; use a new output directory')
    path.write_text(json.dumps(contract, indent=2) + '\n')
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    os.environ.update({key: env[key] for key in ('ROS_DOMAIN_ID', 'NINO_ROS_DOMAIN_ID',
                                               'GZ_PARTITION', 'ROS_AUTOMATIC_DISCOVERY_RANGE')})
    env['PYTHONPATH'] = str(overlay) + os.pathsep + str(ROOT / 'src/nino_rl') + os.pathsep + env.get('PYTHONPATH', '')
    assert_isolated(79, 'nino_flat_79')
    processes = Processes(env, pi_integrator_profile='conditional_v1')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    results = {label: previous[label] for label in ('pi', 'ppo')}
    try:
        for mode in ('speed', 'yaw'):
            directory = output / mode
            cached = complete_evaluation(directory, len(contract['seeds']))
            if cached is None:
                assert_trial_inputs(study)
                processes.world = processes.start(['ros2', 'launch', 'nino_rl', 'training_sim.launch.py',
                    f'world:={study["world"]}', 'world_name:=combined_flat_section',
                    'headless:=true', 'pi_integrator_profile:=conditional_v1'], directory / 'gazebo.log')
                processes.run(['ros2', 'run', 'nino_rl', 'wait_for_sim'], directory / 'readiness.log', timeout=90)
                assert_trial_inputs(study, live=True)
                processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
                    '--config', config_path, '--timeout', 60], directory / 'profile.log', timeout=65)
                print(f'Running {mode} ablation on {len(contract["seeds"])} matching seeds', flush=True)
                processes.run(['ros2', 'run', 'nino_rl', 'evaluate', '--config', config_path,
                    '--model', model, '--device', 'cuda', '--reference-ablation', mode,
                    '--seeds', *contract['seeds'], '--control-trace', '--output', directory], directory / 'evaluation.log')
                assert_trial_inputs(study, live=True)
                processes.close()
                cached = complete_evaluation(directory, len(contract['seeds']))
            if cached is None or cached[1]['evaluation_seeds'] != contract['seeds'] or cached[1]['action_ablation'] != mode:
                raise ValueError('Incomplete or incompatible diagnostic evidence')
            matches = [p for p in directory.glob('*/summary.json') if json.loads(p.read_text()) == cached[1]]
            if len(matches) != 1:
                raise ValueError('Ambiguous diagnostic evidence')
            results[mode] = dict(summary=str(matches[0]), report=cached[1],
                objective=score_episodes(read_episode_rows(matches[0].parent / 'episodes.csv'), contract['evaluation_objective']))
            results[mode]['versus_pi'] = compare_summaries(previous['pi']['report'], cached[1])
    finally:
        processes.close()
    (output / 'comparison.json').write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
    for label, item in results.items():
        metrics = item['report']['metrics_all_episodes']
        print(label, 'arrival', item['report']['success_rate'],
              'time', metrics['time_seconds']['mean'],
              'physical RMSE', metrics['truth_path_rmse_m']['mean'],
              'vibration', metrics['rms_vertical_acceleration_m_s2']['mean'],
              'slip', metrics['rms_wheel_slip']['mean'], 'score', item['objective']['score'], flush=True)


if __name__ == '__main__':
    main()
