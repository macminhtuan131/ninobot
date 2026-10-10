"""Check that the experiment isolates actions and keeps fresh value/optimizer state."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ablation_preserves_input_and_unselected_component():
    module = script('run_flat_speed_yaw_comparison')
    predicted = np.array([.62, -.31])
    assert np.allclose(module.reference_action(predicted, 'speed'), [.62, 0])
    assert np.allclose(module.reference_action(predicted, 'yaw'), [1, -.31])
    assert np.allclose(predicted, [.62, -.31])
    with pytest.raises(ValueError):
        module.reference_action([1, np.nan], 'speed')


def test_arrival_loss_cannot_select_an_ablation_as_better():
    module = script('run_flat_targeted_pilot')
    reports = {name: {'objective': {'quality_cost': cost}, 'report': {'success_rate': rate}}
               for name, cost, rate in [('ppo', 3., 1.), ('speed', 2., .95), ('yaw', 2.5, 1.)]}
    settings = module.choose_initialization(reports)
    assert settings['reset_speed'] and not settings['reset_yaw']


@pytest.mark.parametrize('reset_speed,reset_yaw', [(True, True), (True, False), (False, True)])
def test_pi_centered_actor_does_not_transfer_critic_or_optimizer(monkeypatch, reset_speed, reset_yaw):
    import gymnasium as gym
    import torch
    from stable_baselines3 import PPO
    from nino_rl.policies import HistoryActorCriticPolicy, HistoryFeatures

    class SpaceOnlyEnv(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., (300,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., (2,), dtype=np.float32)

    kwargs = dict(features_extractor_class=HistoryFeatures, share_features_extractor=False,
                  net_arch={'pi': [16], 'vf': [16]}, initial_action_std=[.2, .04])
    source = PPO(HistoryActorCriticPolicy, SpaceOnlyEnv(), policy_kwargs=kwargs,
                 n_steps=8, batch_size=8, seed=1, device='cpu')
    target = PPO(HistoryActorCriticPolicy, SpaceOnlyEnv(), policy_kwargs=kwargs,
                 n_steps=8, batch_size=8, seed=2, device='cpu')
    before = deepcopy(target.policy.state_dict())
    old_actor = deepcopy(source.policy.state_dict())
    module = script('run_flat_targeted_pilot')
    namespace = types.ModuleType('nino_rl.pilot_initialization')
    monkeypatch.setitem(sys.modules, 'nino_rl.pilot_initialization', namespace)
    exec(module.INITIALIZER, namespace.__dict__)
    settings = dict(reset_speed=reset_speed, reset_yaw=reset_yaw, speed_scale=.97,
                    speed_action_std=.08, yaw_action_std=.04)
    namespace.initialize_targeted_actor(target, source, {'flat_targeted_pilot': {'initialization': settings}})
    for key, value in target.policy.state_dict().items():
        if key.startswith(('vf_features_extractor.', 'mlp_extractor.value_net.', 'value_net.')):
            assert torch.equal(value, before[key])
        if key.startswith(('pi_features_extractor.', 'mlp_extractor.policy_net.')):
            assert torch.equal(value, old_actor[key])
        assert torch.equal(source.policy.state_dict()[key], old_actor[key])
    for observation in (np.zeros(300, dtype=np.float32), np.ones(300, dtype=np.float32)):
        action = target.predict(observation, deterministic=True)[0]
        expected = source.predict(observation, deterministic=True)[0]
        if reset_speed:
            expected[0] = .94
        if reset_yaw:
            expected[1] = 0
        assert np.allclose(action, expected, atol=1e-6)
    assert target.num_timesteps == 0 and not target.policy.optimizer.state
