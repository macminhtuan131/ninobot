#!/usr/bin/env python3
"""Read-only H2 decision engine. No ROS, subprocess, simulator or score writes."""
import argparse
import bisect
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np

from prepare_governor_h2_protocol import ROOT, application_issues, sha, validate_bundle, validate_schedule, write

METRICS=("post_slip","post_vibration","whole_slip","whole_vibration","native_slip",
         "time","tracking","sequence_slip","sequence_vibration","grid_slip","shifted_slip",
         "post_peak","whole_peak","post_slip_integral","post_distance","crossing_slip","crossing_vibration")
PRIMARY={"postcontact_GT_slip_square_per_m":"post_slip","postcontact_vertical_sample_rms_m_s2":"post_vibration"}
UNITS=dict(post_slip="s/m",post_vibration="m/s²",whole_slip="dimensionless",whole_vibration="m/s²",
    native_slip="dimensionless",time="s",tracking="m",sequence_slip="s/m",sequence_vibration="m/s²",
    grid_slip="s/m",shifted_slip="s/m",post_peak="m/s²",whole_peak="m/s²",post_slip_integral="s",
    post_distance="m",crossing_slip="s/m",crossing_vibration="m/s²")
BOOTSTRAP_SEED=20261018
BOOTSTRAP_DRAWS=10000
EPS=1e-12  # floating-point comparisons only; not a noninferiority margin


def finite(value):
    try:
        v=float(value)
        return v if not isinstance(value,bool) and math.isfinite(v) and v>=0 else None
    except (ValueError,TypeError):
        return None


def nested(value,*keys):
    for key in keys:
        if not isinstance(value,dict):return None
        value=value.get(key)
    return value


def extract_metrics(result):
    quality=result.get("quality") or {};old=quality.get("existing_reports") or {}
    post=quality.get("postcontact") or {};seq=nested(old,"sequence","metrics","whole_contact_sequence") or {}
    def observed(part,key):
        return finite(part.get(key)) if isinstance(part,dict) and part.get("available") is True else None
    return dict(post_slip=observed(post.get("GT_slip"),"slip_square_per_m"),
        post_vibration=observed(post.get("vertical"),"rms"),
        whole_slip=observed(nested(old,"gt_native","whole_route"),"rms"),
        whole_vibration=finite(old.get("whole_vertical_rms")),native_slip=finite(old.get("native_slip_rms")),
        time=finite(old.get("time_s")),tracking=finite(old.get("physical_rmse_m")),
        sequence_slip=observed(seq.get("slip"),"slip_square_per_m"),sequence_vibration=observed(seq.get("vertical"),"rms"),
        grid_slip=observed(post.get("grid20ms"),"slip_square_per_m"),shifted_slip=observed(post.get("shifted10ms"),"slip_square_per_m"),
        post_peak=observed(post.get("vertical"),"peak"),whole_peak=finite(old.get("whole_vertical_peak")),
        post_slip_integral=observed(post.get("GT_slip"),"slip_square_integral_s"),post_distance=observed(post.get("GT_slip"),"distance_m"),
        crossing_slip=observed(nested(old,"gt_native","crossing"),"slip_square_per_m"),
        crossing_vibration=observed(old.get("crossing_vertical"),"rms"))


