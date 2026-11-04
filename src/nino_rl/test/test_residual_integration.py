"""Meaningful contract/causality/transition and system-ID checks, no robot."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np
import pytest
from nino_control.residual_pipeline import ObservationAssembler,ResidualPipeline
from nino_control.residual_velocity import FEATURES,actor_contract
from nino_control.residual_actor import PortableActor
from nino_rl.residual_experiment import make_environment
from nino_rl.residual_workflow import default_config
from nino_rl.velocity_backend import VelocityBackend
from nino_rl.residual_sysid import fit,response


def test_source_duplicate_cannot_renew_freshness_and_mounting_is_shared():
    c=default_config();a=ObservationAssembler(c['nominal_geometry'],.2,np.pi/2)
    for channel,payload in [('imu',(0.,0.,.2,1.,0.,9.8)),('wheel',(1.,2.)),('baseline',(.05,0.)),('final',(.04,0.)),('status',dict(permission=True,fault=False,emergency_stop=False))]:
        assert a.push(channel,payload,1.,1.)
    assert not a.push('imu',(0.,)*6,1.1,1.)
    view=a.view(1.15);assert view['input_ages_s']['imu']==pytest.approx(.15)
    assert view['features']['accel_y_m_s2']==pytest.approx(1.)
    assert view['actual_actuator_target'] is None
    with pytest.raises(ValueError,match='Stale'):a.view(1.21)


def test_history_stores_only_policy_contribution_not_baseline_ramp():
    c=default_config();b=VelocityBackend(c);view,_=b.reset(seed=1);p=ResidualPipeline(c);p.observe(view)
    for i in range(12):
        trace=p.project((.8,.2),.1,0.)
        assert trace['accepted_policy_delta_wheel_m_s']==(0.,0.)
        assert p.accepted==(0.,0.)
        view,*_=b.advance_reference(*trace['body_reference'],.1);obs=p.observe(view)
        assert obs[-20+14:-20+16]==(0.,0.)
    assert any(trace['baseline_shaping_delta_wheel_m_s'])
    assert p.history.ready
    b.close()


def test_gym_checker_and_proposal_reaches_target_but_truth_not_actor():
    from stable_baselines3.common.env_checker import check_env
    c=default_config();e=make_environment(c,VelocityBackend(c));check_env(e,skip_render_check=True);e.close()
    results=[]
    for proposal in [(0.,0.),(.7,-.3)]:
        e=make_environment(c,VelocityBackend(c));obs,_=e.reset(seed=4)
        for _ in range(32):obs,r,t,tr,info=e.step(np.array(proposal,dtype=np.float32))
        results.append(info['feedback_wheel_rad_s'])
        assert info['reference_trace']['proposal']==pytest.approx(proposal)
        assert len(obs)==100 and not set(FEATURES)&{'truth_pose_m_rad','contact_force'}
        e.close()
    assert np.linalg.norm(np.array(results[0])-results[1])>.1


def test_fault_is_terminal_failure_and_time_limit_is_truncated():
    c=default_config();b=VelocityBackend(c);e=make_environment(c,b);e.reset(seed=2)
    e.pipeline.last_view['fault']=True
    _,r,t,tr,info=e.step(np.zeros(2,dtype=np.float32))
    assert t and not tr and r==-10 and info['reference_trace']['body_reference']==(0.,0.)
    with pytest.raises(RuntimeError):e.step(np.zeros(2,dtype=np.float32))
    e.close();c['backend']['horizon_s']=.2;e=make_environment(c,VelocityBackend(c));e.reset(seed=2)
    e.step(np.zeros(2,dtype=np.float32));_,_,t,tr,_=e.step(np.zeros(2,dtype=np.float32));assert tr and not t;e.close()


def test_portable_actor_rejects_weights_corruption_and_abi_change():
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder);np.savez(p/'actor.npz',w=np.zeros((2,100),dtype=np.float32),b=np.array([.2,-.4],dtype=np.float32))
        meta=dict(abi_sha256='abc',observation_size=100,layers=[dict(kind='linear',weight='w',bias='b')],weights_sha256=hashlib.sha256((p/'actor.npz').read_bytes()).hexdigest())
        (p/'actor.json').write_text(json.dumps(meta));actor=PortableActor(p,'abc')
        np.testing.assert_allclose(actor(np.zeros(100)),[.2,-.4])
        with pytest.raises(ValueError,match='ABI'):PortableActor(p,'other')
        (p/'actor.npz').write_bytes(b'bad')
        with pytest.raises(ValueError,match='hash'):PortableActor(p,'abc')


def test_sysid_recovers_synthetic_lag_with_whole_session_holdout():
    geometry=dict(radius_l=.06,radius_r=.06,separation=.345);data={}
    for name,amplitude in [('train1',.05),('train2',.06),('hold',.055)]:
        t=np.arange(0.,6.,.02);u=np.where((t>=1)&(t<3),amplitude,0.)
        rows=np.column_stack((t,u,t*0,t*0,t*0))
        for wheel,gain,tau in [(0,.96,.15),(1,1.03,.21)]:rows[:,3+wheel]=gain*response(rows,wheel,geometry,.08,tau)
        data[name]=rows
    result=fit(data,dict(held_out_sessions=['hold'],nominal_geometry=geometry,time_basis='common_receipt_clock'))
    assert result['held_out_sessions']==['hold'] and result['fit_sessions']==['train1','train2']
    assert result['calibration_status'].startswith('candidate') and not result['controller_parameters_changed']
    for model in result['models']:
        assert abs(model['combined_delay_s']-.08)<=.02
        assert model['held_out'][0]['rmse_rad_s']<.03


def test_governor_uses_proxy_only_when_actual_target_missing():
    c=default_config();b=VelocityBackend(c);v,_=b.reset(seed=2);v['actual_actuator_target']=None
    p=ResidualPipeline(c,governor=True);p.observe(v);trace=p.project((0.,0.),.1,0.)
    assert trace['actuator_target_readback'] is None
    assert not trace['governor']['wheel_error_channel_available'];b.close()
