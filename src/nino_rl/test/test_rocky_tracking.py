"""Geometry, task and actuator checks for the continuous terrain profile."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import struct
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml
from PIL import Image

from nino_rl.core import PathTracker, RobotState, TrackingState
from nino_rl.control_v2 import decode_control, compute_reward, validate_action_mode, make_observation
from nino_rl.task_geometry import task_succeeded, approach_speed, objective_state

ROOT = Path(__file__).parents[2]
CONFIG = yaml.safe_load((ROOT / 'nino_rl/config/rocky_tracking.yaml').read_text())
PATH = PathTracker([(0.,0.), (6.,0.)])


def test_yaw_request_does_not_inject_opposing_differential_torque():
    speed, torque, yaw = decode_control([.6,.5,-.5], CONFIG)
    assert speed == pytest.approx(.8)
    np.testing.assert_allclose(torque, [.15,.15])
    assert yaw == pytest.approx(-.3)
    legacy = {'max_wheel_torque_nm':2.}
    _, old_torque, old_yaw = decode_control([.6,.5,-.5], legacy)
    np.testing.assert_allclose(old_torque, [2.,0.])
    assert old_yaw == 0.


@pytest.mark.parametrize('x,y,heading,expected', [
    (5.99,0.,0.,False), (6.01,.10,.1,True),
    (6.01,.21,0.,False), (6.01,0.,.4,False), (6.31,0.,0.,False),
])
def test_finish_gate_requires_route_completion_and_tracking(x,y,heading,expected):
    state = RobotState(x=x,y=y,yaw=heading)
    tracking = TrackingState(min(x,6.),y,heading,max(0.,6.-x),np.hypot(x-6.,y))
    assert task_succeeded(tracking,state,PATH,CONFIG) == expected
    assert approach_speed(.2,.1,heading,CONFIG) == .4


def reward(y=0., heading=0., impact=0., delta=.04):
    cfg = {**CONFIG['reward_v2'], 'torque_scale_nm': CONFIG['max_wheel_torque_nm']}
    return compute_reward(
        TrackingState(1.,y,heading,5.,5.), TrackingState(1.+delta,y,heading,5.-delta,5.-delta),
        RobotState(), [.6,0.,0.], [.6,0.,0.], [0.,0.], .1,
        {'impact_integral':impact}, cfg, impact_scale=cfg['impact_scale'])[0]


def test_reward_prefers_stable_progress_to_drift_impacts_or_standing():
    assert reward() > reward(y=.15)
    assert reward() > reward(heading=.3)
    assert reward() > reward(impact=1.)
    assert reward() > 0 > reward(delta=0.)
    assert reward(delta=-.04) < reward(delta=0.)


def test_old_models_cannot_silently_use_new_action_meanings():
    with pytest.raises(ValueError, match='action mode'):
        validate_action_mode(SimpleNamespace(nino_training_contract={'revision':30}),CONFIG)
    validate_action_mode(SimpleNamespace(nino_training_contract={'action_mode':'yaw_reference'}),CONFIG)


def test_physical_scoring_cannot_leak_truth_pose_into_actor():
    state = RobotState(x=6.1, y=.3, ground_x=6.01, ground_y=.01, ground_yaw=0.)
    action = [.6,0.,0.]
    before,_=make_observation(state,PATH,CONFIG['path']['lookahead_m'],action)
    scored=objective_state(state,CONFIG)
    _,tracking=make_observation(scored,PATH,CONFIG['path']['lookahead_m'],action)
    assert task_succeeded(tracking,scored,PATH,CONFIG)
    assert state.y==.3 and scored.y==.01
    # Changing truth affects scoring, but cannot change any sensor observation.
    state.ground_x,state.ground_y,state.ground_yaw=1.,2.,1.
    after,_=make_observation(state,PATH,CONFIG['path']['lookahead_m'],action)
    np.testing.assert_array_equal(before,after)


def test_enclosure_preserved_and_single_rolling_ground():
    old = ET.parse(ROOT/'nino_description/worlds/long_hall.sdf')
    new = ET.parse(ROOT/'nino_description/worlds/rocky_hall.sdf')
    for name in ('left_wall','right_wall','rear_wall','front_wall','ceiling'):
        old_shape=old.find(f".//collision[@name='{name}_collision']")
        new_shape=new.find(f".//collision[@name='{name}_collision']")
        old_pose = [float(v) for v in old_shape.findtext('pose').split()]
        new_pose = [float(v) for v in new_shape.findtext('pose').split()]
        old_size = [float(v) for v in old_shape.findtext('geometry/box/size').split()]
        new_size = [float(v) for v in new_shape.findtext('geometry/box/size').split()]
        assert old_pose[:2] == new_pose[:2]
        assert old_size[:2] == new_size[:2]
        if name != 'ceiling':
            assert new_pose[2] - new_size[2] / 2 <= -.3 + 1e-8
        else:
            assert new_pose == old_pose and new_size == old_size
    assert new.find(".//model[@name='cable_bumps']") is None
    assert new.find(".//model[@name='embedded_rock_bed']") is None
    assert new.findtext('.//scene/grid') == 'false'
    terrain=new.find(".//model[@name='continuous_rocky_ground']")
    assert len(terrain.findall('.//collision'))==1
    assert len(terrain.findall('.//visual'))==1
    collision=terrain.find('.//collision')
    visual=terrain.find('.//visual')
    mesh_uri = 'model://nino_description/terrains/rocky_ground.stl'
    assert collision.findtext('geometry/mesh/uri') == mesh_uri
    assert visual.findtext('geometry/mesh/uri') == mesh_uri
    assert collision.findtext('pose') == visual.findtext('pose')
    assert collision.find('geometry/heightmap') is None
    for name, expected in [('spawn_floor','2.800000 4 0.1'),('goal_floor','1.500000 4 0.1')]:
        slab=new.find(f".//collision[@name='{name}_collision']")
        assert slab.findtext('geometry/box/size') == expected
    meta=json.loads((ROOT/'nino_description/worlds/rocky_hall.json').read_text())
    assert meta['terrain_type']=='shared collision and visual mesh'
    assert meta['profile']=='rolling hills with dense mounds and shallow hollows'
    assert meta['dense_spot_shape']=='asymmetric mounds and shallow rimmed bowls'
    assert meta['local_spot_count']==12
    assert meta['track_spot_count']==15
    assert meta['dense_spot_count']==128
    assert meta['dense_mound_count']==63
    assert meta['dense_hollow_count']==65
    assert meta['route_dense_mound_count']==16
    assert meta['route_dense_hollow_count']==16
    assert meta['dense_relief_scale'] > .95
    assert meta['active_x_m']==[.8,30.5]
    assert meta['clear_width_m']==4.
    assert meta['goal_xy_m']==[6.,0.]
    assert meta['heightmap_pixels']==513
    assert min(meta['height_range_m']) < -.16 < .24 < max(meta['height_range_m'])
    assert meta['maximum_surface_grade'] <= .60 + 1e-8
    pixels=np.asarray(Image.open(ROOT/'nino_description/terrains/rocky_height.png'))
    assert pixels.shape==(513,513) and pixels.std()>5
    source=ROOT/'nino_description/scripts/generate_rocky_world.py'
    spec=importlib.util.spec_from_file_location('rocky_world_generator',source)
    generator=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    dense=generator.dense_spots(42)
    assert len(dense)==128
    assert all(abs(spot[1])<=.17 for spot in dense[::4])
    assert min(spot[0] for spot in dense)<2 and max(spot[0] for spot in dense)>29
    assert len({round(spot[5],1) for spot in dense})>30
    assert sum(spot[2]>0 for spot in dense[::4])==16
    assert sum(spot[2]<0 for spot in dense[::4])==16
    assert (pixels[:,0]==pixels[0,0]).all()
    assert (pixels[:,-1]==pixels[0,0]).all()
    mesh=(ROOT/'nino_description/terrains/rocky_ground.stl').read_bytes()
    facets=struct.unpack_from('<I',mesh,80)[0]
    assert facets==2*256*256
    assert len(mesh)==84+50*facets