def normalize(protocol,slots,evidence):
    """Never pair by seed alone, silently drop duplicates, or invent native outcomes."""
    validate_schedule(protocol["schedule"])
    structural=[];expected=protocol["schedule"]
    if not isinstance(slots,list):slots=[];structural.append("ledger_slots_not_a_list")
    if any(not isinstance(r,dict) for r in slots):
        structural.append("ledger_contains_non_object_slots");slots=[r for r in slots if isinstance(r,dict)]
    if len(slots)!=16:structural.append("ledger_must_retain_all_16_assigned_slots")
    if [r.get("attempt") for r in slots]!=list(range(1,17)):
        structural.append("ledger_attempt_order_or_uniqueness_invalid")
    rows=[]
    for job in expected:
        matches=[r for r in slots if r.get("attempt")==job["attempt"]]
        row=matches[0] if len(matches)==1 else {}
        identity=all(row.get(k)==v for k,v in job.items())
        if not identity:structural.append(f"slot_{job['attempt']}_identity_missing_or_wrong")
        r=row.get("result") if identity else None
        r=r if isinstance(r,dict) else {}
        if r and (r.get("seed"),r.get("profile"))!=(job["seed"],job["profile"]):
            structural.append(f"slot_{job['attempt']}_child_identity_wrong");r={}
        if r and ((r.get("physical_success") is not None and type(r["physical_success"]) is not bool)
                  or (r.get("physical_success") is True and r.get("termination")!="success")):
            structural.append(f"slot_{job['attempt']}_inconsistent_native_outcome")
        sequence=nested(r,"quality","existing_reports","sequence") or {}
        rows.append(dict(**job,status=row.get("status","missing"),identity_valid=identity,
            physical_success=r.get("physical_success"),stop_pass=r.get("stop_pass"),termination=r.get("termination"),
            metrics=extract_metrics(r),result_flags={k:r.get(k) for k in
                ("setup_pass","provenance_pass","measurement_integrity_pass","physical_state_valid","cleanup_confirmed","quality_available")},
            runner_exit=r.get("runner_exit"),approach=sequence.get("approach"),
            timing=evidence.get(job["attempt"],dict(available=False,reason="timing_evidence_unavailable")),
            native_outcome=deepcopy(r.get("native_outcome")),error=row.get("error") or r.get("collection_error")))
    return rows,structural


def paired_metrics(rows):
    pairs=[]
    for seed in (77500,77501):
        for repeat in range(1,5):
            selected={r["profile"]:r for r in rows if r["seed"]==seed and r["repeat"]==repeat}
            metrics={}
            for key in METRICS:
                p,g=(selected[arm]["metrics"][key] for arm in ("full","reactive"))
                metrics[key]=dict(full=p,reactive=g,delta=g-p if p is not None and g is not None else None,
                    relative_benefit=1-g/p if p is not None and p>0 and g is not None else None)
            pairs.append(dict(seed=seed,repeat=repeat,pair_id=f"seed_{seed}_repeat_{repeat}",
                attempts={arm:selected[arm]["attempt"] for arm in selected},metrics=metrics))
    return pairs


def estimate(pairs):
    """Same intact-pair bootstrap draws for every metric; fixed seeds, not terrain inference."""
    rng=np.random.default_rng(BOOTSTRAP_SEED)
    indices=rng.integers(0,4,size=(2,BOOTSTRAP_DRAWS,4))
    output={}
    for key in METRICS:
        blocks={};delta_draws=[];benefit_draws=[]
        for index,seed in enumerate((77500,77501)):
            selected=[p for p in pairs if p["seed"]==seed]
            observed=[p["metrics"][key] for p in selected]
            available=sum(m["full"] is not None and m["reactive"] is not None for m in observed)
            entry=dict(available_pairs=available,expected_pairs=4,available=available==4,
                full_mean=None,reactive_mean=None,mean_delta=None,relative_benefit=None,
                delta_CI95=None,benefit_CI95=None,undefined_bootstrap_denominators=None)
            if available==4:
                a=np.array([m["full"] for m in observed]);b=np.array([m["reactive"] for m in observed])
                da=a[indices[index]].mean(axis=1);db=b[indices[index]].mean(axis=1)
                delta=db-da
                entry.update(full_mean=float(a.mean()),reactive_mean=float(b.mean()),mean_delta=float((b-a).mean()),
                    delta_CI95=np.percentile(delta,[2.5,97.5]).tolist(),
                    relative_benefit=float(1-b.mean()/a.mean()) if a.mean()>0 else None,
                    undefined_bootstrap_denominators=int(np.sum(da<=0)))
                benefit=1-db/da if np.all(da>0) else None
                if benefit is not None:entry["benefit_CI95"]=np.percentile(benefit,[2.5,97.5]).tolist()
                delta_draws.append(delta);benefit_draws.append(benefit)
            else:
                delta_draws.append(None);benefit_draws.append(None)
            blocks[str(seed)]=entry
        aggregate=dict(available=all(b["available"] for b in blocks.values()),full_mean=None,reactive_mean=None,
            mean_delta=None,relative_benefit=None,delta_CI95=None,benefit_CI95=None)
        if aggregate["available"]:
            for field in ("full_mean","reactive_mean","mean_delta"):
                aggregate[field]=sum(b[field] for b in blocks.values())/2
            aggregate["delta_CI95"]=np.percentile((delta_draws[0]+delta_draws[1])/2,[2.5,97.5]).tolist()
            if all(b["relative_benefit"] is not None for b in blocks.values()):
                aggregate["relative_benefit"]=sum(b["relative_benefit"] for b in blocks.values())/2
            if all(b is not None for b in benefit_draws):
                aggregate["benefit_CI95"]=np.percentile((benefit_draws[0]+benefit_draws[1])/2,[2.5,97.5]).tolist()
        output[key]=dict(unit=UNITS[key],blocks=blocks,aggregate=aggregate)
    return output


