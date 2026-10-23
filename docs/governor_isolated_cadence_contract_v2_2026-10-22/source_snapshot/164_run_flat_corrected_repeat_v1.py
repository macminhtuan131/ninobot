#!/usr/bin/env python3
"""Four cold repeats of seed 65004; reuse the frozen command-clock correction."""
import fcntl
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(Path(__file__).parent), str(ROOT / 'src/nino_rl')]
from prepare_rough_foundations import digest, immutable
from run_disturbance_reference_comparisons import read, verify
from train_rough_curriculum import Processes, assert_isolated, complete_evaluation
from run_flat_bullet_contact_candidate_v3 import LIBRARY, RESET_LIBRARY
import analyze_flat_contact_convergence as contact_analysis
from recover_flat_contact_report import safe_window

SOURCE = ROOT / 'rl_runs/flat_command_clock_check_v2'
OUTPUT = ROOT / 'rl_runs/flat_corrected_repeat_v1'


def status(stage, **extra):
    value = dict(stage=stage, pid=os.getpid(), utc=datetime.now(timezone.utc).isoformat(),
                 optuna_held=True, training_started=False, **extra)
    (OUTPUT / 'status.json').write_text(json.dumps(value, indent=2) + '\n')
    print(stage, flush=True)


def prepare():
    if (OUTPUT / 'contract.json').exists():
        plan = read(OUTPUT / 'contract.json')
        verify(plan)
        return plan
    source = read(SOURCE / 'contract.json')
    verify(source)
    original = read(ROOT / 'rl_runs/flat_bullet_contact_candidate_v3/contract.json')
    verify(original)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assets = dict(source['assets'])
    for file in [Path(__file__), SOURCE / 'contract.json', LIBRARY, RESET_LIBRARY,
                 Path(contact_analysis.__file__), Path(__file__).with_name('recover_flat_contact_report.py')]:
        assets[str(file)] = digest(file)
    plan = dict(revision='flat_corrected_repeat_v1', assets=assets,
                world=source['world'], config=str(SOURCE / 'config.yaml'),
                python_overlay=str(SOURCE / 'python'), seed=65004, episodes=4,
                orders=[['full', 'schedule'], ['schedule', 'full']],
                schedule=original['schedule'], gates=original['gates'],
                reset_window_s=original['reset_window_s'],
                reset_stationary_threshold_rad_s=original['reset_stationary_threshold_rad_s'],
                reset_swivel_angle_tolerance_rad=original['reset_swivel_angle_tolerance_rad'],
                materiality=original['materiality'], physics_step_seconds=.001,
                cold_start='One new simulator per episode; no passive caster carryover',
                unchanged='Same corrected command clock, delivery barrier, world, geometry, controller, scoring and 4.60 m recovery schedule',
                qualification='Four repeated nominal episodes of one seed; no automatic broadening, training or Optuna',
                failed_arrivals_retained=True, optuna_held=True)
    immutable(OUTPUT / 'contract.json', json.dumps(plan, indent=2) + '\n')
    return plan


