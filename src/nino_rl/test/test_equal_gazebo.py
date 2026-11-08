"""New Gazebo runner gates exercised without launching Gazebo or an optimizer."""
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from nino_rl import residual_equal_gazebo as job
from nino_rl import residual_equal_information as offline


def row_fixture():
    condition = dict(arm='Proposal_probe', source_stop_s=6.)
    c, _, task, backend_condition = job.configuration(condition)
    env = job.contract.environment(c, offline.fixture_backend(c, 6.), task, backend_condition)
    try:
        env.reset(seed=1)
        _, reward, term, trunc, info = env.step(np.array([1.], np.float32))
        return dict(step=0, reward=reward, terminated=term, truncated=trunc, **info,
                    truth_used_for_guidance=False, qualification_condition=condition)
    finally:
        env.close()


def test_registered_order_budget_and_config_source_task_clock_agree():
    p = job.protocol()
    assert len(p['order']) == 4 and p['maximum_transitions'] == 560
    assert p['training_transitions'] == p['optimizer_updates'] == p['actor_inference_calls'] == p['hardware_actions'] == 0
    for condition in p['order']:
        c, _, task, _ = job.configuration(condition)
        assert c['backend']['command_until_s'] == c['task']['command_until_s'] == task['command_until_s'] == condition['source_stop_s']
        assert c['backend']['horizon_s'] == task['horizon_s'] == 14.
    with pytest.raises(ValueError, match='Unregistered'):
        job.configuration(dict(arm='TD3', source_stop_s=6.))


def test_scalar_request_mapping_and_probe_do_not_load_an_actor():
    obs = np.zeros(103, np.float32);obs[101] = 1.
    assert job.request('B0', obs, 0).tolist() == [0.]
    assert job.request('Classical_scheduled', obs, 0).tolist() == [1.]
    assert [job.request('Proposal_probe', obs, i).item() for i in range(6)] == [-1., 0., 1., -1., 0., 1.]
    with pytest.raises(ValueError, match='Unknown'):
        job.request('TD3', obs, 0)


def test_valid_transition_keeps_requested_action_when_shared_window_closed():
    r = row_fixture()
    job.verify_transition(r, None, r['sensor_clock_s'] - .1, job.protocol()['abi_sha256'])
    assert r['requested_scalar_action'] == [1.] and r['controller_proposal'] == [0., 0.]


@pytest.mark.parametrize('field,value', [
    ('abi_sha256', 'old_100D_ABI'), ('controller_proposal', [0., .1]),
    ('policy_proposal', [0., 0.]), ('truth_used_for_guidance', True)])
def test_malformed_abi_mapping_or_privilege_fails_before_next_tick(field, value):
    r = row_fixture();r[field] = value
    with pytest.raises((ValueError, AssertionError)):
        job.verify_transition(r, None, r['sensor_clock_s'] - .1, job.protocol()['abi_sha256'])


def test_plan_clock_mismatch_and_previous_requested_action_cannot_be_hidden():
    r = row_fixture();epoch = r['sensor_clock_s'] - .1
    broken = deepcopy(r);broken['plan_projection']['decision_task_s'] = .1
    with pytest.raises(ValueError, match='clock'):
        job.verify_transition(broken, None, epoch, job.protocol()['abi_sha256'])
    broken = deepcopy(r);broken['equal_observation'][102] = 1.
    with pytest.raises(ValueError, match='causal'):
        job.verify_transition(broken, None, epoch, job.protocol()['abi_sha256'])


@pytest.mark.parametrize('kind', ['physical', 'measurement'])
def test_failure_preserves_progress_and_closes_unlaunched_slots(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(job, 'parent', lambda: tmp_path)
    monkeypatch.setattr(job.contract.guided, 'dependency_record', lambda p: {})
    monkeypatch.setattr(job, 'prepare_worlds', lambda p: dict(clear_box='world'))
    calls = []
    def rollout(*args):
        calls.append(1)
        return dict(physical_failure=kind == 'physical', guidance_faults=0, steps=140,
                    integration_pass=False, replay_rows_checked=140)
    monkeypatch.setattr(job, 'rollout', rollout)
    if kind == 'physical':
        with pytest.raises(RuntimeError, match='no retry'):
            job.evaluate(tmp_path)
    else:
        result = job.evaluate(tmp_path)
        assert not result['qualification_pass'] and result['evaluation_transitions'] == 140
        assert result['closed_reason']
    assert len(calls) == 1 and (tmp_path / 'qualification_progress.json').is_file()


def test_consumed_budget_cannot_reopen_even_with_corrupt_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path / 'home'))
    (tmp_path / 'state.json').write_text('broken')
    with pytest.raises(ValueError, match='already consumed'):
        job.run(tmp_path)


def test_small_follower_yaw_can_delay_nominal_steady_without_delaying_source():
    c = job.configuration(dict(arm='B0', source_stop_s=6.))[0]
    profiles = [job.contract.PlannedCommonAdapter(c, 6.), job.contract.PlannedCommonAdapter(c, 6.)]
    opened = [[], []];nominal_at_24 = []
    for i in range(30):
        for k, yaw in enumerate([0., .0001]):
            view = dict(baseline=(.2, yaw) if i >= 5 else (0., 0.), permission=True,
                        sensors_fresh=True, fault=False, emergency_stop=False, command_age_s=0.)
            _, audit = profiles[k].prepare(np.zeros(100), view, True)
            if audit['window_open']:opened[k].append(i*.1)
            if i == 24:nominal_at_24.append(audit['nominal_shaped_body'][0])
            profiles[k].project([0.])
    assert opened[0][0] == pytest.approx(2.4) and opened[1][0] == pytest.approx(2.5)
    assert nominal_at_24[0] == pytest.approx(.2) and nominal_at_24[1] < .2 - 1e-8
