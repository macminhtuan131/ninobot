"""Offline candidate checks after V2 closure; NOT wired into any physics job.

Read drive acknowledgement separately from observer reception. These are
software preconditions for a future reset protocol, not safety certification.
No publishing, waiting, simulation steps, mutation or implicit permission.
"""
import math


class DecisionInputNotReady(ValueError):
    pass


def assess_zero_reset(drive, *, source_age_s, physically_quiet, maximum_age_s=.04):
    """Candidate conjunction within the existing five-second setup budget.

    Missing data are unknown/blocked. Callers must retain physical settling,
    diagnostics provenance and timeout; this does not create/renew support.
    """
    reasons=[]
    if physically_quiet is not True:reasons.append('physical_settling_not_confirmed')
    if not isinstance(drive,dict):return dict(ready=False,reasons=reasons+['drive_diagnostics_missing'])
    if (not isinstance(source_age_s,(int,float)) or isinstance(source_age_s,bool)
            or not math.isfinite(source_age_s) or not 0<=source_age_s<=maximum_age_s):
        reasons.append('drive_diagnostics_stale_future_or_unknown')
    have=drive.get('have_wheel_state')
    if not isinstance(have,(int,float)) or isinstance(have,bool) or have!=1.:
        reasons.append('drive_has_not_acknowledged_wheel_feedback')
    for key in ('executed_linear_m_s','executed_yaw_rad_s','left_target_rad_s','right_target_rad_s'):
        value=drive.get(key)
        if (not isinstance(value,(int,float)) or isinstance(value,bool)
                or not math.isfinite(value) or value!=0.):
            reasons.append('zero_not_acknowledged:'+key)
    return dict(ready=not reasons,reasons=reasons)


def require_uninhibited_transition(row):
    """Prepared fail-closed diagnostic BEFORE the unchanged success validator.

    Never replace a null proposal with zero or admit an intervention to replay.
    Does not fix readiness by itself and must not reopen a closed V2 job.
    """
    trace=row.get('reference_trace') or {}
    samples=trace.get('source_samples') or {}
    status=(samples.get('status') or {}).get('values') or {}
    if (status.get('permission') is not True or status.get('fault') is not False
            or status.get('emergency_stop') is not False or row.get('intervention',False) is not False):
        raise DecisionInputNotReady('Decision inhibited before replay: '+str(trace.get('reason','unknown')))
    if trace.get('proposal') is None:
        raise DecisionInputNotReady('Missing controller proposal; retain raw and close remaining slots')
    return row
