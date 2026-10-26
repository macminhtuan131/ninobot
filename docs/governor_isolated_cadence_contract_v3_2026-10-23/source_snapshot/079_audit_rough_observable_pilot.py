#!/usr/bin/env python3
"""Audit exact saved actor/action/reward records; no ROS or new rollouts."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

from analyze_rough_reactive_authority import window_metrics


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def single(paths):
    paths = list(paths)
    if len(paths) != 1:
        raise ValueError(f'Expected one source, found {paths}')
    return paths[0]


def merge(ranges):
    result = []
    for a, b in sorted(ranges):
        if b <= a:
            continue
        if result and a <= result[-1][1] + 1e-9:
            result[-1][1] = max(b, result[-1][1])
        else:
            result.append([a, b])
    return result


def intersection(a, b):
    return merge([(max(x, u), min(y, v)) for x, y in a for u, v in b
                  if min(y, v) > max(x, u)])


def annotate(rows, captures, threshold):
    """Direction of *executed scale*, separate from the detector's phase."""
    if len(rows) != len(captures):
        raise ValueError('Capture/trace row count mismatch')
    annotated = []
    previous_x = 0.
    for row, (record, obs) in zip(rows, captures):
        np.testing.assert_allclose(record['elapsed_s'], float(row['elapsed_s']), atol=1e-8)
        np.testing.assert_allclose(record['action'], float(row['action_speed']), atol=1e-8)
        np.testing.assert_allclose(record['scale'], float(row['speed_scale']), atol=1e-8)
        frame = obs.reshape(5, 72)[-1]
        phase = record['cue']['cue_phase']
        assert phase == row['cue_phase']
        assert bool(frame[62]) == (phase == 'holding')
        assert bool(frame[63]) == (phase == 'recovering')
        assert bool(frame[64]) == (phase == 'cooldown')
        np.testing.assert_allclose(frame[65] * 1.2, record['cue']['cue_remaining_s'], atol=2e-7)
        dt = float(row['step_dt_s'])
        rate = (record['scale'] - float(frame[66])) / dt
        quiet = phase in ('ready', 'cooldown') and not record['cue']['cue_disturbed']
        startup_approach = float(row['elapsed_s']) <= 1. or float(row['physical_goal_distance_m']) < .5
        mode = ('startup_or_approach' if startup_approach else
                'slowdown' if rate < -threshold else
                'acceleration' if rate > threshold else
                'persistent_reduced' if record['scale'] < .95 else 'steady_cruise')
        x = float(row['physical_x_m'])
        if x < previous_x - .001:
            raise ValueError('Spatial attribution requires forward E1 progression')
        annotated.append(dict(row=row, record=record, frame=frame, observation=obs, dt=dt,
                              rate=rate, quiet=quiet, mode=mode, x_range=[previous_x, x]))
        previous_x = x
    return annotated


