#!/usr/bin/env python3
"""One evidence-selected schedule test; conditional known-course PPO and focused study."""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/nino_rl')]
from prepare_rough_foundations import digest,immutable
from run_disturbance_reference_comparisons import read,verify,replace,analyze_flat,metrics
from audit_flat_schedule import SOURCE,OUTPUT as AUDIT

OUTPUT=ROOT/'rl_runs/flat_quiet_tail_correction_v2'
ACTOR=ROOT/'rl_runs/flat_targeted_actor_pilot_v1/train/20261010-002632-975129/nino_ppo_final.zip'


def status(output,stage,**extra):
    from datetime import datetime,timezone
    output.mkdir(parents=True,exist_ok=True)
    data=dict(stage=stage,pid=os.getpid(),updated_utc=datetime.now(timezone.utc).isoformat(),optuna_held=True)
    data.update(extra)
    temporary=output/'status.tmp';temporary.write_text(json.dumps(data,indent=2)+'\n')
    temporary.replace(output/'status.json');print(stage,flush=True)


def prepare():
    source=read(SOURCE/'contract.json');verify(source)
    audit=read(AUDIT/'audit.json');verify(audit)
    if not audit['selected_correction']['supported']:raise ValueError('No supported flat correction')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if (OUTPUT/'contract.json').exists():
        plan=read(OUTPUT/'contract.json');verify(plan)
        return yaml.safe_load((OUTPUT/'config.yaml').read_text()),plan
    shutil.copytree(SOURCE/'python',OUTPUT/'python',ignore=shutil.ignore_patterns('__pycache__'))
    path=OUTPUT/'python/nino_rl/crossing_authority.py'
    path.write_text(replace(path.read_text(),'4.45+.15','4.45+.10'))
    shutil.copyfile(SOURCE/'config.yaml',OUTPUT/'config.yaml')
    # Full PI is byte-identical and has the same seeds; preserve its provenance.
    shutil.copytree(SOURCE/'full',OUTPUT/'full')
    plan=deepcopy(source);plan['revision']='flat_quiet_tail_correction_v2'
    plan['protocol']['recovery_start_x_m']=4.55
    plan['assets'].update({str(p):digest(p) for p in (OUTPUT/'python/nino_rl').glob('*.py')})
    for p in (Path(__file__).resolve(),AUDIT/'audit.json',OUTPUT/'config.yaml'):
        plan['assets'][str(p)]=digest(p)
    for p in (SOURCE/'full').rglob('*'):
        if p.is_file():plan['assets'][str(p)]=digest(p)
    plan['full_pi_provenance']=str(SOURCE/'full')
    plan['selected_change']='Recovery starts 4.55 instead of 4.60 m; all other schedule settings unchanged'
    plan['conditional_learning']=dict(steps=20480,seed=42,source_actor=str(ACTOR),critic='fresh',optimizer='fresh',
        observation='Mapped second-cable reference from estimated pose replaces downward preview; explicit known-course scope',
        action='Existing two speed/yaw reference actions; bounded .4/s speed ramp; zero motor torque residual',
        reward='Existing weights plus one executed-speed reference cost; no scripted PPO action override',
        promotion='Unchanged physical/time/tracking/quality gates plus matched crossing-window criteria')
    immutable(OUTPUT/'contract.json',json.dumps(plan,indent=2)+'\n')
    return yaml.safe_load((OUTPUT/'config.yaml').read_text()),plan


def environment(output):
    os.environ.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env=os.environ.copy();env['PYTHONPATH']=str(output/'python')+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','')
    return env


