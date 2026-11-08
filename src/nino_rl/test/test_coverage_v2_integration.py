"""Actual V2 train_learner, collector, validator and SB3 replay; no physics.

The plant/closure/terminal summaries are explicitly synthetic. The production
transition validator and feasibility checks are deliberately NOT replaced.
"""
import json
from pathlib import Path
import numpy as np
import pytest
from nino_rl import residual_coverage_study_v2 as job


def synthetic_lifecycle(monkeypatch, corrupt=None):
    instances=[]
    class Lifecycle:
        residual_contract_id=job.EpisodeLifecycle.residual_contract_id
        kind='synthetic_lifecycle_interface_fixture'
        calibrated_to_hardware=False
        def __init__(self,config,directory,world,guidance,task,condition,protocol):
            self.config,self.protocol,self.condition=config,task,condition
            self.directory=directory;directory.mkdir(parents=True)
            self.namespace=self.current=None;self.index=-1;self.closed=False
            self.flushes=0;instances.append(self)
        def reset(self,seed=None):
            if self.current is not None:self.current.close()
            self.index+=1;self.namespace=f'synthetic_epoch_{self.index}'
            (self.directory/self.namespace).mkdir()
            from copy import deepcopy
            config=deepcopy(self.config)
            # Balanced synthetic wheels keep the fixture inside engineering
            # gates; no controller/validator limits are relaxed for this test.
            config['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
            self.current=job.frozen.offline.fixture_backend(config,self.protocol['command_until_s'])
            self.current.flush_raw=lambda:setattr(self,'flushes',self.flushes+1)
            return self.current.reset(seed=seed)
        def advance_reference(self,*args,**kwargs):
            view,labels,term,trunc,info=self.current.advance_reference(*args,**kwargs)
            # Fixture has no ROS GuidedBackend; these are interface assumptions,
            # not evidence of real sensor support or Gazebo measurement quality.
            info.update(truth_used_for_guidance=False,guidance_audit=dict(fault=False),
                source_lags_s=dict(wheel=0.,imu=0.))
            if corrupt=='condition':
                info['qualification_condition']=dict(arm='A_gaussian',seed=11,source_stop_s=8.)
            elif corrupt=='clock':
                info['sensor_clock_s']+=.03
            return view,labels,term,trunc,info
        def __getattr__(self,name):return getattr(self.current,name)
        def close(self):
            self.closed=True
            if self.current is not None:self.current.close()
    monkeypatch.setattr(job,'EpisodeLifecycle',Lifecycle)
    monkeypatch.setattr(job.frozen.baseline,'summarize',lambda rows,path:dict(steps=len(rows),functional_proposal_pass=True))
    monkeypatch.setattr(job.frozen.timing,'timestamp_diagnostic',lambda *a:dict(valid=True,synthetic_only=True))
    return instances


@pytest.mark.parametrize('arm',['A_gaussian','C_stratified_probes'])
def test_actual_train_path_all_resets_terminal_replay_and_checkpoint(tmp_path,monkeypatch,arm):
    import torch
    from nino_rl.coverage_td3 import CoverageTD3
    torch.set_num_threads(1)
    instances=synthetic_lifecycle(monkeypatch)
    target=tmp_path/arm
    result=job.train_learner(target,arm,11,'software_fixture_only',0)
    rows=[json.loads(line) for line in (target/'training_trace.jsonl').read_text().splitlines()]
    resets=job.read(target/'resets.json')
    assert len(rows)==1024 and len(resets)==8
    assert [r['stop_s'] for r in resets]==[6.,8.]*4
    assert (result['critic_updates'],result['actor_updates'],result['full_task_terminals'])==(960,480,7)
    assert result['final_segment_steps']==44 and result['final_segment_right_censored']
    assert instances[0].closed and instances[0].flushes==7
    for episode in range(8):
        group=[r for r in rows if r['episode']==episode]
        stop=(6.,8.)[episode%2]
        assert group[0]['step']==0 and group[0]['equal_observation'][102]==0.
        assert group[0]['collection']['timestep']==episode*140+1
        assert group[0]['episode_namespace']==f'synthetic_epoch_{episode}'
        assert all(r['qualification_condition']==dict(arm=arm,seed=11,source_stop_s=stop) for r in group)
        assert group[-1]['terminated']==(episode<7)
        assert not any(r['TimeLimit.truncated'] for r in group)
    loaded=CoverageTD3.load(target/'model.zip',device='cpu')
    loaded.load_replay_buffer(target/'replay_buffer.pkl')
    assert loaded.nino_sampler.decisions==1024
    assert job.frozen.contract.audit_replay(loaded.replay_buffer,rows)['rows_checked']==1024
    np.testing.assert_array_equal(loaded.replay_buffer.actions[:1024,0,0],
        [r['collection']['requested_scalar'][0] for r in rows])
    job.require_identity(loaded.nino_coverage_identity,arm,11)
    with pytest.raises(ValueError,match='identity mismatch'):
        job.require_identity(job.failed_v1.identity(arm,11),arm,11)


@pytest.mark.parametrize('corrupt,match',[('condition','Conflicting'),('clock','clock/source epoch')])
def test_bad_condition_or_clock_in_actual_train_path_never_enters_replay(tmp_path,monkeypatch,corrupt,match):
    import torch
    from nino_rl.coverage_td3 import CoverageTD3
    torch.set_num_threads(1)
    instances=synthetic_lifecycle(monkeypatch,corrupt=corrupt)
    target=tmp_path/'failed'
    with pytest.raises(ValueError,match=match):
        job.train_learner(target,'A_gaussian',11,'software_fixture_only',0)
    model=CoverageTD3.load(target/'partial_model_failed.zip',device='cpu')
    model.load_replay_buffer(target/'partial_replay_failed.pkl')
    assert model.replay_buffer.size()==0 and model._n_updates==0
    assert instances[0].closed and not (target/'training_result.json').exists()
    if corrupt=='clock':assert len((target/'training_trace.jsonl').read_text().splitlines())==1


def test_v2_rejects_historical_root_before_release_source_or_physics(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    job.save(tmp_path/'state.json',dict(runs=[dict(action=job.failed_v1.ACTION,status='failed')]))
    monkeypatch.setattr(job,'source',lambda *a:pytest.fail('Old root must be rejected first'))
    with pytest.raises(ValueError,match='separate root'):
        job.run(tmp_path,job.PREFLIGHT)


def test_only_version_and_declared_correction_change_scientific_plan():
    old,new=job.failed_v1.protocol(),job.protocol()
    assert {k:v for k,v in new.items() if k not in ('revision','protocol_id')}=={
        k:v for k,v in old.items() if k!='protocol_id'}
    job.plan.validate(new)
    new['revision']['budget_source']='reuse_v1_slots'
    with pytest.raises(ValueError,match='lineage'):job.plan.validate(new)
