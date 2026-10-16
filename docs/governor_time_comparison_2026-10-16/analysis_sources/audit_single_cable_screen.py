#!/usr/bin/env python3
"""Observed first-contact timing and speed response; not an exact-state causal trial."""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl")]
from nino_control.governor_core import quaternion_rpy,vertical_acceleration
from analyze_governor_experiment import energy,stamp
from audit_clear_floor_stability import sustained_start
from nino_rl.core import load_config


def analyze(case,clearance_distance=.5):
    case=Path(case)
    evaluation=next((case/"evaluation").glob("*/summary.json")).parent
    logger=next((case/"contact").glob("*/metadata.json")).parent
    config=load_config(evaluation/"config.yaml")
    summary=json.loads((evaluation/"summary.json").read_text())
    paths=list(evaluation.glob("episode-*/control_trace.csv"))
    rows=list(csv.DictReader(paths[0].open())) if paths else []
    outcome=list(csv.DictReader((evaluation/"episodes.csv").open())) if (evaluation/"episodes.csv").exists() else []
    result=dict(case=str(case),evaluation=str(evaluation),logger=str(logger),
        complete=summary["complete"],outcome=outcome[0] if outcome else None,
        qualification="Sensor-triggered paired cold starts, not identical snapshots. Ground truth/contact are analysis-only.")
    if config.get("research_experiment", {}).get("oracle_contact_input"):
        result["qualification"]="Simulation-only post-contact oracle; controlled cold starts, not identical snapshots or deployable detector"
    if not rows:
        return {**result,"available":False,"reason":"no_control_trace"}
    lo=float(rows[0]["sim_time_s"])-float(rows[0]["elapsed_s"])
    hi=float(rows[-1]["sim_time_s"])
    run=rows[0].get("governor_run_id")
    contacts=[]
    for line in (logger/"contact_events.jsonl").open():
        row=json.loads(line)
        if row["event"]=="begin" and row.get("named_positive_obstacle") and lo<=row["time_s"]<=hi:
            if run and not str(row.get("episode","")).startswith(run+":"): continue
            contacts.append(row)
    if not contacts:
        return {**result,"available":False,"reason":"no_recorded_positive_contact"}
    first=min(contacts,key=lambda r:r["time_s"])
    t0=first["time_s"]
    per_component={}
    for c in sorted(contacts,key=lambda r:r["time_s"]):
        per_component.setdefault(c["component"],c["time_s"])
    # Near-simultaneous left/right contacts are reported, not treated as an
    # actionable horizon. A 50ms exclusion is a declared diagnostic window.
    next_contacts=[t for t in per_component.values() if t>=t0+.05]
    next_contact=min(next_contacts,default=None)
    next_drive=min((t for name,t in per_component.items() if name in ("left_wheel","right_wheel") and t>=t0+.05),default=None)
    imu=[];ground=[];joints=[]
    for line in (logger/"samples.jsonl").open():
        try: row=json.loads(line)
        except ValueError: continue
        d=row["data"]
        if "header" not in d: continue
        t=stamp(d)
        if not lo<=t<=hi: continue
        if row["topic"]=="/imu/data":
            q=d["orientation"];r,p,_=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
            imu.append((t,vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x","y","z")),r,p,
                config["policy_v2"]["imu_includes_gravity"])))
        elif row["topic"]=="/ground_truth/odom":
            ground.append((t,d["twist"]["twist"]["linear"]["x"],d["twist"]["twist"]["angular"]["z"],
                d["pose"]["pose"]["position"]["x"],d["pose"]["pose"]["position"]["y"]))
        elif row["topic"]=="/joint_states":
            joints.append((t,dict(zip(d["name"],d["velocity"]))))
    ground.sort();imu.sort()
    g=np.asarray(ground,dtype=float)
    approach=[v for t,v,*_ in ground if t0-.3<=t<t0]
    v0=float(np.median(approach)) if len(approach)>=5 else None
    body_slow=next((t for t,v,*_ in ground if t0<=t<=t0+2. and v0 is not None and v<=.9*v0),None)
    sustained_slow=(sustained_start([(t,v) for t,v,*_ in ground if t0<=t<=t0+2.],
        lambda v:v<=.9*v0,minimum_seconds=.06) if v0 is not None else None)
    actions=[(float(r["governor_input_time_s"]),float(r["governor_scale"])) for r in rows]
    before=[s for t,s in actions if t<t0]
    intervention=next((t for t,s in actions if t>=t0 and s<.999),None)
    event_times=[];event_details=[];previous_events=0
    for row in rows:
        count=int(row["governor_events"])
        if count>previous_events:
            when=float(row["governor_input_time_s"])
            event_times.append(when)
            interval=[v for t,v in imu if when-.100001<=t<=when+1e-6]
            event_details.append(dict(time_s=when,elapsed_s=when-lo,before_first_contact=when<t0,
                filtered_vertical_m_s2=float(row["governor_filtered_vertical_m_s2"]),
                wheel_error_m_s=float(row["governor_wheel_error_m_s"]),
                wheel_error_threshold_m_s=float(row["governor_wheel_error_threshold_m_s"]),
                reconstructed_interval_samples=len(interval),
                reconstructed_sample_rms_m_s2=float(np.sqrt(np.mean(np.square(interval)))) if interval else None,
                reconstructed_sample_peak_m_s2=max(map(abs,interval)) if interval else None))
        previous_events=count
    drive_path=paths[0].with_name("drive_trace.csv")
    drive=list(csv.DictReader(drive_path.open())) if drive_path.exists() else []
    motor=[(float(r["sim_time_s"]),.0625*.5*(float(r["left_target_rad_s"])+float(r["right_target_rad_s"]))) for r in drive]
    prior_targets=[v for t,v in motor if t0-.3<=t<t0]
    target0=float(np.median(prior_targets)) if len(prior_targets)>=5 else None
    target_drop=next((t for t,v in motor if t0<=t<=t0+2. and target0 is not None and v<=.9*target0),None)
    reduced_after=[(t,s) for t,s in actions if t>=t0 and s<.999]
    min_scale=min((s for _,s in reduced_after),default=None)
    min_scale_time=next((t for t,s in reduced_after if s==min_scale),None)
    recovered=next((t for t,s in actions if min_scale_time is not None and t>min_scale_time and s>=.999),None)
    slip=[]
    for t,v in joints:
        at=int(np.argmin(abs(g[:,0]-t))) if len(g) else None
        if at is None or abs(g[at,0]-t)>.025: continue
        body,yaw=g[at,1:3]
        values=[]
        for side,sign in (("left",-1),("right",1)):
            wheel=.0625*v[side+"_wheel_joint"]
            speed=body+sign*.34273666*.5*yaw
            values.append(float(np.clip((wheel-speed)/max(abs(wheel),abs(speed),.1),-5.,5.)))
        # sqrt(mean(slip^2)) integrates to the same mean square convention
        # used by the existing project metric, now on a fixed event window.
        slip.append((t,float(np.sqrt(np.mean(np.square(values))))))
    window_end=t0+2.
    local_slip=energy(slip,t0+.05,window_end,.025)
    local_acc=energy(imu,t0+.05,window_end,.05)
    selected=[r for r in ground if t0+.05<=r[0]<=window_end]
    distance=sum(np.hypot(b[3]-a[3],b[4]-a[4]) for a,b in zip(selected,selected[1:]) if b[0]-a[0]<=.05)
    slip_energy=(local_slip["rms"]**2*local_slip["coverage_s"]/distance
                 if local_slip["available"] and distance>.01 else None)
    world=json.loads((logger/"world_metadata.json").read_text())
    cables=world.get("cables",[])
    clearance=dict(available=False,reason="requires_one_straight_cable_scenario")
    if (len(cables)==1 and abs(cables[0].get("angle_deg",0.))<1e-6
            and config.get("routes",{}).get("fixed_route")=="E1"):
        clear_x=cables[0]["x_m"]+clearance_distance
        clear_time=next((t for t,_,_,x,_ in ground if t>=t0 and x>=clear_x),None)
        clearance=dict(available=False,reason="robot_did_not_reach_clearance",clear_x_m=clear_x,
            rule=f"Offline E1 analysis: body x reaches cable center + declared {clearance_distance:.2f}m; never controller input",
            clearance_distance_m=clearance_distance,end_time_s=clear_time)
        if clear_time is not None:
            local=energy(slip,t0+.05,clear_time,.025)
            accel=energy(imu,t0+.05,clear_time,.05)
            positions=[r for r in ground if t0+.05<=r[0]<=clear_time]
            travel=sum(np.hypot(b[3]-a[3],b[4]-a[4]) for a,b in zip(positions,positions[1:]) if b[0]-a[0]<=.05)
            available=local["available"] and accel["available"] and travel>.01
            clearance.update(available=bool(available),reason=None if available else "incomplete_sensor_or_distance_coverage",
                start_time_s=t0+.05,duration_s=clear_time-(t0+.05),distance_m=float(travel),
                acceleration=accel,slip=local,
                slip_energy_per_m=local["rms"]**2*local["coverage_s"]/travel if available else None,
                fits_in_original_2s_window=clear_time<=window_end)
    result.update(available=True,first_contact=first,first_contact_by_component_s=per_component,
        next_distinct_component_after_50ms_s=next_contact,
        next_driven_wheel_contact_s=next_drive,
        available_time_to_driven_wheel_s=next_drive-t0 if next_drive is not None else None,
        available_time_s=next_contact-t0 if next_contact else None,
        approach_body_speed_m_s=v0,precontact_minimum_scale=min(before) if before else None,
        scale_at_first_contact=before[-1] if before else None,
        postcontact_first_reduced_command_s=intervention,
        governor_event_times_s=event_times,
        governor_event_diagnostics=event_details,
        precontact_governor_event_times_s=[t for t in event_times if t<t0],
        approach_motor_target_m_s=target0,motor_target_drop_10percent_time_s=target_drop,
        motor_target_drop_delay_s=target_drop-t0 if target_drop is not None else None,
        body_slowdown_10percent_time_s=body_slow,
        body_slowdown_delay_s=body_slow-t0 if body_slow is not None else None,
        body_slowdown_sustained_60ms_time_s=sustained_slow,
        sustained_slowdown_before_next_contact=(sustained_slow<next_contact if sustained_slow is not None and next_contact is not None else None),
        sustained_slowdown_before_driven_wheel=(sustained_slow<next_drive if sustained_slow is not None and next_drive is not None else None),
        postcontact_minimum_scale=min_scale,first_recovered_scale_time_s=recovered,
        slowed_before_next_contact=body_slow<next_contact if body_slow is not None and next_contact is not None else None,
        body_speed_at_next_contact_m_s=float(g[np.argmin(abs(g[:,0]-next_contact)),1]) if next_contact is not None and len(g) else None,
        first_50ms_acceleration=energy(imu,t0,t0+.05,.05),
        postcontact_window_s=[t0+.05,window_end],postcontact_acceleration=local_acc,
        postcontact_slip=local_slip,postcontact_distance_m=float(distance),
        postcontact_slip_energy_per_m=slip_energy,
        postcontact_until_clearance=clearance,
        slip_qualification="Simulator GT longitudinal wheel-slip ratio; not a deployable IMU/encoder-only measurement",
        governor_events=outcome[0].get("governor_events") if outcome else None)
    return result


