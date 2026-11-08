"""Contract, serialization, real SB3 resume, failure and shutdown ordering."""
import json
from pathlib import Path
import numpy as np
import pytest
from nino_rl import td3_training_studio as studio
from nino_rl import td3_studio_contract as contract

def request(**kwargs):
    return dict(dict(schema_version=1,mode='train',scenario='clear_box',profile=contract.SMOKE_PROFILE,
        timesteps=20,seed=7,checkpoint_every=8,wall_minutes=2,evaluate=False,resume=None),**kwargs)

@pytest.mark.parametrize('change',[dict(timesteps=0),dict(timesteps=True),dict(seed=-1),dict(evaluate='yes'),
    dict(mode='smoke',timesteps=63),dict(mode='smoke',timesteps=64,resume='actor.zip'),dict(scenario='unknown')])
def test_request_rejects_unbounded_or_ambiguous_input(change):
    with pytest.raises(ValueError):contract.validate_request(request(**change))

@pytest.fixture
def synthetic_backend(tmp_path,monkeypatch):
    import gymnasium as gym
    backends=[]
    class Backend:
        kind='synthetic_test_only'
        def __init__(self,*args):self.closed=False;backends.append(self)
        def close(self):self.closed=True
    class Env(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,shape=(100,),dtype=np.float32)
        action_space=gym.spaces.Box(-1.,1.,shape=(2,),dtype=np.float32)
        def __init__(self,backend):self.backend=backend
        def reset(self,**kwargs):super().reset(**kwargs);return np.zeros(100,np.float32),{}
        def step(self,action):
            task=dict(velocity_error_m_s=0.,cross_track_m=0.,task_success=False,stop_completed=False,marker_reached=False)
            return np.zeros(100,np.float32),0.,False,False,dict(task=task,policy_proposal=action,
                reference_trace={'observation':np.zeros(100,np.float32)},body_speed_m_s=0.,reward_terms={})
        def close(self):self.backend.close()
    parent=tmp_path/'parent';parent.mkdir();(parent/'manifest.json').write_text('{}')
    monkeypatch.setattr(studio.guided.contact,'validated_latest',lambda *a,**k:parent)
    monkeypatch.setattr(studio,'prepare_worlds',lambda p:{'clear_box':tmp_path/'world'})
    monkeypatch.setattr(studio.baseline,'GuidedBackend',Backend)
    monkeypatch.setattr(studio.guided,'environment',lambda c,b,p,k:Env(b))
    return backends

def test_fresh_then_resume_preserves_counters_replay_and_targets(tmp_path,synthetic_backend):
    from stable_baselines3 import TD3
    first=tmp_path/'first';first.mkdir()
    a=studio.train(first,request(),lambda:False)
    assert a['global_steps']==20 and a['optimizer_updates_total']==4 and a['replay_size']==20
    cp=contract.inspect_checkpoint(a['checkpoint'],True)
    assert cp['global_steps']==20 and cp['files_verified']
    model=TD3.load(Path(a['checkpoint'])/'model.zip');model.load_replay_buffer(Path(a['checkpoint'])/'replay_buffer.pkl')
    assert model.actor.optimizer.state and model.critic.optimizer.state
    second=tmp_path/'second';second.mkdir()
    b=studio.train(second,request(timesteps=10,resume=a['checkpoint']),lambda:False)
    assert b['starting_global_steps']==20 and b['global_steps']==30
    assert b['optimizer_updates_this_job']==10 and b['replay_size']==30
    assert b['replay_audit']['rows_checked']==10
    assert not b['continuation_is_bit_exact']

def test_resume_rejects_wrong_scenario_and_corrupt_replay(tmp_path,synthetic_backend):
    out=tmp_path/'first';out.mkdir();r=studio.train(out,request(),lambda:False)
    with pytest.raises(ValueError,match='same task'):contract.require_resume(request(scenario='box_c1_6mm',resume=r['checkpoint']))
    replay=Path(r['checkpoint'])/'replay_buffer.pkl';replay.write_bytes(replay.read_bytes()+b'corrupt')
    with pytest.raises(ValueError,match='hash mismatch'):contract.inspect_checkpoint(r['checkpoint'])

def test_training_backend_is_closed_before_evaluation(tmp_path,synthetic_backend,monkeypatch):
    called=[]
    def evaluate(*args):
        assert synthetic_backend and all(b.closed for b in synthetic_backend)
        called.append(True);return []
    monkeypatch.setattr(studio,'evaluate',evaluate)
    out=tmp_path/'run';out.mkdir();studio.train(out,request(evaluate=True),lambda:False)
    assert called==[True]

def test_cancel_keeps_a_complete_resumable_transition_boundary(tmp_path,synthetic_backend):
    calls=[]
    def stopped():calls.append(True);return len(calls)>10
    out=tmp_path/'run';out.mkdir()
    with pytest.raises(studio.Cancelled):studio.train(out,request(timesteps=30),stopped)
    cp=next((out/'checkpoints').glob('*_interrupted'))
    info=contract.inspect_checkpoint(cp,True)
    assert 0<info['global_steps']<30 and info['replay_size']==info['global_steps']
    assert all(b.closed for b in synthetic_backend)

def test_failure_is_recorded_without_auto_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    def fail(*args):raise RuntimeError('fixture failure')
    monkeypatch.setattr(studio,'train',fail)
    directory,status=studio.run(tmp_path/'jobs',request())
    assert status=='failed' and (directory/'error.txt').is_file()
    manifest=json.loads((directory/'manifest.json').read_text())
    assert manifest['status']=='failed' and 'error.txt' in manifest['files']

def test_replay_tail_indices_survive_old_buffer_and_wrap():
    import gymnasium as gym
    from stable_baselines3.common.buffers import ReplayBuffer
    obs=gym.spaces.Box(-5.,5.,shape=(2,),dtype=np.float32)
    buf=ReplayBuffer(3,obs,obs,device='cpu');rows=[]
    for _ in range(2):buf.add(np.zeros(2),np.zeros(2),np.zeros(2),np.array([0.]),np.array([False]),[{}])
    start=buf.pos
    for i in range(5):
        a=np.array([i/10,i/10],np.float32)
        buf.add(a,a,a,np.array([i]),np.array([False]),[{}])
        rows.append(dict(timestep=101+i,policy_proposal=a,reference_trace={'observation':a},next_observation=a,reward=i,done=False,**{'TimeLimit.truncated':False}))
    assert studio.audit_tail(buf,rows,start,100)['rows_checked']==3

def test_mid_optimizer_error_does_not_publish_interrupted_checkpoint(tmp_path,synthetic_backend,monkeypatch):
    from stable_baselines3 import TD3
    def fail(*args,**kwargs):raise TimeoutError('fixture mid-optimizer timeout')
    monkeypatch.setattr(TD3,'train',fail)
    out=tmp_path/'run';out.mkdir()
    with pytest.raises(TimeoutError,match='mid-optimizer'):studio.train(out,request(),lambda:False)
    assert not list((out/'checkpoints').glob('*_interrupted'))
    earlier=next((out/'checkpoints').glob('*000016_periodic'))
    assert contract.inspect_checkpoint(earlier)['global_steps']==16
