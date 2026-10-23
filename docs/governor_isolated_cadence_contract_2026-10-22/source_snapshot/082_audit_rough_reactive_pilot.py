#!/usr/bin/env python3
"""Read-only audit of saved reactive PPO signals, history and reward totals.

Creates analysis artifacts only. Does not run ROS, modify a frozen experiment,
or infer unrecorded actor observations from incomplete diagnostic traces.
"""
import argparse
import ast
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import yaml


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def average_terms(rows):
    terms = [ast.literal_eval(row['reward_totals']) if isinstance(row['reward_totals'], str)
             else row['reward_totals'] for row in rows]
    return {key: float(np.mean([row[key] for row in terms])) for key in terms[0]}


def episode_audit(rows, config):
    c = config['reactive_probe']
    dt = np.array([float(r['step_dt_s']) for r in rows])
    phases = np.array([r['cue_phase'] for r in rows])
    scales = np.array([float(r['speed_scale']) for r in rows])
    disturbed = np.array([bool(int(r['cue_disturbed'])) for r in rows])
    triggers = [r for r in rows if int(r['cue_triggered'])]
    causes = lambda r: [name for name, field, threshold in (
        ('filtered_acceleration', 'cue_filtered_acceleration_m_s2', c['acceleration_threshold_m_s2']),
        ('body_rate', 'cue_body_rate_rad_s', c['body_rate_threshold_rad_s']),
        ('wheel_command_error', 'cue_wheel_error_m_s', c['wheel_error_threshold_m_s']))
        if float(r[field]) >= threshold]
    runs = []
    for i, row in enumerate(rows):
        if i == 0 or phases[i] != phases[i-1]:
            runs.append(dict(phase=phases[i], start_s=float(row['elapsed_s'])-dt[i], duration_s=0.))
        runs[-1]['duration_s'] += dt[i]
    holding = phases == 'holding'
    quiet = np.isin(phases, ['ready', 'cooldown']) & ~disturbed
    peak = np.array([float(r['step_imu_peak_m_s2']) for r in rows])
    # Next row's cue reads the preceding action's final sensor snapshot;
    # an interval peak is not the EMA threshold used by this detector.
    ending = np.array([abs(float(r['cue_vertical_m_s2'])) for r in rows[1:]])
    interval_high = peak[:-1] >= c['acceleration_threshold_m_s2']
    return dict(seed=int(rows[0]['seed']), duration_s=float(dt.sum()),
        trigger_count=len(triggers), triggers=[dict(time_s=float(r['elapsed_s'])-float(r['step_dt_s']),
            x_m=float(r['physical_x_m']), causes=causes(r)) for r in triggers],
        phase_seconds={phase: float(dt[phases == phase].sum()) for phase in set(phases)},
        longest_recovering_seconds=max([r['duration_s'] for r in runs if r['phase']=='recovering'] or [0.]),
        disturbed_seconds=float(dt[disturbed].sum()),
        disturbed_in_recovering_seconds=float(dt[disturbed & (phases == 'recovering')].sum()),
        holding_scale_mean=float(np.mean(scales[holding])) if holding.any() else None,
        quiet_scale_mean=float(np.mean(scales[quiet])) if quiet.any() else None,
        minimum_scale=float(scales.min()),
        mean_scale=float(np.mean(scales)),
        interval_peaks_above_1_5=int(interval_high.sum()),
        high_intervals_with_next_endpoint_below_1_5=int((interval_high & (ending < c['acceleration_threshold_m_s2'])).sum()),
        endpoint_vs_peak_qualification='Endpoint and integrated peak differ; this is not a false-negative rate for the EMA/body-rate/encoder detector.',
        raw_target_min=float(min(float(r['action_speed']) for r in rows)),
        phase_runs=runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('rl_runs/rough_reactive_reward_pilot_v1'))
    parser.add_argument('--output', type=Path, default=Path('docs/rough_reactive_audit_2026-10-11'))
    args = parser.parse_args()
    root = args.snapshot.resolve()
    config = yaml.safe_load((root/'config.yaml').read_text())
    contract = json.loads((root/'pilot_contract.json').read_text())
    # Check the pilot's own frozen assets without invoking a preparer or simulator.
    for group in ('assets', 'implementation'):
        for name, expected in contract[group].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                raise ValueError('Frozen input changed: '+name)
    train_paths = list((root/'train').glob('*/episodes.jsonl'))
    if len(train_paths) != 1:
        raise ValueError('Ambiguous training run')
    training = [json.loads(line) for line in train_paths[0].read_text().splitlines() if line.strip()]
    reward_groups = {}
    episodes = {}
    trace_groups = {}
    sources = [root/'config.yaml', root/'pilot_contract.json', root/'comparison.json',
               root/'reward_audit.json', train_paths[0], Path(__file__).resolve()]
    accounting_checks = []
    for controller in ('ppo', 'pi_full', 'pi_matched'):
        paths = list((root/'evaluation'/controller).glob('*/episodes.csv'))
        if len(paths) != 1:
            raise ValueError('Ambiguous evaluation: '+controller)
        records = read_csv(paths[0])
        by_seed = {int(r['seed']): r for r in records}
        reward_groups[controller] = dict(mean_terms=average_terms(records),
            mean_raw_return=float(np.mean([float(r['return']) for r in records])), episodes=len(records))
        sources.append(paths[0])
        trace_groups[controller] = []
        for path in sorted(paths[0].parent.glob('episode-*/control_trace.csv')):
            rows = read_csv(path)
            record = by_seed[int(rows[0]['seed'])]
            terms = ast.literal_eval(record['reward_totals'])
            np.testing.assert_allclose(sum(terms.values()), float(record['return']), atol=1e-9)
            weights = config['reward_v2']['longitudinal_weights']
            energy_cost = -weights['vibration']/weights['acceleration_sigma_m_s2']**2 * sum(
                float(r['step_imu_energy']) for r in rows)
            slip_cost = -weights['slip']/weights['slip_sigma']**2 * sum(
                float(r['step_slip_square'])*float(r['step_dt_s']) for r in rows)
            np.testing.assert_allclose(energy_cost, terms['vibration'], atol=1e-8)
            np.testing.assert_allclose(slip_cost, terms['slip'], atol=1e-8)
            accounting_checks.append(dict(controller=controller, seed=int(rows[0]['seed']),
                reward_sum_matches=True, vibration_trace_matches=True, slip_trace_matches=True))
            trace_groups[controller].append(rows)
            sources.append(path)
        episodes[controller] = [episode_audit(rows, config) for rows in trace_groups[controller]]
    training_stats = {}
    for name, records in (('all', training), ('first_10', training[:10]), ('last_10', training[-10:])):
        training_stats[name] = dict(episodes=len(records), mean_terms=average_terms(records),
            mean_raw_return=float(np.mean([r['return'] for r in records])),
            mean_time_s=float(np.mean([r['time_seconds'] for r in records])),
            mean_speed_scale=float(np.mean([r['mean_speed_scale'] for r in records])),
            lowest_episode_min_scale=float(min(r['min_speed_scale'] for r in records)))
    keys = reward_groups['ppo']['mean_terms']
    deltas = {reference: {k: reward_groups['ppo']['mean_terms'][k]-reward_groups[reference]['mean_terms'][k]
                         for k in keys} for reference in ('pi_full', 'pi_matched')}
    evidence = json.loads((root/'reward_audit.json').read_text())
    authority_pairs = {}
    for row in evidence['records']:
        authority_pairs.setdefault(row['seed'], {})[row['controller']] = row['return_raw']
    gains = [row['reactive']-row['pi'] for row in authority_pairs.values()]
    floor = config['longitudinal_control']['minimum_scale']
    initial_mean = 2*config['ppo']['initial_speed_scale']-1
    final_means = [float(r['action_speed']) for rows in trace_groups['ppo'] for r in rows]
    # Logged final std remains ~0.20. Evaluate tails in unsquashed action space.
    probabilities = {}
    for name, mean in (('initial_bias', initial_mean), ('final_mean_action', float(np.mean(final_means)))):
        probabilities[name] = {}
        for target in (.70, .76, .90):
            action = 2*(target-floor)/(1-floor)-1
            probabilities[name][str(target)] = .5*math.erfc((mean-action)/(.20*math.sqrt(2)))
    result = dict(frozen_assets_verified=True, optuna_held=True, accounting_checks=accounting_checks,
        reward_groups=reward_groups, ppo_minus_reference_terms=deltas, training=training_stats,
        detection=episodes,
        observation=dict(frame_size=56, history_frames=5, control_hz=10,
            oldest_to_newest_span_s=.4, imu_update_hz=50, reset_duplicates_first_frame=True,
            hardware_features='IMU quaternion, gyro XYZ, accel XYZ, tilt-compensated vertical accel, encoder velocities, estimated motion, horizontal LiDAR; route/reference and previous raw action.',
            missing=['cue EMA','cue phase/remaining hold/cooldown','executed ramp scale','IMU interval energy/peak','exact previously executed linear/yaw command'],
            caveat='No complete actor observation histories saved; causal dependence cannot be measured from these traces. No terrain preview or ground-truth velocity supplied to actor.'),
        exploration=dict(initial_actual_scale=floor+(1-floor)*config['ppo']['initial_speed_scale'],
            final_mean_raw_action=float(np.mean(final_means)), raw_action_std_approx=.20,
            scale_std_before_clipping=.20*(1-floor)/2,
            probability_one_target_at_or_below_scale=probabilities,
            qualification='Gaussian tails at initialization bias or mean final action, not measured event-conditioned rollout frequencies. Sustained slowdown also requires repeated low actions through the ramp.'),
        prior_authority_reward=dict(pairs=len(gains), reactive_better_count=sum(x>0 for x in gains),
            mean_gain=float(np.mean(gains)), median_gain=float(np.median(gains)),
            qualification=evidence['qualification']),
        limits=['One training seed, five paired fixed-map reset seeds.',
            'Endpoint trace cues omit original 50Hz IMU samples and full actor tensors.',
            'Reward totals are exact saved raw episode totals; only prior authority returns were reconstructed.',
            'No new simulation, policy training or hyperparameter tuning.'])
    args.output.mkdir(parents=True, exist_ok=True)
    result['sources_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (args.output/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = trace_groups['ppo'][0]
    t = np.array([float(r['elapsed_s']) for r in rows])
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), constrained_layout=True)
    axes[0].plot(t, [float(r['speed_scale']) for r in rows], label='PPO executed scale')
    axes[0].step(t, [float(r['cue_target_scale']) for r in rows], label='Scripted probe request (not applied)', alpha=.6)
    for r in episodes['ppo'][0]['phase_runs']:
        if r['phase'] in ('holding', 'recovering'):
            axes[0].axvspan(r['start_s'], r['start_s']+r['duration_s'],
                           color='orange' if r['phase']=='holding' else 'gray', alpha=.15)
    axes[0].set(ylabel='Speed scale', title='Seed 16100: orange hold, gray recovery; PPO stays near 0.975')
    axes[0].legend(fontsize=8)
    axes[1].plot(t, [float(r['step_imu_peak_m_s2']) for r in rows], label='Peak over ensuing action')
    axes[1].plot(t-.1, [abs(float(r['cue_vertical_m_s2'])) for r in rows], label='Endpoint used for cue')
    axes[1].plot(t-.1, [float(r['cue_filtered_acceleration_m_s2']) for r in rows], label='Cue EMA')
    axes[1].axhline(1.5, color='black', linestyle=':', label='EMA threshold')
    axes[1].set(xlabel='Episode time (s)', ylabel='Vertical acceleration (m/s²)')
    axes[1].legend(fontsize=8)
    labels = list(keys)
    x = np.arange(len(labels))
    for i, controller in enumerate(('ppo', 'pi_full', 'pi_matched')):
        axes[2].bar(x+(i-1)*.25, [reward_groups[controller]['mean_terms'][k] for k in labels],
                    width=.25, label=controller)
    axes[2].set_xticks(x, labels, rotation=30, ha='right')
    axes[2].set(ylabel='Mean raw return contribution', title='Exact saved evaluation reward totals (five episodes each)')
    axes[2].legend(fontsize=8)
    fig.savefig(args.output/'signals_and_rewards.png', dpi=160)
    plt.close(fig)
    print(json.dumps({k: result[k] for k in ('reward_groups', 'training', 'exploration', 'prior_authority_reward')}, indent=2))
    print('Saved audit:', args.output)


if __name__ == '__main__':
    main()
