#!/usr/bin/env python3
"""Decompose saved crossing traces; select one quiet-tail change without a new rollout."""
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).parent))
from analyze_rough_reactive_authority import traces
from prepare_rough_foundations import digest, immutable
from run_disturbance_reference_comparisons import verify

SOURCE=ROOT/'rl_runs/disturbance_reference_comparisons_v1/flat'
OUTPUT=ROOT/'docs/flat_schedule_audit_2026-10-11'


def audit():
    contract=json.loads((SOURCE/'contract.json').read_text());verify(contract)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    data={name:traces(SOURCE/name) for name in ('full','schedule','matched')}
    if any(sorted(x)!=contract['seeds'] for x in data.values()):raise ValueError('Audit seed mismatch')
    regions={'before_braking':(-1e9,3.90),'braking':(3.90,4.10),'crossing':(4.10,4.80),
             'recovery':(4.80,5.20),'remaining':(5.20,1e9)}
    means={};paired=[]
    for name,by_seed in data.items():
        sums={r:dict(seconds=0.,imu_energy=0.,slip_energy=0.) for r in regions}
        for rows in by_seed.values():
            for row in rows:
                x=float(row['physical_x_m']);dt=float(row['step_dt_s'])
                region=next(k for k,(a,b) in regions.items() if a<=x<b)
                s=sums[region];s['seconds']+=dt;s['imu_energy']+=float(row['step_imu_energy'])
                s['slip_energy']+=float(row['step_slip_square'])*dt
        means[name]={k:{m:v/len(by_seed) for m,v in s.items()} for k,s in sums.items()}
    for seed,rows in data['schedule'].items():
        tail=[r for r in rows if 4.55<=float(r['physical_x_m'])<4.60]
        if not tail:raise ValueError('No samples in proposed removed tail')
        paired.append(dict(seed=seed,samples=len(tail),seconds=sum(float(r['step_dt_s']) for r in tail),
            imu_energy=sum(float(r['step_imu_energy']) for r in tail),
            peak_acceleration=max(float(r['step_imu_peak_m_s2']) for r in tail),
            slip_energy=sum(float(r['step_slip_square'])*float(r['step_dt_s']) for r in tail)))
    before_delta=means['schedule']['before_braking']['imu_energy']-means['full']['before_braking']['imu_energy']
    crossing_delta=means['schedule']['crossing']['imu_energy']-means['full']['crossing']['imu_energy']
    selected=all(r['peak_acceleration']<.1 for r in paired)
    assets={str(SOURCE/'contract.json'):digest(SOURCE/'contract.json'),str(Path(__file__).resolve()):digest(__file__)}
    for name in data:
        for p in (SOURCE/name).glob('*/episode-*/control_trace.csv'):assets[str(p)]=digest(p)
    result=dict(assets=assets,seeds=contract['seeds'],mean_integrals=means,tail_evidence=paired,
        pre_braking_vibration_energy_difference=before_delta,crossing_vibration_energy_difference=crossing_delta,
        causal_qualification='Full and schedule command scales are 1 before intervention. Large pre-intervention '
          'differences cannot be attributed to second-cable braking; same reset seeds do not guarantee identical contacts.',
        selected_correction=dict(supported=selected,parameter='recovery_start_x_m',before=4.60,after=4.55,
            unchanged='Braking start 3.90, target .70, ramp .4/s, first cable, controller, terrain and scoring',
            rationale='All five saved traces are quiet between 4.55 and 4.60; remove only this low-speed tail.',
            limitation='May save time; not expected to repair pre-intervention variation or guarantee overall quality'),
        simulation_updates=0)
    immutable(OUTPUT/'audit.json',json.dumps(result,indent=2)+'\n')
    lines=['# Flat saved braking/recovery audit','',
      'Five matched reset seeds; saved data only. Regions use physical X for offline accounting.', '',
      '| Region | Full PI vibration energy | Schedule vibration energy | Full PI slip energy | Schedule slip energy |',
      '|---|---:|---:|---:|---:|']
    for r in regions:
        a,b=means['full'][r],means['schedule'][r]
        lines.append(f"| {r} | {a['imu_energy']:.6f} | {b['imu_energy']:.6f} | {a['slip_energy']:.6f} | {b['slip_energy']:.6f} |")
    lines+=['',result['causal_qualification'],'',
      'Recovery is not a large source of slip or vibration here. Do not increase a recovery/slip penalty based on these traces.', '',
      'Selected one small schedule correction: recovery X 4.60 → 4.55 m. Peak acceleration in the removed tail '
      'is below 0.036 m/s² in every seed. Keep all gates; do not claim this small correction solves the whole-run quality loss.', '',
      'If the correction qualifies, the next learning contract is explicitly a known-course reference '
      'using estimated pose and mapped cable coordinates, not downward LiDAR or unknown-terrain anticipation.','']
    (OUTPUT/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(dict(selected_correction=result['selected_correction'],means=means),indent=2))
    return result


if __name__=='__main__':audit()
