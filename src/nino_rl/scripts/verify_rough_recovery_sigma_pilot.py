#!/usr/bin/env python3
"""Offline single-change, fresh initialization, reward and resume-contract checks."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('rl_runs/rough_recovery_sigma_pilot_v1'))
    root = parser.parse_args().snapshot.resolve()
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify_rough_observable_pilot.py')),
                    '--snapshot', str(root)], check=True)
    sys.path.insert(0, str(root / 'python'))
    import gymnasium as gym
    import numpy as np
    import torch
    import yaml
    from stable_baselines3 import PPO
    from nino_rl.core import RobotState
    from nino_rl.policies import policy_spec
    from nino_rl.reactive_reward import compute_reward
    from nino_rl.training_contract import training_contract, validate_resume
    from prepare_rough_observable_pilot_v2 import OUTPUT as original
    torch.set_num_threads(2)
    old = yaml.safe_load((original / 'config.yaml').read_text())
    new = yaml.safe_load((root / 'config.yaml').read_text())
    restored = deepcopy(new)
    restored['reward_v2']['longitudinal_weights']['velocity_sigma_m_s'] = .4
    assert restored == old and new['seed'] == 17000

    class Dummy(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., shape=(360,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)
        def reset(self, *, seed=None, options=None):
            return np.zeros(360, dtype=np.float32), {}
        def step(self, action):
            return np.zeros(360, dtype=np.float32), 0., False, False, {}

    def fresh(config):
        cls, kwargs = policy_spec(config)
        p = config['ppo']
        return PPO(cls, Dummy(), policy_kwargs=kwargs, use_sde=True,
                   sde_sample_freq=p['sde_sample_freq'], n_steps=p['n_steps'],
                   batch_size=p['batch_size'], seed=config['seed'], device='cpu')

    a, b = fresh(old), fresh(new)
    hashes = {}
    for name, tensor in a.policy.state_dict().items():
        other = b.policy.state_dict()[name]
        assert torch.equal(tensor, other), 'Fresh parameter initialization differs: ' + name
        hashes[name] = hashlib.sha256(tensor.detach().cpu().numpy().tobytes()).hexdigest()
    assert a.num_timesteps == b.num_timesteps == 0
    assert not a.policy.optimizer.state and not b.policy.optimizer.state
    assert training_contract(new)['revision'] == 48
    old_contract = deepcopy(training_contract(old))
    old_contract['revision'] = 47
    a.nino_training_contract = old_contract
    try:
        validate_resume(a, new)
    except ValueError:
        pass
    else:
        raise AssertionError('Old contract accepted for optimizer resume')
    start = SimpleNamespace(distance_remaining=10.)
    end = SimpleNamespace(distance_remaining=9.964, lateral_error=0., heading_error=0.)
    robot = RobotState(ground_linear_velocity=.36, left_wheel_velocity=5.76, right_wheel_velocity=5.76)
    args = (start, end, robot, [0.], [0.], [0., 0.], .1, dict(square_integral=.1))
    ref = SimpleNamespace(valid=True, desired_linear_velocity=.4)
    checks = {}
    for phase in ('ready', 'holding', 'recovering', 'cooldown'):
        kwargs = dict(reference=ref, elapsed=10., reactive_holding=phase == 'holding',
                      executed_scale=.9, previous_executed_scale=.88)
        _, before = compute_reward(*args, old['reward_v2'], **kwargs)
        _, after = compute_reward(*args, new['reward_v2'], **kwargs)
        for name in before:
            np.testing.assert_allclose(after[name], before[name] * (16 if name == 'command_velocity' else 1), atol=1e-12)
        if phase == 'holding':
            assert after['command_velocity'] == 0.
        checks[phase] = dict(before=before['command_velocity'], after=after['command_velocity'])
    result = json.loads((root / 'verification.json').read_text())
    result.update(single_reward_parameter_changed=True, initial_actor_critic_identical=True,
        fresh_parameter_sha256=hashes, seed=17000, zero_step_counters=True,
        old_contract_resume_rejected=True, velocity_penalty_multiplier=16,
        phase_reward_checks=checks, training_contract_revision=48)
    (root / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Passed: one config change, identical fresh weights, empty optimizer, old resume rejected, 16x non-holding cost.')


if __name__ == '__main__':
    main()
