"""Objective, finite deadline and reference isolation regressions; no Gazebo."""
from copy import deepcopy
import numpy as np
import pytest
from nino_rl import residual_sim_task as task


def info(base=(.2, 0.), speed=.2, norm=None, x=1., reference=(.2, .2), wheel=(3.2, 3.2)):
    return dict(reference_trace=dict(original_baseline_body=base, accepted_reference_wheel_m_s=reference),
                truth_pose_m_rad=[x, 0., 0.], body_speed_m_s=speed,
                body_speed_norm_m_s=abs(speed) if norm is None else norm, body_yaw_rad_s=0., feedback_wheel_rad_s=wheel)


def test_v2_retains_abi_and_does_not_require_real_or_reuse_v1_budget():
    from nino_rl.residual_experiment import experiment_contract
    from nino_rl.residual_sim_pilot import config as v1
    c = task.config()
    assert experiment_contract(c)['abi_sha256'] == experiment_contract(v1())['abi_sha256']
    assert c['task']['training_transitions'] == 512 and c['backend']['max_episodes'] == 4
    assert c['training']['allowed'] is False and c['hardware_authority'] == 0
    assert task.fingerprint() != __import__('nino_rl.residual_sim_pilot', fromlist=['fingerprint']).fingerprint()


def test_independent_target_cannot_be_changed_by_executed_boost():
    c = task.config()
    a, b = task.TaskScore(c), task.TaskScore(c)
    for step in range(30):
        _, first = a.update(info(reference=(.2, .2)), (0., 0.), (step+1)*.1)
        _, second = b.update(info(reference=(.24, .24)), (1., 0.), (step+1)*.1)
        assert first['nominal_shaped_body'] == second['nominal_shaped_body']
    clean = a.update(info(speed=.2), (0., 0.), 3.1)[0]
    boost = b.update(info(speed=.24), (1., 0.), 3.1)[0]
    assert clean > boost  # Speed boost cannot buy a progress reward.


def test_zero_source_is_not_body_stop_and_stall_is_not_task_success():
    c = task.config()
    s = task.TaskScore(c)
    zero = info(base=(0., 0.), speed=0., x=.68, reference=(0., 0.), wheel=(0., 0.))
    for i in range(120, 140):
        reward, result = s.update(zero, (0., 0.), (i+1)*.1)
    assert result['stop_completed'] and not result['task_success']
    assert result['task_deadline'] and result['reward_terms']['missing_marker'] == -5
    moving = task.TaskScore(c)
    _, result = moving.update(info(base=(0., 0.), speed=0., norm=.02, reference=(0., 0.), wheel=(0., 0.)), (0., 0.), 14.)
    assert not result['stop_completed'] and not result['task_success']
    assert result['reward_terms']['not_stopped'] == -10


def test_task_requires_two_continuous_quiet_seconds_after_shaped_zero():
    s = task.TaskScore(task.config())
    quiet = info(base=(0., 0.), speed=0., reference=(0., 0.), wheel=(0., 0.))
    for i in range(19):
        _, result = s.update(quiet, (0., 0.), 10.+i*.1)
    assert not result['stop_completed']
    s.update(info(base=(0., 0.), speed=.011, reference=(0., 0.), wheel=(0., 0.)), (0., 0.), 11.9)
    for i in range(20):
        _, result = s.update(quiet, (0., 0.), 12.1+i*.1)
    assert result['task_success'] and result['continuous_quiet_s'] == pytest.approx(2.)


def test_fixed_deadline_is_terminal_not_timeout(monkeypatch, tmp_path):
    import gymnasium as gym
    import nino_rl.residual_experiment as shared
    class Fake(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., (100,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., (2,), dtype=np.float32)
        backend = type('Backend', (), {})()
        def reset(self, **kwargs): return np.zeros(100, np.float32), {}
        def step(self, action):
            return np.zeros(100, np.float32), 100., False, True, dict(info(base=(0., 0.), speed=0., reference=(0., 0.), wheel=(0., 0.)), termination_reason='time_limit')
    monkeypatch.setattr(shared, 'make_environment', lambda *args: Fake())
    env = task.environment(task.config(), tmp_path/'backend', tmp_path/'world.sdf')
    env.reset()
    env.steps = 139
    _, reward, terminal, truncated, result = env.step(np.zeros(2))
    assert terminal and not truncated and reward < 0
    assert result['termination_reason'] == 'task_deadline_failure'
    assert not result['task']['task_success']
    assert 'truth' not in result['reference_trace']


def test_caster_audit_cannot_modify_policy_wheel_channel(tmp_path):
    from types import SimpleNamespace as NS
    b = task.TaskBackend(task.config(), tmp_path/'backend', task.repo(), tmp_path/'world.sdf')
    msg = NS(name=['left_wheel_joint', 'right_wheel_joint', 'caster_left_swivel_joint'],
             velocity=[1., 2., 3.], position=[0., 0., 1.5], header=NS(stamp=NS(sec=1, nanosec=0)))
    b._receive('wheel', msg)
    assert b.messages['wheel']['values'] == [1., 2.]
    assert b.messages['caster_audit']['values']['caster_left_swivel_joint']['position_rad'] == 1.5
    assert 'caster' not in b.assembler.__dict__
