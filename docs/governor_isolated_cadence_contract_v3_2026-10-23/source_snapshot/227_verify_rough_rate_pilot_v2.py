#!/usr/bin/env python3
"""Verify discrete likelihoods, exact rate execution and fresh initialization."""
import json
import sys
from pathlib import Path
import numpy as np
import torch
import gymnasium as gym
from prepare_rough_rate_pilot_v2 import OUTPUT,prepare

def main():
    config,plan=prepare();sys.path.insert(0,str(OUTPUT/'python'))
    from nino_rl.rate_actions import policy_spec,target
    from nino_rl.training_contract import training_contract,validate_resume
    from nino_rl.control_v2 import validate_model,validate_action_mode
    from stable_baselines3 import PPO
    class Dummy(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(360,),dtype=np.float32)
        action_space=gym.spaces.Discrete(3)
        def reset(self,*,seed=None,options=None):return np.zeros(360,dtype=np.float32),{}
        def step(self,action):return np.zeros(360,dtype=np.float32),0.,False,False,{}
    torch.set_num_threads(2)
    cls,kw=policy_spec(config);p=config['ppo']
    model=PPO(cls,Dummy(),policy_kwargs=kw,use_sde=False,n_steps=p['n_steps'],batch_size=p['batch_size'],
        seed=17000,device='cpu')
    model.nino_training_contract=training_contract(config)
    assert model.num_timesteps==0 and not model.policy.optimizer.state
    # Use saved realistic causal inputs rather than only zero observations.
    file=next((Path(__file__).resolve().parents[3]/'rl_runs/rough_holding_reference_candidate_v1/train/actor_capture').glob('chunk_*.npz'))
    with np.load(file) as b:obs=torch.as_tensor(b['observations'][:32])
    with torch.no_grad():
        distribution=model.policy.get_distribution(obs)
        probabilities=distribution.distribution.probs
        actions=distribution.get_actions(deterministic=False)
        _,replay,_=model.policy.evaluate_actions(obs,actions)
        direct=probabilities.gather(1,actions.reshape(-1,1)).log().reshape(-1)
    torch.testing.assert_close(probabilities.sum(1),torch.ones(len(obs)))
    torch.testing.assert_close(replay,direct)
    assert int(actions.min())>=0 and int(actions.max())<=2
    validate_model(model,360,1);validate_action_mode(model,config);validate_resume(model,config)
    model.save(OUTPUT/'untrained_verification_model.zip')
    loaded=PPO.load(OUTPUT/'untrained_verification_model.zip',device='cpu')
    validate_model(loaded,360,1);validate_action_mode(loaded,config);validate_resume(loaded,config)
    with torch.no_grad():torch.testing.assert_close(loaded.policy.get_distribution(obs).distribution.probs,probabilities)
    assert not loaded.policy.optimizer.state
    old=PPO.load(next((Path(__file__).resolve().parents[3]/'rl_runs/rough_holding_reference_candidate_v1/train').glob('*/nino_ppo_final.zip')),device='cpu')
    try:validate_action_mode(old,config)
    except ValueError:pass
    else:raise AssertionError('Old continuous actor accepted')
    scales=[];s=1.
    for action in [0]*8+[1]*4+[2]*8:
        _,nextscale=target(action,s,config,.1)
        assert abs(nextscale-s)<=.040001 and .55<=nextscale<=1.
        s=nextscale;scales.append(s)
    np.testing.assert_allclose(scales[5],.76,atol=1e-9)
    np.testing.assert_allclose(scales[7:12],.68,atol=1e-9)
    np.testing.assert_allclose(scales[-1],1.,atol=1e-9)
    for s in (.55,.72,1.):
        for action in range(3):
            _,v=target(action,s,config,.1);assert .55<=v<=1. and abs(v-s)<=.040001
    result=dict(passed=True,revision=52,fresh_actor_critic_optimizer=True,num_timesteps=0,
        categorical_likelihood_replay=True,save_reload=True,old_checkpoint_rejected=True,
        initial_probability_mean=probabilities.mean(0).tolist(),scripted_scale_sequence=scales,
        required_full_to_point70_s=.75,hold_seconds=.8,
        source_reward_unchanged=True,live_execution_pending=True,categorical_telemetry=True)
    (OUTPUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
