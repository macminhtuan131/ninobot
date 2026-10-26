#!/usr/bin/env python3
"""Read-only phase/motor/actor audit of the completed revision-56 pilot."""
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'rl_runs/rough_rate_bc_pilot_v2'
OUTPUT = ROOT / 'docs/rough_bc_slip_audit_2026-10-12'
sys.path[:0] = [str(SOURCE / 'python'), str(Path(__file__).parent), str(ROOT / 'src/nino_rl')]
from prepare_rough_foundations import digest, immutable
from rough_rate_behavior_cloning_v2 import teacher


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def mode(row, previous):
    scale = float(row['speed_scale'])
    delta = scale - previous
    if float(row['elapsed_s']) <= 1.:
        return 'startup'
    if float(row['physical_goal_distance_m']) < .5:
        return 'approach'
    if delta < -.005:
        return 'braking'
    if delta > .005:
        return 'recovery'
    return 'holding' if scale < .98 else 'cruise'


def phase_audit(controller):
    episodes = []
    totals = {}
    for file in sorted((SOURCE / 'evaluation' / controller).glob('*/episode-*/control_trace.csv')):
        control = rows(file)
        drive = rows(file.with_name('drive_trace.csv'))
        stamps = np.array([float(r['sim_time_s']) for r in control])
        labels = []
        last = 1.
        for row in control:
            labels.append(mode(row, last))
            last = float(row['speed_scale'])
        values = {}
        def group(label):
            return values.setdefault(label, dict(seconds=0., slip_integral=0., imu_energy=0., imu_coverage_s=0.,
                frames=0, drive_samples=0, wheel_error_squared=0., executed_speed_sum=0.,
                torque_squared=0., maximum_abs_torque_nm=0., limited_wheels=0, stale_samples=0))
        for row, label in zip(control, labels):
            item = group(label)
            dt = float(row['step_dt_s'])
            item['seconds'] += dt
            item['slip_integral'] += float(row['step_slip_square']) * dt
            item['imu_energy'] += float(row['step_imu_energy'])
            item['imu_coverage_s'] += float(row['step_imu_coverage_s'])
            item['frames'] += 1
        for row in drive:
            stamp = float(row['sim_time_s'])
            i = int(np.searchsorted(stamps, stamp, side='left'))
            if i >= len(control) or stamp <= stamps[i] - float(control[i]['step_dt_s']) - 1e-8:
                continue
            item = group(labels[i])
            item['drive_samples'] += 1
            item['executed_speed_sum'] += float(row['executed_linear_m_s'])
            item['stale_samples'] += int(any(float(row[k]) < .5 for k in ('cmd_fresh', 'policy_fresh', 'have_wheel_state')))
            for side in ('left', 'right'):
                error = float(row[side + '_actual_rad_s']) - float(row[side + '_target_rad_s'])
                torque = float(row[side + '_applied_nm'])
                item['wheel_error_squared'] += error * error
                item['torque_squared'] += torque * torque
                item['maximum_abs_torque_nm'] = max(item['maximum_abs_torque_nm'], abs(torque))
                item['limited_wheels'] += int(float(row[side + '_limited']) > .5)
        scales = np.array([float(r['speed_scale']) for r in control])
        changes = np.diff(np.r_[1., scales])
        signs = np.sign(changes[np.abs(changes) > .005])
        reversals = int(np.sum(signs[1:] != signs[:-1]))
        within_phase_reversals = 0
        prior = None
        for r, change in zip(control, changes):
            if abs(change) <= .005:
                continue
            key = (r['cue_phase'], int(r['cue_events']))
            sign = int(np.sign(change))
            if prior is not None and prior[0] == key and prior[1] != sign:
                within_phase_reversals += 1
            prior = (key, sign)
        episodes.append(dict(seed=int(control[0]['seed']), phases=values,
            reversals_including_normal_event_cycles=reversals,
            within_same_phase_event_reversals=within_phase_reversals,
            recovery_during_holding=int(sum(change > .005 and r['cue_phase'] == 'holding' for r, change in zip(control, changes))),
            brake_during_recovery=int(sum(change < -.005 and r['cue_phase'] == 'recovering' for r, change in zip(control, changes)))))
        for label, item in values.items():
            destination = totals.setdefault(label, {k: 0 for k in item})
            for k, v in item.items():
                if k == 'maximum_abs_torque_nm':
                    destination[k] = max(destination[k], v)
                else:
                    destination[k] += v
    for item in totals.values():
        item['slip_rms'] = float(np.sqrt(item['slip_integral'] / item['seconds']))
        item['vibration_rms'] = float(np.sqrt(item['imu_energy'] / item['imu_coverage_s']))
        n = item['drive_samples']
        item['wheel_tracking_rmse_rad_s'] = float(np.sqrt(item['wheel_error_squared'] / (2*n))) if n else None
        item['mean_executed_speed_m_s'] = item['executed_speed_sum'] / n if n else None
        item['wheel_torque_rms_nm'] = float(np.sqrt(item['torque_squared'] / (2*n))) if n else None
        item['wheel_limit_fraction'] = item['limited_wheels'] / (2*n) if n else None
    return dict(episodes=episodes, phases=totals)


