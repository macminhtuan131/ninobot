#!/usr/bin/env python3
"""Evaluate the selected flat policy and PI on held-out matching scenarios."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=62000)
    parser.add_argument('--episodes', type=int, default=24)
    parser.add_argument('--output', type=Path, default=ROOT / 'rl_runs/flat_optuna_holdout_v1')
    args = parser.parse_args()
    if args.seed < 0 or args.episodes < 1:
        parser.error('Use nonnegative seed and positive episodes')
    os.chdir(ROOT)
    # Avoid importing the isolated rough snapshot into this flat process.
    overlay = str(ROOT / 'src/nino_rl')
    sys.path.insert(0, overlay)
    os.environ['PYTHONPATH'] = overlay + os.pathsep + os.environ.get('PYTHONPATH', '')
    os.environ.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    import optuna
    from nino_rl.core import load_config
    from nino_rl.evaluation import compare_summaries
    from nino_rl.tuning_trials import assert_trial_inputs, verify_training_result, digest
    from nino_rl.tuning_objective import make_objective_contract, read_episode_rows, score_episodes
    from train_rough_curriculum import Processes, assert_isolated, complete_evaluation

    study_dir = ROOT / 'rl_runs/flat_focused_optuna_v1'
    plan = json.loads((study_dir / 'trial_plan.json').read_text())
    study = optuna.load_study(study_name='combined_flat_section', storage='sqlite:///' + str(study_dir / 'study.db'))
    if any(t.state == optuna.trial.TrialState.RUNNING for t in study.trials):
        raise RuntimeError('Flat tuning is still running')
    best = study.best_trial
    if not best.user_attrs.get('arrival_feasible'):
        raise RuntimeError('Selected trial did not qualify for physical arrival')
    comparable = plan['trials']
    assert_trial_inputs(comparable)
    model = Path(best.user_attrs['model'])
    config_path = model.parent / 'ppo.yaml'
    config = load_config(config_path)
    if verify_training_result(model, config, comparable) != best.user_attrs['comparable_training']:
        raise ValueError('Selected model training evidence differs from the trial contract')
    seeds = list(range(args.seed, args.seed + args.episodes))
    if set(seeds) & {s['seed'] for s in plan['evaluation_objective']['scenarios']}:
        raise ValueError('Holdout seeds overlap with tuning evaluation scenarios')
    objective = make_objective_contract(config, ROOT / 'src/nino_rl/config/optuna_objective.yaml',
                                       course='flat', episodes=args.episodes, seed=args.seed)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    contract = dict(selected_trial=best.number, model=str(model), model_sha256=digest(model),
        config_sha256=digest(config_path), source_trial_contract=comparable['sha256'],
        evaluation_objective=objective, scenarios=seeds, baseline_speed_scale=1.0,
        runner_sha256=digest(Path(__file__)))
    path = output / 'validation_plan.json'
    if path.exists() and json.loads(path.read_text()) != contract:
        raise ValueError('Validation conditions changed; use a new output directory')
    path.write_text(json.dumps(contract, indent=2) + '\n')
    assert_isolated(79, 'nino_flat_79')
    processes = Processes(os.environ.copy(), pi_integrator_profile='conditional_v1')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        for label, baseline in [('ppo', False), ('pi', True)]:
            directory = output / label
            cached = complete_evaluation(directory, args.episodes)
            if cached:
                if cached[1].get('evaluation_seeds') != seeds:
                    raise ValueError('Cached evaluation uses different seeds')
                continue
            assert_trial_inputs(comparable)
            directory.mkdir(parents=True, exist_ok=True)
            processes.world = processes.start(['ros2', 'launch', 'nino_rl', 'training_sim.launch.py',
                f'world:={comparable["world"]}', 'world_name:=combined_flat_section',
                'headless:=true', 'pi_integrator_profile:=conditional_v1'], directory / 'gazebo.log')
            processes.run(['ros2', 'run', 'nino_rl', 'wait_for_sim'], directory / 'readiness.log', timeout=90)
            assert_trial_inputs(comparable, live=True)
            processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
                           '--config', config_path, '--timeout', 60], directory / 'profile.log', timeout=65)
            command = ['ros2', 'run', 'nino_rl', 'evaluate_baseline' if baseline else 'evaluate',
                       '--config', config_path, '--seeds', *seeds, '--output', directory]
            if baseline:
                command += ['--baseline-speed-scale', '1.0']
            else:
                command += ['--model', model, '--device', comparable['device']]
            print(f'Running {label}: {args.episodes} held-out episodes; {directory / "evaluation.log"}', flush=True)
            processes.run(command, directory / 'evaluation.log')
            assert_trial_inputs(comparable, live=True)
            processes.close()
    finally:
        processes.close()
    result = {}
    for label in ('ppo', 'pi'):
        evidence = complete_evaluation(output / label, args.episodes)
        if evidence is None:
            raise RuntimeError(f'{label} evaluation incomplete')
        summary = evidence[1]
        paths = [f for f in (output / label).glob('*/summary.json') if json.loads(f.read_text()) == summary]
        if len(paths) != 1:
            raise ValueError('Ambiguous evaluation evidence')
        rows = read_episode_rows(paths[0].parent / 'episodes.csv')
        result[label] = dict(summary=str(paths[0]), objective=score_episodes(rows, objective), report=summary)
    result['comparison'] = compare_summaries(result['pi']['report'], result['ppo']['report'])
    (output / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print('Validation complete:', output / 'comparison.json', flush=True)
    print(json.dumps(result['comparison'], indent=2), flush=True)


if __name__ == '__main__':
    main()
