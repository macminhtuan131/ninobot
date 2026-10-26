#!/usr/bin/env python3
"""Existing-data diagnostics only. Never imports a simulation runner."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / p) for p in
               ('src/nino_rl/scripts', 'src/nino_rl', 'src/nino_control')]
from audit_governor_phase_slip import load, read_csv
from audit_governor_survey_phases import parse_context
from audit_gt_timestamp_slip import gt_timestamp_series
from prepare_governor_contact_sequence import signal_stats
from nino_rl.slip_reporting import integrate, replay_native_trace, RADIUS


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def divergence(candidate, reference, earliest_input, threshold, max_gap):
    """Diagnostic pair divergence; source support is always backward-only."""
    candidate, reference = np.asarray(candidate), np.asarray(reference)
    rows = []
    for t, v in candidate:
        if not -.3 <= t <= 1.:
            continue
        j = np.searchsorted(reference[:, 0], t, side='right') - 1
        if j >= 0 and t - reference[j, 0] <= max_gap and np.isfinite([v, reference[j,1]]).all():
            rows.append([float(t), float(v-reference[j, 1]), float(reference[j, 0])])
    baseline = [d for t, d, rt in rows if -.3 <= t <= -.05]
    if len(baseline) < 3:
        return dict(available=False, reason='insufficient_precontact_support')
    correction = float(np.median(baseline))
    corrected = [[t, d-correction, rt] for t, d, rt in rows]
    pre = [d for t, d, rt in corrected if 0 <= t < earliest_input]
    result = dict(available=True, baseline_candidate_minus_reference_m_s=correction,
                  pre_input_max_abs_adjusted_difference_m_s=max(map(abs, pre), default=None),
                  onset=None, causal_response_onset=None,
                  interpretation='Between-run divergence; unequal physical states, no causal onset identified')
    begin = None
    for i, (t, d, rt) in enumerate(corrected):
        continuous = i == 0 or t-corrected[i-1][0] <= max_gap
        if not np.isfinite(d) or d > -threshold or not continuous:
            begin = None
        if np.isfinite(d) and d <= -threshold:
            if begin is None:
                begin = i
            if t-corrected[begin][0] >= .06-1e-9:
                first = corrected[begin]
                previous = corrected[begin-1] if begin else None
                lower = min(previous[0], previous[2]) if previous else None
                result['onset'] = dict(bracket_s=[lower, first[0]],
                    first_candidate_stamp_s=first[0], reference_support_s=first[2],
                    confirmed_s=t, precedes_earliest_input=first[0] < earliest_input,
                    left_censored=previous is None)
                break
    result['trajectory'] = corrected
    return result


def residual(signal, imu, first, cut):
    total = integrate(signal, first, first+3.)
    tail = integrate(signal, cut, first+3.)
    # A diagnostic squared-sample sum, consistent with original unfiltered IMU RMS.
    all_values = [v for t, v in imu if first <= t <= first+3.]
    after_values = [v for t, v in imu if cut <= t <= first+3.]
    denominator = sum(v*v for v in all_values)
    fraction = (tail['slip_square_integral_s']/total['slip_square_integral_s']
                if tail['available'] and total['available']
                and total['slip_square_integral_s'] > 0 else None)
    return dict(cut_offset_s=cut-first, slip=tail, slip_fraction_remaining=fraction,
                imu_squared_sample_fraction_remaining=sum(v*v for v in after_values)/denominator
                if denominator > 0 else None,
                imu_samples_remaining=len(after_values), imu_samples_total=len(all_values),
                vertical=signal_stats(imu, cut, first+3.))


def command(controls, drive):
    reduced = next((c for c in controls if float(c['governor_scale']) < .999999), None)
    if reduced is None:
        return None
    ti = float(reduced['governor_input_time_s'])
    upstream = float(reduced['governor_requested_linear_m_s'])
    expected = upstream * float(reduced['governor_scale'])
    # Exact first reduced input acknowledgement, not later route goal braking.
    found = next((d for d in drive if
        abs(float(d['command_received_sim_s'])-ti) < 1e-7
        and abs(float(d['requested_linear_m_s'])-expected) < 1e-6), None)
    return dict(input_s=ti, received_s=float(found['command_received_sim_s']) if found else None,
                publication_s=float(found['sim_time_s']) if found else None)


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    write(output/'plan_before_calculation.json', plan)
    manifest = {}
    def protect(path):
        path = Path(path).resolve()
        manifest[str(path)] = sha(path)
    for p in (HERE/'plan.json', Path(__file__), ROOT/'src/nino_rl/nino_rl/slip_reporting.py',
              ROOT/'src/nino_rl/scripts/audit_gt_timestamp_slip.py',
              ROOT/'src/nino_rl/scripts/audit_governor_survey_phases.py',
              ROOT/'src/nino_rl/scripts/audit_governor_phase_slip.py',
              ROOT/'src/nino_rl/scripts/prepare_governor_contact_sequence.py',
              ROOT/'src/nino_control/nino_control/governor_core.py'):
        protect(p)
    episodes, sources, assigned = [], {}, []
    frozen_path = ROOT/'docs/governor_survey_phase_audit_2026-10-20/report.json'
    protect(frozen_path)
    frozen = json.loads(frozen_path.read_text())
    for batch, folder in [('survey', 'governor_descriptive_survey_2026-10-18'),
                          ('cadence', 'governor_cadence_experiment_2026-10-20')]:
        ledger = ROOT/'rl_runs'/folder/'ledger.json'
        protect(ledger)
        slots = json.loads(ledger.read_text())['slots']
        assert len(slots) == (16 if batch == 'survey' else 12)
        for slot in slots:
            ident = f"{batch}_{slot['attempt']:02d}"
            r = slot.get('result') or {}
            assigned.append(dict(id=ident, batch=batch, attempt=slot['attempt'],
                seed=slot['seed'], repeat=slot['repeat'], arm=slot.get('arm', slot['profile']),
                status=slot.get('status'), physical_success=r.get('physical_success'),
                stop_pass=r.get('stop_pass'), measurement_integrity_pass=r.get('measurement_integrity_pass')))
            old = (r.get('quality') or {}).get('existing_reports') or {}
            first = old.get('first_contact_s')
            if first is None or not r.get('logger'):
                continue
            evaluation, logger = Path(r['evaluation']), Path(r['logger'])
            cp = next(evaluation.glob('episode-*/'+('governor_update_trace.csv'
                      if slot.get('arm') == 'reactive_20ms' else 'control_trace.csv')))
            dp = next(evaluation.glob('episode-*/drive_trace.csv'))
            for p in (cp, dp, next(evaluation.glob('episode-*/control_trace.csv')),
                      evaluation/'episodes.csv', logger/'samples.jsonl',
                      logger/'contact_events.jsonl', logger/'resolved_config.json'):
                protect(p)
            data = load(Path(r['case']), dict(r, seed=slot['seed'], profile=slot['profile']))
            context = parse_context(data)
            signal = gt_timestamp_series(data)
            cmd = command(read_csv(cp), read_csv(dp))
            episode = dict(id=ident, batch=batch, seed=slot['seed'], repeat=slot['repeat'],
                arm=slot.get('arm',slot['profile']), first_manifold_s=first,
                command=cmd, sampling=data['sampling'], contact={},
                causal_actual_response_onset=None,
                interpretation='Residual observed cost, never a preventable-cost estimate',
                whole_slip=integrate(signal, data['start'], data['end']),
                native=replay_native_trace(data['controls']),
                residual=[residual(signal, context['imu'], first, first+offset)
                          for offset in plan['remaining_cost_offsets_s']],
                whole_post_vertical=signal_stats(context['imu'], first, first+3.))
            for component, samples in context['contacts'].items():
                selected = [(i,t) for i,(t,v) in enumerate(samples)
                            if first <= t <= data['end'] and v['obstacle_loaded']]
                if selected:
                    i, t = selected[0]
                    episode['contact'][component] = dict(
                        first_loaded_offset_s=t-first,
                        first_loaded_observation_bracket_s=[samples[i-1][0]-first if i else None, t-first],
                        last_loaded_offset_s=selected[-1][1]-first,
                        residual_at_first_loaded=residual(signal,context['imu'],first,t))
            if cmd:
                episode['command_offsets_s'] = {k:v-first if v is not None else None for k,v in cmd.items()}
                episode['clean_floor90_transfer_illustration'] = [
                    residual(signal, context['imu'], first, cmd['input_s']+lag) for lag in (.239,.254)]
                episode['clean_floor90_margin_to_drive_left_s'] = [
                    episode['contact']['left_wheel']['first_loaded_offset_s']
                    -(cmd['input_s']-first+lag) for lag in (.254,.239)]
            if batch == 'survey':
                prev = next(e for e in frozen['episodes'] if e['attempt'] == slot['attempt'])
                a,b=episode['whole_slip']['slip_square_integral_s'],prev['whole']['slip_square_integral_s']
                if not np.isclose(a,b,atol=1e-12,rtol=1e-10):
                    raise ValueError('Original survey slip changed')
                episode['original_whole_slip_reproduced'] = True
            sources[ident] = dict(body=np.column_stack((data['ground'][:,0]-first,data['ground'][:,1])),
                left=np.column_stack((data['joints'][:,0]-first,RADIUS*data['joints'][:,1])),
                right=np.column_stack((data['joints'][:,0]-first,RADIUS*data['joints'][:,2])))
            episodes.append(episode)
            print('Read existing '+ident, flush=True)
    pairs = []
    for batch, seeds, repeats, arms in [('survey',(77500,77501),range(1,5),('reactive','full')),
                                       ('cadence',(77600,77601),range(1,3),('reactive_20ms','reactive_100ms'))]:
        for seed in seeds:
            for repeat in repeats:
                chosen = [next((e for e in episodes if e['batch']==batch and e['seed']==seed
                               and e['repeat']==repeat and e['arm']==arm),None) for arm in arms]
                pair = dict(batch=batch,seed=seed,repeat=repeat,arms=arms,
                    available=False, reason='missing_or_integrity_failed_arm', diagnostics=[])
                if all(chosen):
                    ids=[e['id'] for e in chosen]
                    integrity = all(next(s for s in assigned if s['id']==i)['measurement_integrity_pass'] is True for i in ids)
                    if integrity:
                        pair.update(available=True,reason=None,ids=ids)
                        inputs = [e['command']['input_s']-e['first_manifold_s'] for e in chosen if e['command']]
                        earliest = min(inputs)
                        pair['earliest_input_offset_s']=earliest
                        for channel in ('body','left','right'):
                            for threshold in plan['divergence_sensitivities_m_s']:
                                diag = divergence(sources[ids[0]][channel], sources[ids[1]][channel],
                                    earliest,threshold,.040001 if channel=='body' else .010001)
                                diag.update(channel=channel,threshold_m_s=threshold)
                                pair['diagnostics'].append(diag)
                pairs.append(pair)
    write(output/'report.json', dict(plan=plan,assigned=assigned,episodes=episodes,pairs=pairs,
        causal_response_identified=False,cadence_quality_comparison_allowed=False,
        reason='Closed cadence batch failed integrity; timing subset is descriptive only',
        decision='Pending written review of this artifact; no release or promotion is performed by this tool'))
    with (output/'remaining_cost.csv').open('w') as stream:
        writer=csv.writer(stream)
        writer.writerow(['id','arm','cut_offset_s','slip_fraction_remaining','imu_squared_sample_fraction_remaining','slip_coverage'])
        for e in episodes:
            for r in e['residual']:
                writer.writerow([e['id'],e['arm'],r['cut_offset_s'],r['slip_fraction_remaining'],
                    r['imu_squared_sample_fraction_remaining'],r['slip']['coverage_fraction']])
    changed=[p for p,h in manifest.items() if sha(p)!=h]
    write(output/'provenance.json',dict(inputs_sha256=manifest,changed_during_audit=changed,inputs_unchanged=not changed))
    if changed:
        raise ValueError('Input drift during offline audit')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output)