def evaluate_screen(config,plan):
    from train_rough_curriculum import Processes,assert_isolated,complete_evaluation
    from nino_rl.tuning_trials import assert_trial_inputs
    study=read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials']
    processes=Processes(environment(OUTPUT),pi_integrator_profile='conditional_v1')
    def evaluate(label,scale=1.):
        directory=OUTPUT/label
        cached=complete_evaluation(directory,len(plan['seeds']))
        if cached is None:
            verify(plan);assert_isolated(79,'nino_flat_79')
            status(OUTPUT,'testing quiet-tail '+label)
            processes.env.update(NINO_AUTHORITY_PROFILE=label,NINO_MATCH_SCALE=str(scale))
            processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py',
                f'world:={study["world"]}','world_name:=combined_flat_section','headless:=true',
                'pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
            processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
            assert_trial_inputs(study,live=True)
            processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',OUTPUT/'config.yaml',
                '--timeout','60'],directory/'profile.log',timeout=65)
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',OUTPUT/'config.yaml',
                '--seeds',*plan['seeds'],'--baseline-speed-scale',scale,'--control-trace','--output',directory],
                directory/'evaluate.log',timeout=900)
            processes.close();cached=complete_evaluation(directory,len(plan['seeds']))
        if cached is None or cached[1]['evaluation_seeds']!=plan['seeds']:raise ValueError('Incomplete flat evidence')
        return cached
    try:
        batches={k:evaluate(k) for k in ('full','schedule')}
        scale=min(1.,metrics(batches['full'][1])['time_seconds']/metrics(batches['schedule'][1])['time_seconds'])
        batches['matched']=evaluate('matched',scale)
        result=analyze_flat(OUTPUT,plan,{k:v[1] for k,v in batches.items()},batches)
        status(OUTPUT,'complete: schedule passed' if result['authority_passed'] else 'complete: schedule failed; PPO/Optuna held',
               passed=result['authority_passed'],comparison=str(OUTPUT/'comparison.json'))
        return result
    finally:processes.close()


