import gymnasium as gym
import numpy as np
import pytest
import torch
from stable_baselines3 import TD3
from stable_baselines3.common.callbacks import BaseCallback
from nino_rl.studio_deferred_reset import DeferredResetVecEnv


class ResetFailure(gym.Env):
    observation_space=gym.spaces.Box(-100,100,(1,),dtype=np.float32)
    action_space=gym.spaces.Box(-1,1,(1,),dtype=np.float32)
    def __init__(self,fail=True):self.resets=0;self.fail=fail;self.step_count=0
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed);self.resets+=1
        if self.fail and self.resets==2:raise TimeoutError('synthetic startup failed')
        self.step_count=0;return np.array([10.],np.float32),{}
    def step(self,action):
        self.step_count+=1
        return np.array([10.+self.step_count],np.float32),1.,self.step_count==2,False,{}


def model_and_callback(env,total):
    torch.set_num_threads(1)
    model=TD3('MlpPolicy',env,learning_starts=0,buffer_size=32,batch_size=2,
              train_freq=1,gradient_steps=1,policy_kwargs=dict(net_arch=[8,8]),seed=1)
    class Callback(BaseCallback):
        def _on_step(self):return True
        def _on_rollout_end(self):
            if self.model.num_timesteps<total:env.reset_after_store(self.model)
    return model,Callback()


def test_failed_next_reset_preserves_terminal_replay_and_model_boundary(tmp_path):
    raw=ResetFailure();vec=DeferredResetVecEnv(raw);model,cb=model_and_callback(vec,6)
    try:
        with pytest.raises(TimeoutError):model.learn(6,callback=cb)
        assert model.num_timesteps==model.replay_buffer.size()==2
        assert model.replay_buffer.dones[1,0]==1
        assert model.replay_buffer.next_observations[1,0,0]==12
        model.save(tmp_path/'model');model.save_replay_buffer(tmp_path/'replay.pkl')
        loaded=TD3.load(tmp_path/'model');loaded.load_replay_buffer(tmp_path/'replay.pkl')
        assert loaded.num_timesteps==loaded.replay_buffer.size()==2
        assert loaded._n_updates==model._n_updates
    finally:vec.close()


def test_final_transition_does_not_start_an_unused_episode():
    raw=ResetFailure();vec=DeferredResetVecEnv(raw);model,cb=model_and_callback(vec,2)
    try:
        model.learn(2,callback=cb)
        assert raw.resets==1 and model.num_timesteps==2 and model.replay_buffer.size()==2
    finally:vec.close()


def test_successful_next_reset_is_used_before_next_action():
    raw=ResetFailure(fail=False);vec=DeferredResetVecEnv(raw);model,cb=model_and_callback(vec,4)
    try:
        model.learn(4,callback=cb)
        assert raw.resets==2
        assert model.replay_buffer.observations[2,0,0]==10.
    finally:vec.close()