def actor_audit():
    chunks = [np.load(p) for p in sorted((SOURCE / 'evaluation/ppo/actor_capture').glob('*.npz'))]
    observations = np.concatenate([d['observations'] for d in chunks])
    records = [json.loads(str(r)) for d in chunks for r in d['records']]
    phase = np.array([r['cue']['cue_phase'] for r in records])
    labels = np.array([teacher(o) for o in observations])
    actual = np.array([r['rate_action'] for r in records])
    result = {}
    for name, path in [('bc', SOURCE / 'bc_actor.zip'), ('ppo', next((SOURCE / 'train').glob('*/nino_ppo_final.zip')))]:
        model = PPO.load(path, device='cpu')
        model.policy.set_training_mode(False)
        with torch.no_grad():
            probabilities = model.policy.get_distribution(torch.as_tensor(observations)).distribution.probs.cpu().numpy()
        actions = probabilities.argmax(axis=1)
        if name == 'ppo' and not np.array_equal(actions, actual):
            raise ValueError('Saved actor does not reproduce executed categorical actions')
        item = dict(sha256=digest(path), observations=len(observations),
                    teacher_agreement=float(np.mean(actions == labels)),
                    normalized_probabilities=bool(np.allclose(probabilities.sum(axis=1), 1., atol=1e-6)), phases={})
        for key in ('ready', 'holding', 'recovering', 'cooldown'):
            mask = phase == key
            item['phases'][key] = dict(frames=int(mask.sum()),
                teacher_agreement=float(np.mean(actions[mask] == labels[mask])),
                mean_probabilities=probabilities[mask].mean(axis=0).tolist(),
                teacher_brake_actor_hold=int(np.sum(mask & (labels == 0) & (actions == 1))),
                teacher_recover_actor_hold=int(np.sum(mask & (labels == 2) & (actions == 1))))
        result[name] = item
    result['qualification'] = 'Exact shared pre-action tensors; offline BC replay does not predict a counterfactual physical outcome.'
    return result


