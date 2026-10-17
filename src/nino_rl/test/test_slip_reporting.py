"""No ROS/simulation: telemetry replay and the shared window-reporting contract."""
import csv
from dataclasses import asdict
from io import StringIO
import json

import numpy as np

from nino_rl.core import RobotState, wheel_slip_ratios
from nino_rl.slip_reporting import native_slip_trace, replay_native_trace, synchronized_windows


def snapshot_rows():
    total, rows = 0., []
    for index, velocity in enumerate([.1, .2, .05], 1):
        state = RobotState(joint_stamp_s=index*.1-.002, ground_truth_stamp_s=index*.1-.02,
                           left_wheel_velocity=velocity/.0625, right_wheel_velocity=(velocity+.02)/.0625,
                           ground_linear_velocity=.15, ground_yaw_rate=.02)
        before = asdict(state)
        left, right = wheel_slip_ratios(state)
        total += .5*(left**2+right**2)
        row = native_slip_trace(state, index*.1, left, right, index, total)
        assert asdict(state) == before
        rows.append(row)
    return rows, np.sqrt(total/len(rows))


def test_csv_snapshot_replays_native_without_changing_its_accumulator():
    rows, expected = snapshot_rows()
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows); stream.seek(0)
    replay = replay_native_trace(list(csv.DictReader(stream)))
    assert replay["available"]
    assert replay["steps"] == 3
    assert replay["rms"] == expected
    assert np.isclose(rows[0]["slip_joint_minus_ground_stamp_s"], .018)


def test_signed_ages_expose_future_and_missing_stamps_without_mutating_native():
    state = RobotState(joint_stamp_s=1.01, ground_truth_stamp_s=.98)
    future = native_slip_trace(state, 1., .1, .2, 1, .025)
    assert future["slip_joint_age_s"] < 0
    assert np.isclose(future["slip_ground_truth_age_s"], .02)
    assert future["slip_native_square_sum"] == .025
    state.joint_stamp_s = -float("inf")
    missing = native_slip_trace(state, 1., .1, .2, 1, .025)
    assert missing["slip_joint_stamp_s"] is None
    assert missing["slip_joint_minus_ground_stamp_s"] is None
    json.dumps(missing, allow_nan=False)


def test_legacy_missing_steps_and_corrupt_snapshots_are_not_fabricated():
    assert not replay_native_trace([{"physical_speed_m_s": ".4"}])["available"]
    rows, _ = snapshot_rows()
    assert not replay_native_trace(rows[1:])["available"]
    rows[1]["slip_native_square_sum"] += .1
    assert not replay_native_trace(rows)["available"]
    rows[1]["slip_native_mean_square"] = "broken"
    assert not replay_native_trace(rows)["available"]


def test_same_signal_and_quadrature_for_whole_crossing_and_phases():
    times = np.arange(0., 1.0001, .02)
    data = dict(start=0., end=1., ground=np.column_stack([times, times*0+.4, times*0, times*.4, times*0]),
                joints=np.column_stack([times, (times*.1+.4)/.0625, (times*.1+.4)/.0625]))
    signal, windows = synchronized_windows(data, {"whole": (0., 1.), "a": (0., .311), "b": (.311, 1.)})
    assert np.allclose(signal["ground_support_stamps"][:, 0], times)
    assert np.allclose(signal["joint_support_stamps"][:, 1], times)
    assert np.isclose(windows["whole"]["slip_square_integral_s"],
                      windows["a"]["slip_square_integral_s"]+windows["b"]["slip_square_integral_s"])
    for w in windows.values():
        assert w["available"]
        assert np.isclose(w["rms"]**2*w["coverage_s"], w["slip_square_integral_s"])
        assert np.isclose(w["slip_square_per_m"]*w["distance_m"], w["slip_square_integral_s"])


def test_missing_ground_or_event_is_unavailable_instead_of_zero_slip():
    times = np.arange(0., 1.0001, .02)
    data = dict(start=0., end=1., ground=np.empty((0, 5)),
                joints=np.column_stack([times, times*0+6., times*0+6.]))
    _, windows = synchronized_windows(data, {"whole": (0., 1.), "crossing": None})
    assert not windows["whole"]["available"]
    assert windows["whole"]["rms"] is None
    assert not windows["crossing"]["available"]
    assert windows["crossing"]["slip_square_integral_s"] is None
