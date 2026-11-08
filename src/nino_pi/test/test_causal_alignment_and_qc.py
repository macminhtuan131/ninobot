"""Tests for causal 10 Hz alignment, missing masks, frozen stats, grouped splits, upgraded QC, and GUI panels."""
import hashlib
import json
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from nino_pi.causal_alignment import (
    align_causal_frames,
    apply_frozen_normalization,
    assign_grouped_splits,
    compute_normalization_stats,
)


def _imu_event(bag_ns, wz=0.1, az=9.81, header_ns=None):
    return {
        'topic': '/imu/data',
        'bag_time_ns': bag_ns,
        'source_header_ns': bag_ns if header_ns is None else header_ns,
        'fields': {
            'angular_velocity': {'x': 0.0, 'y': 0.0, 'z': wz},
            'linear_acceleration': {'x': 0.05, 'y': -0.02, 'z': az},
        },
    }


def _wheel_event(bag_ns, left=1.2, right=1.3):
    return {
        'topic': '/motor_fb',
        'bag_time_ns': bag_ns,
        'source_header_ns': bag_ns,
        'fields': {'name': ['left_wheel', 'right_wheel'], 'velocity': [left, right]},
    }


def _cmd_event(topic, bag_ns, vx=0.15, wz=0.0):
    return {
        'topic': topic,
        'bag_time_ns': bag_ns,
        'source_header_ns': None,
        'fields': {'linear': {'x': vx, 'y': 0.0, 'z': 0.0}, 'angular': {'x': 0.0, 'y': 0.0, 'z': wz}},
    }


def test_causal_alignment_never_leaks_future_messages_and_never_zero_fills_missing():
    t0 = 1_000_000_000
    events = [
        _imu_event(t0, wz=0.11),
        # Wheel feedback arrives 1 ns AFTER tick 0 -> must NOT appear in tick 0!
        _wheel_event(t0 + 1, left=2.5, right=2.6),
        _cmd_event('/cmd_vel', t0 + 1, vx=0.20),
    ]
    # Add regular causal samples up to 0.8 s (9 ticks: t0 .. t0 + 800 ms)
    for k in range(1, 9):
        tk = t0 + k * 100_000_000
        events.append(_imu_event(tk - 5_000_000, wz=0.10 + 0.01 * k))
        events.append(_wheel_event(tk - 4_000_000, left=2.0, right=2.0))
        events.append(_cmd_event('/cmd_vel', tk, vx=0.20))
        events.append(_cmd_event('/cmd_vel_teleop', tk, vx=0.20))

    frames, summary = align_causal_frames(events, rate_hz=10.0, max_sensor_age_s=0.25, allow_policy_replay=True)
    assert summary['causal_ticks'] == 9
    # Tick 0 only had IMU at t0; wheel_fb and cmd_final arrived at t0+1 ns (future relative to tick 0).
    assert frames[0]['imu_present'] is True
    assert frames[0]['wheel_fb_present'] is False
    assert frames[0]['wheel_left_rad_s'] is None  # Never fabricated 0.0
    assert frames[0]['cmd_final_present'] is False
    assert frames[0]['cmd_final_vx_m_s'] is None
    assert frames[0]['valid_h1'] is False

    # Ticks 1..8 have all core channels causally present (8 consecutive ticks -> 8 h1, 4 h5, 1 h8).
    assert summary['history_window_counts'] == {'h1': 8, 'h5': 4, 'h8': 1}
    # Teleop is active and no RL shadow proposal exists -> td3_replay_eligible must remain False.
    assert summary['td3_replay_eligible'] is False
    assert all(f['td3_replay_eligible'] is False for f in frames)


def test_frozen_normalization_uses_train_only_and_preserves_none():
    train_frames = [
        {'imu_wz_rad_s': 1.0, 'wheel_left_rad_s': None},
        {'imu_wz_rad_s': 3.0, 'wheel_left_rad_s': 4.0},
    ]
    test_frames = [
        {'imu_wz_rad_s': 5.0, 'wheel_left_rad_s': None},
    ]
    stats = compute_normalization_stats(train_frames, columns=('imu_wz_rad_s', 'wheel_left_rad_s'))
    assert stats['features']['imu_wz_rad_s']['mean'] == 2.0
    assert stats['features']['imu_wz_rad_s']['std'] == 1.0
    normed = apply_frozen_normalization(test_frames, stats)
    assert normed[0]['imu_wz_rad_s_norm'] == pytest.approx(3.0)
    assert normed[0]['wheel_left_rad_s_norm'] is None


