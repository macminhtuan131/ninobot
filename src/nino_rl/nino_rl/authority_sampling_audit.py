"""Offline attribution only; never replaces the frozen E2 primary estimator."""
import numpy as np


def contributions(times, errors, weights, edges):
    """Split each observed rectangle across boundaries without smoothing spikes.

    Error is held constant only for attribution of that estimator's own weight.
    Missing errors are not accepted as zeros. Edges must cover all rectangles.
    """
    t, e, w, b = map(lambda x: np.asarray(x, dtype=float), (times, errors, weights, edges))
    if (t.ndim != 1 or e.shape != t.shape or w.shape != t.shape or b.ndim != 1
            or len(b) < 2 or not all(np.all(np.isfinite(x)) for x in (t, e, w, b))
            or np.any(w <= 0) or np.any(np.diff(t) <= 0) or np.any(np.diff(b) <= 0)
            or (len(t) and (t[0] < b[0]-1e-9 or np.max(t+w) > b[-1]+1e-9))):
        raise ValueError('Finite ordered samples and covering edges required')
    result = []
    for lo, hi in zip(b[:-1], b[1:]):
        widths = np.maximum(0., np.minimum(t+w, hi)-np.maximum(t, lo))
        result.append(dict(start_s=float(lo), end_s=float(hi),
                           observed_weight_s=float(widths.sum()),
                           ise_m2_s=float(np.sum(e**2*widths))))
    return result


def native_equation(rows, truth):
    """Replay task error and identify its actual source stamp, not receipt time."""
    failures, details = [], []
    max_error = max_body = max_nominal = 0.
    for r in rows:
        stamp = r['sensor_clock_s']-r['source_lags_s']['truth']
        query = truth.query([stamp], .000000002)
        supported = bool(query.supported[0])
        nominal = r['task']['nominal_shaped_body'][0]
        delta = r['task']['velocity_error_m_s']-(r['body_speed_m_s']-nominal)
        body_delta = query.values[0].item()-r['body_speed_m_s'] if supported else None
        nominal_delta = nominal-r['oracle_decision']['nominal_shaped_body'][0]
        max_error = max(max_error, abs(delta))
        max_nominal = max(max_nominal, abs(nominal_delta))
        if supported:
            max_body = max(max_body, abs(body_delta))
        if not supported or abs(delta)>1e-12 or abs(nominal_delta)>1e-10 or abs(body_delta or 0)>1e-12:
            failures.append(r['step'])
        details.append(dict(step=r['step'], sensor_clock_s=r['sensor_clock_s'],
                            truth_source_s=stamp, source_age_s=r['source_lags_s']['truth'],
                            source_supported=supported, body_delta_m_s=body_delta,
                            equation_delta_m_s=delta, nominal_delta_m_s=nominal_delta))
    return dict(rows=len(rows), failed_steps=failures, pass_equation_and_source=not failures,
                max_equation_delta_m_s=max_error, max_source_body_delta_m_s=max_body,
                max_oracle_task_nominal_delta_m_s=max_nominal, details=details)
