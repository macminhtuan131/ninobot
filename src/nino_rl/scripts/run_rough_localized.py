#!/usr/bin/env python3
"""Isolate experimental rough localization from the running flat study.

prepare freezes package sources, estimator, robot and terrain hashes. PI uses
this exact snapshot. Training is refused until the physical PI gate passes.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / 'rl_runs/rough_wall_recovery_v16'
MAX_PI_COMMANDED_STALL_SECONDS = 2.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    sys.path.insert(0, str(ROOT / 'src/nino_rl'))
    from nino_rl.core import load_config
    import yaml
    source = ROOT / 'src/nino_rl/nino_rl'
    estimator = ROOT / 'src/nino_rl/scripts/rough_wall_odometry.py'
    files = list(source.glob('*.py')) + [estimator, Path(__file__).with_name('rough_cloud_snapshot.py'), Path(__file__).with_name('rough_stall_recovery.py'),
        ROOT/'src/nino_description/launch/sim.launch.py', ROOT/'src/nino_rl/launch/training_sim.launch.py',
        ROOT / 'src/nino_description/urdf/nino.urdf.xacro',
        ROOT / 'rl_runs/rough_terrain_bank_v1/worlds/original.sdf']
    files += list((ROOT / 'src/nino_control/nino_control').glob('*.py'))
    files += list((ROOT / 'src/nino_description/meshes').glob('*.STL'))
    files += list((ROOT / 'rl_runs/rough_terrain_bank_v1/meshes').glob('*.stl'))
    # Include referenced terrain assets (the world can use an absolute mesh URI).
    import xml.etree.ElementTree as ET
    world = ROOT / 'rl_runs/rough_terrain_bank_v1/worlds/original.sdf'
    for element in ET.parse(world).findall('.//mesh/uri'):
        uri = element.text
        path = Path(uri.removeprefix('file://'))
        if path.is_file():
            files.append(path)
    hashes = {str(p.resolve()): digest(p) for p in files}
    snapshot_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    config = load_config(ROOT / 'src/nino_rl/config/rough_turn_recovery_candidate.yaml')
    config['rough_experiment'] = {'revision': 'rough_wall_recovery_v16', 'snapshot_sha256': snapshot_hash,
                                'imu_transport': 'reliable_v1',
                                'encoder_transport': 'history_100_v1',
                                'localization_sensor': 'vertical_cloud_v1',
                                'loss_handling': 'terminal_navigation_invalid_v1', 'stall_recovery': 'bounded_backoff_s1_alignment_v3'}
    manifest = {'schema': 1, 'inputs': hashes, 'snapshot_sha256': snapshot_hash, 'config': config}
    if (EXPERIMENT / 'manifest.json').exists():
        old = json.loads((EXPERIMENT / 'manifest.json').read_text())
        if {key: old[key] for key in manifest} != manifest:
            raise RuntimeError('Experimental inputs changed; use a new experiment revision/directory')
        verify()
        print(f'Existing immutable rough snapshot verified: {EXPERIMENT}')
        return
    if EXPERIMENT.exists() and any(EXPERIMENT.iterdir()):
        raise RuntimeError('Partial experiment directory exists; inspect it before preparing')
    package = EXPERIMENT / 'python/nino_rl'
    package.mkdir(parents=True)
    for path in source.glob('*.py'):
        shutil.copy2(path, package / path.name)
    shutil.copy2(estimator, package / 'corridor_odometry.py')
    interface = package / 'ros_interface.py'
    content = interface.read_text()
    original = 'IMU_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=100,\n                     reliability=ReliabilityPolicy.BEST_EFFORT)'
    if content.count(original) != 1:
        raise RuntimeError('IMU QoS declaration changed; inspect before generating a reliable snapshot')
    interface.write_text(content.replace(original,original.replace('BEST_EFFORT','RELIABLE')))
    reference = 'return not self.stale_straight_reference_streams(stale_after)'
    content = interface.read_text()
    if content.count(reference) != 1:
        raise RuntimeError('Straight reference validity declaration changed')
    content = content.replace(reference,
        'return (not self.stale_straight_reference_streams(stale_after) and '\
        '(self._assisted_odometry is None or '\
        'getattr(self._assisted_odometry, "localization_valid", True)))')
    interface.write_text(content)
    from rough_cloud_snapshot import install_cloud_subscription, generate_sensor_files
    install_cloud_subscription(interface)
    environment = package/'ros_env.py'
    content = environment.read_text()
    old = 'navigation_invalid = self.nav_invalid_seconds >= float(self.config["navigation_invalid_hold_seconds"])'
    if content.count(old) != 1:
        raise RuntimeError('Navigation termination declaration changed')
    content = content.replace(old,
        'navigation_invalid = (self.nav_invalid_seconds >= float(self.config["navigation_invalid_hold_seconds"]) '\
        'or not getattr(truth, "localization_valid", True))')
    environment.write_text(content)
    recovery = Path(__file__).with_name('rough_stall_recovery.py')
    shutil.copy2(recovery, package/'rough_stall_recovery.py')
    from rough_stall_recovery import install_recovery
    install_recovery(package)
    bridge = [{'ros_topic_name':'/rough/imu/data','gz_topic_name':'/imu/data',
        'ros_type_name':'sensor_msgs/msg/Imu','gz_type_name':'gz.msgs.IMU',
        'direction':'GZ_TO_ROS','frame_id':'imu_link','publisher_queue':100},
        {'ros_topic_name':'/rough/localization/points','gz_topic_name':'/rough_localization_scan/points',
        'ros_type_name':'sensor_msgs/msg/PointCloud2','gz_type_name':'gz.msgs.PointCloudPacked',
        'direction':'GZ_TO_ROS','frame_id':'laser','publisher_queue':10}]
    (EXPERIMENT/'imu_bridge.yaml').write_text(yaml.safe_dump(bridge,sort_keys=False))
    manifest['bridge_sha256'] = digest(EXPERIMENT/'imu_bridge.yaml')
    manifest['snapshot_files'] = {str(p.relative_to(EXPERIMENT)): digest(p) for p in package.glob('*.py')}
    for filename, content in generate_sensor_files(ROOT,EXPERIMENT,config).items():
        (EXPERIMENT/filename).write_text(content)
        manifest['snapshot_files'][filename] = digest(EXPERIMENT/filename)
    # Comparison on subsequent prepare includes the immutable generated snapshot.
    (EXPERIMENT / 'config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
    manifest['config_sha256'] = digest(EXPERIMENT / 'config.yaml')
    (EXPERIMENT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Prepared NEW rough contract: {EXPERIMENT}; flat source files were not changed')


def verify():
    manifest = json.loads((EXPERIMENT / 'manifest.json').read_text())
    # Core RL is snapshotted, so the user may finish/change flat separately.
    for relative, expected in manifest['snapshot_files'].items():
        if digest(EXPERIMENT / relative) != expected:
            raise RuntimeError(f'Frozen rough package changed: {relative}')
    for filename, expected in manifest['inputs'].items():
        path = Path(filename)
        if '/nino_control/nino_control/' in filename or '/nino_description/' in filename or '/rough_terrain_bank_v1/' in filename:
            if digest(path) != expected:
                raise RuntimeError(f'Rough controller/robot/terrain changed: {filename}')
    if digest(EXPERIMENT / 'config.yaml') != manifest['config_sha256']:
        raise RuntimeError('Frozen rough config changed')
    if digest(EXPERIMENT / 'imu_bridge.yaml') != manifest['bridge_sha256']:
        raise RuntimeError('Reliable IMU bridge changed')
    return manifest


def longest_commanded_stall(path):
    """Physical translation stops while raw encoders report travel, away from goal."""
    if not path.exists():
        raise RuntimeError(f'Missing physical control trace: {path}')
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    if len(rows)<2:
        raise RuntimeError(f'Incomplete physical control trace: {path}')
    previous = None
    duration = longest = 0.
    for row in rows:
        values = [float(row[key]) for key in ('elapsed_s','raw_wheel_stamp_s',
            'raw_wheel_x_m','raw_wheel_y_m','physical_speed_m_s','physical_goal_distance_m','speed_scale',
            'physical_x_m','physical_y_m')]
        import math
        if not all(map(math.isfinite,values)):
            raise RuntimeError(f'Nonfinite physical control trace: {path}')
        if previous:
            elapsed = values[0]-previous[0]
            dt = values[1]-previous[1]
            if elapsed<=0 or dt<=0:
                raise RuntimeError(f'Unordered physical control trace: {path}')
            wheel_speed = math.hypot(values[2]-previous[2],values[3]-previous[3])/dt
            physical_xy_speed = math.hypot(values[7]-previous[7],values[8]-previous[8])/elapsed
            stopped = physical_xy_speed<.025 and abs(values[4])<.025 and values[5]>.5 and values[6]>.1 and wheel_speed>.05
            duration = duration+elapsed if stopped else 0.
            longest = max(longest,duration)
        previous=values
    return longest


def physical_gate():
    verify()
    reports = {}
    route_seeds = {'E1': [10000,10003,10006], 'N1': [10001,10004,10007], 'S1': [10002,10005,10008]}
    profiles = [(route,route,EXPERIMENT/'pi'/route,1.) for route in route_seeds]
    profiles.append(('E1_slow','E1',EXPERIMENT/'slow_e1',.65))
    for label,route,directory,speed_scale in profiles:
        candidates = sorted(directory.glob('*/summary.json'))
        if not candidates:
            raise RuntimeError(f'Missing PI validation for {label}')
        summary_path = candidates[-1]
        summary = json.loads(summary_path.read_text())
        with (summary_path.parent / 'episodes.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        config_path = summary_path.parent / 'ppo.yaml'
        if not config_path.exists():
            config_path = summary_path.parent / 'config.yaml'
        if not config_path.exists():
            raise RuntimeError(f'Missing saved PI config: {summary_path.parent}')
        import yaml
        actual = yaml.safe_load(config_path.read_text())
        expected = json.loads((EXPERIMENT / 'manifest.json').read_text())['config']
        from nino_rl.evaluation import prepare_evaluation_config
        expected = prepare_evaluation_config(expected, route=route, baseline=True, control_trace=True)
        if actual != expected:
            raise RuntimeError(f'PI config differs from new contract: {route}')
        seeds = route_seeds[route]
        if (not summary.get('complete') or len(rows) != 3 or summary.get('evaluation_seeds') != seeds
                or summary.get('controller') != 'path_pi_baseline' or summary.get('baseline_speed_scale') != speed_scale):
            raise RuntimeError(f'Incomplete PI validation: {label}')
        passed = all(str(r['success']).lower() in ('true', '1', '1.0')
                     and float(r['truth_endpoint_error_m']) <= .20
                     and float(r['odom_truth_position_error_m']) <= .10
                     and int(r['route_gates_passed']) == int(r['route_gates_total']) for r in rows)
        stall_seconds = [longest_commanded_stall(summary_path.parent/f'episode-{index:03d}'/'control_trace.csv')
                         for index,_ in enumerate(rows,1)]
        stall_passed = max(stall_seconds)<=MAX_PI_COMMANDED_STALL_SECONDS
        reports[label] = {'passed': passed, 'episodes': len(rows), 'speed_scale': speed_scale, 'summary': str(summary_path),
                          'summary_sha256': digest(summary_path), 'episodes_sha256': digest(summary_path.parent/'episodes.csv'),
                          'physical_arrival_passed': passed, 'stall_passed': stall_passed,
                          'longest_commanded_stall_seconds': max(stall_seconds),
                          'control_trace_sha256': [digest(summary_path.parent/f'episode-{index:03d}'/'control_trace.csv')
                                                   for index,_ in enumerate(rows,1)]}
        reports[label]['passed'] = passed and stall_passed
    evidence = {'schema':2,'maximum_pi_commanded_stall_seconds':MAX_PI_COMMANDED_STALL_SECONDS,
                'passed': all(r['passed'] for r in reports.values()), 'routes': reports,
                'note': 'Three seed checks are a pilot qualification, not statistical proof of reliability.'}
    (EXPERIMENT / 'pi_gate.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    if not evidence['passed']:
        raise RuntimeError('Rough PI physical-arrival/localization gate failed; training stays held')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'pi', 'gate', 'curriculum'])
    args, rest = parser.parse_known_args()
    os.chdir(ROOT)
    if args.operation == 'prepare':
        prepare()
        return
    verify()
    sys.path.insert(0, str(EXPERIMENT / 'python'))
    os.environ.update(ROS_DOMAIN_ID='78', NINO_ROS_DOMAIN_ID='78', GZ_PARTITION='nino_rough_78',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    overlay = str(EXPERIMENT / 'python')
    os.environ['PYTHONPATH'] = overlay + os.pathsep + os.environ.get('PYTHONPATH', '')
    if args.operation == 'gate':
        physical_gate()
        return
    if args.operation == 'pi':
        if rest:
            parser.error('PI validation seeds/config are fixed; no additional flags')
        config = str(EXPERIMENT / 'config.yaml')
        subprocess.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py', '--config', config], check=True)
        for route, seeds in [('E1', [10000,10003,10006]), ('N1', [10001,10004,10007]), ('S1', [10002,10005,10008])]:
            existing = sorted((EXPERIMENT/'pi'/route).glob('*/summary.json'), reverse=True)
            if existing:
                saved = json.loads(existing[0].read_text())
                if saved.get('complete') and saved.get('evaluation_seeds') == seeds and saved.get('episodes') == 3:
                    print(f'Preserving completed {route} PI evidence: {existing[0]}', flush=True)
                    continue
            subprocess.run(['ros2', 'run', 'nino_rl', 'evaluate_baseline', '--config', config,
                '--route', route, '--baseline-speed-scale', '1.0', '--seeds', *map(str,seeds),
                '--control-trace', '--output', str(EXPERIMENT/'pi'/route)], check=True)
        physical_gate()
        return
    if '--plan' not in rest:
        physical_gate()
    forbidden = ('--config', '--output', '--domain')
    if any(value.split('=')[0] in forbidden for value in rest):
        parser.error('The experiment fixes config, output and domain')
    # Import the frozen package before the legacy runner adds the source path.
    sys.path.insert(0, overlay)
    import nino_rl.core
    import runpy
    import yaml
    cfg = json.loads((EXPERIMENT/'manifest.json').read_text())['config']
    candidate = yaml.safe_load((ROOT/'src/nino_rl/config/rough_turn_curriculum_candidate.yaml').read_text())
    cfg['rough_curriculum'] = candidate['rough_curriculum']
    cfg['rough_curriculum']['revision'] = 'fixed_wall_recovery_v16'
    path = EXPERIMENT/'curriculum.yaml'
    text = yaml.safe_dump(cfg, sort_keys=False)
    if path.exists() and path.read_text() != text:
        raise RuntimeError('Curriculum contract changed')
    path.write_text(text)
    sys.argv = ['train_rough_curriculum.py', '--config', str(path),
                '--output', str(EXPERIMENT/'curriculum'), '--domain', '78', *rest]
    runpy.run_path(str(ROOT/'src/nino_rl/scripts/train_rough_curriculum.py'), run_name='__main__')


if __name__ == '__main__':
    main()
