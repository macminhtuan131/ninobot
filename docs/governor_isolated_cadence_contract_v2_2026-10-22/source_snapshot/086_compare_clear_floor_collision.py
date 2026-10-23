#!/usr/bin/env python3
"""Compare saved clear-floor mesh/box cold starts, retaining initialization aborts."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl")]
from audit_clear_floor_stability import audit,settling_audit
from nino_rl.core import load_config


def records(roots,label,output):
    results=[];aborted=[]
    for root in roots:
        for case in sorted(Path(root).glob("seed_*")):
            for state_path in case.glob("evaluation/*/summary.json"):
                evaluation=state_path.parent
                state=json.loads(state_path.read_text())
                if not state.get("complete") or not (evaluation/"episodes.csv").exists():
                    aborted.append(dict(case=str(case),summary=str(state_path),failure=state.get("aborted_episode")))
                    continue
                outcome=list(csv.DictReader((evaluation/"episodes.csv").open()))
                if len(outcome)!=1: raise ValueError("Expected a single-episode cold start")
                row=outcome[0];seed=int(row["seed"])
                loggers=list((case/"contact").glob("*/metadata.json"))
                if len(loggers)!=1: raise ValueError("Ambiguous logger provenance")
                logger=loggers[0].parent
                data=audit(evaluation,logger)
                trace=list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))
                data["post_arrival_stop"]=settling_audit(logger,float(trace[-1]["sim_time_s"]))
                directory=output/f"{label}_{seed}"
                directory.mkdir(parents=True,exist_ok=True)
                (directory/"audit.json").write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
                for source,name in ((state_path,"summary.json"),(evaluation/"config.yaml","config.yaml"),
                        (evaluation/"episodes.csv","episodes.csv"),(logger/"metadata.json","logger_metadata.json"),
                        (logger/"world_metadata.json","world_metadata.json")):
                    shutil.copy2(source,directory/name)
                contacts=data["contact_messages"]
                casters=[v for k,v in contacts.items() if k in ("caster_left_wheel","caster_right_wheel")]
                metrics=dict(label=label,seed=seed,success=row["success"]=="True",
                    time_s=float(row["time_seconds"]),physical_endpoint_error_m=float(row["truth_endpoint_error_m"]),
                    physical_rmse_m=float(row["truth_path_rmse_m"]),
                    vertical_rms_m_s2=float(row["rms_vertical_acceleration_m_s2"]),
                    vertical_peak_m_s2=float(row["peak_vertical_acceleration_m_s2"]),
                    slip_rms=float(row["rms_wheel_slip"]),max_abs_roll_deg=data["maximum_abs_roll_deg"],
                    max_abs_pitch_deg=data["maximum_abs_pitch_deg"],settled_2s=data["post_arrival_stop"]["settled"],
                    max_clock_error_s=float(row["max_clock_error_seconds"]),
                    max_motion_lag_s=float(row["max_motion_sensor_lag_seconds"]),
                    caster_peak_recorded_point_force_N=max((v["peak_abs_force_z_N"] for v in casters if v["peak_abs_force_z_N"] is not None),default=None),
                    opposing_vertical_normal_manifolds=sum(v["opposing_vertical_normal_manifolds"] for v in casters),
                    sampled_caster_manifolds=sum(v["manifolds_observed"] for v in casters),
                    motor_near_stopped_samples=sum(v["near_stopped_samples"] for v in data["driven_wheel_response"].values()),
                    max_motor_tracking_error_rad_s=max(v["maximum_abs_tracking_error_rad_s"] for v in data["driven_wheel_response"].values()),
                    evaluation=str(evaluation),logger=str(logger))
                results.append(metrics)
    return results,aborted


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh",type=Path,nargs="+",required=True)
    parser.add_argument("--box",type=Path,nargs="+",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    mesh,ma=records(args.mesh,"mesh",args.output)
    box,ba=records(args.box,"box",args.output)
    pairs=[]
    for baseline in mesh:
        candidates=[r for r in box if r["seed"]==baseline["seed"]]
        if len(candidates)!=1: raise ValueError("Expected one completed box match per mesh seed")
        candidate=candidates[0]
        configs=[load_config(Path(r["evaluation"])/"config.yaml") for r in (baseline,candidate)]
        configs[1]["simulation_model"].pop("floor_collision_control")
        metadata=[json.loads((Path(r["logger"])/"metadata.json").read_text()) for r in (baseline,candidate)]
        world=json.loads((Path(candidate["logger"])/"world_metadata.json").read_text())
        matching_config=configs[0]==configs[1]
        same_robot=metadata[0]["robot_description_sha256"]==metadata[1]["robot_description_sha256"]
        parent_matches=metadata[0]["world_sha256"]==world["diagnostic_control"]["parent_world_sha256"]
        pairs.append(dict(seed=baseline["seed"],same_config_except_floor_metadata=matching_config,
            same_URDF_sha256=same_robot,box_parent_matches_recorded_mesh_world=parent_matches))
        if not all((matching_config,same_robot,parent_matches)):
            raise ValueError("Physical comparison provenance mismatch")
    result=dict(qualification="Matched seeds and unchanged robot/PI, not restored identical simulator state or hardware validation",
        results=mesh+box,pair_checks=pairs,initialization_or_measurement_aborts=ma+ba,
        contact_qualification="Counts concern sampled manifolds. Point wrench maxima are not whole-body net force or impulse.",
        training_started=False,optuna_started=False)
    (args.output/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    with (args.output/"comparison.csv").open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=list((mesh+box)[0]));writer.writeheader();writer.writerows(mesh+box)
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()
