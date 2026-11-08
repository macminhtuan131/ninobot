"""One offline correction: synthetic fixtures + shadow requests on sealed data.

No ROS initialization, processes, physics, actor, replay buffer or optimizer.
Old outcomes remain old outcomes even when a shadow request is different.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from nino_control.residual_velocity import FEATURES, SCALES
from .held_gain_candidate import (HeldGainCandidate, DecisionSupport, support_from_trace,
    specification, fingerprint, repo, ID)

SOURCE_MANIFEST = '3865c03c6881502ac81544c9908a339bd62eb10afe529274da589c153d9e6ebd'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def packet(references, wheel_linear):
    f=np.zeros((5,20))
    for name,values in [('baseline_v_m_s',np.full(5,.2)),('last_final_v_m_s',references),
            ('wheel_l_rad_s',np.asarray(wheel_linear)/.0625),('wheel_r_rad_s',np.asarray(wheel_linear)/.0625)]:
        f[:,FEATURES.index(name)]=np.asarray(values)/SCALES[FEATURES.index(name)]
    return np.r_[f.ravel(),.5,1.,0.]


def fixture_support(t):
    return DecisionSupport(t, 'synthetic_fixture_epoch', (t,)*5, True, True, True, False, False)


def fixtures():
    """Illustrative algebra and lag only; no calibrated Nino dynamics model."""
    summaries, traces = [], []
    geometry=dict(radius_l=.0625,radius_r=.0625)
    for gain in (.98,1.,1.02):
        c=HeldGainCandidate(geometry)
        refs=[.2]*5;wheels=[gain*.2]*5;rows=[]
        for i in range(30):
            obs=packet(refs,wheels)
            action,audit=c.step(obs,fixture_support(i*.1))
            rows.append(dict(t=i*.1,observation=obs.tolist(),support=asdict(fixture_support(i*.1)),
                request=action,audit=audit,synthetic_algebra_only=True))
            # A genuine synthetic feedback loop for the software mechanism;
            # no effort/torque/caster/body model or physical-benefit claim.
            reference=.2+action*.005
            refs=refs[1:]+[reference];wheels=wheels[1:]+[gain*reference]
        held=[r for r in rows if r['audit']['state']=='held']
        if gain!=1. and (not held or any(abs(r['request'])<1e-6 for r in held)):
            raise ValueError('Synthetic self-induced reference change lost held estimate')
        obs[101]=0.
        stopped=c.step(obs,fixture_support(3.))
        if stopped[0]!=0. or c.gain is not None:
            raise ValueError('Window close retained residual or estimate')
        rows.append(dict(t=3.,observation=obs.tolist(),support=asdict(fixture_support(3.)),
            request=stopped[0],audit=stopped[1],synthetic_algebra_only=True))
        summaries.append(dict(case='ideal_static_feedback',hidden_fixture_gain=gain,decisions=31,
            held_ticks=len(held),updated_ticks=sum(r['audit']['update_accepted'] for r in rows),
            bounded=all(abs(r['request'])<=1 for r in rows),window_close_zero=True,
            physical_outcome_evaluated=False))
        traces.append(rows)
    c=HeldGainCandidate(geometry);rows=[]
    for i in range(40):
        times=[max(0.,(i-4+j)*.1) for j in range(5)]
        wheels=[.2*(1.-math.exp(-t/.16)) for t in times]
        obs=packet([.2]*5,wheels);action,audit=c.step(obs,fixture_support(i*.1))
        rows.append(dict(t=i*.1,request=action,audit=audit,synthetic_lag_s=.16))
    accepted=[r['t'] for r in rows if r['audit']['update_accepted']]
    if not accepted or min(accepted)<1.:
        raise ValueError('Illustrative wheel transient accepted before stability screen')
    summaries.append(dict(case='constant_reference_with_illustrative_lag',decisions=40,
        first_update_s=min(accepted),physical_latency_measured=False))
    traces.append(rows)
    # Exact finite-packet ambiguity: hidden static-gain and hidden-state/lag
    # plants can yield the same observed five frames. No label enters c.step.
    left,right=HeldGainCandidate(geometry),HeldGainCandidate(geometry)
    same=packet([.2]*5,[.196]*5)
    for i in range(5):
        a=left.step(same,fixture_support(i*.1));b=right.step(same,fixture_support(i*.1))
        if a!=b:raise ValueError('Hidden label entered identical causal decisions')
    if a[1]['physical_gain_identified']:
        raise ValueError('Finite packet falsely claims physical identification')
    summaries.append(dict(case='indistinguishable_finite_packet',decisions=10,
        equal_input_equal_output=True,identification='unknown_static_gain_versus_hidden_dynamics'))
    return summaries,traces


def shadow(rows,geometry):
    if len(rows)!=140 or [r['step'] for r in rows]!=list(range(140)):
        raise ValueError('Exactly140 ordered sealed source decisions required')
    c=HeldGainCandidate(geometry);trace=[]
    for row in rows:
        # Epoch is a locally assigned run boundary, not a gain/arm/layout label.
        support=support_from_trace(row['reference_trace'],epoch='sealed_source_run')
        action,audit=c.step(row['equal_observation'],support)
        trace.append(dict(step=row['step'],clock_s=support.clock_s,
            shared_window=bool(row['equal_observation'][101]),shadow_request_scalar=action,
            recorded_source_request_scalar=row['requested_scalar_action'][0],**audit,
            trajectory_source='recorded_v1_policy_not_shadow_closed_loop',new_outcome=False))
    active=[r for r in trace if r['shared_window']]
    return dict(source_condition=rows[0]['qualification_condition'],source_rows=140,
        shadow_ticks=140,open_ticks=len(active),states=dict(Counter(r['state'] for r in active)),
        reasons=dict(Counter(r['reason'] for r in active)),
        new_nonzero_shadow_requests=sum(abs(r['shadow_request_scalar'])>1e-8 for r in active),
        recorded_nonzero_requests=sum(abs(r['recorded_source_request_scalar'])>1e-8 for r in active),
        maximum_held_age_s=max((r['estimate_age_s'] for r in trace if r['state']=='held'),default=None),
        not_a_counterfactual_outcome=True),trace


def source():
    from .gain_baseline_qualification import validated_latest,ROOT_NAME
    out=validated_latest(Path.home()/'nino_research'/ROOT_NAME,check_runtime=False)
    if sha(out/'manifest.json')!=SOURCE_MANIFEST:
        raise ValueError('Unexpected baseline qualification source')
    return out


def run(output):
    output=Path(output).expanduser().resolve()
    upstream=source()
    if (output==upstream or output.is_relative_to(upstream) or upstream.is_relative_to(output)
            or output.is_relative_to(repo()/'src')):
        raise ValueError('Offline artifact must be outside source and sealed dataset')
    if output.exists():
        raise ValueError('Offline artifact already exists; retain result, do not overwrite')
    current=fingerprint();p=specification()
    output.mkdir(parents=True,exist_ok=False)
    write(output/'specification.json',p)
    try:
        cases,traces=fixtures();runs=[];pins={}
        write(output/'synthetic_fixture_trace.json',traces)
        for i in range(9):
            cell=upstream/f'eval_{i:02d}'
            rows=[json.loads(line) for line in (cell/'trace.jsonl').read_text().splitlines()]
            summary,shadow_trace=shadow(rows,read(cell/'config.json')['config']['nominal_geometry'])
            for name in ('trace.jsonl','config.json'):
                pins[str(cell/name)]=sha(cell/name)
            runs.append(summary);write(output/f'shadow_{i:02d}_not_outcome.json',shadow_trace)
        if fingerprint()!=current or source()!=upstream:
            raise ValueError('Candidate or sealed source changed during offline qualification')
        result=dict(candidate_id=ID,status='offline_behavior_passed_identification_unknown',
            software_behavior_passed=True,gain_identification='unknown_static_gain_versus_dynamics_bias',
            fixtures=cases,synthetic_decisions=sum(c['decisions'] for c in cases),runs=runs,
            source_rows=1260,shadow_decisions=1260,shadow_is_not_outcome=True,
            source_artifact=str(upstream),source_manifest_sha256=SOURCE_MANIFEST,source_inputs_sha256=pins,
            new_gazebo_launches=0,new_physics_steps=0,actor_loads=0,new_training_transitions=0,
            new_optimizer_updates=0,hardware_actions=0,physics_released=False,training_released=False,
            physical_benefit_verified=False,correction_count=1,correction_budget_closed=True,
            decision='no_automatic_physics_or_learner_release_keep_classical_diagnose_dynamics',
            remaining_question='encoder/reference proxy may mix lag, tracking bias and geometry; no gain-ID claim',
            real_data_cutoff='2026-11-02')
        write(output/'qualification.json',result)
        write(output/'manifest.json',dict(candidate_id=ID,fingerprint=current,status='completed',
            created_utc=datetime.now(timezone.utc).isoformat(),
            files={f.name:sha(f) for f in output.iterdir() if f.is_file()}))
        return result
    except BaseException as exc:
        write(output/'failure.json',dict(error=repr(exc),physics=0,training=0,retain_do_not_retry=True))
        raise


def verified_report(output):
    output=Path(output).resolve();m=read(output/'manifest.json')
    if m['status']!='completed' or m['fingerprint']!=fingerprint():
        raise ValueError('Held candidate sources or completion changed')
    for name,value in m['files'].items():
        path=(output/name).resolve()
        if path.parent!=output or sha(path)!=value:
            raise ValueError('Held offline artifact changed')
    result=read(output/'qualification.json');upstream=Path(result['source_artifact'])
    if (result['source_manifest_sha256']!=SOURCE_MANIFEST or sha(upstream/'manifest.json')!=SOURCE_MANIFEST
            or not result['software_behavior_passed'] or result['physics_released'] or result['training_released']):
        raise ValueError('Held candidate source/release evidence invalid')
    for name,value in result['source_inputs_sha256'].items():
        path=Path(name).resolve()
        if not path.is_relative_to(upstream.resolve()) or sha(path)!=value:
            raise ValueError('Sealed source input changed')
    # Read-only dependency/source check; no execution, actor or ROS init.
    if source()!=upstream:raise ValueError('Gain source no longer matches qualification')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();r=run(args.output)
    print(json.dumps(dict(status=r['status'],shadow_rows=r['shadow_decisions'],
        synthetic_decisions=r['synthetic_decisions'],physics=0,training=0),indent=2))


if __name__=='__main__':main()
