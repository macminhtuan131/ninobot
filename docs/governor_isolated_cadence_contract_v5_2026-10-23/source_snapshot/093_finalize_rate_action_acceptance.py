#!/usr/bin/env python3
"""Complete the additional reactive-reference acceptance check after the pilot."""
import json,time,os
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from prepare_rough_rate_pilot_v2 import OUTPUT,ROOT
from prepare_rough_foundations import digest,immutable

def response_events(rows):
    events=[]
    for index,row in enumerate(rows):
        if not int(row['cue_triggered']):continue
        start=float(row['elapsed_s']);segment=[]
        for r in rows[index:]:
            if segment and r['cue_phase']!='holding':break
            if r['cue_phase']=='holding':segment.append(r)
        if not segment:continue
        scales=[float(r['speed_scale']) for r in segment]
        end=float(segment[-1]['elapsed_s'])
        after=[r for r in rows if float(r['elapsed_s'])>end]
        recovery=next((float(r['elapsed_s'])-end for r in after if float(r['speed_scale'])>=.98),None)
        events.append(dict(trigger_s=start,holding_minimum_scale=min(scales),holding_mean_scale=float(np.mean(scales)),
            holding_duration_s=sum(float(r['step_dt_s']) for r in segment),
            holding_time_below_point90_s=sum(float(r['step_dt_s']) for r in segment if float(r['speed_scale'])<.9),
            recovery_after_holding_s=recovery))
    return events

def finalize():
    result=json.loads((OUTPUT/'comparison.json').read_text());plan=json.loads((OUTPUT/'pilot_contract.json').read_text())
    cap=plan['quality_gate']['max_other_quality_ratio']
    keys=('vibration_energy_per_m','slip_energy_per_m')
    paired=result['reactive_response_comparison']
    ratios={k:float(np.mean([r['ppo_window'][k] for r in paired])/max(np.mean([r['reference_window'][k] for r in paired]),1e-12)) for k in keys}
    global_ratios={k:result['ppo']['metrics_all_episodes'][k]['mean']/max(result['pi_reactive']['metrics_all_episodes'][k]['mean'],1e-12)
        for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
    reference_gate=all(v<=cap for v in (*ratios.values(),*global_ratios.values())) and result['reactive_physical_gate']['passed']
    from analyze_rough_reactive_authority import traces
    rt=traces(OUTPUT/'evaluation/pi_reactive');pt=traces(OUTPUT/'evaluation/ppo')
    response=[dict(seed=s,ppo=response_events(pt[s]),reactive_reference=response_events(rt[s])) for s in sorted(pt)]
    acceptance=dict(complete=True,contract_revision=52,source_comparison_sha256=digest(OUTPUT/'comparison.json'),
        original_physical_behavior_quality_gates_passed=result['pilot_passed'],reactive_quality_gate_passed=reference_gate,
        reactive_maximum_quality_ratio=cap,quality_ratios_to_reactive_reference=ratios,
        global_quality_ratios_to_reactive_reference=global_ratios,response_events=response,
        pilot_passed=bool(result['pilot_passed'] and reference_gate),optuna_held=True,
        next_step='Confirm unseen seeds/physical profiles before Optuna' if result['pilot_passed'] and reference_gate else
            'Inspect categorical response, exposure and reward contributions; preserve this pilot without extending it')
    (OUTPUT/'acceptance.json').write_text(json.dumps(acceptance,indent=2)+'\n')
    lines=['# Rough categorical rate-action pilot: final acceptance','',
        f"Pilot passed: **{acceptance['pilot_passed']}**. Original physical/behavior/quality gates: {result['pilot_passed']}. "
        f"Additional reactive-reference quality gate: {reference_gate}.",'',
        '| Controller | Physical arrivals | Mean time s | Truth path RMSE m | Vibration RMS | Slip RMS |',
        '|---|---:|---:|---:|---:|---:|']
    for label,gate in [('ppo','arrival_tracking_gate'),('pi_full',None),('pi_reactive','reactive_physical_gate'),('pi_matched',None)]:
        s=result[label];m=s['metrics_all_episodes']
        arrival=result[gate]['physical_arrival_rate'] if gate else result['pi_physical_gates']['full' if label=='pi_full' else 'matched']['physical_arrival_rate']
        vals=[m[k]['mean'] for k in ('time_seconds','truth_path_rmse_m','rms_vertical_acceleration_m_s2','rms_wheel_slip')]
        lines.append(f'| {label} | {round(arrival*5)}/5 | '+' | '.join(f'{v:.4f}' for v in vals)+' |')
    lines+=['','Against time-matched PI: `'+json.dumps(result['window_quality_ratios_to_pi_matched'])+'`.',
        'Against reactive PI: `'+json.dumps(ratios)+'`.',
        '', 'Holding depth, duration, recovery times and all individual outcomes are preserved in acceptance.json.',
        'One training seed, five paired scenarios on fixed nominal E1. This is not unseen-terrain or sim-to-real validation.',
        '', 'Next: '+acceptance['next_step']+'. Optuna remains held.','']
    (OUTPUT/'ACCEPTANCE.md').write_text('\n'.join(lines));print(json.dumps(acceptance,indent=2),flush=True)

def main():
    plan=json.loads((OUTPUT/'pilot_contract.json').read_text())
    immutable(OUTPUT/'reactive_acceptance_contract.json',json.dumps(dict(script_sha256=digest(__file__),
        comparison='Original immutable physical/behavior/matched-PI rules plus reactive-reference non-regression',
        maximum_reactive_window_and_global_quality_ratio=plan['quality_gate']['max_other_quality_ratio'],
        original_comparison_preserved=True,threshold_frozen_before_evaluation=True),indent=2)+'\n')
    deadline=time.monotonic()+10800
    while time.monotonic()<deadline:
        if (OUTPUT/'comparison.json').exists():finalize();return
        status=json.loads((OUTPUT/'status.json').read_text())
        if status['stage']=='interrupted':
            (OUTPUT/'acceptance_status.json').write_text(json.dumps(dict(complete=False,held=True,error=status.get('error'),optuna_held=True),indent=2)+'\n')
            raise SystemExit('Pilot interrupted; strict acceptance remains pending')
        time.sleep(5)
    raise SystemExit('Pilot acceptance deadline exceeded; inspect supervisor')

if __name__=='__main__':main()
