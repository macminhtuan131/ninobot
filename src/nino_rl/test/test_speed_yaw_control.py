"""Check the new action meaning and safe transfer without running Gazebo."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import pytest
import torch as th
from stable_baselines3 import PPO

from nino_rl.control_v2 import (
    action_size, baseline_action, decode_control, history_action, make_observation,
)
from nino_rl.core import load_config, PathTracker, RobotState
from nino_rl.flat_curriculum import FlatCourseCurriculum
from nino_rl.model_transfer import initialize_speed_yaw_actor
from nino_rl.policies import policy_spec
from nino_rl.training_contract import training_contract, validate_resume

ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "src/nino_rl/config/combined_flat_speed_yaw_pilot.yaml"


class OfflineEnv(gym.Env):
    def __init__(self, actions):
        self.observation_space = gym.spaces.Box(-5., 5., (300,), dtype=np.float32)
        self.action_space = gym.spaces.Box(-1., 1., (actions,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return np.zeros(300, dtype=np.float32), {}

    def step(self, action):
        return np.zeros(300, dtype=np.float32), 0., True, False, {}


def new_model(config, actions):
    policy, kwargs = policy_spec(config)
    return PPO(policy, OfflineEnv(actions), policy_kwargs=kwargs,
               n_steps=8, batch_size=8, device="cpu", seed=42)


def test_new_mapping_history_and_invalid_actions():
    config = load_config(PROFILE)
    assert action_size(config) == 2
    np.testing.assert_array_equal(baseline_action(config), [1., 0.])
    scale, torque, yaw = decode_control([2., -2.], config)
    assert scale == 1. and yaw == -.25
    np.testing.assert_array_equal(torque, [0., 0.])
    for invalid in ([0., 0., 0.], [np.nan, 0.], [np.inf, 0.]):
        with pytest.raises(ValueError):
            decode_control(invalid, config)
    previous = history_action([.4, -.8], config)
    np.testing.assert_allclose(previous, [.4, 0., -.8])
    state, path = RobotState(accel_z=9.80665), PathTracker([(0., 0.), (6.45, 0.)])
    frame, _ = make_observation(state, path, config["path"]["lookahead_m"], previous,
                                action_mode=config["action_mode"])
    straight, _ = make_observation(state, path, config["path"]["lookahead_m"],
                                   np.array([.4, 0., 0.]), action_mode=config["action_mode"])
    assert frame.shape == (60,)
    np.testing.assert_array_equal(frame[:52], straight[:52])
    np.testing.assert_allclose(frame[52:55], previous)


def test_profile_locks_stage_and_rejects_old_contract():
    config = load_config(PROFILE)
    flat = FlatCourseCurriculum(config["flat_curriculum"],
                                config["course_cable_randomization"]["cables"],
                                config["adaptive_terrain"]["max_features"])
    assert flat.fixed_stage == flat.stage_index == 2
    assert config["flat_curriculum"]["replay_probability"] == 0.
    assert config["flat_curriculum"]["stages"][2]["cable_indices"] == [2, 4]
    assert config["goal_tolerance_m"] == .2
    assert config["target_finish_seconds"] == 22.
    assert config["max_episode_seconds"] == 30.
    contract = training_contract(config)
    assert contract["revision"] == 34
    assert contract["action_interface"]["additive_torque"] is False
    validate_resume(SimpleNamespace(nino_training_contract=contract), config)
    old = load_config(PROFILE.parent / "combined_flat_curriculum_arrival_guard.yaml")
    with pytest.raises(ValueError, match="contract differs"):
        validate_resume(SimpleNamespace(nino_training_contract=training_contract(old)), config)


def test_transfer_keeps_speed_mean_but_discards_torque_and_value(tmp_path):
    th.set_num_threads(1)
    config = load_config(PROFILE)
    old = load_config(PROFILE.parent / "combined_flat_curriculum_arrival_guard.yaml")
    source, target = new_model(old, 3), new_model(config, 2)
    source.nino_training_contract = training_contract(old)
    # Make source differ materially from freshly seeded destination.
    with th.no_grad():
        for param in source.policy.parameters():
            param.add_(.015)
    source_before = deepcopy(source.policy.state_dict())
    target_before = deepcopy(target.policy.state_dict())
    initialize_speed_yaw_actor(target, source)
    obs = np.random.default_rng(17).normal(0., .1, (4, 300)).astype(np.float32)
    source_action, _ = source.predict(obs, deterministic=True)
    target_action, _ = target.predict(obs, deterministic=True)
    np.testing.assert_allclose(target_action[:, 0], source_action[:, 0], atol=1e-7)
    np.testing.assert_array_equal(target_action[:, 1], np.zeros(4))
    for key, tensor in target.policy.state_dict().items():
        if key.startswith(("vf_features_extractor.", "mlp_extractor.value_net.", "value_net.")):
            assert th.equal(tensor, target_before[key]), key
    for key, tensor in source.policy.state_dict().items():
        assert th.equal(tensor, source_before[key]), key
    assert th.equal(target.policy.log_std[0], source.policy.log_std[0])
    assert th.equal(target.policy.log_std[1], target_before["log_std"][1])
    assert target.num_timesteps == 0 and not target.policy.optimizer.state
    target.nino_training_contract = training_contract(config)
    target.save(tmp_path / "new_actor")
    loaded = PPO.load(tmp_path / "new_actor", device="cpu")
    validate_resume(loaded, config)
    np.testing.assert_array_equal(loaded.predict(obs, deterministic=True)[0], target_action)
    source.nino_training_contract["action_mode"] = "yaw_reference"
    with pytest.raises(ValueError, match="action mode"):
        initialize_speed_yaw_actor(target, source)
    loaded.set_env(OfflineEnv(2))
    loaded.learn(8)
    assert loaded.num_timesteps == 8
    assert np.isfinite(loaded.predict(obs, deterministic=True)[0]).all()


def test_absolute_yaw_actor_transfers_speed_to_feedback_with_fresh_yaw_and_critic():
    th.set_num_threads(1)
    old = load_config(PROFILE.parent / 'combined_flat_speed_yaw_timing_pilot.yaml')
    config = load_config(PROFILE.parent / 'combined_flat_feedback_pilot.yaml')
    source, target = new_model(old, 2), new_model(config, 2)
    source.nino_training_contract = training_contract(old)
    with th.no_grad():
        for param in source.policy.parameters():
            param.add_(.015)
    before = deepcopy(target.policy.state_dict())
    initialize_speed_yaw_actor(target, source)
    obs = np.random.default_rng(8).normal(0., .1, (4, 300)).astype(np.float32)
    previous, _ = source.predict(obs, deterministic=True)
    new, _ = target.predict(obs, deterministic=True)
    np.testing.assert_allclose(new[:,0], previous[:,0], atol=1e-7)
    np.testing.assert_array_equal(new[:,1], np.zeros(4))
    for key, tensor in target.policy.state_dict().items():
        if key.startswith(('vf_features_extractor.', 'mlp_extractor.value_net.', 'value_net.')):
            assert th.equal(tensor, before[key]), key
    assert not target.policy.optimizer.state and target.num_timesteps == 0
