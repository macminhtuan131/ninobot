"""Localization and approach invariants for the corrected flat profile."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from nino_rl.core import load_config, PathTracker, RobotState
from nino_rl.control_v2 import make_observation, validate_action_mode
from nino_rl.corridor_odometry import CorridorOdometry, wall_position
from nino_rl.flat_feedback import flat_motion_command
from nino_rl.training_contract import training_contract, validate_resume

PROFILE = Path(__file__).resolve().parents[1] / 'config/combined_flat_feedback_pilot.yaml'


def synthetic_scan(x=6.2, y=.1, yaw=.04):
    angles = -np.pi + np.arange(360) * (2*np.pi/359)
    directions = np.c_[np.cos(angles+yaw), np.sin(angles+yaw)]
    origin = np.array([x+.2*np.cos(yaw), y+.2*np.sin(yaw)])
    distances = np.full((360, 4), np.inf)
    for wall, axis in enumerate((0, 0, 1, 1)):
        with np.errstate(divide='ignore'):
            values = ([-2., 32., -2., 2.][wall] - origin[axis]) / directions[:, axis]
        distances[:, wall] = np.where(values > 0, values, np.inf)
    ranges = distances.min(axis=1)
    ranges[ranges >= 12] = np.inf
    return ranges, -np.pi, 2*np.pi/359, .08, 12.


def test_wall_measurement_corrects_position_with_offset_and_outliers():
    cfg = load_config(PROFILE)['odometry_assistance']['corridor_lidar']
    scan = synthetic_scan()
    scan[0][::11] = .4  # shorter obstacle/self returns must not localize as walls
    estimated = wall_position(scan, (6.37, -.02, .04, 0., 0.), cfg)
    np.testing.assert_allclose(estimated, [6.2, .1], atol=1e-6)
    assert wall_position(scan, (6.37, -.02, .04, .15, 0.), cfg) is None
    blank = (np.full(360, np.inf), *scan[1:])
    assert wall_position(blank, (6.37, -.02, .04, 0., 0.), cfg) is None


def test_delayed_wall_scan_corrects_historical_pose_and_stale_fix_fails_closed():
    cfg = deepcopy(load_config(PROFILE)['odometry_assistance'])
    cfg['corridor_lidar']['correction_gain'] = 1.
    estimator = CorridorOdometry(cfg)
    for t in (0., .02, .04):
        estimator.add_imu(t, 0., 0.)
        estimator.add_joint(t, t/.0625, t/.0625)
    estimator.add_scan(.02, *synthetic_scan(x=.02, y=0., yaw=0.))
    assert estimator.ready
    assert estimator.pose()['x'] == pytest.approx(.04, abs=1e-6)
    estimator.add_scan(.02, *synthetic_scan(x=.2, y=0., yaw=0.))
    assert estimator.accepted_scans == 1  # duplicate stamp ignored
    for t in np.arange(.06, .72, .02):
        estimator.add_imu(t, 0., 0.)
        estimator.add_joint(t, t/.0625, t/.0625)
    with pytest.raises(RuntimeError, match='fresh accepted wall scan'):
        estimator.pose()
    estimator.reset(min_stamp=1.)
    estimator.add_scan(.9, *synthetic_scan(x=0., y=0., yaw=0.))
    assert not estimator.ready and not estimator.scans


@pytest.mark.parametrize('y,expected_sign', [(.2,-1.),(-.2,1.)])
def test_feedback_steers_toward_path_and_fades_policy_at_approach(y, expected_sign):
    cfg = load_config(PROFILE)
    path = PathTracker([(0.,0.),(6.45,0.)])
    state = RobotState(x=6.2,y=y,yaw=0.)
    _, tracking = make_observation(state,path,cfg['path']['lookahead_m'],np.zeros(3))
    speed, yaw = flat_motion_command(state,path,tracking,cfg,0.)
    assert speed > 0 and np.sign(yaw) == expected_sign
    assert abs(yaw) <= .8
    _, with_residual = flat_motion_command(state,path,tracking,cfg,.25)
    assert abs(with_residual-yaw) < .1


def test_feedback_stops_at_estimated_goal_and_old_contract_cannot_resume():
    cfg = load_config(PROFILE)
    path = PathTracker([(0.,0.),(6.45,0.)])
    state = RobotState(x=6.45,y=0.,yaw=0.)
    _, tracking = make_observation(state,path,cfg['path']['lookahead_m'],np.zeros(3))
    assert flat_motion_command(state,path,tracking,cfg,.25) == (0.,0.)
    old = load_config(PROFILE.parent/'combined_flat_speed_yaw_timing_pilot.yaml')
    model = SimpleNamespace(nino_training_contract=training_contract(old))
    with pytest.raises(ValueError, match='contract differs'):
        validate_resume(model,cfg)
    with pytest.raises(ValueError, match='yaw semantics differ'):
        validate_action_mode(model,cfg)
    assert training_contract(cfg)['revision'] == 36
    assert training_contract(cfg)['estimated_pose_source'] == 'imu_encoder_lidar_odometry'
