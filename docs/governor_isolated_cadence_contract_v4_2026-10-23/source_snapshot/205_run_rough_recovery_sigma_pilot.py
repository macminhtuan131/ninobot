#!/usr/bin/env python3
"""Run the reward-only rough pilot; confirm new seeds/physics only if it passes."""
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from prepare_rough_foundations import ROOT, digest, immutable
from prepare_rough_recovery_sigma_pilot import OUTPUT, prepare, verify
import run_rough_observable_pilot_v2 as original_runner
from run_rough_hardware_confirmation import OUTPUT as PHYSICS, make_processes, verify as verify_physics
from run_hardware_sensor_preflight import OUTPUT as SENSOR

original_state = original_runner.state


def state(output, stage, **extra):
    original_state(output, stage, reward_change='velocity sigma .4 -> .1 m/s', contract_revision=48, **extra)
    report = output / 'REPORT.md'
    report.write_text(report.read_text().replace('Fresh rough longitudinal PPO pilot',
        'Rough recovery reward-only pilot').replace('Unchanged reward weights; no reactive action override.',
        'Only velocity sigma changes .4 -> .1 m/s (16x non-holding penalty); no reactive action override.'))


def score_batches(root, config, plan, ppo_rows, ppo, pi_rows, pi, matched_rows, matched, seeds):
    """The previous pilot's exact arrival, response and quality acceptance rules."""
    from analyze_rough_reactive_authority import traces, windows, window_metrics, response
    from prepare_rough_reactive_authority import OUTPUT as authority
    from run_rough_trial8_validation import route_readiness
    wc = json.loads((authority / 'authority_contract.json').read_text())['window']
    pt = traces(root / 'evaluation/ppo')
    ft = traces(root / 'evaluation/pi_full')
    mt = traces(root / 'evaluation/pi_matched')
    if any(sorted(t) != seeds for t in (pt, ft, mt)):
        raise ValueError('Confirmation seeds differ across controllers')
    m = lambda s, key: s['metrics_all_episodes'][key]['mean']
    duration_error = abs(m(matched, 'time_seconds') - m(ppo, 'time_seconds')) / m(ppo, 'time_seconds')
    paired = []
    for seed in seeds:
        ranges = windows(ft[seed], wc)
        if not ranges:
            raise ValueError('No reference disturbance windows')
        behavior = response(pt[seed])
        holding = [float(r['speed_scale']) for r in pt[seed] if r['cue_phase'] == 'holding']
        quiet = [float(r['speed_scale']) for r in pt[seed]
                 if r['cue_phase'] in ('ready', 'cooldown') and not int(r['cue_disturbed'])]
        hm, qm = (float(np.mean(holding)) if holding else None,
                  float(np.mean(quiet)) if quiet else None)
        behavior.update(mean_scale_during_holding=hm, mean_scale_during_quiet=qm,
            conditional_response=bool(holding and quiet and qm-hm >= .03 and qm >= .95 and behavior['recovered']))
        paired.append(dict(seed=seed, windows=ranges, pi=window_metrics(ft[seed], ranges),
            ppo=window_metrics(pt[seed], ranges), pi_matched=window_metrics(mt[seed], ranges), behavior=behavior))
    wr = {k: float(np.mean([r['ppo'][k] for r in paired]) / np.mean([r['pi_matched'][k] for r in paired]))
          for k in ('vibration_rms', 'slip_rms', 'vibration_energy_per_m', 'slip_energy_per_m')}
    qr = {k: m(ppo, k)/max(m(matched, k), 1e-12)
          for k in ('rms_vertical_acceleration_m_s2', 'rms_wheel_slip', 'truth_path_rmse_m')}
    arrival = route_readiness(ppo_rows, config, len(seeds))
    pi_gates = dict(full=route_readiness(pi_rows, config, len(seeds)),
                    matched=route_readiness(matched_rows, config, len(seeds)))
    conditional = all(r['behavior']['conditional_response'] for r in paired)
    learned = bool(arrival['passed'] and conditional and m(ppo, 'time_seconds') <= m(pi, 'time_seconds')*1.15)
    g = plan['quality_gate']
    energy = (wr['vibration_energy_per_m'], wr['slip_energy_per_m'])
    quality = bool(min(energy) <= 1-g['min_gain'] and max(energy) <= g['max_other_quality_ratio']
        and qr['rms_wheel_slip'] <= 1.10 and qr['rms_vertical_acceleration_m_s2'] <= 1.10
        and duration_error <= g['max_duration_match_error'])
    return dict(ppo=ppo, pi_full=pi, pi_matched=matched, arrival_tracking_gate=arrival,
        duration_match_relative_error=duration_error, quality_ratios_to_pi_matched=qr,
        disturbance_windows=paired, window_quality_ratios_to_pi_matched=wr,
        slowdown_and_recovery_present=conditional, learned_response_gate=learned,
        pi_physical_gates=pi_gates, ride_quality_gate=quality,
        pilot_passed=bool(learned and quality and all(v['passed'] for v in pi_gates.values())), optuna_held=True)


