"""Evaluator wiring regression: no ROS, Gazebo, actor training, or new budget."""
import json
from types import SimpleNamespace
import numpy as np
import pytest
from nino_rl import residual_reliable_evaluation as corrected


@pytest.mark.parametrize('arm',['B0','Classical_scheduled','TD3'])
def test_each_arm_uses_lifecycle_and_epoch_before_first_step(tmp_path,monkeypatch,arm):
    events=[];instances=[]
    class Lifecycle:
        def __init__(self,c,directory,world,g,t,condition,p):
            self.namespace=None;self.current=None;self.directory=directory
            self.directory.mkdir();instances.append(self)
        def close(self):events.append('close')
    class Env:
        def reset(self,seed=None):
            b=instances[-1];b.namespace='episode_0';b.current=object()
            events.append('reset');return np.zeros(103,np.float32),{}
        def step(self,action):
            assert instances[-1].namespace=='episode_0' and instances[-1].current is not None
            events.append('step');i=events.count('step')
            return np.zeros(103,np.float32),0.,i==140,False,dict(sensor_clock_s=i*.1,task=dict(elapsed_s=i*.1),source_lags_s=dict(wheel=.001))
        def close(self):instances[-1].close()
    monkeypatch.setattr(corrected,'EpisodeLifecycle',Lifecycle)
    monkeypatch.setattr(corrected.contract,'environment',lambda *args:Env())
    monkeypatch.setattr(corrected.qualified,'verify_transition',lambda *args:None)
    monkeypatch.setattr(corrected,'feasibility',lambda *args:None)
    monkeypatch.setattr(corrected.baseline,'summarize',lambda rows,path:dict(steps=len(rows),functional_proposal_pass=True))
    monkeypatch.setattr(corrected.timing,'timestamp_diagnostic',lambda path,rows:dict(valid=True))
    if arm=='TD3':
        from stable_baselines3 import TD3
        fake=SimpleNamespace(nino_reliable_identity=corrected.frozen.identity(),predict=lambda obs,deterministic:(np.zeros(1,np.float32),None))
        monkeypatch.setattr(TD3,'load',lambda *args,**kwargs:fake)
    condition=dict(arm=arm,source_stop_s=6.)
    if arm=='TD3':condition['seed']=11
    out=tmp_path/'evaluation'
    result=corrected.evaluate_rollout(out,condition,'world',{11:tmp_path})
    assert result['steps']==140 and events==['reset']+['step']*140+['close']
    rr=[json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]
    assert len(rr)==140 and all(r['episode_namespace']=='episode_0' for r in rr)
    assert (out/'episodes').exists() and not (out/'backend').exists()
    assert not corrected.EVALUATION_JOB_RELEASED


def test_wrong_legacy_backend_fails_before_any_physics_control(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(corrected,'EpisodeLifecycle',lambda *a:SimpleNamespace())
    class Env:
        def reset(self,**kwargs):return np.zeros(103,np.float32),{}
        def step(self,*args):pytest.fail('Wrong backend must fail before first control interval')
        def close(self):calls.append('closed')
    monkeypatch.setattr(corrected.contract,'environment',lambda *a:Env())
    with pytest.raises(AttributeError,match='namespace'):
        corrected.evaluate_rollout(tmp_path/'eval',dict(arm='B0',source_stop_s=6.),'world',{})
    assert calls==['closed']
