#!/usr/bin/env python3
"""PI feasibility with only horizontal lidar, IMU and encoders; no learning.

Virtual downward and multi-channel lidars are removed from the spawned robot.
Known corridor walls remain a localization prior, not a terrain preview.
"""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

from prepare_rough_foundations import ROOT, SOURCE, ROBOT, digest, immutable

BASE = ROOT/'rl_runs/foundations_20261011/rough_v6'
OUTPUT = ROOT/'rl_runs/foundations_20261011/hardware_sensors_v2'


def replace(code, old, new):
    if code.count(old) != 1:
        raise ValueError('Unexpected frozen source anchor: '+old[:80])
    return code.replace(old,new)


def prepare(output):
    import yaml
    base=json.loads((BASE/'foundation_contract.json').read_text())
    for group in (base['assets'],base['implementation']):
        for path,expected in group.items():
            if digest(path)!=expected:
                raise ValueError('Foundation input changed: '+path)
    saved=output/'sensor_contract.json'
    if saved.exists():
        previous=json.loads(saved.read_text())
        for group in (previous['assets'],previous['implementation']):
            for path,expected in group.items():
                if digest(path)!=expected:
                    raise ValueError('Sensor preflight input changed: '+path)
        return yaml.safe_load((output/'config.yaml').read_text()),previous
    output.mkdir(parents=True,exist_ok=True)
    package=output/'python/nino_rl'
    if not package.exists():
        shutil.copytree(SOURCE/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'))
    control=(SOURCE/'python/nino_rl/control_v2.py').read_text()
    control=replace(control,'FRAME_SIZE = 60','FRAME_SIZE = 56')
    control=replace(control,
        '    terrain = np.zeros(4) if preview is None else np.asarray(preview)',
        '    # Hardware has no downward sensor. Preview is never an actor input.')
    control=replace(control,
        '                                  [vertical_acceleration(state, includes_gravity) / 10.0],\n                                  terrain)',
        '                                  [vertical_acceleration(state, includes_gravity) / 10.0])')
    env=(SOURCE/'python/nino_rl/ros_env.py').read_text()
    env=replace(env,'        preview = self.ros.terrain_preview(timeout=None)',
        '        preview = None  # Hardware-only actor: never read virtual preview.')
    contract=(SOURCE/'python/nino_rl/training_contract.py').read_text()
    contract=replace(contract,'    return contract\n',
        '    if "hardware_sensor_contract" not in config:\n'
        '        raise ValueError("Hardware preflight requires its sensor contract")\n'
        '    contract["revision"] = 42\n'
        '    contract["hardware_sensor_contract"] = config["hardware_sensor_contract"]\n'
        '    contract["observation_interface"] = "56/frame; no downward preview; 280 history"\n'
        '    return contract\n')
    for name,code in {'control_v2.py':control,'ros_env.py':env,'training_contract.py':contract,
            'train.py':'def main():\n    raise RuntimeError("PI sensor preflight only; freeze a learning contract after validation")\n'}.items():
        compile(code,name,'exec')
        (package/name).write_text(code)
    robot=ET.parse(BASE/'physics/nominal/robot.urdf').getroot()
    removed=[]
    for gazebo in robot.findall('gazebo'):
        for sensor in list(gazebo.findall('sensor')):
            if sensor.get('name') in ('terrain_preview_sensor','rough_localization_lidar'):
                removed.append(sensor.get('name'));gazebo.remove(sensor)
    if sorted(removed)!=['rough_localization_lidar','terrain_preview_sensor']:
        raise ValueError('Expected both unavailable virtual sensors')
    sensors=[s.get('name') for s in robot.findall('gazebo/sensor')]
    if sorted(set(sensors))!=['gpu_lidar','imu_sensor']:
        raise ValueError('Unexpected active robot sensors: '+str(sensors))
    immutable(output/'robot.urdf',ET.tostring(robot,encoding='utf-8',xml_declaration=True))
    # Keep physical links/inertias/collisions identical to nominal contact screen.
    sim=(ROBOT.parent/'sim.launch.py').read_text().replace(str(ROBOT),str(output/'robot.urdf'))
    immutable(output/'sim.launch.py',sim)
    launch=(ROBOT.parent/'training_sim.launch.py').read_text().replace(
        str(ROBOT.parent/'sim.launch.py'),str(output/'sim.launch.py'))
    immutable(output/'training_sim.launch.py',launch)
    bridge=yaml.safe_load((ROBOT.parent/'imu_bridge.yaml').read_text())
    bridge=[row for row in bridge if row['ros_type_name']=='sensor_msgs/msg/Imu']
    if len(bridge)!=1:raise ValueError('Expected exactly one reliable IMU bridge')
    immutable(output/'imu_bridge.yaml',yaml.safe_dump(bridge,sort_keys=False))
    config=yaml.safe_load((BASE/'config.yaml').read_text())
    config.pop('foundation_contract')
    config.pop('rough_experiment_sensor',None)
    walls=config['odometry_assistance']['corridor_lidar']
    walls.pop('pointcloud_topic')
    for key in list(walls):
        if key.startswith('cloud_'):walls.pop(key)
    config['odometry_assistance']['revision']='horizontal_lidar_imu_encoder_preflight_v1'
    config['rough_experiment']['localization_sensor']='horizontal_lidar_only'
    # Stage 2 exposes all three fixed routes for preflight, without learning
    # or changing each route's path, controller settings or physical gates.
    config['rough_runtime']['stage_index']=2
    config['policy_v2']['require_terrain_preview']=False
    config['hardware_sensor_contract']=dict(
        available=['horizontal_lidar','imu','wheel_encoders'],
        excluded=['downward_terrain_preview','multi_channel_wall_cloud'],
        frame_size=56,history_size=280,
        localization_prior='known rectangular corridor walls and calibrated laser mount',
        actor_initialization='old observation models incompatible; no learning in this preflight',
        terrain='half_relief',physical_scoring='unchanged ground truth scoring; not actor/localizer input')
    immutable(output/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets={str(p):digest(p) for p in sorted(output.rglob('*')) if p.is_file() and
        p.suffix in ('.py','.urdf','.yaml') and '__pycache__' not in str(p)}
    assets.update(base['assets'])
    assets.update({str(p):digest(p) for p in (SOURCE/'config.yaml',ROBOT)})
    result=dict(revision='hardware_sensor_preflight_v2',assets=assets,
        implementation={str(Path(__file__)):digest(__file__)},
        active_sensors=sensors,removed_sensors=removed,actor=config['hardware_sensor_contract'],
        checks='PI E1/N1/S1 on unchanged half-relief geometry; no learning or tuning',
        limitations='Known rectangular walls are a map prior; horizontal scan may lose wall coverage under tilt. No claim of unseen pothole preview.')
    immutable(saved,json.dumps(result,indent=2)+'\n')
    return config,result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--routes',nargs='+',choices=['E1','N1','S1'],default=['E1','N1','S1'])
    args=parser.parse_args();os.chdir(ROOT)
    output=args.output.resolve()
    config,contract=prepare(output)
    print('Prepared hardware-only sensor preflight:',output,flush=True)
    if not args.run:return
    lock=(output/'runner.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from run_rough_trial8_validation import Validation, write, route_readiness
    from train_rough_curriculum import Processes, complete_evaluation, assert_isolated
    validation=Validation(output/'validation')
    class HardwareProcesses(Processes):
        def launch(self,world,directory,gui):
            self.close()
            self.env['NINO_ROUGH_LOCALIZATION_LOG']=str(directory/'wall_observations.jsonl')
            self.env['NINO_ROUGH_RECOVERY_LOG']=str(directory/'recovery_events.jsonl')
            self.world=self.start(['ros2','launch',output/'training_sim.launch.py',f'world:={world}',
                'world_name:=combined_rough_section','headless:=true','pi_integrator_profile:=conditional_v1'],
                directory/'gazebo.log')
            self.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
            self.start(['ros2','run','ros_gz_bridge','parameter_bridge','--ros-args','-r',
                '__node:=hardware_imu_bridge','-p',f'config_file:={output/"imu_bridge.yaml"}'],directory/'imu_bridge.log')
            self.run(['ros2','topic','echo','/rough/imu/data','sensor_msgs/msg/Imu','--once',
                '--qos-reliability','reliable','--field','header.stamp'],directory/'imu_readiness.log',timeout=30)
    validation.processes=HardwareProcesses(validation.base_env.copy(),pi_integrator_profile='conditional_v1')
    validation.world=BASE/'worlds/half_relief.sdf'
    validation.base_env['PYTHONPATH']=str(output/'python')+os.pathsep+validation.base_env.get('PYTHONPATH','')
    write(validation.output/'correction_contract.json',dict(snapshot_assets=contract['assets']))
    results={}
    try:
        for route in args.routes:
            directory=output/'pi'/route;directory.mkdir(parents=True,exist_ok=True)
            if complete_evaluation(directory,1) is None:
                validation.processes.close();assert_isolated(78,'nino_rough_78')
                validation.check(output/'python')
                validation.processes.env=validation.base_env.copy()
                validation.processes.launch(validation.world,directory,False)
                live=deepcopy(validation.old_contract['comparable_trials'])
                live['world']=str(validation.world);live['assets'].update(contract['assets'])
                validation.assert_inputs(live,live=True)
                validation.processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py',
                    '--config',output/'config.yaml','--timeout','60'],directory/'profile.log',timeout=65)
                validation.processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',output/'config.yaml',
                    '--route',route,'--seeds','13000','--control-trace','--output',directory],
                    directory/'evaluate.log',timeout=300)
            rows,summary=complete_evaluation(directory,1)
            results[route]=dict(summary=summary,gate=route_readiness(rows,config,1))
            write(output/'screen_results.json',dict(routes=results,
                qualification='One seed per route; hardware sensor feasibility screen only, not robust training approval',
                pilot_allowed=False,optuna_allowed=False))
            print(route,results[route]['gate'],flush=True)
    finally:
        validation.processes.close()


if __name__=='__main__':main()
