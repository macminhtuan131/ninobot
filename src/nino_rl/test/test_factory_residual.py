"""Factory adapter gates; no Gazebo/ROS process launched by these tests."""
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from nino_rl.core import load_config
from nino_rl.factory_velocity_backend import FactoryVelocityBackend
from nino_rl.residual_experiment import experiment_contract
from nino_rl.residual_factory_workflow import prepare,repo


def config():return load_config(repo()/'src/nino_rl/config/residual_factory_td3_smoke.yaml')


def test_factory_contract_is_distinct_from_hardware_and_old_fixture():
    c=config();contract=experiment_contract(c)
    assert contract['observation_size']==100 and contract['history_frames']==5
    assert c['nominal_geometry']==dict(radius_l=.0625,radius_r=.0625,separation=.34273666)
    assert c['imu_yaw_rad']==0 and c['hardware_authority']==0
    assert c['backend']['accept_torque'] is False
    assert c['training']['allowed'] is False
    assert c['smoke']['learning_transitions']==128
    assert not any('truth' in field or 'contact' in field for field in contract['features'])


def test_world_preparation_preserves_factory_physical_collision(tmp_path,monkeypatch):
    from ament_index_python import packages
    installed={}
    for name in ('nino_description','nino_control'):
        share=tmp_path/'install'/name/'share'/name;share.parent.mkdir(parents=True);share.symlink_to(repo()/'src'/name,target_is_directory=True)
        installed[name]=share
    helper=tmp_path/'install/nino_description/lib/nino_description/gz_sim_clean';helper.parent.mkdir(parents=True)
    helper.symlink_to(repo()/'src/nino_description/scripts/gz_sim_clean')
    monkeypatch.setattr(packages,'get_package_share_directory',lambda name:str(installed[name]))
    c,path=prepare(tmp_path)
    source=ET.parse(repo()/'src/nino_description/worlds/factory_floor_mixed.sdf')
    prepared=ET.parse(path)
    for model in ('factory_contact_floor','cable_bumps','enclosed_hall'):
        original=source.find(".//model[@name='"+model+"']")
        actual=prepared.find(".//model[@name='"+model+"']")
        assert ET.tostring(original)==ET.tostring(actual)
    assert prepared.find(".//plugin[@name='gz::sim::systems::Contact']") is not None
    assert len(prepared.findall('.//collision'))==len(source.findall('.//collision'))


def test_physics_requires_exact_completion_without_retry(tmp_path):
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf');calls=[]
    def control(request):calls.append(request);b.iterations+=50;b.clock+=.05;return True
    b._control=control;b.step_world(50)
    assert b.time==pytest.approx(.05) and len(calls)==1
    def overstep(request):calls.append(request);b.iterations+=51;b.clock+=.051
    b._control=overstep
    with pytest.raises(RuntimeError,match='overstepped'):b.step_world(50)
    assert len(calls)==2  # No automatic retry of the bad request.


def test_missing_or_future_source_is_not_valid_boundary_feedback(tmp_path,monkeypatch):
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf')
    b.messages={k:dict(stamp_s=.99) for k in ('imu','wheel','truth','drive')}
    assert all(v==pytest.approx(.01) for v in b._wait_feedback(1.).values())
    b.messages['wheel']['stamp_s']=1.01
    times=iter([0.,0.,6.]);monkeypatch.setattr('nino_rl.factory_velocity_backend.time.monotonic',lambda:next(times))
    with pytest.raises(RuntimeError,match='lags'):b._wait_feedback(1.)


def test_episode_budget_is_enforced_before_new_launch(tmp_path):
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf');b.episode=1
    with pytest.raises(RuntimeError,match='episode budget'):b.reset(seed=7)
    assert b.node is None and b.launch is None


def test_settling_requires_continuous_quiet_and_is_bounded(tmp_path):
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf');b.episode_dir=tmp_path
    b.messages={'truth':dict(values=dict(speed_norm=0.,yaw_rate=0.,roll=0.,pitch=0.)), 'wheel':dict(values=[0.,0.])}
    b._wait_feedback=lambda _:None
    def step(_):b.time+=.05
    b.step_world=step;b.settle();assert b.time==pytest.approx(.5)
    b.time=0.;b.messages['wheel']['values']=[1.,0.]
    with pytest.raises(RuntimeError,match='settling gate'):b.settle()
    assert b.time==pytest.approx(5.)


def test_lost_ack_requires_full_independent_clock_proof_and_no_retry(tmp_path,monkeypatch):
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf');b.episode_dir=tmp_path;calls=[]
    def executed_lost_ack(steps):calls.append(steps);b.iterations+=steps;b.clock+=steps*.001;return False
    b._control=executed_lost_ack;b.step_world(50)
    assert len(calls)==1 and b.time==pytest.approx(.05)
    def not_executed(steps):calls.append(steps);return False
    b._control=not_executed;times=iter([0.,0.,16.,16.])
    monkeypatch.setattr('nino_rl.factory_velocity_backend.time.monotonic',lambda:next(times))
    with pytest.raises(TimeoutError,match='never retry'):b.step_world(50)
    assert len(calls)==2
