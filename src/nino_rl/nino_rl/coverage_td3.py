"""Study-specific SB3 collection/replay; imported only by the worker."""
import numpy as np
from stable_baselines3 import TD3
from stable_baselines3.common.buffers import ReplayBuffer
from stable_baselines3.common.type_aliases import ReplayBufferSamples
from .coverage_sampling import CoverageSampler


class IndependentReplayBuffer(ReplayBuffer):
    def __init__(self, *args, study_seed=11, **kwargs):
        super().__init__(*args, **kwargs)
        if self.n_envs != 1 or self.optimize_memory_usage:
            raise ValueError("Study replay supports one env and explicit next observations")
        self.study_rng = np.random.default_rng(np.random.SeedSequence(study_seed).spawn(6)[5])

    def sample(self, batch_size, env=None):
        upper = self.buffer_size if self.full else self.pos
        if upper == 0:
            raise ValueError("Cannot sample empty study replay")
        i = self.study_rng.integers(0, upper, size=batch_size)
        # Single environment, preserving SB3 timeout and normalization semantics.
        data = (self._normalize_obs(self.observations[i, 0], env), self.actions[i, 0],
                self._normalize_obs(self.next_observations[i, 0], env),
                (self.dones[i, 0] * (1 - self.timeouts[i, 0])).reshape(-1, 1),
                self._normalize_reward(self.rewards[i, 0].reshape(-1, 1), env))
        return ReplayBufferSamples(*tuple(map(self.to_torch, data)))


class CoverageTD3(TD3):
    def _sample_action(self, learning_starts, action_noise=None, n_envs=1):
        if (learning_starts != 64 or n_envs != 1 or action_noise is not None
                or self._last_obs is None or self.action_space.shape != (1,)
                or not np.array_equal(self.action_space.low, [-1.])
                or not np.array_equal(self.action_space.high, [1.])):
            raise ValueError("Study collection contract changed")
        mean = (np.zeros(1, np.float32) if self.num_timesteps < 64 else
                self.predict(self._last_obs, deterministic=True)[0][0])
        request, audit = self.nino_sampler.choose(self._last_obs[0], mean, self.num_timesteps)
        self.nino_collection_audit = audit
        # Return the SAME scalar to the environment and the replay buffer.
        return request.reshape(1, 1).copy(), request.reshape(1, 1).copy()

    def train(self, gradient_steps, batch_size=100):
        originals = {}
        for name in ("actor", "critic"):
            optimizer = getattr(self, name).optimizer
            originals[name] = optimizer.step
            key = "nino_" + name + "_optimizer_steps"
            if not hasattr(self, key):
                setattr(self, key, 0)
            def counted(*args, _key=key, _original=optimizer.step, **kwargs):
                result = _original(*args, **kwargs)
                setattr(self, _key, getattr(self, _key) + 1)
                return result
            optimizer.step = counted
        try:
            return super().train(gradient_steps, batch_size)
        finally:
            for name, original in originals.items():
                getattr(self, name).optimizer.step = original


def build(env, seed, arm, algorithm):
    a = dict(algorithm)
    if a.pop("exploration_sigma") != .1:
        raise ValueError("Frozen Gaussian sigma changed")
    net = a.pop("network_arch")
    model = CoverageTD3("MlpPolicy", env, seed=seed, device="cpu", **a,
        action_noise=None, replay_buffer_class=IndependentReplayBuffer,
        replay_buffer_kwargs=dict(study_seed=seed), policy_kwargs=dict(net_arch=net))
    model.nino_sampler = CoverageSampler(seed, arm)
    model.nino_collection_audit = None
    return model
