from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pickle
import random

import numpy as np
import pytest

from nino_rl import recovery_runner as runner
from nino_rl import recovery_training as training
from nino_rl.recovery_training import RecoveryBankEnv
from nino_rl.recovery_bank import configuration
from nino_rl.recovery_training_contract import (CHECKPOINT_KIND, QualifiedRecoveryBank,
    RecoverySmokeRequest, inspect_recovery_checkpoint, require_live_qualification, sha)
from nino_rl.residual_workflow import save


def request(tmp_path, families=('clean', 'slope')):
    return RecoverySmokeRequest.parse(dict(prepared_root=str(tmp_path/'prepared'),
                                           families=list(families)))


def qualified(tmp_path, families=('clean', 'slope')):
    layouts = []
    for family in families:
        world = tmp_path/(family+'.sdf')
        world.write_text('<sdf/>')
        layouts.append(dict(family=family, stage=0, split='development', seed=1511,
            id=family+'_s0', world=str(world), world_sha256=sha(world),
            initial_pose_xy_yaw=[0., 0., 0.], task_settings={}, obstacles=[]))
    return QualifiedRecoveryBank(tmp_path/'prepared',
        dict(config=configuration(), envelope={}, layouts=layouts), 'bank', 'pins',
        {(family, 0): {} for family in families})


class FakeLifecycle:
    def __init__(self, out, *, terminal_at=None, truncate_at=None, fail_reset=None,
                 fail_step=None, fail_close=False):
        self.out, self.index, self.current = out, -1, None
        self.events, self.terminal_at = [], terminal_at
        self.truncate_at = truncate_at
        self.fail_reset, self.fail_step, self.fail_close = fail_reset, fail_step, fail_close
        self.closed = False

    def _close_current(self):
        if self.current is not None:
            self.events.append(('close', self.index))
            self.current = None
            if self.fail_close:
                self.fail_close = False
                raise RuntimeError('fixture closure failure')

    def reset(self, seed=None):
        assert self.current is None
        self.index += 1
        self.events.append(('launch', self.index))
        (self.out/'episodes'/f'episode_{self.index}').mkdir(parents=True)
        if self.fail_reset == self.index:
            raise RuntimeError('fixture launch failure')
        self.current = object()
        return np.zeros(100, np.float32), dict(physical_sample=dict(stamp_s=0.))

    def close(self):
        self._close_current()
        self.closed = True


class FakeInner:
    def __init__(self, config, layout, envelope, backend, controller):
        self.backend, self.identity = backend, dict(layout=layout['id'])

    def reset(self, seed=None):
        observation, info = self.backend.reset(seed)
        self.n, self.observation = 0, observation
        return observation, info

    def step(self, action):
        self.n += 1
        if self.backend.fail_step == (self.backend.index, self.n):
            raise RuntimeError('fixture source failure before reward')
        previous = self.observation.copy()
        self.observation = np.full(100, self.backend.index*.1+self.n*.001, np.float32)
        term = self.backend.terminal_at == self.n
        trunc = self.backend.truncate_at == self.n
        outcome = dict(measurement_valid=True, task_success=False, terminated=term,
                       truncated=trunc, right_censored=trunc, motion_quality_pass=False,
                       all_obstacles_recovered=False, termination_reason='physical_failure' if term
                       else 'external_cutoff' if trunc else None)
        scalar = float(action[0])
        return self.observation.copy(), 1., term, trunc, dict(task=outcome,
            observation=previous.tolist(), next_observation=self.observation.tolist(),
            requested_scalar_action=scalar, replay_action=[scalar],
            physical_sample=dict(stamp_s=self.n*.1))


def fixture_qc(out):
    resets = list(Path(out).glob('episode_*_reset.json'))
    return dict(valid=bool(resets), episodes={p.name[:-11]: dict(valid=True) for p in resets})