def main():
    os.chdir(ROOT)
    torch.set_num_threads(2)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    model = next((SOURCE / 'train').glob('*/nino_ppo_final.zip'))
    files = [model, model.with_name('ppo.yaml'), SOURCE / 'bc_actor.zip', SOURCE / 'comparison.json',
             SOURCE / 'pilot_contract.json', *sorted((SOURCE / 'evaluation').glob('*/actor_capture/*.npz')),
             *sorted((SOURCE / 'evaluation').glob('*/*/episode-*/control_trace.csv')),
             *sorted((SOURCE / 'evaluation').glob('*/*/episode-*/drive_trace.csv'))]
    before = {str(p): digest(p) for p in files}
    preserved = ROOT / 'rl_runs/rough_rate_bc_trace_audit_v1/preserved/nino_ppo_final.zip'
    immutable(preserved, model.read_bytes())
    ppo, reactive = phase_audit('ppo'), phase_audit('pi_reactive')
    labels = ('startup', 'approach', 'braking', 'holding', 'recovery', 'cruise')
    difference = {key: ppo['phases'].get(key, {}).get('slip_integral', 0.) - reactive['phases'].get(key, {}).get('slip_integral', 0.) for key in labels}
    total = sum(difference.values())
    result = dict(complete=True, preserved_checkpoint=str(preserved), checkpoint_sha256=digest(model),
                  source_hashes=before, ppo=ppo, reactive_pi=reactive, actor_replay=actor_audit(),
                  slip_integral_differences= difference, total_slip_integral_difference=total,
                  startup_approach_share_of_net_difference=(difference['startup']+difference['approach'])/total if total else None,
                  selected_correction=dict(name='Phase-selective behavioral anchor during PPO',
                    proposal='Use the original demonstrated categorical actions as an auxiliary actor BC loss during holding/recovery; no global reward or speed-ramp change.',
                    evidence='Deterministic PPO loses demonstrated BRAKE/RECOVER decisions on identical pre-action tensors; compare BC replay before choosing coefficient.',
                    scope='One future new-contract pilot only after a bounded gradient-balance check; not implemented in the preserved actor and not started.',
                    expected_effect='Preserve complete disturbance sequences; reduction of physical slip is a hypothesis, not an established result.'),
                  limitations=['Phase exposures and physical positions differ; phase comparisons are descriptive, not causal intervention results.',
                    'Startup/approach slip differs despite full-scale commands. It is not justified to attribute this difference to PPO braking or recovery.',
                    'Ground-truth slip is retained for scoring; no scoring exclusions or metric changes.',
                    'Five fixed nominal E1 scenarios, one training seed; no generalization conclusion.'],
                  training_started=False, optuna_held=True)
    after = {str(p): digest(p) for p in files}
    if before != after or digest(preserved) != digest(model):
        raise ValueError('Source artifacts changed')
    result['source_artifacts_unchanged'] = True
    (OUTPUT / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    lines = ['# Rough BC-initialized PPO: saved slip and action audit', '',
             'Completed revision 56 is preserved byte-for-byte with a verified duplicate. No simulation, learning, reward edits or scoring changes in this audit.', '',
             '| Mode | PPO seconds | Reactive seconds | PPO slip RMS | Reactive slip RMS | Slip integral difference |',
             '|---|---:|---:|---:|---:|---:|']
    for key in labels:
        a, b = ppo['phases'].get(key, {}), reactive['phases'].get(key, {})
        fmt = lambda v: 'unavailable' if v is None else f'{v:.5f}'
        lines.append(f"| {key} | {a.get('seconds',0):.2f} | {b.get('seconds',0):.2f} | {fmt(a.get('slip_rms'))} | {fmt(b.get('slip_rms'))} | {difference[key]:+.6f} |")
    lines += ['', 'Startup: first 1 s; approach: physical remaining distance <0.5 m. Else braking/recovery: scale changes exceeding 0.005 per interval; holding: unchanged scale below 0.98. The phase clock is unchanged.',
              '', '## Executed wheel response', '',
              '| Controller / mode | Wheel tracking RMSE rad/s | Applied torque RMS Nm | Limit fraction | Stale samples |',
              '|---|---:|---:|---:|---:|']
    for name, audit in [('PPO', ppo), ('Reactive PI', reactive)]:
        for key, m in audit['phases'].items():
            lines.append(f"| {name} / {key} | {m['wheel_tracking_rmse_rad_s']:.4f} | {m['wheel_torque_rms_nm']:.4f} | {m['wheel_limit_fraction']:.4f} | {m['stale_samples']} |")
    replay = result['actor_replay']
    lines += ['', '## Exact actor replay', '',
              f"Original BC actor agreement with its teacher on PPO-visited tensors: {100*replay['bc']['teacher_agreement']:.2f}%; final PPO: {100*replay['ppo']['teacher_agreement']:.2f}%.",
              f"During holding, PPO selected HOLD instead of teacher BRAKE {replay['ppo']['phases']['holding']['teacher_brake_actor_hold']} times; during recovery, HOLD instead of RECOVER {replay['ppo']['phases']['recovering']['teacher_recover_actor_hold']} times.",
              'Normal braking-to-recovery reversals are not counted as chatter. Per-seed same-event/same-phase reversals and all motor details are in analysis.json.',
              '', '## Decision', '', result['selected_correction']['proposal'],
              'First check the auxiliary actor gradient against the PPO actor gradient; use a new contract. Keep reward weights, scoring, observations, geometry, bounds and ramp fixed.',
              'Do not slow recovery or increase the global slip penalty from these results: recovery slip RMS is not worse than the reactive reference.',
              'The proposed anchor targets demonstrated behavior erosion; it has not been shown to solve total-course slip.',
              '', *result['limitations'], '']
    (OUTPUT / 'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(dict(checkpoint_sha256=result['checkpoint_sha256'], phase_differences=difference,
                         selected_correction=result['selected_correction'], source_artifacts_unchanged=True), indent=2))


if __name__ == '__main__':
    main()
