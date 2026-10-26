#!/usr/bin/env python3
"""Bounded reference comparisons, preserving old models and physical scoring."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'src/nino_rl'), str(Path(__file__).parent)]
from prepare_rough_foundations import digest, immutable

OUTPUT = ROOT / 'rl_runs/disturbance_reference_comparisons_v1'
ROUGH = ROOT / 'rl_runs/rough_recovery_sigma_pilot_v1'
FLAT = ROOT / 'rl_runs/foundations_20261011/flat_authority_v1'


def read(path):
    return json.loads(Path(path).read_text())


def verify(plan):
    for path, expected in plan['assets'].items():
        if digest(path) != expected:
            raise ValueError('Frozen reference input changed: ' + path)


def status(output, stage, **extra):
    output.mkdir(parents=True, exist_ok=True)
    data = dict(stage=stage, pid=os.getpid(), updated_utc=datetime.now(timezone.utc).isoformat(),
                optuna_held=True, **extra)
    temporary = output / 'status.tmp'
    temporary.write_text(json.dumps(data, indent=2)+'\n')
    temporary.replace(output / 'status.json')
    print(stage, flush=True)


def replace(code, anchor, replacement):
    if code.count(anchor) != 1:
        raise ValueError('Unexpected frozen insertion point: ' + anchor)
    return code.replace(anchor, replacement)


def flat_target(x, profile, matched_scale=1.):
    if profile == 'full':
        return 1.
    if profile == 'matched':
        return matched_scale
    if profile != 'schedule':
        raise ValueError('Unknown flat intervention')
    # Known second-cable position, estimated X only. First cable is unchanged.
    return .70 if 4.45-.55 <= x <= 4.45+.15 else 1.


def scripted_scale(env, previous):
    target = flat_target(env.ros.snapshot().x, os.environ['NINO_AUTHORITY_PROFILE'],
                        float(os.environ.get('NINO_MATCH_SCALE', '1')))
    delta = .4 * env.control_dt
    return min(previous+delta, max(previous-delta, target))


def prepare(course):
    output = OUTPUT / course
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / 'contract.json'
    if manifest.exists():
        plan = read(manifest); verify(plan)
        return output, yaml.safe_load((output / 'config.yaml').read_text()), plan
    source = ROUGH if course == 'rough' else FLAT
    source_manifest = source / ('pilot_contract.json' if course == 'rough' else 'authority_contract.json')
    original = read(source_manifest)
    groups = ('assets', 'implementation') if course == 'rough' else ('assets',)
    for group in groups:
        for path, expected in original[group].items():
            if digest(path) != expected:
                raise ValueError('Source experiment changed: '+path)
    package = output / 'python/nino_rl'
    shutil.copytree(source / 'python/nino_rl', package,
                    ignore=shutil.ignore_patterns('__pycache__'), dirs_exist_ok=True)
    code = (package / 'evaluation.py').read_text()
    if course == 'rough':
        # Restore the *original validated scripted controller* only in baseline
        # evaluation. Never override a PPO action or alter a saved model.
        code = replace(code,
            '            if args.reactive:\n                raise ValueError("Observable pilot compares free PPO with fixed PI, not a teacher override")',
            '            if args.reactive:\n'
            '                from nino_rl.reactive_speed import ReactiveSpeed\n'
            '                reference_monitor = ReactiveSpeed(config["reactive_probe"], env.ros.imu_includes_gravity)')
        code = replace(code, '                if args.reactive: action[0] = encode_speed(target, config)',
            '                if args.reactive:\n'
            '                    target, cue_trace = reference_monitor.update(env.previous_robot_state,\n'
            '                        env.ros.desired_twist(), env.longitudinal_scale, env.control_dt)\n'
            '                    action[0] = encode_speed(target, config)')
        seeds = list(range(17100, 17105))
        protocol = dict(reference='Original sensor-only ReactiveSpeed .70/.60s/mandatory recovery/1.20s cooldown',
            preserved='Fixed E1 half-relief, nominal physics, PI yaw, .4 scale/s ramp, hardware inputs, physical gates',
            frozen_ppo=str(ROUGH / 'comparison.json'), no_ppo_action_override=True,
            min_window_gain=.05, max_other_window_ratio=1.10, max_duration_match_error=.03,
            max_time_ratio=1.15, max_global_quality_ratio=1.10)
    else:
        from encoder_history_transport import patch_interface
        interface = package / 'ros_interface.py'
        interface.write_text(patch_interface(interface.read_text()))
        import inspect
        (package / 'crossing_authority.py').write_text('import os\n\n'+
            inspect.getsource(flat_target)+'\n'+inspect.getsource(scripted_scale))
        env = package / 'ros_env.py'
        env.write_text(replace(env.read_text(), '                "sim_time_s": ended_sim, "elapsed_s": elapsed,',
            '                "step_dt_s": step_dt, "step_imu_energy": imu["square_integral"],\n'
            '                "step_imu_coverage_s": imu["duration"], "step_imu_peak_m_s2": imu["peak"],\n'
            '                "step_slip_square": (slip_left**2+slip_right**2)/2,\n'
            '                "sim_time_s": ended_sim, "elapsed_s": elapsed,'))
        seeds = list(range(65000, 65005))
        limits = read(ROOT / 'rl_runs/flat_value_scaled_seed43_v1/repeat_plan.json')['promotion_gates']
        protocol = dict(second_cable_x_m=4.45, braking_start_x_m=3.90, recovery_start_x_m=4.60,
            target_scale=.70, ramp_scale_per_s=.4, first_cable_unchanged=True,
            encoder_transport_history=100, all_three_profiles_same_transport=True,
            physical_gates=limits, max_duration_match_error=.03,
            window=[4.10, 4.80], min_window_gain=.10, max_other_window_ratio=1.,
            qualification='Known cable position + estimated odometry; authority test, not hardware-only learned behavior')
    (package / 'evaluation.py').write_text(code)
    (package / 'train.py').write_text('def main():\n    raise SystemExit("Reference evaluation only; learning needs a new contract")\n')
    config = yaml.safe_load((source / 'config.yaml').read_text())
    immutable(output / 'config.yaml', yaml.safe_dump(config, sort_keys=False))
    for path in package.glob('*.py'):
        compile(path.read_text(), str(path), 'exec')
    assets = dict(original['assets'])
    if course == 'rough':
        assets.update(original['implementation'])
        for directory in (ROUGH / 'evaluation').iterdir():
            for path in directory.rglob('*'):
                if path.is_file(): assets[str(path)] = digest(path)
        assets[str(ROUGH / 'comparison.json')] = digest(ROUGH / 'comparison.json')
    assets.update({str(p): digest(p) for p in package.glob('*.py')})
    for path in (Path(__file__), source_manifest, output / 'config.yaml',
                 Path(__file__).with_name('analyze_rough_reactive_authority.py'),
                 Path(__file__).with_name('run_rough_trial8_validation.py'),
                 Path(__file__).with_name('train_rough_curriculum.py')):
        assets[str(path)] = digest(path)
    plan = dict(revision=course+'_disturbance_reference_v1', course=course, assets=assets,
                seeds=seeds, protocol=protocol, updates=0, training_enabled=False, optuna_held=True)
    immutable(manifest, json.dumps(plan, indent=2)+'\n')
    return output, config, plan


def metrics(summary):
    return {k: summary['metrics_all_episodes'][k]['mean'] for k in
            ('time_seconds', 'truth_path_rmse_m', 'rms_vertical_acceleration_m_s2', 'rms_wheel_slip')}


def response_modes(rows):
    modes = {k: dict(seconds=0., slip_integral=0., scale_integral=0.) for k in
             ('slowdown','acceleration','persistent_reduced','steady_cruise','startup_or_approach')}
    previous = None
    for r in rows:
        scale, dt = float(r['speed_scale']), float(r['step_dt_s'])
        rate = (scale-previous)/dt if previous is not None else 0.
        previous = scale
        mode = ('startup_or_approach' if float(r['elapsed_s'])<=1. or float(r['physical_goal_distance_m'])<.5 else
                'slowdown' if rate<-.05 else 'acceleration' if rate>.05 else
                'persistent_reduced' if scale<.95 else 'steady_cruise')
        m = modes[mode]; m['seconds'] += dt
        m['slip_integral'] += float(r['step_slip_square'])*dt
        m['scale_integral'] += scale*dt
    for m in modes.values():
        m['slip_rms'] = (m['slip_integral']/m['seconds'])**.5 if m['seconds'] else None
        m['mean_scale'] = m['scale_integral']/m['seconds'] if m['seconds'] else None
    return modes


def report(output, course, summaries, result):
    lines = ['# '+course.title()+' disturbance reference comparison', '',
             'Fixed seeds/config/geometry. No learning updates. Optuna held.', '',
             '| Controller | Arrivals | Time s | Physical RMSE m | Vibration RMS | Slip RMS |',
             '|---|---:|---:|---:|---:|---:|']
    for label, s in summaries.items():
        m = metrics(s)
        lines.append(f"| {label} | {round(s['success_rate']*s['episodes'])}/{s['episodes']} | "
                     + ' | '.join(f'{v:.6f}' for v in m.values())+' |')
    lines += ['', '```json', json.dumps(result, indent=2), '```', '',
              'Phase comparisons are associational. Five fixed-map seeds are a screen, not generalization.',
              'Physical thresholds are unchanged. A failure holds training; no additional schedule search.', '']
    (output / 'REPORT.md').write_text('\n'.join(lines))


def analyze_rough(output, config, plan, summaries, batches):
    from analyze_rough_reactive_authority import traces, windows, window_metrics, response
    from run_rough_trial8_validation import route_readiness
    from prepare_rough_reactive_authority import OUTPUT as AUTHORITY
    original = read(ROUGH / 'comparison.json')
    wc = read(AUTHORITY / 'authority_contract.json')['window']
    paths = dict(ppo=ROUGH / 'evaluation/ppo', pi_full=ROUGH / 'evaluation/pi_full',
                 pi_ppo_matched=ROUGH / 'evaluation/pi_matched',
                 reactive=output / 'reactive', pi_reactive_matched=output / 'matched')
    trace = {k: traces(p) for k, p in paths.items()}
    if any(sorted(v) != plan['seeds'] for v in trace.values()): raise ValueError('Rough seeds differ')
    paired = []
    for seed in plan['seeds']:
        ranges = windows(trace['pi_full'][seed], wc)
        if not ranges: raise ValueError('No PI-selected disturbance windows')
        row = dict(seed=seed, windows=ranges, profiles={})
        for label in paths:
            rows = trace[label][seed]
            row['profiles'][label] = dict(window=window_metrics(rows, ranges), response=response(rows))
            if label in ('ppo', 'reactive'):
                scales = [float(r['speed_scale']) for r in rows if r['cue_phase']=='holding']
                row['profiles'][label]['holding_mean_scale'] = float(np.mean(scales)) if scales else None
                row['profiles'][label]['holding_seconds'] = sum(float(r['step_dt_s']) for r in rows if r['cue_phase']=='holding')
                row['profiles'][label]['modes'] = response_modes(rows)
        paired.append(row)
    keys = ('vibration_energy_per_m', 'slip_energy_per_m')
    ratios = {k: float(np.mean([r['profiles']['reactive']['window'][k] for r in paired]) /
                       np.mean([r['profiles']['pi_reactive_matched']['window'][k] for r in paired])) for k in keys}
    median = {k: float(np.median([r['profiles']['reactive']['window'][k] /
                 r['profiles']['pi_reactive_matched']['window'][k] for r in paired])) for k in keys}
    m = {k: metrics(v) for k,v in summaries.items()}
    g = plan['protocol']
    physical = {k: route_readiness(rows, config, len(plan['seeds'])) for k,(rows, _) in batches.items()}
    error = abs(m['reactive']['time_seconds']-m['pi_reactive_matched']['time_seconds'])/m['reactive']['time_seconds']
    passed = bool(all(v['passed'] for v in physical.values()) and
        any(ratios[k]<=1-g['min_window_gain'] and median[k]<1 for k in keys) and
        max(ratios.values())<=g['max_other_window_ratio'] and error<=g['max_duration_match_error'] and
        m['reactive']['time_seconds']<=m['pi_full']['time_seconds']*g['max_time_ratio'] and
        all(r['profiles']['reactive']['response']['recovered'] for r in paired) and
        all(m['reactive'][k]/m['pi_reactive_matched'][k]<=g['max_global_quality_ratio']
            for k in ('rms_vertical_acceleration_m_s2','rms_wheel_slip')))
    result = dict(reference_passed=passed, physical_gates=physical,
        window_ratios_to_time_matched_pi=ratios, median_paired_ratios=median,
        duration_match_relative_error=error, paired=paired, saved_ppo_gate=original['pilot_passed'],
        next_step='Select a single holding-response correction under a new contract' if passed else
                  'Hold another PPO pilot: scripted reference did not qualify against time-matched PI',
        optuna_held=True)
    (output / 'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    brief = {k:v for k,v in result.items() if k!='paired'}
    report(output,'rough',summaries,brief)
    return result


def analyze_flat(output, plan, summaries, batches):
    from analyze_rough_reactive_authority import traces, window_metrics
    from nino_rl.evaluation import compare_summaries
    from run_flat_seed_repeat import promotion_gates
    trace = {k: traces(output/k) for k in ('full','schedule','matched')}
    if any(sorted(v)!=plan['seeds'] for v in trace.values()): raise ValueError('Flat seeds differ')
    ranges = [plan['protocol']['window']]
    windows = {k:[window_metrics(trace[k][seed],ranges) for seed in plan['seeds']] for k in trace}
    ratios = {k:float(np.mean([r[k] for r in windows['schedule']])/
                      np.mean([r[k] for r in windows['matched']]))
              for k in ('vibration_energy_per_m','slip_energy_per_m')}
    pair = dict(pi=dict(report=summaries['full']), ppo=dict(report=summaries['schedule']),
                comparison=compare_summaries(summaries['full'],summaries['schedule']))
    physical = promotion_gates(pair,dict(promotion_gates=plan['protocol']['physical_gates']))
    error = abs(metrics(summaries['matched'])['time_seconds']-
                metrics(summaries['schedule'])['time_seconds'])/metrics(summaries['schedule'])['time_seconds']
    passes = bool(all(physical[k] for k in ('physical_arrival','completion','tracking','quality')) and
        all(s['success_rate']==1 for s in summaries.values()) and
        error<=plan['protocol']['max_duration_match_error'] and
        min(ratios.values())<=1-plan['protocol']['min_window_gain'] and
        max(ratios.values())<=plan['protocol']['max_other_window_ratio'])
    result = dict(authority_passed=passes, existing_flat_gates=physical,
        window_ratios_to_time_matched_pi=ratios, duration_match_relative_error=error,
        windows=windows, source='Known cable X + estimated pose; no physical pose used for action',
        next_step='Prepare one new-contract PPO pilot for the demonstrated crossing mechanism' if passes else
                  'Hold PPO: the single schedule failed the fixed arrival/time/tracking/quality gate',
        optuna_held=True)
    (output / 'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    report(output,'flat',summaries,{k:v for k,v in result.items() if k!='windows'})
    return result


def run_course(course):
    from train_rough_curriculum import Processes, assert_isolated, complete_evaluation
    from nino_rl.tuning_trials import assert_trial_inputs
    output, config, plan = prepare(course)
    lock = (output/'worker.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    domain = 78 if course=='rough' else 79
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID=str(domain),NINO_ROS_DOMAIN_ID=str(domain),
               GZ_PARTITION=f'nino_{course}_{domain}',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env['PYTHONPATH'] = str(output/'python')+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','')
    if course=='rough':
        from run_rough_hardware_confirmation import OUTPUT as PHYSICS, make_processes, verify as verify_physics
        from run_hardware_sensor_preflight import OUTPUT as SENSOR
        from run_rough_trial8_validation import Validation, write
        physics = read(PHYSICS/'confirmation_contract.json'); verify_physics(physics)
        validation = Validation(output/'workflow')
        write(validation.output/'correction_contract.json',dict(snapshot_assets=plan['assets']))
        processes = make_processes(env,physics['profiles']['nominal']['launch'],SENSOR/'imu_bridge.yaml')
        study = deepcopy(validation.old_contract['comparable_trials'])
        study['world'] = physics['world']; study['assets'].update(plan['assets']); study['assets'].update(physics['assets'])
    else:
        study = read(ROOT/'rl_runs/flat_focused_optuna_v1/trial_plan.json')['trials']
        processes = Processes(env,pi_integrator_profile='conditional_v1')
    def evaluate(label, scale=1., reactive=False):
        directory = output/label
        cached = complete_evaluation(directory,len(plan['seeds']))
        if cached is None:
            processes.close(); assert_isolated(domain,env['GZ_PARTITION']); verify(plan)
            status(output,'evaluating '+label,steps=0)
            if course=='rough':
                validation.check(output/'python'); processes.launch(study['world'],directory)
                validation.assert_inputs(study,live=True)
            else:
                processes.env.update(NINO_AUTHORITY_PROFILE=label,NINO_MATCH_SCALE=str(scale))
                processes.world = processes.start(['ros2','launch','nino_rl','training_sim.launch.py',
                    f'world:={study["world"]}','world_name:=combined_flat_section','headless:=true',
                    'pi_integrator_profile:=conditional_v1'],directory/'gazebo.log')
                processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
                assert_trial_inputs(study,live=True)
            processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py',
                '--config',output/'config.yaml','--timeout','60'],directory/'profile.log',timeout=65)
            command=['ros2','run','nino_rl','evaluate_baseline','--config',output/'config.yaml',
                '--seeds',*plan['seeds'],'--baseline-speed-scale',scale,'--control-trace','--output',directory]
            if course=='rough': command += ['--route','E1']
            if reactive: command += ['--reactive']
            processes.run(command,directory/'evaluate.log',timeout=900); processes.close()
            cached=complete_evaluation(directory,len(plan['seeds']))
        if cached is None or cached[1]['evaluation_seeds']!=plan['seeds']:
            raise ValueError('Incomplete/incompatible evaluation: '+label)
        return cached
    try:
        if course=='rough':
            batches={k:complete_evaluation(ROUGH/'evaluation'/v,5) for k,v in
                [('ppo','ppo'),('pi_full','pi_full'),('pi_ppo_matched','pi_matched')]}
            batches['reactive']=evaluate('reactive',reactive=True)
            scale=min(1.,metrics(batches['pi_full'][1])['time_seconds']/metrics(batches['reactive'][1])['time_seconds'])
            batches['pi_reactive_matched']=evaluate('matched',scale)
            result=analyze_rough(output,config,plan,{k:v[1] for k,v in batches.items()},batches)
        else:
            batches={k:evaluate(k) for k in ('full','schedule')}
            scale=min(1.,metrics(batches['full'][1])['time_seconds']/metrics(batches['schedule'][1])['time_seconds'])
            batches['matched']=evaluate('matched',scale)
            result=analyze_flat(output,plan,{k:v[1] for k,v in batches.items()},batches)
        status(output,'complete',passed=result.get('reference_passed',result.get('authority_passed')),
               comparison=str(output/'comparison.json'),next_step=result['next_step'])
        return result
    except BaseException as exc:
        status(output,'interrupted',error=str(exc)); raise
    finally:
        processes.close(); lock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course',choices=['rough','flat','both'],default='both')
    parser.add_argument('--run',action='store_true');args=parser.parse_args()
    os.chdir(ROOT)
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    courses=['rough','flat'] if args.course=='both' else [args.course]
    for course in courses:
        prepare(course)
        if args.run: run_course(course)
        else: print('Prepared',OUTPUT/course,flush=True)


if __name__=='__main__':
    main()
