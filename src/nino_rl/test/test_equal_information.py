"""Causal common-only preview, replay semantics, terminal handling and old ABI rejection."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from nino_rl import equal_information_contract as contract
from nino_rl import residual_equal_information as workflow


def view(**changes):
    return dict(dict(baseline=(.2, 0.), permission=True, sensors_fresh=True,
        fault=False, emergency_stop=False, command_age_s=0.), **changes)


def adapter(stop=6.):
    return contract.PlannedCommonAdapter(contract.configuration(stop)[0], stop)


@pytest.mark.parametrize('stop,expected', [(6., 31), (8., 51)])
def test_same_preview_and_shared_mapping_follow_decision_clock_and_keep_yaw_zero(stop, expected):
    left, right = adapter(stop), adapter(stop)
    active = []
    for i in range(140):
        t = i * .1
        v = view(baseline=(.2 if .5 <= t < stop else 0., 0.))
        base = np.full(100, i / 140, np.float32)
        obs_a, a = left.prepare(base, v, i >= 4)
        obs_b, b = right.prepare(base, v, i >= 4)
        np.testing.assert_array_equal(obs_a, obs_b)
        assert a == b and not a['truth_input']
        assert obs_a.shape == (103,) and obs_a[-3] == np.float32((stop-t)/14.)
        classic = contract.classical_request(obs_a)
        mapped_a, audit_a = left.project(classic)
        mapped_b, audit_b = right.project(classic)
        np.testing.assert_array_equal(mapped_a, mapped_b)
        assert mapped_a[1] == 0. and abs(mapped_a[0]) <= .125
        if a['window_open']:
            active.append(t)
            assert audit_a['windowed_common_m_s'] == .005
        elif t >= stop - .5:
            assert not any(mapped_b)
    assert len(active) == expected and active[-1] == pytest.approx(stop - .6)


@pytest.mark.parametrize('changes,ready,extra', [
    ({'permission': False}, True, {}), ({'sensors_fresh': False}, True, {}),
    ({'fault': True}, True, {}), ({'emergency_stop': True}, True, {}),
    ({'command_age_s': .3}, True, {}), ({'command_age_s': -.1}, True, {}),
    ({'command_age_s': float('nan')}, True, {}), ({}, False, {}),
    ({}, True, {'done': True}), ({}, True, {'latched': True}),
    ({'baseline': (0., 0.)}, True, {})])
def test_nonzero_requested_action_survives_closed_window_in_replay_not_motor_command(changes, ready, extra):
    a = adapter()
    for _ in range(30):
        a.prepare(np.zeros(100), view(), True);a.project([0.])
    obs, preview = a.prepare(np.zeros(100), view(**changes), ready, **extra)
    mapped, trace = a.project([1.])
    assert obs[101] == 0. and not any(mapped)
    assert trace['requested_scalar'] == trace['replay_action'] == [1.]
    assert trace['requested_common_m_s'] == .005 and trace['windowed_common_m_s'] == 0.


def test_prepare_cannot_advance_twice_and_invalid_action_is_not_silently_clipped():
    a = adapter()
    with pytest.raises(RuntimeError, match='Prepare'):
        a.project([0.])
    a.prepare(np.zeros(100), view(), True)
    with pytest.raises(RuntimeError, match='Consume'):
        a.prepare(np.zeros(100), view(), True)
    for wrong in ([0., 0.], [2.], [float('nan')]):
        with pytest.raises(ValueError, match='scalar'):
            a.project(wrong)
    a.project([0.])
    a.reset();obs, trace = a.prepare(np.zeros(100), view(), True)
    assert trace['decision_tick'] == 0 and trace['decision_task_s'] == 0.


def test_privileged_labels_cannot_change_controller_observation_or_mapping():
    a, b = adapter(), adapter()
    altered = view(truth_pose_m_rad=[999, -999, 3], contact_force=1e9, caster_angle=2.)
    for i in range(31):
        x, _ = a.prepare(np.zeros(100), view(), True)
        y, _ = b.prepare(np.zeros(100), altered, True)
        np.testing.assert_array_equal(x, y)
        np.testing.assert_array_equal(a.project([.5])[0], b.project([.5])[0])


def test_old_identity_and_changed_plan_or_action_scale_cannot_load():
    new = contract.identity()
    assert new['observation']['size'] == 103 and new['action']['size'] == 1
    with pytest.raises(ValueError, match='identity mismatch'):
        contract.require_identity(contract.guided.identity())
    altered = deepcopy(new);altered['mapping']['common_bound_m_s'] = .01
    with pytest.raises(ValueError, match='identity mismatch'):
        contract.require_identity(altered)
    for stop in (None, 7., True):
        with pytest.raises(ValueError, match='development'):
            contract.configuration(stop)


def fixture_env(stop=6., backend_class=None):
    c, _, task, condition = contract.configuration(stop)
    backend = workflow.fixture_backend(c, stop)
    if backend_class:
        backend.advance_reference = backend_class(backend.advance_reference)
    return contract.environment(c, backend, task, condition)


def test_request_cost_not_erased_when_window_closed_and_history_resets():
    env = fixture_env()
    try:
        obs, _ = env.reset(seed=1)
        assert obs.shape == (103,) and not env.env.pipeline.history.ready
        obs, reward, term, trunc, info = env.step(np.ones(1, np.float32))
        assert info['controller_proposal'] == [0., 0.] and info['requested_scalar_action'] == [1.]
        assert info['policy_proposal'] == [1.] and list(info['inherited_policy_proposal']) == [0., 0.]
        assert info['abi_sha256'] == env.contract['abi_sha256'] != info['inherited_abi_sha256']
        assert info['reward_terms']['action_size'] < 0 and info['reward_terms']['action_change'] < 0
        assert info['reward_terms']['action_size'] == pytest.approx(-.01 * (.005/.04)**2 * .1)
        assert reward == sum(info['reward_terms'].values()) and not term and not trunc
        env.reset(seed=1)
        assert env.adapter.next_tick == 0 and not env.env.pipeline.history.ready
        assert env.current_observation[101] == 0. and env.current_observation[102] == 0.
    finally:
        env.close()


def test_true_deadline_is_terminal_but_early_time_limit_stays_truncated():
    env = fixture_env()
    try:
        env.reset(seed=1)
        for _ in range(140):
            _, _, term, trunc, info = env.step(np.zeros(1))
        assert term and not trunc and info['task']['task_deadline']
        with pytest.raises(RuntimeError, match='Reset required'):
            env.step(np.zeros(1))
    finally:
        env.close()
    def early(original):
        def wrapped(*args):
            v, labels, term, trunc, info = original(*args)
            return v, labels, term, info['sensor_clock_s'] >= 3.-1e-8, info
        return wrapped
    env = fixture_env(backend_class=early)
    try:
        env.reset(seed=1)
        for _ in range(30):
            obs, _, term, trunc, info = env.step(np.zeros(1))
        assert not term and trunc and not info['task']['task_deadline']
        assert obs[101] == 1. and info['next_plan_preview']['window_open']
    finally:
        env.close()


def test_zero_scalar_head_and_save_load_reject_v3_without_learning(tmp_path):
    import torch
    from stable_baselines3 import TD3
    model = workflow.inspection_model()
    obs = np.ones((8, 103), np.float32)
    assert not np.any(model.predict(obs, deterministic=True)[0])
    with pytest.raises(ValueError, match='fresh'):
        workflow.zero_initialize_scalar(model)
    model.save(tmp_path / 'inspection.zip')
    loaded = TD3.load(tmp_path / 'inspection.zip', device='cpu')
    contract.require_identity(loaded.nino_equal_information_identity)
    for name in ('actor', 'actor_target', 'critic', 'critic_target'):
        for a, b in zip(getattr(model, name).parameters(), getattr(loaded, name).parameters()):
            assert torch.equal(a, b)
    assert loaded.num_timesteps == loaded._n_updates == 0
    assert not loaded.actor.optimizer.state and not loaded.critic.optimizer.state


def test_qualification_never_calls_learning_and_keeps_requested_replay(tmp_path, monkeypatch):
    from stable_baselines3 import TD3
    import torch
    def forbidden(*args, **kwargs):
        raise AssertionError('No optimizer or learner step in offline qualification')
    monkeypatch.setattr(TD3, 'learn', forbidden)
    monkeypatch.setattr(torch.optim.Adam, 'step', forbidden)
    monkeypatch.setattr(workflow, 'parent', lambda: tmp_path)
    monkeypatch.setattr(contract.guided, 'dependency_record', lambda p: {})
    result = workflow.qualify(tmp_path)
    assert result['synthetic_fixture_transitions'] == 840 and result['replay']['rows_checked'] == 280
    assert result['optimizer_updates'] == result['training_transitions'] == result['physics_steps'] == 0
    assert not result['training_released'] and not result['benefit_verified']
    assert (tmp_path / 'qualification.json').is_file()


def test_consumed_offline_ledger_cannot_reopen(tmp_path):
    (tmp_path / 'state.json').write_text('{}')
    with pytest.raises(ValueError, match='already consumed'):
        workflow.run(tmp_path)


def test_previous_requested_action_is_observed_even_when_shared_window_blocks_it():
    env = fixture_env()
    try:
        obs, _ = env.reset(seed=1)
        assert obs[102] == 0.
        next_obs, _, _, _, info = env.step(np.array([1.], np.float32))
        assert info['controller_proposal'] == [0., 0.]
        assert next_obs[101] == 0. and next_obs[102] == 1.
        assert info['equal_observation'][102] == 0. and info['equal_next_observation'][102] == 1.
        assert info['next_plan_preview']['current_features'][2] == 1.
    finally:
        env.close()


@pytest.mark.parametrize('motion_start', [.5, .6])
def test_window_matches_legacy_rule_on_the_same_received_reference(motion_start):
    from nino_rl import residual_classical_common as legacy
    c = contract.configuration(6.)[0]
    new = adapter()
    p = dict(contract.protocol(), withdraw_at_task_s=5.5, planned_source_stop_s=6.,
             residual_scale_m_s=.04, common_compensation_m_s=.005)
    old = legacy.ClassicalCommonProfile(c, p)
    for i in range(140):
        v = view(baseline=(.2 if motion_start <= i*.1 < 6. else 0., 0.))
        obs, preview = new.prepare(np.zeros(100), v, i >= 4)
        mapped, audit = new.project(contract.classical_request(obs))
        expected, old_audit = old.proposal(i*.1, v, i >= 4)
        np.testing.assert_array_equal(mapped, expected)
        np.testing.assert_allclose(preview['nominal_shaped_body'], old_audit['nominal_shaped_body'])