def stats(items):
    duration = sum(r['dt'] for r in items)
    slip = sum(float(r['row']['step_slip_square']) * r['dt'] for r in items)
    energy = sum(float(r['row']['step_imu_energy']) for r in items)
    coverage = sum(float(r['row']['step_imu_coverage_s']) for r in items)
    terms = {k: sum(r['record']['reward_terms'][k] for r in items)
             for k in items[0]['record']['reward_terms']} if items else {}
    return dict(seconds=duration, rows=len(items), slip_integral=slip,
                slip_rms=(slip / duration)**.5 if duration else None,
                vibration_rms=(energy / coverage)**.5 if coverage else None,
                mean_scale=sum(r['record']['scale'] * r['dt'] for r in items) / duration if duration else None,
                mean_interval_imu_rms_seen=sum(float(r['frame'][56]) * 10 * r['dt'] for r in items) / duration if duration else None,
                reward_terms=terms)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('rl_runs/rough_observable_pilot_v2'))
    parser.add_argument('--output', type=Path, default=Path('docs/rough_observable_audit_2026-10-11'))
    args = parser.parse_args()
    root = args.snapshot.resolve()
    config = yaml.safe_load((root / 'config.yaml').read_text())
    contract = json.loads((root / 'pilot_contract.json').read_text())
    for group in ('assets', 'implementation'):
        for path, expected in contract[group].items():
            if digest(path) != expected:
                raise ValueError('Frozen input changed: ' + path)
    comparison = json.loads((root / 'comparison.json').read_text())
    sources = {str(p): digest(p) for p in (root / 'config.yaml', root / 'pilot_contract.json',
                                         root / 'comparison.json', Path(__file__).resolve())}
    controllers = {}
    w = config['reward_v2']['longitudinal_weights']
    accounting = []
    for label in ('ppo', 'pi_full', 'pi_matched'):
        directory = root / 'evaluation' / label
        episodes_file = single(directory.glob('*/episodes.csv'))
        episodes = csv_rows(episodes_file)
        sources[str(episodes_file)] = digest(episodes_file)
        captures = {}
        for path in sorted((directory / 'actor_capture').glob('chunk_*.npz')):
            sources[str(path)] = digest(path)
            with np.load(path, allow_pickle=False) as z:
                for obs, raw in zip(z['observations'], z['records']):
                    record = json.loads(str(raw))
                    captures.setdefault(record['attempt'], []).append((record, obs.copy()))
        by_seed = {}
        for episode in episodes:
            attempt = int(episode['attempt'])
            path = episodes_file.parent / f'episode-{int(episode["episode"]):03d}' / 'control_trace.csv'
            rows = csv_rows(path)
            sources[str(path)] = digest(path)
            annotated = annotate(rows, captures[attempt], .05)
            total = stats(annotated)
            saved = ast.literal_eval(episode['reward_totals'])
            for name, value in saved.items():
                np.testing.assert_allclose(total['reward_terms'][name], value, atol=1e-8)
            np.testing.assert_allclose(sum(saved.values()), float(episode['return']), atol=1e-8)
            np.testing.assert_allclose(-w['slip'] / w['slip_sigma']**2 * total['slip_integral'], saved['slip'], atol=1e-8)
            np.testing.assert_allclose(-w['vibration'] / w['acceleration_sigma_m_s2']**2 *
                sum(float(r['step_imu_energy']) for r in rows), saved['vibration'], atol=1e-8)
            assert all(r['record']['reward_terms']['command_velocity'] == 0
                       for r in annotated if r['record']['cue']['cue_phase'] == 'holding')
            # These are new-contract causal observations, paired with ensuing actions.
            by_seed[int(episode['seed'])] = dict(rows=rows, annotated=annotated,
                                               raw_return=float(episode['return']), total=total)
            accounting.append(dict(controller=label, seed=int(episode['seed']),
                                   exact_reward_totals=True, integrated_slip_and_vibration=True,
                                   holding_velocity_zero=True, actor_phase_and_timer_match=True))
        controllers[label] = by_seed
    seeds = sorted(controllers['ppo'])
    if any(sorted(v) != seeds for v in controllers.values()):
        raise ValueError('Evaluation seed mismatch')
    reward_groups = {name: dict(mean_raw_return=float(np.mean([v['raw_return'] for v in group.values()])),
        mean_terms={k: float(np.mean([v['total']['reward_terms'][k] for v in group.values()]))
                    for k in next(iter(group.values()))['total']['reward_terms']})
        for name, group in controllers.items()}
    paired = []
    for seed in seeds:
        data = controllers['ppo'][seed]
        ann = data['annotated']
        window = next(r['windows'] for r in comparison['disturbance_windows'] if r['seed'] == seed)
        modes = {}
        for mode in ('startup_or_approach', 'slowdown', 'acceleration', 'persistent_reduced', 'steady_cruise'):
            items = [r for r in ann if r['mode'] == mode]
            selected = intersection(merge([r['x_range'] for r in items]), window)
            modes[mode] = dict(all_episode=stats(items), disturbance_ranges=selected)
            if selected:
                a = window_metrics(data['rows'], selected)
                b = window_metrics(controllers['pi_matched'][seed]['rows'], selected)
                modes[mode].update(ppo_window=a, matched_pi_same_positions=b,
                                  excess_slip_integral=a['slip_energy'] - b['slip_energy'])
        quiet = [r for r in ann if r['quiet'] and r['mode'] != 'startup_or_approach']
        holding = [r for r in ann if r['record']['cue']['cue_phase'] == 'holding']
        recovering = [r for r in ann if r['record']['cue']['cue_phase'] == 'recovering']
        recovering_acceleration = [r for r in recovering if r['mode'] == 'acceleration']
        sensor = [r for r in ann if r['record']['cue']['cue_triggered']]
        paired.append(dict(seed=seed, modes=modes, quiet_cruise=stats(quiet),
            holding=stats(holding), detector_recovering=stats(recovering),
            recovering_acceleration=stats(recovering_acceleration), trigger_count=len(sensor),
            target_scale_quiet=float(np.mean([.55 + .225 * (r['record']['action'] + 1) for r in quiet])),
            quiet_target_execution_max_difference=max(abs(.55 + .225 * (r['record']['action'] + 1)
                                                         - r['record']['scale']) for r in quiet),
            quiet_ramp_limited_fraction=float(np.mean([abs(.55 + .225 * (r['record']['action'] + 1)
                                                          - r['record']['scale']) > 1e-5 for r in quiet])),
            mean_quiet_rate=float(np.mean([r['rate'] for r in quiet])),
            quiet_below_095_seconds=sum(r['dt'] for r in quiet if r['record']['scale'] < .95),
            recovering_but_not_accelerating_seconds=sum(r['dt'] for r in recovering if r['mode'] != 'acceleration')))
    aggregate = {}
    for mode in paired[0]['modes']:
        modes = [r['modes'][mode] for r in paired]
        total_slip = sum(r['all_episode']['slip_integral'] for r in modes)
        duration = sum(r['all_episode']['seconds'] for r in modes)
        aggregate[mode] = dict(mean_seconds=duration/len(seeds),
            pooled_slip_rms=(total_slip/duration)**.5 if duration else None,
            mean_slip_integral=total_slip/len(seeds),
            disturbance_excess_slip_integral=sum(r.get('excess_slip_integral', 0.) for r in modes)/len(seeds))
    sensitivity = {}
    for threshold in (.02, .05, .10):
        all_items = []
        for seed in seeds:
            group = controllers['ppo'][seed]
            captures = [(r['record'], r['observation']) for r in group['annotated']]
            all_items.extend(annotate(group['rows'], captures, threshold))
        sensitivity[str(threshold)] = {mode: stats([r for r in all_items if r['mode'] == mode])
                                      for mode in aggregate}
    # Exact reward rescoring of recorded trajectories, NOT alternate control simulations.
    rescoring = {}
    for sigma in (.4, .2, .1):
        factor = (w['velocity_sigma_m_s']/sigma)**2
        rescoring[str(sigma)] = {name: group['mean_raw_return'] + (factor-1)*group['mean_terms']['command_velocity']
                                 for name, group in reward_groups.items()}
    advantage = reward_groups['ppo']['mean_raw_return'] - reward_groups['pi_full']['mean_raw_return']
    velocity_delta = reward_groups['ppo']['mean_terms']['command_velocity'] - reward_groups['pi_full']['mean_terms']['command_velocity']
    break_even_multiplier = 1 - advantage / velocity_delta
    result = dict(snapshot=str(root), sources_sha256=sources, accounting_checks=accounting,
        classification=dict(rate_threshold_scale_per_s=.05, steady_reduced_below=.95,
            exclusions='First 1 second and physical goal distance below .5m separated',
            phase='Detector recovering is not equivalent to actual acceleration',
            spatial='Disjoint PPO action-position intervals intersected with original PI disturbance windows'),
        reward_groups=reward_groups, paired=paired, aggregate_modes=aggregate,
        rate_threshold_sensitivity=sensitivity, unchanged_trajectory_sigma_rescoring=rescoring,
        recorded_ppo_vs_full_pi_break_even=dict(velocity_multiplier=break_even_multiplier,
            sigma_m_s=w['velocity_sigma_m_s']/break_even_multiplier**.5),
        selected_correction=dict(parameter='reward_v2.longitudinal_weights.velocity_sigma_m_s',
            before=.4, after=.1, effect='16x non-holding physical velocity-tracking cost; holding remains zero',
            contract='New reward contract; no incompatible optimizer/critic resume',
            validation='Keep existing physical/behavior/ride gates; requires a new bounded pilot, not established improvement'),
        qualification='Five paired fixed-map reset seeds and one training seed. Spatial/phase associations are not causal contact attribution. Rescoring keeps all recorded states and actions unchanged.',
        optuna_held=True, simulation_started=False)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    # A new reviewable candidate, never mutate the frozen pilot config or package.
    candidate = dict(reward_v2=dict(longitudinal_weights=dict(velocity_sigma_m_s=.1)))
    (args.output/'candidate_reward_override.yaml').write_text(
        '# Proposed single change; NOT a standalone training config.\n'
        '# Apply only to a new frozen contract with a fresh critic/optimizer.\n'
        + yaml.safe_dump(candidate, sort_keys=False))
    make_figure(args.output, controllers, paired, reward_groups)
    write_report(args.output, result)
    print(json.dumps(dict(aggregate_modes=aggregate, reward_groups=reward_groups,
                          unchanged_trajectory_sigma_rescoring=rescoring,
                          quiet=[dict(seed=r['seed'], **{k:r[k] for k in ('quiet_cruise', 'target_scale_quiet',
                              'recovering_but_not_accelerating_seconds')}) for r in paired]), indent=2))
    print('Saved:', args.output)


