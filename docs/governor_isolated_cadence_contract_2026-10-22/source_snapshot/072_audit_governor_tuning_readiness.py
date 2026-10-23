#!/usr/bin/env python3
"""Offline contact/IMU/motor audit; never changes scores or launches simulation."""
import argparse
import csv
import json
from math import isfinite
from pathlib import Path

import numpy as np

from analyze_governor_experiment import energy,stamp
from nino_control.governor_core import quaternion_rpy,vertical_acceleration


def phase_sensitivity(samples,start,end):
    """Diagnostic decimation only, NOT anti-alias filtering or replacement scores."""
    selected=sorted((t,v) for t,v in samples if start<=t<=end)
    return dict(native_50hz=energy(selected,start,end,.05),
        diagnostic_even_25hz=energy(selected[::2],start,end,.09),
        diagnostic_odd_25hz=energy(selected[1::2],start,end,.09),
        qualification="Two phases of unfiltered 2x decimation show coarser sampling sensitivity only; they cannot prove aliasing at 50Hz, reconstruct true impulse, or replace native scoring.")


def nearest(rows,time,tolerance):
    if not rows:return None
    row=min(rows,key=lambda r:abs(r["time_s"]-time))
    return row if abs(row["time_s"]-time)<=tolerance else None


def control_at(rows,time):
    earlier=[r for r in rows if r["time_s"]<=time]
    return earlier[-1] if earlier else None


def low_progress_window(ground,drive,start,end):
    """GT diagnostic, not a wheel-error proxy or a new native stall criterion."""
    selected=[r for r in ground if start<=r["time_s"]<=end]
    intervals=[]
    for a,b in zip(selected,selected[1:]):
        dt=b["time_s"]-a["time_s"]
        if not 0<dt<=.05:continue
        d=nearest(drive,a["time_s"],.025)
        if d is None:continue
        peripheral=.0625*(abs(d["left_actual_rad_s"])+abs(d["right_actual_rad_s"]))/2
        low=abs(a["vx"])<.04 and abs(a["yaw_rate"])<.05
        intervals.append(dict(start_s=a["time_s"],end_s=b["time_s"],
            active=low and peripheral>.20,slow_wheels=low and peripheral<.04,low_body=low))
    total=sum(r["end_s"]-r["start_s"] for r in intervals if r["active"])
    bouts=[]
    for r in intervals:
        if not r["active"]:continue
        if bouts and abs(bouts[-1][1]-r["start_s"])<1.e-8:bouts[-1][1]=r["end_s"]
        else:bouts.append([r["start_s"],r["end_s"]])
    return dict(available=bool(intervals),duration_s=total,bouts_s=bouts,
        low_body_and_slow_wheels_s=sum(r["end_s"]-r["start_s"] for r in intervals if r["slow_wheels"]),
        low_body_total_s=sum(r["end_s"]-r["start_s"] for r in intervals if r["low_body"]),
        covered_s=sum(r["end_s"]-r["start_s"] for r in intervals),
        rule="Saved GT |vx|<0.04m/s, |yaw_rate|<0.05rad/s, mean absolute driven-wheel peripheral speed>0.20m/s; matched drive within25ms. Diagnostic only, no rescoring arrival/stall.")


