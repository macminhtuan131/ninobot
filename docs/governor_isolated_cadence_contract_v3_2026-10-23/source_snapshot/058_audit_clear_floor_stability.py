#!/usr/bin/env python3
"""Align saved wheel PI, passive caster, contact and 3D pose traces.

No simulation/control. Contact message gaps are not proof of lift-off.
"""
import argparse
import csv
import json
from math import degrees,isfinite
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from bisect import bisect_left
from statistics import median
from math import remainder, pi

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl")]
from nino_control.governor_core import quaternion_rpy


def resolve(parent,name):
    parent=Path(parent)
    if (parent/name).is_file(): return parent
    candidates=list(parent.glob("*/"+name))
    if not candidates: raise ValueError(f"No {name} at {parent}")
    return max(candidates,key=lambda path:path.stat().st_mtime).parent


def sustained_start(samples,predicate,minimum_seconds=.1):
    start=previous=None
    for t,value in samples:
        if predicate(value):
            if start is None or previous is None or t-previous>.05: start=t
            if t-start>=minimum_seconds-1e-8: return start
        else: start=None
        previous=t
    return None


def settling_audit(logger,end,seconds=2.):
    """Observed stop after arrival; never changes the arrival score itself."""
    poses=[];commands=[];chassis=[]
    for line in (Path(logger)/"samples.jsonl").open():
        try: row=json.loads(line)
        except ValueError: continue
        data=row["data"];topic=row["topic"]
        if topic=="/nino_drive/diagnostics":
            values=dict(zip(data["layout"]["dim"][0]["label"].split(","),data["data"]))
            if end<=values["sim_time_s"]<=end+seconds: commands.append(values)
            continue
        if "header" not in data: continue
        stamp=data["header"]["stamp"];t=stamp["sec"]+stamp["nanosec"]*1e-9
        if not end<=t<=end+seconds: continue
        if topic=="/ground_truth/odom":
            p=data["pose"]["pose"];q=p["orientation"]
            roll,pitch,_=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
            poses.append(dict(time_s=t,roll_deg=degrees(roll),pitch_deg=degrees(pitch),
                x_m=p["position"]["x"],y_m=p["position"]["y"],
                speed_m_s=data["twist"]["twist"]["linear"]["x"]))
        elif topic=="/nino/contact_lab/chassis" and data["contacts"]: chassis.append(t)
    poses.sort(key=lambda row:row["time_s"])
    feedback_valid=all(d.get("have_wheel_state",0.)>.5 for d in commands)
    if len(poses)<2 or len(commands)<2:
        return dict(available=False,reason="missing_pose_or_drive_feedback",settled=None)
    def covered(times):
        times=sorted(set(times))
        return (len(times)>1 and times[-1]-times[0]>=.95*seconds and
                max(b-a for a,b in zip(times,times[1:]))<=.05+1e-8)
    available=covered([p["time_s"] for p in poses]) and covered([d["sim_time_s"] for d in commands])
    roll=max(abs(p["roll_deg"]) for p in poses);pitch=max(abs(p["pitch_deg"]) for p in poses)
    zero=all(abs(d["requested_linear_m_s"])+abs(d["requested_yaw_rad_s"])<1e-8 for d in commands)
    available=available and feedback_valid
    settled=(zero and max(roll,pitch)<5. and abs(poses[-1]["speed_m_s"])<.01) if available else None
    return dict(available=available,reason=None if available else "incomplete_window_or_sensor_gap",
        qualification="2s stopped-command diagnostic, independent of arrival scoring; 5deg/.01m_s are declared diagnostic thresholds",
        end_time_s=end,window_seconds=seconds,pose_samples=len(poses),drive_samples=len(commands),
        pose_coverage_s=poses[-1]["time_s"]-poses[0]["time_s"],commanded_stop=zero,
        max_abs_roll_deg=roll,max_abs_pitch_deg=pitch,last=poses[-1],
        chassis_contact_messages=len(chassis),settled=settled)