def approach_check(approach):
    if not isinstance(approach,dict):return None
    try:
        def maximum(key):return max(abs(approach[key]["minimum"]),abs(approach[key]["maximum"]))
        values=[approach[k][s] for k in ("v","y","yaw","roll","pitch") for s in ("minimum","maximum","median")]
        if not all(math.isfinite(v) for v in values):return None
        return bool(approach["v"]["minimum"]>=.39 and approach["v"]["maximum"]<=.41 and
            maximum("y")<=.01 and maximum("yaw")<=math.radians(2) and
            max(maximum("roll"),maximum("pitch"))<=math.radians(2) and approach["coverage_fraction"]>=.98)
    except (KeyError,TypeError):return None


def approach_pairs(rows):
    individual=[approach_check(r["approach"]) for r in rows];pairs=[]
    for seed in (77500,77501):
        for repeat in range(1,5):
            chosen={r["profile"]:r["approach"] for r in rows if r["seed"]==seed and r["repeat"]==repeat}
            try:
                a,b=chosen["full"],chosen["reactive"]
                dv=abs(a["v"]["median"]-b["v"]["median"]);dy=abs(a["y"]["median"]-b["y"]["median"])
                yaw=a["yaw"]["median"]-b["yaw"]["median"];dyaw=abs(math.atan2(math.sin(yaw),math.cos(yaw)))
                pairs.append(dict(seed=seed,repeat=repeat,dv_m_s=dv,dy_m=dy,dyaw_rad=dyaw,
                    passed=bool(all(math.isfinite(x) for x in (dv,dy,dyaw)) and dv<=.005 and dy<=.005 and dyaw<=math.radians(1))))
            except (TypeError,KeyError):pairs.append(dict(seed=seed,repeat=repeat,passed=None))
    passed=True if all(v is True for v in individual) and all(p["passed"] is True for p in pairs) else None
    return dict(passed=passed,individual=individual,pairs=pairs,
        qualification="A failed/missing caliper invalidates a clean postcontact comparison; do not exclude or replace the episode.")


