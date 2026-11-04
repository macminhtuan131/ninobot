"""Causal path reference and real ResidualPipeline handoff, offline only."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import math
import pytest
from nino_rl.core import load_config
from nino_rl.residual_guidance import GuidanceReference, PoseSample, apply_guidance
from nino_rl.residual_sim_task import config as task_config
from nino_control.residual_pipeline import ObservationAssembler, ResidualPipeline
from nino_control.residual_velocity import FEATURES, actor_contract


def cfg():
    return load_config(Path(__file__).resolve().parents[1]/'config/residual_guidance_v1.yaml')


def pose(t=0., x=0., y=0., yaw=0.):
    return PoseSample(x,y,yaw,t,t,'odom','wheel_imu_odometry','declared_common_control_clock','fixture')


def test_follower_corrects_lateral_and_heading_without_policy_pose_input():
    c=cfg();g=GuidanceReference(c,epoch='fixture');g.update_pose(pose(y=.1))
    r=g.command(0.,permission=True)
    assert r['reference'][0]>0 and r['reference'][1]<0 and r['valid']
    assert not r['oracle']
    g.reset(epoch='fixture');g.update_pose(pose(yaw=-.2))
    assert g.command(0.,permission=True)['reference'][1]>0
    g.reset(epoch='fixture');g.update_pose(pose(x=1.49))
    assert g.command(0.,permission=True)['reference']==[0.,0.]


def test_duplicate_does_not_renew_pose_lease_and_stale_latches():
    g=GuidanceReference(cfg(),epoch='fixture');p=pose();g.update_pose(p)
    assert not g.update_pose(replace(p,receipt_s=.19))
    assert g.command(.21,permission=True)['fault']
    with pytest.raises(ValueError,match='explicit reset'):g.update_pose(pose(.3))
    g.reset(epoch='fixture');g.update_pose(pose(.3))
    assert g.command(.3,permission=True)['valid']


@pytest.mark.parametrize('field,value',[('source_id','sim_truth_oracle'),('frame_id','map'),('clock_id','another_clock'),('epoch','old_epoch'),('x_m',math.nan)])
def test_bad_pose_contract_fails_closed(field,value):
    g=GuidanceReference(cfg(),epoch='fixture')
    with pytest.raises(ValueError):g.update_pose(replace(pose(),**{field:value}))
    assert g.command(0.,permission=True)['reference']==[0.,0.]
    assert g.command(.1,permission=True)['fault']


def test_oracle_requires_explicit_separate_identity_and_is_labelled():
    c=cfg();c['pose_source']='sim_truth_oracle'
    with pytest.raises(ValueError,match='oracle'):GuidanceReference(c,epoch='fixture')
    c['allow_sim_truth_oracle']=True;g=GuidanceReference(c,epoch='fixture')
    g.update_pose(replace(pose(),source_id='sim_truth_oracle'))
    assert g.command(0.,permission=True)['oracle']
    assert g.contract['sha256']!=GuidanceReference(cfg(),epoch='fixture').contract['sha256']


def test_actual_pipeline_handoff_preserves_abi_feedback_and_stops_stale_guidance():
    c=task_config();g=GuidanceReference(cfg(),epoch='fixture')
    assembler=ObservationAssembler(c['nominal_geometry']);pipeline=ResidualPipeline(c)
    abi=actor_contract(c)['abi_sha256']
    for i in range(30):
        t=i*.1;g.update_pose(pose(t,y=.1))
        for channel,values in [('imu',[0.,0.,0.,0.,0.,9.80665]),('wheel',[1.,1.]),('baseline',[.2,0.]),('final',[.1,0.]),
                               ('status',dict(permission=True,fault=False,emergency_stop=False))]:
            assembler.push(channel,values,t,t,'base_footprint' if channel=='baseline' else None)
        view=assembler.view(t);view['clock_id']=cfg()['clock_id'];view['actual_actuator_target']=[2.,2.]
        guided=apply_guidance(view,g.command(t,permission=True))
        observation=pipeline.observe(guided);trace=pipeline.project([0.,0.],.1,0.)
        assert len(observation)==100 and len(FEATURES)==20
        assert guided['features']['last_final_v_m_s']==.1 and guided['actual_actuator_target']==[2.,2.]
        assert guided['features']['baseline_yaw_rad_s']<0
        assert view['baseline']==(.2,0.)  # Original measurement view is immutable.
    assert trace['body_reference'][1]<0 and not pipeline.reference.latched
    # Make all sensor clocks fresh but leave the independent pose stale.
    for i in range(30,33):
        t=i*.1
        for channel,values in [('imu',[0.,0.,0.,0.,0.,9.80665]),('wheel',[1.,1.]),('baseline',[.2,0.]),('final',[.1,0.]),
                               ('status',dict(permission=True,fault=False,emergency_stop=False))]:
            assembler.push(channel,values,t,t,'base_footprint' if channel=='baseline' else None)
        view=assembler.view(t);view['clock_id']=cfg()['clock_id']
        guided=apply_guidance(view,g.command(t,permission=True))
        pipeline.observe(guided);trace=pipeline.project([0.,0.],.1,1.)
    assert pipeline.reference.latched and trace['body_reference']==(0.,0.)
    assert actor_contract(c)['abi_sha256']==abi


def test_clock_frame_owner_stop_and_corridor_are_explicit():
    g=GuidanceReference(cfg(),epoch='fixture');g.update_pose(pose())
    assert not g.command(0.,permission=False)['permission']
    assert not g.command(.1,permission=True,stop_requested=True)['permission']
    g.reset(epoch='fixture');g.update_pose(pose(y=.5))
    assert not g.command(0.,permission=True)['valid']
    g.reset(epoch='fixture');g.update_pose(pose())
    r=g.command(0.,permission=True)
    with pytest.raises(ValueError,match='clock identity'):
        apply_guidance(dict(stamp_s=0.),r)
