"""Slip telemetry and offline accounting. Never changes control, reward or native metrics."""
from math import isfinite, isclose, sqrt

import numpy as np

RADIUS = .0625
TRACK = .34273666
MAX_GAP = .040001

SLIP_REPORTING_PROTOCOL = {
    "schema": "synchronized_slip_offline_v1",
    "period_s": .02,
    "origin": "first control input simulation timestamp of each episode",
    "timestamp_source": "sensor header simulation stamps, never receipt/wall time",
    "duplicate_stamps": "keep last row",
    "alignment": "linear sensor interpolation, then calculate slip; offline/noncausal",
    "max_ground_gap_s": MAX_GAP,
    "max_joint_gap_s": .010001,
    "minimum_coverage_fraction": .98,
    "denominator_floor_m_s": .10,
    "ratio_clip": [-5., 5.],
    "wheel_radius_m": RADIUS,
    "wheel_separation_m": TRACK,
    "quadrature": "trapezoid of mean left/right squared ratios, clipped at window boundaries",
    "rms": "sqrt(integral / covered_seconds)",
    "integral_unit": "s",
    "integral_per_distance_unit": "s/m",
    "distance": "GT xy distance on the same valid segments as slip",
    "minimum_distance_m": .01,
    "missing": "unavailable/null, never zero or success-only filtering",
    "native": "unchanged control-step arithmetic mean of squared ratios; separate namespace",
}


def interpolate(rows, times, max_gap=MAX_GAP):
    """Linear sensor interpolation, without extrapolation or long gap bridging."""
    rows = np.asarray(rows, dtype=float)
    times = np.asarray(times, dtype=float)
    if len(rows) < 2:
        return np.full((len(times), rows.shape[1]-1 if rows.ndim == 2 else 1), np.nan)
    if not np.all(np.isfinite(rows[:, 0])) or np.any(np.diff(rows[:, 0]) <= 0):
        raise ValueError("Sensor stamps must be finite, sorted and deduplicated")
    right = np.searchsorted(rows[:, 0], times, side="left")
    upper = np.clip(right, 1, len(rows)-1)
    lower = upper-1
    result = np.column_stack([np.interp(times, rows[:, 0], rows[:, i])
                              for i in range(1, rows.shape[1])])
    exact = np.isclose(rows[np.minimum(right, len(rows)-1), 0], times, atol=1e-8, rtol=0.)
    valid = ((times >= rows[0, 0]-1e-8) & (times <= rows[-1, 0]+1e-8)
             & ((rows[upper, 0]-rows[lower, 0] <= max_gap) | exact))
    result[~valid] = np.nan
    return result


def interpolation_stamps(rows, times):
    """Expose both support stamps; the later sample is allowed only offline."""
    rows = np.asarray(rows, dtype=float)
    if len(rows) < 2:
        return np.full((len(times), 2), np.nan)
    right = np.minimum(np.searchsorted(rows[:, 0], times, side="left"), len(rows)-1)
    exact = np.isclose(rows[right, 0], times, atol=1e-8, rtol=0.)
    left = np.where(exact, right, np.maximum(right-1, 0))
    support = np.column_stack([rows[left, 0], rows[right, 0]])
    support[(times < rows[0, 0]-1e-8) | (times > rows[-1, 0]+1e-8)] = np.nan
    return support


def slip_square(wheels, ground):
    """core.wheel_slip_ratios convention, evaluated on already aligned sensors."""
    wheel = RADIUS*wheels
    body = ground[:, 0, None]+ground[:, 1, None]*np.array([-TRACK/2, TRACK/2])
    ratio = np.clip((wheel-body)/np.maximum(np.maximum(abs(wheel), abs(body)), .1), -5., 5.)
    return np.mean(ratio**2, axis=1)


def synchronized_series(data, period=.02, offset=0.):
    ground_rows = np.asarray(data["ground"], dtype=float).reshape(-1, 5)
    joint_rows = np.asarray(data["joints"], dtype=float).reshape(-1, 3)
    if not isfinite(period) or period <= 0 or not isfinite(offset) or offset < 0:
        raise ValueError("Period must be positive and offset non-negative")
    count = max(0, int(np.floor((data["end"]-data["start"]-offset)/period))+1)
    times = data["start"]+offset+np.arange(count)*period
    ground = interpolate(ground_rows, times)
    wheels = interpolate(joint_rows, times, .010001)
    return dict(time=times, q=slip_square(wheels, ground), xy=ground[:, 2:4],
                ground_support_stamps=interpolation_stamps(ground_rows, times),
                joint_support_stamps=interpolation_stamps(joint_rows, times))


