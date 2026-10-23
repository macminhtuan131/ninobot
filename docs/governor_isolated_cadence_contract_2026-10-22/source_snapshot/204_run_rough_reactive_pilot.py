#!/usr/bin/env python3
"""Gate a fresh 20,480-step PPO pilot and matching PI evaluations; Optuna held."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import sys

from prepare_rough_foundations import ROOT,digest,immutable
from prepare_rough_reactive_pilot import OUTPUT,prepare
from run_rough_hardware_confirmation import OUTPUT as CONFIRM,make_processes,verify
from run_hardware_sensor_preflight import OUTPUT as SENSOR


def state(output,stage,**extra):
    from run_rough_trial8_validation import write
    value=dict(stage=stage,pid=os.getpid(),updated_utc=datetime.now(timezone.utc).isoformat(),
        optuna_held=True,**extra)
    write(output/'status.json',value)
    with (output/'status_history.jsonl').open('a') as stream:stream.write(json.dumps(value)+'\n')
    lines=['# Fresh rough longitudinal PPO pilot','', 'Stage: '+stage,'',
        'One speed action (.55–1), fixed .4 scale/s ramp, unscaled PI yaw, no residual torque. '
        'Horizontal LiDAR/IMU/encoder history only. Fixed half-relief E1, nominal physics. '
        'Fresh actor/critic/optimizer, seed 16000, exactly 20,480 requested transitions. '
        'Bounded sensor-cue reward weighting; no reactive action override.','',
        'Optuna remains held. Timing and independent physical arrival checks remain strict.','',
        '```json',json.dumps(extra,indent=2),'```','']
    (output/'REPORT.md').write_text('\n'.join(lines))
    print(stage,flush=True)


def verify_inputs(plan):
    for group in (plan['assets'],plan['implementation']):
        for path,expected in group.items():
            if digest(path)!=expected:raise ValueError('Pilot input changed: '+path)


def authority_gate(directory):
    import csv
    import numpy as np
    traces=list(directory.glob('*/episode-*/drive_trace.csv'))
    if len(traces)!=3:raise ValueError('Expected all three PI actuator traces')
    errors=[];raw_errors=[];scales=[];residual=[];settled_errors=[];settled_counts=[]
    for path in traces:
        rows=list(csv.DictReader(path.open()))
        settled_count=0
        for row in rows:
            # The driver sees already-scaled linear commands and unscaled yaw;
            # adapter scale must remain one during every motion action.
            if (float(row['cmd_fresh'])>.5 and float(row['policy_fresh'])>.5 and
                    (abs(float(row['requested_linear_m_s']))>.03 or abs(float(row['requested_yaw_rad_s']))>.03)):
                requested=float(row['requested_yaw_rad_s'])
                executed=float(row['executed_yaw_rad_s'])
                filtered=float(row['filtered_speed_scale'])
                # The unchanged driver ramps from stop to adapter scale one
                # at 2/s. That startup safety ramp affects PI and PPO equally.
                # Verify its exact response; policy scaling must never weaken yaw.
                errors.append(abs(executed-requested*filtered))
                raw_errors.append(abs(executed-requested))
                if filtered>.999999:
                    settled_errors.append(abs(executed-requested))
                    settled_count+=1
                scales.append(float(row['speed_scale']))
                residual.append(abs(float(row['left_residual_nm']))+abs(float(row['right_residual_nm'])))
        settled_counts.append(settled_count)
    if not errors:raise ValueError('No executed motion in actuator traces')
    passed=bool(max(errors)<1e-6 and min(scales)>.999 and max(residual)<1e-6
        and min(settled_counts)>=100 and max(settled_errors,default=float('inf'))<1e-6)
    return dict(passed=passed,max_error_vs_driver_startup_ramp_rad_s=max(errors),
        max_settled_yaw_reference_error_rad_s=max(settled_errors,default=None),
        max_raw_yaw_reference_error_rad_s=max(raw_errors),settled_samples_per_episode=settled_counts,
        shared_startup_ramp='Unchanged driver 2 scale/s ramp; exact expected response checked',
        min_adapter_speed_scale=min(scales),maximum_additive_residual_nm=max(residual))


def run(output,config,plan):
    from run_rough_trial8_validation import Validation,route_readiness,write
    from train_rough_curriculum import assert_isolated,complete_evaluation,newest_checkpoint,checkpoint_steps
    confirmation=json.loads((CONFIRM/'confirmation_contract.json').read_text());verify(confirmation)
    result=json.loads((CONFIRM/'feasibility_result.json').read_text())
    if not result['passed'] or result['contract_sha256']!=digest(CONFIRM/'confirmation_contract.json'):
        raise ValueError('Confirmation is incomplete or failed; PPO and Optuna remain held')
    if len(result['batches'])!=9 or not all(x['gate']['passed'] for x in result['batches'].values()):
        raise ValueError('All nine physical-profile route batches must pass')
    verification=json.loads((output/'verification.json').read_text())
    if not all(verification[k] for k in ('one_action','no_truth_velocity_or_preview','fresh_optimizer','save_reload_passed','old_model_rejected')):
        raise ValueError('Offline new-policy verification failed')
    immutable(output/'runner_contract.json',json.dumps(dict(script_sha256=digest(__file__),
        pilot_contract_sha256=digest(output/'pilot_contract.json'),
        confirmation_contract_sha256=digest(CONFIRM/'confirmation_contract.json')),indent=2)+'\n')
    validation=Validation(output/'workflow')
    env=validation.base_env.copy();env['PYTHONPATH']=str(output/'python')+os.pathsep+env.get('PYTHONPATH','')
    processes=make_processes(env,confirmation['profiles']['nominal']['launch'],SENSOR/'imu_bridge.yaml')
    write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
    def launch(directory):
        processes.close();assert_isolated(78,'nino_rough_78');verify_inputs(plan)
        validation.check(output/'python');processes.launch(confirmation['world'],directory)
        live=deepcopy(validation.old_contract['comparable_trials'])
        live['world']=confirmation['world'];live['assets'].update(plan['assets'])
        live['assets'].update(confirmation['assets']);validation.assert_inputs(live,live=True)
        processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',output/'config.yaml',
            '--timeout','60'],directory/'profile.log',timeout=65)
    def evaluate(directory,seeds,baseline,scale=1.,model=None):
        if complete_evaluation(directory,len(seeds)) is None:
            launch(directory)
            command=['ros2','run','nino_rl','evaluate_baseline' if baseline else 'evaluate',
                '--config',output/'config.yaml','--route','E1','--seeds',*seeds,'--control-trace','--output',directory]
            command+=['--baseline-speed-scale',scale] if baseline else ['--device','cuda','--model',model]
            processes.run(command,directory/'evaluate.log',timeout=600)
            processes.close()
        return complete_evaluation(directory,len(seeds))
    try:
        for label,scale in [('full',1.),('reduced',.7)]:
            directory=output/'controller_pi'/label
            state(output,'validating new PI authority '+label)
            rows,summary=evaluate(directory,[13100,13101,13102],True,scale)
            gate=route_readiness(rows,config,3);authority=authority_gate(directory)
            write(directory/'gate.json',dict(physical=gate,actuator=authority))
            if not gate['passed'] or not authority['passed']:
                state(output,'held: new PI authority failed',profile=label,physical=gate,actuator=authority)
                return
        state(output,'training fresh PPO',requested_steps=plan['steps'],training_seed=plan['training_seed'])
        directory=output/'train';directory.mkdir(parents=True,exist_ok=True)
        final=list(directory.glob('*/nino_ppo_final.zip'))
        if len(final)>1:raise ValueError('Ambiguous final pilot checkpoint')
        if not final:
            interrupted=newest_checkpoint(directory)
            if interrupted is not None:
                raise ValueError('Pilot checkpoint exists without completion; preserve it and review interruption before rerunning a fresh task')
            launch(directory)
            processes.run(['ros2','run','nino_rl','train','--config',output/'config.yaml','--route','E1',
                '--device','cuda','--timesteps',plan['steps'],'--checkpoint-every','4096','--check-env',
                '--output',directory],directory/'train.log',timeout=7200)
            processes.close();final=list(directory.glob('*/nino_ppo_final.zip'))
        if len(final)!=1 or checkpoint_steps(final[0])!=plan['steps']:
            raise ValueError('Pilot did not finish its fixed transition budget')
        model=final[0];seeds=plan['evaluation_seeds']
        state(output,'evaluating fresh PPO',model=str(model))
        ppo_rows,ppo=evaluate(output/'evaluation/ppo',seeds,False,model=model)
        state(output,'evaluating full-speed PI')
        pi_rows,pi=evaluate(output/'evaluation/pi_full',seeds,True)
        ppo_time=ppo['metrics_all_episodes']['time_seconds']['mean']
        pi_time=pi['metrics_all_episodes']['time_seconds']['mean']
        scale=min(1.,max(config['longitudinal_control']['minimum_scale'],pi_time/ppo_time))
        state(output,'evaluating speed-matched PI',speed_scale=scale)
        matched_rows,matched=evaluate(output/'evaluation/pi_matched',seeds,True,scale)
        matched_time=matched['metrics_all_episodes']['time_seconds']['mean']
        comparison=dict(ppo=ppo,pi_full=pi,pi_matched=matched,matched_scale=scale,
            duration_match_relative_error=abs(matched_time-ppo_time)/ppo_time,
            arrival_tracking_gate=route_readiness(ppo_rows,config,len(seeds)),
            qualification='Five paired reset seeds, one training seed, fixed nominal map; not generalization or a sim-to-real claim',
            optuna_held=True)
        comparison['quality_ratios_to_pi_matched']={name:
            ppo['metrics_all_episodes'][name]['mean']/max(matched['metrics_all_episodes'][name]['mean'],1e-12)
            for name in ('rms_vertical_acceleration_m_s2','rms_wheel_slip','truth_path_rmse_m')}
        from analyze_rough_reactive_authority import traces,windows,window_metrics,response
        from prepare_rough_reactive_authority import OUTPUT as authority_output
        window_config=json.loads((authority_output/'authority_contract.json').read_text())['window']
        pi_traces=traces(output/'evaluation/pi_full');ppo_traces=traces(output/'evaluation/ppo')
        matched_traces=traces(output/'evaluation/pi_matched')
        paired=[]
        for seed in seeds:
            ranges=windows(pi_traces[seed],window_config)
            pi_window=window_metrics(pi_traces[seed],ranges)
            ppo_window=window_metrics(ppo_traces[seed],ranges)
            matched_window=window_metrics(matched_traces[seed],ranges)
            behavior=response(ppo_traces[seed])
            holding=[float(r['speed_scale']) for r in ppo_traces[seed] if r['cue_phase']=='holding']
            quiet=[float(r['speed_scale']) for r in ppo_traces[seed]
                if r['cue_phase'] in ('ready','cooldown') and not int(r['cue_disturbed'])]
            import numpy as np
            holding_mean=float(np.mean(holding)) if holding else None
            quiet_mean=float(np.mean(quiet)) if quiet else None
            behavior.update(mean_scale_during_holding=holding_mean,mean_scale_during_quiet=quiet_mean,
                conditional_response=bool(holding and quiet and quiet_mean-holding_mean>=.03
                    and quiet_mean>=.95 and behavior['recovered']))
            paired.append(dict(seed=seed,windows=ranges,pi=pi_window,pi_matched=matched_window,ppo=ppo_window,behavior=behavior))
        comparison['disturbance_windows']=paired
        comparison['slowdown_and_recovery_present']=all(r['behavior']['conditional_response'] for r in paired)
        comparison['window_quality_ratios_to_pi_matched']={k:
            float(np.mean([r['ppo'][k] for r in paired])/np.mean([r['pi_matched'][k] for r in paired]))
            for k in ('vibration_rms','slip_rms','vibration_energy_per_m','slip_energy_per_m')}
        comparison['learned_response_gate']=bool(comparison['arrival_tracking_gate']['passed']
            and comparison['slowdown_and_recovery_present'] and ppo_time<=pi_time*1.15)
        comparison['behavior_qualification']='Fixed-map response association, not causal IMU dependence or unseen-terrain adaptation'
        # A held-out seed comparison is recorded regardless of whether it wins;
        # no reward adjustment or Optuna launch follows these observations.
        write(output/'comparison.json',comparison)
        state(output,'complete',model=str(model),physical_gate=comparison['arrival_tracking_gate'],
            comparison=str(output/'comparison.json'),
            quality_ratios_to_speed_matched_pi=comparison['quality_ratios_to_pi_matched'],
            duration_match_relative_error=comparison['duration_match_relative_error'])
    finally:processes.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--run',action='store_true');args=parser.parse_args();os.chdir(ROOT)
    output=args.output.resolve();config,plan=prepare(output)
    if not args.run:print('Prepared runner; no simulation or training started');return
    lock=(output/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:run(output,config,plan)
    except BaseException as exc:
        state(output,'interrupted',error=str(exc));raise


if __name__=='__main__':main()
