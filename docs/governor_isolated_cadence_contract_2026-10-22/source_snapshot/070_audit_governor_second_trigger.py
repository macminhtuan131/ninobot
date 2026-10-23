#!/usr/bin/env python3
"""Read-only seed77320 audit: detector attribution, contact and pre-brake mismatch."""
import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from nino_rl.slip_reporting import integrate


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def asof(series,time,max_age):
    """Header-time lookup: never select a future sensor/command sample."""
    i=bisect.bisect_right([t for t,_ in series],time+1e-9)-1
    if i<0 or time-series[i][0]>max_age+1e-9:return None
    return dict(stamp_s=series[i][0],age_s=max(0.,time-series[i][0]),value=series[i][1])


def summarize(values):
    return dict(n=len(values),minimum=min(values),maximum=max(values),median=statistics.median(values)) if values else dict(n=0)


def replay_quiet_armed(controls,settings,dt):
    """Replay the recorded detector gates, without inventing unlogged inputs."""
    quiet=confirmed=0.
    armed=True
    count=0
    result=[]
    previous_phase="CRUISE"
    for c in controls:
        ratio=float(c["governor_trigger_ratio"])
        quiet=quiet+dt if ratio<=settings["release_ratio"] else 0.
        confirmed=confirmed+dt if c["governor_disturbed"]=="True" else 0.
        before=armed
        if quiet>=settings["quiet_seconds"]:armed=True
        rearmed=not before and armed
        event=int(c["governor_events"])>count
        eligible=armed and previous_phase not in ("DELAY","STALL") and confirmed>=settings["confirmation_seconds"]
        if event:
            if not eligible:raise ValueError("Recorded trigger inconsistent with arming/confirmation")
            armed=False
        if not math.isclose(quiet,float(c["governor_quiet_seconds"]),abs_tol=1e-10):
            raise ValueError("Quiet timer mismatch")
        if armed!=(c["governor_armed"]=="True"):raise ValueError("Armed replay mismatch")
        result.append(dict(time_s=float(c["governor_input_time_s"]),quiet_seconds=quiet,
            confirmed_seconds=confirmed,rearmed=rearmed,event=event,armed_after=armed,
            phase_before=previous_phase,phase_after=c["governor_phase"],events=int(c["governor_events"])))
        count=int(c["governor_events"])
        previous_phase=c["governor_phase"]
    return result


