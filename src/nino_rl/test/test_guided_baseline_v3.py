"""Causal estimator and V3 handoff semantics; no Gazebo or learner."""
from copy import deepcopy
from pathlib import Path
import math
import numpy as np
import pytest
from nino_rl.causal_planar_estimator import CausalPlanarEstimator
from nino_rl import residual_guided_baseline as v3


def estimator():
    e=CausalPlanarEstimator(radius_l=.0625,radius_r=.0625)
    e.reset(stamp_s=0.,pose=[0.,0.,0.],epoch='fixture');return e


def test_future_wheel_is_never_used_for_earlier_gyro():
    e=estimator();e.push('wheel',0.,[1.,1.],10.)
    e.push('wheel',.04,[2.,2.],10.1);e.push('imu',.02,[0.],10.2)
    rows=e.advance(.02)
    assert rows[0]['wheel_stamp_s']==0. and rows[0]['pose'][0]==pytest.approx(.0625*.02)
    assert e.estimate()['stamp_s']==.02
    e.push('imu',.04,[0.5],10.3);rows=e.advance(.04)
    assert rows[0]['wheel_stamp_s']==.04 and rows[0]['pose'][2]==pytest.approx(.01)
    assert rows[0]['truth_input'] is False


def test_duplicates_do_not_reintegrate_and_initial_pose_is_explicit():
    e=estimator();e.push('wheel',0.,[1.,1.],10.);e.push('imu',.02,[1.],10.1)
    assert not e.push('imu',.02,[1.],20.)
    assert len(e.advance(.02))==1 and not e.advance(.02)
    assert 'not_truth_readback' in e.estimate()['initialization']
    with pytest.raises(ValueError,match='Only gyro-Z'):e.push('truth',.03,[9.,9.],10.)
    with pytest.raises(ValueError,match='reversal'):e.push('imu',.01,[1.],21.)


def test_missing_stale_or_gapped_support_fails_instead_of_extrapolation():
    e=estimator();e.push('wheel',.03,[1.,1.],10.);e.push('imu',.02,[0.],10.1)
    with pytest.raises(ValueError,match='No causal wheel'):e.advance(.02)
    e=estimator();e.push('wheel',0.,[1.,1.],10.);e.push('imu',.06,[0.],10.1)
    with pytest.raises(ValueError,match='gyro source gap'):e.advance(.06)
    e=estimator();e.push('wheel',0.,[1.,1.],10.)
    for t in [.02,.04,.06]:e.push('imu',t,[0.],10.+t)
    with pytest.raises(ValueError,match='wheel support stale'):e.advance(.06)


def test_planar_integration_rotates_forward_velocity_using_gyro_only():
    e=estimator()
    for i in range(51):e.push('wheel',i*.02,[1.6,1.6],100.+i*.02)
    for i in range(1,51):e.push('imu',i*.02,[1.],200.+i*.02)
    e.advance(1.);p=e.estimate()['pose']
    assert p[2]==pytest.approx(1.)
    assert p[0]==pytest.approx(.1*math.sin(1.),abs=2e-6)
    assert p[1]==pytest.approx(.1*(1-math.cos(1.)),abs=2e-6)


def test_budget_no_actor_and_heading_error_comes_from_rotated_path():
    p=v3.protocol();assert len(p['order'])==8 and p['maximum_transitions']==1120
    assert p['training_transitions']==0 and p['initial_pose_m_rad']==[0.,0.,0.]
    c,g=v3.configuration(p['order'][0],p)
    assert c['simulation_authority']==0 and c['training']['allowed'] is False
    assert c['actor']['history_frames']==5 and not c['reward_weights']
    assert math.atan2(*g['path_points_m'][1][::-1])==pytest.approx(math.radians(5.))
    assert g['pose_source']=='wheel_imu_odometry' and not g['allow_sim_truth_oracle']


def sample():
    return dict(truth_pose_m_rad=[1.,0.,0.],body_speed_m_s=0.,body_yaw_rad_s=0.,body_speed_norm_m_s=0.,
        feedback_wheel_rad_s=[0.,0.],estimator_audit=dict(pose=[1.,0.,0.]),
        reference_trace=dict(original_baseline_body=[0.,0.],accepted_reference_wheel_m_s=[0.,0.]))


def test_score_uses_declared_path_and_stop_not_reward_world_y():
    p=v3.protocol();condition=p['order'][0];c,_=v3.configuration(condition,p)
    score=v3.BaselineScore(c,p,condition);r=sample()
    for i in range(20):reward,task=score.update(r,12.1+i*.1,False)
    assert task['cross_track_m']==pytest.approx(-math.sin(math.radians(5.)))
    assert task['task_success'] and task['stop_completed']
    assert reward==0 and set(task['reward_terms'])=={'velocity_tracking','yaw_tracking'}


def test_environment_forbids_any_residual_action_before_physics(monkeypatch):
    import gymnasium as gym
    class Fake(gym.Env):
        observation_space=gym.spaces.Box(-5.,5.,(100,),np.float32)
        action_space=gym.spaces.Box(-1.,1.,(2,),np.float32)
        def reset(self,**kwargs):return np.zeros(100,np.float32),{}
        def step(self,action):pytest.fail('No physics step for prohibited action')
    monkeypatch.setattr(v3,'make_environment',lambda *a:Fake())
    p=v3.protocol();condition=p['order'][0];c,_=v3.configuration(condition,p)
    e=v3.environment(c,object(),p,condition);e.reset()
    with pytest.raises(ValueError,match='forbids'):e.step([.01,0.])


def test_existing_batch_does_not_reopen_budget(tmp_path,monkeypatch):
    monkeypatch.setattr(v3.Path,'home',lambda:tmp_path)
    root=tmp_path/'batch';root.mkdir();(root/'state.json').write_text('{}')
    with pytest.raises(ValueError,match='already closed'):v3.run(root)
