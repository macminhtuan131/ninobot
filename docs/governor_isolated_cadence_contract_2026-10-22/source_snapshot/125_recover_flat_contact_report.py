#!/usr/bin/env python3
"""Failure-aware analysis of preserved contact episodes; never invent coverage."""
import argparse,json
from pathlib import Path
import numpy as np
import analyze_flat_contact_convergence as original
from train_rough_curriculum import complete_evaluation
from prepare_rough_foundations import digest

REAL_WINDOW=original.window_metrics
def safe_window(rows,ranges):
    try:return dict(REAL_WINDOW(rows,ranges),available=True,reason=None)
    except ValueError as exc:
        if str(exc)!='No covered reference disturbance windows':raise
        return dict(available=False,reason=str(exc),duration_s=None,coverage_s=None,
            distance_m=None,vibration_energy_per_m=None,slip_energy_per_m=None)

def mean(rows,section,key):
    values=[r[section].get(key) for r in rows]
    return None if any(v is None for v in values) else float(np.mean(values))

def analyze(source,output):
    contract=json.loads((source/'contract.json').read_text());original.window_metrics=safe_window
    groups={};table={};gates=[];pairs=[]
    for repeat in (1,2):
        for step,profile in contract['profiles'].items():
            for controller in ('full','schedule'):
                values={}
                for seed in contract['seeds']:
                    directory=source/f'repeat_{repeat}'/step/controller/f'seed_{seed}'
                    batch=complete_evaluation(directory,1)
                    if batch is None:raise ValueError('Missing completed episode '+str(directory))
                    row=original.episode_data(directory,batch[0][0],profile['step_seconds'],contract)
                    row['termination']=batch[0][0]['termination'];values[seed]=row
                groups[f'{repeat}/{step}/{controller}']=values
    keys=('vibration_energy_per_m','slip_energy_per_m')
    for step in contract['profiles']:
        for controller in ('full','schedule'):
            rows=[groups[f'{rep}/{step}/{controller}'][seed] for rep in (1,2) for seed in contract['seeds']]
            table[f'{step}/{controller}']=dict(episodes=len(rows),arrivals=sum(r['arrival'] for r in rows),
                means={k:mean(rows,'episode',k) for k in rows[0]['episode']},
                crossing_available=sum(r['crossing']['available'] for r in rows),
                window_means={k:mean(rows,'crossing',k) for k in keys})
        for rep in (1,2):
            schedule=[groups[f'{rep}/{step}/schedule'][s] for s in contract['seeds']]
            full=[groups[f'{rep}/{step}/full'][s] for s in contract['seeds']]
            def ratio(section,key):
                a,b=mean(schedule,section,key),mean(full,section,key)
                return None if a is None or b is None or b<=0 else a/b
            local={k:ratio('crossing',k) for k in keys}
            quality={k:ratio('episode',k) for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
            tracking=ratio('episode','truth_path_rmse_m')
            coverage=all(r['crossing']['available'] for r in schedule+full)
            gate=dict(step=step,repeat=rep,physical=all(r['arrival'] and r['episode']['truth_endpoint_error_m']<=.2+1e-6 for r in schedule+full),
                reset_stationary=all(r['reset_stationary'] and r['caster_reset_angles_valid'] for r in schedule+full),
                timing=mean(schedule,'episode','time_seconds')<=18.5,tracking=tracking<=1.05,tracking_ratio=tracking,
                crossing_coverage=coverage,local_quality=coverage and min(local.values())<=.9 and max(local.values())<=1.,window_ratios=local,
                global_quality=min(quality.values())<=.9 and max(quality.values())<=1.,global_ratios=quality)
            gate['passed']=all(gate[k] for k in ('physical','reset_stationary','timing','tracking','crossing_coverage','local_quality','global_quality'));gates.append(gate)
    for rep in (1,2):
        for controller in ('full','schedule'):
            for seed in contract['seeds']:
                a,b=(groups[f'{rep}/{step}/{controller}'][seed] for step in ('1ms','2ms'))
                covered=a['crossing']['available'] and b['crossing']['available']
                relative={k:a['crossing'][k]/max(b['crossing'][k],1e-12)-1 if covered else None for k in keys}
                rmse=a['episode']['truth_path_rmse_m']-b['episode']['truth_path_rmse_m']
                depth=lambda r:max((v['maximum_penetration_m'] for v in r['second_cable_contacts'].values()),default=0.)
                delta=depth(a)-depth(b) if covered else None
                pairs.append(dict(repeat=rep,control=controller,seed=seed,crossing_coverage=covered,
                    relative_crossing_change=relative,tracking_delta_m=rmse,maximum_penetration_delta_m=delta,
                    material_change=(any(abs(v)>=.1 for v in relative.values()) or abs(rmse)>=.005 or abs(delta)>=.001) if covered else None))
    material=any(r['material_change'] is True for r in pairs);covered=all(r['crossing_coverage'] for r in pairs)
    result=dict(complete=True,episodes=16,arrivals=sum(v['arrivals'] for v in table.values()),groups=groups,table=table,gates=gates,
        step_pairs=pairs,material_step_dependence=material,complete_paired_crossing_coverage=covered,
        screening_gates_passed=all(g['passed'] for g in gates) and covered and not material,
        source=str(source),source_contract_sha256=digest(source/'contract.json'),analyzer_sha256=digest(__file__),
        failed_arrivals_retained=True,missing_windows='Unavailable/null; no zero substitution and no scenario exclusion',
        flat_ppo_started=False,optuna_held=True)
    output.mkdir(parents=True,exist_ok=True);(output/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# Failure-aware flat contact report','',f"Collected 16 episodes; physical arrivals {result['arrivals']}/16. Screening passed: {result['screening_gates_passed']}.",
        'Missing crossing measurements are unavailable, not zero. Failed arrivals remain in all episode totals.','',
        '| Physics / controller | Arrival | Time s | Physical RMSE m | Vibration RMS | Slip RMS | Second-cable coverage |','|---|---:|---:|---:|---:|---:|---:|']
    for key,row in table.items():
        m=row['means'];lines.append(f"| {key} | {row['arrivals']}/4 | {m['time_seconds']:.2f} | {m['truth_path_rmse_m']:.4f} | {m['rms_vertical_acceleration_m_s2']:.3f} | {m['rms_wheel_slip']:.3f} | {row['crossing_available']}/4 |")
    lines+=['','Unsuccessful durations are time to termination, not arrival times. Do not interpret the pooled failed-group time as faster completion.',
        '',f'Material sensitivity among covered pairs: {material}. Complete paired coverage: {covered}.',
        'Original reports, episodes and models are untouched. No flat learning or Optuna is authorized by this report.','']
    (output/'REPORT.md').write_text('\n'.join(lines));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=analyze(a.source.resolve(),a.output.resolve());print(json.dumps({k:r[k] for k in ('complete','episodes','arrivals','screening_gates_passed')}))
