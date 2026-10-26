#!/usr/bin/env python3
"""Offline invariants for bounded rearming, hardware inputs and SB3 exploration."""
import argparse
import json
from pathlib import Path
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('rl_runs/rough_observable_pilot_v2'))
    root=parser.parse_args().snapshot.resolve()
    sys.path.insert(0,str(root/'python'))
    import numpy as np
    import yaml
    import gymnasium as gym
    from stable_baselines3 import PPO
    from nino_rl.core import RobotState, PathTracker, NavReference
    from nino_rl.control_v2 import make_observation, history_action, baseline_action, validate_model
    from nino_rl.longitudinal_control import decode_speed,ramp_speed
    from nino_rl.reactive_observable import BoundedCue,extra_observation
    from nino_rl.policies import policy_spec
    config=yaml.safe_load((root/'config.yaml').read_text())
    from nino_rl.training_contract import training_contract
    interface=training_contract(config)['observation_interface']
    assert '72/frame' in interface and '360 history' in interface
    cue=BoundedCue(config['reactive_probe'])
    disturbed=RobotState(accel_z=12.,left_wheel_velocity=6.4,right_wheel_velocity=6.4)
    phases=[]
    longest=run=0
    for _ in range(200):
        _, trace=cue.update(disturbed,(.4,0),.975,.1)
        phases.append(trace['cue_phase'])
        run=run+1 if trace['cue_phase']=='recovering' else 0
        longest=max(longest,run)
    assert trace['cue_events']>=5 and longest<=8
    quiet=BoundedCue(config['reactive_probe'])
    for _ in range(100):
        _,qt=quiet.update(RobotState(accel_z=9.80665,left_wheel_velocity=6.4,
            right_wheel_velocity=6.4),(.4,0),.975,.1)
    assert qt['cue_events']==0
    state=RobotState(accel_z=9.80665,linear_velocity=.34,left_wheel_velocity=5.44,right_wheel_velocity=5.44)
    path=PathTracker([(0.,0.),(10.5,0.)])
    reference=NavReference(desired_linear_velocity=.4,final_goal_distance=10.5,
        local_waypoint_distance=2.,waypoint_time_remaining_fraction=1.,valid=True)
    action=history_action(baseline_action(config),config)
    frame,_=make_observation(state,path,config['path']['lookahead_m'],action,reference)
    extra=extra_observation(dict(duration=.1,square_integral=.4,peak=3.),qt,.85,(.34,0),(.33,0),.1)
    assert extra.shape==(16,) and np.isclose(extra[0],.2) and extra[-1]==1
    obs=np.tile(np.concatenate((frame,extra)),5).astype(np.float32)
    assert obs.shape==(360,)
    state.ground_linear_velocity=123.;state.ground_yaw_rate=456.
    other,_=make_observation(state,path,config['path']['lookahead_m'],action,reference,
                            preview=[np.nan]*4)
    np.testing.assert_array_equal(frame,other)
    class Dummy(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(360,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,shape=(1,),dtype=np.float32)
        def reset(self,*,seed=None,options=None):return obs.copy(),{}
        def step(self,action):return obs.copy(),0.,False,False,{}
    cls,kwargs=policy_spec(config)
    model=PPO(cls,Dummy(),policy_kwargs=kwargs,use_sde=True,sde_sample_freq=6,
        n_steps=8,batch_size=8,seed=config['seed'],device='cpu')
    assert len(model.policy.optimizer.state)==0 and model.num_timesteps==0
    fixed=model.predict(obs,deterministic=True)[0]
    model.policy.reset_noise(1)
    a=model.predict(obs,deterministic=False)[0]
    b=model.predict(obs,deterministic=False)[0]
    np.testing.assert_array_equal(a,b)
    samples=[]
    for _ in range(200):
        model.policy.reset_noise(1)
        samples.append(float(model.predict(obs,deterministic=False)[0][0]))
    assert np.std(samples)>.1
    with tempfile.TemporaryDirectory() as temp:
        model.save(Path(temp)/'model.zip')
        restored=PPO.load(Path(temp)/'model.zip',device='cpu')
        np.testing.assert_array_equal(restored.predict(obs,deterministic=True)[0],fixed)
    from types import SimpleNamespace
    try:validate_model(SimpleNamespace(observation_space=SimpleNamespace(shape=(280,)),
                                      action_space=SimpleNamespace(shape=(1,))),360,1)
    except ValueError:pass
    else:raise AssertionError('Old tensor contract accepted')
    result=dict(one_action=True,no_truth_velocity_or_preview=True,fresh_optimizer=True,
        save_reload_passed=True,old_model_rejected=True,bounded_rearming=True,
        max_recovery_s=longest*.1,noise_persistent_on_fixed_observation=True,
        empirical_clipped_action_std=float(np.std(samples)),history_size=360,
        initial_example_speed_scale=decode_speed(fixed,config),
        qualification='Synthetic hardware frame; a real stochastic-rollout exposure gate follows before training')
    (root/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
