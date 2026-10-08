#!/usr/bin/env python3
"""Inspect timestamped sensors in one saved rough evaluation episode."""
import argparse
import csv
import json
from math import atan2, asin
from pathlib import Path

import numpy as np


def orientation(q):
    return (atan2(2 * (q.w * q.x + q.y * q.z), 1 - 2 * (q.x*q.x + q.y*q.y)),
            asin(max(-1., min(1., 2 * (q.w * q.y - q.z * q.x)))),
            atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y*q.y + q.z*q.z)))


def stats(values):
    return {k: float(v) for k, v in (
        ('mean', np.mean(values)), ('rms', np.sqrt(np.mean(values**2))),
        ('p99_abs', np.percentile(np.abs(values), 99)), ('max_abs', np.max(np.abs(values))))}


def series(rows):
    # Preserve arrival-order anomaly statistics separately; interpolation uses
    # the final received sample at each timestamp and never extrapolates.
    unique = {r[0]: r for r in rows}
    return np.asarray([unique[t] for t in sorted(unique)], dtype=float)


def main():
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bag', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--episode', type=int, default=1)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheel-radius', type=float, default=0.0625)
    parser.add_argument('--wheel-separation', type=float, default=0.34273666)
    args = parser.parse_args()
    if not all(np.isfinite(v) and v > 0 for v in (args.wheel_radius, args.wheel_separation)):
        parser.error('Positive finite wheel geometry is required')
    with (args.run / 'episodes.csv').open() as stream:
        episode = next(r for r in csv.DictReader(stream) if int(r['episode']) == args.episode)
    with (args.run / f'episode-{args.episode:03d}' / 'control_trace.csv').open() as stream:
        control = list(csv.DictReader(stream))
    start, end = float(control[0]['sim_time_s']), float(control[-1]['sim_time_s'])
    topics = ('/joint_states', '/imu/data', '/odom', '/ground_truth/odom', '/nino_drive/diagnostics')
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(args.bag.resolve()), storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types() if t.name in topics}
    missing = set(topics) - set(types)
    if missing:
        raise ValueError(f'Missing bag topics: {sorted(missing)}')
    reader.set_filter(rosbag2_py.StorageFilter(topics=list(topics)))
    reader.seek(int((start - 1.) * 1e9))
    rows = {topic: [] for topic in topics}
    while reader.has_next():
        topic, data, receipt_ns = reader.read_next()
        receipt = receipt_ns * 1e-9
        if receipt > end + 1.:
            break
        msg = deserialize_message(data, types[topic])
        if topic == '/nino_drive/diagnostics':
            fields = msg.layout.dim[0].label.split(',')
            d = dict(zip(fields, msg.data))
            stamp = d['sim_time_s']
            payload = [d['left_actual_rad_s'], d['right_actual_rad_s']]
        else:
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            if topic == '/joint_states':
                indices = [msg.name.index(n) for n in ('left_wheel_joint', 'right_wheel_joint')]
                payload = [msg.position[i] for i in indices] + [msg.velocity[i] for i in indices]
            elif topic == '/imu/data':
                payload = [*orientation(msg.orientation), msg.angular_velocity.z]
            else:
                payload = [msg.pose.pose.position.x, msg.pose.pose.position.y,
                           orientation(msg.pose.pose.orientation)[2], msg.twist.twist.linear.x,
                           msg.twist.twist.angular.z]
        if start - .25 <= stamp <= end + .25:
            rows[topic].append([stamp, receipt - stamp, *payload])
    timing = {}
    arrays = {}
    for topic, records in rows.items():
        if len(records) < 2:
            raise ValueError(f'Insufficient samples in episode window: {topic}')
        arrival = np.asarray(records)
        dt = np.diff(arrival[:, 0])
        arrays[topic] = series(records)
        timing[topic] = {'samples_in_window': len(records),
            'backwards_header_timestamps': int(np.sum(dt < -1e-9)),
            'duplicate_header_timestamps': int(np.sum(np.abs(dt) < 1e-9)),
            'positive_header_gap_p99_s': float(np.percentile(dt[dt > 1e-9], 99)),
            'positive_header_gap_max_s': float(np.max(dt)),
            'recording_time_minus_header_s': stats(arrival[:, 1])}
    lo = max(start, *(a[0, 0] for a in arrays.values()))
    hi = min(end, *(a[-1, 0] for a in arrays.values()))
    if hi <= lo:
        raise ValueError('No common sensor time window')
    odom = arrays['/odom']
    grid = odom[(odom[:, 0] >= lo) & (odom[:, 0] <= hi), 0]

    def interp(topic, column, angular=False):
        a = arrays[topic]
        value = np.unwrap(a[:, column]) if angular else a[:, column]
        return np.interp(grid, a[:, 0], value)

    def wrap(v):
        return np.arctan2(np.sin(v), np.cos(v))

    ox, oy, oyaw = (interp('/odom', i, i == 4) for i in (2, 3, 4))
    gx, gy, gyaw = (interp('/ground_truth/odom', i, i == 4) for i in (2, 3, 4))
    iyaw = interp('/imu/data', 4, True)
    # Continuous wheel joints are integrated from their recorded unbounded
    # position values; do not np.unwrap multi-revolution encoder positions.
    left, right = (interp('/joint_states', i) for i in (2, 3))
    turn = args.wheel_radius * ((right - right[0]) - (left - left[0])) / args.wheel_separation
    yaw_change = oyaw - oyaw[0]
    yaw_from_imu = iyaw - iyaw[0] + gyaw[0]
    pose_error = np.hypot(ox - gx, oy - gy)
    distance = .5 * args.wheel_radius * (np.diff(left) + np.diff(right))
    heading = .5 * (yaw_from_imu[1:] + yaw_from_imu[:-1])
    pitch = interp('/imu/data', 3)
    projection = np.cos(.5 * (pitch[1:] + pitch[:-1]))
    reconstructions = {}
    for label, horizontal_distance in (
            ('encoder_distance_with_imu_heading', distance),
            ('encoder_distance_with_imu_heading_and_pitch', distance * projection)):
        rx = ox[0] + np.r_[0., np.cumsum(horizontal_distance * np.cos(heading))]
        ry = oy[0] + np.r_[0., np.cumsum(horizontal_distance * np.sin(heading))]
        error = np.hypot(rx - gx, ry - gy)
        reconstructions[label] = {'position_error_m': stats(error),
            'final_position_error_m': float(error[-1])}
    diagnostic = arrays['/nino_drive/diagnostics']
    jt = arrays['/joint_states']
    index = np.maximum(0, np.searchsorted(jt[:, 0], diagnostic[:, 0], side='right') - 1)
    differences = diagnostic[:, 2:4] - jt[index, 4:6]
    report = {
        'bag': str(args.bag.resolve()), 'run': str(args.run.resolve()),
        'seed': int(episode['seed']), 'termination': episode['termination'],
        'episode_start_sim_s': start, 'episode_end_sim_s': end,
        'common_window_seconds': hi - lo,
        'wheel_radius_m': args.wheel_radius, 'wheel_separation_m': args.wheel_separation,
        'sensor_timing': timing,
        'estimated_vs_physical_position_m': stats(pose_error),
        'estimated_vs_physical_heading_deg': stats(np.degrees(wrap(oyaw - gyaw))),
        'imu_relative_vs_physical_heading_deg': stats(np.degrees(wrap(yaw_from_imu - gyaw))),
        'encoder_position_vs_odometry_yaw_change_deg': stats(np.degrees(turn - yaw_change)),
        'diagnostic_vs_latest_timestamp_joint_velocity_rad_s': stats(differences.flatten()),
        'final_pose_disagreement_m': float(pose_error[-1]),
        'final_encoder_vs_odometry_yaw_change_deg': float(np.degrees(turn[-1] - yaw_change[-1])),
        'final_estimated_goal_distance_m': float(control[-1]['estimated_goal_distance_m']),
        'final_physical_goal_distance_m': float(control[-1]['physical_goal_distance_m']),
        'offline_reconstructions': reconstructions,
        'limitations': [
            'Bag receipt time is recorder ROS time, not a measurement of controller callback latency.',
            'Recorded joint messages and diagnostics do not establish which joint packet the controller consumed.',
            'Interpolated comparisons use the common timestamp interval; poses are not extrapolated.',
            'IMU relative yaw comparison aligns the initial heading; simulator orientation accuracy is not a hardware guarantee.',
            'Wheel position/yaw consistency does not prove translational slip or fix localization.',
            'Offline pose reconstruction follows the already-executed motion; it does not measure closed-loop performance after a controller change.',
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'sensor_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    with (args.output / 'aligned_sensor_comparison.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['sim_time_s', 'estimated_x_m', 'estimated_y_m', 'physical_x_m', 'physical_y_m',
                         'estimated_yaw_rad', 'physical_yaw_rad', 'imu_aligned_yaw_rad', 'encoder_yaw_change_rad'])
        writer.writerows(zip(grid, ox, oy, gx, gy, oyaw, gyaw, yaw_from_imu, turn))
    print(json.dumps({k: v for k, v in report.items() if k not in ('sensor_timing', 'limitations')}, indent=2))
    print(f'Saved audit and aligned sensors to {args.output}')


if __name__ == '__main__':
    main()
