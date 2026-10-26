#!/usr/bin/env python3
"""PI callback timing and observed caster support from saved single-cable runs."""
import argparse
from bisect import bisect_left
import csv
import json
from math import isfinite
from pathlib import Path

import numpy as np

from analyze_governor_experiment import stamp
from audit_single_cable_screen import analyze as crossing
from summarize_contact_oracle_h2 import native_status
from nino_control.governor_core import quaternion_rpy,vertical_acceleration


def stats(values):
    values=[v for v in values if v is not None and isfinite(v)]
    return dict(n=len(values),minimum=float(min(values)),median=float(np.median(values)),
                maximum=float(max(values))) if values else dict(n=0,minimum=None,median=None,maximum=None)


def timing(rows):
    required=("control_updates","control_raw_dt_sum_s","control_raw_dt_min_s","control_raw_dt_max_s",
              "control_dt_fallbacks","control_joint_age_max_s","command_received_sim_s")
    if not rows or any(k not in rows[0] for k in required):
        return dict(available=False,reason="PI-callback telemetry unavailable; 50Hz status is not 500Hz control timing")
    elapsed=sum(float(r["control_raw_dt_sum_s"]) for r in rows)
    updates=sum(float(r["control_updates"]) for r in rows)
    return dict(available=True,status_samples=len(rows),updates=int(updates),raw_elapsed_s=elapsed,
        observed_updates_per_sim_s=updates/elapsed if elapsed>0 else None,
        minimum_raw_dt_s=min(float(r["control_raw_dt_min_s"]) for r in rows),
        maximum_raw_dt_s=max(float(r["control_raw_dt_max_s"]) for r in rows),
        dt_fallbacks=int(sum(float(r["control_dt_fallbacks"]) for r in rows)),
        invalid_dt=int(sum(float(r["control_dt_invalid"]) for r in rows)),
        intervals_over_4ms=int(sum(float(r["control_dt_over_4ms"]) for r in rows)),
        window_joint_age_max_s=stats([float(r["control_joint_age_max_s"]) for r in rows
                                    if float(r["control_joint_age_max_s"])!=-1.]),
        future_joint_updates=int(sum(float(r["control_future_joint_updates"]) for r in rows)))


def caster_window(joints,ground,forces,lo,hi):
    times=[r[0] for r in ground]
    output={}
    for side in ("left","right"):
        samples=[]
        ft=[r[0] for r in forces[side]]
        for t,velocity,position in joints:
            if not lo<=t<=hi:continue
            at=bisect_left(times,t)
            possible=[i for i in (at-1,at) if 0<=i<len(times)]
            if not possible:continue
            at=min(possible,key=lambda i:abs(times[i]-t))
            if abs(times[at]-t)>.025:continue
            speed=ground[at][1]
            force=None
            fi=bisect_left(ft,t)
            possible=[i for i in (fi-1,fi) if 0<=i<len(ft)]
            if possible:
                fi=min(possible,key=lambda i:abs(ft[i]-t))
                if abs(ft[fi]-t)<=.015:force=forces[side][fi][1]
            omega=velocity[f"caster_{side}_wheel_joint"]
            samples.append(dict(time_s=t,omega=omega,swivel=position[f"caster_{side}_swivel_joint"],
                body_speed=speed,ratio=abs(omega)*.016/abs(speed) if abs(speed)>.25 else None,
                reported_support_z_N=force))
        slow=[r for r in samples if r["ratio"] is not None and r["ratio"]<.5]
        output[side]=dict(samples=len(samples),wheel_rad_s=stats([r["omega"] for r in samples]),
            swivel_rad=stats([r["swivel"] for r in samples]),rolling_ratio=stats([r["ratio"] for r in samples]),
            observed_support_z_N=stats([r["reported_support_z_N"] for r in samples]),
            strong_support_samples=sum(r["reported_support_z_N"] is not None and r["reported_support_z_N"]>=1. for r in samples),
            weak_support_samples=sum(r["reported_support_z_N"] is not None and r["reported_support_z_N"]<=.2 for r in samples),
            support_unavailable_samples=sum(r["reported_support_z_N"] is None for r in samples),
            slow_rotation_samples=len(slow),
            slow_with_observed_strong_support=sum(r["reported_support_z_N"] is not None and r["reported_support_z_N"]>=1. for r in slow),
            slow_with_support_unavailable=sum(r["reported_support_z_N"] is None for r in slow))
    return output


def imu_sampling(samples,lo,hi):
    selected=np.asarray([(t,v) for t,v in samples if lo<=t<=hi],dtype=float)
    if len(selected)<2:
        return dict(available=False,reason="insufficient_IMU_samples")
    selected=selected[np.argsort(selected[:,0])]
    dt=np.diff(selected[:,0]);valid=(dt>0)&(dt<=.05)
    weights=np.zeros(len(selected))
    for i,interval in enumerate(dt):
        if valid[i]:
            weights[i]+=interval/2;weights[i+1]+=interval/2
    squared=weights*selected[:,1]**2
    total=float(sum(squared));index=int(np.argmax(np.abs(selected[:,1])))
    return dict(available=True,samples=len(selected),interval_s=stats(list(dt)),
        largest_absolute_sample_m_s2=float(abs(selected[index,1])),
        p95_absolute_sample_m_s2=float(np.percentile(np.abs(selected[:,1]),95)),
        largest_sample_time_s=float(selected[index,0]),
        largest_sample_fraction_of_integrated_squared_signal=(float(max(squared)/total) if total>0 else None),
        qualification="Native 50Hz IMU only. Contribution uses the existing trapezoidal squared-signal metric. Cannot resolve sub-sample impact duration or prove aliasing/contact cause.")


