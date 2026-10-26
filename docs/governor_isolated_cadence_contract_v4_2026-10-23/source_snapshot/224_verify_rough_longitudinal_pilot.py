#!/usr/bin/env python3
"""Verify one-action policy construction, fresh optimizer and sensor isolation."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,default=Path(__file__).resolve().parents[3]/'rl_runs/rough_longitudinal_pilot_v1')
    root=parser.parse_args().snapshot.resolve();sys.path.insert(0,str(root/'python'))
    import numpy as np
    import yaml
    import gymnasium as gym
    from stable_baselines3 import PPO
    from nino_rl.core import RobotState,PathTracker
    from nino_rl.control_v2 import make_observation,baseline_action,history_action,action_size,decode_control,validate_model
    from nino_rl.policies import policy_spec
    config=yaml.safe_load((root/'config.yaml').read_text())
    assert action_size(config)==1
    action=baseline_action(config);assert action.shape==(1,)
    speed,torque,yaw=decode_control(action,config)
    assert speed==1. and yaw==0.;np.testing.assert_array_equal(torque,[0,0])
    state=RobotState(accel_z=9.80665);path=PathTracker([(0,0),(10,0)])
    previous=history_action(action,config)
    observation,_=make_observation(state,path,config['path']['lookahead_m'],previous,preview=[1,2,3,1])
    state.ground_linear_velocity=100.;state.ground_yaw_rate=20.
    other,_=make_observation(state,path,config['path']['lookahead_m'],previous,preview=[np.nan]*4)
    np.testing.assert_array_equal(observation,other)
    class Dummy(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(280,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,shape=(1,),dtype=np.float32)
        def reset(self,*,seed=None,options=None):return np.zeros(280,dtype=np.float32),{}
        def step(self,action):return np.zeros(280,dtype=np.float32),0.,False,False,{}
    policy,kwargs=policy_spec(config)
    model=PPO(policy,Dummy(),policy_kwargs=kwargs,n_steps=8,batch_size=8,seed=config['seed'],device='cpu')
    prediction,_=model.predict(np.zeros(280,dtype=np.float32),deterministic=True)
    assert prediction.shape==(1,)
    assert decode_control(prediction,config)[0]>=.9
    assert len(model.policy.optimizer.state)==0 and model.num_timesteps==0
    with __import__('tempfile').TemporaryDirectory() as temporary:
        checkpoint=Path(temporary)/'shape.zip';model.save(checkpoint)
        restored=PPO.load(checkpoint,device='cpu')
        np.testing.assert_array_equal(restored.predict(np.zeros(280,dtype=np.float32),deterministic=True)[0],prediction)
    try:validate_model(SimpleNamespace(observation_space=SimpleNamespace(shape=(300,)),
        action_space=SimpleNamespace(shape=(3,))),280,1)
    except ValueError:pass
    else:raise AssertionError('Old observation/action contract accepted')
    result=dict(one_action=True,history_size=280,no_truth_velocity_or_preview=True,
        fresh_optimizer=True,fresh_step_counter=True,initial_speed_scale=decode_control(prediction,config)[0],
        save_reload_passed=True,old_model_rejected=True)
    (root/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(result)


if __name__=='__main__':main()