def verify_scoring_rules(config, plan):
    """Regression-check unchanged scoring against all of the source pilot's data."""
    from prepare_rough_observable_pilot_v2 import OUTPUT as source
    from train_rough_curriculum import complete_evaluation
    old = json.loads((source / 'comparison.json').read_text())
    batches = [complete_evaluation(source / 'evaluation' / label, 5)
               for label in ('ppo', 'pi_full', 'pi_matched')]
    new = score_batches(source, config, plan, *[v for pair in batches for v in pair], plan['evaluation_seeds'])
    for key in ('arrival_tracking_gate', 'pi_physical_gates', 'quality_ratios_to_pi_matched',
                'window_quality_ratios_to_pi_matched', 'disturbance_windows',
                'learned_response_gate', 'ride_quality_gate', 'pilot_passed'):
        if new[key] != old[key]:
            raise ValueError('Physical/quality scoring changed: ' + key)


def confirm(output, config, plan, model):
    from run_rough_trial8_validation import Validation, write
    from train_rough_curriculum import assert_isolated, complete_evaluation
    physics = json.loads((PHYSICS / 'confirmation_contract.json').read_text())
    verify_physics(physics)
    validation = Validation(output / 'confirmation/workflow')
    write(validation.output / 'correction_contract.json', dict(snapshot_assets=plan['assets']))
    env = validation.base_env.copy()
    env['PYTHONPATH'] = str(output / 'python') + os.pathsep + env.get('PYTHONPATH', '')
    seeds = plan['confirmation']['seeds']
    results = {}
    for profile in plan['confirmation']['profiles']:
        root = output / 'confirmation' / profile
        processes = make_processes(env.copy(), physics['profiles'][profile]['launch'], SENSOR / 'imu_bridge.yaml')
        def evaluate(label, baseline=False, scale=1.):
            directory = root / 'evaluation' / label
            if complete_evaluation(directory, len(seeds)) is None:
                processes.close()
                assert_isolated(78, 'nino_rough_78')
                verify(plan); verify_physics(physics); validation.check(output / 'python')
                processes.env['NINO_REACTIVE_RECORD_DIR'] = str(directory / 'actor_capture')
                processes.launch(physics['world'], directory)
                live = deepcopy(validation.old_contract['comparable_trials'])
                live['world'] = physics['world']; live['assets'].update(plan['assets']); live['assets'].update(physics['assets'])
                validation.assert_inputs(live, live=True)
                processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
                               '--config', output / 'config.yaml', '--timeout', '60'], directory / 'profile.log', timeout=65)
                command = ['ros2', 'run', 'nino_rl', 'evaluate_baseline' if baseline else 'evaluate',
                    '--config', output / 'config.yaml', '--route', 'E1', '--seeds', *seeds,
                    '--control-trace', '--output', directory]
                command += ['--baseline-speed-scale', scale] if baseline else ['--device', 'cuda', '--model', model]
                processes.run(command, directory / 'evaluate.log', timeout=600)
                processes.close()
            result = complete_evaluation(directory, len(seeds))
            if result[1]['evaluation_seeds'] != seeds:
                raise ValueError('Saved confirmation has incompatible seeds')
            return result
        try:
            state(output, 'confirming unseen seeds on ' + profile, prior_profiles=results)
            ppo_rows, ppo = evaluate('ppo')
            pi_rows, pi = evaluate('pi_full', True)
            scale = min(1., max(config['longitudinal_control']['minimum_scale'],
                pi['metrics_all_episodes']['time_seconds']['mean'] / ppo['metrics_all_episodes']['time_seconds']['mean']))
            matched_rows, matched = evaluate('pi_matched', True, scale)
            result = score_batches(root, config, plan, ppo_rows, ppo, pi_rows, pi, matched_rows, matched, seeds)
            result.update(profile=profile, physical_profile=physics['profiles'][profile], matched_scale=scale,
                qualification=plan['confirmation']['qualification'])
            write(root / 'comparison.json', result)
            results[profile] = dict(passed=result['pilot_passed'], comparison=str(root / 'comparison.json'),
                physical_gate=result['arrival_tracking_gate'], learned_response_gate=result['learned_response_gate'],
                ride_quality_gate=result['ride_quality_gate'])
            write(output / 'confirmation/result.json', dict(profiles=results, complete=False, optuna_held=True))
        finally:
            processes.close()
    passed = all(v['passed'] for v in results.values())
    write(output / 'confirmation/result.json', dict(profiles=results, complete=True, passed=passed,
        model=str(model), seeds=seeds, qualification=plan['confirmation']['qualification'], optuna_held=True))
    state(output, 'complete: confirmation passed' if passed else 'complete: confirmation failed',
          pilot_passed=True, confirmation_passed=passed, confirmation=results, model=str(model))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    output = args.output.resolve()
    config, plan = prepare(output)
    if not args.run:
        print('Prepared reward-only contract; no simulation/training started.')
        return
    lock = (output / 'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        if not (output / 'verification.json').exists():
            state(output, 'verifying single-change initialization and reward')
            subprocess.run([sys.executable, 'src/nino_rl/scripts/verify_rough_recovery_sigma_pilot.py',
                            '--snapshot', output], check=True)
        verification = json.loads((output / 'verification.json').read_text())
        if not all(verification[k] for k in ('single_reward_parameter_changed', 'initial_actor_critic_identical',
                'zero_step_counters', 'old_contract_resume_rejected')):
            raise ValueError('New-contract initialization checks failed')
        verify_scoring_rules(config, plan)
        immutable(output / 'workflow_contract.json', json.dumps(dict(script_sha256=digest(__file__),
            pilot_contract_sha256=digest(output / 'pilot_contract.json'),
            source_runner_sha256=digest(Path(original_runner.__file__)),
            verification_sha256=digest(output / 'verification.json'), scoring_regression_passed=True), indent=2)+'\n')
        original_runner.state = state
        original_runner.run(output, config, plan)
        comparison = output / 'comparison.json'
        if not comparison.exists():
            return
        result = json.loads(comparison.read_text())
        if not result['pilot_passed']:
            state(output, 'complete: pilot failed; confirmation held', pilot_passed=False,
                learned_response_gate=result['learned_response_gate'], ride_quality_gate=result['ride_quality_gate'],
                physical_gate=result['arrival_tracking_gate'], comparison=str(comparison))
            return
        model = Path(result['ppo']['model'])
        confirm(output, config, plan, model)
    except BaseException as exc:
        state(output, 'interrupted', error=str(exc))
        raise


if __name__ == '__main__':
    main()
