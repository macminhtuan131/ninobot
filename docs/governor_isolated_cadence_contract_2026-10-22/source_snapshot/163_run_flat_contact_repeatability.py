#!/usr/bin/env python3
"""Read-only contact repetition of two problematic cable scenarios. No learning."""
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/nino_rl')]
from prepare_rough_foundations import digest, immutable
from run_disturbance_reference_comparisons import verify, read
from train_rough_curriculum import Processes, assert_isolated, complete_evaluation

OUTPUT=ROOT/'rl_runs/flat_contact_repeatability_v1'
SOURCE=ROOT/'rl_runs/disturbance_reference_comparisons_v1/flat'
LIBRARY=ROOT/'build/flat_contact_probe/libnino_flat_contact_probe.so'

def status(stage,**extra):
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'status.json').write_text(json.dumps(dict(stage=stage,pid=os.getpid(),
        utc=datetime.now(timezone.utc).isoformat(),training_started=False,optuna_held=True,**extra),indent=2)+'\n')
    print(stage,flush=True)

def prepare():
    if (OUTPUT/'contract.json').exists():
        contract=read(OUTPUT/'contract.json'); verify(contract); return contract
    source=read(SOURCE/'contract.json');verify(source)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE/'python',OUTPUT/'python',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(SOURCE/'config.yaml',OUTPUT/'config.yaml')
    path=OUTPUT/'python/nino_rl/crossing_authority.py'
    code=path.read_text();old='4.45+.15'
    if code.count(old)!=1:raise ValueError('Unexpected schedule implementation')
    path.write_text(code.replace(old,"float(os.environ.get('NINO_RECOVERY_START', '4.60'))"))
    assets=dict(source['assets'])
    assets.update({str(p):digest(p) for p in (OUTPUT/'python/nino_rl').glob('*.py')})
    for p in [OUTPUT/'config.yaml',LIBRARY,Path(__file__),*Path(__file__).with_name('flat_contact_probe').glob('*')]:
        if p.is_file():assets[str(p)]=digest(p)
    contract=dict(revision='flat_contact_repeatability_v1',assets=assets,seeds=[65001,65004],
        repetitions=3,profiles=['full','old_460','new_455','matched'],
        matched_scale=17.58/18.30,source_protocol=source['protocol'],
        capture='Robot contact and collision pose every 2 ms; no forces or actuation changed',
        cold_start='Each profile/repetition starts a new simulator; seed order alternates',
        controller='Same frozen wheel PI and estimator; only pre-existing speed schedules compared',
        training_started=False,optuna_held=True,scope='Repeatability on two saved scenarios, not unseen-map validation')
    immutable(OUTPUT/'contract.json',json.dumps(contract,indent=2)+'\n');return contract

def main():
    os.chdir(ROOT);contract=prepare()
    os.environ.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',
        ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env=os.environ.copy();env['PYTHONPATH']=str(OUTPUT/'python')+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','')
    from nino_rl.tuning_trials import assert_trial_inputs
    study=read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials']
    processes=Processes(env,pi_integrator_profile='conditional_v1')
    try:
        for repeat,order in enumerate([['full','old_460','new_455','matched'],
                                      ['matched','new_455','old_460','full'],
                                      ['old_460','full','matched','new_455']]):
            seeds=contract['seeds'][::1 if repeat%2==0 else -1]
            for label in order:
                directory=OUTPUT/f'repeat_{repeat+1}'/label
                if complete_evaluation(directory,2) is not None:continue
                verify(contract);assert_isolated(79,'nino_flat_79')
                status(f'contact repetition {repeat+1}/3: {label}')
                profile='schedule' if label in ('old_460','new_455') else label
                scale=contract['matched_scale'] if label=='matched' else 1.
                processes.env.update(NINO_AUTHORITY_PROFILE=profile,NINO_MATCH_SCALE=str(scale),
                    NINO_RECOVERY_START='4.55' if label=='new_455' else '4.60')
                processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py',
                    f'world:={study["world"]}','world_name:=combined_flat_section','headless:=true',
                    'pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
                processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
                assert_trial_inputs(study,live=True)
                processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',OUTPUT/'config.yaml',
                    '--timeout','60'],directory/'profile.log',timeout=65)
                payload=('entity {name: "combined_flat_section" type: WORLD} plugins {'
                    'name: "NinoFlatContactProbe" filename: '+json.dumps(str(LIBRARY))+
                    ' innerxml: '+json.dumps(f'<output>{directory/"contacts.csv"}</output>')+'}')
                processes.run(['gz','service','-s','/world/combined_flat_section/entity/system/add',
                    '--reqtype','gz.msgs.EntityPlugin_V','--reptype','gz.msgs.Boolean','--timeout','5000',
                    '--req',payload],directory/'probe.log',timeout=10)
                if 'data: true' not in (directory/'probe.log').read_text():raise ValueError('Contact plugin not acknowledged')
                processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',OUTPUT/'config.yaml',
                    '--seeds',*seeds,'--baseline-speed-scale',scale,'--control-trace','--output',directory],
                    directory/'evaluate.log',timeout=500)
                processes.close()
                if complete_evaluation(directory,2) is None:raise ValueError('Incomplete contact batch')
                if not (directory/'contacts.csv').exists() or (directory/'contacts.csv').stat().st_size<1000:
                    raise ValueError('Missing actual contact evidence')
        status('complete: contacts captured; analysis pending')
    except BaseException as exc:
        status('interrupted; evidence preserved',error=str(exc));raise
    finally:processes.close()

if __name__=='__main__':main()
