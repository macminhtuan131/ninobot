"""Gym transitions on invented data: no Gazebo, robot or optimizer is started."""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from nino_rl.unknown_step_environment import UnknownStepEnv
from nino_rl.unknown_step_runtime import RewardSettings, UnknownTaskData
from test_unknown_step_runtime import controller_config, sample, settings, view


class ToyBackend:
    def __init__(self, *, cutoff=None, bad_clock=None):
        self.cutoff, self.bad_clock = cutoff, bad_clock
        self.closed = False

    def reset(self, seed=None):
        self.n = 0
        return view(0.), dict(physical_sample=sample(), truth_used_for_guidance=False)

    def advance_reference(self, v, w, dt):
        self.n += 1
        t, x = self.n * dt, min(2., self.n * .4)
        left, right = v - .34273666 * w / 2, v + .34273666 * w / 2
        p = sample(t, x, body_speed_norm_m_s=.1 if x < 2. else 0.,
                   accepted_reference_m_s=(left, right), motion_requested=x < 2.)
        if self.n == self.bad_clock:
            p = replace(p, stamp_s=t - .06)
        return view(t, baseline=(0., 0.) if x == 2. else (.2, 0.)), {}, False, self.n == self.cutoff, dict(
            physical_sample=p, truth_used_for_guidance=False)

    def close(self):
        self.closed = True


def environment(backend=None, **changes):
    weights = RewardSettings(progress=1., cross_track=.1, heading=.1, time=.01,
                             accepted_action=.01, accepted_action_change=.001,
                             success=2., failure=3., cross_scale_m=.1, heading_scale_rad=.2)
    return UnknownStepEnv(controller_config(), backend or ToyBackend(), settings(**changes), weights)


def test_gym_contract_on_synthetic_backend():
    env = environment()
    try:
        check_env(env, skip_render_check=True)
    finally:
        env.close()
    assert env.backend.closed


def test_complete_episode_keeps_requested_projected_and_physical_evidence_separate():
    env = environment()
    obs, reset = env.reset(seed=11)
    assert obs.shape == (100,) and 'physical_sample' in reset
    total = 0.
    try:
        for _ in range(100):
            obs, reward, term, trunc, info = env.step(np.array([1.], np.float32))
            total += reward
            assert obs.shape == (100,) and reward == pytest.approx(sum(info['reward_terms'].values()))
            assert info['replay_action'] == [1.] and info['requested_scalar_action'] == [1.]
            assert info['reference_trace']['inherited_proposal'] == [.5, 0.]
            assert not info['truth_used_for_guidance']
            if term or trunc:
                break
        assert term and not trunc and info['task']['task_success']
        assert info['task']['whole_robot_clear'] and info['task']['continuous_quiet_s'] >= .2 - 1e-8
        assert np.isfinite(total)
        with pytest.raises(RuntimeError):
            env.step([0.])
    finally:
        env.close()


def test_external_cutoff_is_censored_not_a_task_failure_or_success():
    env = environment(ToyBackend(cutoff=3))
    try:
        env.reset()
        for _ in range(3):
            _, _, term, trunc, info = env.step([0.])
        assert not term and trunc and not info['task']['task_success']
        assert info['task']['right_censored'] and 'outcome' not in info['reward_terms']
    finally:
        env.close()


def test_bad_measurement_has_no_transition_and_requires_reset():
    env = environment(ToyBackend(bad_clock=2))
    try:
        env.reset()
        env.step([0.])
        with pytest.raises(UnknownTaskData):
            env.step([0.])
        with pytest.raises(RuntimeError):
            env.step([0.])
    finally:
        env.close()


def test_full_checkpoint_identity_pins_task_and_reward_not_only_tensor_shape():
    env = environment()
    try:
        env.require_checkpoint(deepcopy(env.identity))
        wrong = deepcopy(env.identity)
        wrong['reward']['progress'] *= 2
        with pytest.raises(ValueError, match='identity'):
            env.require_checkpoint(wrong)
        with pytest.raises(ValueError):
            env.require_checkpoint(dict(engine='common103_v2'))
    finally:
        env.close()
