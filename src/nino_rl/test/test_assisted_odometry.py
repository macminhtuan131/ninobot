from math import pi
from threading import Lock
from types import SimpleNamespace

import pytest

from nino_rl.assisted_odometry import ImuEncoderOdometry
from nino_rl.core import RobotState, load_config
from nino_rl.ros_interface import RosRobotInterface
from nino_rl.training_contract import training_contract, validate_resume
from nino_rl.control_v2 import ImuWindow
from sensor_msgs.msg import Imu
from pathlib import Path


def test_encoder_increments_project_slope_and_survive_duplicate_packets():
    e = ImuEncoderOdometry({'wheel_radius_m': 1.})
    e.add_imu(0., 0., pi/3)
    e.add_joint(0., 0., 0.)
    e.add_joint(.02, 1., 1.)
    e.add_joint(.02, 900., 900.)  # duplicate must not create false distance
    assert e.pose()['x'] == 0.  # future joint waits for matching IMU
    e.add_imu(.02, 0., pi/3)
    assert e.pose()['x'] == pytest.approx(.5)
    assert e.pose()['linear_velocity'] == pytest.approx(25.)


def test_yaw_interpolation_crosses_pi_without_full_circle_jump():
    e = ImuEncoderOdometry({'wheel_radius_m': 1.})
    e.add_imu(0., pi-.01, 0.)
    e.add_joint(0., 0., 0.)
    e.add_joint(.01, 0., 0.)
    e.add_imu(.02, -pi+.01, 0.)
    assert e.pose()['yaw'] == pytest.approx(.01)


def test_reset_reanchors_and_rejects_packets_from_previous_episode():
    e = ImuEncoderOdometry({})
    e.add_imu(1., 1., 0.)
    e.add_joint(1., 50., 50.)
    e.reset(min_stamp=2.)
    e.add_imu(1.5, -1., 0.)
    e.add_joint(1.5, 900., 900.)
    with pytest.raises(RuntimeError, match='No synchronized'):
        e.pose()
    e.add_imu(2.02, -.5, 0.)
    e.add_joint(2.02, 70., 70.)
    assert e.pose()['x'] == 0.
    assert e.pose()['yaw'] == 0.


def test_gap_does_not_silently_credit_unknown_motion():
    e = ImuEncoderOdometry({'max_imu_gap_seconds': .03})
    e.add_imu(0., 0., 0.)
    e.add_joint(0., 0., 0.)
    e.add_joint(.02, 1., 1.)
    with pytest.raises(RuntimeError, match='IMU gap'):
        e.add_imu(.06, 0., 0.)


def test_delayed_imu_never_uses_a_future_orientation():
    e = ImuEncoderOdometry({'imu_delay_seconds': .02})
    e.add_imu(0., 0., 0.)
    e.add_joint(0., 0., 0.)
    assert not e.ready
    e.add_imu(.02, 0., 0.)
    assert e.pose()['odom_stamp_s'] == 0.
    e.add_joint(.02, 1., 1.)
    e.add_imu(.04, 0., 0.)
    assert e.pose()['odom_stamp_s'] == .02


def test_snapshot_selects_assisted_pose_and_preserves_raw_state_and_truth():
    e = ImuEncoderOdometry({})
    e.add_imu(0., 0., 0.)
    e.add_joint(0., 0., 0.)
    raw = RobotState(x=5., ground_x=10.)
    ros = SimpleNamespace(_lock=Lock(), _state=raw, _assisted_odometry=e, _assisted_error=None)
    state = RosRobotInterface.snapshot(ros)
    assert state.x == 0. and state.ground_x == 10.
    assert raw.x == 5.
    ros._assisted_error = 'stale sensor'
    with pytest.raises(RuntimeError, match='stale sensor'):
        RosRobotInterface.snapshot(ros)
    ros._assisted_odometry = None
    assert RosRobotInterface.snapshot(ros).x == 5.


def test_new_estimator_requires_a_new_training_contract():
    root = Path(__file__).parents[1] / 'config'
    raw = load_config(root / 'rough_e1_stop_margin_check.yaml')
    assisted = load_config(root / 'rough_e1_imu_assisted.yaml')
    assert training_contract(assisted)['revision'] == 35
    with pytest.raises(ValueError, match='contract differs'):
        validate_resume(SimpleNamespace(nino_training_contract=training_contract(raw)), assisted)
    assert assisted['goal_tolerance_m'] == raw['goal_tolerance_m'] == .2


@pytest.mark.parametrize('unavailable', [False, True])
def test_missing_imu_orientation_cannot_silently_become_perfect_heading(unavailable):
    e = ImuEncoderOdometry({})
    ros = SimpleNamespace(_lock=Lock(), _state=RobotState(), _assisted_odometry=e,
        _assisted_error=None, _imu_epoch_min_stamp=-float('inf'),
        imu_window=ImuWindow(), imu_includes_gravity=False, _mark_received=lambda name: None)
    msg = Imu()
    msg.header.stamp.sec = 1
    msg.orientation.w = 0.
    if unavailable:
        msg.orientation.w = 1.
        msg.orientation_covariance[0] = -1.
    RosRobotInterface._imu_callback(ros, msg)
    assert 'valid orientation' in ros._assisted_error
    assert not e.ready
