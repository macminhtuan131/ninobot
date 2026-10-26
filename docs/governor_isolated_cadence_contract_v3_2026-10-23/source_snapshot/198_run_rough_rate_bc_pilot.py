#!/usr/bin/env python3
"""Demonstrate, imitate, physically verify, then conditionally run one PPO pilot."""
import fcntl,json,os,sys
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from prepare_rough_rate_bc import OUTPUT,ROOT,prepare
from prepare_rough_foundations import digest,immutable
from run_disturbance_reference_comparisons import verify
from run_rough_hardware_confirmation import OUTPUT as CONFIRM,make_processes,verify as verify_physics
from run_hardware_sensor_preflight import OUTPUT as SENSOR

def state(stage,**extra):
    OUTPUT.mkdir(parents=True,exist_ok=True)
    x=dict(stage=stage,pid=os.getpid(),utc=datetime.now(timezone.utc).isoformat(),optuna_held=True,**extra)
    tmp=OUTPUT/'status.tmp';tmp.write_text(json.dumps(x,indent=2)+'\n');tmp.replace(OUTPUT/'status.json');print(stage,flush=True)

def main():
    os.chdir(ROOT);config,plan=prepare();lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from run_rough_trial8_validation import Validation,write,route_readiness
    from train_rough_curriculum import assert_isolated,complete_evaluation,checkpoint_steps,newest_checkpoint
    from run_rough_recovery_sigma_pilot import score_batches,verify_scoring_rules
    regression_plan=deepcopy(plan)
    regression_plan['evaluation_seeds']=list(range(17100,17105))
    verify_scoring_rules(config,regression_plan)
    immutable(OUTPUT/'workflow_contract.json',json.dumps(dict(script_sha256=digest(__file__),pilot_contract_sha256=digest(OUTPUT/'pilot_contract.json'),
        stages=['5 causal teacher episodes: 3 train, 1 validation, 1 held-out test','Actor-only supervised BC',
            '3 deterministic physical probes','Conditional single 20480-step actor-initialized PPO','5 paired seeds against full/reactive/time-matched PI'],
        prerequisite='Fresh critic/optimizer; unchanged physical gates; no extension of failed checkpoint'),indent=2)+'\n')
    confirmation=json.loads((CONFIRM/'confirmation_contract.json').read_text());verify_physics(confirmation)
    validation=Validation(OUTPUT/'workflow');write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
    env=validation.base_env.copy();env['PYTHONPATH']=str(OUTPUT/'python')+os.pathsep+env.get('PYTHONPATH','')
    processes=make_processes(env,confirmation['profiles']['nominal']['launch'],SENSOR/'imu_bridge.yaml')
    helper=Path(__file__).with_name('rough_rate_behavior_cloning.py')
    def launch(directory):
        processes.close();assert_isolated(78,'nino_rough_78');verify(plan);verify_physics(confirmation)
        processes.env['NINO_REACTIVE_RECORD_DIR']=str(directory/'actor_capture')
        validation.check(OUTPUT/'python');processes.launch(confirmation['world'],directory)
        live=deepcopy(validation.old_contract['comparable_trials']);live['world']=confirmation['world']
        live['assets'].update(plan['assets']);live['assets'].update(confirmation['assets']);validation.assert_inputs(live,live=True)
        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',OUTPUT/'config.yaml','--timeout','60'],directory/'profile.log',timeout=65)
    def evaluate(label,baseline=False,scale=1.,model=None,reactive=False):
        directory=OUTPUT/'evaluation'/label;seeds=plan['evaluation_seeds']
        if complete_evaluation(directory,len(seeds)) is None:
            state('evaluating '+label);launch(directory)
            command=['ros2','run','nino_rl','evaluate_baseline' if baseline else 'evaluate','--config',OUTPUT/'config.yaml',
                '--route','E1','--seeds',*seeds,'--control-trace','--output',directory]
            command+=['--baseline-speed-scale',scale] if baseline else ['--device','cuda','--model',model]
            if reactive:command+=['--reactive']
            processes.run(command,directory/'evaluate.log',timeout=900);processes.close()
        return complete_evaluation(directory,len(seeds))
    try:
        if not (OUTPUT/'demonstrations.json').exists():
            if list(OUTPUT.glob('demo_*.npz')):raise ValueError('Partial demonstrations preserved; no implicit overwrite')
            state('collecting causal reactive categorical demonstrations');launch(OUTPUT/'demonstration_run')
            processes.run([sys.executable,helper,'collect','--config',OUTPUT/'config.yaml','--output',OUTPUT,
                '--seeds',17200,17201,17202,17203,17204],OUTPUT/'demonstrations.log',timeout=1200);processes.close()
        demonstrations=json.loads((OUTPUT/'demonstrations.json').read_text())
        if not demonstrations['physical_passed'] or not demonstrations['deterministic_response_passed']:
            state('held: teacher physical/response gate failed');return
        if not (OUTPUT/'bc_verification.json').exists():
            state('training actor-only behavior cloning; no PPO updates')
            processes.run([sys.executable,helper,'fit','--config',OUTPUT/'config.yaml','--output',OUTPUT],OUTPUT/'bc.log',timeout=1200)
        bc=json.loads((OUTPUT/'bc_verification.json').read_text())
        if not bc['passed'] or digest(OUTPUT/'bc_actor.zip')!=bc['actor_sha256']:
            state('held: BC held-out verification failed');return
        if not (OUTPUT/'probe.json').exists():
            state('verifying deterministic BC actor on physical E1');launch(OUTPUT/'probe_run')
            processes.run([sys.executable,helper,'probe','--config',OUTPUT/'config.yaml','--output',OUTPUT,
                '--seeds',*plan['probe_seeds']],OUTPUT/'probe.log',timeout=900);processes.close()
        probe=json.loads((OUTPUT/'probe.json').read_text())
        if not probe['physical_passed'] or not probe['deterministic_response_passed']:
            state('held: BC closed-loop response/arrival failed; no PPO pilot');return
        directory=OUTPUT/'train';final=list(directory.glob('*/nino_ppo_final.zip'))
        if not final:
            if newest_checkpoint(directory):raise ValueError('Interrupted PPO pilot retained; no implicit resume')
            state('training one actor-initialized PPO pilot',requested_steps=20480);launch(directory)
            processes.run(['ros2','run','nino_rl','train','--config',OUTPUT/'config.yaml','--route','E1','--device','cuda',
                '--init-model',OUTPUT/'bc_actor.zip','--timesteps','20480','--checkpoint-every','4096','--check-env','--output',directory],directory/'train.log',timeout=7200)
            processes.close();final=list(directory.glob('*/nino_ppo_final.zip'))
        if len(final)!=1 or checkpoint_steps(final[0])!=20480:raise ValueError('Wrong completed pilot budget')
        transfer=json.loads(final[0].with_name('actor_transfer.json').read_text())
        if transfer['source_sha256']!=bc['actor_sha256'] or transfer['critic']!='fresh' or transfer['optimizer']!='fresh' or transfer['training_counter']!=0:
            raise ValueError('Expected BC actor-only transfer')
        pr,ppo=evaluate('ppo',model=final[0]);fr,full=evaluate('pi_full',True);rr,reactive=evaluate('pi_reactive',True,reactive=True)
        scale=min(1.,max(.55,full['metrics_all_episodes']['time_seconds']['mean']/ppo['metrics_all_episodes']['time_seconds']['mean']))
        mr,matched=evaluate('pi_matched',True,scale)
        result=score_batches(OUTPUT,config,plan,pr,ppo,fr,full,mr,matched,plan['evaluation_seeds'])
        from analyze_rough_reactive_authority import traces,window_metrics
        rt=traces(OUTPUT/'evaluation/pi_reactive');windows=result['disturbance_windows'];cap=plan['quality_gate']['max_other_quality_ratio']
        ratios={k:float(np.mean([x['ppo'][k] for x in windows])/max(np.mean([window_metrics(rt[x['seed']],x['windows'])[k] for x in windows]),1e-12))
            for k in ('vibration_energy_per_m','slip_energy_per_m')}
        global_ratios={k:ppo['metrics_all_episodes'][k]['mean']/max(reactive['metrics_all_episodes'][k]['mean'],1e-12)
            for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
        reactive_gate=route_readiness(rr,config,len(plan['evaluation_seeds']))
        result.update(pi_reactive=reactive,reactive_physical_gate=reactive_gate,reactive_quality_ratios=ratios,
            reactive_global_quality_ratios=global_ratios,matched_scale=scale,contract_revision=54,
            qualification='One BC-initialized training seed, five fixed nominal E1 scenarios; not generalization/sim-to-real')
        result['pilot_passed']=bool(result['pilot_passed'] and reactive_gate['passed'] and all(v<=cap for v in (*ratios.values(),*global_ratios.values())))
        write(OUTPUT/'comparison.json',result);state('complete',pilot_passed=result['pilot_passed'],model=str(final[0]))
    except BaseException as exc:state('interrupted; evidence preserved',error=str(exc));raise
    finally:
        processes.close();lock.close()
        if digest(plan['preserved_checkpoint'])!=plan['preserved_checkpoint_sha256']:raise RuntimeError('Preserved checkpoint changed')

if __name__=='__main__':main()
