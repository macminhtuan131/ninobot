"""One speed target above PI; hardware actor inputs, physical training reward."""
import numpy as np


def decode_speed(action, config):
    value=np.asarray(action,dtype=float)
    if value.shape!=(1,) or not np.isfinite(value).all():
        raise ValueError('Longitudinal policy requires one finite action')
    floor=float(config['longitudinal_control']['minimum_scale'])
    if not 0<floor<1:raise ValueError('Invalid speed floor')
    return floor+(1-floor)*(float(np.clip(value[0],-1,1))+1)/2


def encode_speed(scale, config):
    floor=float(config['longitudinal_control']['minimum_scale'])
    if not floor<=scale<=1:raise ValueError('Baseline scale is outside the declared speed range')
    return 2*(scale-floor)/(1-floor)-1


def ramp_speed(previous,target,dt,rate):
    if not np.isfinite([previous,target,dt,rate]).all() or min(dt,rate)<=0:
        raise ValueError('Invalid reference ramp')
    return float(previous+np.clip(target-previous,-rate*dt,rate*dt))


def velocity_reference(linear,angular,scale):
    """Only translation changes. PI yaw and a zero translation stay intact."""
    if not np.isfinite([linear,angular,scale]).all() or not 0<=scale<=1:
        raise ValueError('Invalid longitudinal reference')
    return float(linear*scale),float(angular)


def compute_reward(previous,current,state,action,previous_action,torque,dt,imu,cfg,
                   *,succeeded=False,failed=None,timed_out=False,reference=None,**ignored):
    from nino_rl.core import wheel_slip_ratios
    if not np.isfinite(dt) or dt<=0:raise ValueError('Invalid reward interval')
    w=cfg['longitudinal_weights']
    slip=np.asarray(wheel_slip_ratios(state),dtype=float)
    desired=reference.desired_linear_velocity if reference is not None and reference.valid else 0.
    # cfg's reference is the route PI request BEFORE the action modifies it.
    # Energy integrates measured vertical acceleration squared, matching RMS.
    delta=previous.distance_remaining-current.distance_remaining
    difference=float(np.asarray(action)[0]-np.asarray(previous_action)[0])
    terms=dict(progress=w['progress_per_m']*delta,
        time=-dt*w['time_per_s'],
        command_velocity=-dt*w['velocity']*((state.ground_linear_velocity-desired)/w['velocity_sigma_m_s'])**2,
        vibration=-w['vibration']*imu['square_integral']/w['acceleration_sigma_m_s2']**2,
        slip=-dt*w['slip']*float(np.mean((slip/w['slip_sigma'])**2)),
        lateral=-dt*w['lateral']*(current.lateral_error/w['lateral_sigma_m'])**2,
        heading=-dt*w['heading']*(current.heading_error/w['heading_sigma_rad'])**2,
        action_rate=-w['action_rate']*difference**2/dt,
        terminal=-w['failure'] if failed or timed_out else w['arrival'] if succeeded else 0.)
    if not all(np.isfinite(v) for v in terms.values()):raise ValueError('Non-finite longitudinal reward')
    return float(sum(terms.values())),terms