def analyze(plan):
    contact_analysis.window_metrics = safe_window
    episodes = []
    for repeat in (1, 2):
        for profile in ('full', 'schedule'):
            directory = OUTPUT / f'repeat_{repeat}' / profile
            batch = complete_evaluation(directory, 1)
            if batch is None:
                raise ValueError('Missing completed episode ' + str(directory))
            episode = batch[0][0]
            result = contact_analysis.episode_data(directory, episode, .001, plan)
            run = next(p.parent for p in directory.glob('*/summary.json') if read(p)['complete'])
            trace = contact_analysis.rows(run / 'episode-001/control_trace.csv')
            result.update(repeat=repeat, profile=profile, termination=episode['termination'],
                          all_reference_valid=all(int(r['reference_valid']) for r in trace),
                          max_clock_error_s=float(episode['max_clock_error_seconds']),
                          max_motion_lag_s=float(episode['max_motion_sensor_lag_seconds']),
                          self_command_wall_expiry_frames=sum(int(r['command_wall_would_expire']) for r in trace))
            episodes.append(result)
    def mean(rs, section, key):
        values = [r[section].get(key) for r in rs]
        return None if any(v is None for v in values) else float(np.mean(values))
    table = {}
    for profile in ('full', 'schedule'):
        rs = [r for r in episodes if r['profile'] == profile]
        table[profile] = dict(episodes=2, arrivals=sum(r['arrival'] for r in rs),
                             means={k: mean(rs, 'episode', k) for k in rs[0]['episode']},
                             crossing_means={k: mean(rs, 'crossing', k) for k in
                                             ('vibration_energy_per_m', 'slip_energy_per_m')})
    paired = []
    g = plan['gates']
    for repeat in (1, 2):
        full = next(r for r in episodes if r['repeat'] == repeat and r['profile'] == 'full')
        schedule = next(r for r in episodes if r['repeat'] == repeat and r['profile'] == 'schedule')
        covered = full['crossing']['available'] and schedule['crossing']['available']
        local = {k: schedule['crossing'][k] / max(full['crossing'][k], 1e-12) if covered else None
                 for k in ('vibration_energy_per_m', 'slip_energy_per_m')}
        global_ratios = {k: schedule['episode'][k] / max(full['episode'][k], 1e-12)
                         for k in ('rms_vertical_acceleration_m_s2', 'rms_wheel_slip')}
        tracking_ratio = schedule['episode']['truth_path_rmse_m'] / max(full['episode']['truth_path_rmse_m'], 1e-12)
        checks = dict(physical=all(r['arrival'] and r['episode']['truth_endpoint_error_m'] <= .2 + 1e-6 for r in (full, schedule)),
                      reset=all(r['reset_stationary'] and r['caster_reset_angles_valid'] for r in (full, schedule)),
                      reference=all(r['all_reference_valid'] for r in (full, schedule)),
                      timing=schedule['episode']['time_seconds'] <= g['maximum_mean_time_s'],
                      tracking=tracking_ratio <= g['tracking_ratio_to_full'], crossing_coverage=covered,
                      local_quality=covered and min(local.values()) <= 1-g['minimum_quality_gain'] and max(local.values()) <= g['maximum_other_quality_ratio'],
                      global_quality=min(global_ratios.values()) <= 1-g['minimum_quality_gain'] and max(global_ratios.values()) <= g['maximum_other_quality_ratio'])
        paired.append(dict(repeat=repeat, checks=checks, passed=all(checks.values()),
                           tracking_ratio=tracking_ratio, local_ratios=local, global_ratios=global_ratios))
    repeatability = []
    for profile in ('full', 'schedule'):
        a, b = [r for r in episodes if r['profile'] == profile]
        covered = a['crossing']['available'] and b['crossing']['available']
        relative = {k: b['crossing'][k]/max(a['crossing'][k], 1e-12)-1 if covered else None
                    for k in ('vibration_energy_per_m', 'slip_energy_per_m')}
        delta = b['episode']['truth_path_rmse_m'] - a['episode']['truth_path_rmse_m']
        material = not covered or any(abs(v) >= plan['materiality']['relative_quality'] for v in relative.values()) or abs(delta) >= plan['materiality']['absolute_tracking_m']
        repeatability.append(dict(profile=profile, covered=covered, crossing_relative_change=relative,
                                  tracking_delta_m=delta, material_variation=material))
    passed = all(p['passed'] for p in paired) and not any(r['material_variation'] for r in repeatability)
    result = dict(complete=True, episodes=episodes, table=table, paired_gates=paired,
                  repeatability=repeatability, screening_passed=passed,
                  failed_arrivals_retained=True, missing_crossing='Unavailable/null; never excluded or replaced with zero',
                  qualification=plan['qualification'], optuna_held=True, flat_ppo_started=False)
    (OUTPUT / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    lines = ['# Corrected flat repeat: seed 65004', '',
             'Four new cold episodes at 1 ms. Original brake x=3.90 m, recovery x=4.60 m. No learning or tuning.', '',
             '| Repeat | Controller | Arrival | Time s | Physical RMSE m | Vibration RMS | Slip RMS |',
             '|---|---|---|---:|---:|---:|---:|']
    for r in episodes:
        m = r['episode']
        lines.append(f"| {r['repeat']} | {r['profile']} | {r['arrival']} | {m['time_seconds']:.2f} | {m['truth_path_rmse_m']:.5f} | {m['rms_vertical_acceleration_m_s2']:.3f} | {m['rms_wheel_slip']:.4f} |")
    lines += ['', f'Screening passed: **{passed}**. Original physical/timing/tracking/quality limits retained.',
              'See analysis.json for paired gates, region tracking, motor response, contacts and repeatability.',
              'One repeated seed cannot establish numerical convergence, unseen-scenario robustness or PPO readiness. Broader tests remain held.', '']
    (OUTPUT / 'REPORT.md').write_text('\n'.join(lines))
    return result


def main():
    os.chdir(ROOT)
    plan = prepare()
    lock = (OUTPUT / 'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env = os.environ.copy()
    env.update(PYTHONUNBUFFERED='1', NINO_MATCH_SCALE='1')
    env['PYTHONPATH'] = plan['python_overlay'] + os.pathsep + str(ROOT / 'src/nino_rl') + os.pathsep + env.get('PYTHONPATH', '')
    processes = Processes(env, pi_integrator_profile='conditional_v1')
    try:
        for repeat, order in enumerate(plan['orders'], 1):
            for profile in order:
                directory = OUTPUT / f'repeat_{repeat}' / profile
                if complete_evaluation(directory, 1) is not None:
                    continue
                verify(plan)
                assert_isolated(79, 'nino_flat_79')
                status(f'repetition {repeat}/2: {profile}, seed 65004')
                processes.env['NINO_AUTHORITY_PROFILE'] = profile
                processes.world = processes.start(['ros2', 'launch', 'nino_rl', 'training_sim.launch.py',
                    'world:=' + plan['world'], 'world_name:=combined_flat_section', 'headless:=true',
                    'pi_integrator_profile:=conditional_v1', 'verbosity:=3'], directory / 'gazebo.log')
                processes.run(['ros2', 'run', 'nino_rl', 'wait_for_sim'], directory / 'readiness.log', timeout=90)
                processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py', '--config', plan['config'], '--timeout', '60'], directory / 'profile.log', timeout=65)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if 'Using [bullet] collision detector' in re.sub(r'\x1b\[[0-9;]*m', '', (directory / 'gazebo.log').read_text()):
                        break
                    time.sleep(.25)
                else:
                    raise ValueError('No runtime Bullet acknowledgement')
                for name, library, file in [('NinoFlatContactProbe', LIBRARY, 'contacts.csv'), ('NinoFlatResetProbe', RESET_LIBRARY, 'joints.csv')]:
                    payload = 'entity {name: "combined_flat_section" type: WORLD} plugins {name: ' + json.dumps(name) + ' filename: ' + json.dumps(str(library)) + ' innerxml: ' + json.dumps(f'<output>{directory / file}</output>') + '}'
                    log = directory / (name + '.log')
                    processes.run(['gz', 'service', '-s', '/world/combined_flat_section/entity/system/add', '--reqtype', 'gz.msgs.EntityPlugin_V', '--reptype', 'gz.msgs.Boolean', '--timeout', '5000', '--req', payload], log, timeout=10)
                    if 'data: true' not in log.read_text():
                        raise ValueError('Probe not acknowledged ' + name)
                processes.run(['ros2', 'run', 'nino_rl', 'evaluate_baseline', '--config', plan['config'], '--seeds', 65004, '--baseline-speed-scale', '1', '--control-trace', '--output', directory], directory / 'evaluate.log', timeout=900)
                processes.close()
                if complete_evaluation(directory, 1) is None:
                    raise ValueError('Incomplete episode ' + str(directory))
        status('four episodes complete; analyzing')
        result = analyze(plan)
        status('complete: broader testing held', screening_passed=result['screening_passed'])
    except BaseException as exc:
        status('interrupted; evidence preserved', error=str(exc))
        raise
    finally:
        processes.close()
        lock.close()


if __name__ == '__main__':
    main()