def audit(evaluation,logger):
    evaluation=resolve(evaluation,"metadata.json")
    logger=Path(logger)
    if (logger/"view_manifest.json").exists():
        from nino_rl.acquisition_contract import verify_view
        verify_view(logger)
    else:logger=resolve(logger,"metadata.json")
    paths=list(evaluation.glob("episode-*/control_trace.csv"))
    if len(paths)!=1: raise ValueError("Select one episode/run for the stability audit")
    rows=list(csv.DictReader(paths[0].open()))
    if not rows: raise ValueError("No completed control step to audit")
    summary=json.loads((evaluation/"summary.json").read_text()) if (evaluation/"summary.json").exists() else None
    origin=float(rows[0]["sim_time_s"])-float(rows[0]["elapsed_s"])
    dt=(float(rows[1]["elapsed_s"])-float(rows[0]["elapsed_s"])) if len(rows)>1 else .1
    cutoff=float(rows[-1]["sim_time_s"])+(0. if summary and summary.get("complete") else dt)+1e-6
    cruise=max(float(r["governor_requested_linear_m_s"]) for r in rows)
    approach=next((float(r["elapsed_s"]) for r in rows
                   if float(r["elapsed_s"])>2. and 0<float(r["governor_requested_linear_m_s"])<.9*cruise),None)
    eid=(rows[0].get("governor_run_id") or None)
    poses=[]; joints=[]; caster_joints=[]; contact={}; episode_ids=set()
    caster_forces={side:[] for side in ("left","right")}
    for line in (logger/"samples.jsonl").open():
        try: row=json.loads(line)
        except ValueError: continue
        if not row.get("episode"): continue
        data=row["data"];topic=row["topic"]
        if "header" not in data: continue
        stamp=data["header"]["stamp"];t=stamp["sec"]+stamp["nanosec"]*1e-9
        if not origin<=t<=cutoff: continue
        # Time window selects this single run; reject a mixed run ID if known.
        if eid and not str(row["episode"]).startswith(eid+":"): continue
        episode_ids.add(str(row["episode"]))
        elapsed=t-origin
        if topic=="/ground_truth/odom":
            p=data["pose"]["pose"];q=p["orientation"]
            roll,pitch,_=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
            poses.append(dict(elapsed_s=elapsed,x_m=p["position"]["x"],y_m=p["position"]["y"],
                z_m=p["position"]["z"],roll_deg=degrees(roll),pitch_deg=degrees(pitch),
                speed_m_s=data["twist"]["twist"]["linear"]["x"],
                yaw_rate_rad_s=data["twist"]["twist"]["angular"]["z"]))
        elif topic=="/joint_states":
            values=dict(zip(data["name"],data["velocity"]))
            joints.append((elapsed,values))
            caster_joints.append((elapsed,values,dict(zip(data["name"],data["position"]))))
        elif topic.startswith("/nino/contact_lab/"):
            component=topic.rsplit("/",1)[-1]
            if not data["contacts"]: continue
            record=contact.setdefault(component,dict(first_recorded_s=elapsed,last_recorded_s=elapsed,
                peak_abs_force_z_N=None,sampled_messages=0,manifolds_observed=0,
                opposing_vertical_normal_manifolds=0))
            record["last_recorded_s"]=elapsed
            record["sampled_messages"]+=1
            for c in data["contacts"]:
                record["manifolds_observed"]+=1
                normal_z=[n["z"] for n in c["normals"] if n["z"] is not None and isfinite(n["z"])]
                if normal_z and min(normal_z)<-.9 and max(normal_z)>.9:
                    record["opposing_vertical_normal_manifolds"]+=1
                for wrench in c["wrenches"]:
                    force=wrench["body_1_wrench"]["force"]["z"]
                    if force is not None and isfinite(force):
                        if record["peak_abs_force_z_N"] is None or abs(force)>record["peak_abs_force_z_N"]:
                            record.update(peak_abs_force_z_N=abs(force),peak_force_elapsed_s=elapsed,
                                peak_force_depths_m=c["depths"],peak_force_positions=c["positions"],
                                peak_force_collision_pair=[c["collision1"]["name"],c["collision2"]["name"]],
                                peak_force_normal_z=[n["z"] for n in c["normals"]],
                                reported_signed_force_z_sum_at_peak=sum(w["body_1_wrench"]["force"]["z"] for w in c["wrenches"]
                                    if w["body_1_wrench"]["force"]["z"] is not None and isfinite(w["body_1_wrench"]["force"]["z"])))
            for side in caster_forces:
                if component==f"caster_{side}_wheel":
                    values=[abs(w["body_1_wrench"]["force"]["z"]) for c in data["contacts"]
                        for w in c["wrenches"] if w["body_1_wrench"]["force"]["z"] is not None
                        and isfinite(w["body_1_wrench"]["force"]["z"])]
                    if values: caster_forces[side].append((elapsed,max(values)))
    if len(episode_ids)>1: raise ValueError("Multiple episodes overlap this audit window")
    drive=list(csv.DictReader((paths[0].parent/"drive_trace.csv").open()))
    poses.sort(key=lambda row:row["elapsed_s"])
    times=[p["elapsed_s"] for p in poses]
    rolling={side:[] for side in ("left","right")}
    loaded_rolling={side:[] for side in rolling}
    for side in caster_forces: caster_forces[side].sort()
    force_times={side:[t for t,_ in values] for side,values in caster_forces.items()}
    for t,velocity,position in caster_joints:
        if not times: continue
        index=bisect_left(times,t)
        index=min((i for i in (index-1,index) if 0<=i<len(times)),key=lambda i:abs(times[i]-t))
        pose=poses[index]
        speed=pose["speed_m_s"]
        if abs(times[index]-t)>.05 or speed<=.25 or abs(pose["yaw_rate_rad_s"])>.05: continue
        for side in rolling:
            if abs(remainder(position[f"caster_{side}_swivel_joint"],2*pi))>.15: continue
            ratio=abs(velocity[f"caster_{side}_wheel_joint"])*.016/speed
            rolling[side].append(ratio)
            ft=force_times[side]
            if ft:
                at=bisect_left(ft,t)
                at=min((i for i in (at-1,at) if 0<=i<len(ft)),key=lambda i:abs(ft[i]-t))
                if abs(ft[at]-t)<=.015 and caster_forces[side][at][1]>=1.:
                    loaded_rolling[side].append(ratio)
    rolling_report={side:dict(samples=len(values),median=median(values) if values else None,
        fraction_below_half_rolling=sum(v<.5 for v in values)/len(values) if values else None)
        for side,values in rolling.items()}
    for side,values in loaded_rolling.items():
        rolling_report[side]["positive_force_subset"]=dict(samples=len(values),median=median(values) if values else None)
    drive_response={}
    for side in ("left","right"):
        commanded=[r for r in drive if origin<=float(r["sim_time_s"])<=cutoff and float(r[side+"_target_rad_s"])>2.]
        drive_response[side]=dict(forward_target_samples=len(commanded),
            near_stopped_samples=sum(abs(float(r[side+"_actual_rad_s"]))<.1*float(r[side+"_target_rad_s"]) for r in commanded),
            maximum_abs_tracking_error_rad_s=max((abs(float(r[side+"_actual_rad_s"])-float(r[side+"_target_rad_s"])) for r in commanded),default=None))
    after=[(t,v) for t,v in joints if approach is not None and t>=approach]
    caster_slow=sustained_start(after,lambda v:all(abs(v[f"caster_{side}_wheel_joint"])<1.
                                                for side in ("left","right")))
    onset=[]
    windows=((2.,14.),(14.,16.),(16.,18.))
    for lo,hi in windows:
        selected=[r for r in drive if lo<=float(r["sim_time_s"])-origin<hi]
        if not selected: continue
        entry=dict(window_s=[lo,hi],samples=len(selected),wheels={})
        for side in ("left","right"):
            effort=[float(r[side+"_applied_nm"]) for r in selected]
            entry["wheels"][side]=dict(maximum_abs_applied_nm=max(map(abs,effort)),
                minimum_actual_rad_s=min(float(r[side+"_actual_rad_s"]) for r in selected),
                maximum_tracking_error_rad_s=max(abs(float(r[side+"_target_rad_s"])-float(r[side+"_actual_rad_s"])) for r in selected),
                residual_nonzero_samples=sum(abs(float(r[side+"_residual_nm"]))>1e-9 for r in selected))
        onset.append(entry)
    observed={}
    urdf=logger/"robot_description.urdf"
    if urdf.exists():
        robot=ET.fromstring(urdf.read_text())
        for side in ("left","right"):
            observed[side]=float(robot.find(f"joint[@name='caster_{side}_wheel_joint']/dynamics").get("damping"))
    return dict(qualification="Saved-trace sequence audit; temporal order is not a proven root cause",
        evaluation=str(evaluation),logger=str(logger),completed_control_steps=len(rows),
        completed_evaluation=summary.get("complete",False) if summary else False,
        physical_success_rate=summary.get("success_rate") if summary else None,
        source_episode_ids=sorted(episode_ids),approach_started_s=approach,
        first_sustained_both_casters_below_1rad_s=caster_slow,
        first_ground_truth_tilt_above_5deg=next((p for p in poses if max(abs(p["roll_deg"]),abs(p["pitch_deg"]))>5.),None),
        first_ground_truth_roll_above_15deg=next((p for p in poses if abs(p["roll_deg"])>15.),None),
        maximum_abs_roll_deg=max((abs(p["roll_deg"]) for p in poses),default=None),
        maximum_abs_pitch_deg=max((abs(p["pitch_deg"]) for p in poses),default=None),
        last_ground_truth=poses[-1] if poses else None,contact_messages=contact,wheel_windows=onset,
        observed_caster_wheel_damping=observed,
        caster_rolling_ratio=rolling_report,
        caster_rolling_qualification="Nominal radius .016m; body speed>.25m/s, abs yaw rate<.05rad/s, swivel alignment<.15rad, nearest GT within .05s. Positive-force subset additionally needs recorded abs vertical contact force>=1N within .015s. Low unconditional ratio can include unloaded wheels; do not label it slip/stall without support evidence. Diagnostic filters, not hardware limits or inferred readiness thresholds.",
        driven_wheel_response=drive_response,
        damping_drag_at_025m_s_N={side:value*(.25/.016)/.016 for side,value in observed.items()},
        damping_drag_qualification="b*omega/r at nominal caster radius0.016m and pure rolling; not a measured contact force",
        message_gap_qualification="Only nonempty contacts are published; a gap is not proof of no contact or exact lift-off")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation",type=Path,required=True)
    parser.add_argument("--logger",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    data=audit(args.evaluation,args.logger)
    if data["completed_evaluation"] and data["physical_success_rate"]==1.:
        row=list(csv.DictReader(next(Path(data["evaluation"]).glob("episode-*/control_trace.csv")).open()))[-1]
        data["post_arrival_stop"]=settling_audit(data["logger"],float(row["sim_time_s"]))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
    print("Saved "+str(args.output))


if __name__=="__main__": main()
