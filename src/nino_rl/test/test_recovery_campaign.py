from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from nino_rl import recovery_campaign as campaign
from nino_rl import recovery_runner as runner
from nino_rl.recovery_campaign_contract import (CAMPAIGN_KIND, CHECKPOINT_KIND,
    CampaignRequest, ReadyBank, algorithm, inspect_checkpoint)
from nino_rl.recovery_curriculum import FAMILIES
from nino_rl.residual_workflow import save
from test_recovery_training import FakeInner, FakeLifecycle, qualified


def request(tmp_path, **changes):
    return CampaignRequest.parse(dict(prepared_root=str(tmp_path/'prepared'),
        transitions=1200, checkpoint_every=400, **changes))


def identity(req):
    plan = req.state()
    plan.pop('resume')
    return dict(kind=CAMPAIGN_KIND,checkpoint_kind=CHECKPOINT_KIND,request=plan,
                profile=algorithm(req),source_pins=dict(fixture=True))


class PhysicalFixture(FakeInner):
    def step(self, action):
        observation,reward,term,trunc,info = super().step(action)
        if term:
            info['task']['termination_reason'] = 'stall'
        return observation,reward,term,trunc,info


def fixture(tmp_path, req, monkeypatch, name, **faults):
    out = tmp_path/name
    out.mkdir()
    bank = qualified(tmp_path,FAMILIES)
    ready = ReadyBank(bank.root,bank.bank,tmp_path/'readiness',dict.fromkeys(FAMILIES,{}))
    backend = FakeLifecycle(out,**faults)
    env = campaign.CampaignEnv(out,req,ready,lifecycle=backend,
        environment_factory=PhysicalFixture,
        episode_qc=lambda episode:dict(valid=True,episodes={episode:dict(valid=True)}))
    monkeypatch.setattr(runner,'sources',lambda:dict(fixture=True))
    return out,env,backend,ready


def test_default_campaign_is_bounded_full_episode_research_not_smoke(tmp_path):
    req = CampaignRequest.parse(dict(prepared_root=str(tmp_path)))
    assert (req.transitions,req.episode_transition_limit,req.checkpoint_every) == (20000,400,5000)
    assert req.wall_seconds == 86400 and req.minimum_free_bytes == 2**31
    assert req.families == FAMILIES
    assert algorithm(req)['learning_starts'] == 1000
    assert algorithm(req)['buffer_size'] == 20000
    assert CampaignRequest.parse(req.state()) == req
    with pytest.raises(ValueError,match='retention'):
        CampaignRequest.parse(dict(prepared_root=str(tmp_path),transitions=100000,
                                   maximum_launches=300,checkpoint_keep=6))


@pytest.mark.parametrize('change',[dict(transitions=640),dict(transitions=100001),
    dict(transitions=True),dict(episode_transition_limit=128),dict(schema_version=2),
    dict(profile='nino_td3_smoke_h5_v1'),dict(maximum_launches=4),
    dict(wall_seconds=180000),dict(minimum_free_bytes=2**30),dict(raw_retention_bytes=1),
    dict(checkpoint_keep=1),dict(unknown=True)])
def test_campaign_rejects_open_or_incompatible_limits(tmp_path,change):
    with pytest.raises(ValueError):
        CampaignRequest.parse(dict(prepared_root=str(tmp_path),**change))


def test_campaign_keeps_full_400_step_episodes_and_stops_exactly_at_budget(tmp_path,monkeypatch):
    req = request(tmp_path)
    out,env,backend,ready = fixture(tmp_path,req,monkeypatch,'full')
    result = campaign.train(out,req,ready,identity(req),env=env)
    assert result['status'] == 'completed'
    assert result['global_transitions'] == result['replay_rows_verified'] == 1200
    assert result['launch_attempts'] == 3
    assert len(env.censored) == 3 and not env.completed
    assert result['critic_updates'] == 200 and result['actor_updates'] == 100
    assert result['learned_benefit_verified'] is False
    assert [r['family'] for r in env.assignments] == list(FAMILIES[:3])
    assert all(c.stage == 0 for c in env.curricula.values())
    assert backend.events[-1] == ('close',2)
    checkpoint = inspect_checkpoint(result['checkpoint'],expected_identity=identity(req))
    assert checkpoint['checkpoint']['optimizer_boundary'] is True
    assert checkpoint['checkpoint']['critic_updates'] == 200
    assert len(list((out/'checkpoints').glob('step_*'))) <= req.checkpoint_keep
    progress = json.loads((out/'progress.json').read_text())
    assert progress['global_steps'] == 1200 and progress['actor_updates'] == 100
    assert list((out/'tensorboard').rglob('events.out.tfevents.*'))


def load_model(path):
    from stable_baselines3 import TD3
    model = TD3.load(Path(path)/'model.zip')
    model.load_replay_buffer(Path(path)/'replay_buffer.pkl')
    return model


