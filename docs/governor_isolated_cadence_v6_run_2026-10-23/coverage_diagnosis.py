#!/usr/bin/env python3
"""One read-only coverage diagnosis. No filling, rescoring or experiment release."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('src/nino_rl','src/nino_control','src/nino_rl/scripts')]
from nino_rl.acquisition_frames import read_frames
from audit_governor_phase_slip import load,read_csv
from audit_gt_timestamp_slip import gt_timestamp_series


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def main():
    out=Path(__file__).resolve().parent
    protected=json.loads((out/'closed_run_sha256.json').read_text())
    assert all(sha(p)==h for p,h in protected.items())
    ledger=json.loads((ROOT/'rl_runs/governor_isolated_cadence_v6_2026-10-23/ledger.json').read_text())
    r=ledger['slots'][0]['result'];case=Path(r['case']);view=Path(r['logger'])
    windows=r['quality']['existing_reports']['gt_native']
    crossing=windows['crossing'];start,end=crossing['start_s'],crossing['end_s']
    data=load(case,dict(r,seed=77600,profile='full'))
    signal=gt_timestamp_series(data)
    raw=list(read_frames(case/'joint_gt'))  # Fully consumes CRC/sequence/SHA validation.
    reset=[f for f in raw if f['topic']=='/nino/governor/episode'][0]
    selected=[f for f in raw if f['epoch']==reset['epoch']]
    joint=[f for f in selected if f['topic']=='/joint_states']
    gt=[f for f in selected if f['topic']=='/ground_truth/odom']
    primary_joint={};primary_gt={}
    for line in (Path(r['primary_logger'])/'samples.jsonl').open():
        row=json.loads(line)
        if row['topic'] not in ('/joint_states','/ground_truth/odom'):continue
        s=row['data']['header']['stamp'];ns=s['sec']*1_000_000_000+s['nanosec']
        if start-.1<=ns*1e-9<=end+.1:
            (primary_joint if row['topic']=='/joint_states' else primary_gt)[ns]=row
    gaps=[]
    for a,b in zip(joint,joint[1:]):
        if b['source_ns']-a['source_ns']<=10_001_000:continue
        if not (a['source_ns']*1e-9<end and b['source_ns']*1e-9>start):continue
        delivered_elsewhere=sorted(t for t in primary_joint if a['source_ns']<t<b['source_ns'])
        gaps.append(dict(start_s=a['source_ns']*1e-9,end_s=b['source_ns']*1e-9,
            source_gap_ms=(b['source_ns']-a['source_ns'])*1e-6,
            receipt_wall_gap_ms=(b['receipt_monotonic_ns']-a['receipt_monotonic_ns'])*1e-6,
            receipt_sim_gap_ms=(b['receipt_sim_ns']-a['receipt_sim_ns'])*1e-6,
            sequence_before=a['sequence'],sequence_after=b['sequence'],
            primary_joint_stamps_inside_s=[t*1e-9 for t in delivered_elsewhere]))
    invalid=[]
    for i in range(len(signal['time'])-1):
        a,b=signal['time'][i:i+2]
        if min(b,end)<=max(a,start):continue
        if (b-a>.040001 or not np.isfinite(signal['q'][i:i+2]).all()
                or not np.isfinite(signal['xy'][i:i+2]).all()):
            invalid.append(dict(gt_segment_s=[float(a),float(b)],overlap_s=float(min(b,end)-max(a,start)),
                mean_square_finite=np.isfinite(signal['q'][i:i+2]).tolist(),
                joint_support_s=signal['joint_support_stamps'][i:i+2].tolist()))
    # Verify raw CDR -> decoded -> selected view source-stamp fidelity.
    sets={name:{f['source_ns'] for f in rows if start<=f['source_ns']*1e-9<=end}
          for name,rows in (('joint',joint),('gt',gt))}
    view_sets={name:set() for name in sets}
    for line in (view/'samples.jsonl').open():
        row=json.loads(line)
        name={'/joint_states':'joint','/ground_truth/odom':'gt'}.get(row['topic'])
        if name is None:continue
        s=row['data']['header']['stamp'];ns=s['sec']*1_000_000_000+s['nanosec']
        if start<=ns*1e-9<=end:view_sets[name].add(ns)
    drives=read_csv(next(Path(r['evaluation']).glob('episode-*/drive_trace.csv')))
    context=[{k:v for k,v in d.items() if k in ('sim_time_s','control_joint_age_max_s',
        'control_raw_dt_max_s','control_updates','control_dt_over_4ms','have_wheel_state')}
        for d in drives if any(g['start_s']-.04<=float(d['sim_time_s'])<=g['end_s']+.04 for g in gaps)]
    result=dict(mode='offline_gap_diagnosis',simulation_attempts=0,thresholds_changed=False,
        original_crossing=crossing,invalid_quadrature_segments=invalid,
        invalid_seconds=sum(v['overlap_s'] for v in invalid),isolated_joint_gaps=gaps,
        raw_capture_integrity_passed=True,
        raw_to_view_stamps_unchanged={name:sets[name]==view_sets[name] for name in sets},
        gt_source_max_gap_ms=max((b['source_ns']-a['source_ns'])*1e-6 for a,b in zip(gt,gt[1:])
            if a['source_ns']*1e-9<end and b['source_ns']*1e-9>start),
        drive_context=context,
        qualification='A timestamp present in primary but absent in recorder proves delivery to another consumer, not the exact drop location or cause. Contiguous frame sequence validates recorded frames, not source publication completeness.',
        source_sha256=sha(__file__))
    result['closed_run_files_unchanged']=all(sha(p)==h for p,h in protected.items())
    assert result['closed_run_files_unchanged']
    (out/'coverage_diagnosis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
