#!/usr/bin/env python3
"""Exactly two cold-start clean-floor command-path maneuvers; no tuning/retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_clear_floor_repeat import ROOT, resolve, stop_owned
from nino_rl.core import load_config
import yaml


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--domain",type=int,default=104)
    args=p.parse_args()
    root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    frozen=ROOT/"rl_runs/governor_frozen_repeats_2026-10-16/config.yaml"
    config=load_config(frozen)
    config["governor"]["parameters"]["profile"]="full"
    config["research_map"].update(revision="matched_clean_ramp_response_v1",training_allowed=False,optuna_allowed=False)
    config_path=root/"config.yaml"
    config_path.write_text(yaml.safe_dump(config,sort_keys=False))
    sources=[ROOT/"src/nino_rl/scripts/run_governor_foundation_probe.py",
             ROOT/"src/nino_rl/scripts/run_matched_ramp_probe.py",
             ROOT/"src/nino_rl/nino_rl/ros_env.py",ROOT/"src/nino_rl/nino_rl/ros_interface.py",
             ROOT/"src/nino_control/nino_control/effort_drive.py",
             ROOT/"src/nino_control/nino_control/governor_core.py",
             ROOT/"src/nino_control/config/effort_drive.yaml",
             ROOT/"src/nino_description/urdf/nino.urdf.xacro"]
    source_hashes={str(s):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}
    (root/"source_snapshot").mkdir()
    for index,source in enumerate(sources):
        (root/"source_snapshot"/f"{index:02d}_{source.name}").write_bytes(source.read_bytes())
    write(root/"protocol_before_results.json",dict(maximum_attempts=2,seeds=[77300,77301],
        variant="clear_box",case="matched_governor_ramp",duration_each_sim_s=12.,
        action="Scripted .400 cruise 7s; .384/.368/.360 at7.0/7.1/7.2s; .376/.392/.400 at8.0/8.1/8.2s; zero10s to12s",
        purpose="Isolate current PI/plant response from obstacle impact; not arrival/H2 quality validation",
        source_sha256=source_hashes,frozen_config_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest(),
        no_retry=True,no_tuning=True,no_training=True,physics_step_s=.001,control_interval_s=.1,
        stop_rule="Abort remaining attempt if process, clock, telemetry or physical termination fails; preserve all attempts",
        measurements="Raw reference, wheel targets, encoder and GT on native stamps; baseline6.7–6.95s, threshold/sustained40ms/gap25ms; report no-response/missing as unavailable",
        qualification="CAD-based simulation only; real caster dimensions remain unverified",
        domain=args.domain,partition=f"nino_clean_response_{args.domain}"))
    environment=os.environ.copy()
    environment.update(ROS_DOMAIN_ID=str(args.domain),NINO_ROS_DOMAIN_ID=str(args.domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",GZ_PARTITION=f"nino_clean_response_{args.domain}")
    attempts=[]
    for number,seed in enumerate((77300,77301),1):
        case=root/f"attempt_{number:02d}"
        case.mkdir()
        launch=probe=None
        result=dict(attempt=number,seed=seed,complete=False,passed=False)
        try:
            with (case/"gazebo.log").open("w") as stream:
                launch=subprocess.Popen(["ros2","launch","nino_rl","factory_floor_governor.launch.py",
                    "variant:=clear_box","headless:=true","caster_wheel_damping:=0.001",
                    f"config:={config_path}",f"output_directory:={case/'contact'}"],
                    cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+360
                while True:
                    if launch.poll() is not None:raise RuntimeError("Simulator exited at startup")
                    try:
                        logger=resolve(case/"contact","metadata.json")
                        meta=json.loads((logger/"metadata.json").read_text())
                        if meta.get("robot_description_validated") and "Effort drive ready:" in (case/"gazebo.log").read_text():break
                    except (ValueError,FileNotFoundError):pass
                    if time.monotonic()>deadline:raise TimeoutError("Startup deadline")
                    time.sleep(.5)
                result["logger"]=str(logger)
                with (case/"probe.log").open("w") as log:
                    probe=subprocess.Popen([sys.executable,str(ROOT/"src/nino_rl/scripts/run_governor_foundation_probe.py"),
                        "--run","--case","matched_governor_ramp","--variant","clear_box",
                        "--config",str(config_path),"--seed",str(seed),"--logger",str(logger),"--output",str(case/"probe")],
                        cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    probe.wait(timeout=420)
                result["returncode"]=probe.returncode
                summary_path=resolve(case/"probe","summary.json")/"summary.json"
                summary=json.loads(summary_path.read_text())
                result.update(summary=str(summary_path),results=summary["results"],complete=summary["complete"])
                result["passed"]=(probe.returncode==0 and summary["complete"] and len(summary["results"])==1
                    and all(r["steps"]==120 and not r["terminated"] and r["events"]==0
                            and r["minimum_scale"]==1. for r in summary["results"]))
        except BaseException as error:
            result["error"]=f"{type(error).__name__}: {error}"
        finally:
            for process in (probe,launch):
                if process is not None:stop_owned(process)
            attempts.append(result)
            write(case/"result.json",result)
            write(root/"attempts.json",attempts)
            print(json.dumps(result),flush=True)
        if not result["passed"]:break
    write(root/"decision.json",dict(attempts=len(attempts),execution_passed=len(attempts)==2 and all(a["passed"] for a in attempts),
        arrival_evaluation=False,H2_quality_validated=False,hardware_verified=False,
        no_tuning=True,no_retry=True,next="Audit raw response and final stopped window; no automatic promotion or extra attempts"))
    if not all(a["passed"] for a in attempts):raise SystemExit(1)


if __name__=="__main__":main()