def assert_tensor_state_equal(a,b):
    import torch
    if isinstance(a,torch.Tensor):
        assert torch.equal(a,b)
    elif isinstance(a,dict):
        assert a.keys() == b.keys()
        for key in a:
            assert_tensor_state_equal(a[key],b[key])
    elif isinstance(a,(list,tuple)):
        assert len(a) == len(b)
        for x,y in zip(a,b):
            assert_tensor_state_equal(x,y)
    else:
        assert a == b


def test_resume_after_optimizer_boundary_matches_uninterrupted_model_replay_and_rng(tmp_path,monkeypatch):
    req = request(tmp_path)
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'continuous',terminal_at=40)
    continuous = campaign.train(out,req,ready,identity(req),env=env)
    a = load_model(continuous['checkpoint'])
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'part',terminal_at=40)
    part = campaign.train(out,req,ready,identity(req),env=env,stop_after=1040)
    assert part['status'] == 'paused' and part['global_transitions'] == 1040
    assert part['critic_updates'] == 40
    continued = replace(req,resume=Path(part['checkpoint']))
    out,env,backend,ready = fixture(tmp_path,continued,monkeypatch,'resume',terminal_at=40)
    resumed = campaign.train(out,continued,ready,identity(req),env=env)
    b = load_model(resumed['checkpoint'])
    assert resumed['global_transitions'] == 1200
    assert resumed['critic_updates'] == 200 and resumed['actor_updates'] == 100
    assert backend.events[0] == ('launch',26)
    assert_tensor_state_equal(a.policy.state_dict(),b.policy.state_dict())
    assert_tensor_state_equal(a.actor.optimizer.state_dict(),b.actor.optimizer.state_dict())
    assert_tensor_state_equal(a.critic.optimizer.state_dict(),b.critic.optimizer.state_dict())
    for name in ('observations','next_observations','actions','rewards','dones','timeouts'):
        np.testing.assert_array_equal(getattr(a.replay_buffer,name),getattr(b.replay_buffer,name))
    with (Path(continuous['checkpoint'])/'rng.pkl').open('rb') as stream:
        rng_a = __import__('pickle').load(stream)
    with (Path(resumed['checkpoint'])/'rng.pkl').open('rb') as stream:
        rng_b = __import__('pickle').load(stream)
    assert_tensor_state_equal(rng_a['torch'],rng_b['torch'])
    assert rng_a['python'] == rng_b['python']
    np.testing.assert_array_equal(rng_a['numpy'][1],rng_b['numpy'][1])
    assert rng_a['action_space'] == rng_b['action_space']


def test_stop_file_waits_for_stored_terminal_and_does_not_skip_optimizer_update(tmp_path,monkeypatch):
    req = request(tmp_path)
    out,env,backend,ready = fixture(tmp_path,req,monkeypatch,'stopped',terminal_at=40)
    (out/'STOP').touch()
    result = campaign.train(out,req,ready,identity(req),env=env)
    assert result['status'] == 'paused' and result['global_transitions'] == 40
    assert result['replay_rows_verified'] == 40
    assert result['launch_attempts'] == 1 and backend.events[-1] == ('close',0)
    assert inspect_checkpoint(result['checkpoint'])['checkpoint']['resumable'] is True


def test_fault_terminal_is_not_learned_as_an_ordinary_physical_failure(tmp_path,monkeypatch):
    req = request(tmp_path)
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'fault',terminal_at=1)
    class FaultFixture(PhysicalFixture):
        def step(self,action):
            observation,reward,term,trunc,info = super().step(action)
            info['task']['termination_reason'] = 'drive_fault'
            return observation,reward,term,trunc,info
    env.environment_factory = FaultFixture
    with pytest.raises(ValueError,match='ordinary'):
        campaign.train(out,req,ready,identity(req),env=env)
    assert json.loads((out/'result.json').read_text())['status'] == 'failed'


@pytest.mark.parametrize('task_reason,backend_reason',[
    ('owner_intervention','owner_intervention'),
    ('drive_fault','drive_fault'),
    ('unknown','unknown'),
    ('external_cutoff',None),
    ('external_cutoff','owner_intervention'),
    ('drive_fault','time_limit'),
])
def test_unproven_inner_truncation_is_rejected_before_trace_or_replay(
        tmp_path,monkeypatch,task_reason,backend_reason):
    req = request(tmp_path)
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'truncated',truncate_at=1)
    class TruncatedFixture(PhysicalFixture):
        def step(self,action):
            observation,reward,term,trunc,info = super().step(action)
            info['task']['termination_reason'] = task_reason
            if backend_reason is not None:
                info['termination_reason'] = backend_reason
            return observation,reward,term,trunc,info
    env.environment_factory = TruncatedFixture
    (out/'STOP').touch()
    with pytest.raises(ValueError,match='ordinary'):
        campaign.train(out,req,ready,identity(req),env=env)
    assert env.count == env.episode_steps == 0
    assert not env.current_trace.exists()
    assert not env.completed and not env.censored and not env.qc_records
    assert not list((out/'checkpoints').glob('step_*'))