def analyze(case,baseline,make_plot=None):
    logger=next(case.glob("contact/*/metadata.json")).parent
    evaluation=next(case.glob("evaluation/*/episodes.csv")).parent
    config=json.loads((logger/"resolved_config.json").read_text())
    controls=[]
    for r in csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()):
        controls.append(dict(time_s=float(r["governor_input_time_s"]),phase=r["governor_phase"],
            scale=float(r["governor_scale"]),wheel_error=float(r["governor_wheel_error_m_s"]),
            wheel_error_threshold=float(r["governor_wheel_error_threshold_m_s"])))
    drive=[]
    for r in csv.DictReader(next(evaluation.glob("episode-*/drive_trace.csv")).open()):
        row={k:float(v) for k,v in r.items() if k not in ("seed",)}
        row["time_s"]=row.pop("sim_time_s");drive.append(row)
    first=baseline["first_contact_s"]
    clear=baseline["clearance_duration_s"]+first+.05
    start=first-.5;end=clear+.3
    ground=[];imu=[];contacts=[];bad_rows=0
    for line in (logger/"samples.jsonl").open():
        try:r=json.loads(line)
        except ValueError:bad_rows+=1;continue
        d=r["data"];topic=r["topic"]
        if "header" not in d:continue
        t=stamp(d)
        if not start<=t<=end:continue
        if topic=="/imu/data":
            q=tuple(d["orientation"][k] for k in ("x","y","z","w"))
            roll,pitch,_=quaternion_rpy(q)
            acceleration=tuple(d["linear_acceleration"][k] for k in ("x","y","z"))
            imu.append(dict(time_s=t,vertical=vertical_acceleration(acceleration,roll,pitch,
                config["policy_v2"]["imu_includes_gravity"]),raw_xyz=acceleration,
                quaternion_norm=float(np.linalg.norm(q)),roll_rad=roll,pitch_rad=pitch))
        elif topic=="/ground_truth/odom":
            tw=d["twist"]["twist"];p=d["pose"]["pose"]["position"]
            ground.append(dict(time_s=t,x=p["x"],z=p["z"],vx=tw["linear"]["x"],
                reported_vz=tw["linear"]["z"],yaw_rate=tw["angular"]["z"]))
        elif topic.startswith("/nino/contact_lab/"):
            for c in d["contacts"]:
                values=[w["body_1_wrench"]["force"]["z"] for w in c["wrenches"]]
                pair=[c["collision1"]["name"],c["collision2"]["name"]]
                contacts.append(dict(time_s=t,component=topic.rsplit("/",1)[-1],
                    positive_obstacle=any("cable_bumps" in name or "training_cable" in name for name in pair),
                    pair=pair,
                    reported_body1_force_z_sum=sum(values) if values and all(isfinite(v) for v in values) else None,
                    normal_z=[n["z"] for n in c["normals"]],depths_m=c["depths"],
                    positions=c["positions"]))
    for rows in (ground,imu,contacts,drive,controls):rows.sort(key=lambda r:r["time_s"])
    selected=[r for r in imu if first+.05<=r["time_s"]<=clear]
    peak=max(selected,key=lambda r:abs(r["vertical"]))
    peak_time=peak["time_s"]
    neighbors=[r for r in imu if abs(r["time_s"]-peak_time)<=.040001]
    contact_neighborhood=[r for r in contacts if abs(r["time_s"]-peak_time)<=.025001]
    phases=[]
    for r in controls:
        if first-.1<=r["time_s"]<=clear and (not phases or phases[-1]["phase"]!=r["phase"]):
            phases.append(dict(relative_s=r["time_s"]-first,phase=r["phase"],scale=r["scale"]))
    window_drive=[r for r in drive if first<=r["time_s"]<=clear]
    result=dict(case=str(case),seed=baseline["seed"],profile=baseline["profile"],
        native_physical_success=baseline["physical_success"],native_stop_settled=baseline["stop_settled"],
        first_contact_s=first,clearance_s=clear,clearance_duration_s=clear-first,
        phase_changes=phases,
        peak=dict(**peak,relative_s=peak_time-first,control=control_at(controls,peak_time),
            nearest_drive=nearest(drive,peak_time,.025),nearest_ground_truth=nearest(ground,peak_time,.025),
            neighbor_imu_samples=neighbors,recorded_contacts_within_25ms=contact_neighborhood),
        sampling=phase_sensitivity([(r["time_s"],r["vertical"]) for r in imu],first+.05,clear),
        low_progress_rotating_wheels=low_progress_window(ground,drive,first,clear),
        drive=dict(maximum_abs_applied_effort_Nm=max(abs(r[k]) for r in window_drive for k in ("left_applied_nm","right_applied_nm")),
            limited_status_samples=sum(bool(r["left_limited"] or r["right_limited"]) for r in window_drive),
            stale_command_status_samples=sum(not bool(r["cmd_fresh"]) for r in window_drive),
            reversed_target_status_samples=sum(r["left_target_rad_s"]<-.01 or r["right_target_rad_s"]<-.01 for r in window_drive)),
        logger_closed=json.loads((logger/"metadata.json").read_text()).get("complete"),
        malformed_json_lines=bad_rows,
        qualification="Temporal association only. Contact forces are reported per manifold, not net force/impulse. GT body twist and displaced IMU are different measurements; no exact acceleration reconstruction. Missing contacts unknown. Native failures/outliers retained.")
    if make_plot:
        plot(result,imu,ground,contacts,drive,controls,make_plot)
    return result


