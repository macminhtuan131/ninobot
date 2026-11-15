"""Store a terminal transition before attempting the next costly Gazebo reset.

Only for single-env TD3 with train_freq=(1,step). The Studio callback MUST call
reset_after_store at rollout end, before the next policy action is sampled.
"""
from copy import deepcopy
from stable_baselines3.common.vec_env import DummyVecEnv


class DeferredResetVecEnv(DummyVecEnv):
    def __init__(self,env):
        super().__init__([lambda:env]);self.pending_reset=False

    def step_wait(self):
        if self.pending_reset:
            raise RuntimeError('Terminal transition must be stored then reset before next action')
        obs,self.buf_rews[0],terminated,truncated,self.buf_infos[0]=self.envs[0].step(self.actions[0])
        self.buf_dones[0]=terminated or truncated
        self.buf_infos[0]['TimeLimit.truncated']=bool(truncated and not terminated)
        if self.buf_dones[0]:
            self.buf_infos[0]['terminal_observation']=deepcopy(obs)
            self.pending_reset=True
        self._save_obs(0,obs)
        return self._obs_from_buf(),self.buf_rews.copy(),self.buf_dones.copy(),deepcopy(self.buf_infos)

    def reset_after_store(self,model):
        if not self.pending_reset:return
        obs,self.reset_infos[0]=self.envs[0].reset()
        self._save_obs(0,obs)
        model._last_obs=self._obs_from_buf()
        self.pending_reset=False
