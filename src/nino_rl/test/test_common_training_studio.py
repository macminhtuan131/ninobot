"""Actual SB3 updates/checkpoints on synthetic plant; no Gazebo benefit claim."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest
from nino_rl import common_training_studio as job
from nino_rl import common_studio_contract as spec
from nino_rl import training_studio_api as api


def request(**kw):
    return dict(dict(schema_version=1, mode='train', scenario='clear_box', profile=spec.SMOKE_PROFILE,
        timesteps=145, seed=11, checkpoint_every=64, wall_minutes=10, evaluate=False, resume=None), **kw)


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    instances=[]
    class Backend:
        residual_contract_id=job.EpisodeLifecycle.residual_contract_id
        kind='synthetic_test_only';calibrated_to_hardware=False
        def __init__(self,c,directory,world,g,task,bc,lp,backend_factory=None):
            assert backend_factory is job.DriveReadinessBackend
            self.config,self.protocol,self.directory=c,task,directory
            directory.mkdir(parents=True);self.current=None;self.namespace=None
            self.index=-1;self.closed=False;self.stops=[];instances.append(self)
        def reset(self,seed=None):
            self.index+=1;self.namespace=f'episode_{self.index}'
            (self.directory/self.namespace).mkdir()
            c=deepcopy(self.config);c['backend'].update(wheel_gain=[1.,1.],motor_lag_s=[.16,.16],imu_noise_std=0.)
            self.stops.append(self.protocol['command_until_s'])
            self.current=job.frozen.offline.fixture_backend(c,self.protocol['command_until_s'])
            return self.current.reset(seed=seed)
        def view(self):return deepcopy(self.current.last_view)
        def advance_reference(self,*args):
            view,labels,term,trunc,info=self.current.advance_reference(*args)
            info.update(truth_used_for_guidance=False,guidance_audit=dict(fault=False),
                        source_lags_s=dict(wheel=0.,imu=0.),fixture_only=True)
            return view,labels,term,trunc,info
        def __getattr__(self,name):
            current=self.__dict__.get('current')
            if current is None:raise AttributeError(name)
            return getattr(current,name)
        def close(self):
            self.closed=True
            if self.current is not None:self.current.close()
    monkeypatch.setattr(job,'EpisodeLifecycle',Backend)
    monkeypatch.setattr(job,'prepare_worlds',lambda p:{'clear_box':'synthetic_only'})
    return instances


def test_dispatch_budget_and_contract_separation():
    value=dict(request(),schema_version=2,engine=spec.ENGINE)
    engine,body=api.split(value)
    assert engine==spec.ENGINE and body==request()
    assert api.split(request())[0]=='legacy100_v1'
    assert spec.budget(request(timesteps=280))['training_launches_max']==3
    assert spec.profiles()['nino_td3_research_h5_v1']['algorithm']['buffer_size']==32768
    assert spec.legacy.profiles()['nino_td3_research_h5_v1']['algorithm']['buffer_size']==1000000
    for bad in [dict(scenario='box_c1_6mm'),dict(timesteps=20001),
                dict(profile='nino_td3_research_h5_v1',timesteps=10000)]:
        with pytest.raises(ValueError):spec.validate_request(request(**bad))


def test_actual_training_replay_and_resume(tmp_path,synthetic):
    from stable_baselines3 import TD3
    first=tmp_path/'first';first.mkdir()
    result=job.train(first,request(),lambda:False)
    assert result['transitions']==145 and result['optimizer_updates_total']==129
    assert result['actor_updates_total']==64
    assert result['terminal_episodes']==1 and result['final_segment_right_censored']
    assert synthetic[0].stops==[6.,8.] and all(b.closed for b in synthetic)
    assert result['replay_audit']['rows_checked']==145
    assert result['action_coverage']['window_open']>0
    cp=spec.inspect_checkpoint(result['checkpoint'],check_runtime=True)
    model=TD3.load(Path(cp['path'])/'model.zip');model.load_replay_buffer(Path(cp['path'])/'replay_buffer.pkl')
    assert model.actor.optimizer.state and model.critic.optimizer.state
    assert model.observation_space.shape==(103,) and model.action_space.shape==(1,)
    second=tmp_path/'second';second.mkdir()
    resumed=job.train(second,request(timesteps=20,resume=cp['path']),lambda:False)
    assert resumed['starting_global_steps']==145 and resumed['global_steps']==165
    assert resumed['optimizer_updates_this_job']==20 and resumed['replay_size']==165
    assert api.inspect_checkpoint(cp['path'])['engine']==spec.ENGINE
    with pytest.raises(ValueError,match='same common'):spec.require_resume(request(seed=22,resume=cp['path']))
    with pytest.raises(ValueError,match='Unsupported'):spec.legacy.inspect_checkpoint(cp['path'])
    p=Path(cp['path'])/'replay_buffer.pkl';p.write_bytes(p.read_bytes()+b'corrupt')
    with pytest.raises(ValueError,match='hash mismatch'):spec.inspect_checkpoint(cp['path'])


def test_cancel_boundary_and_no_mid_optimizer_snapshot(tmp_path,synthetic,monkeypatch):
    out=tmp_path/'cancel';out.mkdir();calls=[]
    def stopped():calls.append(True);return len(calls)>12
    with pytest.raises(job.Cancelled):job.train(out,request(),stopped)
    cp=next((out/'checkpoints').glob('*_interrupted'))
    info=spec.inspect_checkpoint(cp)
    assert info['global_steps']==info['replay_size'] and 0<info['global_steps']<145
    from stable_baselines3 import TD3
    def fail(*args,**kw):raise TimeoutError('mid optimizer')
    monkeypatch.setattr(TD3,'train',fail)
    out=tmp_path/'mid';out.mkdir()
    with pytest.raises(TimeoutError,match='mid optimizer'):job.train(out,request(),lambda:False)
    assert not list((out/'checkpoints').glob('*_interrupted'))
    assert all(b.closed for b in synthetic)


def test_permission_failure_before_command(tmp_path,synthetic,monkeypatch):
    monkeypatch.setattr(job.ready,'require_ready',lambda view:(_ for _ in ()).throw(ValueError('denied')))
    out=tmp_path/'denied';out.mkdir()
    with pytest.raises(ValueError,match='denied'):job.train(out,request(),lambda:False)
    assert not (out/'training_trace.jsonl').exists()
    assert all(b.closed for b in synthetic)


def test_disk_preflight_before_job_or_physics(tmp_path,monkeypatch):
    from collections import namedtuple
    Disk=namedtuple('Disk','total used free')
    monkeypatch.setattr(spec.shutil,'disk_usage',lambda p:Disk(1024,1024,0))
    monkeypatch.setattr(job,'train',lambda *args:pytest.fail('No physics on disk failure'))
    root=tmp_path/'jobs'
    with pytest.raises(ValueError,match='Disk budget'):job.run(root,request())
    assert not root.exists()


def test_training_closed_before_evaluation(tmp_path,synthetic,monkeypatch):
    def evaluate(*args):
        assert all(b.closed for b in synthetic)
        return []
    monkeypatch.setattr(job,'evaluate',evaluate)
    out=tmp_path/'eval';out.mkdir()
    assert job.train(out,request(evaluate=True),lambda:False)['evaluation']==[]


def test_real_eval_loop_all_six_conditions_actor_purity(tmp_path,synthetic,monkeypatch):
    monkeypatch.setattr(job.frozen.baseline,'summarize',lambda rows,target:dict(
        steps=len(rows),functional_proposal_pass=True,synthetic_summary=True))
    monkeypatch.setattr(job.frozen.timing,'timestamp_diagnostic',lambda *args:dict(valid=True,synthetic_only=True))
    b=job.make_backend(tmp_path/'actor','synthetic_only',1)
    env=job.environment(b,tmp_path,64)
    model=job.build_model(env,request());job.frozen.offline.zero_initialize_scalar(model)
    result=job.evaluate(tmp_path,request(),'synthetic_only',model,lambda:False)
    assert len(result)==6 and sum(r['steps'] for r in result)==840
    assert {r['source_stop_s'] for r in result}=={6.,8.}
    assert {r['arm'] for r in result}=={'B0','Classical_scheduled','TD3'}
    env.close()
    assert all(b.closed for b in synthetic)


def test_checkpoint_exact_network_target_optimizer_parity(tmp_path,synthetic,monkeypatch):
    from stable_baselines3 import TD3
    original=job.checkpoint;checks=[]
    def checking(model,*args):
        path=original(model,*args)
        loaded=TD3.load(path/'model.zip',device='cpu')
        loaded.load_replay_buffer(path/'replay_buffer.pkl')
        assert job.ready.parent.full_snapshot(loaded)==job.ready.parent.full_snapshot(model)
        assert loaded.num_timesteps==model.num_timesteps
        assert loaded.replay_buffer.size()==model.replay_buffer.size()
        checks.append(True);return path
    monkeypatch.setattr(job,'checkpoint',checking)
    out=tmp_path/'parity';out.mkdir()
    job.train(out,request(timesteps=32),lambda:False)
    assert checks==[True]
