#!/usr/bin/env python3
"""Audit saved rough control traces without running or changing the simulator."""
import argparse
from bisect import bisect_right
import csv
import json
from math import atan2, cos, degrees, hypot, isfinite, sin
from pathlib import Path


def load_rows(path):
    with path.open() as stream:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(stream)]
    if len(rows) < 2 or any(not isfinite(v) for row in rows for v in row.values()):
        raise ValueError(f"Insufficient or nonfinite trace: {path}")
    if any(b['sim_time_s'] <= a['sim_time_s'] for a, b in zip(rows, rows[1:])):
        raise ValueError(f"Non-increasing simulation timestamps: {path}")
    return rows


def sample(rows, stamp):
    times = [r['sim_time_s'] for r in rows]
    if not times[0] <= stamp <= times[-1]:
        raise ValueError('Interpolation would extrapolate outside the saved trace')
    i = min(bisect_right(times, stamp) - 1, len(rows) - 2)
    a, b = rows[i:i + 2]
    fraction = (stamp - times[i]) / (times[i + 1] - times[i])
    result = {}
    for key in a:
        delta = b[key] - a[key]
        if key.endswith('yaw_rad'):
            delta = atan2(sin(delta), cos(delta))
        result[key] = a[key] + fraction * delta
    return result


def reconstruct(control, drive, radius, separation):
    start = max(control[0]['sim_time_s'], drive[0]['sim_time_s'])
    end = min(control[-1]['sim_time_s'], drive[-1]['sim_time_s'])
    if end <= start:
        raise ValueError('Controller and pose traces have no shared time interval')
    first, last = sample(control, start), sample(control, end)
    wheels = [sample(drive, start)] + [r for r in drive if start < r['sim_time_s'] < end] + [sample(drive, end)]
    x, y, yaw = (first[k] for k in ('estimated_x_m', 'estimated_y_m', 'estimated_yaw_rad'))
    for a, b in zip(wheels, wheels[1:]):
        dt = b['sim_time_s'] - a['sim_time_s']
        left = 0.5 * (a['left_actual_rad_s'] + b['left_actual_rad_s'])
        right = 0.5 * (a['right_actual_rad_s'] + b['right_actual_rad_s'])
        distance = 0.5 * radius * (left + right) * dt
        turn = radius * (right - left) / separation * dt
        x += distance * cos(yaw + 0.5 * turn)
        y += distance * sin(yaw + 0.5 * turn)
        yaw += turn
    return {
        'overlap_seconds': end - start,
        'reconstructed_vs_estimated_position_m': hypot(x - last['estimated_x_m'], y - last['estimated_y_m']),
        'reconstructed_vs_estimated_heading_deg': degrees(atan2(sin(yaw - last['estimated_yaw_rad']), cos(yaw - last['estimated_yaw_rad']))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheel-radius', type=float, default=0.0625)
    parser.add_argument('--wheel-separation', type=float, default=0.34273666)
    args = parser.parse_args()
    if any(not isfinite(v) or v <= 0 for v in (args.wheel_radius, args.wheel_separation)):
        parser.error('Wheel geometry must be finite and positive')
    summary = json.loads((args.run / 'summary.json').read_text())
    if not summary.get('complete'):
        parser.error('A completed evaluation summary is required')
    with (args.run / 'episodes.csv').open() as stream:
        episodes = list(csv.DictReader(stream))
    reports = []
    for episode in episodes:
        directory = args.run / f"episode-{int(episode['episode']):03d}"
        control = load_rows(directory / 'control_trace.csv')
        drive = load_rows(directory / 'drive_trace.csv')
        last = control[-1]
        stopped_outside = [r for r in drive
            if control[0]['sim_time_s'] <= r['sim_time_s'] <= control[-1]['sim_time_s']
            and r['cmd_fresh'] == 1 and r['policy_fresh'] == 1
            and abs(r['requested_linear_m_s']) < 1e-6
            and abs(r['requested_yaw_rad_s']) < 1e-6
            and sample(control, r['sim_time_s'])['physical_goal_distance_m'] > 0.20]
        report = {
            'seed': int(episode['seed']), 'termination': episode['termination'],
            'final_estimated_goal_distance_m': last['estimated_goal_distance_m'],
            'final_physical_goal_distance_m': last['physical_goal_distance_m'],
            'final_pose_disagreement_m': hypot(last['estimated_x_m'] - last['physical_x_m'], last['estimated_y_m'] - last['physical_y_m']),
            'final_heading_disagreement_deg': degrees(atan2(sin(last['estimated_yaw_rad'] - last['physical_yaw_rad']), cos(last['estimated_yaw_rad'] - last['physical_yaw_rad']))),
            'max_controller_sample_gap_s': max(b['sim_time_s'] - a['sim_time_s'] for a, b in zip(drive, drive[1:])),
            'fresh_zero_command_samples_outside_physical_goal': len(stopped_outside),
            'classification': 'premature_estimated_stop' if episode['termination'] == 'timeout' and stopped_outside and last['estimated_goal_distance_m'] < 0.05 and last['physical_goal_distance_m'] > 0.20 else episode['termination'],
            **reconstruct(control, drive, args.wheel_radius, args.wheel_separation),
        }
        reports.append(report)
    limitations = [
        '50 Hz wheel feedback reconstruction approximates the 500 Hz odometry integrator; differences do not prove a software bug.',
        'Control trace poses are latest sensor snapshots, not exactly synchronized pose measurements.',
        'Joint message header timestamps and IMU samples were not recorded in these CSVs; sensor latency, pitch effects and slip causes cannot be isolated.',
        'Geometry uses the current effort_drive defaults; pass overrides if the launch used other values.',
        'Physical and estimated poses are compared in the common reset frame used by this E1 evaluation.',
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    payload = {'source': str(args.run.resolve()), 'wheel_radius_m': args.wheel_radius,
               'wheel_separation_m': args.wheel_separation, 'episodes': reports, 'limitations': limitations}
    (args.output / 'odometry_audit.json').write_text(json.dumps(payload, indent=2) + '\n')
    lines = ['# Rough E1 odometry audit', '', '| Seed | Classification | Estimated goal (m) | Physical goal (m) | Pose disagreement (m) | Wheel reconstruction vs odom (m) |', '|---|---|---:|---:|---:|---:|']
    for r in reports:
        lines.append(f"| {r['seed']} | {r['classification']} | {r['final_estimated_goal_distance_m']:.3f} | {r['final_physical_goal_distance_m']:.3f} | {r['final_pose_disagreement_m']:.3f} | {r['reconstructed_vs_estimated_position_m']:.3f} |")
    lines += ['', '## Interpretation', '', 'A fresh zero motion command outside the physical goal identifies a navigation stop. Reconstructed wheel odometry checks numerical consistency with sampled wheel feedback; it cannot correct physical drift or establish its cause.', '', '## Limitations', ''] + [f'- {item}' for item in limitations]
    (args.output / 'README.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines[:len(reports) + 4]))
    print(f'\nSaved {args.output / "odometry_audit.json"} and {args.output / "README.md"}')


if __name__ == '__main__':
    main()