def plot(result,imu,ground,contacts,drive,controls,path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    first=result["first_contact_s"];end=result["clearance_s"]
    figure,axes=plt.subplots(5,1,figsize=(11,10),sharex=True,constrained_layout=True)
    axes[0].step([r["time_s"]-first for r in controls],[r["scale"] for r in controls],where="post",color="#1670b8")
    axes[0].set_ylabel("Speed scale")
    axes[1].plot([r["time_s"]-first for r in ground],[r["vx"] for r in ground],label="GT body vx")
    axes[1].plot([r["time_s"]-first for r in drive],[.0625*(r["left_target_rad_s"]+r["right_target_rad_s"])/2 for r in drive],label="Wheel target",ls="--")
    axes[1].plot([r["time_s"]-first for r in drive],[.0625*(r["left_actual_rad_s"]+r["right_actual_rad_s"])/2 for r in drive],label="Wheel peripheral",alpha=.7)
    axes[1].set_ylabel("Speed (m/s)");axes[1].legend(ncol=3,fontsize=8)
    for key in ("left_applied_nm","right_applied_nm"):
        axes[2].plot([r["time_s"]-first for r in drive],[r[key] for r in drive],label=key)
    axes[2].set_ylabel("Reported effort\n(Nm)");axes[2].legend(fontsize=8)
    axes[3].plot([r["time_s"]-first for r in imu],[r["vertical"] for r in imu],marker=".",ms=3,color="#a22632")
    axes[3].set_ylabel("Native vertical\naccel (m/s²)")
    names=sorted({r["component"] for r in contacts})
    for i,name in enumerate(names):
        for positive,color in ((False,"0.65"),(True,"#bd4335")):
            rows=[r for r in contacts if r["component"]==name and r["positive_obstacle"]==positive]
            axes[4].scatter([r["time_s"]-first for r in rows],[i]*len(rows),s=3,color=color,
                label=("Cable" if positive else "Floor/other") if i==0 else None)
    axes[4].set_yticks(range(len(names)),names,fontsize=7)
    axes[4].set_ylabel("Recorded contact\n(any surface)")
    axes[4].legend(fontsize=8,ncol=2)
    axes[4].set_xlabel("Simulation seconds after first recorded obstacle contact")
    for ax in axes:
        ax.set_xlim(-.3,end-first+.2);ax.axvline(result["peak"]["relative_s"],color="#a22632",ls=":",alpha=.7);ax.grid(alpha=.2)
    figure.suptitle(f"Saved-trace audit — seed {result['seed']}, {result['profile']}\nNo simulation or rescoring; contact dots are observations, not continuous support")
    figure.savefig(path,dpi=160);plt.close(figure)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen",type=Path,required=True)
    parser.add_argument("--crossing-result",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    source=json.loads(args.crossing_result.read_text());results=[]
    focus={(76500,"moderate"),(76501,"moderate"),(76502,"moderate"),(76503,"full")}
    for baseline in source["episodes"]:
        try:
            name=f"seed_{baseline['seed']}_{baseline['profile']}"
            result=analyze(args.screen/name,baseline,args.output/(name+".png")
                if (baseline["seed"],baseline["profile"]) in focus else None)
            results.append(dict(available=True,**result))
        except Exception as error:
            results.append(dict(seed=baseline["seed"],profile=baseline["profile"],
                native_physical_success=baseline.get("physical_success"),available=False,
                reason=f"{type(error).__name__}: {error}"))
    (args.output/"result.json").write_text(json.dumps(dict(results=results,
        no_simulation=True,physical_scoring_changed=False),indent=2,allow_nan=False)+"\n")
    print("Saved offline audit:",args.output)


if __name__=="__main__":main()
