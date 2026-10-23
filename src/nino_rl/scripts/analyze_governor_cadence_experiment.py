#!/usr/bin/env python3
"""Descriptive three-arm analysis, fixed metrics and null-preserving contrasts."""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from prepare_governor_cadence_experiment import validate, validate_schedule, SEEDS, sha, write
from analyze_governor_h2_replication import extract_metrics, METRICS, UNITS, timing_evidence
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from nino_rl.slip_reporting import integrate

CONTRASTS = (("reactive_20ms","reactive_100ms"),("reactive_100ms","full"),("reactive_20ms","full"))


def estimate(rows):
    """Resample intact triads; identical draws for every metric and contrast."""
    rng=np.random.default_rng(20261020)
    draws={s:rng.integers(0,2,(10000,2)) for s in SEEDS}
    result={}
    for candidate,reference in CONTRASTS:
        contrasts={}
        for key in METRICS:
            blocks={};boot=[];benefit_boot=[]
            for seed in SEEDS:
                pairs=[]
                for repeat in (1,2):
                    arms={r["arm"]:r for r in rows if r["seed"]==seed and r["repeat"]==repeat}
                    pairs.append([arms.get(a,{}).get("metrics",{}).get(key) for a in (reference,candidate)])
                entry=dict(complete_pairs=sum(all(v is not None and math.isfinite(v) for v in pair) for pair in pairs),
                           reference_mean=None,candidate_mean=None,delta=None,relative_benefit=None)
                if entry["complete_pairs"]==2:
                    values=np.array(pairs,float)
                    ref,can=values.mean(axis=0)
                    resampled=values[draws[seed]].mean(axis=1)
                    delta=resampled[:,1]-resampled[:,0]
                    entry.update(reference_mean=float(ref),candidate_mean=float(can),delta=float(can-ref),
                                 relative_benefit=float(1-can/ref) if ref>0 else None)
                    boot.append(delta)
                    benefit_boot.append(1-resampled[:,1]/resampled[:,0] if np.all(resampled[:,0]>0) else None)
                blocks[str(seed)]=entry
            aggregate=dict(delta=None,delta_CI95=None,relative_benefit=None,benefit_CI95=None)
            if len(boot)==2:
                aggregate.update(delta=float(np.mean([b["delta"] for b in blocks.values()])),
                    delta_CI95=np.percentile(np.mean(boot,axis=0),[2.5,97.5]).tolist())
                if all(b is not None for b in benefit_boot):
                    aggregate.update(relative_benefit=float(np.mean([b["relative_benefit"] for b in blocks.values()])),
                        benefit_CI95=np.percentile(np.mean(benefit_boot,axis=0),[2.5,97.5]).tolist())
            contrasts[key]=dict(unit=UNITS[key],blocks=blocks,aggregate=aggregate)
        result[candidate+"_minus_"+reference]=contrasts
    return result


def report(protocol, slots):
    validate_schedule(protocol["schedule"])
    structural=[];rows=[]
    if len(slots)!=12 or [s.get("attempt") for s in slots]!=list(range(1,13)):
        structural.append("ledger_missing_duplicate_or_out_of_order_slots")
    for job in protocol["schedule"]:
        matching=[s for s in slots if s.get("attempt")==job["attempt"]]
        slot=matching[0] if len(matching)==1 else {}
        valid=all(slot.get(k)==v for k,v in job.items())
        r=(slot.get("result") or {}) if valid else {}
        if not valid:
            structural.append(f"attempt_{job['attempt']}_identity_invalid")
        if r and (r.get("seed"),r.get("profile"),r.get("arm"))!=(job["seed"],job["profile"],job["arm"]):
            structural.append(f"attempt_{job['attempt']}_child_identity_invalid");r={}
        if r and ((r.get("physical_success") is not None and type(r["physical_success"]) is not bool)
                  or (r.get("physical_success") is True and r.get("termination")!="success")):
            structural.append(f"attempt_{job['attempt']}_native_outcome_inconsistent");r={}
        rows.append(dict(**job,status=slot.get("status","not_attempted"),
            physical_success=r.get("physical_success"),termination=r.get("termination"),stop_pass=r.get("stop_pass"),
            metrics=extract_metrics(r),native_outcome=r.get("native_outcome"),cadence_integrity=r.get("cadence_integrity")))
    stats=estimate(rows)
    sensitivity={}
    for contrast,metrics in stats.items():
        sensitivity[contrast]={}
        for label in (*map(str,SEEDS),"aggregate"):
            values={key:(metrics[key]["aggregate"] if label=="aggregate" else metrics[key]["blocks"][label])["relative_benefit"]
                    for key in ("post_slip","grid_slip","shifted_slip")}
            observed=list(values.values())
            sensitivity[contrast][label]=dict(values=values,sign_reversal=
                min(observed)<0<max(observed) if all(v is not None for v in observed) else None)
    return dict(mode="descriptive_cadence_experiment",H2_decision="not_assessed",thresholds_applied=False,
        automatic_promotion=False,structural_issues=structural,episodes=rows,contrasts=stats,sampling_sensitivity=sensitivity,
        counts=dict(assigned=12,arrivals=sum(r["physical_success"] is True for r in rows),
                    failures=sum(r["physical_success"] is False for r in rows),
                    unknown=sum(r["physical_success"] is None for r in rows)),
        uncertainty="Only2 triads per block: bootstrap intervals descriptive, no guaranteed power/coverage. No metric/interval fills missing data or drops failures.")


