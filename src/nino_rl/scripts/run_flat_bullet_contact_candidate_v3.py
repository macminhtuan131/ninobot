#!/usr/bin/env python3
"""One contact-detector correction candidate after the failed fixed-geometry screen."""
from copy import deepcopy
from datetime import datetime,timezone
import fcntl,json,os,sys,shutil,re,time
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/nino_rl')]
from prepare_rough_foundations import digest,immutable
from train_rough_curriculum import Processes,assert_isolated,complete_evaluation
from run_disturbance_reference_comparisons import verify,read
SOURCE=ROOT/'rl_runs/disturbance_reference_comparisons_v1/flat'
OUTPUT=ROOT/'rl_runs/flat_bullet_contact_candidate_v3'
LIBRARY=ROOT/'build/flat_contact_probe/libnino_flat_contact_probe.so'
RESET_LIBRARY=ROOT/'build/flat_reset_probe/libnino_flat_reset_probe.so'

def status(stage,**extra):
    value=dict(stage=stage,pid=os.getpid(),utc=datetime.now(timezone.utc).isoformat(),training_started=False,optuna_held=True,**extra)
    (OUTPUT/'status.json').write_text(json.dumps(value,indent=2)+'\n');print(stage,flush=True)

def prepare():
    if (OUTPUT/'contract.json').exists():
        contract=read(OUTPUT/'contract.json');verify(contract);return contract
    source=read(SOURCE/'contract.json');verify(source)
    diagnosis=ROOT/'rl_runs/flat_contact_convergence_v3/analysis.json'
    previous=read(diagnosis)
    if not previous['complete'] or not previous['material_step_dependence']:
        raise ValueError('No completed material numerical sensitivity diagnosis')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE/'python',OUTPUT/'python',ignore=shutil.ignore_patterns('__pycache__'))
    study=read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials']
    world=Path(study['world']).read_text();config=yaml.safe_load((SOURCE/'config.yaml').read_text())
    assert config['control_hz']==10.
    profiles={}
    for label,dt in [('2ms',.002),('1ms',.001)]:
        text=world.replace('<max_step_size>0.002</max_step_size>',f'<max_step_size>{dt}</max_step_size>')
        if world.count('<max_step_size>0.002</max_step_size>')!=1:raise ValueError('Physics step anchor changed')
        # Entire geometry/materials/plugins remain identical, not just mesh paths.
        assert text.replace(f'<max_step_size>{dt}</max_step_size>','<max_step_size>0.002</max_step_size>')==world
        old='</physics>'
        text=text.replace(old,'<dart><collision_detector>bullet</collision_detector></dart>'+old,1)
        assert text.replace('<dart><collision_detector>bullet</collision_detector></dart>','').replace(
            f'<max_step_size>{dt}</max_step_size>','<max_step_size>0.002</max_step_size>')==world
        path=OUTPUT/f'world_{label}.sdf';immutable(path,text)
        cfg=deepcopy(config);cfg['policy_v2']['simulation_physics_step_seconds']=dt
        immutable(OUTPUT/f'config_{label}.yaml',yaml.safe_dump(cfg,sort_keys=False))
        profiles[label]=dict(step_seconds=dt,world=str(path),config=str(OUTPUT/f'config_{label}.yaml'))
    assets=dict(source['assets'])
    assets.update({str(p):digest(p) for p in (OUTPUT/'python/nino_rl').glob('*.py')})
    for p in [Path(__file__),diagnosis,Path(__file__).with_name('analyze_flat_contact_convergence.py'),LIBRARY,RESET_LIBRARY,*OUTPUT.glob('*.sdf'),*OUTPUT.glob('*.yaml'),
              *Path(__file__).with_name('flat_reset_probe').glob('*')]:
        if p.is_file():assets[str(p)]=digest(p)
    contract=dict(revision='flat_bullet_contact_candidate_v3',assets=assets,profiles=profiles,seeds=[65001,65004],repetitions=2,
        episodes=16,control_interval_s=.1,schedule=dict(brake_x_m=3.9,recovery_x_m=4.60,target_scale=.70,slew_per_s=.4),
        geometry='Byte identical world except max_step_size and explicit DART Bullet collision detector; robot unchanged',
        selected_correction='DART collision detector only: default to explicit Bullet; solver unchanged',
        evidence=str(diagnosis),physical_candidate_not_yet_validated=True,
        documentation='https://github.com/gazebosim/gz-sim/blob/main/tutorials/physics.md',
        instrumentation='Same contact probe plus actual joint angle/velocity readback in all episodes; no actuation writes',
        reset_stationary_threshold_rad_s=.05,reset_window_s=.10,reset_swivel_angle_tolerance_rad=.001,
        cold_start='One new simulator per measured episode; eliminate passive caster carryover',
        materiality=dict(relative_quality=.10,absolute_tracking_m=.005,absolute_penetration_m=.001),
        gates=dict(arrival_rate=1.,maximum_mean_time_s=18.5,tracking_ratio_to_full=1.05,
            minimum_quality_gain=.10,maximum_other_quality_ratio=1.),
        qualification='Two scenarios, two cold simulator repetitions per profile/step; not final 24-seed promotion',optuna_held=True)
    immutable(OUTPUT/'contract.json',json.dumps(contract,indent=2)+'\n');return contract

