#!/usr/bin/env python3
"""Cold-start single-obstacle PI screen; explicit --run required to launch."""
import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import re
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src/nino_rl'), str(Path(__file__).parent)]
from nino_rl.flat_reactive_research import lookup_scenario
from prepare_flat_reactive_research import OUTPUT, prepare
from prepare_rough_foundations import digest, immutable
from train_rough_curriculum import Processes, assert_isolated, complete_evaluation
from run_disturbance_reference_comparisons import verify
from recover_flat_contact_report import safe_window
from run_flat_bullet_contact_candidate_v3 import LIBRARY, RESET_LIBRARY


def screen_plan(bundle, physics, output, bundle_path=OUTPUT):
    spec = yaml.safe_load(Path(bundle['config']).read_text())['flat_research']
    bank = json.loads(Path(bundle['bank']).read_text())
    cases = [lookup_scenario(bank, f'A_train_{i:03d}') for i in spec['screen']['train_scenario_indices']]
    if any(r['split'] != 'train' or len(r['obstacles']) != 1 for r in cases):
        raise ValueError('Mechanism screen requires training single-obstacle cases')
    rows = []
    for repeat in range(1, spec['screen']['repetitions']+1):
        order = spec['screen']['profiles'][::1 if repeat % 2 else -1]
        for case in cases:
            for profile in order:
                rows.append(dict(repeat=repeat, profile=profile, scenario=case,
                    output=str(output/f'repeat_{repeat}'/case['id']/profile)))
    return dict(revision=bundle['revision'], physical_profile=physics,
        assets={str(Path(__file__)):digest(Path(__file__)),
                str(bundle_path/'contract.json'):digest(bundle_path/'contract.json')},
        config=bundle['config'], world=bundle['world'], bank=bundle['bank'],
        launch=bundle['profiles'][physics]['launch'], rows=rows,
        qualification='Development PI mechanism/physics screen; no time-matched claim, PPO promotion or Optuna release',
        reserved_test_used=False, training_started=False, optuna_held=True)


