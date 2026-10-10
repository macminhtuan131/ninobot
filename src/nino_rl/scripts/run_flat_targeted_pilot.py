#!/usr/bin/env python3
"""One evidence-selected actor-head pilot, with a fresh critic and optimizer."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]

INITIALIZER = '''"""Frozen pilot actor initialization; reward/actions/controller are unchanged."""
from copy import deepcopy
import math
import torch
from nino_rl.model_transfer import initialize_actor

def initialize_targeted_actor(target, source, config):
    before = deepcopy(target.policy.state_dict())
    keys = initialize_actor(target, source)
    settings = config['flat_targeted_pilot']['initialization']
    with torch.no_grad():
        if settings['reset_speed']:
            target.policy.action_net.weight[0].zero_()
            target.policy.action_net.bias[0] = 2. * settings['speed_scale'] - 1.
            target.policy.log_std[0] = math.log(settings['speed_action_std'])
        if settings['reset_yaw']:
            target.policy.action_net.weight[1].zero_()
            target.policy.action_net.bias[1].zero_()
            target.policy.log_std[1] = math.log(settings['yaw_action_std'])
    for key, value in target.policy.state_dict().items():
        if key.startswith(('vf_features_extractor.', 'mlp_extractor.value_net.', 'value_net.')):
            if not torch.equal(value, before[key]):
                raise ValueError('Actor initialization modified a critic tensor')
    if target.num_timesteps != 0 or target.policy.optimizer.state:
        raise ValueError('Pilot reused optimizer/counter state')
    return keys
'''


def choose_initialization(reports):
    """Descriptive decision rule, frozen before looking at pilot test scenarios."""
    full = reports['ppo']['objective']['quality_cost']
    # The speed ablation removes yaw; the yaw ablation removes speed scaling.
    arrivals = reports['ppo']['report']['success_rate']
    yaw_harmful = (reports['speed']['report']['success_rate'] >= arrivals
                   and reports['speed']['objective']['quality_cost'] < full)
    speed_harmful = (reports['yaw']['report']['success_rate'] >= arrivals
                     and reports['yaw']['objective']['quality_cost'] < full)
    if not yaw_harmful and not speed_harmful:
        # If interactions prevent isolation, test competence-centered initialization
        # rather than claiming one output has been identified as the cause.
        speed_harmful = yaw_harmful = True
        reason = 'Neither ablation improved fixed quality; test PI-centered actor heads as an interaction hypothesis'
    else:
        reason = 'Reset only heads whose removal improved fixed quality while preserving arrival feasibility'
    return dict(reset_speed=bool(speed_harmful), reset_yaw=bool(yaw_harmful),
                speed_scale=0.97, speed_action_std=0.08, yaw_action_std=0.04,
                reason=reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, default=ROOT / 'rl_runs/flat_speed_yaw_ablation_v1/comparison.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'rl_runs/flat_targeted_actor_pilot_v1')
    parser.add_argument('--timesteps', type=int, default=20480)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / 'src/nino_rl'))
    from nino_rl.core import load_config
    from nino_rl.tuning_trials import assert_trial_inputs, digest
    from nino_rl.tuning_objective import make_objective_contract, read_episode_rows, score_episodes
    from nino_rl.evaluation import compare_summaries, benchmark_id, prepare_evaluation_config
    from train_rough_curriculum import Processes, assert_isolated, complete_evaluation, checkpoint_steps
    import yaml

    if not args.comparison.is_file():
        raise ValueError('Finish the speed/yaw comparison before preparing this pilot')
    reports = json.loads(args.comparison.read_text())
    for label in ('pi', 'ppo', 'speed', 'yaw'):
        if not reports[label]['report']['complete']:
            raise ValueError('Comparison must finish before selecting a pilot')
        compare_summaries(reports['pi']['report'], reports[label]['report'])
    previous = json.loads((ROOT / 'rl_runs/flat_optuna_holdout_v1/validation_plan.json').read_text())
    study = json.loads((ROOT / 'rl_runs/flat_focused_optuna_v1/trial_plan.json').read_text())['trials']
    assert_trial_inputs(study)
    model = Path(previous['model'])
    if digest(model) != previous['model_sha256']:
        raise ValueError('Source actor changed')
    config = load_config(model.parent / 'ppo.yaml')
    initialization = choose_initialization(reports)
    if args.timesteps < 1024 or args.timesteps % int(config['ppo']['n_steps']):
        raise ValueError('Pilot budget must cover an exact positive number of complete rollouts')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    overlay = output / 'python'
    package = overlay / 'nino_rl'
    if not package.exists():
        shutil.copytree(ROOT / 'src/nino_rl/nino_rl', package, ignore=shutil.ignore_patterns('__pycache__'))
        (package / 'pilot_initialization.py').write_text(INITIALIZER)
        path = package / 'train.py'
        code = path.read_text()
        before = 'from nino_rl.model_transfer import initialize_actor\n                validate_action_mode(source, config)\n                actor_keys = initialize_actor(model, source)'
        after = 'from nino_rl.pilot_initialization import initialize_targeted_actor\n                validate_action_mode(source, config)\n                actor_keys = initialize_targeted_actor(model, source, config)'
        if code.count(before) != 1:
            raise ValueError('Unexpected trainer source; pilot snapshot not usable')
        code = code.replace(before, after)
        before = 'actor_transfer = dict(source=str(args.init_model.resolve()),'
        after = 'actor_transfer = dict(targeted_head_initialization=config["flat_targeted_pilot"]["initialization"],\n                    source=str(args.init_model.resolve()),'
        if code.count(before) != 1:
            raise ValueError('Unexpected actor-transfer metadata source')
        code = code.replace(before, after)
        compile(code, str(path), 'exec')
        path.write_text(code)
    if ('actor_keys = initialize_targeted_actor(model, source, config)' not in (package / 'train.py').read_text()
            or (package / 'pilot_initialization.py').read_text() != INITIALIZER):
        raise ValueError('Pilot snapshot is incomplete or differs; preserve it and use a new output directory')
    assets = {str(path): digest(path) for path in sorted(package.rglob('*.py'))}
    experiment = dict(revision='flat_targeted_actor_heads_v1', initialization=initialization,
        source_actor=str(model), source_actor_sha256=digest(model),
        comparison_sha256=digest(args.comparison), snapshot_assets=assets,
        training_steps=args.timesteps, critic='fresh', optimizer='fresh', training_counter=0,
        unchanged=['reward', 'action meanings', 'controller', 'estimator', 'terrain', 'physical arrival criteria'])
    config['flat_targeted_pilot'] = experiment
    # Keep diagnostic provenance outside the physical task benchmark ID.
    settings = ROOT / 'src/nino_rl/config/optuna_objective.yaml'
    scoring_config = deepcopy(config)
    scoring_config.pop('flat_targeted_pilot')
    objective = make_objective_contract(scoring_config, settings, course='flat', episodes=24, seed=63000)
    plan = dict(experiment=experiment, evaluation_objective=objective,
        source_trial_contract=study['sha256'], evaluation_seeds=list(range(63000, 63024)),
        gates=dict(arrivals=24, mean_completion_seconds=18.5, physical_rmse_ratio_max=1.05,
                   comfort_or_slip_ratio_max=0.90, other_metric_ratio_max=1.0),
        interpretation='A single training seed pilot; new scenario seeds, unchanged two-cable task; not a generalization claim')
    path = output / 'pilot_plan.json'
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError('Pilot contract changed; use a new output directory')
    path.write_text(json.dumps(plan, indent=2) + '\n')
    config_path = output / 'pilot.yaml'
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    # Separate evaluation config removes only provenance, never task settings.
    evaluation_config = output / 'evaluation.yaml'
    evaluation_config.write_text(yaml.safe_dump(scoring_config, sort_keys=False))
    if benchmark_id(prepare_evaluation_config(scoring_config)) != reports['pi']['report']['benchmark_id']:
        raise ValueError('Pilot altered physical benchmark settings')
    print('Pilot initialization:', json.dumps(initialization), flush=True)
    print('Frozen plan:', path, flush=True)
    if args.prepare_only:
        return
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    os.environ.update({key: env[key] for key in ('ROS_DOMAIN_ID', 'NINO_ROS_DOMAIN_ID', 'GZ_PARTITION', 'ROS_AUTOMATIC_DISCOVERY_RANGE')})
    env['PYTHONPATH'] = str(overlay) + os.pathsep + str(ROOT / 'src/nino_rl') + os.pathsep + env.get('PYTHONPATH', '')
    assert_isolated(79, 'nino_flat_79')
    processes = Processes(env, pi_integrator_profile='conditional_v1')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    def launch(directory, profile):
        assert_trial_inputs(study)
        processes.world = processes.start(['ros2', 'launch', 'nino_rl', 'training_sim.launch.py',
            f'world:={study["world"]}', 'world_name:=combined_flat_section', 'headless:=true',
            'pi_integrator_profile:=conditional_v1'], directory / 'gazebo.log')
        processes.run(['ros2', 'run', 'nino_rl', 'wait_for_sim'], directory / 'readiness.log', timeout=90)
        assert_trial_inputs(study, live=True)
        processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
            '--config', profile, '--timeout', 60], directory / 'profile.log', timeout=65)

    try:
        models = list((output / 'train').glob('*/nino_ppo_final.zip'))
        if len(models) > 1:
            raise ValueError('Ambiguous pilot models')
        if not models:
            if list((output / 'train').glob('*/nino_ppo_interrupted.zip')):
                raise ValueError('Interrupted pilot exists; inspect checkpoint before starting another run')
            launch(output / 'train', config_path)
            print(f'Training one {args.timesteps}-step targeted pilot', flush=True)
            processes.run(['ros2', 'run', 'nino_rl', 'train', '--config', config_path,
                '--device', 'cuda', '--init-model', model, '--timesteps', args.timesteps,
                '--checkpoint-every', 10240, '--preflight-timeout', 60,
                '--output', output / 'train'], output / 'train/training.log')
            processes.close()
            models = list((output / 'train').glob('*/nino_ppo_final.zip'))
        if len(models) != 1 or checkpoint_steps(models[0]) != args.timesteps:
            raise ValueError('Pilot did not complete the frozen step budget')
        trained = models[0]
        result = {}
        for label in ('ppo', 'pi'):
            directory = output / label
            cached = complete_evaluation(directory, 24)
            if cached is None:
                launch(directory, evaluation_config)
                command = ['ros2', 'run', 'nino_rl', 'evaluate_baseline' if label == 'pi' else 'evaluate',
                    '--config', evaluation_config, '--seeds', *plan['evaluation_seeds'], '--output', directory]
                if label == 'ppo':
                    command += ['--model', trained, '--device', 'cuda']
                else:
                    command += ['--baseline-speed-scale', 1.0]
                print(f'Evaluating {label} on 24 fresh matching seeds', flush=True)
                processes.run(command, directory / 'evaluation.log')
                processes.close()
                cached = complete_evaluation(directory, 24)
            if cached is None or cached[1]['evaluation_seeds'] != plan['evaluation_seeds']:
                raise ValueError('Incomplete or incompatible pilot evaluation')
            paths = [p for p in directory.glob('*/summary.json') if json.loads(p.read_text()) == cached[1]]
            if len(paths) != 1:
                raise ValueError('Ambiguous pilot evaluation')
            result[label] = dict(summary=str(paths[0]), report=cached[1],
                objective=score_episodes(read_episode_rows(paths[0].parent / 'episodes.csv'), objective))
        result['comparison'] = compare_summaries(result['pi']['report'], result['ppo']['report'])
        metrics = result['comparison']['metrics']
        ratio = lambda name: metrics[name]['candidate'] / metrics[name]['baseline']
        vibration = ratio('rms_vertical_acceleration_m_s2')
        slip = ratio('rms_wheel_slip')
        result['gates'] = dict(
            physical_arrival=result['ppo']['report']['success_rate'] == 1.0,
            completion=metrics['time_seconds']['candidate'] <= 18.5,
            tracking=ratio('truth_path_rmse_m') <= 1.05,
            quality=(vibration <= .90 and slip <= 1.) or (slip <= .90 and vibration <= 1.),
            vibration_ratio=vibration, slip_ratio=slip)
        result['promote'] = all(result['gates'][key] for key in ('physical_arrival', 'completion', 'tracking', 'quality'))
        result['model'] = str(trained)
        (output / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        print('Pilot finished:', output / 'comparison.json', flush=True)
        print(json.dumps(result['gates'], indent=2), flush=True)
    finally:
        processes.close()


if __name__ == '__main__':
    main()
