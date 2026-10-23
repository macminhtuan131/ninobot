#!/usr/bin/env python3
"""Read-only alignment of saved interval IMU, contact and motor/joint traces."""
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'rl_runs/flat_corrected_repeat_v1'
OUTPUT = ROOT / 'docs/flat_peak_contacts_2026-10-12'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def link(name):
    value = name.split('::')[-2]
    if value == 'base_footprint':
        return 'laser' if 'laser_collision' in name else 'chassis'
    return value


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / 'src/nino_description/urdf/nino.urdf.xacro'
    model_hash = digest(model_path)
    model = ET.parse(model_path).getroot()
    ns = {'xacro': 'http://www.ros.org/wiki/xacro'}
    caster = model.find("xacro:macro[@name='caster']", ns)
    axle = caster.find("joint[@name='caster_${index}_wheel_joint']")
    damping = float(axle.find('dynamics').attrib['damping'])
    radius = float(model.find("xacro:property[@name='caster_radius']", ns).attrib['value'])
    inertia = float(caster.find("link[@name='caster_${index}_wheel_link']/inertial/inertia").attrib['izz'])
    groups = {}
    for repeat in (1, 2):
        for profile in ('full', 'schedule'):
            directory = SOURCE / f'repeat_{repeat}' / profile
            episode = next(directory.glob('*/episode-001'))
            paths = {key: path for key, path in (
                ('control', episode / 'control_trace.csv'), ('drive', episode / 'drive_trace.csv'),
                ('contacts', directory / 'contacts.csv'), ('joints', directory / 'joints.csv'))}
            hashes = {str(path): digest(path) for path in paths.values()}
            control, drive = rows(paths['control']), rows(paths['drive'])
            times = np.array([float(r['sim_time_s']) for r in control])
            positions = np.array([float(r['physical_x_m']) for r in control])
            speeds = np.array([float(r['physical_speed_m_s']) for r in control])
            quiet_joints, quiet_floor = {}, {}
            indices = []
            # Retain independent maxima in both cable regions, plus the largest
            # energy interval of the whole episode. Deduplicate by row index.
            for low, high in ((2.1, 2.8), (4.1, 4.8), (-np.inf, np.inf)):
                eligible = [i for i, r in enumerate(control) if low <= float(r['physical_x_m']) <= high]
                indices.extend(sorted(eligible, key=lambda i: float(control[i]['step_imu_energy']), reverse=True)[:3])
            indices = sorted(set(indices), key=lambda i: float(control[i]['step_imu_energy']), reverse=True)
            events = []
            for i in indices:
                row = control[i]; end = float(row['sim_time_s']); begin = end - float(row['step_dt_s'])
                events.append(dict(index=i, begin=begin, end=end, elapsed_s=float(row['elapsed_s']),
                    x_m=float(row['physical_x_m']), speed_scale=float(row['speed_scale']),
                    physical_speed_m_s=float(row['physical_speed_m_s']),
                    imu_peak_m_s2=float(row['step_imu_peak_m_s2']), imu_energy=float(row['step_imu_energy']),
                    imu_coverage_s=float(row['step_imu_coverage_s']), contact_rows=[], joint_rows=[]))
            with paths['contacts'].open() as stream:
                for r in csv.DictReader(stream):
                    stamp = float(r['sim_time_s'])
                    if times[0] <= stamp <= times[-1] and 1.0 < np.interp(stamp, times, positions) < 1.8:
                        if 'caster' in r['collision'] and 'wheel' in r['collision'] and 'floor' in r['other']:
                            quiet_floor.setdefault(link(r['collision']), []).append(float(r['force_z_n']))
                    if int(r['points']) <= 0:
                        continue
                    for event in events:
                        # Strict interval association; widened sensitivity checked separately.
                        if event['begin'] - .02 <= stamp <= event['end'] + .02:
                            event['contact_rows'].append(r)
            with paths['joints'].open() as stream:
                for r in csv.DictReader(stream):
                    stamp = float(r['sim_time_s'])
                    if times[0] <= stamp <= times[-1] and 1.0 < np.interp(stamp, times, positions) < 1.8:
                        if 'caster' in r['joint']:
                            quiet_joints.setdefault(r['joint'].split('::')[-1], []).append(
                                (float(r['velocity_rad_s']), float(np.interp(stamp, times, speeds)), float(r['position_rad'])))
                    for event in events:
                        if event['begin'] - .1 <= stamp <= event['end'] + .1:
                            event['joint_rows'].append(r)
            for event in events:
                contact_rows = event.pop('contact_rows'); joint_rows = event.pop('joint_rows')
                contacts = {}
                for r in contact_rows:
                    if not event['begin'] <= float(r['sim_time_s']) <= event['end']:
                        continue
                    key = link(r['collision']) + ' / ' + r['other']
                    contacts.setdefault(key, []).append(r)
                event['contacts'] = {}
                for key, values in contacts.items():
                    force = np.array([[float(r[k]) for k in ('force_x_n', 'force_y_n', 'force_z_n')] for r in values])
                    norms = np.linalg.norm(force, axis=1); peak = values[int(np.argmax(norms))]
                    event['contacts'][key] = dict(samples=len(values), duration_proxy_s=.001*len(values),
                        max_depth_mm=1000*max(float(r['max_depth_m']) for r in values),
                        peak_solver_force_n=float(norms.max()), peak_force_stamp_s=float(peak['sim_time_s']),
                        peak_force_xyz_n=[float(peak[k]) for k in ('force_x_n','force_y_n','force_z_n')],
                        summed_force_norm_dt_proxy_ns=float(norms.sum()*.001),
                        peak_pose_z_m=float(peak['z_m']))
                expanded_bracket = sorted({r['other'] for r in contact_rows if 'bracket' in link(r['collision'])})
                event['bracket_contacts_with_20ms_margin'] = expanded_bracket
                event['joints'] = {}
                for name in sorted({r['joint'] for r in joint_rows}):
                    values = [r for r in joint_rows if r['joint']==name]
                    v = np.array([float(r['velocity_rad_s']) for r in values])
                    p = np.array([float(r['position_rad']) for r in values])
                    event['joints'][name.split('::')[-1]] = dict(min_velocity_rad_s=float(v.min()),
                        max_velocity_rad_s=float(v.max()), mean_velocity_rad_s=float(v.mean()),
                        min_angle_rad=float(p.min()), max_angle_rad=float(p.max()))
                local = [r for r in drive if event['begin'] <= float(r['sim_time_s']) <= event['end']]
                if not local:
                    raise ValueError('Missing drive feedback at an impact')
                event['motor'] = dict(samples=len(local),
                    max_abs_applied_nm=max(abs(float(r[k])) for r in local for k in ('left_applied_nm','right_applied_nm')),
                    wheel_error_rmse_rad_s=float(np.sqrt(np.mean([(float(r[f'{side}_actual_rad_s'])-float(r[f'{side}_target_rad_s']))**2 for r in local for side in ('left','right')]))),
                    mean_executed_linear_m_s=float(np.mean([float(r['executed_linear_m_s']) for r in local])),
                    mean_executed_yaw_rad_s=float(np.mean([float(r['executed_yaw_rad_s']) for r in local])),
                    limited_fraction=float(np.mean([float(r[f'{side}_limited']) for r in local for side in ('left','right')])),
                    command_fresh=all(float(r['cmd_fresh'])==1 for r in local),
                    wheel_state_present=all(float(r['have_wheel_state'])==1 for r in local))
                event['motor_samples'] = local
            for path in paths.values():
                if digest(path) != hashes[str(path)]:
                    raise RuntimeError('Saved trace changed during analysis')
            quiet = {}
            for name, values in quiet_joints.items():
                if 'wheel' not in name:
                    continue
                data = np.array(values)
                actual, speed = float(data[:,0].mean()), float(data[:,1].mean())
                normal = float(np.mean(quiet_floor[name.replace('_joint','_link')]))
                swivel = np.array(quiet_joints[name.replace('wheel','swivel')])[:,2]
                quiet[name] = dict(actual_angular_speed_rad_s=actual,
                    nominal_rolling_angular_speed_rad_s=speed/radius, physical_speed_m_s=speed,
                    angular_speed_ratio=actual/(speed/radius), mean_contact_normal_force_n=normal,
                    max_abs_swivel_angle_rad=float(np.abs(swivel).max()),
                    configured_axle_damping_nm_s_per_rad=damping,
                    required_damping_torque_at_rolling_nm=damping*speed/radius,
                    equivalent_axle_drag_at_rolling_n=damping*speed/radius**2,
                    candidate_drag_at_rolling_n=.001*speed/radius**2)
            groups[f'{repeat}/{profile}'] = dict(input_hashes=hashes, events=events, clear_floor_caster_response=quiet)
    if digest(model_path) != model_hash:
        raise RuntimeError('Robot source changed during audit')
    result = dict(groups=groups, source=str(SOURCE), physics_step_s=.001, analysis_only=True,
        robot_model=dict(path=str(model_path),sha256=model_hash,caster_radius_m=radius,
            caster_axle_inertia_kg_m2=inertia,axle_damping_nm_s_per_rad=damping),
        selected_correction=dict(parameter='caster wheel axle damping',old=damping,candidate=.001,
            scope='Both passive caster wheel joints only; swivel damping stays unchanged',
            evidence='Repeatable under-rotation and excessive configured drag in clear-floor x=1.0–1.8 m',
            qualification='Single physical-model candidate, not a validated cure for all impact spikes; real axle drag must be measured',
            validation_required='Repeat the existing four cold-start comparisons before any flat PPO pilot'),
        source_files_preserved=True, limitations=[
            'IMU peaks are action-interval summaries, not individually timestamped raw IMU samples.',
            'A contact/IMU temporal association does not establish causation.',
            'Contact force values are solver outputs; sums times dt are diagnostic proxies, not calibrated impulses.',
            'Joint velocities are simulation states; no real caster measurement is available.',
            'Four episodes of one evaluation seed do not establish generalization.'])
    (OUTPUT / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    lines = ['# Saved flat impact/contact audit', '',
        'Saved four cold-start seed-65004 episodes; 1 ms physics, unchanged 100 ms control.', '',
        '| Repeat/profile | Elapsed s | Physical x m | Scale | IMU peak m/s² | IMU energy | Bracket during interval | Max solver force kN / link | Motor torque Nm | Wheel error rad/s |',
        '|---|---:|---:|---:|---:|---:|---|---|---:|---:|']
    for group, data in groups.items():
        for event in data['events']:
            c=event['contacts']; key=max(c, key=lambda k:c[k]['peak_solver_force_n']) if c else None
            bracket=any('bracket' in k for k in c)
            lines.append(f"| {group} | {event['elapsed_s']:.1f} | {event['x_m']:.3f} | {event['speed_scale']:.2f} | {event['imu_peak_m_s2']:.2f} | {event['imu_energy']:.2f} | {bracket} | {c[key]['peak_solver_force_n']/1000:.2f} / {key.split(' / ')[0] if key else 'unavailable'} | {event['motor']['max_abs_applied_nm']:.3f} | {event['motor']['wheel_error_rmse_rad_s']:.3f} |")
    lines += ['', '## Interpretation limits', '', *['- '+v for v in result['limitations']], '',
        '## Clear-floor caster response (x = 1.0–1.8 m)', '',
        '| Repeat/profile | Caster | Actual rad/s | Rolling reference rad/s | Ratio | Mean normal force N | Configured drag at rolling N | Candidate drag N |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for group,data in groups.items():
        for name,q in data['clear_floor_caster_response'].items():
            lines.append(f"| {group} | {name} | {q['actual_angular_speed_rad_s']:.2f} | {q['nominal_rolling_angular_speed_rad_s']:.2f} | {q['angular_speed_ratio']:.3f} | {q['mean_contact_normal_force_n']:.2f} | {q['equivalent_axle_drag_at_rolling_n']:.2f} | {q['candidate_drag_at_rolling_n']:.2f} |")
    lines += ['', 'Selected physical correction: test caster **wheel-axle** damping `0.01 → 0.001 N·m·s/rad` in an isolated candidate. '
        'Keep swivel damping, masses, geometry, cable layout, physics/control steps and scoring fixed. '
        'This is a candidate to correct demonstrated baseline drag, not an established explanation for every impact. '
        'The straight-line rolling reference uses body forward speed/radius; small swivel angles are recorded in analysis.json. '
        'No source model was changed and no new flat simulation was started.', '',
        'All contact/motor details and immutable source hashes: [analysis.json](analysis.json).', '']
    (OUTPUT / 'REPORT.md').write_text('\n'.join(lines))
    print('\n'.join(lines[:30]))


if __name__ == '__main__':
    main()
