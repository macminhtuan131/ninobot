#!/usr/bin/env python3
"""Start one known-course pilot only after the contact candidate passes its screen."""
from copy import deepcopy
import csv,fcntl,json,os,sys,time,shutil
from pathlib import Path
import numpy as np
import yaml
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/nino_rl')]
from prepare_rough_foundations import digest,immutable
from train_rough_curriculum import Processes,assert_isolated,complete_evaluation,checkpoint_steps,newest_checkpoint
from run_disturbance_reference_comparisons import read,verify,replace
from analyze_rough_reactive_authority import window_metrics
from run_flat_quiet_tail_workflow import ACTOR
SOURCE=ROOT/'rl_runs/flat_bullet_contact_candidate_v3'
OUTPUT=ROOT/'rl_runs/flat_bullet_known_course_pilot_v1'

def status(stage,**extra):
    OUTPUT.mkdir(parents=True,exist_ok=True)
    data=dict(stage=stage,pid=os.getpid(),optuna_held=True,**extra)
    (OUTPUT/'status.json').write_text(json.dumps(data,indent=2)+'\n');print(stage,flush=True)

def prepare():
    if (OUTPUT/'learning_contract.json').exists():
        plan=read(OUTPUT/'learning_contract.json');verify(plan);return plan
    candidate=read(SOURCE/'contract.json');verify(candidate)
    result=read(SOURCE/'analysis.json')
    if not result['complete'] or not result['screening_gates_passed']:raise ValueError('Contact candidate not qualified')
    # Reuse the reviewed build routine without mutating its original snapshot.
    import run_flat_quiet_tail_workflow as builder
    source=OUTPUT/'learning_source';source.mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE/'python',source/'python',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(SOURCE/'config_2ms.yaml',source/'config.yaml')
    builder.OUTPUT=source
    config,train_source=builder.build_learning_snapshot(OUTPUT)
    package=OUTPUT/'python/nino_rl'
    path=package/'known_course_reference.py';path.write_text(replace(path.read_text(),'4.55','4.60'))
    path=package/'training_contract.py';path.write_text(replace(path.read_text(),'contract["revision"] = 50','contract["revision"] = 53'))
    config['known_course_reference']['recovery_start_x_m']=4.60
    config['physics_contract']=dict(engine='DART',collision_detector='bullet',physics_step_s=.002,
        controller_update_s=.002,control_interval_s=.1,world=SOURCE.joinpath('world_2ms.sdf').as_posix(),
        world_sha256=digest(SOURCE/'world_2ms.sdf'))
    # builder freezes config.yaml before this declared schedule/physics revision;
    # retain that intermediate preparation separately, without using it to train.
    (OUTPUT/'config.yaml').rename(OUTPUT/'builder_config.yaml')
    immutable(OUTPUT/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    for p in package.glob('*.py'):compile(p.read_text(),str(p),'exec')
    assets=dict(candidate['assets']);assets.update({str(p):digest(p) for p in package.glob('*.py')})
    for p in [Path(__file__),Path(builder.__file__),ACTOR,train_source,OUTPUT/'config.yaml',SOURCE/'analysis.json']:
        assets[str(p)]=digest(p)
    plan=dict(revision='flat_bullet_known_course_pilot_v1',training_contract_revision=53,assets=assets,
        steps=20480,seed=42,seeds=list(range(65000,65005)),source_actor=str(ACTOR),source_actor_sha256=digest(ACTOR),
        initialization='Compatible two-action actor parameters only; fresh critic/optimizer and zero counter',
        observation='Mapped cable distance/reference from estimated pose replaces downward preview; 300 values',
        action='Free speed/yaw policy with .4 scale/s ramp, no teacher action override',
        reward='Existing weights plus .25 executed-speed-reference cost; reward unit scale .01',
        world=str(SOURCE/'world_2ms.sdf'),gates=candidate['gates'],max_match_error=.03,
        qualification='Five-scenario bounded pilot, not the final 24-arrival promotion or sim-to-real validation',optuna_held=True)
    immutable(OUTPUT/'learning_contract.json',json.dumps(plan,indent=2)+'\n');return plan

def run(plan):
    from nino_rl.tuning_trials import assert_trial_inputs
    os.environ.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env=os.environ.copy();env['PYTHONPATH']=str(OUTPUT/'python')+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','')
    processes=Processes(env,pi_integrator_profile='conditional_v1')
    live=read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials'];live=deepcopy(live)
    live['world']=plan['world'];live['assets'].update(plan['assets'])
    def launch(directory,baseline=False,scale=1.):
        processes.close();verify(plan);assert_isolated(79,'nino_flat_79')
        processes.env.update(NINO_AUTHORITY_PROFILE='matched' if baseline else 'full',NINO_MATCH_SCALE=str(scale))
        processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py','world:='+plan['world'],
            'world_name:=combined_flat_section','headless:=true','pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
        processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
        assert_trial_inputs(live,live=True)
        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',OUTPUT/'config.yaml',
            '--timeout','60'],directory/'profile.log',timeout=65)
    def evaluate(label,model,baseline=False,scale=1.):
        values=[]
        for seed in plan['seeds']:
            directory=OUTPUT/label/f'seed_{seed}';batch=complete_evaluation(directory,1)
            if batch is None:
                status('evaluating '+label,seed=seed);launch(directory,baseline,scale)
                cmd=['ros2','run','nino_rl','evaluate_baseline' if baseline else 'evaluate','--config',OUTPUT/'config.yaml',
                    '--seeds',seed,'--control-trace','--output',directory]
                cmd+=['--baseline-speed-scale',scale] if baseline else ['--model',model,'--device','cuda']
                processes.run(cmd,directory/'evaluate.log',timeout=900);processes.close();batch=complete_evaluation(directory,1)
            if batch is None:raise ValueError('Incomplete cold evaluation')
            folder=next(p.parent for p in directory.glob('*/summary.json') if read(p)['complete'])
            with (folder/'episode-001/control_trace.csv').open() as stream:control=list(csv.DictReader(stream))
            e=batch[0][0]
            holding=[float(r['speed_scale']) for r in control if 4.2<=float(r['estimated_x_m'])<=4.6]
            before=[float(r['speed_scale']) for r in control if 1.<=float(r['estimated_x_m'])<3.9]
            after=[float(r['speed_scale']) for r in control if 4.9<=float(r['estimated_x_m'])<=5.7]
            behavior=dict(holding_mean=float(np.mean(holding)) if holding else None,
                cruise_mean=float(np.mean(before)) if before else None,recovered_scale=max(after) if after else None)
            behavior['slowdown_and_recovery']=bool(holding and before and after and np.mean(before)>=.95
                and np.mean(before)-np.mean(holding)>=.03 and min(holding)<=.8 and max(after)>=.95)
            values.append(dict(seed=seed,episode=e,window=window_metrics(control,[[4.1,4.8]]),behavior=behavior))
        return values
    try:
        final=list((OUTPUT/'train').glob('*/nino_ppo_final.zip'))
        if not final:
            if newest_checkpoint(OUTPUT/'train'):raise ValueError('Interrupted pilot retained; no implicit incompatible resume')
            status('training one conditional pilot',steps=20480);launch(OUTPUT/'train')
            processes.env['NINO_FLAT_TRAIN_TRACE']=str(OUTPUT/'training_trace.csv')
            processes.run(['ros2','run','nino_rl','train','--config',OUTPUT/'config.yaml','--device','cuda','--init-model',ACTOR,
                '--timesteps','20480','--checkpoint-every','4096','--check-env','--output',OUTPUT/'train'],OUTPUT/'train/train.log',timeout=10800)
            processes.close();processes.env.pop('NINO_FLAT_TRAIN_TRACE',None);final=list((OUTPUT/'train').glob('*/nino_ppo_final.zip'))
        if len(final)!=1 or checkpoint_steps(final[0])!=20480:raise ValueError('Conditional pilot budget incomplete')
        transfer=read(final[0].with_name('actor_transfer.json'))
        if transfer['source_sha256']!=plan['source_actor_sha256'] or transfer['critic']!='fresh' or transfer['optimizer']!='fresh' or transfer['training_counter']!=0:
            raise ValueError('Actor-only initialization differs')
        ppo=evaluate('ppo',final[0]);pi=evaluate('pi_full',final[0],True)
        mean=lambda rs,k:float(np.mean([float(r['episode'][k]) for r in rs]))
        scale=min(1.,mean(pi,'time_seconds')/mean(ppo,'time_seconds'));matched=evaluate('pi_matched',final[0],True,scale)
        g=plan['gates'];quality={k:mean(ppo,k)/mean(pi,k) for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
        window={k:float(np.mean([r['window'][k] for r in ppo])/np.mean([r['window'][k] for r in matched]))
            for k in ('vibration_energy_per_m','slip_energy_per_m')}
        physical=all(r['episode']['success']=='True' and float(r['episode']['truth_endpoint_error_m'])<=.2+1e-6 for r in ppo+pi+matched)
        match=abs(mean(matched,'time_seconds')/mean(ppo,'time_seconds')-1)
        passed=physical and mean(ppo,'time_seconds')<=g['maximum_mean_time_s'] and mean(ppo,'truth_path_rmse_m')<=g['tracking_ratio_to_full']*mean(pi,'truth_path_rmse_m')
        behavior_passed=all(r['behavior']['slowdown_and_recovery'] for r in ppo)
        passed=passed and behavior_passed and min(quality.values())<=.9 and max(quality.values())<=1. and min(window.values())<=.9 and max(window.values())<=1. and match<=.03
        result=dict(complete=True,pilot_screen_passed=bool(passed),physical_arrival_passed=physical,model=str(final[0]),
            ppo=ppo,pi_full=pi,pi_matched=matched,quality_ratios=quality,window_ratios_to_matched=window,matched_scale=scale,
            duration_match_error=match,slowdown_and_recovery_passed=behavior_passed,
            qualification=plan['qualification'],final_promotion=False,optuna_held=True)
        (OUTPUT/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');status('complete',pilot_screen_passed=bool(passed),optuna_held=True)
    finally:processes.close()

def main():
    os.chdir(ROOT);status('waiting for contact-numerics screen; no flat pilot started')
    lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    immutable(OUTPUT/'conditional_workflow.json',json.dumps(dict(script_sha256=digest(__file__),candidate=str(SOURCE),
        prerequisite='All sixteen candidate screening gates pass, no material timestep sensitivity',
        learning_budget=20480,optuna_held=True),indent=2)+'\n')
    deadline=time.monotonic()+14400
    while not (SOURCE/'analysis.json').exists():
        if read(SOURCE/'status.json')['stage'].startswith('interrupted'):
            status('held: contact candidate interrupted');return
        if time.monotonic()>deadline:raise TimeoutError('Contact screen deadline')
        time.sleep(5)
    result=read(SOURCE/'analysis.json')
    if not result['screening_gates_passed']:
        status('held: contact candidate failed; no flat PPO started',analysis=str(SOURCE/'analysis.json'));return
    # The contact engine is costlier; sequence learning after the rough workflow.
    rough=ROOT/'rl_runs/rough_rate_action_pilot_v2/status.json'
    while read(rough)['stage'] not in ('complete','interrupted'):
        status('contact screen passed; waiting for rough workflow to release compute')
        if time.monotonic()>deadline:raise TimeoutError('Rough workflow deadline')
        time.sleep(30)
    run(prepare())

if __name__=='__main__':
    try:main()
    except BaseException as exc:status('interrupted',error=str(exc));raise
