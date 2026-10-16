#!/usr/bin/env python3
"""Bounded clean-floor maneuvers, not arrival evaluation or PPO training.

Start factory_floor_governor.launch.py variant:=clear in the same domain.
Default prints the plan; --run executes it with existing timing/physical checks.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from nino_rl.core import load_config
from nino_rl.evaluation import prepare_evaluation_config
from nino_rl.trajectory_metrics import write_csv


CASES={
    "accelerate": [(0.,0.,0.),(.5,.4,0.),(3.,0.,0.)],
    "brake_recover": [(0.,.4,0.),(1.5,.18,0.),(2.5,.4,0.),(3.5,0.,0.)],
    "turn": [(0.,.25,0.),(1.5,.25,.4),(3.,.25,0.),(3.5,0.,0.)],
    "crossing": [(0.,.4,0.)],
}
CLEAN_CASES=("accelerate","brake_recover","turn")


def duration(case):
    return 10. if case=="crossing" else 4.


def command(case,elapsed):
    rows=[row for row in CASES[case] if row[0]<=elapsed+1e-8]
    return rows[-1][1:]


def verified_logger(path,config,variant):
    path=Path(path)
    if not (path/"metadata.json").is_file():
        candidates=list(path.glob("*/metadata.json"))
        if not candidates: raise ValueError("No logger metadata at "+str(path))
        path=max(candidates,key=lambda item:item.stat().st_mtime).parent
    metadata=json.loads((path/"metadata.json").read_text())
    world=json.loads((path/"world_metadata.json").read_text())
    expected=config.get("simulation_model",{}).get("caster_wheel_damping",.01)
    if (world["variant"]!=variant or not metadata.get("robot_description_validated") or
            any(abs(metadata.get("caster_wheel_damping_observed",{}).get(side,-1)-expected)>1e-12
                for side in ("left","right"))):
        raise ValueError("Logger world/model does not match probe contract")
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=[*CASES,"all"],default="all")
    parser.add_argument("--config",type=Path,default=ROOT/"src/nino_rl/config/factory_floor_governor_full.yaml")
    parser.add_argument("--seed",type=int,default=76100)
    parser.add_argument("--output",type=Path,default=ROOT/"rl_runs/governor_clean_floor")
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--logger",type=Path,help="Current logger directory; required for a physical-model candidate")
    parser.add_argument("--variant",choices=["clear","clear_box","cable","cable_box"],
                        help="Actual isolated world; negative maneuvers require a clear floor")
    args=parser.parse_args()
    cases=list(CLEAN_CASES) if args.case=="all" else [args.case]
    variant=args.variant or ("cable" if args.case=="crossing" else "clear")
    if (args.case=="crossing") != variant.startswith("cable"):
        parser.error("Crossing requires a cable world; negative maneuvers require a clear world")
    plan=dict(qualification="Bounded scripted maneuvers; not physical arrival evaluation",
              variant_required=variant,cases={case:CASES[case] for case in cases},
              duration_per_case_s={case:duration(case) for case in cases},seed=args.seed,
              profile=load_config(args.config)["governor"]["parameters"]["profile"],
              training_started=False,optuna_started=False)
    if not args.run:
        print(json.dumps(plan,indent=2)); return
    from nino_rl.governor_adapter import frame_from_state
    from nino_rl.ros_env import NinoGazeboEnv
    from nino_rl.control_v2 import BASELINE_ACTION
    from std_msgs.msg import String
    import yaml

    output=args.output/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
    output.mkdir(parents=True,exist_ok=False)
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    config=prepare_evaluation_config(load_config(args.config),baseline=True,route="E1",control_trace=True)
    logger=(verified_logger(args.logger,config,plan["variant_required"]) if args.logger else None)
    if config.get("simulation_model") and logger is None:
        parser.error("Physical-model candidates require --logger and observed URDF validation")
    plan["logger"]=str(logger) if logger else None
    source=Path(__file__).read_bytes()
    plan["runner_sha256"]=hashlib.sha256(source).hexdigest()
    (output/"runner_snapshot.py").write_bytes(source)
    if logger:
        for filename in ("metadata.json","world_metadata.json","robot_description.urdf"):
            (output/("logger_start_"+filename)).write_bytes((logger/filename).read_bytes())
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    (output/"config.yaml").write_text(yaml.safe_dump(config,sort_keys=False))

    class ProbeEnv(NinoGazeboEnv):
        def _governor_command(self,linear,angular):
            elapsed=self.lockstep_sim_time-self.episode_started_sim
            linear,angular=command(self.case,elapsed)
            end=self.lockstep_sim_time
            rows=self.ros.drive_diagnostics(end-.25,end+1e-6)
            self.probe_frame=(asdict(frame_from_state(self.previous_robot_state,rows[-1],
                self.governor_imu,self.ros.imu_includes_gravity)) if rows else {})
            return super()._governor_command(linear,angular)

    env=None
    results=[]
    try:
        env=ProbeEnv(config,total_training_steps=1)
        for index,case in enumerate(cases):
            env.case=case
            _,reset=env.reset(seed=args.seed+index)
            directory=output/case
            directory.mkdir()
            rows=[]
            result=dict(case=case,seed=args.seed+index,complete=False,bounded_probe=True,
                        arrival_evaluation=False,terminated=False,termination=None,
                        run_id=env.governor_run_id,attempt=env.attempt_number,
                        started_sim_s=env.lockstep_sim_time)
            try:
                for _ in range(round(duration(case)/env.control_dt)):
                    _,_,terminated,truncated,info=env.step(BASELINE_ACTION.copy())
                    row={**info["control_trace"],**env.probe_frame,"dt":env.control_dt}
                    rows.append(row)
                    write_csv(directory/"trace.csv",rows)  # Preserve completed steps on interruption.
                    if terminated or truncated:
                        result.update(terminated=True,termination=info.get("episode_metrics",{}).get("termination","episode_ended"),
                                      episode_metrics=info.get("episode_metrics"))
                        break
                result.update(complete=True,steps=len(rows),events=env.governor.events,
                              minimum_scale=min(row["governor_scale"] for row in rows),
                              clock_error_s=env.max_clock_error)
            except BaseException as error:
                result["error"]=str(error)
                raise
            finally:
                (directory/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
                env.ros.publish_motion_command(0.,0.)
                env.governor_episode_publisher.publish(String(data=json.dumps(dict(
                    event="probe_end",run_id=env.governor_run_id,attempt=env.attempt_number,
                    time_s=env.lockstep_sim_time,result=result))))
                results.append(result)
                print(json.dumps(result),flush=True)
    finally:
        if env is not None: env.close()
        (output/"summary.json").write_text(json.dumps(dict(plan=plan,results=results,
            complete=len(results)==len(cases) and all(row["complete"] for row in results)),indent=2)+"\n")
        print("Saved "+str(output),flush=True)


if __name__=="__main__":
    main()