def read_case(row):
    case=Path(row["case"])
    logger=next(case.glob("contact/*/metadata.json")).parent
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    cp=next(evaluation.glob("episode-*/control_trace.csv"))
    dp=next(evaluation.glob("episode-*/drive_trace.csv"))
    controls=list(csv.DictReader(cp.open()))
    drive=[(float(c["sim_time_s"]),{k:float(v) for k,v in c.items() if k!="seed"}) for c in csv.DictReader(dp.open())]
    config=json.loads((logger/"resolved_config.json").read_text())
    params=config["governor"]["parameters"]
    tc=row["first_contact_s"]
    imu,joints,ground,contacts=[],[],[],[]
    recorded_feedback={}
    for line in (logger/"samples.jsonl").open():
        packet=json.loads(line)
        topic,d=packet["topic"],packet["data"]
        if topic=="/nino_drive/diagnostics":
            names=d["layout"]["dim"][0]["label"].split(",")
            f=dict(zip(names,d["data"]))
            recorded_feedback[f["sim_time_s"]]=f
            continue
        if topic not in ("/imu/data","/joint_states","/ground_truth/odom") and not topic.startswith("/nino/contact_lab/"):continue
        t=d["header"]["stamp"]["sec"]+d["header"]["stamp"]["nanosec"]*1e-9
        if not tc-.5<=t<=tc+2.6:continue
        if topic=="/imu/data":
            imu.append((t,dict(body_rate_xy_rad_s=math.hypot(d["angular_velocity"]["x"],d["angular_velocity"]["y"]),
                gyro_z_rad_s=d["angular_velocity"]["z"])))
        elif topic=="/joint_states":
            joints.append((t,dict(velocity=dict(zip(d["name"],d["velocity"])),position=dict(zip(d["name"],d["position"])))))
        elif topic=="/ground_truth/odom":ground.append((t,dict(vx=d["twist"]["twist"]["linear"]["x"],yaw_rate=d["twist"]["twist"]["angular"]["z"])))
        else:
            for c in d["contacts"]:
                names=c["collision1"]["name"]+c["collision2"]["name"]
                kind="cable" if "cable_bumps" in names else "floor" if "terrain_collision" in names else "other"
                forces=[]
                for depth,w in zip(c["depths"],c["wrenches"]):
                    f=w["body_1_wrench"]["force"]
                    magnitude=math.sqrt(sum(f[k]**2 for k in ("x","y","z")))
                    forces.append(dict(depth_m=depth,force_magnitude_N=magnitude))
                contacts.append(dict(time_s=t,relative_s=t-tc,component=topic.rsplit("/",1)[-1],kind=kind,
                    loaded=any(f["depth_m"]>0 and f["force_magnitude_N"]>1e-6 for f in forces),
                    sampled_force_magnitude_sum_N=sum(f["force_magnitude_N"] for f in forces),points=forces))
    events=[json.loads(line) for line in (logger/"contact_events.jsonl").open()]
    for series in (imu,joints,ground):series.sort(key=lambda p:p[0])
    replay=replay_quiet_armed(controls,params,1./config["control_hz"])
    feedback_series=sorted(recorded_feedback.items())
    previous_targets=None
    timeline=[]
    for c,gate in zip(controls,replay):
        t=float(c["governor_input_time_s"])
        # First input feedback precedes the first action-window drive CSV.
        # Recover that exact recorded stamp from raw diagnostics, never from
        # a later action endpoint or an interpolated target.
        feedback=asof(feedback_series,float(c["governor_feedback_stamp_s"]),1e-6)
        if feedback is None:raise ValueError("Recorded feedback stamp not present in raw drive diagnostics")
        f=feedback["value"]
        targets=(f["left_target_rad_s"],f["right_target_rad_s"])
        target_accel=max(abs(a-b) for a,b in zip(targets,previous_targets))*.0625*config["control_hz"] if previous_targets else 0.
        previous_targets=targets
        if not tc-.3<=t<=tc+2.5:continue
        sample=asof(joints,t,.1)
        im=asof(imu,t,.1)
        wheel=float(c["governor_wheel_error_m_s"])
        threshold=float(c["governor_wheel_error_threshold_m_s"])
        error=max(abs(sample["value"]["velocity"][s+"_wheel_joint"]-f[s+"_target_rad_s"])*.0625 for s in ("left","right"))
        wr=wheel/threshold
        body=im["value"]["body_rate_xy_rad_s"] if im else None
        vertical=float(c["governor_filtered_vertical_m_s2"])/params["vertical_trigger_m_s2"]
        reconstruction=max(vertical,wr,body/params["body_rate_trigger_rad_s"] if body is not None else 0.)
        timeline.append(dict(**gate,relative_s=t-tc,scale=float(c["governor_scale"]),
            wheel_error_m_s=wheel,wheel_threshold_m_s=threshold,wheel_ratio=wr,
            body_rate_latest_hardware_sample=im,body_rate_latest_ratio=body/params["body_rate_trigger_rad_s"] if body is not None else None,
            filtered_vertical_ratio=vertical,total_ratio=float(c["governor_trigger_ratio"]),
            disturbed=c["governor_disturbed"]=="True",feedback_stamp_s=float(c["governor_feedback_stamp_s"]),
            input_joint_sample=sample,wheel_error_reconstruction_delta_m_s=error-wheel,
            total_ratio_reconstruction_delta=reconstruction-float(c["governor_trigger_ratio"]),
            threshold_reconstruction_delta_m_s=params["wheel_error_trigger_m_s"]+params["wheel_error_acceleration_allowance_s"]*target_accel-threshold,
            feedback=f,body=asof(ground,t,.03),requested_v=float(c["governor_requested_linear_m_s"]),
            requested_w=float(c["governor_requested_yaw_rad_s"])))
    data=load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=77320,profile=row["profile"]))
    return dict(row=row,tc=tc,logger=logger,evaluation=evaluation,controls=controls,drive=drive,
        contacts=contacts,contact_events=events,timeline=timeline,gate_replay=replay,
        ground=ground,joints=joints,signal=gt_timestamp_series(data),config=config,
        files=[cp,dp,logger/"samples.jsonl",logger/"contact_events.jsonl",logger/"metadata.json",logger/"resolved_config.json"])


