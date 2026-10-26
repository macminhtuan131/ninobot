#!/usr/bin/env python3
"""One 20480-step anchored actor pilot and preserved five-seed physical gates."""
import fcntl
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from prepare_rough_phase_anchor_v1 import ROOT, OUTPUT, prepare
from prepare_rough_foundations import digest
from run_disturbance_reference_comparisons import verify
from run_rough_hardware_confirmation import OUTPUT as CONFIRM, make_processes, verify as verify_physics
from run_hardware_sensor_preflight import OUTPUT as SENSOR


def state(stage, **extra):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    value = dict(stage=stage, pid=os.getpid(), utc=datetime.now(timezone.utc).isoformat(), optuna_held=True, **extra)
    (OUTPUT / 'status.json').write_text(json.dumps(value, indent=2) + '\n')
    print(stage, flush=True)


def main():
    os.chdir(ROOT)
    config, plan = prepare()
    lock = (OUTPUT / 'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from train_rough_curriculum import assert_isolated, complete_evaluation, checkpoint_steps, newest_checkpoint
    from run_rough_trial8_validation import Validation, write, route_readiness
    from run_rough_recovery_sigma_pilot import score_batches, verify_scoring_rules
    regression = deepcopy(plan)
    regression['evaluation_seeds'] = list(range(17100,17105))
    verify_scoring_rules(config, regression)
    confirmation = json.loads((CONFIRM / 'confirmation_contract.json').read_text())
    verify_physics(confirmation)
    validation = Validation(OUTPUT / 'workflow')
    write(validation.output / 'correction_contract.json', dict(snapshot_assets=plan['assets']))
    env = validation.base_env.copy()
    env['PYTHONPATH'] = str(OUTPUT / 'python') + os.pathsep + env.get('PYTHONPATH', '')
    processes = make_processes(env, confirmation['profiles']['nominal']['launch'], SENSOR / 'imu_bridge.yaml')
    def launch(directory):
        processes.close()
        assert_isolated(78, 'nino_rough_78')
        verify(plan)
        verify_physics(confirmation)
        processes.env['NINO_REACTIVE_RECORD_DIR'] = str(directory / 'actor_capture')
        validation.check(OUTPUT / 'python')
        processes.launch(confirmation['world'], directory)
        live = deepcopy(validation.old_contract['comparable_trials'])
        live['world'] = confirmation['world']
        live['assets'].update(plan['assets'])
        live['assets'].update(confirmation['assets'])
        validation.assert_inputs(live, live=True)
        processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py', '--config', OUTPUT / 'config.yaml', '--timeout', '60'], directory / 'profile.log', timeout=65)
    def evaluate(label, baseline=False, scale=1., model=None, reactive=False):
        directory = OUTPUT / 'evaluation' / label
        seeds = plan['evaluation_seeds']
        if complete_evaluation(directory, len(seeds)) is None:
            state('evaluating ' + label)
            launch(directory)
            command = ['ros2','run','nino_rl','evaluate_baseline' if baseline else 'evaluate','--config',OUTPUT/'config.yaml',
                       '--route','E1','--seeds',*seeds,'--control-trace','--output',directory]
            command += ['--baseline-speed-scale',scale] if baseline else ['--device','cuda','--model',model]
            if reactive:
                command += ['--reactive']
            processes.run(command, directory/'evaluate.log', timeout=900)
            processes.close()
        return complete_evaluation(directory, len(seeds))
    try:
        directory = OUTPUT / 'train'
        final = list(directory.glob('*/nino_ppo_final.zip'))
        if not final:
            if newest_checkpoint(directory):
                raise ValueError('Interrupted pilot preserved; no implicit resume')
            state('training one anchored actor pilot', requested_steps=20480)
            launch(directory)
            processes.run(['ros2','run','nino_rl','train','--config',OUTPUT/'config.yaml','--route','E1','--device','cuda',
                '--init-model',plan['source_actor'],'--timesteps','20480','--checkpoint-every','4096','--check-env','--output',directory],directory/'train.log',timeout=7200)
            processes.close()
            final = list(directory.glob('*/nino_ppo_final.zip'))
        if len(final) != 1 or checkpoint_steps(final[0]) != 20480:
            raise ValueError('Wrong pilot budget')
        transfer = json.loads(final[0].with_name('actor_transfer.json').read_text())
        if transfer['source_sha256'] != plan['source_actor_sha256'] or transfer['critic'] != 'fresh' or transfer['optimizer'] != 'fresh' or transfer['training_counter'] != 0:
            raise ValueError('Wrong actor-only initialization')
        pr, ppo = evaluate('ppo', model=final[0])
        fr, full = evaluate('pi_full', True)
        rr, reactive = evaluate('pi_reactive', True, reactive=True)
        scale = min(1., max(.55, full['metrics_all_episodes']['time_seconds']['mean']/ppo['metrics_all_episodes']['time_seconds']['mean']))
        mr, matched = evaluate('pi_matched', True, scale)
        result = score_batches(OUTPUT, config, plan, pr, ppo, fr, full, mr, matched, plan['evaluation_seeds'])
        from analyze_rough_reactive_authority import traces, window_metrics
        rt = traces(OUTPUT/'evaluation/pi_reactive')
        windows = result['disturbance_windows']
        cap = plan['quality_gate']['max_other_quality_ratio']
        ratios = {k:float(np.mean([x['ppo'][k] for x in windows])/max(np.mean([window_metrics(rt[x['seed']],x['windows'])[k] for x in windows]),1e-12)) for k in ('vibration_energy_per_m','slip_energy_per_m')}
        global_ratios = {k:ppo['metrics_all_episodes'][k]['mean']/max(reactive['metrics_all_episodes'][k]['mean'],1e-12) for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')}
        gate = route_readiness(rr, config, len(plan['evaluation_seeds']))
        result.update(pi_reactive=reactive, reactive_physical_gate=gate, reactive_quality_ratios=ratios,
            reactive_global_quality_ratios=global_ratios, matched_scale=scale, contract_revision=57,
            qualification='One gradient-bounded phase-anchor pilot; fixed nominal E1, one training seed')
        result['pilot_passed'] = bool(result['pilot_passed'] and gate['passed'] and all(v <= cap for v in (*ratios.values(),*global_ratios.values())))
        write(OUTPUT/'comparison.json',result)
        state('complete',pilot_passed=result['pilot_passed'],model=str(final[0]))
    except BaseException as exc:
        state('interrupted; evidence preserved',error=str(exc))
        raise
    finally:
        processes.close()
        lock.close()
        if digest(plan['preserved_checkpoint']) != plan['preserved_checkpoint_sha256']:
            raise RuntimeError('Preserved source checkpoint changed')


if __name__ == '__main__':
    main()
