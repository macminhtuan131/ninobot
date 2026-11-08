"""Stop6 semantics, ABI isolation and honest inherited driver identity."""
from copy import deepcopy
import numpy as np
import pytest
from nino_rl import pi_stop_validation_context as context
from nino_rl import pi_screen_context as selected
from nino_rl.pi_stop_validation_preflight import fixture_backend


@pytest.fixture(scope='module')
def identity():return context.identity()


@pytest.mark.parametrize('ki',[.1,.15])
def test_only_schedule_and_identity_change_from_selected_context(ki):
    c,g,t,b=context.configuration(ki);old,og,ot,ob=selected.configuration(ki)
    assert c['backend']['command_until_s']==c['task']['command_until_s']==t['command_until_s']==6.
    assert g==og and b==ob
    for v in (c,old):
        v.pop('purpose');v['backend'].pop('scenario_id')
        v['backend'].pop('command_until_s');v['task'].pop('command_until_s')
    for v in (t,ot):v.pop('protocol_id');v.pop('command_until_s')
    assert c==old and t==ot


def test_new_ABI_keeps_shape_but_rejects_old_checkpoint_identity(identity):
    old=selected.identity()
    assert identity['observation']==old['observation'] and identity['action']==old['action']
    assert identity['abi_sha256']!=old['abi_sha256'] and identity['source_stop_s']==6.
    assert not identity['actor_loading_allowed'] and not identity['training_released']
    with pytest.raises(ValueError):context.require_identity(old)


@pytest.mark.parametrize('field,value',[('backend_stop',8.),('task_stop',8.),
    ('guided_stop',8.),('gain',1.02),('training',True),('hardware',1.)])
def test_environment_rejects_wrong_schedule_gain_or_authority(field,value):
    c,g,t,b=context.configuration(.1)
    if field=='backend_stop':c['backend']['command_until_s']=value
    if field=='task_stop':c['task']['command_until_s']=value
    if field=='guided_stop':t['command_until_s']=value
    if field=='gain':c['backend']['sim_common_gain']=value
    if field=='training':c['training']['allowed']=value
    if field=='hardware':c['hardware_authority']=value
    with pytest.raises(ValueError,match='stop6/gain1'):context.environment(c,None,t,b)


@pytest.mark.parametrize('action',[np.ones(1),np.zeros(2),np.array([np.nan])])
def test_invalid_residual_rejected_before_backend(action,identity,monkeypatch):
    monkeypatch.setattr(context,'identity',lambda:deepcopy(identity))
    c,g,t,b=context.configuration(.1);backend=fixture_backend(c)
    env=context.environment(c,backend,t,b)
    env.reset(seed=701)
    monkeypatch.setattr(backend,'advance_reference',lambda *a:pytest.fail('No backend step'))
    with pytest.raises(ValueError,match='B0 only'):env.step(action)
    env.close()


@pytest.mark.parametrize('ki',[None,.2,float('nan'),True])
def test_no_new_Ki_condition(ki):
    with pytest.raises((TypeError,ValueError)):context.configuration(ki)


def test_full_stop6_wrapper_parity(identity,monkeypatch):
    monkeypatch.setattr(context,'identity',lambda:deepcopy(identity))
    proof=context.wrapper_parity()
    assert len(proof)==2 and sum(r['wrapper_transitions'] for r in proof)==560
    assert all(r['observation_reward_reference_projection_terminal_exact'] and not r['Ki_dynamics_modeled'] for r in proof)


def test_source_really_withdraws_at_6_not_8(identity,monkeypatch):
    from nino_rl.pi_stop_validation_preflight import SyntheticLifecycle
    monkeypatch.setattr(context,'identity',lambda:deepcopy(identity))
    c,g,t,b=context.configuration(.1)
    # Synthetic source models the declared stop schedule; not real guidance dynamics.
    from nino_rl.pi_stop_validation_runner import EpisodeLifecycle,PiScreenBackend
    from functools import partial
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as root:
        backend=SyntheticLifecycle(c,Path(root)/'ep','fixture',g,t,b,{},
            backend_factory=partial(PiScreenBackend,allow_physics=True))
        env=context.environment(c,backend,t,b)
        try:
            env.reset(seed=701);rows=[]
            for step in range(140):rows.append(env.step(np.zeros(1,np.float32))[-1])
            # Inspect the scheduler's baseline source, not body motion or final ramp.
            samples=[r['reference_trace']['source_samples']['baseline'] for r in rows]
            assert any(s['values'][0]>0 for s in samples if s['receipt_s']<6.)
            assert all(s['values'][0]==0 for s in samples if s['receipt_s']>=6.+1e-7)
        finally:env.close()


@pytest.mark.parametrize('now,expected',[(.49,0.),(.5,.2),(5.9,.2),(6.,0.),(7.9,0.),(8.,0.)])
def test_inherited_real_guidance_schedule_without_ROS(now,expected,monkeypatch):
    """Call the actual backend view scheduler; mock IO and final view adapter."""
    import threading
    from types import SimpleNamespace
    from nino_rl import residual_guided_baseline as guided
    from nino_rl.pi_screen_backend import PiScreenBackend
    from nino_rl.residual_guidance import GuidanceReference
    assert PiScreenBackend.view is guided.GuidedBackend.view
    c,g,t,b=context.configuration(.1)
    obj=object.__new__(PiScreenBackend)
    obj.time=now;obj.start_time=0.;obj.active=True;obj.cached_view=None
    obj.lock=threading.Lock();obj.protocol=t;obj.config=c;obj.gconf=g;obj.condition=b
    obj.estimator=SimpleNamespace(advance=lambda tick:[],estimate=lambda:dict(
        pose=[0.,0.,0.],stamp_s=now,epoch='test'))
    obj.guidance=GuidanceReference(g,epoch='test');obj._store=lambda *a:None
    monkeypatch.setattr(guided.v2.TaskBackend,'view',lambda self:dict(stamp_s=now,permission=True))
    monkeypatch.setattr(guided,'apply_guidance',lambda view,reference:dict(
        view,baseline=reference['reference'],profile_phase=reference['profile_phase']))
    result=obj.view()
    assert result['baseline']==[expected,0.]
