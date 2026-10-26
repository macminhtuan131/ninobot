"""New explicit time/comfort tradeoff; cruise tracking resumes after a bounded cue."""
from copy import deepcopy
from nino_rl.longitudinal_control import compute_reward as base_reward


def compute_reward(previous,current,state,action,previous_action,torque,dt,imu,cfg,
                   *,reactive_holding=False,elapsed=0.,executed_scale=1.,previous_executed_scale=1.,**kwargs):
    effective=deepcopy(cfg)
    if reactive_holding:effective['longitudinal_weights']['velocity']=0.
    _,terms=base_reward(previous,current,state,action,previous_action,torque,dt,imu,effective,**kwargs)
    w=cfg['longitudinal_weights']
    # Penalize the reference actually executed after the fixed ramp, not
    # Gaussian target jumps which the motors never receive directly.
    terms['action_rate']=-w['action_rate']*(executed_scale-previous_executed_scale)**2/dt
    late=max(0.,elapsed-max(elapsed-dt,w['late_after_s']))
    terms['late_time']=-w['late_time_per_s']*late
    return float(sum(terms.values())),terms
