#!/usr/bin/env python3
"""Offline review of the bounded delay experiment; no rescore or simulation."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from audit_governor_height_screen import mechanism
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from nino_rl.slip_reporting import integrate


def write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def ratio(candidate,reference):
    return candidate/reference if candidate is not None and reference is not None and reference>0 else None


def metrics(row):
    result={k:row[k] for k in ("time_s","physical_rmse_m","whole_vertical_rms","whole_vertical_peak")}
    result["crossing_vertical_rms"]=row["crossing_vertical"]["rms"]
    for grid in ("gt_native","primary","shifted"):
        for key,window,field in (("whole_slip_rms","whole_route","rms"),
                                 ("crossing_slip2_per_m","crossing","slip_square_per_m")):
            result[grid+"_"+key]=row[grid][window][field]
    return result


def timing(row):
    case=Path(row["case"])
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    controls=list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))
    drive=list(csv.DictReader(next(evaluation.glob("episode-*/drive_trace.csv")).open()))
    events={}
    for c in controls:
        if int(c["governor_events"]) and c["governor_trigger_time_s"]:
            event=events.setdefault(c["governor_events"],dict(trigger_time_s=float(c["governor_trigger_time_s"]),
                brake_onset_time_s=None,pending_input_times_s=[],pending_hold_seconds=[],pending_scales=[],
                first_recorded_event_scale=float(c["governor_scale"])))
            if c["governor_brake_onset_time_s"]:
                event["brake_onset_time_s"]=float(c["governor_brake_onset_time_s"])
            if c["governor_phase"]=="DELAY":
                event["pending_input_times_s"].append(float(c["governor_input_time_s"]))
                event["pending_hold_seconds"].append(float(c["governor_hold_seconds"]))
                event["pending_scales"].append(float(c["governor_scale"]))
    tc=row["first_contact_s"]
    for event in events.values():
        onset=event["brake_onset_time_s"]
        event["observed_delay_s"]=onset-event["trigger_time_s"] if onset is not None else None
        event["trigger_after_first_manifold_s"]=event["trigger_time_s"]-tc
        event["brake_after_first_manifold_s"]=onset-tc if onset is not None else None
        reduced=next((d for d in drive if onset is not None and float(d["sim_time_s"])>=onset-1e-9
                      and float(d["executed_linear_m_s"])<.395),None)
        event["first_reduced_drive_feedback_s"]=float(reduced["sim_time_s"]) if reduced else None
        event["drive_command_received_sim_s"]=float(reduced["command_received_sim_s"]) if reduced else None
        driven=[t for c,t in row["mechanism"]["first_manifold_by_component_after_first_s"].items()
                   if c in ("left_wheel","right_wheel")]
        event["first_driven_manifold_after_first_s"]=min(driven) if driven else None
        event["command_lead_before_first_driven_manifold_s"]=tc+min(driven)-onset if driven and onset is not None else None
    expected=.2 if row["arm"]=="delayed_200ms" else 0.
    passed=(not events if row["arm"]=="full" else bool(events) and all(
        e["observed_delay_s"] is not None and abs(e["observed_delay_s"]-expected)<1e-8
        and (expected==0. or len(e["pending_input_times_s"])==2
             and all(v==0. for v in e["pending_hold_seconds"])) for e in events.values()))
    return dict(passed=bool(passed),expected_delay_s=expected,events=events,
        qualification="Input boundaries and native drive feedback; contact-induced body deceleration is not identified as isolated motor response.")


def paired_phase_audit(arms):
    """Use delayed-arm phase boundaries, align references to their own contact."""
    candidate=arms["delayed_200ms"]
    tc=candidate["first_contact_s"]
    case=Path(candidate["case"])
    controls=list(csv.DictReader(next(case.glob("evaluation/*/episode-*/control_trace.csv")).open()))
    end=min(r["clearance_s"]-r["first_contact_s"] for r in arms.values())
    if end<=.05:return dict(available=False,reason="no common crossing window")
    cuts=[.05]+[float(c["governor_input_time_s"])-tc for c in controls
                  if .05<float(c["governor_input_time_s"])-tc<end]+[end]
    labels=[]
    for a in cuts[:-1]:
        c=next(c for c in reversed(controls) if float(c["governor_input_time_s"])<=tc+a+1e-9)
        phase=c["governor_phase"].lower()
        if phase=="hold":phase="braking" if float(c["governor_scale"])>.900001 else "holding"
        labels.append("event_"+c["governor_events"]+"_"+phase)
    result={}
    for arm,row in arms.items():
        case=Path(row["case"])
        evaluation=next(case.glob("evaluation/*/summary.json")).parent
        logger=next(case.glob("contact/*/metadata.json")).parent
        data=load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=row["seed"],profile=row["profile"]))
        signal=gt_timestamp_series(data)
        origin=row["first_contact_s"]
        phases={}
        coverage=True
        for name,a,b in zip(labels,cuts,cuts[1:]):
            m=integrate(signal,origin+a,origin+b)
            coverage &= m["available"]
            phase=phases.setdefault(name,dict(duration_s=0.,slip_square_integral_s=0.,distance_m=0.))
            phase["duration_s"]+=b-a
            phase["slip_square_integral_s"]+=m["slip_square_integral_s"]
            phase["distance_m"]+=m["distance_m"]
        for phase in phases.values():
            phase["rms"]=math.sqrt(phase["slip_square_integral_s"]/phase["duration_s"])
            phase["slip_square_per_m"]=phase["slip_square_integral_s"]/phase["distance_m"] if phase["distance_m"]>.01 else None
        whole=integrate(signal,origin+cuts[0],origin+cuts[-1])
        total=sum(p["slip_square_integral_s"] for p in phases.values())
        result[arm]=dict(phases=phases,common_window=whole,phase_sum_s=total,
            coverage_pass=bool(coverage),conservation_pass=abs(total-whole["slip_square_integral_s"])<1e-12)
    return dict(available=True,boundaries_s=cuts,segment_labels=labels,arms=result,
        qualification="GT native timestamps; candidate command-phase boundaries translated to each reference's own first manifold, retaining all re-triggers. Secondary diagnostic, not replacement scoring or causal intervention from identical state.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    rows=json.loads((args.run/"episodes.json").read_text())
    for row in rows:
        if row.get("reporting_pass"):
            row["mechanism"]=mechanism(row)
            row["delay_timing"]=timing(row)
    pairs=[]
    phases=[]
    for seed in (77320,77321):
        arms={r["arm"]:r for r in rows if r["seed"]==seed}
        if set(arms)!={"full","frozen_reactive","delayed_200ms"} or not all(r.get("reporting_pass") for r in arms.values()):
            pairs.append(dict(seed=seed,available=False,attempted_arms=list(arms)))
            continue
        for reference in ("full","frozen_reactive"):
            c,b=metrics(arms["delayed_200ms"]),metrics(arms[reference])
            ratios={k:ratio(c[k],b[k]) for k in c}
            pairs.append(dict(seed=seed,reference=reference,available=True,ratios=ratios,
                crossing_slip_grid_ranking_reversal=(ratios["primary_crossing_slip2_per_m"]-1)*(ratios["shifted_crossing_slip2_per_m"]-1)<0))
        phases.append(dict(seed=seed,**paired_phase_audit(arms)))
    aggregate={}
    if len(rows)==6 and all(r.get("reporting_pass") for r in rows):
        for arm in ("full","frozen_reactive","delayed_200ms"):
            selected=[r for r in rows if r["arm"]==arm]
            aggregate[arm]={key:statistics.mean(r[key] for r in selected) for key in ("time_s","physical_rmse_m")}
        for arm in ("frozen_reactive","delayed_200ms"):
            a,b=aggregate[arm],aggregate["full"]
            a.update(mean_time_ratio=a["time_s"]/b["time_s"],mean_tracking_ratio=a["physical_rmse_m"]/b["physical_rmse_m"])
            a["existing_time_tracking_gates_pass"]=a["mean_time_ratio"]<=1.05 and a["mean_tracking_ratio"]<=1.05 and a["time_s"]<=18.5
    complete=len(rows)==6 and len(pairs)==4 and all(p["available"] for p in pairs)
    directional=complete and all(p["ratios"]["crossing_vertical_rms"]<=1.
        and p["ratios"]["gt_native_crossing_slip2_per_m"]<=1.
        and min(p["ratios"]["crossing_vertical_rms"],p["ratios"]["gt_native_crossing_slip2_per_m"])<1. for p in pairs)
    timing_pass=all(r.get("delay_timing",{}).get("passed",False) for r in rows)
    gates=bool(aggregate.get("delayed_200ms",{}).get("existing_time_tracking_gates_pass"))
    decision=dict(status="incomplete_or_reporting_failure_no_retry" if not complete else
        "favorable_direction_needs_separate_confirmation" if directional and timing_pass and gates else
        "reject_200ms_delay_for_tested_scope_no_further_sweep",
        attempts=len(rows),timing_pass=timing_pass,complete=complete,both_seed_directional_benefit=bool(directional),
        existing_time_tracking_gates_pass=gates,aggregate=aggregate,
        qualification="Two seed blocks, one run per arm/block; no causal or significance claim, no exclusion of spikes/failures, not hardware validation.",
        optuna_started=False,training_started=False,predictor_started=False,extra_episodes=False)
    write(out/"episodes.json",rows)
    write(out/"comparisons.json",pairs)
    write(out/"phase_slip.json",phases)
    write(out/"decision.json",decision)
    print(json.dumps(dict(decision=decision,pairs=pairs),indent=2))


if __name__=="__main__":main()