def plot_timing(results,output,title=None):
    """Saved signals only. Do not infer action causality from body slowing alone."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors={"full":"#333333","moderate":"#2378b5","pulse":"#df7c20"}
    fig,axes=plt.subplots(3,1,figsize=(11,8.5),sharex=True)
    for result in results:
        if not result.get("available"): continue
        profile=load_config(Path(result["evaluation"])/"config.yaml")["governor"]["parameters"]["profile"]
        color=colors[profile];first=result["first_contact"]["time_s"]
        trace=list(csv.DictReader(next(Path(result["evaluation"]).glob("episode-*/control_trace.csv")).open()))
        times=[float(r["governor_input_time_s"])-first for r in trace]
        axes[0].step(times,[float(r["governor_scale"]) for r in trace],where="post",label=result.get("controller_label",profile),color=color)
        body=[];imu=[]
        cfg=load_config(Path(result["evaluation"])/"config.yaml")
        for line in (Path(result["logger"])/"samples.jsonl").open():
            try: row=json.loads(line)
            except ValueError: continue
            d=row["data"]
            if "header" not in d: continue
            t=stamp(d)-first
            if not -4.<=t<=4.3: continue
            if row["topic"]=="/ground_truth/odom":body.append((t,d["twist"]["twist"]["linear"]["x"]))
            elif row["topic"]=="/imu/data":
                q=d["orientation"];roll,pitch,_=quaternion_rpy(tuple(q[k] for k in ("x","y","z","w")))
                imu.append((t,vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x","y","z")),roll,pitch,
                    cfg["policy_v2"]["imu_includes_gravity"])))
        body.sort();imu.sort()
        if body:axes[1].plot(*zip(*body),color=color,label=profile)
        if imu:axes[2].plot(*zip(*imu),color=color,alpha=.8,linewidth=1.)
        drive=list(csv.DictReader(next(Path(result["evaluation"]).glob("episode-*/drive_trace.csv")).open()))
        target=[(float(r["sim_time_s"])-first,.0625*.5*(float(r["left_target_rad_s"])+float(r["right_target_rad_s"]))) for r in drive]
        axes[1].plot(*zip(*target),color=color,linestyle="--",alpha=.65,linewidth=.9)
        driven=result.get("next_driven_wheel_contact_s")
        if driven is not None:
            t=driven-first
            axes[1].axvline(t,color=color,linestyle=":",alpha=.55)
    for ax in axes:
        ax.axvline(0.,color="#a11f32",linewidth=1.)
        ax.grid(alpha=.2);ax.set_xlim(-4.,4.3)
    axes[0].set_ylim(.65,1.04);axes[0].set_ylabel("Governor scale");axes[0].legend(loc="lower left",ncol=3)
    axes[1].set_ylabel("Forward speed (m/s)")
    axes[1].text(.02,.04,"Solid: body speed   Dashed: motor target   Dotted: first driven-wheel contact",transform=axes[1].transAxes,fontsize=8)
    axes[2].set_ylabel("Vertical acceleration (m/s²)");axes[2].set_xlabel("Time relative to first recorded bracket/cable contact (s)")
    fig.suptitle(title or "One rigid cable on box floor — seed 76200\nApproach speeds differ; body slowing includes the mechanical impact",fontsize=12)
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(output,dpi=160);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--clearance-distance",type=float,default=.5,
        help="Offline E1 clearance beyond cable center in metres, identical for all profiles")
    parser.add_argument("--plot",type=Path,help="Optional saved-signal timing figure")
    args=parser.parse_args()
    if not np.isfinite(args.clearance_distance) or args.clearance_distance<=0:
        parser.error("Clearance distance must be positive and finite")
    results=[]
    for case in sorted(args.screen.glob("seed_*")):
        try: results.append(analyze(case,args.clearance_distance))
        except Exception as error:
            results.append(dict(case=str(case),available=False,error=f"{type(error).__name__}: {error}"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(results=results,training_started=False,optuna_started=False),indent=2,allow_nan=False)+"\n")
    if args.plot:
        args.plot.parent.mkdir(parents=True,exist_ok=True)
        plot_timing(results,args.plot)
    print("Saved "+str(args.output))


if __name__=="__main__": main()
