#!/usr/bin/env python3
"""One bounded closed-loop negative-control batch on the corrected box floor."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from run_clear_floor_repeat import ROOT, resolve, stop_owned


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=76300)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    (output/"runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    launch=probe=None
    result=dict(complete=False,passed=False,physical_arrival_evaluation=False,training_started=False,optuna_started=False)
    try:
        with (output/"gazebo.log").open("w") as stream:
            launch=subprocess.Popen(["ros2","launch","nino_rl","factory_floor_governor.launch.py",
                "variant:=clear_box","headless:=true","caster_wheel_damping:=0.001",
                f"config:={args.config.resolve()}",f"output_directory:={output/'contact'}"],
                cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            deadline=time.monotonic()+360
            while True:
                if launch.poll() is not None:raise RuntimeError("Owned simulator exited during startup")
                try:
                    logger=resolve(output/"contact","metadata.json")
                    metadata=json.loads((logger/"metadata.json").read_text())
                    if metadata.get("robot_description_validated") and "Effort drive ready:" in (output/"gazebo.log").read_text():break
                except (ValueError,FileNotFoundError):pass
                if time.monotonic()>deadline:raise TimeoutError("Startup deadline")
                time.sleep(.5)
            result["logger"]=str(logger)
            with (output/"probe.log").open("w") as log:
                probe=subprocess.Popen([sys.executable,str(ROOT/"src/nino_rl/scripts/run_governor_foundation_probe.py"),
                    "--run","--case","all","--variant","clear_box","--config",str(args.config.resolve()),
                    "--seed",str(args.seed),"--logger",str(logger),"--output",str(output/"probe")],
                    cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                probe.wait(timeout=420)
            result["probe_returncode"]=probe.returncode
            summary_path=resolve(output/"probe","summary.json")/"summary.json"
            summary=json.loads(summary_path.read_text())
            result.update(summary=str(summary_path),results=summary["results"],complete=summary["complete"])
            result["passed"]=(probe.returncode==0 and summary["complete"] and len(summary["results"])==3 and
                all(r["complete"] and not r["terminated"] and r["events"]==0 and r["minimum_scale"]==1.
                    for r in summary["results"]))
    except BaseException as error:
        result["error"]=f"{type(error).__name__}: {error}"
    finally:
        for process in (probe,launch):
            if process is not None:stop_owned(process)
        (output/"summary.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2),flush=True)
    if not result["passed"]:raise SystemExit(1)


if __name__=="__main__":main()
