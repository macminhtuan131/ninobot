#!/usr/bin/env python3
"""Summarize physical arrival, stalls and recovery from the frozen PI evidence."""
import csv
import json
from pathlib import Path
from statistics import mean

from run_rough_localized import EXPERIMENT, ROOT, longest_commanded_stall, verify


def main():
    verify()
    output = ROOT/'docs/rough_recovery_2026-10-09'
    output.mkdir(exist_ok=True)
    result = {'experiment':str(EXPERIMENT), 'profiles':{}}
    for label, directory in [('E1', EXPERIMENT/'pi/E1'), ('N1', EXPERIMENT/'pi/N1'),
                             ('S1', EXPERIMENT/'pi/S1'), ('E1_slow', EXPERIMENT/'slow_e1')]:
        reports = sorted(directory.glob('*/summary.json'))
        if not reports:
            continue
        report = reports[-1]
        summary = json.loads(report.read_text())
        if not summary.get('complete'):
            continue
        rows = list(csv.DictReader((report.parent/'episodes.csv').open()))
        episodes = []
        for index, row in enumerate(rows, 1):
            path = report.parent/f'episode-{index:03d}/control_trace.csv'
            trace = list(csv.DictReader(path.open()))
            modes = {}
            for previous, sample in zip(trace, trace[1:]):
                # Command recorded with its resulting sample describes the
                # interval since the preceding sample.
                mode = sample['rough_recovery_mode']
                modes[mode] = modes.get(mode, 0.)+float(sample['elapsed_s'])-float(previous['elapsed_s'])
            episodes.append(dict(seed=summary['evaluation_seeds'][index-1],
                success=row['success'].lower()=='true', termination=row['termination'],
                time_s=float(row['time_seconds']), endpoint_m=float(row['truth_endpoint_error_m']),
                path_rmse_m=float(row['truth_path_rmse_m']), pose_disagreement_m=float(row['odom_truth_position_error_m']),
                maximum_feedback_lag_s=float(row['max_motion_sensor_lag_seconds']),
                attempts=max(int(sample['rough_recovery_attempts']) for sample in trace),
                longest_physical_stall_s=longest_commanded_stall(path), mode_seconds=modes,
                trace=str(path)))
        result['profiles'][label] = dict(summary=str(report), episodes=episodes,
            successes=sum(ep['success'] for ep in episodes),
            mean_time_s=mean(ep['time_s'] for ep in episodes),
            maximum_physical_stall_s=max(ep['longest_physical_stall_s'] for ep in episodes))
    gate = EXPERIMENT/'pi_gate.json'
    result['gate'] = json.loads(gate.read_text()) if gate.exists() else None
    (output/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    if 'S1' in result['profiles']:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        figure, axes = plt.subplots(1, 2, figsize=(10, 5), layout='constrained')
        previous = sorted((ROOT/'rl_runs/rough_wall_cloud_v11/pi/S1').glob('*/summary.json'))[-1]
        for ax, report, title in [(axes[0], previous, 'V11: 2/3 physical arrivals'),
                (axes[1], Path(result['profiles']['S1']['summary']),
                 f"{EXPERIMENT.name.rsplit('_', 1)[-1].upper()}: {result['profiles']['S1']['successes']}/3 physical arrivals")]:
            for index, seed in enumerate((10002, 10005, 10008), 1):
                trace = list(csv.DictReader((report.parent/f'episode-{index:03d}/control_trace.csv').open()))
                ax.plot([float(r['physical_x_m']) for r in trace], [float(r['physical_y_m']) for r in trace], label=str(seed))
            ax.plot([0., 2.5, 2.5], [0., 0., -6.2], 'k--', alpha=.45, label='Drawn route')
            ax.add_patch(plt.Circle((2.5, -6.2), .2, fill=False, color='green'))
            ax.set(title=title, xlabel='X (m)', ylabel='Y (m)', xlim=(-.3, 3.3), ylim=(-6.6, .4))
            ax.set_aspect('equal'); ax.grid(alpha=.25); ax.legend(fontsize=8)
        figure.suptitle('S1 physical trajectories — matching scenario seeds, fixed terrain')
        figure.savefig(output/'s1_paths.png', dpi=150)
        plt.close(figure)
    print(json.dumps(result, indent=2))
    print(f'Saved {output}/comparison.json')


if __name__ == '__main__':
    main()
