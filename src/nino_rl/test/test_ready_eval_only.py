"""Actual eval wrapper + real validator on balanced synthetic plant, no Gazebo.

Summary/GT-grid callbacks are explicitly synthetic. The fixture actor is fresh,
not the scientific checkpoint; source/run gates pin the real completed model.
"""
from copy import deepcopy
import json,threading
from pathlib import Path
import numpy as np
import pytest
from nino_rl import residual_ready_eval_only as job


@pytest.fixture(scope='module')
def checkpoint(tmp_path_factory):
    import torch
    from nino_rl.coverage_td3 import build
    torch.set_num_threads(1)
    c,_,task,condition=job.parent.configuration(6.)
    backend=job.parent.frozen.offline.fixture_backend(c,6.)
    env=job.parent.frozen.contract.environment(c,backend,task,condition)
    env.reset(seed=11)
    model=build(env,11,'A_gaussian',job.parent.frozen.protocol()['algorithm'])
    job.parent.frozen.offline.zero_initialize_scalar(model)
    model.nino_coverage_identity=job.parent.identity('A_gaussian',11)
    path=tmp_path_factory.mktemp('inspection_actor')/'model.zip';model.save(path);env.close()
    return path


def synthetic_lifecycle(monkeypatch,deny=False,truth_fault=False):
    instances=[]
    class Backend:
        residual_contract_id=job.EpisodeLifecycle.residual_contract_id
        kind='synthetic_eval_interface_fixture';calibrated_to_hardware=False
        def __init__(self,c,directory,world,g,task,bc,lp,backend_factory=None):
            assert backend_factory is job.DriveReadinessBackend
            self.config,self.task,self.directory=c,task,directory
            directory.mkdir(parents=True);self.current=None;self.namespace=None
            self.closed=False;self.calls=[];self.resets=0;instances.append(self)
        def reset(self,seed=None):
            self.resets+=1;self.namespace='synthetic_episode_0'
            (self.directory/self.namespace).mkdir()
            c=deepcopy(self.config);c['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
            self.current=job.parent.frozen.offline.fixture_backend(c,self.task['command_until_s'])
            return self.current.reset(seed=seed)
        def view(self):
            result=deepcopy(self.current.last_view)
            if deny:result['permission']=False
            return result
        def advance_reference(self,*args,**kwargs):
            self.calls.append(args)
            v,labels,term,trunc,info=self.current.advance_reference(*args,**kwargs)
            info.update(truth_used_for_guidance=truth_fault,guidance_audit=dict(fault=False),
                source_lags_s=dict(wheel=0.,imu=0.),fixture_only=True)
            return v,labels,term,trunc,info
        def __getattr__(self,name):
            current=self.__dict__.get('current')
            if current is None:raise AttributeError(name)
            return getattr(current,name)
        def close(self):
            self.closed=True
            if self.current is not None:self.current.close()
    monkeypatch.setattr(job,'EpisodeLifecycle',Backend)
    monkeypatch.setattr(job.parent.frozen.baseline,'summarize',lambda rows,target:dict(
        steps=len(rows),functional_proposal_pass=True,nominal_velocity_rmse_m_s=.01,synthetic_summary=True))
    monkeypatch.setattr(job.parent.frozen.timing,'timestamp_diagnostic',lambda *a:dict(valid=True,
        header_grid={'0.0':dict(rmse_m_s=.01),'0.01':dict(rmse_m_s=.01)},synthetic_only=True))
    return instances


@pytest.mark.parametrize('arm',['B0','A_gaussian','Classical_scheduled'])
@pytest.mark.parametrize('stop',[6.,8.])
def test_actual_eval_path_140_steps_real_validator_and_actor_purity(tmp_path,monkeypatch,checkpoint,arm,stop):
    instances=synthetic_lifecycle(monkeypatch)
    condition=next(c for c in job.protocol()['evaluation_order'] if c['arm']==arm and c['source_stop_s']==stop)
    before=job.parent.sha(checkpoint)
    result=job.evaluate(tmp_path/'eval',condition,'software_only',checkpoint)
    trace=[json.loads(l) for l in (tmp_path/'eval/trace.jsonl').read_text().splitlines()]
    assert len(trace)==140 and result['steps']==140
    assert instances[0].resets==1 and instances[0].closed and len(instances[0].calls)==140
    assert all(r['qualification_condition']==condition for r in trace)
    assert trace[-1]['terminated'] and not trace[-1]['truncated']
    assert result['actor_unchanged'] and result['exploration_unchanged'] and result['optimizer_updates_in_job']==0
    assert job.parent.sha(checkpoint)==before
    assert job.parent.read(tmp_path/'eval/actor_before.json')==job.parent.read(tmp_path/'eval/actor_after.json')


def test_initial_permission_denied_never_reaches_first_control_request(tmp_path,monkeypatch,checkpoint):
    instances=synthetic_lifecycle(monkeypatch,deny=True)
    with pytest.raises(ValueError,match='Input not ready'):
        job.evaluate(tmp_path/'eval',job.protocol()['evaluation_order'][0],'software_only',checkpoint)
    assert instances[0].closed and instances[0].calls==[]
    assert not (tmp_path/'eval/control_attempts.jsonl').exists()
    assert job.parent.read(tmp_path/'eval/failure.json')['valid_rows']==0


def test_real_validator_rejects_privileged_input_in_actual_eval_path(tmp_path,monkeypatch,checkpoint):
    instances=synthetic_lifecycle(monkeypatch,truth_fault=True)
    with pytest.raises(ValueError,match='Privileged controller input'):
        job.evaluate(tmp_path/'eval',job.protocol()['evaluation_order'][0],'software_only',checkpoint)
    assert instances[0].closed and len(instances[0].calls)==1
    assert len((tmp_path/'eval/trace.jsonl').read_text().splitlines())==1
    assert job.parent.read(tmp_path/'eval/failure.json')['valid_rows']==0


def test_foreign_condition_is_rejected_before_backend_or_output(tmp_path,monkeypatch,checkpoint):
    monkeypatch.setattr(job,'EpisodeLifecycle',lambda *a,**kw:pytest.fail('No undeclared launch'))
    with pytest.raises(ValueError,match='Undeclared'):job.evaluate(tmp_path/'eval',dict(arm='C_stratified_probes',seed=11,source_stop_s=6.),'none',checkpoint)
    assert not (tmp_path/'eval').exists()


def test_release_guard_does_not_consume_slot(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    monkeypatch.setattr(job,'release_record',lambda:dict(released=False))
    with pytest.raises(ValueError,match='not released'):job.run(tmp_path/'root')
    assert not (tmp_path/'root/state.json').exists()


def test_consumed_or_corrupt_ledger_cannot_reopen_budget(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    (tmp_path/'state.json').write_text('broken')
    monkeypatch.setattr(job,'source',lambda *a:pytest.fail('Consumed root must fail first'))
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path)


@pytest.mark.parametrize('cancel',[False,True])
def test_failed_job_seals_status_and_closes_future_slots(tmp_path,monkeypatch,cancel):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    monkeypatch.setattr(job,'release_ready',lambda root:dict(synthetic_only=True))
    monkeypatch.setattr(job,'source',lambda *a:dict(checkpoint='fixture'))
    monkeypatch.setattr(job,'fingerprint',lambda:'synthetic-only')
    def stop(*a):raise KeyboardInterrupt() if cancel else RuntimeError('synthetic fault')
    monkeypatch.setattr(job,'execute',stop)
    with pytest.raises(KeyboardInterrupt if cancel else RuntimeError):job.run(tmp_path/'root')
    state=job.parent.read(tmp_path/'root/state.json');row=state['runs'][-1]
    assert state['latest']=={} and row['status']==('cancelled' if cancel else 'failed')
    assert job.parent.read(tmp_path/'root'/row['path']/'manifest.json')['status']==row['status']
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path/'root')


def test_partial_matrix_failure_never_launches_later_conditions(tmp_path,monkeypatch):
    monkeypatch.setattr(job.parent.frozen,'prepare_worlds',lambda out:dict(clear_box='none'))
    checkpoint=tmp_path/'model.zip';checkpoint.write_bytes(b'fixture')
    calls=[]
    def evaluate(out,condition,*a):
        calls.append(condition)
        if len(calls)==3:raise RuntimeError('stop remaining')
        return dict(steps=140)
    monkeypatch.setattr(job,'evaluate',evaluate)
    with pytest.raises(RuntimeError):job.execute(tmp_path,dict(checkpoint=str(checkpoint)))
    assert calls==job.protocol()['evaluation_order'][:3]
    assert job.parent.read(tmp_path/'evaluation_progress.json')['remaining_slots_closed']


@pytest.mark.parametrize('kind,decision',[
    ('better','descriptive_candidate_requires_separate_holdout'),
    ('worse','no_go_expand_this_checkpoint_clear_known_stop'),
    ('small','unknown_small_or_condition_dependent_effect'),('grid','unknown_grid_sensitive')])
def test_fixed_comparison_does_not_promote_single_seed_or_mix_grids(kind,decision):
    runs=[]
    for condition in job.protocol()['evaluation_order']:
        value=1.2 if condition['arm']=='B0' else 1. if condition['arm']=='Classical_scheduled' else (
            .94 if kind=='better' else 1.02 if kind=='worse' else .98)
        gt=1.02 if condition['arm']=='A_gaussian' and kind=='grid' else value
        runs.append(dict(evaluation_condition=condition,nominal_velocity_rmse_m_s=value,
            timestamp_diagnostic=dict(header_grid={'0.0':dict(rmse_m_s=gt),'0.01':dict(rmse_m_s=gt)})))
    result=job.compare(runs)
    assert result['decision']==decision and not result['benefit_verified'] and result['one_training_seed_only']
