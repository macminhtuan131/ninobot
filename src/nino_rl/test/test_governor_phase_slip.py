"""Offline metrics must conserve phase energy and expose missing sensor coverage."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_governor_phase_slip import integrate, interpolate, slip_square


def test_phase_boundaries_conserve_integral_and_distance():
    signal = dict(time=np.array([0., .02, .04]), q=np.array([1., 9., 1.]),
                  xy=np.array([[0., 0.], [.01, 0.], [.02, 0.]]))
    whole = integrate(signal, 0., .04)
    phases = [integrate(signal, 0., .013), integrate(signal, .013, .031), integrate(signal, .031, .04)]
    assert all(p["available"] for p in phases)
    assert np.isclose(sum(p["slip_square_integral_s"] for p in phases), whole["slip_square_integral_s"])
    assert np.isclose(sum(p["distance_m"] for p in phases), whole["distance_m"])
    assert np.isclose(whole["slip_square_integral_s"], .2)


def test_missing_or_long_gaps_are_not_interpolated_as_zero_slip():
    rows = np.array([[0., 1.], [.02, 2.], [.2, 8.], [.22, 9.]])
    result = interpolate(rows, np.array([-.01, .01, .02, .10, .20, .23]))[:, 0]
    assert np.isnan(result[[0, 3, 5]]).all()
    assert np.allclose(result[[1, 2, 4]], [1.5, 2., 8.])
    signal = dict(time=rows[:, 0], q=rows[:, 1], xy=np.column_stack([rows[:, 0], rows[:, 0]*0]))
    metric = integrate(signal, 0., .22)
    assert not metric["available"]
    assert metric["rms"] is None
    assert metric["slip_square_integral_s"] is None
    assert np.isclose(metric["coverage_s"], .04)


def test_slip_matches_project_formula_for_turning_and_low_speed():
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from nino_rl.core import wheel_slip_ratios
    states = [SimpleNamespace(left_wheel_velocity=4., right_wheel_velocity=7.,
                              ground_linear_velocity=.3, ground_yaw_rate=.7),
              SimpleNamespace(left_wheel_velocity=-.1, right_wheel_velocity=.2,
                              ground_linear_velocity=.001, ground_yaw_rate=-.03)]
    for s in states:
        q = slip_square(np.array([[s.left_wheel_velocity, s.right_wheel_velocity]]),
                        np.array([[s.ground_linear_velocity, s.ground_yaw_rate]]))[0]
        assert np.isclose(q, np.mean(np.square(wheel_slip_ratios(s))))


def test_empty_window_is_unavailable_and_never_perfect():
    signal = dict(time=np.array([0., .02]), q=np.array([0., 0.]), xy=np.zeros((2, 2)))
    result = integrate(signal, 1., 2.)
    assert result["coverage_s"] == 0.
    assert result["rms"] is None
    assert result["observed_slip_square_integral_s"] is None