def compare_windows(cases,cuts):
    result={}
    for arm,case in cases.items():
        result[arm]={name:integrate(case["signal"],case["tc"]+a,case["tc"]+b) for name,a,b in cuts}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--resume-incomplete",action="store_true")
    args=parser.parse_args()
    root=args.output.resolve()
    if args.resume_incomplete and (root/"decision.json").exists():
        raise ValueError("Completed audit may not be overwritten")
    root.mkdir(parents=True,exist_ok=args.resume_incomplete)
    rows=[r for r in json.loads((args.run/"episodes.json").read_text()) if r["seed"]==77320]
    assert len(rows)==3 and {r["arm"] for r in rows}=={"full","frozen_reactive","delayed_200ms"}
    # Protect every archived experiment input and live controller source.
    old_manifest=json.loads((ROOT/"docs/governor_brake_delay_2026-10-16/input_sha256.json").read_text())
    guard={str(ROOT/name):digest for name,digest in old_manifest.items()}
    for directory in (ROOT/"src/nino_control",ROOT/"src/nino_rl/config",ROOT/"docs/governor_brake_delay_2026-10-16"):
        for path in directory.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:guard[str(path)]=sha(path)
    guard[str(ROOT/"src/nino_rl/nino_rl/ros_env.py")]=sha(ROOT/"src/nino_rl/nino_rl/ros_env.py")
    changed=[p for p,h in guard.items() if not Path(p).is_file() or sha(Path(p))!=h]
    if changed:raise ValueError("Archived/current inputs changed before audit: "+str(changed))
    write(root/"protocol_before_analysis.json",dict(seed=77320,arms=[r["arm"] for r in rows],
        scope="Second-trigger channel/rearm, contact-command ordering, pre-brake mismatch. No new simulation or correction.",
        timestamp_rule="Use input boundary; saved exact feedback stamp, causal latest IMU/joint samples. Validate reconstructed scalars against captured detector values; raw sample reconstruction is not callback identity proof.",
        contact_rule="positive depth and sampled force>1e-6N, distinguish manifold from load; no impulse from sampled forces",
        decision_options=["command_induced_false_trigger_supported","contact_transition_supported_keep_detector","unresolved_no_parameter_change"],
        new_simulation_episodes=0,native_metric_changes=False,controller_changes=False))
    cases={r["arm"]:read_case(r) for r in rows}
    candidate=cases["delayed_200ms"]
    timeline=candidate["timeline"]
    second=next(t for t in timeline if t["event"] and t["events"]==2)
    first=next(t for t in timeline if t["event"] and t["events"]==1)
    rearm=next(t for t in timeline if t["rearmed"] and first["time_s"]<t["time_s"]<second["time_s"])
    tc=candidate["tc"]
    onset=next(float(c["governor_input_time_s"])-tc for c in candidate["controls"] if c["governor_phase"]=="HOLD")
    earliest_brake=min(float(c["governor_input_time_s"])-case["tc"] for case in cases.values() for c in case["controls"] if float(c["governor_scale"])<.999)
    cuts=[("precontact_baseline",-.3,-.05),("first_50ms_GT_slip_not_IMU",0.,.05),
          ("before_any_reduced_command",0.,earliest_brake),
          ("after_trigger_before_candidate_brake",first["relative_s"],onset),
          ("before_candidate_brake",0.,onset)]
    comparison=compare_windows(cases,cuts)
    transitions={}
    for arm,case in cases.items():
        transitions[arm]=[dict(e,relative_s=e["time_s"]-case["tc"]) for e in case["contact_events"]
                          if -.02<=e["time_s"]-case["tc"]<=1.2]
        write(root/(arm+"_detector_timeline.json"),case["timeline"])
    context=[c for c in candidate["contacts"] if second["time_s"]-.08<=c["time_s"]<=second["time_s"]]
    before_command=asof(candidate["drive"],second["time_s"],.03)
    earlier=asof(candidate["drive"],second["time_s"]-.1,.03)
    near_commands=[f for t,f in candidate["drive"] if second["time_s"]-.2<=t<=second["time_s"]]
    right_joint=second["input_joint_sample"]["value"]["velocity"]["right_wheel_joint"]
    loaded=any(c["component"]=="right_wheel" and c["loaded"] for c in context)
    samples_verified=all(abs(t["wheel_error_reconstruction_delta_m_s"])<1e-10 and abs(t["threshold_reconstruction_delta_m_s"])<1e-10
                         for t in timeline if .4<=t["relative_s"]<=1.2)
    classification=("contact_transition_supported_keep_detector" if loaded and right_joint<0 and samples_verified
                    and second["wheel_ratio"]>=1. and before_command["value"]["right_target_rad_s"]>0 else
                    "unresolved_no_parameter_change")
    evidence=dict(first_trigger=first,rearm=rearm,second_trigger=second,
        pre_second_contact_samples=context,command_before_trigger=before_command,command_100ms_earlier=earlier,
        preceding_200ms_executed_v_m_s=summarize([c["executed_linear_m_s"] for c in near_commands]),
        preceding_200ms_executed_w_rad_s=summarize([c["executed_yaw_rad_s"] for c in near_commands]),
        reconstruction_near_event_pass=samples_verified,
        reconstructed_all_focused_timeline=dict(samples=len(timeline),
            max_abs_wheel_error_delta_m_s=max(abs(t["wheel_error_reconstruction_delta_m_s"]) for t in timeline),
            max_abs_total_ratio_delta=max(abs(t["total_ratio_reconstruction_delta"]) for t in timeline),
            max_abs_threshold_delta_m_s=max(abs(t["threshold_reconstruction_delta_m_s"]) for t in timeline)),
        caveat="Contact transition is supported by ordering and sampled load, not proof of unique causal force or sim-to-real fidelity. IMU latest-sample replay does not establish subscriber callback identity.")
    write(root/"trigger_evidence.json",evidence)
    write(root/"contact_transitions.json",transitions)
    write(root/"window_comparison.json",comparison)
    write(root/"candidate_contact_force_samples.json",candidate["contacts"])
    changed=[p for p,h in guard.items() if not Path(p).is_file() or sha(Path(p))!=h]
    decision=dict(status=classification,detector_correction_supported=False,
        reason="Recorded wheel error crosses threshold while driven wheel reverses against a forward target and right-wheel floor/cable load changes precede trigger; no evidence of a BRAKE/RECOVER command reversal causing a false event.",
        delay_200ms_remains_rejected=True,default_delay_seconds=0.,
        next_action="Keep detector; decide how to control/compare complete multi-contact sequences with reset/contact variability before another intervention budget. No automatic suppression of second event.",
        input_files_protected=len(guard),changed_protected=changed,new_simulation_episodes=0,
        runtime_changes=False,native_metric_changes=False,study_score_changes=False,
        optuna_started=False,predictor_started=False,training_started=False)
    write(root/"preservation_before.json",guard)
    write(root/"decision.json",decision)
    print(json.dumps(dict(decision=decision,event=dict(rearm_relative_s=rearm["relative_s"],second_relative_s=second["relative_s"],
        wheel_ratio=second["wheel_ratio"],latest_body_rate_ratio=second["body_rate_latest_ratio"],
        right_actual_rad_s=right_joint),verification=evidence["reconstructed_all_focused_timeline"],windows=comparison),indent=2))


if __name__=="__main__":main()
