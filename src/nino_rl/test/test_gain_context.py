"""New context and actual wrapper parity; no actor, ROS init or Gazebo."""
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from nino_rl import gain_context as c
from nino_rl.gain_context_preflight import wrapper_parity,fixture_backend
from nino_rl.gain_factory_backend import GainReadinessBackend
from nino_rl.gain_reference_map import diagnostic_support


@pytest.fixture(scope='module')
def paired():
    return wrapper_parity()


def test_actual103_wrapper_parity_all_baselines_140_decisions(paired):
    results,traces=paired
    assert len(results)==3 and sum(r['old_and_new_transitions'] for r in results)==840
    assert all(r['observations_rewards_projection_terminal_exact'] for r in results)
    assert all(len(rows)==140 for rows in traces)


def test_new_context_rejects_old_same_shape_checkpoint_identity():
    assert c.identity()['abi_sha256']!=c.contract.identity()['abi_sha256']
    with pytest.raises(ValueError,match='no old103D'):c.require_identity(c.contract.identity())


@pytest.mark.parametrize('gain',[.98,1.,1.02])
def test_condition_not_embedded_in_observation_abi(gain):
    config,_,_,_=c.configuration(gain)
    assert config['backend']['sim_common_gain']==gain
    assert 'sim_common_gain' not in str(c.identity()['observation'])
    assert c.identity()['conditions_not_controller_inputs']


def test_evaluation_gain_metadata_cannot_change_received_observation():
    config,_,task,cond=c.configuration(1.)
    a=c.environment(config,fixture_backend(config),task,cond)
    b=c.environment(config,fixture_backend(config),task,cond)
    original=b.env.backend.advance_reference
    def metadata_only(*args,**kwargs):
        view,labels,t,u,info=original(*args,**kwargs)
        info['evaluation_gain']=987.;info['gain_map_audit']['common_gain']=987.
        return view,labels,t,u,info
    b.env.backend.advance_reference=metadata_only
    try:
        x,_=a.reset(seed=701);y,_=b.reset(seed=701);np.testing.assert_array_equal(x,y)
        for _ in range(6):
            x,*_=a.step(np.zeros(1,np.float32));y,*_=b.step(np.zeros(1,np.float32))
            np.testing.assert_array_equal(x,y)
    finally:a.close();b.close()


@pytest.mark.parametrize('fault',['double','hidden_source','target','future','effective','clip','oldabi'])
def test_validator_rejects_gain_telemetry_or_source_drift(paired,fault):
    row=deepcopy(paired[1][0][40]);previous=paired[1][0][39]
    if fault=='double':row['gain_map_audit']['map_calls_this_update']=2
    if fault=='hidden_source':row['reference_trace']['source_samples']['gain']={'values':1.}
    if fault=='target':row['applied_target_rad_s'][0]+=.1
    if fault=='future':row['gain_map_audit']['sim_time_s']+=1.
    if fault=='effective':row['gain_map_audit']['effective_linear_m_s']+=.01
    if fault=='clip':row['gain_map_audit']['speed_clip_required']=1.
    if fault=='oldabi':row['abi_sha256']=c.contract.identity()['abi_sha256']
    with pytest.raises((ValueError,AssertionError)):
        c.verify_transition(row,previous,row['sensor_clock_s']-row['task']['elapsed_s'],1.,expected_identity=c.identity())


def test_no_physics_release_fails_before_output_or_io(tmp_path):
    with pytest.raises(ValueError,match='no physics release'):
        GainReadinessBackend({},tmp_path/'unused',None,None,None,None,None)
    assert not (tmp_path/'unused').exists()


def test_only_baselines_can_request_actions(paired):
    row=paired[1][0][40]
    with pytest.raises(ValueError,match='no actor'):
        c.request('TD3',row['equal_observation'],dict(radius_l=.0625,radius_r=.0625))


def test_source_nanosecond_support_does_not_relax_or_fabricate_freshness():
    assert diagnostic_support(2.3,2.3,2.34)
    assert not diagnostic_support(2.3,2.3,2.340000001)
    assert not diagnostic_support(2.300000001,2.300000001,2.3)
    assert not diagnostic_support(2.3,2.300000001,2.3)


@pytest.mark.parametrize('state',['ready','missing','different_stamp','wrong_gain'])
def test_backend_requires_matched_gain_ack_without_extra_physics(state,monkeypatch):
    from types import SimpleNamespace
    import threading
    from nino_rl import gain_factory_backend as module
    from nino_rl.drive_readiness_candidate import DriveReadinessBackend
    monkeypatch.setattr(DriveReadinessBackend,'_wait_feedback',lambda *a:dict(wheel=0.,imu=0.))
    ticks=iter(i*.5 for i in range(30))
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda *a:None)
    messages=dict(drive=dict(stamp_s=2.3),gain_map=dict(stamp_s=2.3,values=dict(common_gain=1.)))
    if state=='missing':messages.pop('gain_map')
    if state=='different_stamp':messages['gain_map']['stamp_s']=2.299
    if state=='wrong_gain':messages['gain_map']['values']['common_gain']=.98
    obj=object.__new__(GainReadinessBackend)
    obj.__dict__.update(messages=messages,sim_common_gain=1.,lock=threading.RLock(),_check=lambda:None)
    if state=='ready':assert GainReadinessBackend._wait_feedback(obj,2.3)['gain_map']==0.
    else:
        with pytest.raises((ValueError,RuntimeError)):GainReadinessBackend._wait_feedback(obj,2.3)
