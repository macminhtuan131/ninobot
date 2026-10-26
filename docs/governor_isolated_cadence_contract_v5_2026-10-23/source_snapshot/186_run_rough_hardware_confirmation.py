#!/usr/bin/env python3
"""Confirm fixed E1/N1/S1 PI on actual friction/mass profiles; no Optuna."""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import sys
import subprocess
import xml.etree.ElementTree as ET

from prepare_rough_foundations import ROOT, digest, immutable
from run_hardware_sensor_preflight import BASE, OUTPUT as SENSOR, prepare as sensor_prepare

OUTPUT=ROOT/'rl_runs/rough_hardware_confirmation_v1'
SEEDS=[13010,13011,13012]


def prepare(output):
    import yaml
    config,sensor=sensor_prepare(SENSOR)
    output.mkdir(parents=True,exist_ok=True)
    saved=output/'confirmation_contract.json'
    if saved.exists():
        plan=json.loads(saved.read_text())
        verify(plan)
        return config,plan
    profiles={}
    for profile in ('nominal','low_friction','heavy'):
        directory=output/'physics'/profile
        robot=ET.parse(BASE/f'physics/{profile}/robot.urdf').getroot()
        for block in robot.findall('gazebo'):
            for s in list(block.findall('sensor')):
                if s.get('name') in ('terrain_preview_sensor','rough_localization_lidar'):block.remove(s)
        immutable(directory/'robot.urdf',ET.tostring(robot,encoding='utf-8',xml_declaration=True))
        sdf=subprocess.check_output(['gz','sdf','-p',str(directory/'robot.urdf')],text=True,stderr=subprocess.PIPE)
        immutable(directory/'robot.sdf',sdf)
        parsed=ET.fromstring(sdf)
        mu=[float(parsed.find(f"model/link[@name='{side}_wheel_link']/collision/surface/friction/ode/mu").text)
            for side in ('left','right')]
        sensors=[s.get('name') for s in parsed.findall('model/link/sensor')]
        if set(sensors)!={'imu_sensor','gpu_lidar'}:raise ValueError('Unavailable sensor in physical profile')
        sim=(SENSOR/'sim.launch.py').read_text().replace(str(SENSOR/'robot.urdf'),str(directory/'robot.urdf'))
        immutable(directory/'sim.launch.py',sim)
        launch=(SENSOR/'training_sim.launch.py').read_text().replace(str(SENSOR/'sim.launch.py'),str(directory/'sim.launch.py'))
        immutable(directory/'training_sim.launch.py',launch)
        profiles[profile]=dict(launch=str(directory/'training_sim.launch.py'),drive_mu=mu,
            mass_multiplier=1.15 if profile=='heavy' else 1.,active_sensors=sensors)
    assets={str(p):digest(p) for p in (output/'physics').rglob('*') if p.is_file()}
    assets.update(sensor['assets']);assets.update(sensor['implementation'])
    plan=dict(revision='rough_hardware_confirmation_v1',seeds=SEEDS,routes=['E1','N1','S1'],
        profiles=profiles,assets=assets,implementation={str(Path(__file__)):digest(__file__)},
        world=str(BASE/'worlds/half_relief.sdf'),config=str(SENSOR/'config.yaml'),
        overlay=str(SENSOR/'python'),scoring='unchanged physical arrival, route order, localization and .05m mean tracking gate',
        scope='3 seeds per route/profile: 27 PI episodes, not a final robustness estimate',optuna_held=True)
    immutable(saved,json.dumps(plan,indent=2)+'\n')
    return config,plan


def verify(plan):
    for group in (plan['assets'],plan['implementation']):
        for path,expected in group.items():
            if digest(path)!=expected:raise ValueError('Confirmation input changed: '+path)


