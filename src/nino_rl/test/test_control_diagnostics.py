"""Diagnostic provenance checks, without starting ROS or a simulator."""
from collections import deque
from copy import deepcopy
from threading import Lock
from types import SimpleNamespace

import pytest

from nino_rl.evaluation import benchmark_id, compare_summaries
from nino_rl.ros_interface import RosRobotInterface


def test_controller_diagnostics_reject_invalid_samples_and_bound_the_window():
    interface = SimpleNamespace(_lock=Lock(), _drive_diagnostics=deque(maxlen=3))
    for stamp in (1., 1.1, 1.2):
        message = SimpleNamespace(
            layout=SimpleNamespace(dim=[SimpleNamespace(label="sim_time_s,executed_yaw_rad_s")]),
            data=[stamp, .05])
        RosRobotInterface._drive_diagnostic_callback(interface, message)
    invalid = deepcopy(message)
    invalid.data[1] = float("nan")
    RosRobotInterface._drive_diagnostic_callback(interface, invalid)
    assert len(interface._drive_diagnostics) == 3
    rows = RosRobotInterface.drive_diagnostics(interface, 1., 1.1)
    assert rows == [{"sim_time_s": 1.1, "executed_yaw_rad_s": .05}]
    rows[0]["executed_yaw_rad_s"] = 999
    assert interface._drive_diagnostics[1]["executed_yaw_rad_s"] == .05


def test_trace_logging_does_not_change_the_benchmark_or_allow_different_seeds():
    assert benchmark_id({"task": "flat"}) == benchmark_id(
        {"task": "flat", "evaluation_control_trace": True})
    report = dict(complete=True, schema_version=1, benchmark_id="same", phase=1,
                  seed=61005, episodes=2, randomized=False, pose_source="wheel_odometry",
                  evaluation_seeds=[61005, 61019])
    different = {**report, "evaluation_seeds": [61005, 61020]}
    with pytest.raises(ValueError, match="evaluation_seeds"):
        compare_summaries(report, different)