def analyze(case):
    case=Path(case)
    metadata_path=next(case.glob("contact/*/metadata.json"));logger=metadata_path.parent
    path=next(case.glob("evaluation/*/episode-001/control_trace.csv"))
    control=list(csv.DictReader(path.open()));drive=list(csv.DictReader(path.with_name("drive_trace.csv").open()))
    origin=float(control[0]["governor_input_time_s"]);end=float(control[-1]["sim_time_s"])
    contact=[json.loads(line) for line in (logger/"contact_events.jsonl").open()]
    first=min((r["time_s"] for r in contact if r["event"]=="begin" and r.get("named_positive_obstacle")
               and origin<=r["time_s"]<=end),default=None)
    config=json.loads((logger/"resolved_config.json").read_text())
    ground=[];joints=[];imu=[];forces={side:[] for side in ("left","right")}
    for line in (logger/"samples.jsonl").open():
        try:r=json.loads(line)
        except ValueError:continue
        d=r["data"];topic=r["topic"]
        if "header" not in d:continue
        t=stamp(d)
        if not origin-.2<=t<=end:continue
        if topic=="/ground_truth/odom":ground.append((t,d["twist"]["twist"]["linear"]["x"]))
        elif topic=="/joint_states":joints.append((t,dict(zip(d["name"],d["velocity"])),dict(zip(d["name"],d["position"]))))
        elif topic=="/imu/data":
            q=d["orientation"];roll,pitch,_=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
            imu.append((t,vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x","y","z")),
                roll,pitch,config["policy_v2"]["imu_includes_gravity"])))
        else:
            for side in forces:
                if topic!=f"/nino/contact_lab/caster_{side}_wheel":continue
                values=[]
                for c in d["contacts"]:
                    pair=(c["collision1"]["name"],c["collision2"]["name"])
                    if not any("terrain_collision" in name for name in pair):continue
                    wrench=[w["body_1_wrench"]["force"]["z"] for w in c["wrenches"]]
                    if wrench and all(isfinite(v) for v in wrench):values.append(abs(sum(wrench)))
                if values:forces[side].append((t,max(values)))
    ground.sort()
    raw_joint_samples=len(joints)
    # Repeated timestamped JointStates can contain dictionaries and cannot be
    # tuple-sorted. Keep the last logged measurement at each simulation stamp;
    # receipt duplicates must not gain extra weight in the support summary.
    joints=sorted({row[0]:row for row in joints}.values(),key=lambda row:row[0])
    for values in forces.values():values.sort()
    measured=[r for r in drive if origin+.1<=float(r["sim_time_s"])<=end]
    initial=next((r for r in drive if float(r["requested_linear_m_s"])>.3),None)
    outcome=crossing(case)
    meta=json.loads(metadata_path.read_text())
    result=dict(case=str(case),**native_status(case),first_contact_s=first,
        effort_drive_sha256=meta.get("effort_drive_sha256"),world_sha256=meta.get("world_sha256"),
        timing=timing(measured),initial_body_speed_m_s=stats([v for t,v in ground if origin-.1<=t<=origin]),
        repeated_joint_timestamps=raw_joint_samples-len(joints),
        initial_caster=caster_window(joints,ground,forces,origin-.1,origin),
        precontact_caster=caster_window(joints,ground,forces,first-.5,first-.05) if first is not None else None,
        first_50ms_acceleration=outcome.get("first_50ms_acceleration"),
        postcontact_clearance=outcome.get("postcontact_until_clearance"),
        imu_postcontact_sampling=(imu_sampling(imu,outcome["postcontact_until_clearance"]["start_time_s"],
            outcome["postcontact_until_clearance"]["end_time_s"])
            if outcome.get("postcontact_until_clearance",{}).get("available") else None),
        initial_command_received_delay_s=(float(initial["command_received_sim_s"])-origin
            if initial is not None and "command_received_sim_s" in initial else None),
        qualification="Observed floor wrench magnitude is a support proxy. Missing stream is unknown, not unloaded. Caster rotation is not slip without support. Frames are correlated; episode is the replication unit.")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();results=[]
    for case in sorted(args.screen.glob("seed_*")):
        try:results.append(analyze(case))
        except Exception as error:results.append(dict(case=str(case),**native_status(case),available=False,reason=str(error)))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(results=results,controller_changed=False),indent=2,allow_nan=False)+"\n")
    print("Saved",args.output)


if __name__=="__main__":main()