def evaluate(protocol,slots,criteria,evidence=None,source_kind="synthetic",context_issues=()):
    rows,structure=normalize(protocol,slots,evidence or {})
    pairs=paired_metrics(rows);estimates=estimate(pairs);approach=approach_pairs(rows)
    issues=list(context_issues)+structure
    if criteria.get("status")!="confirmed" or application_issues(criteria):
        issues.append("criteria_not_confirmed_or_complete")
    if source_kind!="synthetic" and criteria.get("synthetic_only"):
        issues.append("synthetic_criteria_cannot_validate_a_real_batch")
    gates={};reasons={}
    def gate(name,value,reason):gates[name]=value;reasons[name]=reason
    complete=all(r["status"]=="collected" for r in rows)
    gate("complete_16",True if complete else None,"All16 slots must be collected without hard-stop/error/unattempted slots")
    known_failure=any(r["identity_valid"] and (r["physical_success"] is False or r["stop_pass"] is False) for r in rows)
    arrival=False if known_failure else True if all(r["physical_success"] is True and r["stop_pass"] is True for r in rows) else None
    gate("physical_arrival_and_stop",arrival,"Every arm must have8/8 physical arrivals and observed stable2s stops; retain known failures")
    good_flags=all(all(v is True for v in r["result_flags"].values()) and r["runner_exit"]==0 for r in rows)
    gate("measurement_and_provenance",True if good_flags else None,"Invalid/missing integrity is not evidence of performance benefit or harm")
    metrics_present=all(all(v is not None for v in r["metrics"].values()) for r in rows)
    gate("required_metrics_present",True if metrics_present else None,"No missing/nonfinite metric is zero-filled or dropped from the decision population")
    gate("approach_comparable",approach["passed"],"No failed caliper exclusion; preserve both blocks and all pairs")
    timing=[];precontact=False
    for row in rows:
        e=row["timing"]
        if e.get("precontact_reduction") is True:precontact=True
        if row["profile"]=="reactive":
            timing.append(e.get("timing_pass") if e.get("available") is True else None)
    authority=None if precontact or any(v is None for v in timing) else all(v is True for v in timing)
    gate("executed_intervention_before_next_contact",authority,"Every reactive run needs measured command/target reduction before a subsequent loaded contact and body/joint evidence; precontact intervention invalidates isolation")
    selected=PRIMARY.get(criteria.get("primary_metric"));minimum=finite(criteria.get("minimum_relative_improvement"));extra=finite(criteria.get("maximum_added_route_seconds"))
    p=estimates.get(selected,{})
    aggregate=p.get("aggregate",{});ci=aggregate.get("benefit_CI95")
    primary=None
    if ci is not None and minimum is not None:
        points=[b["relative_benefit"] for b in p["blocks"].values()]
        if ci[1]<minimum-EPS:primary=False
        elif ci[0]>=minimum-EPS and all(v is not None and v>=minimum-EPS for v in points):primary=True
    gate("worthwhile_primary_benefit",primary,"Both block point benefits and aggregate lower95% bound must meet the prespecified minimum; overlap gives inconclusive")
    secondary="post_vibration" if selected=="post_slip" else "post_slip"
    keys=(secondary,"whole_slip","whole_vibration")
    all_secondary=all(b["available"] for k in keys for b in estimates[k]["blocks"].values())
    no_harm=all(b["mean_delta"]<=EPS for k in keys for b in estimates[k]["blocks"].values()) if all_secondary else None
    gate("secondary_and_whole_route_no_worsening",no_harm,"Point-estimate nonworsening per block; a failed point gate is not a claim of statistically proven harm")
    sequence=estimates["sequence_slip" if selected=="post_slip" else "sequence_vibration"]
    seqbenefits=[b["relative_benefit"] for b in sequence["blocks"].values()]
    gate("complete_contact_sequence_same_direction",all(v>EPS for v in seqbenefits) if all(v is not None for v in seqbenefits) else None,
        "Do not dilute a longer contact sequence into a favorable fixed-window-only conclusion")
    caps=[]
    for seed in ("77500","77501"):
        t,q=estimates["time"]["blocks"][seed],estimates["tracking"]["blocks"][seed]
        caps.append(t["reactive_mean"]<=18.5+EPS and t["reactive_mean"]<=1.05*t["full_mean"]+EPS and
                    q["reactive_mean"]<=1.05*q["full_mean"]+EPS if t["available"] and q["available"] else None)
    gate("existing_time_tracking_caps",all(v is True for v in caps) if all(v is not None for v in caps) else None,
        "Each block:mean time<=18.5s and1.05xPI;mean physical RMSE<=1.05xPI")
    tci=estimates["time"]["aggregate"]["delta_CI95"]
    time_gate=None if tci is None or extra is None else True if tci[1]<=extra+EPS else False if tci[0]>extra+EPS else None
    gate("application_added_time",time_gate,"Upper95% added-time bound must fit application seconds; interval crossing limit is inconclusive")
    reversal=[]
    if selected=="post_slip":
        for level in ("77500","77501","aggregate"):
            benefits=[estimates[k]["aggregate"] if level=="aggregate" else estimates[k]["blocks"][level]
                      for k in ("post_slip","grid_slip","shifted_slip")]
            values=[b["relative_benefit"] for b in benefits]
            if all(v is not None for v in values) and min(values)<-EPS and max(values)>EPS:
                reversal.append(dict(level=level,GT_grid20ms_shifted_benefits=values))
        sensitive_missing=any(not estimates[k]["aggregate"]["available"] or estimates[k]["aggregate"]["relative_benefit"] is None for k in ("post_slip","grid_slip","shifted_slip"))
        sampling=None if reversal or sensitive_missing else True
    else:sampling=True if selected is not None else None
    gate("primary_sampling_direction_stable",sampling,"Any primary-slip sign reversal across originalGT/20ms/+10ms makes evidence inconclusive; never select favorable origin")
    if structure or any("inputs_changed" in issue for issue in issues):
        decision="chua_du_bang_chung"
    elif known_failure:
        decision="khong_dat"
    elif issues or not complete or not good_flags or not metrics_present or approach["passed"] is not True or precontact or reversal:
        decision="chua_du_bang_chung"
    elif any(v is False for v in gates.values()):
        decision="khong_dat"
    elif all(v is True for v in gates.values()):
        decision="dat"
    else:decision="chua_du_bang_chung"
    return dict(schema="H2_offline_decision_v1",decision=decision,
        decision_label={"dat":"Đạt","khong_dat":"Không đạt","chua_du_bang_chung":"Chưa đủ bằng chứng"}[decision],
        source_kind=source_kind,synthetic_result_is_not_robot_validation=source_kind=="synthetic",
        issues=issues,gates=gates,gate_reasons=reasons,sampling_reversals=reversal,approach=approach,
        counts=dict(assigned=16,input_ledger_rows=len(slots),attempted=sum(r["status"] not in ("not_attempted","missing") for r in rows),
            physical_failures=sum(r["physical_success"] is False for r in rows),stop_failures=sum(r["stop_pass"] is False for r in rows),
            native_unknown=sum(r["physical_success"] is None for r in rows),
            missing_metric_counts={k:sum(r["metrics"][k] is None for r in rows) for k in METRICS}),
        episodes=rows,pairs=pairs,estimates=estimates,criteria=deepcopy(criteria),
        bootstrap=dict(draws=BOOTSTRAP_DRAWS,seed=BOOTSTRAP_SEED,unit="intact pair resampled within fixed seed",interval="percentile95",small_sample_coverage_not_guaranteed=True),
        recommended_action="Review separate bounded classical tuning budget" if decision=="dat" else "Stop this frozen intervention/small-screen branch; no automatic extra episodes or parameter search",
        automatic_execution=False,simulation_episodes=0,native_scoring_changed=False,
        predictor_started=False,PPO_started=False,optuna_started=False)