def make_figure(output, controllers, paired, rewards):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    # Display the largest excess-slip scenario, not a cherry-picked best run.
    worst = max(paired, key=lambda r: sum(m.get('excess_slip_integral', 0.) for m in r['modes'].values()))
    seed = worst['seed']
    ppo = controllers['ppo'][seed]
    matched = controllers['pi_matched'][seed]
    for label, data in [('PPO', ppo), ('Duration-matched PI', matched)]:
        x = [float(r['physical_x_m']) for r in data['rows']]
        axes[0].plot(x, [float(r['speed_scale']) for r in data['rows']], label=label)
        axes[1].plot(x, [float(r['step_slip_square'])**.5 for r in data['rows']], label=label, alpha=.8)
    for mode, color in [('slowdown', '#e8a34a'), ('acceleration', '#ce5f68')]:
        for start, end in merge([r['x_range'] for r in ppo['annotated'] if r['mode'] == mode]):
            axes[0].axvspan(start, end, color=color, alpha=.18)
            axes[1].axvspan(start, end, color=color, alpha=.18)
    axes[0].set(ylabel='Executed speed scale', title=f'Seed {seed}: orange slowdown, red acceleration (>0.05 scale/s)')
    axes[1].set(xlabel='Physical route position (m)', ylabel='Action-interval slip RMS')
    axes[1].set_ylim(0, .065)
    axes[1].set_title('Cruise detail; startup slip above axis range is excluded from cruise attribution')
    for ax in axes[:2]:
        ax.legend(); ax.grid(alpha=.2)
    keys = ['time', 'command_velocity', 'vibration', 'slip', 'action_rate']
    x = np.arange(len(keys))
    for i, label in enumerate(('ppo', 'pi_full', 'pi_matched')):
        axes[2].bar(x + (i-1)*.25, [rewards[label]['mean_terms'][k] for k in keys],
                    width=.25, label=label)
    axes[2].set_xticks(x, keys)
    axes[2].set(ylabel='Mean raw return contribution', title='Exact reward accounting: five episodes per controller')
    axes[2].legend(); axes[2].grid(axis='y', alpha=.2)
    fig.savefig(output/'slip_and_reward.png', dpi=150)
    plt.close(fig)


