"""Prospective IMU-point motion-quality metric; offline, no controller authority.

Requires a verified body-aligned sensor and +g-at-rest specific-force convention.
GT roll/pitch may support Sim scoring; they are not deployable controller inputs.
"""
import math
import numpy as np
from .causal_source_support import SourceSeries, ns

METRIC_ID = 'nino_imu_point_vertical_rms_v1'


def vertical_rms(force_z, attitude, start_s, end_s, *, gravity_m_s2,
                 convention_verified, mount_body_aligned, maximum_age_s=.04):
    """Integrate causal ZOH on the source-event union, clipping exact boundaries.

    force_z samples are (source_s, fz); attitude samples are (source_s, [roll,pitch]).
    Expiry events split unsupported durations explicitly; no extrapolation or
    missing-as-zero. This is sensor-point vertical acceleration, not CoM/force.
    """
    if convention_verified is not True or mount_body_aligned is not True:
        raise ValueError('Specific-force convention and sensor mounting must be verified')
    if (not all(math.isfinite(v) for v in (start_s,end_s,gravity_m_s2,maximum_age_s))
            or start_s >= end_s or gravity_m_s2 <= 0 or maximum_age_s <= 0):
        raise ValueError('Finite ordered window, positive gravity/age required')
    f, a = SourceSeries(force_z), SourceSeries(attitude)
    if f.groups[0]['payloads'][0].shape != (1,) or a.groups[0]['payloads'][0].shape != (2,):
        raise ValueError('Require scalar fz and roll/pitch pair in radians')
    start, end, age = ns(start_s), ns(end_s), ns(maximum_age_s)
    edges = {start,end}
    for series in (f,a):
        for stamp in series.times_ns:
            for boundary in (int(stamp),int(stamp)+age):
                if start < boundary < end: edges.add(boundary)
    edges = sorted(edges); integral = covered = 0.; ledger = []
    for lo,hi in zip(edges,edges[1:]):
        # No source event lies inside this interval. Midpoint support checks
        # avoid treating an exact expiry timestamp as support for later time.
        mid = (lo+hi)/2e9
        fq, aq = f.query([mid], maximum_age_s), a.query([mid], maximum_age_s)
        supported = bool(fq.supported[0] and aq.supported[0])
        width = (hi-lo)/1e9
        acceleration = None
        if supported:
            roll,pitch = aq.values[0]
            acceleration = fq.values[0].item()-gravity_m_s2*math.cos(roll)*math.cos(pitch)
            integral += acceleration**2*width; covered += width
        ledger.append(dict(start_s=lo/1e9,end_s=hi/1e9,supported=supported,
                           force_source_ns=fq.source_ns[0],attitude_source_ns=aq.source_ns[0],
                           force_reason=fq.reasons[0],attitude_reason=aq.reasons[0],
                           vertical_acceleration_m_s2=acceleration))
    duration = (end-start)/1e9
    return dict(metric_id=METRIC_ID,integral_m2_s3=integral,
                rms_m_s2=math.sqrt(integral/covered) if covered else None,
                supported_duration_s=covered,window_duration_s=duration,
                coverage_fraction=covered/duration,coverage_pass=covered/duration >= .98-1e-12,
                force_conflict_groups=len(f.conflicts),attitude_conflict_groups=len(a.conflicts),
                semantics='causal_source_event_ZOH_at_IMU_point_not_force_damage_or_CoM',segments=ledger)
