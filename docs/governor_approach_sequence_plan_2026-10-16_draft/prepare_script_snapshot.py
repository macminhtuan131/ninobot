#!/usr/bin/env python3
"""Offline-only preparation: precontact balance and complete contact/recovery windows.

No ROS imports, subprocesses, simulation, controller updates or native rescoring.
Historical data demonstrate instrumentation only, never select a new candidate.
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from nino_rl.slip_reporting import integrate
from nino_control.governor_core import quaternion_rpy,vertical_acceleration


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def angle_delta(a,b):return math.atan2(math.sin(a-b),math.cos(a-b))


def sustained(samples,start,end,predicate,duration=.3,max_gap=.05):
    begin=previous=None
    for t,v in sorted(samples):
        if not start<=t<=end:continue
        if not predicate(v):begin=previous=None;continue
        if previous is None or t-previous>max_gap+1e-9:begin=t
        previous=t
        if t-begin>=duration-1e-9:return dict(begin_s=begin,confirmed_s=t)
    return None


def closed_contact_end(events,first,terminal):
    """No silent completion with a lingering manifold or missing event pair."""
    active=set()
    last=None
    for e in sorted(events,key=lambda e:e["time_s"]):
        if not e.get("named_positive_obstacle") or not first-1e-9<=e["time_s"]<=terminal:continue
        key=(e["component"],tuple(sorted(e["collisions"])))
        if e["event"]=="begin":active.add(key)
        elif e["event"]=="end":
            if key not in active:return dict(available=False,reason="unpaired_contact_end")
            active.remove(key);last=e["time_s"]
    return dict(available=last is not None and not active,last_end_upper_bound_s=last,
        active_components=sorted({k[0] for k in active}),reason="contact_sequence_censored" if active else None)


def sequence_windows(first,clear,last_contact,terminal,command_recovery,body_recovery):
    if clear is None or not last_contact.get("available"):
        return dict(available=False,reason="missing_clearance_or_unclosed_contact",observed_until_s=terminal)
    contact_end=max(clear,last_contact["last_end_upper_bound_s"]+.2)
    if contact_end>terminal:return dict(available=False,reason="contact_quiet_tail_censored",observed_until_s=terminal)
    recovery_end=max(contact_end,command_recovery["confirmed_s"],body_recovery["confirmed_s"]) if command_recovery and body_recovery else None
    return dict(available=True,contact_start_s=first,contact_end_s=contact_end,
        recovery_end_s=recovery_end,recovery_available=recovery_end is not None and recovery_end<=terminal,
        fixed_horizon_end_s=first+3.,fixed_horizon_available=first+3.<=terminal,
        qualification="Contact end=max(clearance,last manifold end upper bound+0.2s); keep fixed 3s outcome too, so a longer adaptive window cannot dilute RMS unnoticed.")


def negative_support(signal,first,end_relative,first_reduction):
    times=signal["time"]
    a=max(0,bisect.bisect_right(times,first)-1)
    b=min(len(times)-1,bisect.bisect_left(times,first+end_relative))
    if b<=a:return dict(available=False,reason="insufficient_signal_support")
    joint=float(np.nanmax(signal["joint_support_stamps"][a:b+1]))
    last=max(float(times[b]),joint)
    return dict(available=bool(np.isfinite(last) and (first_reduction is None or last<first_reduction-1e-9)),
        latest_support_s=last,first_reduced_command_s=first_reduction,
        reason="support_reaches_intervention" if first_reduction is not None and last>=first_reduction-1e-9 else None)


def summary(values):
    return dict(n=len(values),median=float(statistics.median(values)),minimum=float(min(values)),maximum=float(max(values))) if values else dict(n=0,median=None,minimum=None,maximum=None)


def signal_stats(samples,start,end):
    chosen=[(t,v) for t,v in samples if start<=t<=end]
    covered=sum(max(0.,min(end,b[0])-max(start,a[0])) for a,b in zip(samples,samples[1:]) if 0<b[0]-a[0]<=.050000001)
    coverage=covered/(end-start) if end>start else 0.
    if coverage<.98 or not chosen:return dict(available=False,coverage_fraction=coverage,rms=None,peak=None,p95_abs=None)
    values=np.array([v for _,v in chosen])
    return dict(available=True,coverage_fraction=coverage,rms=float(np.sqrt(np.mean(values**2))),
                peak=float(np.max(abs(values))),p95_abs=float(np.percentile(abs(values),95)),
                definition="Unfiltered samples at original IMU timestamps; sample RMS/percentile, no fabricated high-frequency peak or impulse.")


def analyze(row):
    result=dict(seed=row["seed"],arm=row["arm"],case=row["case"],native_physical_pass=row.get("physical_pass"),
                legacy_reporting_pass=row.get("reporting_pass"),available=False)
    case=Path(row["case"])
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    logger=next(case.glob("contact/*/metadata.json")).parent
    data=load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=row["seed"],profile=row["profile"]))
    signal=gt_timestamp_series(data)
    tc=row.get("first_contact_s")
    if tc is None:return {**result,"reason":"missing_first_contact; native outcome retained"}
    config=json.loads((logger/"resolved_config.json").read_text())
    drive=[(float(c["sim_time_s"]),{k:float(v) for k,v in c.items() if k!="seed"})
           for c in csv.DictReader(next(evaluation.glob("episode-*/drive_trace.csv")).open())]
    poses=[];joints=[];imu=[];supports={side:[] for side in ("left","right")}
    last_loaded=None
    for line in (logger/"samples.jsonl").open():
        packet=json.loads(line);topic,d=packet["topic"],packet["data"]
        if "header" not in d:continue
        t=d["header"]["stamp"]["sec"]+d["header"]["stamp"]["nanosec"]*1e-9
        if not data["start"]-.6<=t<=data["end"]+.02:continue
        if topic=="/ground_truth/odom":
            r,p,y=quaternion_rpy(tuple(d["pose"]["pose"]["orientation"][k] for k in ("x","y","z","w")))
            pos=d["pose"]["pose"]["position"];v=d["twist"]["twist"]
            poses.append((t,dict(x=pos["x"],y=pos["y"],yaw=y,roll=r,pitch=p,v=v["linear"]["x"],w=v["angular"]["z"])))
        elif topic=="/joint_states":joints.append((t,dict(position=dict(zip(d["name"],d["position"])),velocity=dict(zip(d["name"],d["velocity"])))))
        elif topic=="/imu/data":
            r,p,_=quaternion_rpy(tuple(d["orientation"][k] for k in ("x","y","z","w")))
            imu.append((t,vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x","y","z")),r,p,config["policy_v2"]["imu_includes_gravity"])))
        elif topic.startswith("/nino/contact_lab/"):
            component=topic.rsplit("/",1)[-1]
            floor_loaded=False
            for contact in d["contacts"]:
                names=contact["collision1"]["name"]+contact["collision2"]["name"]
                loaded=any(depth>0 and math.sqrt(sum(w["body_1_wrench"]["force"][k]**2 for k in ("x","y","z")))>1e-6
                           for depth,w in zip(contact["depths"],contact["wrenches"]))
                if "terrain_collision" in names and loaded:floor_loaded=True
                if "cable_bumps" in names and loaded and tc<=t<=data["end"]:last_loaded=max(t,last_loaded or t)
            for side in supports:
                if component==f"caster_{side}_wheel" and tc-.3<=t<=tc-.05:supports[side].append(float(floor_loaded))
    for series in (poses,joints,imu):series.sort(key=lambda p:p[0])
    approach=[p for t,p in poses if tc-.3<=t<=tc-.05]
    if not approach:return {**result,"reason":"missing_precontact_pose"}
    pre={k:summary([p[k] for p in approach]) for k in ("v","w","y","yaw","roll","pitch")}
    pre["window_s"]=[tc-.3,tc-.05]
    pre["coverage_fraction"]=signal_stats([(t,p["v"]) for t,p in poses],tc-.3,tc-.05)["coverage_fraction"]
    pre["caster"]={}
    for side,values in supports.items():
        chosen=[p for t,p in joints if tc-.3<=t<=tc-.05]
        rate=sum(values)/len(values) if values else None
        pre["caster"][side]=dict(floor_loaded_fraction=rate,
            load_class="unavailable" if rate is None else "loaded" if rate>=.8 else "unloaded" if rate<=.2 else "mixed",
            rolling_rad_s=summary([p["velocity"][f"caster_{side}_wheel_joint"] for p in chosen]),
            swivel_rate_rad_s=summary([p["velocity"][f"caster_{side}_swivel_joint"] for p in chosen]),
            last_swivel_rad=chosen[-1]["position"][f"caster_{side}_swivel_joint"] if chosen else None,
            qualification="Privileged diagnostic; low rotation of an unloaded caster is not a slip/failure criterion.")
    settle=[p for t,p in poses if data["start"]-.5<=t<=data["start"]]
    reset=dict(window_s=[data["start"]-.5,data["start"]],samples=len(settle),
        max_abs_v_m_s=max((abs(p["v"]) for p in settle),default=None),max_abs_w_rad_s=max((abs(p["w"]) for p in settle),default=None),
        qualification="Passive historical measurement only; no new online reset/settling barrier implemented.")
    events=[json.loads(l) for l in (logger/"contact_events.jsonl").open()]
    end=closed_contact_end(events,tc,data["end"])
    if last_loaded is not None and end.get("last_end_upper_bound_s") is not None and last_loaded>end["last_end_upper_bound_s"]+1e-9:
        end.update(available=False,reason="loaded_sample_after_reported_manifold_end")
    contact_end=max(row["clearance_s"],end["last_end_upper_bound_s"]+.2) if end.get("available") and row.get("clearance_s") is not None else None
    command_recovery=body_recovery=None
    if contact_end is not None:
        command_recovery=sustained([(float(c["governor_input_time_s"]),c) for c in data["controls"]],contact_end,data["end"],
            lambda c:c["governor_phase"]=="CRUISE" and float(c["governor_scale"])>=.98,duration=.3,max_gap=.100000001)
        # Verify the final driver command independently of requested scale.
        executed=sustained(drive,contact_end,data["end"],lambda d:d["executed_linear_m_s"]>=.98*.4)
        if not executed:command_recovery=None
        elif command_recovery:command_recovery["confirmed_s"]=max(command_recovery["confirmed_s"],executed["confirmed_s"])
        body_recovery=sustained([(t,p["v"]) for t,p in poses],contact_end,data["end"],lambda v:v>=.95*pre["v"]["median"])
    windows=sequence_windows(tc,row.get("clearance_s"),end,data["end"],command_recovery,body_recovery)
    measures={}
    bounds={"legacy_crossing":(tc+.05,row.get("clearance_s")),"fixed_3s_after_contact":(tc,tc+3.)}
    if windows.get("available"):bounds["whole_contact_sequence"]=(tc,windows["contact_end_s"])
    if windows.get("recovery_available"):bounds["contact_and_confirmed_recovery"]=(tc,windows["recovery_end_s"])
    for name,(a,b) in bounds.items():
        if b is None or b>data["end"]:measures[name]=dict(available=False,reason="censored_or_missing_end");continue
        measures[name]=dict(slip=integrate(signal,a,b),vertical=signal_stats(imu,a,b),duration_s=b-a)
    reduced=next((float(c["governor_input_time_s"]) for c in data["controls"] if float(c["governor_scale"])<.999),None)
    negative=negative_support(signal,tc,.05,reduced)
    if negative["available"]:negative["GT_slip"]=integrate(signal,tc,tc+.05)
    changes=[];previous=0
    for c in data["controls"]:
        count=int(c["governor_events"])
        if count>previous:changes.append(dict(time_s=float(c["governor_input_time_s"]),event=count,phase=c["governor_phase"]))
        previous=count
    return dict(**{k:v for k,v in result.items() if k!="available"},available=True,approach=pre,reset=reset,
        contact_end=end,last_loaded_contact_sample_s=last_loaded,windows=windows,metrics=measures,
        negative_control=negative,all_triggers=changes,command_recovery=command_recovery,body_recovery=body_recovery,
        native_metrics_untouched=True,diagnostic_only_not_new_candidate_validation=True)


def planned_protocol(run):
    config=run/"frozen_reactive.yaml"
    world=run/"attempt_01/confirmation/height/scenario.sdf"
    return dict(status="prepared_offline_only_not_executed",revision="approach_contact_sequence_v1",
        rejected_candidate="delay_200ms",default_delay_seconds=0.,runtime_changes=False,
        reference_config=str(config),reference_config_sha256=sha(config),world=str(world),world_sha256=sha(world),
        fixed=dict(height_m=.006,x_m=3.1,yaw_deg=8.,cruise_m_s=.4,physics_dt_s=.001,control_dt_s=.1,
                   robot_PI_detector_ramp_observations="unchanged"),
        stage_A=dict(kind="PI_only_repeatability_not_intervention",maximum_attempts=4,
            order=[dict(seed=s,repeat=r,profile="full") for s,r in ((77400,1),(77401,1),(77401,2),(77400,2))],
            cold_start_per_attempt=True,no_retry=True,no_controller_search=True,execution_authorized_by_this_preparation=False),
        prospective_diagnostic_limits=dict(origin="Engineering preparation limits, not industry standards or retroactive scoring",
            reset_observe_seconds=.5,reset_max_abs_v_m_s=.01,reset_max_abs_w_rad_s=.03,
            approach_window_before_contact_s=[-.3,-.05],approach_speed_m_s=[.39,.41],
            approach_abs_y_m=.01,approach_abs_yaw_deg=2.,approach_abs_roll_pitch_deg=2.,
            paired_max_median_speed_difference_m_s=.005,paired_max_wrapped_yaw_difference_deg=1.,paired_max_median_y_difference_m=.005,
            caster_rule="Report loaded/unloaded/mixed support and circular angle differences; never force an unloaded caster to meet rolling-speed equality",
            enforcement="Analysis flags only so far; online reset gate not implemented, no caster teleport, no extra reset attempts"),
        outcomes=dict(legacy="Keep native/whole-route/crossing(first+50ms to plane+0.5m), physical arrivals and2sstop unchanged",
            new=["all contact identities and sampled loads","fixed3s after contact: peak/P95/RMS/slip integral/distance/time",
                 "complete contact sequence=max(clearance,last contact end+0.2s)",
                 "all retriggers and command/body recovery sustained0.3s, minimum forward progress, failures"],
            negative_control="First50ms GT slip only if all GT/joint quadrature support precedes first actual intervention; missing IMU stays missing",
            failure_rule="Retain every attempt, including approach flags/failures/censoring; never success-only averages or zero-imputation"),
        stop_and_decision=dict(stop_on="reporting/provenance/physical failure; no retry or replacement",
            stage_A_result="Four PI runs estimate a coarse repeatability range only; no confidence/power claim from n=2 perseed",
            balance_failed="Stop intervention planning; one supported setup correction at most, no new speed parameter",
            balance_passed="Report raw PI-PI differences across metrics, including contact order and negative control; specify smallest worthwhile effect/application cost and comparison budget BEFORE any intervention",
            unresolved_noise="If noise cannot be separated from effect within a justified affordable budget, stop predictive-governor H2 branch; no endless repeats",
            stage_B="No new candidate or run count selected now; separate predeclared randomized blocked experiment only after StageA review",
            gate_time_tracking="Existing limits unchanged: mean time<=18.5s and<=1.05xPI, mean physical RMSE<=1.05xPI",
            no_automatic_release=["Optuna","predictor","PPO","curriculum","hardware deployment"]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    run=args.run.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    guard={str(ROOT/p):h for p,h in json.loads((ROOT/"docs/governor_brake_delay_2026-10-16/input_sha256.json").read_text()).items()}
    for directory in (ROOT/"docs/governor_second_trigger_2026-10-16",ROOT/"src/nino_control",ROOT/"src/nino_rl/config"):
        for p in directory.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:guard[str(p)]=sha(p)
    changed=[p for p,h in guard.items() if not Path(p).is_file() or sha(Path(p))!=h]
    if changed:raise ValueError("Protected data changed before preparation")
    write(out/"protocol_before_future_runs.json",planned_protocol(run))
    rows=json.loads((run/"episodes.json").read_text());result=[]
    for row in rows:
        try:result.append(analyze(row))
        except Exception as error:result.append(dict(seed=row["seed"],arm=row["arm"],case=row["case"],
            native_physical_pass=row.get("physical_pass"),available=False,reason=f"{type(error).__name__}: {error}"))
    write(out/"historical_sequence_demonstration.json",result)
    changed=[p for p,h in guard.items() if not Path(p).is_file() or sha(Path(p))!=h]
    write(out/"preservation_before.json",guard)
    write(out/"preparation_status.json",dict(status="prepared_not_run",historical_rows=len(result),
        available=sum(bool(r["available"]) for r in result),protected_files=len(guard),changed_protected=changed,
        new_simulation_episodes=0,stage_A_executed=False,stage_B_authorized=False,delay_200ms_rejected=True,
        default_controller_changed=False,native_changed=False,study_scores_changed=False))
    shutil.copy2(Path(__file__),out/"prepare_script_snapshot.py")
    print((out/"preparation_status.json").read_text())


if __name__=="__main__":main()
