#!/usr/bin/env python3
"""Check the prepared actor's isolation from unavailable/privileged inputs."""
import argparse
import ast
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,default=Path(__file__).resolve().parents[3]/
        'rl_runs/foundations_20261011/hardware_sensors_v2')
    root=parser.parse_args().snapshot.resolve()
    if any(key=='nino_rl' or key.startswith('nino_rl.') for key in sys.modules):
        raise RuntimeError('Use a fresh Python process to avoid importing a different policy contract')
    sys.path.insert(0,str(root/'python'))
    import numpy as np
    import yaml
    from nino_rl.core import RobotState,PathTracker
    from nino_rl.control_v2 import make_observation,BASELINE_ACTION,ObservationHistory
    from nino_rl.corridor_odometry import CorridorOdometry
    config=yaml.safe_load((root/'config.yaml').read_text())
    assert not config['policy_v2']['require_terrain_preview']
    lookahead=config['path']['lookahead_m']
    state=RobotState(accel_z=9.80665);path=PathTracker([(0,0),(10,0)])
    a,_=make_observation(state,path,lookahead,BASELINE_ACTION,preview=[1,2,3,1])
    state.ground_linear_velocity=50.;state.ground_yaw_rate=10.
    b,_=make_observation(state,path,lookahead,BASELINE_ACTION,preview=[float('nan')]*4)
    assert a.shape==(56,);np.testing.assert_array_equal(a,b)
    assert ObservationHistory(5).reset(a).shape==(280,)
    code=ast.parse((root/'python/nino_rl/ros_env.py').read_text())
    method=next(n for c in code.body if isinstance(c,ast.ClassDef) for n in c.body
        if isinstance(n,ast.FunctionDef) and n.name=='_actor_observation')
    module=ast.Module(body=[method],type_ignores=[]);namespace={'make_observation':make_observation}
    exec(compile(ast.fix_missing_locations(module),'actor-isolation','exec'),namespace)
    class NoPreview:
        imu_includes_gravity=True
        def terrain_preview(self,*args,**kwargs):raise AssertionError('Virtual preview read')
    env=SimpleNamespace(ros=NoPreview(),config=config,path=path,lookahead=lookahead)
    np.testing.assert_array_equal(namespace['_actor_observation'](env,state,BASELINE_ACTION,None),a)
    assert not CorridorOdometry(config['odometry_assistance']).use_pointcloud
    sensors=ET.parse(root/'robot.urdf').getroot().findall('gazebo/sensor')
    assert set(n.get('name') for n in sensors)=={'gpu_lidar','imu_sensor'}
    try:
        importlib.import_module('nino_rl.train').main()
    except RuntimeError as exc:
        assert 'PI sensor preflight only' in str(exc)
    else:
        raise AssertionError('Preflight unexpectedly permits training')
    result=dict(preview_injection_no_effect=True,ground_truth_velocity_injection_no_effect=True,
        actor_calls_no_preview_api=True,wall_estimator_uses_no_cloud=True,
        training_disabled=True,frame_size=56,history_size=280,active_sensors=[n.get('name') for n in sensors])
    (root/'sensor_integrity.json').write_text(json.dumps(result,indent=2)+'\n');print(result)


if __name__=='__main__':main()