def make_processes(environment,launch,bridge):
    from train_rough_curriculum import Processes
    class HardwareProcesses(Processes):
        def launch(self,world,directory,gui=False):
            self.close()
            self.env['NINO_ROUGH_LOCALIZATION_LOG']=str(directory/'wall_observations.jsonl')
            self.env['NINO_ROUGH_RECOVERY_LOG']=str(directory/'recovery_events.jsonl')
            self.world=self.start(['ros2','launch',launch,f'world:={world}',
                'world_name:=combined_rough_section',f'headless:={str(not gui).lower()}',
                'pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
            self.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
            self.start(['ros2','run','ros_gz_bridge','parameter_bridge','--ros-args',
                '-r','__node:=hardware_imu_bridge','-p',f'config_file:={bridge}'],directory/'imu_bridge.log')
            self.run(['ros2','topic','echo','/rough/imu/data','sensor_msgs/msg/Imu','--once',
                '--qos-reliability','reliable','--field','header.stamp'],directory/'imu_readiness.log',timeout=30)
    return HardwareProcesses(environment,pi_integrator_profile='conditional_v1')


def report(output,results,stage):
    from run_rough_trial8_validation import write
    ready=len(results)==9 and all(x['gate']['passed'] for x in results.values())
    write(output/'status.json',dict(stage=stage,pid=os.getpid(),batches=results,feasibility_passed=ready,
        optuna_held=True,pilot_allowed=ready))
    lines=['# Hardware-only rough PI confirmation','','Stage: '+stage,'',
        'Three seeds per E1/N1/S1 route on nominal, low-friction and +15% mass/inertia profiles. '
        'Fixed half-relief terrain; horizontal LiDAR/IMU/encoders; independent physical scoring.','',
        '| Profile / route | Arrival | Physical RMSE m | Mean pose error m | Passed |',
        '|---|---:|---:|---:|---:|']
    for key,data in results.items():
        g=data['gate'];lines.append(f"| {key} | {g['physical_arrival_rate']:.0%} | {g['truth_path_rmse_m']:.4f} | {g['max_episode_mean_pose_disagreement_m']:.4f} | {g['passed']} |")
    lines+=['','Feasibility passed: '+str(ready)+'. Optuna remains held. '
        'A passing batch authorizes only the bounded learning pilot, not a sim-to-real or generalization claim.']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return ready


def run(output,config,plan):
    from run_rough_trial8_validation import Validation,route_readiness,write
    from train_rough_curriculum import complete_evaluation,assert_isolated
    validation=Validation(output/'validation')
    env=validation.base_env.copy();env['PYTHONPATH']=plan['overlay']+os.pathsep+env.get('PYTHONPATH','')
    write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
    results={}
    for profile in plan['profiles']:
        processes=make_processes(env.copy(),plan['profiles'][profile]['launch'],SENSOR/'imu_bridge.yaml')
        try:
            for route in plan['routes']:
                directory=output/'pi'/profile/route;directory.mkdir(parents=True,exist_ok=True)
                key=profile+'/'+route;report(output,results,'evaluating '+key)
                if complete_evaluation(directory,len(SEEDS)) is None:
                    verify(plan);validation.check(Path(plan['overlay']))
                    if processes.world is None:
                        assert_isolated(78,'nino_rough_78');processes.launch(plan['world'],directory)
                        live=deepcopy(validation.old_contract['comparable_trials'])
                        live['world']=plan['world'];live['assets'].update(plan['assets'])
                        validation.assert_inputs(live,live=True)
                        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py',
                            '--config',plan['config'],'--timeout','60'],directory/'profile.log',timeout=65)
                    processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',plan['config'],
                        '--route',route,'--seeds',*SEEDS,'--control-trace','--output',directory],
                        directory/'evaluate.log',timeout=600)
                rows,summary=complete_evaluation(directory,len(SEEDS))
                results[key]=dict(gate=route_readiness(rows,config,len(SEEDS)),summary=summary,directory=str(directory))
                print(key,results[key]['gate'],flush=True)
                report(output,results,'completed '+key)
        finally:processes.close()
    ready=report(output,results,'complete')
    write(output/'feasibility_result.json',dict(passed=ready,batches=results,
        contract_sha256=digest(output/'confirmation_contract.json'),optuna_held=True))
    return ready


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args();os.chdir(ROOT)
    output=args.output.resolve();config,plan=prepare(output)
    print('Prepared confirmation',output,flush=True)
    if args.run:
        lock=(output/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not run(output,config,plan):raise SystemExit('Feasibility failed; PPO and Optuna remain held')


if __name__=='__main__':main()
