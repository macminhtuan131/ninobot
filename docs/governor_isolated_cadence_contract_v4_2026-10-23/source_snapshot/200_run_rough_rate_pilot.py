#!/usr/bin/env python3
"""Own and gate one fresh 20,480-step discrete rate pilot; Optuna remains held."""
from copy import deepcopy
from datetime import datetime,timezone
import fcntl,json,os,sys
from pathlib import Path
from prepare_rough_rate_pilot import OUTPUT,ROOT,prepare,verify
from prepare_rough_foundations import digest,immutable
from run_rough_hardware_confirmation import OUTPUT as CONFIRM,make_processes,verify as verify_physics
from run_hardware_sensor_preflight import OUTPUT as SENSOR

def state(stage,**extra):
    value=dict(stage=stage,pid=os.getpid(),utc=datetime.now(timezone.utc).isoformat(),optuna_held=True,**extra)
    (OUTPUT/'status.json').write_text(json.dumps(value,indent=2)+'\n')
    with (OUTPUT/'status_history.jsonl').open('a') as stream:stream.write(json.dumps(value)+'\n')
    print(stage,flush=True)

def main():
    os.chdir(ROOT);config,plan=prepare()
    lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from run_rough_trial8_validation import Validation,write,route_readiness
    from train_rough_curriculum import assert_isolated,complete_evaluation,checkpoint_steps,newest_checkpoint
    from run_rough_recovery_sigma_pilot import score_batches,verify_scoring_rules
    verification=json.loads((OUTPUT/'verification.json').read_text())
    if not verification['passed']:raise ValueError('Offline verification failed')
    verify_scoring_rules(config,plan)
    immutable(OUTPUT/'workflow_contract.json',json.dumps(dict(script_sha256=digest(__file__),
        probe_sha256=digest(Path(__file__).with_name('probe_rough_rate_execution.py')),
        pilot_contract_sha256=digest(OUTPUT/'pilot_contract.json'),verification_sha256=digest(OUTPUT/'verification.json')),
        indent=2)+'\n')
    confirmation=json.loads((CONFIRM/'confirmation_contract.json').read_text());verify_physics(confirmation)
    validation=Validation(OUTPUT/'workflow');write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
    env=validation.base_env.copy();env['PYTHONPATH']=str(OUTPUT/'python')+os.pathsep+env.get('PYTHONPATH','')
    processes=make_processes(env,confirmation['profiles']['nominal']['launch'],SENSOR/'imu_bridge.yaml')
    def launch(directory):
        processes.close();assert_isolated(78,'nino_rough_78');verify(plan);verify_physics(confirmation)
        processes.env['NINO_REACTIVE_RECORD_DIR']=str(directory/'actor_capture')
        validation.check(OUTPUT/'python');processes.launch(confirmation['world'],directory)
        live=deepcopy(validation.old_contract['comparable_trials']);live['world']=confirmation['world']
        live['assets'].update(plan['assets']);live['assets'].update(confirmation['assets']);validation.assert_inputs(live,live=True)
        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',OUTPUT/'config.yaml',
            '--timeout','60'],directory/'profile.log',timeout=65)
    def evaluate(label,seeds,baseline=False,scale=1.,model=None,reactive=False):
        directory=OUTPUT/'evaluation'/label
        if complete_evaluation(directory,len(seeds)) is None:
            state('evaluating '+label);launch(directory)
            command=['ros2','run','nino_rl','evaluate_baseline' if baseline else 'evaluate','--config',OUTPUT/'config.yaml',
                '--route','E1','--seeds',*seeds,'--control-trace','--output',directory]
            command+=['--baseline-speed-scale',scale] if baseline else ['--device','cuda','--model',model]
            if reactive:command+=['--reactive']
            processes.run(command,directory/'evaluate.log',timeout=900);processes.close()
        return complete_evaluation(directory,len(seeds))
    try:
        directory=OUTPUT/'execution'
        if not (directory/'execution.json').exists():
            state('verifying live BRAKE/HOLD/RECOVER and categorical exposure');launch(directory)
            processes.run([sys.executable,'src/nino_rl/scripts/probe_rough_rate_execution.py','--config',OUTPUT/'config.yaml',
                '--output',directory],directory/'execution.log',timeout=900);processes.close()
        execution=json.loads((directory/'execution.json').read_text())
        if not execution['execution_passed'] or not execution['physical_passed']:
            state('held: live execution or feasibility failed');return
        directory=OUTPUT/'train';final=list(directory.glob('*/nino_ppo_final.zip'))
        if not final:
            if newest_checkpoint(directory):raise ValueError('Interrupted checkpoint preserved; fresh rerun requires review')
            state('training fresh categorical PPO',requested_steps=20480,seed=17000);launch(directory)
            processes.run(['ros2','run','nino_rl','train','--config',OUTPUT/'config.yaml','--route','E1','--device','cuda',
                '--timesteps','20480','--checkpoint-every','4096','--check-env','--output',directory],directory/'train.log',timeout=7200)
            processes.close();final=list(directory.glob('*/nino_ppo_final.zip'))
        if len(final)!=1 or checkpoint_steps(final[0])!=20480:raise ValueError('Wrong completed pilot budget')
        seeds=plan['evaluation_seeds'];model=final[0]
        ppo_rows,ppo=evaluate('ppo',seeds,model=model)
        pi_rows,pi=evaluate('pi_full',seeds,True)
        reactive_rows,reactive=evaluate('pi_reactive',seeds,True,reactive=True)
        scale=min(1.,max(.55,pi['metrics_all_episodes']['time_seconds']['mean']/ppo['metrics_all_episodes']['time_seconds']['mean']))
        matched_rows,matched=evaluate('pi_matched',seeds,True,scale)
        result=score_batches(OUTPUT,config,plan,ppo_rows,ppo,pi_rows,pi,matched_rows,matched,seeds)
        result.update(pi_reactive=reactive,reactive_physical_gate=route_readiness(reactive_rows,config,len(seeds)),matched_scale=scale,
            contract_revision=51,qualification='Five paired scenarios, one fresh training seed; no unseen-map or sim-to-real claim')
        from analyze_rough_reactive_authority import traces,window_metrics,response
        rt=traces(OUTPUT/'evaluation/pi_reactive');pt=traces(OUTPUT/'evaluation/ppo')
        result['reactive_response_comparison']=[dict(seed=x['seed'],reference=response(rt[x['seed']]),
            ppo=response(pt[x['seed']]),reference_window=window_metrics(rt[x['seed']],x['windows']),
            ppo_window=x['ppo']) for x in result['disturbance_windows']]
        result['pilot_passed']=bool(result['pilot_passed'] and result['reactive_physical_gate']['passed'])
        write(OUTPUT/'comparison.json',result)
        state('complete',pilot_passed=result['pilot_passed'],model=str(model),comparison=str(OUTPUT/'comparison.json'))
        (OUTPUT/'REPORT.md').write_text('# Fresh rough categorical rate pilot\n\n'
            'BRAKE / HOLD / RECOVER, unchanged .55–1 bounds and .4 scale/s ramp. '
            'Holding duration .8 s; old .6 s could not reach .70. Fresh actor, critic and optimizer, seed 17000. '
            'All reward weights, physical scoring, 360 hardware observations and terrain preserved.\n\n'
            '```json\n'+json.dumps(result,indent=2)+'\n```\n')
    except BaseException as exc:state('interrupted',error=str(exc));raise
    finally:processes.close();lock.close()

if __name__=='__main__':main()
