"""Versioned native metrics for v2 development evaluation, not damage/energy claims."""
import math
import numpy as np

METRIC_ID = 'common103_v2_native_metrics_v2'


def physical_metrics(rows, stop_s, config):
    if not rows:
        raise ValueError('Cannot extract physical metrics from empty episode trace')
    dt = float(config['control_interval_s'])
    times = np.asarray([r['task']['elapsed_s'] for r in rows], dtype=float)
    if not math.isfinite(dt) or dt <= 0 or not np.all(np.isfinite(times)):
        raise ValueError('Finite positive native clock required')
    if len(times) > 1 and not np.allclose(np.diff(times), dt, atol=1e-8, rtol=0):
        raise ValueError('Native metric clock has gaps or reversed timestamps')

    def rms(values):
        values = np.asarray(values, dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError('Nonfinite physical metric input')
        return float(np.sqrt(np.mean(values ** 2)))

    accepted = np.asarray([r['reference_trace']['body_reference'][0] for r in rows], dtype=float)
    if not np.all(np.isfinite(accepted)):
        raise ValueError('Nonfinite accepted reference')
    body = np.asarray([r['body_speed_m_s'] for r in rows], dtype=float)
    nominal = np.asarray([r['task']['nominal_shaped_body'][0] for r in rows], dtype=float)
    if not np.all(np.isfinite(body)) or not np.all(np.isfinite(nominal)):
        raise ValueError('Nonfinite body/nominal speed')
    # Derivatives on observed native intervals only; do not invent a sample before the first row.
    acceleration = np.diff(accepted) / dt
    jerk = np.diff(acceleration) / dt
    if len(jerk) == 0:
        raise ValueError('At least 3 samples needed for reference jerk')
    geometry = config['nominal_geometry']
    wheel_cap = float(config['reference_limits']['wheel_speed_m_s'])
    if not math.isfinite(wheel_cap) or wheel_cap <= 0:
        raise ValueError('Invalid wheel speed cap')
    saturated = []
    for row in rows:
        # Missing telemetry is an error, never an unsaturated zero target.
        target = np.asarray(row['applied_target_rad_s'], dtype=float)
        if target.shape != (2,) or not np.all(np.isfinite(target)):
            raise ValueError('Finite left/right actuator targets required')
        speed = target * [geometry['radius_l'], geometry['radius_r']]
        saturated.append(bool(np.any(np.abs(speed) >= wheel_cap - 1e-8)))

    onset = None
    quiet_start = None
    quiet_samples = 0
    for t, row in zip(times, rows):
        if t < stop_s - 1e-8:
            continue
        if row['task']['quiet_now']:
            if quiet_start is None:
                quiet_start = t - dt
            quiet_samples += 1
            if quiet_samples * dt >= 2.0 - 1e-8:
                onset = max(0.0, float(quiet_start - stop_s))
                break
        else:
            quiet_start, quiet_samples = None, 0
    if onset is None:
        raise ValueError('No observed sustained stop; settling time is unknown')
    failed = (not rows[-1]['task']['task_success'] or not rows[-1]['task']['stop_completed'])
    intervention = any(r.get('intervention') or r.get('guidance_audit', {}).get('fault')
                       or abs(r['task']['cross_track_m']) > 0.04 for r in rows)
    return dict(
        rms_v_m_s=rms([r['task']['velocity_error_m_s'] for r in rows]),
        rms_omega_rad_s=rms([r['task']['yaw_rate_error_rad_s'] for r in rows]),
        cross_track_rmse_m=rms([r['task']['cross_track_m'] for r in rows]),
        max_overshoot_m_s=float(np.max(np.maximum(0., body - nominal))),
        settling_time_s=onset,
        action_jerk_rms=rms(jerk),  # Accepted-reference jerk, m/s^3; not measured body jerk.
        reference_acceleration_rms_m_s2=rms(acceleration),
        saturation_fraction=float(np.mean(saturated)),
        safety_intervention_rate=float(bool(failed or intervention)),  # Episode incidence, never diluted by ticks.
    )