def main():
    os.chdir(ROOT);contract=prepare()
    lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.environ.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env=os.environ.copy();env.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',PYTHONUNBUFFERED='1')
    env['PYTHONPATH']=str(OUTPUT/'python')+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','')
    from nino_rl.tuning_trials import assert_trial_inputs
    original=read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials']
    processes=Processes(env,pi_integrator_profile='conditional_v1')
    try:
        orders=[[('2ms','full'),('1ms','schedule'),('1ms','full'),('2ms','schedule')],
                [('1ms','full'),('2ms','schedule'),('2ms','full'),('1ms','schedule')]]
        for repeat,order in enumerate(orders,1):
            for dt,profile,seed in [(dt,profile,seed) for dt,profile in order for seed in contract['seeds'][::1 if repeat==1 else -1]]:
                directory=OUTPUT/f'repeat_{repeat}'/dt/profile/f'seed_{seed}'
                if complete_evaluation(directory,1) is not None:continue
                verify(contract);assert_isolated(79,'nino_flat_79')
                status(f'repetition {repeat}/2: {dt} {profile} seed {seed}')
                cfg=contract['profiles'][dt];live=deepcopy(original);live['world']=cfg['world'];live['assets'].update(contract['assets'])
                processes.env.update(NINO_AUTHORITY_PROFILE=profile,NINO_MATCH_SCALE='1')
                processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py',
                    'world:='+cfg['world'],'world_name:=combined_flat_section','headless:=true',
                    'pi_integrator_profile:=conditional_v1','verbosity:=3'],directory/'gazebo.log')
                processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
                assert_trial_inputs(live,live=True)
                processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',cfg['config'],
                    '--timeout','60'],directory/'profile.log',timeout=65)
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    messages=re.sub(r'\x1b\[[0-9;]*m','',(directory/'gazebo.log').read_text())
                    if 'Using [bullet] collision detector' in messages:break
                    time.sleep(.25)
                else:raise ValueError('Runtime did not acknowledge Bullet after initialization; no episodes collected')
                for name,library,file in [('NinoFlatContactProbe',LIBRARY,'contacts.csv'),('NinoFlatResetProbe',RESET_LIBRARY,'joints.csv')]:
                    payload=('entity {name: "combined_flat_section" type: WORLD} plugins {'
                        'name: '+json.dumps(name)+' filename: '+json.dumps(str(library))+
                        ' innerxml: '+json.dumps(f'<output>{directory/file}</output>')+'}')
                    log=directory/(name+'.log')
                    processes.run(['gz','service','-s','/world/combined_flat_section/entity/system/add',
                        '--reqtype','gz.msgs.EntityPlugin_V','--reptype','gz.msgs.Boolean','--timeout','5000','--req',payload],log,timeout=10)
                    if 'data: true' not in log.read_text():raise ValueError('Probe not acknowledged '+name)
                processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',cfg['config'],
                    '--seeds',seed,'--baseline-speed-scale','1',
                    '--control-trace','--output',directory],directory/'evaluate.log',timeout=600)
                processes.close()
                if complete_evaluation(directory,1) is None:raise ValueError('Incomplete convergence batch')
                for file in ('joints.csv','contacts.csv'):
                    if not (directory/file).exists() or (directory/file).stat().st_size<1000:raise ValueError('Missing '+file)
        status('complete: sixteen episodes captured; analysis pending')
        processes.run([sys.executable,'src/nino_rl/scripts/analyze_flat_contact_convergence.py','--output',OUTPUT],OUTPUT/'analysis.log',timeout=180)
        result=read(OUTPUT/'analysis.json')
        status('complete: numerical review required' if result['material_step_dependence'] else 'complete: screening evaluated',
            material_step_dependence=result['material_step_dependence'],screening_gates_passed=result['screening_gates_passed'],
            flat_ppo_started=False)
    except BaseException as exc:status('interrupted; evidence preserved',error=str(exc));raise
    finally:processes.close();lock.close()

if __name__=='__main__':main()
