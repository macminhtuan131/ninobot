from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from nino_rl import recovery_bank as prior
from nino_rl.recovery_v4_campaign import FixtureLifecycle
from nino_rl.recovery_v4_campaign_contract import CampaignRequest, algorithm
from nino_rl.recovery_v4_runtime import make_environment, runtime_configuration
from nino_rl.recovery_v4_environment import governor_action
from nino_rl.recovery_v4_bank import sample_layout
from nino_rl.unknown_step_runtime import UnknownTaskData


def fixture():
    from test_unknown_step_runtime import settings
    config = prior.configuration()
    layout = prior.sample_layout(config, 'clean', 1511, 0)
    from dataclasses import asdict
    layout['initial_pose_xy_yaw'] = [0.,0.,0.]
    layout['task_settings'] = asdict(settings(route_m=((0.,0.),(4.,0.)),
        obstacle_near_m=None, obstacle_far_m=None, maximum_seconds=40., continuous_stop_s=2.))
    c, *_ = runtime_configuration(config, layout)
    backend = FixtureLifecycle(c)
    return make_environment(config, layout, {}, backend), backend


def test_real_history_precedes_first_replay_and_action_is_slowdown():
    env, backend = fixture()
    obs, info = env.reset(seed=1)
    assert obs.shape == (107,) and info['warmup']['real_frames'] == 5
    assert info['warmup']['replay_rows'] == 0 and backend.t == pytest.approx(.4)
    assert len(set(r['stamp_s'] for r in info['warmup']['source_frames'])) == 5
    next_obs, reward, term, trunc, row = env.step([-1.])
    assert row['reference_trace']['requested_slowdown_m_s'] == 0
    np.testing.assert_array_equal(row['observation'], obs)
    np.testing.assert_array_equal(row['next_observation'], next_obs)
    assert reward == pytest.approx(sum(row['reward_terms'].values()))
    assert row['truth_used_for_guidance'] is False
    assert not term and not trunc
    for _ in range(30):
        _, _, term, _, row = env.step([1.])
        assert row['reference_trace']['accepted_slowdown_m_s'] <= .02
        assert row['reference_trace']['body_reference'][0] <= row['reference_trace']['nominal_body_reference'][0]+1e-12
        if term:
            break
    env.close()


def test_invalid_sensor_fails_before_a_transition_is_returned():
    env, backend = fixture()
    env.reset()
    env.adapter.view['features']['imu_age_s'] = .5
    with pytest.raises(UnknownTaskData):
        env.step([-1.])
    assert env.closed and backend.v == 0


@pytest.mark.parametrize('field', ['imu_age_s', 'wheel_age_s', 'command_age_s'])
def test_incoming_stale_observation_cannot_enter_replay_or_finish_warmup(field):
    env, backend = fixture()
    env.reset()
    advance = backend.advance_reference
    def stale(*args):
        view, labels, term, trunc, info = advance(*args)
        if field == 'command_age_s':
            view[field] = .5
        else:
            view['features'][field] = .5
        return view, labels, term, trunc, info
    backend.advance_reference = stale
    with pytest.raises(UnknownTaskData, match='Incoming'):
        env.step([-1.])
    assert env.closed


def test_fifth_stale_reset_frame_cannot_become_an_initial_actor_tensor():
    env, backend = fixture()
    advance = backend.advance_reference
    def stale_fifth(*args):
        view, labels, term, trunc, info = advance(*args)
        if backend.t >= .4:
            view['features']['imu_age_s'] = .5
        return view, labels, term, trunc, info
    backend.advance_reference = stale_fifth
    with pytest.raises(UnknownTaskData, match='Incoming'):
        env.reset()
    assert env.closed and env.current_observation is None


def test_v4_budget_and_fixture_identity_are_distinct(tmp_path):
    request = CampaignRequest.parse(dict(prepared_root=str(tmp_path)))
    assert request.transitions == 200000 and request.wall_seconds == 345600
    assert algorithm(request)['buffer_size'] == 200000
    assert CampaignRequest.parse(request.state()) == request
    with pytest.raises(ValueError):
        CampaignRequest.parse(dict(prepared_root=str(tmp_path), learning_starts=32))
    with pytest.raises(ValueError):
        CampaignRequest.parse(dict(prepared_root=str(tmp_path), checkpoint_keep=2))


def test_bank_schedule_is_reproducible_and_cannot_leak_heldout():
    bank = dict(layouts=[dict(id=f'{split}_{n}',family='clean',split=split) for split in
        ('train','tune','heldout') for n in range(8)])
    a = [sample_layout(bank,'clean','train',1511,n)['id'] for n in range(16)]
    b = [sample_layout(bank,'clean','train',1511,n)['id'] for n in range(16)]
    assert a == b and len(set(a[:8])) == 8
    assert all(r.startswith('train') for r in a)
    assert set(a[:8]) == set(a[8:])


def test_frozen_governor_uses_deployable_history_only():
    env, _ = fixture()
    obs, _ = env.reset()
    assert governor_action(obs).tolist() == [-1.]
    disturbed = obs.copy()
    disturbed[86] = .2
    assert governor_action(disturbed).tolist() == [1.]
    env.close()
