"""Fault injection for epoch initialization and paused-world telemetry delivery."""
from collections import deque
import csv
from io import StringIO
import json
from threading import Lock, Thread
from time import sleep
from types import SimpleNamespace

import pytest

from nino_rl.assisted_odometry import ImuEncoderOdometry
from nino_rl.core import RobotState
from nino_rl.evaluation import append_action_traces
from nino_rl.ros_interface import RosRobotInterface


def transport():
    return SimpleNamespace(_lock=Lock(), _drive_diagnostics=deque(), _drive_epoch_min_stamp=1.)


def test_deferred_discovery_backlog_is_not_fused_but_active_gaps_still_fault():
    estimator = ImuEncoderOdometry({})
    ros = SimpleNamespace(_assisted_odometry=estimator, _assisted_error=None,
                          _assisted_epoch_active=False, _mark_received=lambda name: None)
    # These discovery samples would create an invalid .3 s IMU interpolation.
    for sensor, values in (("imu", (0., 0., 0.)), ("joint", (.1, 0., 0.)),
                           ("imu", (.3, 0., 0.))):
        RosRobotInterface._update_assisted(ros, sensor, *values)
    assert not estimator.imus and not estimator.joints and ros._assisted_error is None
    ros._assisted_epoch_active = True
    RosRobotInterface._update_assisted(ros, "imu", 0., 0., 0.)
    RosRobotInterface._update_assisted(ros, "joint", .1, 0., 0.)
    RosRobotInterface._update_assisted(ros, "imu", .3, 0., 0.)
    assert "IMU gap" in ros._assisted_error
    # No automatic recovery within a live epoch.
    RosRobotInterface._update_assisted(ros, "imu", .31, 0., 0.)
    assert "IMU gap" in ros._assisted_error


def test_reset_establishes_new_fusion_and_diagnostic_epoch_without_old_samples():
    ros = transport()
    ros._sim_clock_stamp = 2.
    ros._assisted_odometry = ImuEncoderOdometry({})
    ros._assisted_error = "old epoch fault"
    ros._assisted_epoch_active = False
    ros._received, ros._received_at = {"assisted_odom"}, {"assisted_odom": 0.}
    ros.reset_odometry = SimpleNamespace(wait_for_service=lambda **kw: True)
    ros._call_idempotent_service = lambda *args: SimpleNamespace(success=True)
    ros._drive_diagnostics.append(dict(sim_time_s=1.99))
    RosRobotInterface.reset_drive_state(ros, .1)
    assert ros._assisted_epoch_active and ros._assisted_error is None
    assert ros._assisted_odometry.min_stamp == ros._drive_epoch_min_stamp == 2.
    assert not ros._drive_diagnostics and "assisted_odom" not in ros._received
    def message(stamp):
        return SimpleNamespace(layout=SimpleNamespace(dim=[SimpleNamespace(label="sim_time_s,x")]),
                               data=[stamp, 0.])
    for stamp in (1.9, 2., 2.02):
        RosRobotInterface._drive_diagnostic_callback(ros, message(stamp))
    assert [r["sim_time_s"] for r in ros._drive_diagnostics] == [2.02]


def test_encoder_contract_is_checked_after_activation_not_on_discovery_backlog():
    ros = SimpleNamespace(_lock=Lock(), _state=RobotState(),
        _assisted_odometry=ImuEncoderOdometry({}), _assisted_epoch_active=False,
        _assisted_error=None, _mark_received=lambda name: None)
    msg = SimpleNamespace(name=["left_wheel_joint", "right_wheel_joint"], velocity=[0., 0.],
        position=[], header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)))
    RosRobotInterface._joint_callback(ros, msg)
    assert ros._assisted_error is None
    ros._assisted_epoch_active=True
    RosRobotInterface._joint_callback(ros, msg)
    assert ros._assisted_error == "Joint feedback lacks encoder positions"


def test_delayed_feedback_is_received_without_advancing_physics_or_reusing_other_intervals():
    ros = transport()
    ros._drive_diagnostics.extend([dict(sim_time_s=.99), dict(sim_time_s=1.2)])
    def deliver():
        sleep(.015)
        with ros._lock:
            ros._drive_diagnostics.append(dict(sim_time_s=1.08, executed_linear_m_s=.4))
    thread = Thread(target=deliver)
    thread.start()
    try:
        result = RosRobotInterface.wait_for_drive_diagnostics(ros, 1., 1.1, timeout=.2)
    finally:
        thread.join()
    assert result == [dict(sim_time_s=1.08, executed_linear_m_s=.4)]
    result[0]["executed_linear_m_s"] = 99.
    assert ros._drive_diagnostics[-1]["executed_linear_m_s"] == .4


@pytest.mark.parametrize("stamps", [[], [.99], [1.11], [1.01]])
def test_missing_previous_future_and_stale_feedback_remain_failures(stamps):
    ros = transport()
    ros._drive_diagnostics.extend(dict(sim_time_s=t) for t in stamps)
    with pytest.raises(TimeoutError, match="Drive feedback unavailable"):
        RosRobotInterface.wait_for_drive_diagnostics(ros, 1., 1.1, timeout=.005, max_latest_lag=.04)


def test_trace_failure_keeps_control_sample_and_observed_failed_terminal_outcome(tmp_path):
    def unavailable(*args, **kwargs):
        raise TimeoutError("missing feedback")
    streams = [StringIO(), StringIO()]
    info = dict(control_trace=dict(sim_time_s=1.1, governor_fault="stale_drive_feedback"),
                episode_metrics=dict(success=False, termination="governor_failsafe"))
    with pytest.raises(TimeoutError):
        append_action_traces(SimpleNamespace(wait_for_drive_diagnostics=unavailable),
            info, 1., 1.1, 77200, streams, [None, None], tmp_path, .01)
    controls = list(csv.DictReader(StringIO(streams[0].getvalue())))
    assert len(controls) == 1 and controls[0]["governor_fault"] == "stale_drive_feedback"
    context = json.loads((tmp_path/"trace_failure_context.json").read_text())
    assert context["native_terminal_outcome"]["success"] is False
    assert not streams[1].getvalue()  # No invented drive sample or zero impact.


def test_trace_barrier_preserves_real_stamps_and_values(tmp_path):
    ros = transport()
    ros._drive_diagnostics.append(dict(sim_time_s=1.08, executed_linear_m_s=.4))
    ros.wait_for_drive_diagnostics = lambda *args, **kw: RosRobotInterface.wait_for_drive_diagnostics(ros, *args, **kw)
    streams = [StringIO(), StringIO()]
    append_action_traces(ros, dict(control_trace=dict(sim_time_s=1.1)), 1., 1.1, 77200,
                         streams, [None, None], tmp_path, .01)
    row = list(csv.DictReader(StringIO(streams[1].getvalue())))[0]
    assert float(row["sim_time_s"]) == 1.08 and float(row["executed_linear_m_s"]) == .4
    assert not (tmp_path/"trace_failure_context.json").exists()