def test_grouped_session_splits_prevent_leakage_and_pin_heldout_to_test():
    sessions = [
        {'session_id': f's_straight_{i}', 'scenario': 'straight', 'floor_load_note': 'tile'}
        for i in range(5)
    ] + [
        {'session_id': 's_heldout_0', 'scenario': 'heldout', 'floor_load_note': 'tile'},
    ]
    split = assign_grouped_splits(sessions, ratios=(0.6, 0.2, 0.2), seed=11)
    assert 's_heldout_0' in split['buckets']['test']
    all_assigned = split['buckets']['train'] + split['buckets']['validation'] + split['buckets']['test']
    assert len(all_assigned) == 6 and len(set(all_assigned)) == 6
    with pytest.raises(ValueError, match='duplicate'):
        assign_grouped_splits(sessions + [sessions[0]])


def test_upgraded_gui_panels_expose_governance_and_status_banner():
    pytest.importorskip('PyQt5')
    from PyQt5 import QtWidgets as Q
    from nino_pi.studio_panel import StudioPanel
    from nino_pi.td3_parameter_panel import TD3ParameterPanel

    app = Q.QApplication.instance() or Q.QApplication([])
    p_param = TD3ParameterPanel()
    s_panel = StudioPanel(lambda: {'host': 'pi@192.168.1.50', 'key': '~/.ssh/id_ed25519', 'domain': 0}, demo=True)
    try:
        assert p_param.tabs.count() == 2
        assert p_param.check() is not None
        assert 'search_bounds_check' in p_param.result.toPlainText()
        assert 'BLOCKED' in p_param.governance_view.toPlainText()
        p_param.stage_checks['observation_action_contract'].setChecked(True)
        assert 'dynamics_model_sysid' in p_param.governance_view.toPlainText()

        assert '0 motor publishers' in s_panel.status_banner.text()
        s_panel.scenario.setCurrentIndex(s_panel.scenario.findData('heldout'))
        assert 'TEST' in s_panel.scenario_guide.text()
    finally:
        p_param.close()
        s_panel.close()
        app.processEvents()


def test_exporter_writes_causal_manifest_and_enforces_raw_guards(tmp_path, monkeypatch):
    import sys
    import types
    from nino_pi import dataset_exporter

    raw = tmp_path / 'session_stub' / 'raw'
    (raw / 'bag').mkdir(parents=True)
    (raw / 'manifest.json').write_text('{"status":"captured_not_calibrated","issues":[]}')
    hashes = {'manifest.json': hashlib.sha256((raw / 'manifest.json').read_bytes()).hexdigest()}
    (raw / 'sha256.json').write_text(json.dumps(hashes))

    class FakeMsg:
        pass

    fake_records = [
        ('/imu/data', 'sensor_msgs/msg/Imu', 1_000_000_000, FakeMsg()),
        ('/motor_fb', 'sensor_msgs/msg/JointState', 1_000_000_000, FakeMsg()),
        ('/cmd_vel', 'geometry_msgs/msg/Twist', 1_000_000_000, FakeMsg()),
    ]
    payloads = [
        {'angular_velocity': {'x': 0.0, 'y': 0.0, 'z': 0.05}, 'linear_acceleration': {'x': 0.0, 'y': 0.0, 'z': 9.81}},
        {'name': ['left_wheel', 'right_wheel'], 'velocity': [1.0, 1.0]},
        {'linear': {'x': 0.1, 'y': 0.0, 'z': 0.0}, 'angular': {'x': 0.0, 'y': 0.0, 'z': 0.0}},
    ]
    headers = [(1_000_000_000, 'imu_link'), (1_000_000_000, 'base_link'), (None, None)]
    idx = {'i': 0}

    monkeypatch.setattr(dataset_exporter, 'decoded', lambda _bag: iter(fake_records))
    monkeypatch.setattr(dataset_exporter, 'source_header', lambda _m: headers[idx['i']])

    fake_rosidl = types.ModuleType('rosidl_runtime_py.convert')
    def _to_od(_m):
        out = payloads[idx['i']]
        idx['i'] += 1
        return out
    fake_rosidl.message_to_ordereddict = _to_od

    fake_pa = types.ModuleType('pyarrow')
    fake_pa.string = lambda: 'string'
    fake_pa.int64 = lambda: 'int64'
    fake_pa.float64 = lambda: 'float64'
    fake_pa.bool_ = lambda: 'bool'
    fake_pa.schema = lambda fields: list(fields)
    fake_pa.Table = types.SimpleNamespace(from_pylist=lambda rows, schema=None: {'rows': list(rows), 'schema': schema})

    fake_pq = types.ModuleType('pyarrow.parquet')
    class FakeWriter:
        def __init__(self, path, schema):
            self.path = Path(path)
            self.batches = []
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.path.write_text(json.dumps(self.batches))
        def write_table(self, table):
            self.batches.extend(table['rows'])
    fake_pq.ParquetWriter = FakeWriter
    fake_pq.write_table = lambda table, path: Path(path).write_text(json.dumps(table))
    fake_pa.parquet = fake_pq

    monkeypatch.setitem(sys.modules, 'pyarrow', fake_pa)
    monkeypatch.setitem(sys.modules, 'pyarrow.parquet', fake_pq)
    monkeypatch.setitem(sys.modules, 'rosidl_runtime_py', types.ModuleType('rosidl_runtime_py'))
    monkeypatch.setitem(sys.modules, 'rosidl_runtime_py.convert', fake_rosidl)

    derived = tmp_path / 'derived_stub'
    report = dataset_exporter.export_session(tmp_path / 'session_stub', derived)
    assert report['rows'] == 3
    assert report['causal_frames_rows'] == 1
    assert report['td3_replay_eligible'] is False
    assert report['causal_history_window_counts'] == {'h1': 1, 'h5': 0, 'h8': 0}
    causal_table = json.loads((derived / 'causal_frames.parquet').read_text())
    assert causal_table['rows'][0]['valid_h1'] is True
    assert causal_table['rows'][0]['imu_wz_rad_s'] == 0.05
    manifest = json.loads((derived / 'causal_manifest.json').read_text())
    assert manifest['schema_sha256'] == report['causal_schema_sha256']