def build_learning_snapshot(root):
    """Build source in an isolated directory; this does not qualify or launch learning."""
    package=root/'python/nino_rl'
    shutil.copytree(OUTPUT/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'))
    # Evaluation intervention exists only in the baseline branch. PPO stays free.
    train_source=ROOT/'rl_runs/flat_value_scaled_pilot_v1/python/nino_rl/train.py'
    shutil.copyfile(train_source,package/'train.py')
    helper='''import numpy as np

def target(x):
    return .70 if 3.90 <= x <= 4.55 else 1.

def observed_reference(state):
    # Known mapped cable coordinate and estimated pose. No physical pose/height.
    return np.array([np.clip(4.45-state.x,-5.,5.),target(state.x),0.,1.],dtype=np.float32)
'''
    (package/'known_course_reference.py').write_text(helper)
    path=package/'ros_env.py';code=path.read_text()
    code=replace(code,'        preview = self.ros.terrain_preview(timeout=None)',
        '        from nino_rl.known_course_reference import observed_reference\n'
        '        preview = observed_reference(state)')
    code=replace(code,'        self.attempt_number += 1',
        '        self.attempt_number += 1\n        self.known_course_scale = 1.')
    code=replace(code,'        raw_action = action.copy()',
        '        requested_scale = scale\n'
        '        delta = .4*self.control_dt\n'
        '        scale = min(self.known_course_scale+delta,max(self.known_course_scale-delta,scale))\n'
        '        self.known_course_scale = scale\n'
        '        action[0] = 2.*scale-1.\n'
        '        raw_action = action.copy()')
    code=replace(code,'        self.episode_return += reward',
        '        from nino_rl.known_course_reference import target\n'
        '        reference_cost = -step_dt*self.config["known_course_reference"]["weight"]*'
        '((scale-target(self.previous_robot_state.x))*reward_reference.desired_linear_velocity/.1)**2 '
        'if reward_reference.valid else 0.\n'
        '        reward_terms["known_course_speed_reference"] = reference_cost\n'
        '        reward += reference_cost\n'
        '        self.episode_return += reward')
    # Existing optional trace is emitted during training too; retain exposure data.
    code=replace(code,'        return observation, reward, terminated, truncated, info',
        '        if self.config.get("known_course_reference") and "control_trace" in info:\n'
        '            import csv, os\n'
        '            capture = os.environ.get("NINO_FLAT_TRAIN_TRACE")\n'
        '            if capture:\n'
        '                row = dict(attempt=self.attempt_number, requested_scale=requested_scale, '
        '**info["control_trace"])\n'
        '                exists = os.path.exists(capture)\n'
        '                with open(capture,"a") as stream:\n'
        '                    writer = csv.DictWriter(stream,fieldnames=list(row))\n'
        '                    if not exists: writer.writeheader()\n'
        '                    writer.writerow(row)\n'
        '        return observation, reward, terminated, truncated, info')
    path.write_text(code)
    path=package/'training_contract.py';code=path.read_text()
    code=replace(code,'    return contract\n',
        '    if config.get("known_course_reference"):\n'
        '        contract["revision"] = 50\n'
        '        contract["known_course_reference"] = config["known_course_reference"]\n'
        '        contract["policy_speed_ramp_per_s"] = .4\n'
        '        contract["preview_input"] = "mapped cable distance/reference, estimated pose only"\n'
        '    return contract\n')
    path.write_text(code)
    config=yaml.safe_load((OUTPUT/'config.yaml').read_text())
    config['policy_v2']['require_terrain_preview']=False
    config['training_reward_scale']=.01;config['evaluation_control_trace']=True
    config['known_course_reference']=dict(revision='mapped_second_cable_v1',cable_x_m=4.45,
        braking_start_x_m=3.90,recovery_start_x_m=4.55,target_scale=.70,weight=.25,
        inference='Free speed/yaw policy; map-reference observations, not teacher actuation',
        scope='Known mapped flat course only; no unknown-cable generalization claim')
    immutable(root/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    for p in package.glob('*.py'):compile(p.read_text(),str(p),'exec')
    return config,train_source


def prepare_learning():
    """Known-course inputs are declared; never label a mapped reference sensor anticipation."""
    if not read(OUTPUT/'comparison.json')['authority_passed']:raise ValueError('Schedule screen failed')
    root=ROOT/'rl_runs/flat_known_course_pilot_v1';root.mkdir(parents=True,exist_ok=True)
    if (root/'learning_contract.json').exists():
        plan=read(root/'learning_contract.json');verify(plan);return root,plan
    config,train_source=build_learning_snapshot(root)
    package=root/'python/nino_rl'
    source=read(OUTPUT/'contract.json')
    assets=dict(source['assets']);assets.update({str(p):digest(p) for p in package.glob('*.py')})
    for p in (ACTOR,root/'config.yaml',OUTPUT/'comparison.json',train_source):assets[str(p)]=digest(p)
    plan=dict(revision='flat_known_course_pilot_v1',training_contract_revision=50,assets=assets,
        source_actor=str(ACTOR),source_actor_sha256=digest(ACTOR),actor='Full compatible two-action parameters',
        critic='fresh',optimizer='fresh',training_counter=0,steps=20480,training_seed=42,
        seeds=list(range(65000,65005)),protocol=source['protocol'],
        initialization_limitation='Observation shape/action meanings match; four former preview values change semantics. '
          'Transferred parameters are initialization, not claimed behavioral equivalence.',
        requires_matching_new_contract_pi=True,optuna_held=True)
    immutable(root/'learning_contract.json',json.dumps(plan,indent=2)+'\n')
    return root,plan


def learning_run(root,plan):
    from train_rough_curriculum import Processes,assert_isolated,complete_evaluation,checkpoint_steps,newest_checkpoint
    from nino_rl.tuning_trials import assert_trial_inputs
    study=read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials']
    env=environment(root);processes=Processes(env,pi_integrator_profile='conditional_v1')
    def launch(directory,baseline=False,scale=1.):
        verify(plan);processes.close();assert_isolated(79,'nino_flat_79')
        # The new learning package replaces baseline interpolation with constant
        # PI for fair full-speed/time-matched comparisons (below in preparation).
        processes.env.update(NINO_AUTHORITY_PROFILE='matched' if baseline else 'full',NINO_MATCH_SCALE=str(scale))
        processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py',
            f'world:={study["world"]}','world_name:=combined_flat_section','headless:=true',
            'pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
        processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
        assert_trial_inputs(study,live=True)
        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',root/'config.yaml',
            '--timeout','60'],directory/'profile.log',timeout=65)
    try:
        finals=list((root/'train').glob('*/nino_ppo_final.zip'))
        if len(finals)>1:raise ValueError('Ambiguous flat model')
        if not finals:
            if newest_checkpoint(root/'train'):raise ValueError('Interrupted flat pilot preserved; review before optimizer resume')
            status(root,'training known-course PPO',requested_steps=20480)
            processes.env['NINO_FLAT_TRAIN_TRACE']=str(root/'training_trace.csv')
            launch(root/'train')
            processes.run(['ros2','run','nino_rl','train','--config',root/'config.yaml','--device','cuda',
                '--init-model',ACTOR,'--timesteps','20480','--checkpoint-every','4096','--check-env',
                '--output',root/'train'],root/'train/train.log',timeout=7200)
            processes.close();processes.env.pop('NINO_FLAT_TRAIN_TRACE',None)
            finals=list((root/'train').glob('*/nino_ppo_final.zip'))
        if len(finals)!=1 or checkpoint_steps(finals[0])!=20480:raise ValueError('Flat budget incomplete')
        transfer=read(finals[0].with_name('actor_transfer.json'))
        if transfer['source_sha256']!=plan['source_actor_sha256'] or any(transfer[k]!=plan[k] for k in
            ('critic','optimizer','training_counter')):raise ValueError('Flat initialization changed')
        def evaluate(label,baseline=False,scale=1.):
            directory=root/label;cached=complete_evaluation(directory,len(plan['seeds']))
            if cached is None:
                status(root,'evaluating '+label);launch(directory,baseline,scale)
                cmd=['ros2','run','nino_rl','evaluate_baseline' if baseline else 'evaluate','--config',root/'config.yaml',
                    '--seeds',*plan['seeds'],'--control-trace','--output',directory]
                cmd+=['--baseline-speed-scale',scale] if baseline else ['--model',finals[0],'--device','cuda']
                processes.run(cmd,directory/'evaluate.log',timeout=900);processes.close()
                cached=complete_evaluation(directory,len(plan['seeds']))
            if cached is None or cached[1]['evaluation_seeds']!=plan['seeds']:raise ValueError('Flat evaluation incomplete')
            return cached
        batches={'full':evaluate('full',True),'schedule':evaluate('schedule')}
        scale=min(1.,metrics(batches['full'][1])['time_seconds']/metrics(batches['schedule'][1])['time_seconds'])
        batches['matched']=evaluate('matched',True,scale)
        result=analyze_flat(root,plan,{k:v[1] for k,v in batches.items()},batches)
        result['schedule_label_means']='Free learned PPO in this report; not baseline script'
        result['model']=str(finals[0]);result['contract_revision']=50
        (root/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
        report=root/'REPORT.md'
        report.write_text(report.read_text().replace('Flat disturbance reference comparison','Flat known-course PPO pilot')
            .replace('No learning updates. Optuna held.','20,480 PPO steps, actor transfer, fresh critic/optimizer. '
                     'The schedule row is free learned PPO. Known mapped cable reference; no downward preview.')
            +'\nContract revision 50. Independent physical gates unchanged.\n')
        status(root,'complete: PPO passed' if result['authority_passed'] else 'complete: PPO failed; Optuna held',
               passed=result['authority_passed'],comparison=str(root/'comparison.json'))
        return result
    finally:processes.close()


def tune(pilot,trials=6):
    import optuna
    if not read(pilot/'comparison.json')['authority_passed']:raise ValueError('Flat PPO not ready for tuning')
    root=ROOT/'rl_runs/flat_known_course_focused_optuna_v1';root.mkdir(parents=True,exist_ok=True)
    base=yaml.safe_load((pilot/'config.yaml').read_text());source=read(pilot/'learning_contract.json')
    search=dict(learning_rate=[1e-5,1e-4],ent_coef=[1e-5,.003],n_epochs=[2,3,5],clip_range=[.12,.25],
        time_penalty=[.06,.15],impact_weight=[.015,.05],slip_weight=[.15,.30],reference_weight=[.15,.40])
    immutable(root/'study_contract.json',json.dumps(dict(revision='flat_known_course_focused_v1',assets=source['assets'],
        source_actor=str(ACTOR),steps_per_trial=20480,training_seed=42,evaluation_seeds=source['seeds'],
        max_trials=trials,search=search,fixed_config=base,protocol=source['protocol'],
        objective='Infeasible arrival: -1000-100*failed_fraction. Feasible: '
          '-(.30*time/18.5+.20*truth_rmse/full_PI_rmse+.25*vibration/full_PI_vibration+.25*slip/full_PI_slip)',
        gates='Unchanged; export only qualified candidates',historical_scores_imported=False),indent=2)+'\n')
    study=optuna.create_study(study_name='flat_known_course_focused_v1',storage='sqlite:///'+str(root/'study.sqlite3'),
        direction='maximize',load_if_exists=True,sampler=optuna.samplers.TPESampler(seed=42,n_startup_trials=3))
    def objective(trial):
        config=deepcopy(base)
        for key in ('learning_rate','ent_coef'):config['ppo'][key]=trial.suggest_float(key,*search[key],log=True)
        config['ppo']['n_epochs']=trial.suggest_categorical('n_epochs',search['n_epochs'])
        config['ppo']['clip_range']=trial.suggest_float('clip_range',*search['clip_range'])
        for key in ('time_penalty','impact_weight','slip_weight'):
            config['reward_v2'][key]=trial.suggest_float('reward.'+key,*search[key])
        config['known_course_reference']['weight']=trial.suggest_float('reference_weight',*search['reference_weight'])
        directory=root/f'trial_{trial.number:04d}';directory.mkdir()
        shutil.copytree(pilot/'python',directory/'python',ignore=shutil.ignore_patterns('__pycache__'))
        immutable(directory/'config.yaml',yaml.safe_dump(config,sort_keys=False))
        plan=deepcopy(source);plan['assets'].update({str(p):digest(p) for p in (directory/'python/nino_rl').glob('*.py')})
        plan['assets'][str(directory/'config.yaml')]=digest(directory/'config.yaml')
        immutable(directory/'learning_contract.json',json.dumps(plan,indent=2)+'\n')
        result=learning_run(directory,plan)
        gates=result['existing_flat_gates']
        if not gates['physical_arrival']:
            from train_rough_curriculum import complete_evaluation
            rate=complete_evaluation(directory/'schedule',5)[1]['success_rate'];score=-1000-100*(1-rate)
        else:
            from train_rough_curriculum import complete_evaluation
            candidate=metrics(complete_evaluation(directory/'schedule',5)[1]);pi=metrics(complete_evaluation(directory/'full',5)[1])
            score=-(.30*candidate['time_seconds']/18.5+.20*candidate['truth_path_rmse_m']/pi['truth_path_rmse_m']+
                .25*candidate['rms_vertical_acceleration_m_s2']/pi['rms_vertical_acceleration_m_s2']+
                .25*candidate['rms_wheel_slip']/pi['rms_wheel_slip'])
        trial.set_user_attr('qualified',result['authority_passed']);trial.set_user_attr('model',result['model'])
        return score
    status(root,'focused tuning',optuna_held=False,trial_budget=trials)
    study.optimize(objective,n_trials=max(0,trials-len(study.trials)),catch=(RuntimeError,))
    qualified=[t for t in study.trials if t.state==optuna.trial.TrialState.COMPLETE and t.user_attrs.get('qualified')]
    if qualified:
        best=max(qualified,key=lambda x:x.value)
        (root/'best_qualified.json').write_text(json.dumps(dict(trial=best.number,score=best.value,params=best.params,
            **best.user_attrs,requires_independent_validation=True),indent=2)+'\n')
    status(root,'complete: focused screening',optuna_held=False,qualified_candidates=len(qualified))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true')
    p.add_argument('--wait-for-rough',action='store_true');p.add_argument('--tune-if-pass',action='store_true')
    args=p.parse_args();os.chdir(ROOT);config,plan=prepare()
    if not args.run:print('Prepared one quiet-tail correction; no simulator launched.');return
    lock=(OUTPUT/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        if args.wait_for_rough:
            status(OUTPUT,'queued: waiting for rough workflow to release simulator')
            rough=(ROOT/'rl_runs/rough_holding_reference_candidate_v1/runner.lock').open('a')
            while True:
                try:fcntl.flock(rough,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:time.sleep(5)
            rough.close()
        result=evaluate_screen(config,plan)
        if not result['authority_passed']:return
        root,learning=prepare_learning();result=learning_run(root,learning)
        if result['authority_passed'] and args.tune_if_pass:tune(root)
    except BaseException as exc:status(OUTPUT,'interrupted',error=str(exc));raise
    finally:lock.close()


if __name__=='__main__':main()