def asof(series,t,max_age):
    i=bisect.bisect_right([p[0] for p in series],t+1e-9)-1
    return dict(stamp_s=series[i][0],age_s=max(0.,t-series[i][0]),value=series[i][1]) if i>=0 and t-series[i][0]<=max_age+1e-9 else None


def covered(series,start,end,max_gap):
    times=[t for t,v in series]
    if len(times)<2 or not all(math.isfinite(t) for t in times):return False
    a=max(0,bisect.bisect_right(times,start)-1);b=min(len(times)-1,bisect.bisect_left(times,end))
    return bool(times[a]<=start+1e-9 and times[b]>=end-1e-9 and
                all(0<y-x<=max_gap+1e-9 for x,y in zip(times[a:b+1],times[a+1:b+1])))


def timing_evidence(controls,drive,events,loads,ground,joints,tc,profile):
    """Conservative measured publication-time bound; no future sensor lookup."""
    result=dict(available=False,precontact_reduction=None,timing_pass=None)
    try:
        cs=sorted((float(c["governor_input_time_s"]),c) for c in controls)
        ds=sorted((float(d["sim_time_s"]),d) for d in drive)
        if not cs or not ds:raise ValueError("empty command/drive trace")
        for name,series,gap in (("control",cs,.100001),("drive",ds,.050001),
                                ("body",ground,.040001),("joints",joints,.010001)):
            if not covered(series,tc-.3,tc+3.,gap):raise ValueError("incomplete_or_gapped_"+name+"_timing_support")
        reductions=[(t,c) for t,c in cs if float(c["governor_scale"])<.999999]
        result["precontact_reduction"]=any(t<tc-1e-9 for t,c in reductions)
        if profile=="full":
            return dict(result,available=True,timing_pass=True,precontact_reduction=bool(reductions),reason="PI arm must retain scale1")
        executed=[]
        for t,d in ds:
            received=float(d["command_received_sim_s"])
            if not math.isfinite(received) or received>t+1e-9:raise ValueError("future_or_nonfinite_command_received_stamp")
            c=asof(cs,received,.100001)
            if c is None:continue
            v=float(c["value"]["governor_requested_linear_m_s"]);scale=float(c["value"]["governor_scale"])
            if scale>=.999999 or v<=0:continue
            requested=float(d["requested_linear_m_s"]);actual=float(d["executed_linear_m_s"])
            targets=.0625*(float(d["left_target_rad_s"])+float(d["right_target_rad_s"]))/2
            if abs(requested-v*scale)<=1e-6 and actual<v-1e-6 and targets<v-1e-6 and t>=c["stamp_s"]-1e-9:
                executed.append(dict(time_s=t,command_received_s=received,input_s=c["stamp_s"],requested_v=requested,
                    executed_v=actual,wheel_target_mean_m_s=targets))
        first=next((e for e in executed if e["time_s"]>=tc),None)
        result.update(first_reduced_input_s=reductions[0][0] if reductions else None,first_executed=first)
        if first is None:
            return dict(result,available=True,timing_pass=False,reason="no_measured_postcontact_command_and_target_reduction")
        candidates=[]
        for event in events:
            if event.get("event")!="begin" or not event.get("named_positive_obstacle") or not first["time_s"]<event["time_s"]<=tc+3.:continue
            names=tuple(sorted(event["collisions"]))
            end=min((e["time_s"] for e in events if e.get("event")=="end" and e["component"]==event["component"] and
                tuple(sorted(e["collisions"]))==names and e["time_s"]>=event["time_s"]),default=tc+3.)
            end=min(end,tc+3.)
            loaded=next((c for c in loads if c["component"]==event["component"] and tuple(sorted(c["collisions"]))==names and
                event["time_s"]<=c["time_s"]<=end),None)
            if loaded:candidates.append(dict(manifold=event,loaded=loaded))
        future=min(candidates,key=lambda c:c["manifold"]["time_s"]) if candidates else None
        snapshots={}
        for label,t in (("before_execution",first["time_s"]-.02),("at_execution",first["time_s"]),
                        ("next_loaded_contact",future["loaded"]["time_s"] if future else first["time_s"]+.02)):
            snapshots[label]=dict(body=asof(ground,t,.040001),joints=asof(joints,t,.010001))
        response_available=all(v["body"] is not None and v["joints"] is not None for v in snapshots.values())
        if response_available:
            response_available=all(math.isfinite(v["body"]["value"]["linear"]["x"]) and
                all(math.isfinite(v["joints"]["value"][side+"_wheel_joint"]) for side in ("left","right")) for v in snapshots.values())
        return dict(result,available=response_available,timing_pass=bool(future) if response_available else None,
            next_loaded_contact=future,response_snapshots=snapshots,
            reason="measured_reduction_precedes_new_loaded_manifold" if future else "no_subsequent_new_loaded_manifold_within3s",
            qualification="Drive publication time is a conservative upper bound; body/encoder response is descriptive, not actuator latency or causal benefit by itself")
    except (ValueError,KeyError,TypeError) as error:
        return dict(result,error=f"{type(error).__name__}: {error}")


