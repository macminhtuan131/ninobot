#!/usr/bin/env python3
"""Run the two fixed flat pilots sequentially and write their joint comparison."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
COURSES = ('flat_value_scaled_pilot_v1', 'flat_energy_scaled_pilot_v1')
METRICS = ('time_seconds', 'truth_path_rmse_m', 'rms_vertical_acceleration_m_s2',
           'peak_vertical_acceleration_m_s2', 'rms_wheel_slip')


def read(path):
    return json.loads(Path(path).read_text())


def verify_plans(plans):
    first, second = plans
    for key in ('source_trial_contract', 'evaluation_seeds', 'promotion_gates'):
        if first[key] != second[key]:
            raise ValueError(f'Pilot comparison mismatch: {key}')
    for key in ('source_actor', 'source_actor_sha256', 'critic', 'optimizer',
                'actor', 'training_counter', 'training_steps', 'training_reward_scale'):
        if first['experiment'][key] != second['experiment'][key]:
            raise ValueError(f'Pilot initialization mismatch: {key}')
    if first['experiment']['training_steps'] != 20480 or first['evaluation_seeds'] != list(range(64000, 64024)):
        raise ValueError('Expected the frozen 20,480-step/24-seed comparison')
    if first['evaluation_objective'] != second['evaluation_objective']:
        raise ValueError('Pilot evaluation objectives differ')


def critic_summary(run):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    accumulator = EventAccumulator(str(run / 'tensorboard/PPO_1'))
    accumulator.Reload()
    tags = accumulator.Tags()['scalars']
    names = [name for name in tags if name.startswith('critic/') or name in
             ('train/explained_variance', 'train/value_loss', 'train/policy_gradient_loss')]
    curves = {name: [dict(step=row.step, value=row.value) for row in accumulator.Scalars(name)] for name in names}
    if not curves.get('critic/pre_update_explained_variance'):
        raise ValueError('New critic diagnostics were not recorded')
    return dict(curves=curves, last={name: rows[-1] for name, rows in curves.items() if rows},
                units='learner rewards = raw task rewards × 0.01; value losses are squared learner units')


def compare(output):
    sys.path[:0] = [str(ROOT / 'src/nino_rl'), str(Path(__file__).parent)]
    from nino_rl.evaluation import compare_summaries
    from nino_rl.tuning_objective import read_episode_rows
    from nino_rl.tuning_trials import digest
    from train_rough_curriculum import checkpoint_steps
    import numpy as np
    folders = [ROOT / 'rl_runs' / name for name in COURSES]
    plans = [read(folder / 'pilot_plan.json') for folder in folders]
    verify_plans(plans)
    if digest(plans[0]['experiment']['source_actor']) != plans[0]['experiment']['source_actor_sha256']:
        raise ValueError('Source actor changed')
    results = [read(folder / 'comparison.json') for folder in folders]
    for folder, plan, result in zip(folders, plans, results):
        models = list((folder / 'train').glob('*/nino_ppo_final.zip'))
        if len(models) != 1 or checkpoint_steps(models[0]) != 20480:
            raise ValueError('Pilot has not completed its exact training budget')
        transfer = read(models[0].with_name('actor_transfer.json'))
        if transfer['source_sha256'] != plan['experiment']['source_actor_sha256'] or any(
                transfer[key] != expected for key, expected in
                (('critic', 'fresh'), ('optimizer', 'fresh'), ('training_counter', 0))):
            raise ValueError('Live actor-transfer evidence differs from the pilot plan')
        for label in ('ppo', 'pi'):
            report = result[label]['report']
            if not report['complete'] or report['evaluation_seeds'] != plan['evaluation_seeds']:
                raise ValueError('Evaluation is incomplete or uses different seeds')
            if result[label]['objective']['objective_sha256'] != plan['evaluation_objective']['sha256']:
                raise ValueError('Evaluation used a different fixed objective')
        result['critic_diagnostics'] = critic_summary(models[0].parent)
    comparison = compare_summaries(results[0]['ppo']['report'], results[1]['ppo']['report'])
    pi_repeat = compare_summaries(results[0]['pi']['report'], results[1]['pi']['report'])
    rows = [read_episode_rows(Path(result['ppo']['summary']).with_name('episodes.csv')) for result in results]
    indexed = [{int(row['seed']): row for row in group} for group in rows]
    expected_seeds = plans[0]['evaluation_seeds']
    if any(len(group) != 24 or sorted(group) != expected_seeds for group in indexed):
        raise ValueError('Incomplete or duplicated evaluation seed rows')
    rng = np.random.default_rng(42)
    draws = rng.integers(0, 24, size=(10000, 24))
    paired = {}
    for metric in METRICS:
        differences = np.array([float(indexed[1][seed][metric]) - float(indexed[0][seed][metric])
                                for seed in expected_seeds])
        low, high = np.quantile(differences[draws].mean(axis=1), [.025, .975])
        paired[metric] = dict(mean_difference=float(differences.mean()), ci95=[float(low), float(high)])
    combined = dict(scale_only=results[0], aligned_impact=results[1], paired_ppo_comparison=comparison,
                    repeated_pi_comparison=pi_repeat, paired_scenario_bootstrap=paired,
                    uncertainty='Paired scenario uncertainty only; one training seed, asynchronous Gazebo is not bitwise deterministic',
                    same_starting_actor=plans[0]['experiment']['source_actor'],
                    fixed_objective_sha256=plans[0]['evaluation_objective']['sha256'],
                    training_steps_per_pilot=20480, evaluation_seeds=expected_seeds,
                    no_automatic_optuna_start=True)
    (output / 'comparison.json').write_text(json.dumps(combined, indent=2, allow_nan=False) + '\n')
    lines = ['# Flat reward validation — scale versus aligned impacts', '',
             'Both pilots completed 20,480 steps from the same actor with a fresh critic/optimizer.',
             'PPO and PI were evaluated on matching seeds 64000–64023 with fixed physical scoring.', '',
             '| Metric | Scale PI | Scale PPO | Aligned PI | Aligned PPO |',
             '|---|---:|---:|---:|---:|']
    reports = [results[0]['pi']['report'], results[0]['ppo']['report'],
               results[1]['pi']['report'], results[1]['ppo']['report']]
    lines.append('| Physical arrivals | ' + ' | '.join(f"{round(r['success_rate'] * 24)}/24" for r in reports) + ' |')
    for metric in METRICS:
        lines.append('| ' + metric + ' | ' + ' | '.join(f"{r['metrics_all_episodes'][metric]['mean']:.5f}" for r in reports) + ' |')
    lines += ['', '| Critic diagnostic (final logged) | Scale-only | Aligned impacts |', '|---|---:|---:|']
    for metric in ('train/explained_variance', 'critic/pre_update_explained_variance', 'train/value_loss'):
        values = [result['critic_diagnostics']['last'].get(metric, {}).get('value') for result in results]
        lines.append('| ' + metric + ' | ' + ' | '.join('missing' if value is None else f'{value:.6f}' for value in values) + ' |')
    lines += ['', 'Value MSE is in scaled learner units. Lower MSE alone does not establish better fit;',
              'inspect explained variance and physical evaluation performance.', '', '## Promotion gates', '']
    for label, result in zip(('Scale-only', 'Aligned impacts'), results):
        lines.append(f"- {label}: {json.dumps(result['gates'])}; promote={result['promote']}.")
    lines += ['', '## Paired PPO differences (aligned minus scale-only)', '',
              '| Metric | Mean difference | Scenario bootstrap 95% interval |', '|---|---:|---:|']
    for metric, result in paired.items():
        lines.append(f"| {metric} | {result['mean_difference']:.6f} | [{result['ci95'][0]:.6f}, {result['ci95'][1]:.6f}] |")
    lines += ['', 'Negative time/error/vibration/slip differences favor the aligned profile.',
              'These intervals cover evaluation scenarios, not independent training seeds.',
              'Check arrival counts before interpreting quality gains; early failures can shorten episodes.',
              'Repeated PI evaluations also expose simulation variation under identical controller settings.',
              'Raw episode returns are not comparable between different reward formulas.', '',
              'No Optuna or further training is launched automatically. Full evidence: `comparison.json`.', '']
    (output / 'REPORT.md').write_text('\n'.join(lines))
    return combined


def process_identity(pid):
    try:
        proc = Path('/proc') / str(pid)
        command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
        start = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        return command, start
    except (OSError, IndexError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-for-pid', type=int, help='Adopt an already-started scale-only worker; no duplicate launch')
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'rl_runs/flat_reward_validation_v1')
    args = parser.parse_args()
    os.chdir(ROOT)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'worker.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sys.path.insert(0, str(Path(__file__).parent))
        from train_rough_curriculum import Processes
        processes = Processes(os.environ.copy())
        adopted = process_identity(args.wait_for_pid) if args.wait_for_pid else None
        if args.wait_for_pid and adopted and ('run_flat_reward_pilot.py' not in adopted[0]
                or 'combined_flat_value_scaled_pilot.yaml' not in adopted[0]):
            raise ValueError('Refusing to adopt an unrelated process')
        state = dict(pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat(),
                     stage='starting', completed=[], output=str(output))

        def save(stage, **extra):
            state.update(stage=stage, updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
            temporary = output / 'status.tmp'
            temporary.write_text(json.dumps(state, indent=2) + '\n')
            temporary.replace(output / 'status.json')
            print(stage, flush=True)

        def interrupt(*_):
            raise KeyboardInterrupt()

        signal.signal(signal.SIGTERM, interrupt)
        try:
            if not args.report_only:
                plans = [read(ROOT / 'rl_runs' / course / 'pilot_plan.json') for course in COURSES]
                verify_plans(plans)
                for index, profile in enumerate(('combined_flat_value_scaled_pilot.yaml', 'combined_flat_energy_scaled_pilot.yaml')):
                    stage = 'scale_only' if index == 0 else 'aligned_impact'
                    if index == 0 and args.wait_for_pid:
                        save(stage, adopted_pid=args.wait_for_pid)
                        while adopted is not None and process_identity(args.wait_for_pid) == adopted:
                            time.sleep(1.)
                        if not (ROOT / 'rl_runs' / COURSES[0] / 'comparison.json').exists():
                            raise RuntimeError('Adopted scale-only worker stopped before completing evaluation; aligned pilot remains queued')
                    else:
                        save(stage)
                        processes.run([sys.executable, str(Path(__file__).with_name('run_flat_reward_pilot.py')),
                            '--config', ROOT / 'src/nino_rl/config' / profile, '--run'], output / (stage + '.log'))
                    state['completed'].append(stage)
            save('comparing')
            compare(output)
            save('complete', report=str(output / 'REPORT.md'))
        except KeyboardInterrupt:
            if adopted and process_identity(args.wait_for_pid) == adopted:
                os.kill(args.wait_for_pid, signal.SIGINT)
            save('cancelled')
            raise
        except Exception as error:
            save('failed', error=str(error))
            raise
        finally:
            processes.close()


if __name__ == '__main__':
    main()
