#!/usr/bin/env python3
"""Capture contacts and sensors at the current rough pose; advance only 2 sim seconds.

Does not reset the robot, publish motor commands or use physical pose for control.
The user must leave the rough evaluator/trainer stopped during this diagnostic.
"""
import argparse
import json
from pathlib import Path
import subprocess
import threading
import time


def main():
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu, JointState, LaserScan
    from nav_msgs.msg import Odometry
    from rosidl_runtime_py.convert import message_to_ordereddict

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    args.output.mkdir(parents=True, exist_ok=False)
    library = root / 'build/rough_contact_probe/libnino_rough_contact_probe.so'
    if not library.exists():
        raise SystemExit('Build src/nino_rl/scripts/rough_contact_probe with CMake first')
    def request(service, typ, payload):
        result = subprocess.run(['gz', 'service', '-s', service, '--reqtype', typ,
            '--reptype', 'gz.msgs.Boolean', '--timeout', '5000', '--req', payload],
            capture_output=True, text=True, check=True)
        if 'data: true' not in result.stdout:
            raise RuntimeError(result.stdout + result.stderr)
    # A completed evaluator may restore a freely running world. Freeze it
    # before discovery so the explicit multi-step window is really bounded.
    request('/world/combined_rough_section/control', 'gz.msgs.WorldControl', 'pause: true')
    request('/world/combined_rough_section/entity/system/add', 'gz.msgs.EntityPlugin_V',
        'entity {name: "combined_rough_section" type: WORLD} plugins {'
        'name: "NinoContactProbe" filename: ' + json.dumps(str(library)) +
        ' innerxml: ' + json.dumps(f'<output>{(args.output / "contacts.csv").resolve()}</output>') + '}')
    rclpy.init()
    node = rclpy.create_node('rough_stall_capture')
    records = []
    subscriptions = []
    for topic, typ in [('/scan', LaserScan), ('/imu/data', Imu),
                       ('/joint_states', JointState), ('/ground_truth/odom', Odometry)]:
        subscriptions.append(node.create_subscription(typ, topic,
            lambda msg, topic=topic: records.append({'topic': topic, 'message': message_to_ordereddict(msg)}),
            qos_profile_sensor_data))
    # Let DDS discover before asking the paused world for new sensor samples.
    until = time.monotonic() + 2.
    while time.monotonic() < until:
        rclpy.spin_once(node, timeout_sec=.1)
    failures = []
    def step():
        try:
            request('/world/combined_rough_section/control', 'gz.msgs.WorldControl',
                    'pause: true multi_step: 1000')
        except Exception as exc:
            failures.append(str(exc))
    worker = threading.Thread(target=step)
    worker.start()
    until = time.monotonic() + 12.
    while time.monotonic() < until:
        rclpy.spin_once(node, timeout_sec=.1)
    worker.join(timeout=6.)
    node.destroy_node()
    rclpy.shutdown()
    # JSON allows NaN/Infinity for laser no-return values, as raw ROS data does.
    (args.output / 'sensors.json').write_text(json.dumps(records) + '\n')
    seen = {r['topic'] for r in records}
    if failures or worker.is_alive() or seen != {'/scan', '/imu/data', '/joint_states', '/ground_truth/odom'}:
        raise RuntimeError(f'Incomplete capture: topics={seen}, failures={failures}')
    print(f'Saved {len(records)} sensor messages and contact samples to {args.output}')


if __name__ == '__main__':
    main()