def read_evidence(row,run_root):
    r=row.get("result") or {};case=Path(r.get("case","")).resolve()
    if not case.is_relative_to(run_root.resolve()):raise ValueError("Case outside selected new batch")
    def single(pattern):
        files=list(case.glob(pattern))
        if len(files)!=1:raise ValueError("Expected one "+pattern)
        return files[0]
    cp=single("evaluation/*/episode-*/control_trace.csv");dp=single("evaluation/*/episode-*/drive_trace.csv")
    ep=single("contact/*/contact_events.jsonl");sp=single("contact/*/samples.jsonl")
    paths=[cp,dp,ep,sp];before={str(p.resolve()):sha(p) for p in paths}
    tc=nested(r,"quality","existing_reports","first_contact_s")
    if tc is None:raise ValueError("First contact unavailable")
    ground={};joints={};loads=[]
    for line in sp.open():
        packet=json.loads(line);d=packet["data"];topic=packet["topic"]
        if "header" not in d:continue
        stamp=d["header"]["stamp"];t=stamp["sec"]+stamp["nanosec"]*1e-9
        if not tc-.4<=t<=tc+3.05:continue
        if topic=="/ground_truth/odom":ground[t]=d["twist"]["twist"]
        elif topic=="/joint_states":joints[t]=dict(zip(d["name"],d["velocity"]))
        elif topic.startswith("/nino/contact_lab/"):
            for contact in d["contacts"]:
                names=[contact[k]["name"] for k in ("collision1","collision2")]
                if not any("cable_bumps" in n for n in names):continue
                loaded=any(depth>0 and math.sqrt(sum(w["body_1_wrench"]["force"][k]**2 for k in ("x","y","z")))>1e-6
                    for depth,w in zip(contact["depths"],contact["wrenches"]))
                if loaded:loads.append(dict(time_s=t,component=topic.rsplit("/",1)[-1],collisions=names))
    events=[json.loads(line) for line in ep.open()]
    evidence=timing_evidence(list(csv.DictReader(cp.open())),list(csv.DictReader(dp.open())),events,
        sorted(loads,key=lambda c:c["time_s"]),sorted(ground.items()),sorted(joints.items()),tc,row["profile"])
    if any(sha(Path(p))!=h for p,h in before.items()):raise ValueError("timing_inputs_changed_while_reading")
    return evidence,before


