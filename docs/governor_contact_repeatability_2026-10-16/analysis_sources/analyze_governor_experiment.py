#!/usr/bin/env python3
"""Summarize causal timestamps/coverage from saved governor logs, no simulation."""
import argparse
import csv
import json
from math import hypot
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl")]
from nino_control.governor_core import quaternion_rpy,vertical_acceleration
from nino_rl.core import load_config


def identity(row):
    episode=row.get("episode")
    if isinstance(episode,dict):
        return (str(episode["run_id"])+":"+str(episode["attempt"])
                if episode.get("run_id") else episode.get("attempt"))
    return episode


def stamp(data):
    time=data["header"]["stamp"]
    return time["sec"]+time["nanosec"]*1e-9


def energy(samples,start,end,maximum_gap_s=.1):
    selected=np.array([(t,v) for t,v in samples if start<=t<=end],dtype=float)
    if len(selected)<2:
        return dict(available=False,reason="insufficient_samples",rms=None,peak=None,coverage_s=0.)
    selected=selected[np.argsort(selected[:,0])]
    duration=float(selected[-1,0]-selected[0,0])
    if duration<=0:
        return dict(available=False,reason="zero_duration",rms=None,peak=None,coverage_s=0.)
    intervals=np.diff(selected[:,0])
    valid=(intervals>0)&(intervals<=maximum_gap_s)
    covered=float(sum(intervals[valid]))
    if covered<=0:
        return dict(available=False,reason="missing_intervals",rms=None,peak=None,coverage_s=0.)
    integral=float(sum((selected[i,1]**2+selected[i-1,1]**2)*.5*intervals[i-1]
                       for i in range(1,len(selected)) if valid[i-1]))
    coverage=covered/(end-start)
    return dict(available=coverage>=.8,reason=None if coverage>=.8 else "partial_window",
        rms=float(np.sqrt(integral/covered)),peak=float(np.max(np.abs(selected[:,1]))),
        coverage_s=covered,coverage_fraction=float(coverage),maximum_gap_s=maximum_gap_s)


def analyze(evaluation,logger,horizon=2.):
    evaluation,logger=Path(evaluation),Path(logger)
    config=load_config(evaluation/"config.yaml")
    metadata=json.loads((logger/"metadata.json").read_text())
    with (evaluation/"episodes.csv").open() as stream:
        outcomes=list(csv.DictReader(stream))
    episodes={}
    imu={}
    body={}
    states={}
    for line in (logger/"samples.jsonl").open():
        try:
            row=json.loads(line)
        except ValueError:
            continue  # Partial last write remains unavailable, not zero.
        topic,data=row["topic"],row["data"]
        eid=identity(row)
        if eid is None:
            continue
        if topic=="/nino/governor/episode":
            episodes.setdefault(eid,{})[data["event"]]=data
        elif topic=="/nino/governor/state":
            states.setdefault(eid,[]).append(data)
        elif topic=="/imu/data":
            try:
                q=data["orientation"]
                roll,pitch,_=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
                acc=data["linear_acceleration"]
                vertical=vertical_acceleration(tuple(acc[k] for k in ("x","y","z")),roll,pitch,
                    config["policy_v2"]["imu_includes_gravity"])
                imu.setdefault(eid,[]).append((stamp(data),vertical))
            except (ValueError,TypeError):
                pass
        elif topic=="/ground_truth/odom":
            body.setdefault(eid,[]).append((stamp(data),data["twist"]["twist"]["linear"]["x"]))
    contacts={}
    for line in (logger/"contact_events.jsonl").open():
        row=json.loads(line)
        if row.get("named_positive_obstacle") and row["event"]=="begin":
            contacts.setdefault(identity(row),[]).append(row)
    results=[]
    for outcome in outcomes:
        attempt=int(outcome["attempt"])
        eid=(outcome["governor_run_id"]+":"+str(attempt) if outcome.get("governor_run_id") else attempt)
        lifecycle=episodes.get(eid,{})
        start=lifecycle.get("reset",{}).get("time_s")
        end=lifecycle.get("end",{}).get("time_s")
        candidate_contacts=[r for r in contacts.get(eid,[]) if start is not None and end is not None
                            and start<=r["time_s"]<=end]
        first=min(candidate_contacts,key=lambda r:r["time_s"]) if candidate_contacts else None
        holds=[r["time_s"] for r in states.get(eid,[]) if r.get("governor_phase",r.get("phase"))=="HOLD"]
        begin=min(holds) if holds else None
        row=dict(attempt=attempt,run_id=outcome.get("governor_run_id"),seed=int(outcome["seed"]),success=outcome["success"].lower()=="true",
            termination=outcome["termination"],time_seconds=float(outcome["time_seconds"]),
            truth_endpoint_error_m=float(outcome["truth_endpoint_error_m"]),
            governor_events=int(outcome.get("governor_events",0)),
            first_recorded_positive_contact=first,
            first_hold_time_s=begin,
            contact_to_hold_s=begin-first["time_s"] if first and begin is not None else None,
            post_contact_acceleration=None,body_slowdown_time_s=None)
        if first:
            t=first["time_s"]
            row["post_contact_acceleration"]=energy(imu.get(eid,[]),t,t+horizon)
            speeds=body.get(eid,[])
            approach=[abs(v) for when,v in speeds if t-.5<=when<t]
            if approach:
                v0=float(np.median(approach))
                slower=[when for when,v in speeds if t<=when<=t+horizon and abs(v)<=.9*v0]
                row["approach_body_speed_m_s"]=v0
                row["body_slowdown_time_s"]=min(slower) if slower else None
        results.append(row)
    return dict(schema_version=1,qualification="Timing/coverage associations, not causal benefit or sim-to-real proof",
        failures_retained=True,horizon_seconds=horizon,logger_closed=metadata.get("complete",False),
        instrumented_components=metadata.get("contact_components","legacy_four_wheels"),
        missing_contact="Unavailable; absence of a message is not proof of no contact",
        physical_slip="Use saved independently scored episodes.csv; wheel error is a separate proxy",
        results=results)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation",type=Path,required=True)
    parser.add_argument("--logger",type=Path,required=True)
    parser.add_argument("--horizon",type=float,default=2.,help="Diagnostic window; lock final horizon after H2 timing analysis")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not np.isfinite(args.horizon) or args.horizon<=0:
        parser.error("Positive finite horizon required")
    result=analyze(args.evaluation,args.logger,args.horizon)
    output=args.output or args.evaluation/"governor_analysis.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(f"Saved {output}; {sum(r['success'] for r in result['results'])}/{len(result['results'])} arrivals; failures retained")


if __name__=="__main__":
    main()
