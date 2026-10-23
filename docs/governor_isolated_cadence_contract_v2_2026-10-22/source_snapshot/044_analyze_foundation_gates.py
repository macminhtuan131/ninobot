#!/usr/bin/env python3
"""Summarize physical foundations and paired interventions without reward claims."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[3]


def load_rows(path):
    return list(csv.DictReader(path.open()))


def contact_window(directory):
    path=next((directory/'evaluation').glob('*/episode-001/control_trace.csv'))
    trace=load_rows(path)
    # A fixed terminal window avoids cherry-picking a moving crossing.
    end=float(trace[-1]['elapsed_s'])
    rows=[r for r in trace if float(r['elapsed_s'])>=end-14.9]
    low,high=float(rows[0]['sim_time_s']),float(rows[-1]['sim_time_s'])
    contacts=[r for r in load_rows(directory/'contacts.csv') if low<=float(r['sim_time_s'])<=high]
    groups={}
    for collision in sorted({r['collision'] for r in contacts}):
        all_rows=[r for r in contacts if r['collision']==collision]
        touching=[r for r in all_rows if int(r['points'])>0]
        groups[collision]=dict(samples=len(all_rows),contact_fraction=len(touching)/len(all_rows),
            mean_reported_z_force_n=float(np.mean([float(r['force_z_n']) for r in touching])) if touching else 0.)
    return dict(window_elapsed_s=[float(rows[0]['elapsed_s']),end],
        x_span_m=float(np.ptp([float(r['physical_x_m']) for r in rows])),
        y_span_m=float(np.ptp([float(r['physical_y_m']) for r in rows])),collisions=groups,
        force_caveat='Probe body-1 wrench Z; no calibrated support-load fraction claimed')


def crossing_rows(directory):
    summaries=list(directory.glob('*/summary.json'))
    if len(summaries)!=1:return None
    summary=json.loads(summaries[0].read_text())
    if not summary.get('complete') or summary['episodes']!=3:return None
    results=[]
    for row in load_rows(summaries[0].with_name('episodes.csv')):
        trace=load_rows(summaries[0].parent/f"episode-{int(row['episode']):03d}/control_trace.csv")
        selected=[r for r in trace if abs(float(r['physical_x_m'])-4.45)<=.35]
        if not selected:raise ValueError('No second-cable crossing')
        dt=np.diff([float(r['sim_time_s']) for r in trace],prepend=float(trace[0]['sim_time_s'])-.1)
        mask=np.array([abs(float(r['physical_x_m'])-4.45)<=.35 for r in trace])
        square=np.array([.5*(float(r['slip_left'])**2+float(r['slip_right'])**2) for r in trace])
        vibration=np.array([float(r['imu_square_integral']) for r in trace])
        results.append(dict(seed=int(row['seed']),success=row['success'].lower()=='true',
            time_s=float(row['time_seconds']),path_rmse_m=float(row['truth_path_rmse_m']),
            crossing_speed_m_s=float(np.mean([float(r['physical_speed_m_s']) for r in selected])),
            crossing_slip=float(np.sqrt(np.sum(square[mask]*dt[mask])/dt[mask].sum())),
            crossing_vibration_m_s2=float(np.sqrt(vibration[mask].sum()/dt[mask].sum())),
            mean_requested_scale=float(np.mean([float(r['speed_scale']) for r in selected]))))
    return dict(episodes=results,arrivals=sum(r['success'] for r in results),
        means={key:float(np.mean([r[key] for r in results])) for key in results[0] if key not in ('seed','success')})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'rl_runs/foundations_20261011')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/rl_foundations_2026-10-11')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    result=dict(old_n1_contact=contact_window(args.root/'rough_contact'),flat={},rough={},
        training_started=False,optuna_started=False,
        physical_robot_sensors=['horizontal_lidar','imu','wheel_encoders'])
    for profile in ('full','constant','anticipatory'):
        data=crossing_rows(args.root/'flat_authority_v1'/profile)
        if data:result['flat'][profile]=data
    rough=args.root/'rough_v5/screen_nominal'
    if (rough/'screen_result.json').exists():
        result['rough']['contact_screen']=json.loads((rough/'screen_result.json').read_text())
        result['rough']['terminal_contacts']=contact_window(rough)
    if (rough/'preview.jsonl').exists():
        rows=[json.loads(s) for s in (rough/'preview.jsonl').read_text().splitlines()]
        result['rough']['preview']=dict(samples=len(rows),valid_both_fraction=float(np.mean([r['preview'][-1] for r in rows])),
            valid_left_fraction=float(np.mean([r['preview'][2] for r in rows])),
            valid_right_fraction=float(np.mean([r['preview'][5] for r in rows])),
            invalid_mask_preserved=True,
            limitation='Single-plane fan coverage; nominal axle height cannot correct body heave. PI contact screen does not consume preview.')
    low=args.root/'rough_v6/screen_low_friction/screen_result.json'
    if low.exists():
        result['rough']['low_friction_screen']=json.loads(low.read_text())
        result['rough']['physics_response']=dict(zero_rl_residual=True,
            drive_mu_nominal=1.2,drive_mu_low=.6,nominal_evidence=str(rough/'screen_result.json'),
            low_friction_evidence=str(low),same_seed=13000,
            qualification='Two one-seed screens with identical terrain triangles and controller. Preliminary motion evidence only; mass variation and randomized training remain unvalidated.')
    hardware=args.root/'hardware_sensors_v2'
    result['hardware_sensor_preflight']=dict(started=(hardware/'sensor_contract.json').exists())
    for name in ('sensor_integrity','screen_results'):
        if (hardware/(name+'.json')).exists():
            result['hardware_sensor_preflight'][name]=json.loads((hardware/(name+'.json')).read_text())
    result['hardware_sensor_preflight']['wall_coverage']={}
    for route in ('E1','N1','S1'):
        logs=hardware/'pi'/route/'wall_observations.jsonl'
        traces=list((hardware/'pi'/route).glob('*/episode-001/control_trace.csv'))
        summaries=list((hardware/'pi'/route).glob('*/summary.json'))
        if not logs.exists() or len(traces)!=1 or len(summaries)!=1:continue
        if not json.loads(summaries[0].read_text()).get('complete'):continue
        trace=load_rows(traces[0]);lo=float(trace[0]['sim_time_s'])-.1;hi=float(trace[-1]['sim_time_s'])
        rows=[json.loads(s) for s in logs.read_text().splitlines()]
        rows=[r for r in rows if lo<=r['stamp']<=hi]
        fixes=[r['stamp'] for r in rows if r['fix'] is not None]
        result['hardware_sensor_preflight']['wall_coverage'][route]=dict(
            observations=len(rows),two_axis_fix_fraction=len(fixes)/len(rows),
            maximum_interval_between_wall_candidates_s=float(np.max(np.diff(fixes))) if len(fixes)>1 else None,
            sensors=sorted({r['sensor'] for r in rows}),
            limitation='Candidates before bounded correction acceptance; controller freshness and physical scoring remain independent checks')
    result['gate']=dict(foundation_ready=False,pilot_allowed=False,optuna_allowed=False,
        reason='Qualify horizontal-only localization, feasible terrain/routes and physical train/holdout profiles; freeze the deployable learning task before a pilot')
    if len(result['flat'])==3:
        base=result['flat']['full']
        result['authority_screen']=dict(
            speed_responds=result['flat']['anticipatory']['means']['crossing_speed_m_s']<.9*base['means']['crossing_speed_m_s'],
            arrivals_preserved=result['flat']['anticipatory']['arrivals']==3,
            crossing_slip_ratio=result['flat']['anticipatory']['means']['crossing_slip']/base['means']['crossing_slip'],
            crossing_vibration_ratio=result['flat']['anticipatory']['means']['crossing_vibration_m_s2']/base['means']['crossing_vibration_m_s2'],
            limitation='Three paired reset seeds on fixed two-cable course; scripted intervention, not learned improvement or training-seed robustness')
    (args.output/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# RL foundation checks — 2026-10-11','',
        'No PPO updates or Optuna trials. Historical maps, packages, checkpoints and studies were preserved.', '',
        'This report records the initial foundation experiments. For the subsequent confirmation and '
        'fresh PPO pilot, see [the follow-up workflow](../ROUGH_HARDWARE_PILOT_2026-10-11.md). '
        'Its live runner reports distinguish ongoing confirmation, training and completed evaluation.', '',
        '## Rough physical failure', '',
        'The unchanged rejected N1 maneuver was recaptured with a diagnostic contact plugin. '
        'It failed with recovery exhausted. During the final 14.9 seconds the chassis, '
        'right caster and left wheel contacted the terrain; the right drive wheel did not. '
        'Physical pose span was below one micrometre. This is strong evidence of a chassis-supported hang-up, '
        'rather than a reward or arrival-estimation problem. One reproduction does not qualify every route.', '',
        '## Hardware constraint', '',
        'The user confirmed horizontal LiDAR, IMU and wheel encoders only. The simulated downward '
        'fan and 33-channel wall sensor are unavailable on the physical robot. Downward preview is '
        'diagnostic only. Earlier 3D-wall-assisted PI results do not qualify the hardware estimator.', '',
        'A separate hardware-sensor preflight removes both virtual sensors from the spawned URDF, '
        'uses the existing IMU-compensated horizontal wall fit, and excludes all four preview values '
        'from the actor (56/frame, 280 with five frames). It preserves physical links/masses, PI settings, '
        'terrain and strict arrival scoring. The known corridor wall geometry is still a localization '
        'prior: this is not arbitrary-map localization or a deployment-ready result. Learning is '
        'disabled in this preflight snapshot.', '',
        'IMU and encoder history can support reactive ride adjustment after contact. Horizontal LiDAR '
        'may observe obstacles intersecting its scan plane, but does not reliably measure an unseen '
        'pothole ahead. The earlier known-location anticipatory intervention is a control-authority '
        'reference, not evidence that these sensors provide terrain preview.', '',
        '## Isolated diagnostic correction', '',
        '- Candidate terrain: same XY features/topology, 50% elevation relief; one STL for collision and visual. '
        'Height range −0.0820…+0.1219 m; maximum triangle grade 0.2944. Original map unchanged.',
        '- Preview uses evaluated URDF extrinsics (.33,0,.20 m), axle height .0625 m, timestamp-matched '
        'IMU roll/pitch and proper 3D ray rotation. The original .2325 m sensor height was inconsistent with '
        'the .2625 m nominal floor-relative transform.',
        '- Diagnostic preview overlay: separate left/right distance, height and validity, '
        '63 values/frame and 315 with five frames. This overlay is not the hardware actor. '
        'Neither its 315-value nor the hardware preflight 280-value contract accepts a 300-value checkpoint resume.',
        '- Missing returns stay invalid. Reset history is refreshed after epoch clearing, with motors stopped; '
        'actual paused time defines time zero. Per-action timing checks remain intact.',
        '- Real nominal/low-friction/heavy URDF/SDF profiles are prepared (wheel mu 1.2/0.6, mass/inertia '
        '×1.0/1.15). Converted SDF friction was checked. Randomized training and the mass profile are not yet qualified.',
        '- The [Gazebo DART importer](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc#L859) '
        'reads the SDF ODE friction coefficients into DART contact dynamics; these profiles do not scale policy torque.', '',
        '## Rough mechanical screening', '',
        '| Profile | Arrivals | Completion s | Physical RMSE m | Slip | RMS vertical acceleration m/s² |',
        '|---|---:|---:|---:|---:|---:|']
    for profile,key in [('nominal','contact_screen'),('low friction','low_friction_screen')]:
        if key not in result['rough']:continue
        s=result['rough'][key]['summary'];m=s['metrics_all_episodes']
        lines.append(f"| {profile} | {round(s['success_rate'])}/1 | "+' | '.join(
            f"{m[k]['mean']:.4f}" for k in ('time_seconds','truth_path_rmse_m','rms_wheel_slip','rms_vertical_acceleration_m_s2'))+' |')
    lines += ['', 'Both screens use seed 13000 with zero RL residual. One trial per profile cannot establish '
        'a repeatable friction effect or qualify E1/S1. The nominal final window has no chassis contact. '
        'These are PI results on changed geometry, not improved PPO results.', '',
        '## Longitudinal authority', '',
        'The same three reset seeds compare full PI, constant 0.70 scale, and an anticipatory 0.60 scale '
        'near cables with a 0.4 scale/s reference ramp. The intervention uses estimated pose and known '
        'cable locations, zero RL torque/yaw, unchanged PI and independent physical scoring. '
        'It tests control authority; it is not a deployment policy.', '',
        '| Intervention | Arrivals | Completion s | Physical RMSE m | Second-cable speed m/s | Slip | Vibration m/s² |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for profile,data in result['flat'].items():
        m=data['means']
        lines.append(f"| {profile} | {data['arrivals']}/3 | {m['time_s']:.3f} | {m['path_rmse_m']:.4f} | "
            f"{m['crossing_speed_m_s']:.3f} | {m['crossing_slip']:.3f} | {m['crossing_vibration_m_s2']:.3f} |")
    lines+=['','## Hardware-only PI screening','']
    screen=result['hardware_sensor_preflight'].get('screen_results',{})
    if screen.get('routes'):
        lines+=['| Route | Physical arrivals | Physical RMSE m | Mean pose disagreement m | Screen gate |',
            '|---|---:|---:|---:|---:|']
        for route,data in screen['routes'].items():
            g=data['gate']
            lines.append(f"| {route} | {g['physical_arrival_rate']:.0%} | {g['truth_path_rmse_m']:.4f} | "
                f"{g['max_episode_mean_pose_disagreement_m']:.4f} | {g['passed']} |")
        lines+=['','One reset seed (13000) per completed route. Passing a screen does not establish robustness.']
    else:
        lines+=['No completed hardware-only route batch yet. Inspect `hardware_sensors_v2/pi/*/evaluate.log` for live progress.']
    if result['hardware_sensor_preflight'].get('sensor_integrity'):
        lines+=['','Actor-isolation checks passed: injected preview and truth velocity have no effect; '
            'the actor does not call the preview API, the estimator does not use a point cloud, '
            'and the spawned robot contains only horizontal LiDAR and IMU sensor types.']
    lines+=['','The [next pilot plan](NEXT_PILOT.md) records the hardware-specific learning task and remaining qualification steps.']
    lines+=['','## Remaining gates','',
        '1. Qualify a mechanically feasible route/terrain combination, including N1 and unchanged route scoring.',
        '2. Validate horizontal-only localization and sensor history. Preserve invalid/stale-data handling; '
        'IMU tilt compensation cannot create missing wall returns. Keep virtual preview outside the deployable actor and estimator.',
        '3. Confirm response to physical friction/mass variants at zero RL residual; declare fixed train/holdout distributions.',
        '4. Freeze a narrow speed/acceleration task using hardware sensor history, independent PI steering and reward, then one short learning pilot. '
        'Use fresh weights for changed inputs, or an explicitly audited input remapping with fresh critic/optimizer.',
        '5. Once useful behavior is learned, create new focused studies with fixed physical evaluation and '
        'matching PI references. Keep independent training seeds and unseen terrain/dynamics for validation.', '',
        'Read `analysis.json` for completed/pending measurements. Infrastructure or sensor interruptions '
        'are not counted as unsuccessful Optuna parameter trials. No automatic long training or tuning.', '']
    lines += ['## Commands', '', 'Run from the workspace, after sourcing ROS and the virtual environment:', '',
        '```bash', 'cd ~/ninorobot', 'source /opt/ros/jazzy/setup.bash', 'source .venv/bin/activate',
        'source install/setup.bash',
        '# Prepare/recheck the isolated contract (does not start training)',
        'python src/nino_rl/scripts/prepare_rough_foundations.py',
        '# Reuse the complete low-friction mechanical screen',
        'python src/nino_rl/scripts/prepare_rough_foundations.py --screen --profile low_friction',
        '# Capture nominal PI on the same current contract if further screening is needed',
        'python src/nino_rl/scripts/prepare_rough_foundations.py --screen --profile nominal',
        '# Reuse all three completed flat interventions',
        'python src/nino_rl/scripts/run_crossing_authority.py --run',
        '# Hardware-only PI preflight; removes virtual lidars and does not train',
        'python src/nino_rl/scripts/run_hardware_sensor_preflight.py --run',
        'python src/nino_rl/scripts/verify_hardware_sensor_preflight.py',
        'python src/nino_rl/scripts/analyze_foundation_gates.py', '```', '',
        'Rough and flat runners own their simulator/bridge processes on domains 78 and 79, respectively. '
        'Do not launch a second simulator in those partitions. No rebuild is required for these isolated snapshots. '
        'Changed inputs require a new output directory; old studies are never resumed with this contract.', '']
    (args.output/'REPORT.md').write_text('\n'.join(lines))
    print(args.output/'REPORT.md')


if __name__=='__main__':main()