def make_env(out, req, bank, **faults):
    out.mkdir(exist_ok=True)
    backend = FakeLifecycle(out, **faults)
    env = RecoveryBankEnv(out, req, bank, lifecycle=backend,
        environment_factory=FakeInner, qc=fixture_qc)
    return env, backend


@pytest.mark.parametrize('change', [dict(transitions=True), dict(transitions=385),
    dict(maximum_launches=5), dict(episode_transition_limit=129), dict(seed=True),
    dict(wall_seconds=float('nan')), dict(profile='nino_td3_research_h5_v1'),
    dict(families=['clean', 'clean']), dict(families=['unknown']), dict(automatic_retries=1)])
def test_request_rejects_budget_and_domain_changes(tmp_path, change):
    raw = dict(prepared_root=str(tmp_path), families=['clean'])
    raw.update(change)
    with pytest.raises(ValueError):
        RecoverySmokeRequest.parse(raw)


def test_admin_censor_round_robin_closes_and_never_promotes(tmp_path):
    req = replace(request(tmp_path), transitions=4, episode_transition_limit=2)
    env, backend = make_env(tmp_path/'job', req, qualified(tmp_path))
    for episode, family in enumerate(('clean', 'slope')):
        obs, info = env.reset()
        assert info['recovery_assignment']['family'] == family
        for step in range(2):
            obs, _, term, trunc, info = env.step(np.array([.7], np.float32))
            assert term is False
            assert trunc is (step == 1)
        np.testing.assert_array_equal(obs, np.full(100, episode*.1+.002, np.float32))
        assert info['task']['right_censored'] is True
        assert info['task']['task_success'] is False
        assert info['TimeLimit.truncated'] is True
        with pytest.raises(RuntimeError):
            env.reset()
        env.finish_stored_episode()
    assert env.state()['cursor'] == 2
    assert len(env.censored) == 2 and not env.completed
    assert all(c.total == 0 and c.stage == 0 for c in env.curricula.values())
    with pytest.raises(ValueError, match='budget'):
        env.reset()
    env.close()
    assert backend.events == [('launch', 0), ('close', 0), ('launch', 1), ('close', 1)]


def test_unqualified_stage_blocks_before_a_launch(tmp_path):
    req = request(tmp_path)
    env, backend = make_env(tmp_path/'job', req, qualified(tmp_path))
    env.curricula['clean'].stage = 1
    env.curricula['clean'].settings['earlier_stage_probability'] = 0.
    with pytest.raises(ValueError, match='Unqualified'):
        env.reset()
    assert backend.events == [] and env.launch_attempts == 0


def test_external_censor_is_not_a_curriculum_failure(tmp_path):
    req = request(tmp_path)
    env, _ = make_env(tmp_path/'job', req, qualified(tmp_path), truncate_at=1)
    env.reset()
    _, _, term, trunc, info = env.step(np.array([0.], np.float32))
    assert trunc is True and term is False and info['task']['right_censored'] is True
    env.finish_stored_episode()
    assert len(env.censored) == 1 and env.curricula['clean'].total == 0
    env.close()