def timing(slot):
    r=slot.get("result") or {};old=(r.get("quality") or {}).get("existing_reports") or {}
    tc=old.get("first_contact_s")
    if tc is None:
        return dict(available=False,reason="contact_window_unavailable_not_zero"),None
    evaluation,logger=Path(r["evaluation"]),Path(r["logger"])
    cp=next(evaluation.glob("episode-*/"+("governor_update_trace.csv" if slot["arm"]=="reactive_20ms" else "control_trace.csv")))
    dp=next(evaluation.glob("episode-*/drive_trace.csv"))
    ground={};joints={};loads=[]
    for line in (logger/"samples.jsonl").open():
        packet=json.loads(line);d=packet["data"];topic=packet["topic"]
        if "header" not in d:continue
        s=d["header"]["stamp"];t=s["sec"]+s["nanosec"]*1e-9
        if not tc-.4<=t<=tc+3.05:continue
        if topic=="/ground_truth/odom":ground[t]=d["twist"]["twist"]
        elif topic=="/joint_states":joints[t]=dict(zip(d["name"],d["velocity"]))
        elif topic.startswith("/nino/contact_lab/"):
            for c in d["contacts"]:
                names=[c[k]["name"] for k in ("collision1","collision2")]
                if not any("cable_bumps" in n for n in names):continue
                if any(depth>0 and sum(w["body_1_wrench"]["force"][k]**2 for k in ("x","y","z"))>1e-12
                       for depth,w in zip(c["depths"],c["wrenches"])):
                    loads.append(dict(time_s=t,component=topic.rsplit("/",1)[-1],collisions=names))
    events=[json.loads(line) for line in (logger/"contact_events.jsonl").open()]
    evidence=timing_evidence(list(csv.DictReader(cp.open())),list(csv.DictReader(dp.open())),events,
        sorted(loads,key=lambda x:x["time_s"]),sorted(ground.items()),sorted(joints.items()),tc,slot["profile"])
    data=load(Path(r["case"]),dict(seed=slot["seed"],profile=slot["profile"],evaluation=str(evaluation),logger=str(logger)))
    signal=gt_timestamp_series(data)
    evidence["precontact_slip"]=integrate(signal,tc-.3,tc-.05)
    evidence["first50ms_fixed_diagnostic_not_necessarily_negative_control"]=integrate(signal,tc,tc+.05)
    evidence["first_contact_s"]=tc
    e=evidence.get("first_executed")
    evidence["execution_after_contact_s"]=e["time_s"]-tc if e else None
    return evidence,(signal,tc)


def diagnostic_window(signal,start,end):
    """Keep original clipped quadrature; flag support reaching past intervention."""
    value=integrate(signal,start,end)
    t=signal["time"]
    indices=np.where((t[:-1]<end)&(t[1:]>start))[0]
    used=np.unique(np.concatenate((indices,indices+1))) if len(indices) else np.array([],dtype=int)
    support=signal["joint_support_stamps"][used] if len(used) else np.array([])
    latest=max(float(np.max(t[used])),float(np.max(support))) if len(used) and np.isfinite(support).all() else None
    return dict(metric=value,latest_sensor_support_s=latest,
        all_support_precedes_intervention=bool(latest is not None and latest<end),
        qualification="Boundary-clipped offline quadrature can use a later GT/joint support; not automatically a causal negative control")


def analyze(bundle,run,output,*,bundle_validator=None):
    (bundle_validator or validate)(bundle)
    output.mkdir(parents=True,exist_ok=False)
    path=run/"ledger.json";before=sha(path)
    ledger=json.loads(path.read_text())
    if ledger.get("dry_run"):
        raise ValueError("Synthetic executor ledger is not simulation data")
    protocol=json.loads((bundle/"protocol.json").read_text())
    slots=ledger["slots"];answer=report(protocol,slots);signals={};timings={}
    for slot in slots:
        try:
            evidence,data=timing(slot)
            if data is not None:signals[slot["attempt"]]=data
        except (OSError,ValueError,KeyError,TypeError,StopIteration) as error:
            evidence=dict(available=False,reason=f"{type(error).__name__}: {error}")
        timings[slot["attempt"]]=evidence
    pre=[]
    for seed in SEEDS:
        for repeat in (1,2):
            arms={s["arm"]:s for s in slots if s["seed"]==seed and s["repeat"]==repeat}
            for candidate,reference in CONTRASTS:
                selected=[arms.get(a) for a in (reference,candidate)]
                delays=[timings[s["attempt"]].get("execution_after_contact_s") for s in selected if s and s["arm"]!="full"]
                bound=min(delays) if delays and all(d is not None and d>0 for d in delays) else None
                values={}
                for s in selected:
                    data=signals.get(s["attempt"]) if s else None
                    values[s["arm"] if s else "missing"]=diagnostic_window(data[0],data[1],data[1]+bound) if data and bound else None
                offsets={s["arm"]:timings[s["attempt"]].get("execution_after_contact_s") for s in selected if s}
                fast=offsets.get(candidate);ref=offsets.get(reference)
                pre.append(dict(seed=seed,repeat=repeat,candidate=candidate,reference=reference,
                    end_offset_s=bound,windows=values,command_execution_offsets_s=offsets,
                    candidate_minus_reference_command_offset_s=fast-ref if fast is not None and ref is not None else None,
                    qualification="Same contact-relative duration before EITHER intervention, not identical contact state; check sensor supports before treating as negative control"))
    answer.update(timing=timings,preintervention_pairs=pre)
    if sha(path)!=before:raise ValueError("Ledger changed during analysis")
    write(output/"report.json",answer)
    (output/"REPORT.md").write_text("# Cadence descriptive report\n\nNo H2 decision or threshold application.\n\n"
        +json.dumps(answer["counts"],indent=2)+"\n\nSee report.json for every assigned attempt, null-preserving contrasts, sampling sensitivity, pre-intervention windows and causal timing snapshots.\n")
    return answer["counts"]


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("bundle","run","output"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(analyze(a.bundle,a.run,a.output),indent=2))
