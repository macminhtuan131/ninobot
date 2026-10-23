"""Paired spatial disturbance windows, selected from PI only; frozen quality gate."""
import csv
import json
from pathlib import Path
import numpy as np


def traces(directory):
    found={}
    for path in Path(directory).glob('*/episode-*/control_trace.csv'):
        rows=list(csv.DictReader(path.open()))
        if not rows:raise ValueError('Empty trace: '+str(path))
        seed=int(rows[0]['seed'])
        if seed in found:raise ValueError('Ambiguous completed traces for seed '+str(seed))
        found[seed]=rows
    return found


def windows(rows,config):
    ranges=sorted((float(r['physical_x_m'])-config['before_m'],float(r['physical_x_m'])+config['after_m'])
        for r in rows if int(r['cue_triggered']))
    merged=[]
    for low,high in ranges:
        if merged and low<=merged[-1][1]:merged[-1][1]=max(high,merged[-1][1])
        else:merged.append([max(0.,low),high])
    return merged


def window_metrics(rows,ranges):
    energy=duration=covered=slip=distance=0.;peak=0.;previous=0.
    for row in rows:
        position=float(row['physical_x_m']);low,high=sorted((previous,position));dx=high-low
        fraction=(sum(max(0.,min(high,b)-max(low,a)) for a,b in ranges)/dx
            if dx>1e-9 else float(any(a<=position<=b for a,b in ranges)))
        fraction=min(1.,fraction);dt=float(row['step_dt_s'])*fraction
        energy+=float(row['step_imu_energy'])*fraction
        covered+=float(row['step_imu_coverage_s'])*fraction
        slip+=float(row['step_slip_square'])*dt
        distance+=dx*fraction;duration+=dt
        if fraction>0:peak=max(peak,float(row['step_imu_peak_m_s2']))
        previous=position
    if min(duration,covered,distance)<=0:raise ValueError('No covered reference disturbance windows')
    return dict(vibration_rms=float(np.sqrt(energy/covered)),slip_rms=float(np.sqrt(slip/duration)),
        vibration_energy_per_m=energy/distance,slip_energy_per_m=slip/distance,
        imu_energy=energy,slip_energy=slip,coverage_s=covered,duration_s=duration,
        distance_m=distance,peak_acceleration_m_s2=peak)


def response(rows):
    scales=np.array([float(r['speed_scale']) for r in rows]);triggers=sum(int(r['cue_triggered']) for r in rows)
    low=np.flatnonzero(scales<.9)
    recovered=bool(len(low) and np.any(scales[low[0]+1:]>=.98))
    return dict(trigger_count=triggers,minimum_scale=float(scales.min()),
        recovered=recovered,fraction_full_speed=float(np.mean(scales>=.98)))


def compare(output,plan,config):
    from train_rough_curriculum import complete_evaluation
    from run_rough_trial8_validation import route_readiness,write
    root=Path(output);seeds=plan['seeds'];n=len(seeds)
    pi_rows,pi=complete_evaluation(root/'pi',n)
    reactive_rows,reactive=complete_evaluation(root/'reactive',n)
    physical=route_readiness(reactive_rows,config,n)
    baseline_physical=route_readiness(pi_rows,config,n)
    a=traces(root/'pi');b=traces(root/'reactive')
    if sorted(a)!=seeds or sorted(b)!=seeds:raise ValueError('Paired traces do not match frozen seeds')
    paired=[]
    for seed in seeds:
        selected=windows(a[seed],plan['window'])
        if not selected:raise ValueError('No PI disturbance triggers; do not credit a quiet task')
        p=window_metrics(a[seed],selected);q=window_metrics(b[seed],selected)
        paired.append(dict(seed=seed,windows=selected,pi=p,reactive=q,response=response(b[seed]),
            ratios={k:q[k]/max(p[k],1e-12) for k in ('vibration_rms','slip_rms','vibration_energy_per_m','slip_energy_per_m')}))
    ratios={k:float(np.mean([r['reactive'][k] for r in paired])/np.mean([r['pi'][k] for r in paired]))
        for k in paired[0]['ratios']}
    medians={k:float(np.median([r['ratios'][k] for r in paired])) for k in ratios}
    m=lambda s,k:s['metrics_all_episodes'][k]['mean']
    time_ratio=m(reactive,'time_seconds')/m(pi,'time_seconds')
    slip_ratio=m(reactive,'rms_wheel_slip')/max(m(pi,'rms_wheel_slip'),1e-12)
    g=plan['gate'];energy_keys=('vibration_energy_per_m','slip_energy_per_m')
    benefit=any(ratios[k]<=1-g['min_quality_gain'] and medians[k]<1 for k in energy_keys)
    no_tradeaway=max(ratios[k] for k in energy_keys)<=g['max_other_quality_ratio']
    recovery=all(r['response']['recovered'] and r['response']['trigger_count']>0 for r in paired)
    passed=bool(physical['passed'] and baseline_physical['passed'] and benefit and no_tradeaway
        and recovery and time_ratio<=g['max_time_ratio'] and slip_ratio<=g['max_global_slip_ratio'])
    result=dict(passed=passed,physical_gate=physical,pi_physical_gate=baseline_physical,
        useful_window_benefit=benefit,no_window_quality_tradeaway=no_tradeaway,all_episodes_recovered=recovery,
        window_ratios=ratios,median_paired_ratios=medians,time_ratio=time_ratio,global_slip_ratio=slip_ratio,
        paired=paired,pi_summary=pi,reactive_summary=reactive,
        window_qualification='PI-trigger spatial unions; per-action energy allocated by interval overlap; no trigger-position input to control',
        qualification=plan['qualification'],optuna_held=True)
    write(root/'authority_result.json',result)
    return result