def analyze_run(bundle,run,criteria_path,output):
    validation=validate_bundle(bundle)
    ledger=run/"ledger.json"
    issues=[]
    manifest={str(p.resolve()):sha(p) for p in (bundle/"protocol.json",ledger,criteria_path) if p.is_file()}
    protocol=json.loads((bundle/"protocol.json").read_text())
    try:
        slots=json.loads(ledger.read_text())["slots"]
        if not isinstance(slots,list) or any(not isinstance(s,dict) for s in slots):raise ValueError("invalid slots")
    except (OSError,ValueError,KeyError,TypeError):slots=[];issues.append("ledger_unavailable_or_malformed")
    try:
        criteria=json.loads(criteria_path.read_text())
        if not isinstance(criteria,dict):raise ValueError("invalid criteria")
    except (OSError,ValueError):criteria={};issues.append("criteria_unavailable_or_malformed")
    snapshot=run/"protocol_snapshot.json"
    if snapshot.is_file():manifest[str(snapshot.resolve())]=sha(snapshot)
    try:
        if json.loads(snapshot.read_text())!=protocol:raise ValueError("different protocol")
    except (OSError,ValueError):issues.append("batch_protocol_snapshot_missing_or_mismatched")
    auth=run/"authorization_snapshot.json"
    if auth.is_file():
        manifest[str(auth.resolve())]=sha(auth)
        try:
            record=json.loads(auth.read_text())
            if not isinstance(record,dict):record={}
        except ValueError:record={}
        if (record.get("application")!=criteria or nested(record,"release","application_sha256")!=sha(criteria_path)
            or nested(record,"release","protocol_sha256")!=sha(bundle/"protocol.json")
            or nested(record,"release","application_confirmed") is not True
            or nested(record,"release","budget_released") is not True
            or nested(record,"release","execution_authorized") is not True
            or nested(record,"release","maximum_attempts")!=16
            or nested(record,"release","execution_dependency_sha256",str(Path(__file__).resolve().relative_to(ROOT)))!=sha(Path(__file__))):
            issues.append("criteria_or_analyzer_not_sealed_in_batch_authorization")
    else:issues.append("batch_authorization_snapshot_missing")
    evidence={}
    for row in slots:
        if row.get("status")=="not_attempted" or not row.get("result"):continue
        try:
            evidence[row["attempt"]],hashes=read_evidence(row,run);manifest.update(hashes)
        except (ValueError,KeyError,OSError,TypeError) as error:
            evidence[row.get("attempt")]=dict(available=False,reason=f"{type(error).__name__}: {error}")
    changed=[p for p,h in manifest.items() if sha(Path(p))!=h]
    if changed:issues.append("inputs_changed_while_analyzing")
    report=evaluate(protocol,slots,criteria,evidence,source_kind="new_batch",context_issues=issues)
    output.mkdir(parents=True,exist_ok=False)
    write(output/"report.json",report);write(output/"input_sha256.json",manifest)
    changed=[p for p,h in manifest.items() if sha(Path(p))!=h]
    if changed:
        report=evaluate(protocol,slots,criteria,evidence,source_kind="new_batch",context_issues=issues+["inputs_changed_while_writing_report"])
        write(output/"report.json",report)
    validate_bundle(bundle)
    write(output/"verification.json",dict(input_files=len(manifest),changed_inputs=changed,protocol_validation=validation,
        simulation_episodes=0,native_scoring_changed=False))
    (output/"REPORT.md").write_text(markdown_report(report))
    return report


