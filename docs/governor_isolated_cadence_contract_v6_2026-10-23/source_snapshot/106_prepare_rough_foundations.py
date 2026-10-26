#!/usr/bin/env python3
"""Prepare an isolated, physically changed foundation contract; optionally screen N1.

Never overwrites a map, checkpoint or Optuna study. No learning or tuning here.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'rl_runs/rough_n1_heading_braking_v20'
ROBOT = ROOT/'rl_runs/rough_wall_recovery_v16/rough_robot.urdf.xacro'
OUTPUT = ROOT/'rl_runs/foundations_20261011/rough_v6'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def immutable(path, data):
    data = data.encode() if isinstance(data,str) else data
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Foundation input changed; choose a new output: ' + str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)


def scaled_mesh(source, fraction):
    """Scale actual triangle elevations, recomputing normals; keep XY and topology."""
    import numpy as np
    data=Path(source).read_bytes()
    count=struct.unpack_from('<I',data,80)[0]
    if len(data) != 84+count*50:
        raise ValueError('Expected binary STL')
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    triangles=np.frombuffer(data, dtype=dtype, offset=84).copy()
    triangles['vertices'][:,:,2] *= fraction
    v=triangles['vertices']
    normal=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0])
    length=np.linalg.norm(normal,axis=1)
    if (length==0).any():
        raise ValueError('Degenerate terrain triangle')
    triangles['normal']=normal/length[:,None]
    return (b'Nino foundation: 50 percent relief, same triangle collision/visual'.ljust(80,b'\0')+
            struct.pack('<I',count)+triangles.tobytes()), dict(triangles=count,
                height_range_m=[float(v[:,:,2].min()),float(v[:,:,2].max())],
                maximum_triangle_grade=float(np.linalg.norm(normal[:,:2],axis=1).__truediv__(np.abs(normal[:,2])).max()))


def prepare(output):
    import yaml
    from terrain_preview_foundation import calibration_from_urdf, patch_interface
    output.mkdir(parents=True,exist_ok=True)
    saved=output/'foundation_contract.json'
    if saved.exists():
        previous=json.loads(saved.read_text())
        for group in (previous['assets'],previous['implementation']):
            for path,expected in group.items():
                if digest(path)!=expected:
                    raise ValueError('Frozen foundation changed; choose a new output: '+path)
    urdf=subprocess.check_output(['xacro',str(ROBOT)],text=True)
    calibration=calibration_from_urdf(urdf)
    overlay=output/'python'
    if not overlay.exists():
        shutil.copytree(SOURCE/'python',overlay,ignore=shutil.ignore_patterns('__pycache__'))
    original=(SOURCE/'python/nino_rl/ros_interface.py').read_text()
    changes={'ros_interface.py':patch_interface(original,calibration),
             'terrain_preview_foundation.py':Path(__file__).with_name('terrain_preview_foundation.py').read_text()}
    original=(SOURCE/'python/nino_rl/control_v2.py').read_text()
    changes['control_v2.py']=original.replace('FRAME_SIZE = 60','FRAME_SIZE = 63').replace(
        'terrain = np.zeros(4)', 'terrain = np.zeros(7)').replace(
        '# Preview is [distance/1m, left height/0.1m, right height/0.1m, valid].',
        '# Calibrated preview: separate distance/height/valid per side, overall valid.')
    original=(SOURCE/'python/nino_rl/training_contract.py').read_text()
    if original.count('    return contract\n')!=1:
        raise ValueError('Unexpected training contract')
    changes['training_contract.py']=original.replace('    return contract\n',
        '    if "foundation_contract" not in config:\n'
        '        raise ValueError("Foundation overlay requires its own contract")\n'
        '    contract["revision"] = 41\n'
        '    contract["observation_interface"] = "63 values/frame; calibrated seven-value preview"\n'
        '    return contract\n')
    original=(SOURCE/'python/nino_rl/ros_env.py').read_text()
    anchor='            timeout=self.simulation_step_timeout\n        )\n        truth = self.ros.snapshot()'
    if original.count(anchor)!=1:
        raise ValueError('Unexpected episode epoch anchor')
    changes['ros_env.py']=original.replace(anchor,
        '            timeout=self.simulation_step_timeout\n        )\n'
        '        # The epoch clears IMU/preview history after the first reset refresh.\n'
        '        # Collect a paired post-epoch scan/attitude with motors stopped,\n'
        '        # then select time zero from the actual paused clock.\n'
        '        self.ros.refresh_reset_sensors(["imu", "terrain", "ground_truth", "scan"],\n'
        '            timeout=self.sensor_timeout, step_timeout=self.simulation_step_timeout)\n'
        '        self.lockstep_sim_time = self.ros.wait_for_clock_quiescence(\n'
        '            timeout=self.simulation_step_timeout)\n'
        '        truth = self.ros.snapshot()')
    # The initial clone contains originals; only preparation may replace these
    # declared files. A stored manifest forbids subsequent silent changes.
    if (output/'foundation_contract.json').exists():
        old=json.loads((output/'foundation_contract.json').read_text())
        for path, expected in old['assets'].items():
            if digest(path)!=expected:
                raise ValueError('Frozen foundation asset changed: '+path)
    for path in (overlay/'nino_rl').glob('*.py'):
        expected=changes.get(path.name, (SOURCE/'python/nino_rl'/path.name).read_text()
                             if (SOURCE/'python/nino_rl'/path.name).exists() else None)
        if expected is None:
            raise ValueError('Undeclared overlay module')
        if path.name not in changes and path.read_text()!=expected:
            raise ValueError('Undeclared overlay modification')
    for name, code in changes.items():
        compile(code,name,'exec')
        (overlay/'nino_rl'/name).write_text(code)
    mesh, stats=scaled_mesh(ROOT/'rl_runs/rough_terrain_bank_v1/meshes/original.stl',.5)
    immutable(output/'meshes/half_relief.stl',mesh)
    world=ET.parse(ROOT/'rl_runs/rough_terrain_bank_v1/worlds/original.sdf')
    for kind in ('visual','collision'):
        world.find(f"world/model[@name='rough_approach_ground']/link/{kind}/geometry/mesh/uri").text=(output/'meshes/half_relief.stl').as_uri()
    immutable(output/'worlds/half_relief.sdf',ET.tostring(world.getroot(),encoding='utf-8',xml_declaration=True))
    profiles={}
    # Real URDF properties, converted to SDF and checked before a launch.
    # These bounds are simulation screening values, not measured hardware distributions.
    for name, friction, mass in [('nominal',1.2,1.),('low_friction',.6,1.),('heavy',1.2,1.15)]:
        robot=ET.fromstring(urdf)
        for side in ('left','right'):
            surface=robot.find(f"gazebo[@reference='{side}_wheel_link']")
            for key in ('mu1','mu2'):
                surface.find(key).text=str(friction)
        for inertial in robot.findall('link/inertial'):
            node=inertial.find('mass'); node.set('value',str(float(node.get('value'))*mass))
            inertia=inertial.find('inertia')
            for key,value in inertia.attrib.items():
                inertia.set(key,str(float(value)*mass))
        robot_path=output/f'physics/{name}/robot.urdf'
        immutable(robot_path,ET.tostring(robot,encoding='utf-8',xml_declaration=True))
        sdf=subprocess.check_output(['gz','sdf','-p',str(robot_path)],text=True,stderr=subprocess.PIPE)
        parsed=ET.fromstring(sdf)
        observed=[]
        for side in ('left','right'):
            link=parsed.find(f"model/link[@name='{side}_wheel_link']")
            mu=link.find('collision/surface/friction/ode/mu')
            if mu is None or abs(float(mu.text)-friction)>1e-6:
                raise ValueError('Drive friction did not survive URDF->SDF conversion')
            observed.append(float(mu.text))
        immutable(output/f'physics/{name}/robot.sdf',sdf)
        sim=(ROBOT.parent/'sim.launch.py').read_text().replace(str(ROBOT),str(robot_path))
        immutable(output/f'physics/{name}/sim.launch.py',sim)
        training=(ROBOT.parent/'training_sim.launch.py').read_text().replace(
            str(ROBOT.parent/'sim.launch.py'),str(output/f'physics/{name}/sim.launch.py'))
        immutable(output/f'physics/{name}/training_sim.launch.py',training)
        profiles[name]=dict(drive_friction=observed,mass_and_inertia_multiplier=mass,
            launch=str(output/f'physics/{name}/training_sim.launch.py'),
            applied_to='URDF/SDF wheel contact and link mass/inertia; zero residual torque is permitted',
            physical_response_verified=False)
    config=yaml.safe_load((SOURCE/'config.yaml').read_text())
    config['rough_runtime']['stage_index']=1
    config['rough_runtime']['terrain_variant_id']='half_relief'
    config['rough_runtime']['bank_digest']=hashlib.sha256(mesh).hexdigest()
    # PI does not use preview. Audit missing terrain information separately;
    # this contact screen cannot qualify a masked sample for training.
    config['policy_v2']['require_terrain_preview']=False
    config['foundation_contract']=dict(revision='rough_foundations_v1',preview=calibration,
        observation_frame=63,terrain='half_relief',physics_profiles=profiles,
        actor_transfer='incompatible observation contract; fresh actor or explicit tested input remapping required',
        use='PI contact feasibility only; mandatory preview decoupled and audited; no training',
        scoring='independent physical arrival and ordered route gates unchanged')
    immutable(output/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    # Fingerprint inputs only. Completed evaluation outputs must not change the
    # prepared contract when another physical profile is screened.
    candidates=[output/'config.yaml']
    for folder in ('python','physics','meshes','worlds'):
        candidates.extend(p for p in (output/folder).rglob('*') if p.is_file() and
            p.suffix in ('.py','.sdf','.stl','.urdf') and '__pycache__' not in str(p))
    assets={str(path):digest(path) for path in sorted(candidates)}
    contract=dict(revision='rough_foundations_v1',calibration=calibration,terrain=stats,physics_profiles=profiles,
        source_config_sha256=digest(SOURCE/'config.yaml'),source_robot_sha256=digest(ROBOT),assets=assets,
        implementation={str(Path(__file__)):digest(__file__),
            str(Path(__file__).with_name('terrain_preview_foundation.py')):digest(Path(__file__).with_name('terrain_preview_foundation.py'))},
        gates=dict(contact_feasibility='no sustained chassis-supported stall; complete N1 then E1/S1 physical checks',
            preview='tilt/known-plane math, then live sensor coverage and validity audit',
            randomization='distinct converted SDF plus measured physical response under zero RL residual',
            authority='paired crossing-quality response to scripted speed/acceleration intervention',
            pilot='only after the foundation and authority gates pass'))
    immutable(output/'foundation_contract.json',json.dumps(contract,indent=2)+'\n')
    return config,contract


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--screen',action='store_true')
    parser.add_argument('--profile',choices=['nominal','low_friction','heavy'],default='nominal')
    args=parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/nino_rl')]
    config,contract=prepare(args.output.resolve())
    print('Prepared',args.output,flush=True)
    if not args.screen:
        return
    from run_rough_trial8_validation import Validation,write
    from rough_localized_processes import ReliableRoughProcesses
    from train_rough_curriculum import complete_evaluation
    output=args.output.resolve()
    class PhysicalValidation(Validation):
        def launch(self,directory,config_path,overlay=None):
            from train_rough_curriculum import assert_isolated
            self.check(overlay)  # Preserve and verify the historical source offline.
            for group in (contract['assets'],contract['implementation']):
                for path,expected in group.items():
                    if digest(path)!=expected:
                        raise ValueError('Foundation input changed: '+path)
            self.processes.close()
            assert_isolated(78,'nino_rough_78')
            self.processes.env=self.base_env.copy()
            self.processes.env['PYTHONPATH']=str(overlay)+os.pathsep+self.base_env.get('PYTHONPATH','')
            self.processes.launch(self.world,directory,False)
            live=deepcopy(self.old_contract['comparable_trials'])
            live['world']=str(self.world)
            live['assets'].update(contract['assets'])
            # This is a zero-update physical screen, not a trial in the old study.
            self.assert_inputs(live,live=True)
            self.processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py',
                '--config',config_path,'--timeout','60'],directory/'profile.log',timeout=65)
    validation=PhysicalValidation(output/('screen_'+args.profile))
    class PhysicalProfileProcesses(ReliableRoughProcesses):
        def start(self,command,*values,**keywords):
            command=list(command)
            old=str(ROBOT.parent/'training_sim.launch.py')
            command=[contract['physics_profiles'][args.profile]['launch'] if str(v)==old else v for v in command]
            return super().start(command,*values,**keywords)
    validation.processes=PhysicalProfileProcesses(validation.base_env,pi_integrator_profile='conditional_v1')
    validation.config=config
    validation.base_env['NINO_PREVIEW_AUDIT']=str(validation.output/'preview.jsonl')
    validation.world=output/'worlds/half_relief.sdf'
    write(validation.output/'correction_contract.json',dict(snapshot_assets=contract['assets']))
    directory=validation.output/'evaluation'
    directory.mkdir(parents=True,exist_ok=True)
    try:
        if complete_evaluation(directory,1) is None:
            validation.launch(directory,output/'config.yaml',output/'python')
            library=ROOT/'build/rough_contact_probe/libnino_rough_contact_probe.so'
            payload=('entity {name: "combined_rough_section" type: WORLD} plugins {name: "NinoContactProbe" filename: '+
                json.dumps(str(library))+' innerxml: '+json.dumps(f'<output>{validation.output/"contacts.csv"}</output>')+'}')
            validation.processes.run(['gz','service','-s','/world/combined_rough_section/entity/system/add',
                '--reqtype','gz.msgs.EntityPlugin_V','--reptype','gz.msgs.Boolean','--timeout','5000','--req',payload],
                validation.output/'probe.log',timeout=10)
            if 'data: true' not in (validation.output/'probe.log').read_text():
                raise RuntimeError('Contact probe not acknowledged')
            validation.processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',output/'config.yaml',
                '--route','N1','--seeds','13000','--control-trace','--output',directory],
                validation.output/'evaluate.log',timeout=300)
        result=complete_evaluation(directory,1)
        if result is None:
            raise RuntimeError('Incomplete physical screening')
        rows,summary=result
        write(validation.output/'screen_result.json',dict(summary=summary,
            passed=summary['success_rate']==1.,
            qualification='single-seed mechanical screen only; not curriculum or training approval'))
        print('Physical arrival',summary['success_rate'],flush=True)
    finally:
        validation.processes.close()


if __name__=='__main__':
    main()
