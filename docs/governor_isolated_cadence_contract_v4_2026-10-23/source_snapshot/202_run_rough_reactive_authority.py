#!/usr/bin/env python3
"""Run a frozen hardware-trigger comparison; authorize a new pilot only on benefit."""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import sys
from prepare_rough_reactive_authority import OUTPUT,prepare,verify
from prepare_rough_foundations import ROOT,digest,immutable
from run_rough_hardware_confirmation import OUTPUT as CONFIRM,make_processes,verify as verify_confirmation
from run_hardware_sensor_preflight import OUTPUT as SENSOR


def state(output,stage,**extra):
    from run_rough_trial8_validation import write
    write(output/'status.json',dict(stage=stage,pid=os.getpid(),optuna_held=True,**extra))
    (output/'REPORT.md').write_text('# Reactive rough authority test\n\nStage: '+stage+'\n\nOptuna remains held.\n\n```json\n'+json.dumps(extra,indent=2)+'\n```\n')
    print(stage,flush=True)


def run(output,config,plan):
    from run_rough_trial8_validation import Validation,write
    from train_rough_curriculum import assert_isolated,complete_evaluation
    from analyze_rough_reactive_authority import compare
    confirmation=json.loads((CONFIRM/'confirmation_contract.json').read_text());verify_confirmation(confirmation)
    result=json.loads((CONFIRM/'feasibility_result.json').read_text())
    if not result['passed']:raise ValueError('Hardware feasibility has not passed')
    immutable(output/'runner_contract.json',json.dumps(dict(script_sha256=digest(__file__),
        analysis_sha256=digest(Path(__file__).with_name('analyze_rough_reactive_authority.py')),
        authority_contract_sha256=digest(output/'authority_contract.json')),indent=2)+'\n')
    validation=Validation(output/'workflow')
    env=validation.base_env.copy();env['PYTHONPATH']=str(output/'python')+os.pathsep+env.get('PYTHONPATH','')
    processes=make_processes(env,confirmation['profiles']['nominal']['launch'],SENSOR/'imu_bridge.yaml')
    write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
    try:
        for label in ('pi','reactive'):
            state(output,'evaluating '+label)
            directory=output/label
            if complete_evaluation(directory,len(plan['seeds'])) is not None:continue
            assert_isolated(78,'nino_rough_78');verify(plan);validation.check(output/'python')
            processes.launch(confirmation['world'],directory)
            live=deepcopy(validation.old_contract['comparable_trials']);live['world']=confirmation['world']
            live['assets'].update(plan['assets']);live['assets'].update(confirmation['assets'])
            validation.assert_inputs(live,live=True)
            processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',output/'config.yaml','--timeout','60'],directory/'profile.log',timeout=65)
            command=['ros2','run','nino_rl','evaluate_baseline','--config',output/'config.yaml',
                '--route','E1','--seeds',*plan['seeds'],'--control-trace','--output',directory]
            if label=='reactive':command+=['--reactive']
            processes.run(command,directory/'evaluate.log',timeout=600);processes.close()
        result=compare(output,plan,config)
        state(output,'authority passed' if result['passed'] else 'held: no qualified reactive benefit',
            passed=result['passed'],window_ratios=result['window_ratios'],time_ratio=result['time_ratio'],
            global_slip_ratio=result['global_slip_ratio'],physical_gate=result['physical_gate'])
        return result
    finally:processes.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true')
    args=parser.parse_args();os.chdir(ROOT);config,plan=prepare(OUTPUT)
    if not args.run:print('Prepared',OUTPUT);return
    lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:run(OUTPUT,config,plan)
    except BaseException as exc:state(OUTPUT,'interrupted',error=str(exc));raise


if __name__=='__main__':main()