def write_report(output, result):
    pairs = result['paired']
    terms = result['reward_groups']
    lines = ['# Rough observable PPO: saved-trace and reward audit', '',
        'Completed offline on 2026-10-11. No Gazebo, training, tuning, or new evaluations were started.', '',
        '## Evidence and verification', '',
        'Five paired E1 reset seeds (17100–17104), one training seed (17000), fixed nominal half-relief terrain. '
        'All frozen input hashes pass. Exact captured actor inputs, ensuing actions and rewards match the control traces. '
        'For all 15 controller episodes, component sums reconstruct raw returns, and integrated IMU/slip traces reconstruct their reward costs. '
        'Holding velocity costs are exactly zero; actor-visible phase and timer match the phase used by the reward.', '',
        '## 1. Where the extra slip occurs', '',
        'Modes use executed policy speed-scale rate, not the detector phase: slowdown below −0.05 scale/s, '
        'acceleration above +0.05 scale/s, otherwise persistent reduced speed below 0.95 or steady cruise. '
        'Startup (first second) and final approach (physical goal distance <0.5 m) are separate. '
        'Changing the rate boundary to 0.02 or 0.10 scale/s retains higher pooled slip during acceleration than persistent reduced-speed driving.', '',
        '| Mode | Mean duration per episode | Pooled slip RMS | Mean excess slip integral in disturbance windows vs PI at the same positions |',
        '|---|---:|---:|---:|']
    for name, row in result['aggregate_modes'].items():
        lines.append(f'| {name} | {row["mean_seconds"]:.2f} s | {row["pooled_slip_rms"]:.5f} | {row["disturbance_excess_slip_integral"]:+.7f} |')
    positive_accel = sum(p['modes']['acceleration'].get('excess_slip_integral', 0) > 0 for p in pairs)
    negative_reduced = sum(p['modes']['persistent_reduced'].get('excess_slip_integral', 0) < 0 for p in pairs)
    lines += ['', f'Acceleration has positive excess slip in {positive_accel}/5 scenarios; persistent reduced-speed intervals '
        f'have less slip in {negative_reduced}/5. Seed 17100 contributes the largest excess, during both slowdown and acceleration. '
        'The detector labels an average 6.24 seconds as recovering, but 5.06 of those seconds are not actual acceleration at the stated threshold.', '',
        'These are associations. Phase intervals encounter different terrain; matched-position PI comparisons reduce this confound but do not establish causality. '
        'The metric is the existing bounded wheel-versus-body velocity ratio, with a 0.10 m/s denominator floor. '
        'It is a longitudinal slip proxy, not direct wheel/contact measurement. Spatial attribution uses 0.1-second action intervals. '
        'The mode excess-integral table is not a replacement for the original per-metre quality gate.', '',
        '## 2. Why quiet cruising stays low', '',
        'Quiet means ready/cooldown with no detector threshold exceeded; it does not mean the ride has zero vibration. '
        'The table below also excludes startup and final approach, so its means differ slightly from the original gate averages.', '',
        '| Seed | Quiet executed scale | Quiet actor target scale | Ramp-limited quiet actions |',
        '|---|---:|---:|---:|']
    for p in pairs:
        lines.append(f'| {p["seed"]} | {p["quiet_cruise"]["mean_scale"]:.4f} | {p["target_scale_quiet"]:.4f} | {p["quiet_ramp_limited_fraction"]:.0%} |')
    lines += ['', 'The low scale is requested by the saved deterministic actor, not held down by the reference ramp. '
        'There are 7–8 disturbance events per episode: bounded rearming works. The four low-cruise episodes still observe '
        'mean interval IMU RMS of approximately 0.74–0.95 m/s² during quiet cruise. Comfort cost remains active there, while cruise-tracking cost is weak. '
        'Reward balance is a supported explanation, not proof that optimization has converged or that IMU alone causes the output.', '',
        '## 3. What the reward currently favors', '',
        '| Mean raw reward contribution | PPO | Full-speed PI | Duration-matched PI |',
        '|---|---:|---:|---:|']
    for k in ('time', 'command_velocity', 'vibration', 'slip', 'lateral', 'heading', 'action_rate'):
        lines.append(f'| {k} | {terms["ppo"]["mean_terms"][k]:.4f} | {terms["pi_full"]["mean_terms"][k]:.4f} | {terms["pi_matched"]["mean_terms"][k]:.4f} |')
    lines.append('| Total return | ' + ' | '.join(f'{terms[k]["mean_raw_return"]:.4f}' for k in ('ppo', 'pi_full', 'pi_matched')) + ' |')
    lines += ['', 'PPO gains about 0.626 raw reward from vibration relative to full-speed PI. Its additional time cost is only 0.106 '
        'and additional velocity-tracking cost only 0.044. It earns the highest total return although it fails the intended recovery/quality gates. '
        'No episode exceeds 31 seconds, so lateness contributes zero. At ideal 0.4 m/s reference tracking, constant scale 0.936 '
        'costs only 0.001024 reward/s for velocity tracking with sigma 0.4 m/s. '
        'Observed trace rewards substantiate a mismatch between the training incentive and the desired recovery behavior.', '',
        '## One selected correction', '',
        'Change **only `reward_v2.longitudinal_weights.velocity_sigma_m_s`: 0.4 → 0.1 m/s**. '
        'This increases the existing non-holding velocity-tracking penalty by 16× and retains exactly zero velocity penalty during holding. '
        'Keep all other reward weights, observations, gSDE, speed range, 0.4 scale/s ramp, PI yaw, estimator, terrain, physical arrival and quality gates fixed.', '',
        'Exact rescoring of the same recorded trajectories (no altered actions or physics):', '',
        '| Velocity sigma | PPO return | Full-speed PI return | Matched PI return |',
        '|---|---:|---:|---:|']
    for sigma, group in result['unchanged_trajectory_sigma_rescoring'].items():
        lines.append('| ' + sigma + ' m/s | ' + ' | '.join(f'{group[k]:.4f}' for k in ('ppo', 'pi_full', 'pi_matched')) + ' |')
    lines += ['', 'The recorded PPO/full-speed-PI ranking reverses below sigma ≈0.124 m/s; 0.2 m/s is insufficient to reverse it. '
        'The proposed 0.1 is a bounded pilot candidate based on incentive accounting, not an optimized value or demonstrated new performance. '
        'A stronger physical-speed penalty can increase acceleration-related slip or favor constant full speed; retaining the existing ramp and strict ride-quality gates is essential.', '',
        'The override file is a proposal, not a standalone training configuration. If a pilot is authorized, use a new frozen reward contract, '
        'the same original fresh actor initialization and training seed 17000, fresh critic/optimizer, and the same 20,480-step budget. '
        'Using the newly trained actor instead would confound this single-change comparison. Existing five seeds are now diagnostic; '
        'a subsequent confirmation must use new seeds. Keep Optuna held.', '',
        '## Reproduce', '', '```bash', 'cd ~/ninorobot',
        '.venv/bin/python src/nino_rl/scripts/audit_rough_observable_pilot.py', '```', '',
        'Artifacts: `audit.json` (input hashes and detailed per-seed accounting), '
        '`candidate_reward_override.yaml` (single proposed change), and `slip_and_reward.png`.', '',
        '![Saved speed/slip traces and reward contributions](slip_and_reward.png)', '']
    (output/'REPORT.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
