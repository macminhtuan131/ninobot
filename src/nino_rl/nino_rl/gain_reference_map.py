"""One simulated reference calibration map, not actuator/current/traction gain."""
import math
from nino_control.kinematics import wheel_angular_targets

CONTEXT_ID='nino_sim_common_gain_context_v1_2026_11_06'
SUPPORTED_GAINS=(.98,1.,1.02)


def diagnostic_support(gain_stamp_s,drive_stamp_s,target_s):
    """Compare ROS-source nanoseconds, avoiding float subtraction at boundaries."""
    if not all(math.isfinite(v) for v in (gain_stamp_s,drive_stamp_s,target_s)):return False
    gain_ns,drive_ns,target_ns=(round(v*1e9) for v in (gain_stamp_s,drive_stamp_s,target_s))
    return gain_ns==drive_ns and 0<=target_ns-gain_ns<=40_000_000


def require_gain(gain):
    if type(gain) not in (int,float) or not math.isfinite(gain) or gain not in SUPPORTED_GAINS:
        raise ValueError('Only declared fixed common gains .98/1/1.02 are supported')
    return float(gain)


def target_map(linear,angular,radius,separation,gain):
    """Map common once before unchanged wheel speed/ramp/PI/torque limits.

    The effective request is not a measurement. Differential/yaw is unchanged
    before independent wheel limits, which may alter both and must be reported.
    """
    gain=require_gain(gain)
    if not all(math.isfinite(v) for v in (linear,angular,radius,separation)) or min(radius,separation)<=0:
        raise ValueError('Finite reference and positive nominal geometry required')
    targets=wheel_angular_targets(gain*linear,angular,radius,separation)
    return targets,dict(map_active=True,common_gain=gain,
        reference_linear_m_s=float(linear),reference_yaw_rad_s=float(angular),
        effective_linear_m_s=float(gain*linear),effective_yaw_rad_s=float(angular),
        left_unlimited_target_rad_s=targets[0],right_unlimited_target_rad_s=targets[1])


def map_audit(record, *, stamp_s, targets, max_speed, calls):
    """Post-limit targets remain genuine driver state, never fabricated GT."""
    r=dict(record) if record is not None else dict(map_active=False,common_gain=0.,
        reference_linear_m_s=0.,reference_yaw_rad_s=0.,effective_linear_m_s=0.,effective_yaw_rad_s=0.,
        left_unlimited_target_rad_s=0.,right_unlimited_target_rad_s=0.)
    r.update(sim_time_s=stamp_s,left_target_rad_s=targets[0],right_target_rad_s=targets[1],
        map_calls_this_update=calls,post_limit_targets_valid=record is not None)
    r['speed_clip_required']=bool(record is not None and max(abs(record[k]) for k in
        ('left_unlimited_target_rad_s','right_unlimited_target_rad_s'))>max_speed)
    clipped=[max(-max_speed,min(max_speed,r[k])) for k in
        ('left_unlimited_target_rad_s','right_unlimited_target_rad_s')]
    r['target_ramp_active']=bool(record is not None and any(abs(a-b)>1e-10 for a,b in zip(targets,clipped)))
    return r
