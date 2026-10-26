#!/usr/bin/env python3
"""One predeclared second batch for a borderline effect; no third batch or gate change."""
import fcntl
import json
import os
from pathlib import Path
import numpy as np
from prepare_rough_foundations import ROOT,digest,immutable
from prepare_rough_reactive_authority import OUTPUT as FIRST,prepare as verify_first
from prepare_rough_reactive_confirmation import OUTPUT,prepare
from run_rough_reactive_authority import run,state


def aggregate(config,plan):
    from train_rough_curriculum import complete_evaluation
    from run_rough_trial8_validation import route_readiness,write
    results=[json.loads((p/'authority_result.json').read_text()) for p in (FIRST,OUTPUT)]
    paired=[r for result in results for r in result['paired']]
    if len(paired)!=10 or len({r['seed'] for r in paired})!=10:raise ValueError('Need ten distinct paired seeds')
    pi_rows=[];reactive_rows=[]
    for root in (FIRST,OUTPUT):
        pi_rows+=complete_evaluation(root/'pi',5)[0];reactive_rows+=complete_evaluation(root/'reactive',5)[0]
    physical=route_readiness(reactive_rows,config,10);baseline=route_readiness(pi_rows,config,10)
    ratios={k:float(np.mean([r['reactive'][k] for r in paired])/np.mean([r['pi'][k] for r in paired]))
        for k in paired[0]['ratios']}
    medians={k:float(np.median([r['ratios'][k] for r in paired])) for k in ratios}
    mean=lambda rows,key:float(np.mean([float(r[key]) for r in rows]))
    time_ratio=mean(reactive_rows,'time_seconds')/mean(pi_rows,'time_seconds')
    slip_ratio=mean(reactive_rows,'rms_wheel_slip')/mean(pi_rows,'rms_wheel_slip')
    g=plan['gate'];keys=('vibration_energy_per_m','slip_energy_per_m')
    benefit=any(ratios[k]<=1-g['min_quality_gain'] and medians[k]<1 for k in keys)
    no_tradeaway=max(ratios[k] for k in keys)<=g['max_other_quality_ratio']
    recovery=all(r['response']['recovered'] and r['response']['trigger_count']>0 for r in paired)
    passed=bool(physical['passed'] and baseline['passed'] and benefit and no_tradeaway and recovery
        and time_ratio<=g['max_time_ratio'] and slip_ratio<=g['max_global_slip_ratio'])
    result=dict(passed=passed,physical_gate=physical,pi_physical_gate=baseline,window_ratios=ratios,
        median_paired_ratios=medians,time_ratio=time_ratio,global_slip_ratio=slip_ratio,
        useful_window_benefit=benefit,no_window_quality_tradeaway=no_tradeaway,
        all_episodes_recovered=recovery,paired=paired,
        first_result_sha256=digest(FIRST/'authority_result.json'),
        second_result_sha256=digest(OUTPUT/'authority_result.json'),
        pi_mean_time_s=mean(pi_rows,'time_seconds'),reactive_mean_time_s=mean(reactive_rows,'time_seconds'),
        qualification='Ten paired fixed-map reset seeds across two batches; no independent terrain/dynamics test or training seed claim',
        optuna_held=True)
    write(OUTPUT/'combined_result.json',result)
    state(OUTPUT,'combined authority passed' if passed else 'held: combined authority failed',
        passed=passed,physical_gate=physical,window_ratios=ratios,time_ratio=time_ratio,
        global_slip_ratio=slip_ratio,no_further_confirmation=True)
    return result


def main():
    os.chdir(ROOT);_,first=verify_first(FIRST);config,plan=prepare(OUTPUT)
    if first['gate']!=plan['gate'] or first['window']!=plan['window']:
        raise ValueError('Confirmation must preserve the original gates and window definition')
    if (FIRST/'config.yaml').read_bytes()!=(OUTPUT/'config.yaml').read_bytes():
        raise ValueError('Confirmation changed the controller or task configuration')
    immutable(OUTPUT/'confirmation_protocol.json',json.dumps(dict(
        script_sha256=digest(__file__),first_contract_sha256=digest(FIRST/'authority_contract.json'),
        first_result_sha256=digest(FIRST/'authority_result.json'),
        second_contract_sha256=digest(OUTPUT/'authority_contract.json'),
        rule='Exactly one second batch; aggregate ten pairs using unchanged original thresholds; no third batch'),indent=2)+'\n')
    lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:run(OUTPUT,config,plan);aggregate(config,plan)
    except BaseException as exc:state(OUTPUT,'interrupted',error=str(exc));raise


if __name__=='__main__':main()
