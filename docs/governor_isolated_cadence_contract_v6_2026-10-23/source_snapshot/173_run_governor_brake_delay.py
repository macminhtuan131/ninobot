#!/usr/bin/env python3
"""One preregistered 200ms brake-delay hypothesis: six cold starts, no retry."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from run_governor_height_screen import make_height_world,sha,write
from run_frozen_governor_confirmation import analyze_batch
from run_governor_frozen_repeats import enrich
from summarize_contact_oracle_h2 import native_status

PLAN=ROOT/"docs/governor_height_screen_2026-10-16/next_delay_hypothesis_protocol.json"
FROZEN=ROOT/"rl_runs/governor_frozen_repeats_2026-10-16/config.yaml"
URDF="6e74ef55720b5878ddca1c60fe6a7b4e5d82b7a68aa4934d2d1a026451c4878b"


def configs(base):
    frozen=copy.deepcopy(base)
    frozen["governor"]["parameters"]["trigger_to_brake_delay_seconds"]=0.
    delayed=copy.deepcopy(frozen)
    delayed["governor"]["parameters"]["trigger_to_brake_delay_seconds"]=.2
    return dict(full=frozen,frozen_reactive=frozen,delayed_200ms=delayed)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--domain",type=int,default=106)
    args=parser.parse_args()
    plan=json.loads(PLAN.read_text())
    assert plan["maximum_new_episodes"]==len(plan["case_order"])==6
    assert sha(FROZEN)=="6ce2de78c09eb502e89ab6e81f614a2c0064a05bacc1995df5e421d58e5cb7f5"
    root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    candidates=configs(yaml.safe_load(FROZEN.read_text()))
    for arm,config in candidates.items():
        (root/(arm+".yaml")).write_text(yaml.safe_dump(config,sort_keys=False))
    shutil.copy2(PLAN,root/"prepared_protocol_snapshot.json")
    sources=[ROOT/"src/nino_rl/nino_rl"/n for n in ("ros_env.py","ros_interface.py","evaluation.py","slip_reporting.py")]
    sources += [ROOT/"src/nino_control/nino_control"/n for n in ("governor_core.py","effort_drive.py","control_timing.py")]
    sources += [Path(__file__).resolve(),ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"]
    (root/"source_snapshot").mkdir()
    for i,path in enumerate(sources):shutil.copy2(path,root/"source_snapshot"/f"{i:02d}_{path.name}")
    guard={}
    for directory in (ROOT/"docs/governor_height_screen_2026-10-16",ROOT/"rl_runs/governor_height_screen_2026-10-16",
                      ROOT/"docs/gt_governor_optuna_v2_2026-10-16",ROOT/"src/nino_rl/config",ROOT/"src/nino_control"):
        for path in directory.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:guard[str(path)]=sha(path)
    guard[str(FROZEN)]=sha(FROZEN)
    write(root/"preservation_before.json",guard)
    write(root/"protocol_before_results.json",dict(contract="governor_trigger_brake_delay_200ms_v1",
        prepared_protocol=plan,source_sha256={str(p):sha(p) for p in sources},
        domain=args.domain,partition=f"nino_brake_delay_{args.domain}",
        configuration_change="One parameter only: trigger_to_brake_delay_seconds 0 to0.2. Full arm uses existing profile override.",
        historical_wording_correction="Prepared hypothesis says wheel-first; observed6mm first manifold was caster-left. No assumed contact ordering in controller.",
        comparative_limits=dict(mean_time_ratio_max=1.05,mean_tracking_ratio_max=1.05,mean_time_s_max=18.5),
        quality_review="Both seed blocks, delayed vs frozen AND full: report crossing RMS and GT slip-square/m; mixed/no benefit rejects hypothesis. No p-value or win claim from n=2; favorable direction only merits separate confirmation.",
        authorized_source_change="Opt-in default-zero delay and added telemetry only; historical source snapshots/scores remain unchanged."))
    environment=os.environ.copy()
    environment.update(ROS_DOMAIN_ID=str(args.domain),NINO_ROS_DOMAIN_ID=str(args.domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",GZ_PARTITION=f"nino_brake_delay_{args.domain}")
    rows=[]
    stop=None
    for index,(seed,arm) in enumerate(plan["case_order"],1):
        block=root/f"attempt_{index:02d}"
        stage=block/"confirmation/height"
        stage.mkdir(parents=True)
        write(block/"protocol_before_results.json",dict(scenarios=[dict(id="height",x_m=3.1,angle_deg=8.,seeds=[seed])]))
        make_height_world(stage/"scenario.sdf",.006)
        profile="full" if arm=="full" else "reactive"
        command=[sys.executable,str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
            "--variant","cable_box_capsule","--config",str(root/(arm+".yaml")),"--profiles",profile,
            "--seeds",str(seed),"--world",str(stage/"scenario.sdf"),"--output",str(stage/"screen")]
        if profile=="full":command += ["--full-reference-speed",".4"]
        print("START",index,seed,arm,flush=True)
        row=dict(attempt=index,seed=seed,arm=arm,profile=profile,height_m=.006,
            reporting_pass=False,physical_pass=False,case=str(stage/"screen"/f"seed_{seed}_{profile}"))
        try:
            with (block/"run.log").open("w") as stream:
                result=subprocess.run(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
            row["runner_exit"]=result.returncode
            if not (stage/"screen/summary.json").is_file():
                row.update(native_status(Path(row["case"])))
                raise RuntimeError("No screen summary; retain unavailable attempt, no retry")
            analyze_batch(block)
            analyzed=json.loads((block/"confirmation_episodes.json").read_text())
            if len(analyzed)!=1:raise RuntimeError("Expected exactly one retained outcome")
            row.update(analyzed[0])
            enrich(row)
            row["provenance_pass"]=row["provenance"]["robot_description_sha256"]==URDF
            row["provenance_pass"] &= row["provenance"]["governor_core_sha256"]==sha(ROOT/"src/nino_control/nino_control/governor_core.py")
        except Exception as error:
            row["analysis_error"]=f"{type(error).__name__}: {error}"
            row["reporting_pass"]=False
        rows.append(row)
        write(root/"episodes.json",rows)
        print("END",index,arm,"physical",row.get("physical_pass"),"reporting",row.get("reporting_pass"),flush=True)
        if row.get("runner_exit")!=0 or not all(row.get(k) for k in ("physical_pass","reporting_pass","provenance_pass")):
            stop="reporting_physical_or_provenance_failure_no_retry"
            break
    changed=[name for name,digest in guard.items() if not Path(name).is_file() or sha(name)!=digest]
    write(root/"decision.json",dict(status=stop or "six_attempts_complete_offline_comparison_required",attempts=len(rows),
        unattempted=plan["case_order"][len(rows):],changed_protected=changed,protected_files=len(guard),
        source_changed=[str(p) for p in sources if sha(p)!=sha(root/"source_snapshot"/f"{sources.index(p):02d}_{p.name}")],
        no_retry=True,extra_episodes=False,tuning_started=False,training_started=False,predictor_started=False,
        hardware_validated=False))
    print((root/"decision.json").read_text(),flush=True)


if __name__=="__main__":main()
