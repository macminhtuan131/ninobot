#!/usr/bin/env python3
"""Read-only post-pilot action-phase comparison; optionally wait for saved results."""
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np

from audit_rough_observable_pilot import annotate, csv_rows, digest, single, stats


def batch(root):
    directory = root / 'evaluation/ppo'
    episodes_file = single(directory.glob('*/episodes.csv'))
    episodes = csv_rows(episodes_file)
    captures = {}
    sources = {str(episodes_file): digest(episodes_file)}
    for path in sorted((directory / 'actor_capture').glob('*.npz')):
        sources[str(path)] = digest(path)
        with np.load(path, allow_pickle=False) as z:
            for raw, observation in zip(z['records'], z['observations']):
                record = json.loads(str(raw))
                captures.setdefault(record['attempt'], []).append((record, observation.copy()))
    result = {}
    for episode in episodes:
        path = episodes_file.parent / f'episode-{int(episode["episode"]):03d}/control_trace.csv'
        rows = csv_rows(path)
        sources[str(path)] = digest(path)
        ann = annotate(rows, captures[int(episode['attempt'])], .05)
        quiet = [r for r in ann if r['quiet'] and r['mode'] != 'startup_or_approach']
        result[int(episode['seed'])] = dict(
            modes={mode: stats([r for r in ann if r['mode'] == mode])
                   for mode in ('slowdown', 'acceleration', 'persistent_reduced', 'steady_cruise', 'startup_or_approach')},
            quiet_scale=stats(quiet)['mean_scale'], total_time_s=float(episode['time_seconds']))
    return result, sources


def worker_alive(status):
    try:
        pid = int(status['pid'])
        os.kill(pid, 0)
        return b'run_rough_recovery_sigma_pilot.py' in Path(f'/proc/{pid}/cmdline').read_bytes()
    except (OSError, KeyError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('rl_runs/rough_observable_pilot_v2'))
    parser.add_argument('--candidate', type=Path, default=Path('rl_runs/rough_recovery_sigma_pilot_v1'))
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    root = args.candidate.resolve()
    comparison_file = root / 'comparison.json'
    if args.wait:
        # Waiting happens in this optional background monitor, not in the trainer.
        # A stopped/interrupted trainer is reported; no simulator or training is resumed here.
        deadline = time.monotonic() + 9000
        while not comparison_file.exists():
            status_file = root / 'status.json'
            status = json.loads(status_file.read_text()) if status_file.exists() else {}
            if status.get('stage') == 'interrupted' or not worker_alive(status):
                raise RuntimeError('Pilot stopped before final comparison; saved checkpoints remain preserved')
            if time.monotonic() >= deadline:
                raise TimeoutError('No saved comparison within bounded monitoring period')
            time.sleep(10)
    if not comparison_file.exists():
        raise ValueError('No completed candidate comparison')
    old, old_sources = batch(args.source.resolve())
    new, new_sources = batch(root)
    if sorted(old) != sorted(new):
        raise ValueError('Diagnostic seeds must match the previous pilot')
    comparison = json.loads(comparison_file.read_text())
    paired = [dict(seed=seed, before=old[seed], after=new[seed],
                   quiet_scale_delta=new[seed]['quiet_scale']-old[seed]['quiet_scale']) for seed in sorted(old)]
    aggregate = {}
    for mode in next(iter(old.values()))['modes']:
        aggregate[mode] = {}
        for label, rows in [('before', old), ('after', new)]:
            items = [v['modes'][mode] for v in rows.values()]
            seconds = sum(v['seconds'] for v in items)
            slip = sum(v['slip_integral'] for v in items)
            aggregate[mode][label] = dict(mean_seconds=seconds/len(rows),
                pooled_slip_rms=(slip/seconds)**.5 if seconds else None,
                mean_slip_integral=slip/len(rows))
        a, b = aggregate[mode]['before'], aggregate[mode]['after']
        aggregate[mode]['slip_rms_ratio'] = b['pooled_slip_rms']/a['pooled_slip_rms'] if a['pooled_slip_rms'] and b['pooled_slip_rms'] is not None else None
    sources = {**old_sources, **new_sources, str(comparison_file): digest(comparison_file),
               str(Path(__file__).resolve()): digest(__file__),
               str(Path(__file__).with_name('audit_rough_observable_pilot.py')): digest(Path(__file__).with_name('audit_rough_observable_pilot.py'))}
    result = dict(paired=paired, aggregate_modes=aggregate, sources_sha256=sources,
        pilot_passed=comparison['pilot_passed'], learned_response_gate=comparison['learned_response_gate'],
        ride_quality_gate=comparison['ride_quality_gate'],
        unchanged_acceptance='Diagnostic phase metrics do not change existing physical/behavior/quality gates.',
        qualification='Same reset scenarios and training seed, different trained actors. Mode membership/duration can change; phase slip is associational and not a causal acceleration test. Returns from different rewards are not compared.',
        optuna_held=True)
    (root / 'action_response_comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    lines = ['# Reward-only pilot: speed recovery and slip', '',
        '| Executed scale mode | Old duration | New duration | Old slip RMS | New slip RMS |',
        '|---|---:|---:|---:|---:|']
    for mode, group in aggregate.items():
        a, b = group['before'], group['after']
        f = lambda v: f'{v:.5f}' if v is not None else 'no samples'
        lines.append(f'| {mode} | {a["mean_seconds"]:.2f}s | {b["mean_seconds"]:.2f}s | {f(a["pooled_slip_rms"])} | {f(b["pooled_slip_rms"])} |')
    lines += ['', '| Seed | Previous quiet scale | Corrected quiet scale |', '|---|---:|---:|']
    for p in paired:
        lines.append(f'| {p["seed"]} | {p["before"]["quiet_scale"]:.4f} | {p["after"]["quiet_scale"]:.4f} |')
    lines += ['', f'Existing pilot gate passed: **{comparison["pilot_passed"]}**. '
        f'Learned response: {comparison["learned_response_gate"]}; ride quality: {comparison["ride_quality_gate"]}.', '',
        result['qualification'], '', 'Physical scoring and acceptance thresholds remain unchanged. Optuna remains held.', '']
    (root / 'ACTION_RESPONSE_REPORT.md').write_text('\n'.join(lines))
    print('Saved action-phase comparison:', root / 'ACTION_RESPONSE_REPORT.md', flush=True)


if __name__ == '__main__':
    main()