def prepare_baseline(tmp_path, monkeypatch):
    req = request(tmp_path, ('clean',))
    bank = qualified(tmp_path, ('clean',))
    inputs = req.prepared_root/'inputs'
    inputs.mkdir(parents=True)
    save(inputs/'bank.json', bank.bank)
    save(inputs/'source_pins.json', dict(current=True))
    root = req.prepared_root/'baseline_clean_s0'
    raw = root/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    raw.parent.mkdir(parents=True)
    raw.write_text(''.join(json.dumps(dict(channel=channel, stamp_s=n*.01))+'\n'
        for n in range(11) for channel in ('imu', 'wheel', 'truth', 'drive')))
    layout = bank.bank['layouts'][0]
    save(root/'episode_0_reset.json', dict(reset=dict(physical_sample=dict(stamp_s=0.)),
                                         private_layout=layout))
    (root/'environment_trace.jsonl').write_text(json.dumps(dict(episode=0,
        physical_sample=dict(stamp_s=.1)))+'\n')
    qc = runner.raw_qc(root)
    save(root/'job.json', dict(status='completed', action='baseline', family='clean', stage=0,
                              source_pins=dict(current=True)))
    save(root/'result.json', dict(family='clean', stage=0, classical_baseline_only=True,
        optimizer_updates=0, physical_gate_pass=True, bank_sha256=sha(inputs/'bank.json'),
        world_sha256=layout['world_sha256'], layout_id=layout['id'], source_qc=qc,
        outcome=dict(measurement_valid=True, task_success=True, motion_quality_pass=True,
                     all_obstacles_recovered=True, terminated=True, truncated=False)))
    def manifest():
        save(root/'manifest.json', {str(p.relative_to(root)): sha(p) for p in root.rglob('*')
                                   if p.is_file() and p.name != 'manifest.json'})
    manifest()
    monkeypatch.setattr(runner, 'require_bank', lambda _: bank.bank)
    monkeypatch.setattr(runner, 'sources', lambda: dict(current=True))
    return req, root, manifest


@pytest.mark.parametrize('fault', ['missing', 'changed', 'bank', 'world', 'motion', 'raw'])
def test_unqualified_baseline_never_constructs_a_model_or_launch(tmp_path, monkeypatch, fault):
    req, root, manifest = prepare_baseline(tmp_path, monkeypatch)
    assert require_live_qualification(req).layout('clean', 0)['id'] == 'clean_s0'
    if fault == 'missing':
        (root/'manifest.json').unlink()
    elif fault == 'changed':
        (root/'result.json').write_text('{}')
    elif fault == 'raw':
        raw = root/'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
        raw.write_text(raw.read_text()+json.dumps(dict(channel='wheel', stamp_s=.1))+'\n')
        manifest()
    else:
        result = json.loads((root/'result.json').read_text())
        if fault in ('bank', 'world'):
            result[fault+'_sha256'] = 'different'
        else:
            result['outcome']['motion_quality_pass'] = False
        save(root/'result.json', result)
        manifest()
    monkeypatch.setattr(training, '_learn', lambda *_: pytest.fail('Unqualified learner started'))
    with pytest.raises((ValueError, OSError)):
        training.run_live_smoke(tmp_path/'should_not_exist', req)
    assert not (tmp_path/'should_not_exist').exists()


def run_fixture_optimizer(tmp_path, monkeypatch, *, cap=128, **faults):
    req = replace(request(tmp_path), episode_transition_limit=cap)
    bank = qualified(tmp_path)
    out = tmp_path/'learn'
    out.mkdir()
    env, backend = make_env(out, req, bank, **faults)
    monkeypatch.setattr(training, 'RecoveryBankEnv', lambda *_: env)
    identity = dict(checkpoint_kind=CHECKPOINT_KIND, test_fixture=True)
    return req, env, backend, identity, out


