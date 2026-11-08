"""Fresh learner orchestration tested offline; no extra Gazebo launches."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest
from nino_rl import residual_common_td3 as job
from nino_rl import residual_equal_information as offline


def test_fixed_release_budget_does_not_mutate_historical_parent():
    p = job.protocol()
    assert p['training_transitions_maximum'] + p['evaluation_transitions_maximum'] == 4472
    assert p['maximum_gazebo_launches'] == 3 * 8 + 10
    assert p['training_released_for_this_pilot_only'] and not p['resume_allowed']
    assert not job.contract.identity()['training_released']
    assert job.identity()['observation_size'] == 103 and job.identity()['action_size'] == 1
    assert p['minimum_effect_accepted'] is None
    with pytest.raises(ValueError, match='identity mismatch'):
        job.require_identity(job.contract.identity())


def test_episode_stop_changes_all_source_task_and_preview_configs_together():
    backend = SimpleNamespace()
    stops = []
    for episode in range(8):
        c, task, condition, stop = job.configure_episode(backend, episode)
        stops.append(stop)
        assert c['backend']['max_episodes'] == 8
        assert c['backend']['command_until_s'] == c['task']['command_until_s'] == task['command_until_s'] == stop
        assert backend.protocol == task and backend.config == c and backend.condition == condition
        backend.protocol['command_until_s'] = -1
        assert task['command_until_s'] == stop  # independent copies
    assert stops == [6., 8.] * 4
    with pytest.raises(ValueError, match='budget exhausted'):
        job.configure_episode(backend, 8)


def valid_row():
    return dict(reward=0., equal_observation=[0.] * 103, equal_next_observation=[0.] * 103,
                task=dict(cross_track_m=0., estimator_position_error_m=0., estimator_yaw_error_rad=0., task_success=True),
                guidance_audit=dict(fault=False), truth_used_for_guidance=False, source_lags_s=dict(imu=.02, wheel=.002),
                terminated=False, truncated=False)


@pytest.mark.parametrize('kind', ['stale', 'bounds', 'fault', 'terminal', 'truncated', 'nan'])
def test_failure_gate_rejects_before_auto_reset(kind):
    row = valid_row()
    if kind == 'stale':row['source_lags_s']['imu'] = .041
    if kind == 'bounds':row['task']['cross_track_m'] = .041
    if kind == 'fault':row['guidance_audit']['fault'] = True
    if kind == 'terminal':row.update(terminated=True);row['task']['task_success'] = False
    if kind == 'truncated':row['truncated'] = True
    if kind == 'nan':row['equal_next_observation'][2] = float('nan')
    with pytest.raises(ValueError):job.feasibility(row)
    job.feasibility(valid_row())


def test_fresh_model_103_scalar_and_offline_checkpoint_replay(tmp_path):
    # No optimizer/physics: verify model construction against real wrapper ABI,
    # replay semantics and full checkpoint round-trip using software fixture.
    import torch
    torch.set_num_threads(1)
    c, _, task, condition = job.configuration(6.)
    env = job.contract.environment(c, offline.fixture_backend(c, 6.), task, condition)
    model = job.build_model(env, 11)
    offline.zero_initialize_scalar(model)
    model.nino_common_identity = job.identity()
    obs, _ = env.reset(seed=11)
    rows = []
    try:
        for i, request in enumerate([.5, -.8, 1.]):
            action = np.array([request], np.float32)
            nxt, reward, term, trunc, info = env.step(action)
            row = dict(done=bool(term or trunc), **info)
            row['TimeLimit.truncated'] = bool(trunc and not term)
            model.replay_buffer.add(obs, nxt, action, np.array([reward]), np.array([term or trunc]), [row])
            rows.append(dict(row, reward=reward))
            obs = nxt
        assert model.observation_space.shape == (103,) and model.action_space.shape == (1,)
        np.testing.assert_array_equal(model.predict(obs, deterministic=True)[0], [0.])
        result = job.checkpoint_check(model, tmp_path, rows)
        assert result['replay']['rows_checked'] == 3
        assert result['model_optimizer_target_replay_parity'] and not result['physics_restore']
        assert model.num_timesteps == model._n_updates == 0
    finally:env.close()


def test_stage_failure_closes_unstarted_seeds_and_evaluations(tmp_path, monkeypatch):
    monkeypatch.setattr(job, 'parent', lambda: tmp_path)
    monkeypatch.setattr(job.contract.guided, 'dependency_record', lambda p: {})
    monkeypatch.setattr(job, 'prepare_worlds', lambda p: dict(clear_box='world'))
    called = []
    def fail(*args):
        called.append(args[1])
        raise ValueError('retained failure')
    monkeypatch.setattr(job, 'train_seed', fail)
    monkeypatch.setattr(job, 'evaluate_rollout', lambda *args: pytest.fail('Evaluation after training failure'))
    with pytest.raises(ValueError, match='retained failure'):job.execute(tmp_path)
    assert called == [11]


def test_consumed_even_corrupt_ledger_cannot_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path / 'home'))
    (tmp_path / 'state.json').write_text('broken')
    with pytest.raises(ValueError, match='already consumed'):job.run(tmp_path)


def test_alternating_wrapper_reset_exposes_real_103_plan_without_hidden_steps(tmp_path, monkeypatch):
    original = job.contract.environment
    def fixture(c, backend, task, condition):
        return original(c, offline.fixture_backend(c, task['command_until_s']), task, condition)
    monkeypatch.setattr(job.contract, 'environment', fixture)
    backend = SimpleNamespace(close=lambda: None)
    env = job.alternating_environment(backend, tmp_path, 11)
    for episode in range(8):
        obs, _ = env.reset(seed=11 if episode == 0 else None)
        assert obs.shape == (103,) and obs[100] == pytest.approx([6.,8.][episode%2]/14.)
        assert obs[102] == 0. and not env.rows
        assert env.inner.steps == 0 and len(env.resets) == episode + 1
    with pytest.raises(ValueError, match='budget exhausted'):env.reset()
    assert len(json.loads((tmp_path/'resets.json').read_text())) == 8
    env.close()
