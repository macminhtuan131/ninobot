"""Categorical supervisory speed-rate actions; all low-level PI remains unchanged."""
import gymnasium as gym
import numpy as np
from stable_baselines3.common.policies import ActorCriticPolicy

LABELS=('BRAKE','HOLD','RECOVER')

def target(action,previous,config,dt):
    value=np.asarray(action)
    if value.size!=1 or not np.isfinite(value).all() or float(value.reshape(-1)[0])!=int(value.reshape(-1)[0]):
        raise ValueError('Rate action must be one categorical integer')
    selected=int(value.reshape(-1)[0])
    if selected not in range(3):raise ValueError('Invalid rate action')
    rate=float(config['longitudinal_control']['scale_rate_per_s'])
    floor=float(config['longitudinal_control']['minimum_scale'])
    return selected,float(np.clip(previous+(selected-1)*rate*dt,floor,1.))

class RateEnv(gym.Wrapper):
    """The internal history records the continuous command actually executed."""
    def __init__(self,env):
        super().__init__(env);self.action_space=gym.spaces.Discrete(3)

    def __getattr__(self,name):
        if name=='env':raise AttributeError(name)
        return getattr(self.env,name)

    def reset(self,**kwargs):
        self.env.selected_rate_action=1
        return self.env.reset(**kwargs)

    def step(self,action):
        from nino_rl.longitudinal_control import encode_speed
        selected,desired=target(action,self.env.longitudinal_scale,self.env.config,self.env.control_dt)
        self.env.selected_rate_action=selected
        obs,reward,terminated,truncated,info=self.env.step(np.array([encode_speed(desired,self.env.config)],dtype=np.float32))
        info['rate_action']=selected
        if 'control_trace' in info:
            info['control_trace']['rate_action']=selected
            info['control_trace']['rate_target_scale']=desired
        if abs(self.env.longitudinal_scale-desired)>1e-6:
            # E1 has no corner override; recovery can supersede control on other routes.
            if self.env.episode_route['id']=='E1' and self.env.rough_recovery.mode=='tracking':
                raise RuntimeError('Rate command differs from executed reference')
        return obs,reward,terminated,truncated,info

def policy_spec(config):
    from nino_rl.policies import policy_spec as history_spec
    _,kwargs=history_spec(config)
    kwargs.pop('initial_speed_scale');kwargs.pop('initial_action_std',None)
    kwargs.pop('log_std_init',None)
    return ActorCriticPolicy,kwargs