def test_qc_command_chain_drift_and_annotations(tmp_path):
    rosbag2_py = pytest.importorskip('rosbag2_py')
    from rclpy.serialization import serialize_message
    from geometry_msgs.msg import Twist
    from nav2_msgs.msg import CollisionMonitorState
    from sensor_msgs.msg import Imu, JointState
    from nino_pi.studio_quality import inspect_session, verify_raw

    root = tmp_path / 'session_qc'
    raw = root / 'raw'
    raw.mkdir(parents=True)
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(raw / 'bag'), storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    topics = [
        (0, '/imu/data', 'sensor_msgs/msg/Imu'),
        (1, '/motor_fb', 'sensor_msgs/msg/JointState'),
        (2, '/cmd_vel_teleop', 'geometry_msgs/msg/Twist'),
        (3, '/cmd_vel', 'geometry_msgs/msg/Twist'),
        (4, '/collision_monitor_state', 'nav2_msgs/msg/CollisionMonitorState'),
    ]
    for tid, name, typ in topics:
        writer.create_topic(rosbag2_py.TopicMetadata(id=tid, name=name, type=typ, serialization_format='cdr'))

    base = 10_000_000_000
    for k in range(6):
        stamp = base + k * 100_000_000
        imu = Imu()
        imu.header.stamp.sec = stamp // 10**9
        imu.header.stamp.nanosec = stamp % 10**9
        imu.header.frame_id = 'imu_link'
        imu.linear_acceleration.z = 9.81
        imu.angular_velocity.z = 0.02
        writer.write('/imu/data', serialize_message(imu), stamp)

        fb = JointState()
        fb.header.stamp.sec = stamp // 10**9
        fb.header.stamp.nanosec = stamp % 10**9
        fb.name = ['left_wheel', 'right_wheel']
        fb.velocity = [0.0, 0.0]
        writer.write('/motor_fb', serialize_message(fb), stamp)

        tel = Twist(); tel.linear.x = 0.25
        writer.write('/cmd_vel_teleop', serialize_message(tel), stamp)

        cmd = Twist(); cmd.linear.x = 0.0  # Blocked downstream!
        writer.write('/cmd_vel', serialize_message(cmd), stamp)

        cm = CollisionMonitorState(); cm.action_type = 1; cm.polygon_name = 'PolygonStop'
        writer.write('/collision_monitor_state', serialize_message(cm), stamp)
    del writer

    config = {'topics': [{'name': '/imu/data', 'required': True}, {'name': '/motor_fb', 'required': True},
                         {'name': '/cmd_vel', 'required': True}], 'storage_id': 'mcap'}
    (raw / 'collection_config.json').write_text(json.dumps(config))
    (raw / 'manifest.json').write_text(json.dumps({'status': 'captured_not_calibrated', 'issues': [], 'reason': 'duration_reached'}))
    hashes = {str(p.relative_to(raw)): hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.rglob('*') if p.is_file()}
    (raw / 'sha256.json').write_text(json.dumps(hashes))
    (root / 'annotations.json').write_text(json.dumps([
        {'wall_time_ns': base, 'receipt_monotonic_ns': 1000, 'text': 'operator observed PolygonStop blocking motion'}
    ]))

    qc = inspect_session(root)
    assert qc['verdict'] == 'WARN' and qc['level'] == 'Q2'
    assert qc['command_chain']['blocked_upstream_motion'] is True
    assert qc['command_chain']['collision_monitor_stop_samples'] == 6
    assert qc['annotations_summary']['count'] == 1
    assert qc['causal_10hz_readiness']['valid_h5_windows'] == 2
    assert any('Upstream motion command was blocked' in r for r in qc['recommendations'])
    assert verify_raw(raw)['mismatches'] == []
