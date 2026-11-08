"""Zero qualification coordinator/ownership tests; synthetic, no physics."""
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from nino_rl import residual_drive_readiness as job


def view():return dict(permission=True,sensors_fresh=True,fault=False,emergency_stop=False,input_ages_s=dict(wheel=.001,imu=.003,drive=.009))


@pytest.mark.parametrize('age',[.041,-.001,float('nan'),float('inf')])
def test_initial_support_cannot_be_unknown_or_outside_fixed_gate(age):
    v=view();v['input_ages_s']['wheel']=age
    with pytest.raises(ValueError,match='not ready'):job.require_ready(v)


def test_unreleased_job_does_not_consume_a_slot(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    monkeypatch.setattr(job,'release_record',lambda:dict(released=False))
    with pytest.raises(ValueError,match='not released'):job.run(tmp_path/'root')
    assert not (tmp_path/'root/state.json').exists()


def test_closed_or_foreign_root_rejected_before_release(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path/'home'))
    job.save(tmp_path/'state.json',dict(runs=[dict(action='old')]))
    monkeypatch.setattr(job,'release_ready',lambda:pytest.fail('Consumed root must reject first'))
    with pytest.raises(ValueError,match='already consumed'):job.run(tmp_path)


@pytest.mark.parametrize('deny_first',[False,True])
def test_actual_coordinator_only_sends_zero_and_closes_before_next_launch(tmp_path,monkeypatch,deny_first):
    instances=[];commands=[]
    class Backend:
        def __init__(self,c,d,*a,backend_factory=None):
            assert backend_factory is job.DriveReadinessBackend
            if instances:assert instances[-1].closed
            self.closed=False;self.directory=d;self.namespace='synthetic_epoch';instances.append(self)
            p=d/self.namespace;(p/'backend/episode_0').mkdir(parents=True)
            (p/'independent').mkdir()
            job.save(p/'backend/episode_0/settling.json',dict(passed=True,rows=[dict(readiness=dict(ready=True))]*5))
            job.save(p/'independent/process_exit.json',dict(returncode=0,shutdown_ack=True))
            (p/'boundary_checks.jsonl').write_text(json.dumps(dict(primary_after=dict(supported=True,age_ns=0),independent=dict(supported=True,age_ns=0)))+'\n')
            self.current=SimpleNamespace(flush_raw=lambda:None)
        def reset(self,**kw):
            v=view()
            if deny_first:v['permission']=False
            return v,dict(synthetic_only=True)
        def advance_reference(self,v,w,dt):
            commands.append((v,w,dt))
            return view(),{},False,False,dict(final_ros_reference=[0.,0.],applied_target_rad_s=[0.,0.])
        def close(self):self.closed=True
    monkeypatch.setattr(job,'EpisodeLifecycle',Backend)
    monkeypatch.setattr(job.parent.frozen,'prepare_worlds',lambda out:dict(clear_box='unused'))
    if deny_first:
        with pytest.raises(ValueError,match='not ready'):job.qualify(tmp_path)
        assert commands==[] and len(instances)==1 and instances[0].closed
    else:
        r=job.qualify(tmp_path)
        assert commands==[(0.,0.,.1)]*20 and len(instances)==2 and all(x.closed for x in instances)
        assert r['zero_control_ticks']==20 and r['optimizer_updates']==0 and r['actor_loads']==0