def integrate(signal, start, end):
    """Same integration/sampling for every window; phase sums conserve the total."""
    t, q, xy = signal["time"], signal["q"], signal["xy"]
    integral = covered = distance = 0.
    for i in range(len(t)-1):
        a, b = max(start, t[i]), min(end, t[i+1])
        if b <= a or t[i+1]-t[i] > MAX_GAP or not np.isfinite([q[i], q[i+1], *xy[i], *xy[i+1]]).all():
            continue
        dt = t[i+1]-t[i]
        fa, fb = (a-t[i])/dt, (b-t[i])/dt
        qa, qb = q[i]+fa*(q[i+1]-q[i]), q[i]+fb*(q[i+1]-q[i])
        integral += (qa+qb)*.5*(b-a)
        covered += b-a
        distance += float(np.linalg.norm(xy[i+1]-xy[i]))*(fb-fa)
    duration = end-start
    available = duration > 0 and covered >= .98*duration
    return dict(available=bool(available), start_s=float(start), end_s=float(end),
                duration_s=float(duration), coverage_s=float(covered),
                coverage_fraction=float(covered/duration) if duration > 0 else None,
                observed_slip_square_integral_s=float(integral) if covered else None,
                slip_square_integral_s=float(integral) if available else None,
                rms=float(np.sqrt(integral/covered)) if available else None,
                distance_m=float(distance) if available else None,
                slip_square_per_m=float(integral/distance) if available and distance > .01 else None)


def synchronized_windows(data, windows, *, offset=0.):
    """One signal for route and crossing, never independently resampled per window."""
    signal = synchronized_series(data, offset=offset)
    output = {}
    for name, bounds in windows.items():
        if bounds is None:
            output[name] = {"available": False, "reason": "window_boundaries_unavailable",
                            **{k: None for k in ("start_s", "end_s", "duration_s", "coverage_s",
                                "coverage_fraction", "observed_slip_square_integral_s",
                                "slip_square_integral_s", "rms", "distance_m", "slip_square_per_m")}}
        else:
            output[name] = integrate(signal, *bounds)
    return signal, output


def native_slip_trace(state, endpoint_s, left, right, step_count, square_sum):
    """Record the exact existing snapshot/accumulator, without synchronizing native."""
    def finite(value):
        return float(value) if isfinite(value) else None
    joint, ground = finite(state.joint_stamp_s), finite(state.ground_truth_stamp_s)
    return {
        "slip_trace_schema": "native_slip_snapshot_v1",
        "slip_joint_stamp_s": joint, "slip_ground_truth_stamp_s": ground,
        "slip_joint_age_s": endpoint_s-joint if joint is not None else None,
        "slip_ground_truth_age_s": endpoint_s-ground if ground is not None else None,
        "slip_joint_minus_ground_stamp_s": joint-ground if joint is not None and ground is not None else None,
        "slip_left_wheel_rad_s": finite(state.left_wheel_velocity),
        "slip_right_wheel_rad_s": finite(state.right_wheel_velocity),
        "slip_ground_linear_m_s": finite(state.ground_linear_velocity),
        "slip_ground_yaw_rad_s": finite(state.ground_yaw_rate),
        "slip_native_left_ratio": finite(left), "slip_native_right_ratio": finite(right),
        "slip_native_mean_square": finite(.5*(left**2+right**2)),
        "slip_native_square_sum": finite(square_sum), "slip_native_step_count": step_count,
    }


def replay_native_trace(rows):
    """Reproduce native from telemetry, explicitly unavailable for legacy traces."""
    fields = ["slip_trace_schema", "slip_native_step_count", "slip_native_mean_square",
              "slip_native_square_sum", "slip_native_left_ratio", "slip_native_right_ratio",
              "slip_left_wheel_rad_s", "slip_right_wheel_rad_s", "slip_ground_linear_m_s",
              "slip_ground_yaw_rad_s"]
    unavailable = dict(available=False, rms=None)
    if not rows or any(any(row.get(k) in (None, "") for k in fields) for row in rows):
        return {**unavailable, "reason": "missing_snapshot_fields; cannot infer legacy sensor stamps"}
    total = 0.
    for i, row in enumerate(rows, 1):
        try:
            step = float(row["slip_native_step_count"])
            numbers = [float(row[k]) for k in fields[2:]]
        except (TypeError, ValueError):
            return {**unavailable, "reason": "invalid_snapshot_values"}
        if row["slip_trace_schema"] != "native_slip_snapshot_v1" or step != i:
            return {**unavailable, "reason": "unknown_schema_or_noncontiguous_native_steps"}
        if not all(isfinite(v) for v in numbers):
            return {**unavailable, "reason": "nonfinite_snapshot_values"}
        expected = slip_square(np.array([[float(row["slip_left_wheel_rad_s"]), float(row["slip_right_wheel_rad_s"])]]),
                               np.array([[float(row["slip_ground_linear_m_s"]), float(row["slip_ground_yaw_rad_s"])]]))[0]
        q = float(row["slip_native_mean_square"])
        ratios_q = .5*(float(row["slip_native_left_ratio"])**2+float(row["slip_native_right_ratio"])**2)
        total += q
        if not (isclose(q, expected, abs_tol=1e-10, rel_tol=1e-10)
                and isclose(q, ratios_q, abs_tol=1e-10, rel_tol=1e-10)
                and isclose(total, float(row["slip_native_square_sum"]), abs_tol=1e-10, rel_tol=1e-10)):
            return {**unavailable, "reason": "native_accumulator_or_snapshot_mismatch"}
    return dict(available=True, reason=None, steps=len(rows), square_sum=total, rms=sqrt(total/len(rows)))
