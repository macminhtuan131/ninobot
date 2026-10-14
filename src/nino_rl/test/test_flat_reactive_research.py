"""Research invariants: no privileged inputs, no layout leakage, causal control."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from nino_rl.flat_reactive_research import (
    ReactiveReference, SensorHistory, scenario_bank, scenario_cables, sensor_frame,
)

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT/'src/nino_rl/config/flat_proprioceptive_research.yaml').read_text())


def state():
    return SimpleNamespace(roll=0., pitch=0., gyro_x=0., gyro_y=0., gyro_z=0.,
                           accel_x=0., accel_y=0., accel_z=9.80665,
                           left_wheel_velocity=6.4, right_wheel_velocity=6.4)


def feedback(scale=1.):
    return dict(executed_linear_m_s=.4*scale, executed_yaw_rad_s=0., filtered_speed_scale=scale)


def test_actor_and_reactive_reference_ignore_pose_obstacles_and_ground_truth():
    a = state(); b = deepcopy(a)
    for key in ('x','y','yaw','ground_x','ground_y','ground_linear_velocity',
                'path_progress','terrain_preview','caster_joint_state','lidar_ranges'):
        setattr(b, key, object())
    imu = dict(duration=.1, square_integral=.02, peak=2.)
    np.testing.assert_array_equal(sensor_frame(a,(.4,0),feedback(),imu,.1),
                                  sensor_frame(b,(.4,0),feedback(),imu,.1))
    ra = ReactiveReference(SPEC['reactive_reference'])
    rb = ReactiveReference(SPEC['reactive_reference'])
    for _ in range(12):
        assert ra.update(a, feedback(), .1) == rb.update(b, feedback(), .1)
    history = SensorHistory(5)
    assert history.reset(sensor_frame(a,(.4,0),feedback(),imu,.1)).shape == (90,)
    with pytest.raises(ValueError, match='Invalid IMU'):
        sensor_frame(a,(.4,0),feedback(),dict(duration=.1,square_integral=float('nan')),.1)


def test_reactive_brakes_after_signal_then_recovers_and_rearms():
    cfg = deepcopy(SPEC['reactive_reference'])
    reference = ReactiveReference(cfg)
    s = state()
    for _ in range(10):
        assert reference.update(s, feedback(), .1)[0] == 1.
    s.accel_z += 10.
    target, trace = reference.update(s, feedback(), .1)
    assert target == .7 and trace['phase'] == 'holding' and trace['events'] == 1
    s.accel_z = 9.80665
    actual_scale = 1.
    for _ in range(40):
        s.left_wheel_velocity = s.right_wheel_velocity = .4*actual_scale/.0625
        target, trace = reference.update(s, feedback(actual_scale), .1)
        actual_scale = min(actual_scale+.04, max(actual_scale-.04, target))
    assert actual_scale == pytest.approx(1.) and trace['phase'] == 'ready'
    s.accel_z += 10.
    assert reference.update(s, feedback(), .1)[1]['events'] == 2
    cfg['hold_seconds'] = .6
    with pytest.raises(ValueError, match='too short'):
        ReactiveReference(cfg)


def test_real_layout_changes_and_disjoint_holdout_geometry():
    a = scenario_bank(SPEC)
    assert a == scenario_bank(SPEC)
    cases = a['scenarios']
    assert len(cases) == 168 and len({r['id'] for r in cases}) == len(cases)
    layouts = {tuple(tuple(o.values()) for o in r['obstacles']) for r in cases}
    assert len(layouts) == len(cases)
    for r in cases:
        assert 1 <= len(r['obstacles']) <= (1 if r['stage']=='A' else 6)
        xs = [o['x_m'] for o in r['obstacles']]
        assert all(1.5 <= x <= 4.9 for x in xs)
        assert all(b-a >= .55-1e-6 for a,b in zip(xs,xs[1:]))
        expected = SPEC['scenarios']['heldout_radii_m' if r['split']=='test' else 'training_radii_m']
        assert all(o['radius_m'] in expected and abs(o['angle_deg'])<=30 for o in r['obstacles'])
        tuples = scenario_cables(a,r['id'])
        assert [v[:2] for v in tuples] == [(o['x_m'],o['radius_m']) for o in r['obstacles']]
    assert scenario_cables(a,'A_train_000') != scenario_cables(a,'A_train_001')
    with pytest.raises(ValueError, match='Unknown'):
        scenario_cables(a,'missing')


def test_generated_runtime_rejects_coordinate_profile_and_missing_feedback(monkeypatch):
    script = ROOT/'src/nino_rl/scripts/prepare_flat_reactive_research.py'
    spec = importlib.util.spec_from_file_location('flat_preparation_test',script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    namespace = {}; exec(module.RUNTIME,namespace)
    monkeypatch.setenv('NINO_FLAT_RESEARCH_PROFILE','schedule')
    with pytest.raises(ValueError, match='Coordinate'):
        namespace['scripted_scale'](object(),1.)
    env = SimpleNamespace(config={'policy_v2':dict(sensor_wait_timeout_seconds=.001,
                                                 motion_max_lag_seconds=.04)},
                          ros=SimpleNamespace(drive_diagnostics=lambda start,end:[]))
    with pytest.raises(RuntimeError, match='No fresh'):
        namespace['feedback'](env,0.,.1)


def test_failed_csv_arrival_is_not_truthy(tmp_path, monkeypatch):
    script = ROOT/'src/nino_rl/scripts/run_flat_reactive_screen.py'
    spec = importlib.util.spec_from_file_location('flat_screen_test',script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rows = []
    for profile in ('full','reactive'):
        directory = tmp_path/profile
        trace = directory/'run/episode-001';trace.mkdir(parents=True)
        (directory/'run/summary.json').write_text('{"complete":true}')
        (trace/'control_trace.csv').write_text('research_disturbed,research_phase\nFalse,ready\n')
        rows.append(dict(output=str(directory), repeat=1, profile=profile,
                         scenario=dict(id='A_train_000',obstacles=[{'x_m':2.}])) )
    episode = dict(success='0',truth_endpoint_error_m='2.0',time_seconds='20',
                   truth_path_rmse_m='.01',rms_vertical_acceleration_m_s2='1',rms_wheel_slip='.02')
    monkeypatch.setattr(module,'complete_evaluation',lambda path,count:([episode],{}))
    monkeypatch.setattr(module,'safe_window',lambda rows,windows:dict(available=False))
    module.analyze(dict(rows=rows,qualification='test'),tmp_path)
    import json
    result = json.loads((tmp_path/'analysis.json').read_text())
    assert result['table']['full']['arrivals'] == 0
    assert result['paired'][0]['crossing_ratios']['slip_energy_per_m'] is None