def test_explicit_backend_time_limit_is_a_bootstrapped_replay_timeout(tmp_path,monkeypatch):
    req = request(tmp_path)
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'timeout',truncate_at=1)
    class TimeoutFixture(PhysicalFixture):
        def step(self,action):
            observation,reward,term,trunc,info = super().step(action)
            info['termination_reason'] = 'time_limit'
            return observation,reward,term,trunc,info
    env.environment_factory = TimeoutFixture
    (out/'STOP').touch()
    result = campaign.train(out,req,ready,identity(req),env=env)
    model = load_model(result['checkpoint'])
    assert result['status'] == 'paused'
    assert result['global_transitions'] == result['replay_rows_verified'] == 1
    assert len(env.censored) == 1 and not env.completed
    assert env.last['administrative_censor'] is False
    assert model.replay_buffer.dones[0,0] == model.replay_buffer.timeouts[0,0] == 1
    assert float(model.replay_buffer.sample(1).dones[0,0]) == 0


def test_retention_preserves_failure_bytes_and_bounds_success_archives(tmp_path):
    req = replace(request(tmp_path),successful_raw_keep=1)
    retention = campaign.EpisodeRetention(tmp_path,req)
    failed_hashes = []
    for n in range(5):
        episode = f'episode_{n}'
        raw = tmp_path/'episodes'/episode
        raw.mkdir(parents=True)
        (raw/'payload.txt').write_text(f'raw source {n}')
        success = n > 0
        retention.finish(episode,dict(family='clean'),dict(task_success=success),dict(valid=True))
        assert not raw.exists()
        if not success:
            failed_hashes.append(campaign.sha(tmp_path/'episode_records'/episode/'raw.tar.gz'))
    assert retention.records[0]['retained_raw'] is True
    assert campaign.sha(tmp_path/'episode_records/episode_0/raw.tar.gz') == failed_hashes[0]
    assert sum(r['retained_raw'] for r in retention.records) == 3
    assert all((tmp_path/'episode_records'/f'episode_{n}'/'summary.json').is_file() for n in range(5))


def test_manifest_tampering_rejects_campaign_resume(tmp_path,monkeypatch):
    req = request(tmp_path)
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'tamper',terminal_at=1)
    (out/'STOP').touch()
    result = campaign.train(out,req,ready,identity(req),env=env)
    path = Path(result['checkpoint'])
    (path/'rng.pkl').write_bytes(b'changed')
    with pytest.raises(ValueError,match='manifest'):
        inspect_checkpoint(path)


def test_old_checkpoint_success_prune_receipt_keeps_resume_eligible(tmp_path,monkeypatch):
    req = replace(request(tmp_path),successful_raw_keep=1)
    out,env,_,ready = fixture(tmp_path,req,monkeypatch,'old')
    for n in range(3):
        raw = out/'episodes'/f'episode_{n}'
        raw.mkdir(parents=True)
        (raw/'source.json').write_text(str(n))
        env.retention.finish(f'episode_{n}',dict(family='clean'),dict(task_success=True),dict(valid=True))
    state = deepcopy(env.state())
    assert state['retention'][2]['retained_raw'] is True
    raw = out/'episodes/episode_3'
    raw.mkdir(parents=True)
    (raw/'source.json').write_text('3')
    env.retention.finish('episode_3',dict(family='clean'),dict(task_success=True),dict(valid=True))
    assert not (out/'episode_records/episode_2/raw.tar.gz').exists()
    continued = replace(req,resume=out/'checkpoints/old_boundary')
    _,resumed,backend,_ = fixture(tmp_path,continued,monkeypatch,'resumed')
    resumed.restore(state)
    assert resumed.retention.records[2]['retained_raw'] is False
    assert not backend.events


@pytest.mark.parametrize('fault',['missing','corrupt'])
def test_missing_or_changed_failure_archive_blocks_resume_before_launch(tmp_path,monkeypatch,fault):
    req = request(tmp_path)
    out,env,_,_ = fixture(tmp_path,req,monkeypatch,'old')
    raw = out/'episodes/episode_0'
    raw.mkdir(parents=True)
    (raw/'source.json').write_text('failure raw')
    env.retention.finish('episode_0',dict(family='clean'),dict(task_success=False),dict(valid=True))
    state = env.state()
    archive = out/'episode_records/episode_0/raw.tar.gz'
    if fault == 'missing':
        archive.unlink()
    else:
        archive.write_bytes(b'corrupt')
    continued = replace(req,resume=out/'checkpoints/old_boundary')
    _,resumed,backend,_ = fixture(tmp_path,continued,monkeypatch,'resumed')
    with pytest.raises(ValueError,match='archive'):
        resumed.restore(state)
    assert not backend.events
