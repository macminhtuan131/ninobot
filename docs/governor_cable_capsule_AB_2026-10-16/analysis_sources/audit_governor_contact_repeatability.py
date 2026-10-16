#!/usr/bin/env python3
"""Saved oracle/sensor sequence and caster-state audit, never controller input."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from analyze_governor_experiment import stamp


def analyze(case):
    case=Path(case)
    logger=next((case/"contact").glob("*/metadata.json")).parent
    trace=list(csv.DictReader(next(case.glob("evaluation/*/episode-001/control_trace.csv")).open()))
    start=float(trace[0]["governor_input_time_s"])
    end=float(trace[-1]["sim_time_s"])
    contacts=[json.loads(line) for line in (logger/"contact_events.jsonl").open()]
    contacts=[r for r in contacts if r["event"]=="begin" and r.get("named_positive_obstacle") and start<=r["time_s"]<=end]
    first=min(r["time_s"] for r in contacts)
    by_component={}
    for r in sorted(contacts,key=lambda r:r["time_s"]):
        by_component.setdefault(r["component"],r["time_s"]-first)
    changes=[];previous=None;scales=[]
    for row in trace:
        t=float(row["governor_input_time_s"])-first
        phase=row["governor_phase"]
        if phase!=previous:
            changes.append(dict(relative_s=t,phase=phase,scale=float(row["governor_scale"])))
            previous=phase
        if t>=0:scales.append((t,float(row["governor_scale"])))
    samples=[];ground=[];last=None
    for line in (logger/"samples.jsonl").open():
        row=json.loads(line);data=row["data"]
        if "header" not in data:continue
        t=stamp(data)
        if not first-.3<=t<=first-.05:continue
        if row["topic"]=="/joint_states":
            velocity=dict(zip(data["name"],data["velocity"]));position=dict(zip(data["name"],data["position"]))
            samples.append((t,velocity,position))
            if last is None or t>last[0]:last=(t,velocity,position)
        elif row["topic"]=="/ground_truth/odom":ground.append(data["twist"]["twist"]["linear"]["x"])
    wheel={}
    for side in ("left","right"):
        name=f"caster_{side}_wheel_joint";swivel=f"caster_{side}_swivel_joint"
        wheel[side]=dict(samples=len(samples),
            median_wheel_rad_s=float(np.median([v[name] for _,v,_ in samples])) if samples else None,
            last_wheel_rad_s=last[1].get(name) if last else None,
            last_swivel_rad=last[2].get(swivel) if last else None,
            last_sample_before_contact_s=first-last[0] if last else None)
    return dict(case=str(case),first_contact_s=first,phase_changes=changes,
        first_contacts_relative_s=by_component,precontact_caster_window_s=[-.3,-.05],
        precontact_body_median_m_s=float(np.median(ground)) if ground else None,
        precontact_caster=wheel,postcontact_scales=scales,
        qualification="Caster joint measurements are privileged offline diagnostics. Low caster rotation does not establish slip if the caster is unloaded. Cold-start caster/contact states were not restored identically.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle",type=Path,required=True)
    parser.add_argument("--sensor",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    results=[]
    for group,root in (("oracle",args.oracle),("sensor",args.sensor)):
        for case in sorted(root.glob("seed_*_moderate")):
            try:results.append(dict(group=group,seed=int(case.name.split("_")[1]),available=True,**analyze(case)))
            except Exception as error:
                results.append(dict(group=group,case=str(case),available=False,reason=f"{type(error).__name__}: {error}"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(results=results,controller_changed=False),indent=2,allow_nan=False)+"\n")
    print("Saved",args.output)


if __name__=="__main__":main()