def markdown_report(report):
    def number(value):return "Không khả dụng" if value is None else f"{value:.6g}"
    def interval(values):return "Không khả dụng" if values is None else "["+", ".join(number(v) for v in values)+"]"
    labels={True:"Đạt",False:"Không đạt",None:"Chưa xác định"}
    lines=[f"# H2: {report['decision_label']}","",f"Nguồn: **{report['source_kind']}**. Analyzer chạy **0 simulation episodes**.",""]
    if report["source_kind"]=="synthetic":lines += ["**DỮ LIỆU TỔNG HỢP — không phải kết quả robot, chấp nhận tiêu chí hoặc cấp ngân sách.**",""]
    counts=report["counts"]
    lines += [f"Assigned: {counts['assigned']}; attempted: {counts['attempted']}; physical failures: {counts['physical_failures']}; stop failures: {counts['stop_failures']}; native unknown: {counts['native_unknown']}.","",
        "## Gates","","| Gate | Kết luận |","|---|---|"]
    lines += [f"| {name} | {labels[value]} |" for name,value in report["gates"].items()]
    lines += ["","## Metric và bất định","","Delta = governor − PI; benefit >0 là giảm metric, chỉ có lợi theo ngữ cảnh của metric. Không lấy benefit thời gian/tracking làm objective mới.","",
        "| Metric | Block | PI mean | Governor mean | Delta | CI95 delta | Benefit | CI95 benefit |",
        "|---|---|---:|---:|---:|---|---:|---|"]
    for key in ("post_slip","post_vibration","whole_slip","whole_vibration","time","tracking","sequence_slip","sequence_vibration"):
        m=report["estimates"][key]
        for name in ("77500","77501","aggregate"):
            b=m["aggregate"] if name=="aggregate" else m["blocks"][name]
            lines.append(f"| {key} ({m['unit']}) | {name} | {number(b['full_mean'])} | {number(b['reactive_mean'])} | {number(b['mean_delta'])} | {interval(b['delta_CI95'])} | {number(b['relative_benefit'])} | {interval(b['benefit_CI95'])} |")
    lines += ["","Benefit được ghi theo fraction (0.1 = 10%). Khoảng bootstrap n=4 cặp/block không bảo đảm coverage danh nghĩa hoặc đại diện quần thể địa hình.","",
        "## Tám cặp đã phân công","","| Pair | PI attempt | Governor attempt | Delta slip²/m | Delta time (s) |","|---|---:|---:|---:|---:|"]
    for p in report["pairs"]:
        lines.append(f"| {p['pair_id']} | {p['attempts']['full']} | {p['attempts']['reactive']} | {number(p['metrics']['post_slip']['delta'])} | {number(p['metrics']['time']['delta'])} |")
    lines += ["","## Giới hạn / quyết định","",report["recommended_action"],"",
        "Không zero-impute missing/censored, không chọn subset success, không gộp seed cũ, không tự chạy thêm hoặc mở Optuna/PPO/predictor.","",
        "Một gate point-estimate không đạt không tự chứng minh tác hại có ý nghĩa thống kê. Không đạt/chưa đủ bằng chứng không phủ định H2 cho mọi controller.",""]
    lines += ["- "+str(issue) for issue in report["issues"]]
    return "\n".join(lines)+"\n"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol",required=True,type=Path);parser.add_argument("--batch",required=True,type=Path)
    parser.add_argument("--criteria",type=Path);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    report=analyze_run(args.protocol.resolve(),args.batch.resolve(),args.criteria or args.protocol/"application_requirements.json",args.output)
    print(json.dumps(dict(decision=report["decision"],label=report["decision_label"],issues=report["issues"]),ensure_ascii=False))


if __name__=="__main__":main()