def analyze(plan, output):
    results = []
    for case in plan['rows']:
        batch = complete_evaluation(Path(case['output']), 1)
        if batch is None:
            raise ValueError('Incomplete episode: '+case['output'])
        episode = batch[0][0]
        run = next(p.parent for p in Path(case['output']).glob('*/summary.json')
                   if json.loads(p.read_text()).get('complete'))
        with (run/'episode-001/control_trace.csv').open() as stream:
            trace = list(csv.DictReader(stream))
        x = case['scenario']['obstacles'][0]['x_m']
        # Independent physical-position window for analysis ONLY; never input
        # to the controller. Contact traces establish which component touched.
        window = safe_window(trace, [[x-.4, x+.5]])
        results.append(dict(repeat=case['repeat'], profile=case['profile'],
            scenario_id=case['scenario']['id'], episode=episode, crossing=window,
            disturbed_frames=sum(str(r['research_disturbed']).lower() in ('1','true') for r in trace),
            holding_frames=sum(r['research_phase']=='holding' for r in trace),
            recovering_frames=sum(r['research_phase']=='recovering' for r in trace),
            physical_arrival=(str(episode['success']).lower() in ('1','true') and
                              float(episode['truth_endpoint_error_m']) <= .20+1e-6)))
    table = {}
    for profile in ('full','reactive'):
        rs = [r for r in results if r['profile']==profile]
        keys = ('time_seconds','truth_path_rmse_m','rms_vertical_acceleration_m_s2','rms_wheel_slip')
        table[profile] = dict(episodes=len(rs), arrivals=sum(r['physical_arrival'] for r in rs),
            means={k:float(np.mean([float(r['episode'][k]) for r in rs])) for k in keys})
    paired = []
    for full in (r for r in results if r['profile']=='full'):
        reactive = next(r for r in results if r['profile']=='reactive' and
                        (r['repeat'],r['scenario_id'])==(full['repeat'],full['scenario_id']))
        covered = all(r['crossing']['available'] for r in (full, reactive))
        ratios = {k: (reactive['crossing'][k]/full['crossing'][k]
                      if covered and full['crossing'][k] > 0 else None)
                  for k in ('vibration_energy_per_m','slip_energy_per_m')}
        paired.append(dict(repeat=full['repeat'], scenario_id=full['scenario_id'],
            physical_arrivals=full['physical_arrival'] and reactive['physical_arrival'],
            crossing_available=covered, crossing_ratios=ratios))
    data = dict(complete=True, results=results, table=table, paired=paired,
                qualification=plan['qualification'], time_matched_PI_complete=False,
                failed_arrivals_retained=True, missing_crossing='Unavailable/null, never zero or excluded',
                PPO_released=False, optuna_held=True)
    (output/'analysis.json').write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    lines = ['# Flat sensor-only mechanism screen', '', plan['qualification'], '',
             '| Controller | Arrivals | Mean time s | Physical RMSE m | Vibration RMS | Slip RMS |',
             '|---|---:|---:|---:|---:|---:|']
    for name, value in table.items():
        m = value['means']
        lines.append(f"| {name} | {value['arrivals']}/{value['episodes']} | {m['time_seconds']:.2f} | "
                     f"{m['truth_path_rmse_m']:.5f} | {m['rms_vertical_acceleration_m_s2']:.3f} | {m['rms_wheel_slip']:.4f} |")
    lines += ['', 'Inspect crossing ratios, contact/reset/drive traces and repeated-case variation before '
              'choosing a correction. Time-matched PI and broader validation are still required.', '']
    (output/'REPORT.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physics', choices=['original','caster_damping_candidate'], default='original')
    parser.add_argument('--bundle', type=Path, default=OUTPUT,
                        help='Prepared bundle path; use a new path for a changed contract')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    bundle_path = args.bundle.resolve()
    bundle = prepare(bundle_path)
    output = bundle_path/'screens'/args.physics
    plan = screen_plan(bundle, args.physics, output, bundle_path)
    immutable(output/'plan.json', json.dumps(plan, indent=2)+'\n')
    print(f"Prepared {len(plan['rows'])} cold episodes for {args.physics}; --run launches them.")
    if not args.run:
        return
    for p in (LIBRARY, RESET_LIBRARY):
        if not p.is_file(): raise ValueError('Build required instrumentation: '+str(p))
    probe_assets = {str(p):digest(p) for p in (LIBRARY, RESET_LIBRARY)}
    immutable(output/'probe_assets.json', json.dumps(probe_assets, indent=2)+'\n')
    lock = (output/'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    env = os.environ.copy()
    # Clear inherited coordinate-profile variables from legacy terminals.
    env.pop('NINO_AUTHORITY_PROFILE', None)
    env.pop('NINO_MATCH_SCALE', None)
    env.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST', PYTHONUNBUFFERED='1',
               NINO_FLAT_SCENARIO_BANK=plan['bank'])
    env['PYTHONPATH'] = bundle['python_overlay']+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','')
    processes = Processes(env, pi_integrator_profile='conditional_v1')
    try:
        for row in plan['rows']:
            directory = Path(row['output'])
            if complete_evaluation(directory, 1) is not None: continue
            verify(bundle); verify(plan)
            if any(digest(Path(p)) != h for p,h in probe_assets.items()):
                raise ValueError('Instrumentation changed')
            assert_isolated(79,'nino_flat_79')
            processes.env.update(NINO_FLAT_SCENARIO_ID=row['scenario']['id'],
                                 NINO_FLAT_RESEARCH_PROFILE=row['profile'])
            processes.world = processes.start(['ros2','launch',plan['launch'], 'world:='+plan['world'],
                'world_name:=combined_flat_section','headless:=true',
                'pi_integrator_profile:=conditional_v1','verbosity:=3'], directory/'gazebo.log')
            processes.run(['ros2','run','nino_rl','wait_for_sim'], directory/'readiness.log', timeout=90)
            processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py',
                           '--config',plan['config'],'--timeout','60'], directory/'profile.log', timeout=65)
            log = re.sub(r'\x1b\[[0-9;]*m','',(directory/'gazebo.log').read_text())
            if 'Using [bullet] collision detector' not in log:
                raise ValueError('Runtime Bullet acknowledgement missing')
            for name, library, filename in [('NinoFlatContactProbe',LIBRARY,'contacts.csv'),
                                             ('NinoFlatResetProbe',RESET_LIBRARY,'joints.csv')]:
                payload = ('entity {name: "combined_flat_section" type: WORLD} plugins {name: '+
                    json.dumps(name)+' filename: '+json.dumps(str(library))+' innerxml: '+
                    json.dumps(f'<output>{directory/filename}</output>')+'}')
                probe_log = directory/(name+'.log')
                processes.run(['gz','service','-s','/world/combined_flat_section/entity/system/add',
                    '--reqtype','gz.msgs.EntityPlugin_V','--reptype','gz.msgs.Boolean','--timeout','5000',
                    '--req',payload], probe_log, timeout=10)
                if 'data: true' not in probe_log.read_text(): raise ValueError('Probe not acknowledged')
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',plan['config'],
                          '--seeds',row['scenario']['scenario_seed'],'--baseline-speed-scale','1',
                          '--control-trace','--output',directory], directory/'evaluate.log', timeout=900)
            processes.close()
            if complete_evaluation(directory, 1) is None: raise ValueError('Incomplete measured episode')
        analyze(plan, output)
        print('Screen complete; evidence saved. PPO and Optuna remain unreleased.')
    finally:
        processes.close()
        lock.close()


if __name__ == '__main__':
    main()