def test_td3_stores_384_requested_actions_and_three_terminal_observations(tmp_path, monkeypatch):
    req, env, backend, identity, out = run_fixture_optimizer(tmp_path, monkeypatch)
    result = training._learn(out, req, env.qualified, identity)
    assert result['global_transitions'] == result['replay_rows_verified'] == 384
    assert result['launch_attempts'] == 3
    assert result['administrative_censors'] == 3
    assert result['physical_completed_episodes'] == 0
    assert result['actor_updates'] > 0 and result['critic_updates'] > 0
    assert result['actor_parameter_l1_change'] > 0
    assert result['checkpoint_qualified'] is True
    assert backend.events == [('launch', 0), ('close', 0), ('launch', 1), ('close', 1),
                              ('launch', 2), ('close', 2)]
    from stable_baselines3 import TD3
    model = TD3.load(Path(result['checkpoint'])/'model.zip')
    model.load_replay_buffer(Path(result['checkpoint'])/'replay_buffer.pkl')
    replay = model.replay_buffer
    for index, expected in ((127, .128), (255, .228), (383, .328)):
        np.testing.assert_allclose(replay.next_observations[index, 0], expected, atol=1e-7)
        assert bool(replay.dones[index, 0]) and bool(replay.timeouts[index, 0])
    inspected = inspect_recovery_checkpoint(result['checkpoint'], expected_identity=identity,
                                            require_resumable=True)
    assert inspected['state']['cursor'] == 3
    with pytest.raises(ValueError, match='identity'):
        inspect_recovery_checkpoint(result['checkpoint'], expected_identity=dict(identity, changed=True))
    with (Path(result['checkpoint'])/'rng.pkl').open('rb') as stream:
        rng = pickle.load(stream)
    training.restore_rng(model, rng)
    expected = (random.random(), np.random.random(), float(__import__('torch').rand(())))
    resumed, _ = make_env(tmp_path/'resume', req, env.qualified)
    training.restore_checkpoint(model, resumed, inspected)
    assert resumed.state() == {k: v for k, v in inspected['state'].items() if k != 'returned_transitions'}
    assert (random.random(), np.random.random(), float(__import__('torch').rand(()))) == expected
    assert resumed.backend.index == 2 and resumed.launch_attempts == 3
    (Path(result['checkpoint'])/'model.zip').write_bytes(b'changed')
    with pytest.raises(ValueError, match='manifest'):
        inspect_recovery_checkpoint(result['checkpoint'])


def test_physical_failure_consumes_four_launches_without_extra_reset(tmp_path, monkeypatch):
    req, env, backend, identity, out = run_fixture_optimizer(tmp_path, monkeypatch, terminal_at=3)
    result = training._learn(out, req, env.qualified, identity)
    assert result['status'] == 'budget_exhausted'
    assert result['global_transitions'] == 12 and result['launch_attempts'] == 4
    assert result['physical_completed_episodes'] == 4 and result['administrative_censors'] == 0
    assert sum(c.total for c in env.curricula.values()) == 4
    assert len([event for event in backend.events if event[0] == 'launch']) == 4
    assert env.last['TimeLimit.truncated'] is False


@pytest.mark.parametrize('faults,prefix,attempts', [
    (dict(fail_reset=1), 2, 2), (dict(fail_step=(0, 2)), 1, 1),
    (dict(fail_close=True), 2, 1)])
def test_failed_attempt_keeps_stored_prefix_and_diagnostic_bundle(tmp_path, monkeypatch,
                                                                faults, prefix, attempts):
    req, env, backend, identity, out = run_fixture_optimizer(tmp_path, monkeypatch, cap=2, **faults)
    with pytest.raises(RuntimeError, match='fixture'):
        training._learn(out, req, env.qualified, identity)
    result = json.loads((out/'result.json').read_text())
    assert result['global_transitions'] == result['replay_rows_verified'] == prefix
    assert result['launch_attempts'] == attempts
    assert result['status'] == 'failed' and result['checkpoint_qualified'] is False
    inspect_recovery_checkpoint(result['checkpoint'], expected_identity=identity)
    with pytest.raises(ValueError, match='Diagnostic'):
        inspect_recovery_checkpoint(result['checkpoint'], require_resumable=True)


def test_manifest_rejects_missing_required_file_and_path_escape(tmp_path):
    from nino_rl.recovery_training_contract import require_manifest
    root = tmp_path/'bundle'
    root.mkdir()
    outside = tmp_path/'outside'
    outside.write_text('secret')
    save(root/'manifest.json', {'../outside': sha(outside)})
    with pytest.raises(ValueError):
        require_manifest(root, ('model.zip',))
    save(root/'manifest.json', {'../outside': sha(outside)})
    with pytest.raises(ValueError):
        require_manifest(root, ())
