"""Whole-session real velocity identification and matched-reference Sim inputs.

Final ROS Twist is a reference, not actuator target telemetry. Receipt-clock
response includes communication, command shaping and unmeasured motor dynamics.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from . import residual_sysid


HELD_OUT = ('20261117_122526_OwllD9', '20261117_122752_FYBrKr')
GEOMETRY = dict(radius_l=.06, radius_r=.06, separation=.345)
MAX_AGE_S = .15


def aligned_session(session):
    commands = np.asarray(session['commands'], dtype=float)
    motor = session['motor']
    if (session['integrity'] != 'ok'
            or session['source_sha256'] != session['source_sha256_after']):
        raise ValueError('Source integrity or immutable extraction failed')
    if len(commands) < 2 or len(motor) < 20:
        raise ValueError('Insufficient source support')
    names = ('left_wheel', 'right_wheel')
    wheel = []
    for row in motor:
        if len(row[2]) != len(row[4]) or len(set(row[2])) != len(row[2]):
            raise ValueError('Ambiguous raw wheel mapping')
        values = dict(zip(row[2], row[4]))
        wheel.append([row[0], row[1], *(values[n] for n in names)])
    wheel = np.asarray(wheel, dtype=float)
    if not np.isfinite(commands).all() or not np.isfinite(wheel).all():
        raise ValueError('Nonfinite raw sample')
    for stamps in (commands[:, 0], wheel[:, 0], wheel[:, 1]):
        if np.any(np.diff(stamps) <= 0):
            raise ValueError('Nonmonotonic or duplicate source/receipt timestamp')
    index = np.searchsorted(commands[:, 0], wheel[:, 0], side='right')-1
    age = (wheel[:, 0]-commands[np.maximum(index, 0), 0])/1e9
    supported = (index >= 0) & (age <= MAX_AGE_S)
    selected = np.flatnonzero(supported)
    if len(selected) < 20:
        raise ValueError('No supported command-to-wheel window')
    origin = wheel[selected[0], 0]
    rows = np.column_stack(((wheel[selected, 0]-origin)/1e9,
                            commands[index[selected], 1:3], wheel[selected, 2:4]))
    internal_missing = int(np.sum(~supported[selected[0]:selected[-1]+1]))
    qc = dict(raw_wheel_samples=len(motor), aligned_samples=len(rows),
              unsupported_boundary_samples=int(np.sum(~supported))-internal_missing,
              unsupported_internal_samples=internal_missing,
              maximum_aligned_gap_s=float(np.max(np.diff(rows[:, 0]))),
              maximum_wheel_source_gap_s=float(np.max(np.diff(wheel[:, 1]))/1e9),
              maximum_wheel_receipt_gap_s=float(np.max(np.diff(wheel[:, 0]))/1e9),
              maximum_command_receipt_gap_s=float(np.max(np.diff(commands[:, 0]))/1e9),
              interpolation=False, source_clock_used_for_alignment=False,
              absolute_receipt_origin_ns=int(origin))
    qc['eligible'] = internal_missing == 0 and qc['maximum_aligned_gap_s'] <= MAX_AGE_S
    qc['reason'] = None if qc['eligible'] else 'Missing internal command support; retain whole run as diagnostic'
    return rows, qc


def prepare(export_path, output):
    export_path, output = Path(export_path), Path(output)
    export = json.loads(export_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    groups, quality = {}, {}
    provenance = []
    for session in export['sessions']:
        name = session['session_id']
        if name in quality:
            raise ValueError('Duplicate whole session')
        rows, qc = aligned_session(session)
        quality[name] = qc
        provenance.append({key: session[key] for key in ('session_id', 'source', 'source_sha256')})
        if qc['eligible']:
            groups[name] = rows
    if not set(HELD_OUT) <= groups.keys():
        raise ValueError('Predeclared holdout lacks source support; no replacement selected')
    metadata = dict(units=dict(time_s='s', final_v_m_s='m/s', final_yaw_rad_s='rad/s',
                               wheel_l_rad_s='rad/s', wheel_r_rad_s='rad/s'),
                    time_basis='common_receipt_clock',
                    alignment_note='Causal as-of final ROS reference at raw wheel receipt time. '
                                   'No future samples or interpolation. Twist has no execution stamp. '
                                   'Combined delay is not actuator or body latency.',
                    provenance=provenance,
                    conditions_note='17 November Nav2 velocity sessions. Operator floor/load/caster '
                                    'annotations incomplete. Encoder and localization are not body GT.',
                    nominal_geometry=GEOMETRY, held_out_sessions=list(HELD_OUT),
                    maximum_command_age_s=MAX_AGE_S,
                    input_export_sha256=hashlib.sha256(export_path.read_bytes()).hexdigest(),
                    quality=quality, selection='Chronological first four fit, last two holdout. '
                                               'Whole source-invalid runs excluded before fitting.')
    with (output/'source.csv').open('w', newline='') as f:
        writer = csv.writer(f); writer.writerow(residual_sysid.COLUMNS)
        for name, rows in groups.items():
            writer.writerows((name, *row) for row in rows)
    (output/'source_metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    data, metadata = residual_sysid.read_dataset(output/'source.csv', output/'source_metadata.json')
    fit = residual_sysid.fit(data, metadata)
    for model, wheel in zip(fit['models'], (0, 1)):
        for metric in model['held_out']:
            rows = data[metric['session_id']]
            sign = -1 if wheel == 0 else 1
            nominal = (rows[:, 1]+sign*GEOMETRY['separation']*rows[:, 2]/2)/GEOMETRY['radius_l']
            mask = rows[:, 0]-rows[0, 0] >= 1.
            metric['nominal_reference_rmse_rad_s'] = float(np.sqrt(np.mean(
                (nominal[mask]-rows[mask, 3+wheel])**2)))
            metric['fraction_of_nominal_rmse'] = metric['rmse_rad_s']/max(
                metric['nominal_reference_rmse_rad_s'], 1e-12)
    fit['automatic_sim_parameter_promotion'] = False
    fit['quality'] = quality
    (output/'sysid_result.json').write_text(json.dumps(fit, indent=2)+'\n')
    # This schedule is an evaluation input. It never enters a TD3 replay buffer.
    name = HELD_OUT[0]
    rows = data[name]
    session = next(s for s in export['sessions'] if s['session_id'] == name)
    origin = quality[name]['absolute_receipt_origin_ns']
    commands = np.asarray(session['commands'], dtype=float)
    command_times = (commands[:, 0]-origin)/1e9
    times = np.arange(0., min(35., rows[-1, 0])-.1, .1)
    indices = np.searchsorted(rows[:, 0], times+.1, side='right')-1
    command_indices = np.searchsorted(command_times, times, side='right')-1
    if (np.any(command_indices < 0) or np.any(indices < 0)
            or np.any(times-command_times[command_indices] > MAX_AGE_S)
            or np.any(times+.1-rows[indices, 0] > MAX_AGE_S)):
        raise ValueError('Matched replay lacks causal source support')
    schedule = dict(schema_version=1, purpose='matched_real_reference_gazebo_diagnostic',
                    session_id=name, interval_s=.1, geometry_status='nominal_not_effective',
                    real_geometry=GEOMETRY, source_export_sha256=metadata['input_export_sha256'],
                    rows=[dict(time_s=float(t), v_m_s=float(commands[j, 1]), yaw_rad_s=float(commands[j, 2]),
                               comparison_time_s=float(t+.1),
                               reported_wheel_rad_s=list(rows[i, 3:5]),
                               real_feedback_age_s=float(t+.1-rows[i, 0]))
                          for t, i, j in zip(times, indices, command_indices)],
                    physical_calibration_accepted=False, td3_replay_eligible=False)
    (output/'sim_replay.json').write_text(json.dumps(schedule, indent=2)+'\n')
    return fit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.export, args.output)
    print(json.dumps(dict(fit_sessions=result['fit_sessions'], held_out=result['held_out_sessions'],
                          models=result['models']), indent=2))


if __name__ == '__main__':
    main()
