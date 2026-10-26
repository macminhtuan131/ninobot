#!/usr/bin/env python3
"""Locked four-attempt PI-only batch with post-reset standstill initialization."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from run_governor_height_screen import sha,write
from run_frozen_governor_confirmation import analyze_batch
from run_governor_frozen_repeats import enrich
from summarize_contact_oracle_h2 import native_status
from prepare_governor_contact_sequence import analyze as sequence_analysis

PLAN=ROOT/"docs/governor_approach_sequence_plan_2026-10-16/protocol_before_future_runs.json"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--domain",type=int,default=107)
    args=parser.parse_args()
    plan=json.loads(PLAN.read_text())
    jobs=plan["stage_A"]["order"]
    assert len(jobs)==plan["stage_A"]["maximum_attempts"]==4
    assert [(j["seed"],j["repeat"],j["profile"]) for j in jobs]==[(77400,1,"full"),(77401,1,"full"),(77401,2,"full"),(77400,2,"full")]
    frozen=Path(plan["reference_config"]);world=Path(plan["world"])
    assert sha(frozen)==plan["reference_config_sha256"] and sha(world)==plan["world_sha256"]
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    values=yaml.safe_load(frozen.read_text())
    assert values["governor"]["parameters"]["trigger_to_brake_delay_seconds"]==0.
    values["reset_standstill_gate"]=dict(enabled=True,revision="post_reset_zero_standstill_v1")
    (root/"config.yaml").write_text(yaml.safe_dump(values,sort_keys=False))
    shutil.copy2(PLAN,root/"prepared_protocol_snapshot.json")
    sources=[ROOT/"src/nino_rl/nino_rl"/n for n in ("ros_env.py","ros_interface.py","evaluation.py","reset_standstill.py","slip_reporting.py")]
    sources += [ROOT/"src/nino_control/nino_control"/n for n in ("governor_core.py","effort_drive.py","control_timing.py")]
    sources += [Path(__file__).resolve(),ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py",ROOT/"src/nino_rl/scripts/prepare_governor_contact_sequence.py"]
    (root/"source_snapshot").mkdir()
    for i,p in enumerate(sources):shutil.copy2(p,root/"source_snapshot"/f"{i:02d}_{p.name}")
    guard={}
    for directory in (ROOT/"docs/governor_approach_sequence_plan_2026-10-16",ROOT/"docs/governor_second_trigger_2026-10-16",
                      ROOT/"docs/governor_brake_delay_2026-10-16",ROOT/"docs/gt_governor_optuna_v2_2026-10-16",
                      ROOT/"src/nino_control",ROOT/"src/nino_rl/config"):
        for p in directory.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:guard[str(p)]=sha(p)
    archived=json.loads((ROOT/"docs/governor_brake_delay_2026-10-16/input_sha256.json").read_text())
    guard.update({str(ROOT/p):h for p,h in archived.items()})
    write(root/"preservation_before.json",guard)
    write(root/"protocol_before_results.json",dict(contract="PI_repeatability_post_reset_standstill_v1_2026_10_17",
        prepared_protocol=plan,maximum_attempts=4,source_sha256={str(p):sha(p) for p in sources},
        initialization_only_change="Zero commands, bounded5simulationseconds, continuous0.5s post-mutation measured standstill; episode time begins after release; gate wait logged separately",
        historical_sources="Authorized opt-in initialization/reporting code change; old source snapshots, controller/configs and study scores preserved",
        gate_failure="Readiness/measurement failure retained as attempt with task outcome unavailable, stop with no retry",
        execution="Sequential cold starts, one owned simulator, no exact-snapshot or hardware claim",domain=args.domain,
        partition=f"nino_pi_standstill_{args.domain}",new_intervention=False))
    environment=os.environ.copy()
    environment.update(ROS_DOMAIN_ID=str(args.domain),NINO_ROS_DOMAIN_ID=str(args.domain),
        ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",GZ_PARTITION=f"nino_pi_standstill_{args.domain}")
    rows=[];stop=None
    for index,job in enumerate(jobs,1):
        seed=job["seed"];block=root/f"attempt_{index:02d}";stage=block/"confirmation/height"
        stage.mkdir(parents=True)
        shutil.copy2(world,stage/"scenario.sdf");shutil.copy2(world.with_suffix(".json"),stage/"scenario.json")
        write(block/"protocol_before_results.json",dict(scenarios=[dict(id="height",x_m=3.1,angle_deg=8.,seeds=[seed])]))
        row=dict(attempt=index,seed=seed,repeat=job["repeat"],arm="full",profile="full",height_m=.006,
            case=str(stage/"screen"/f"seed_{seed}_full"),status="starting",physical_pass=None,reporting_pass=False,reset_gate_pass=False)
        write(root/"attempts_ledger.json",rows+[row])
        command=[sys.executable,str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),"--variant","cable_box_capsule",
            "--config",str(root/"config.yaml"),"--world",str(stage/"scenario.sdf"),"--profiles","full",
            "--full-reference-speed",".4","--seeds",str(seed),"--output",str(stage/"screen")]
        print("START",index,seed,"repeat",job["repeat"],flush=True)
        try:
            with (block/"run.log").open("w") as stream:
                execution=subprocess.run(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
            row["runner_exit"]=execution.returncode
            case=Path(row["case"])
            gate_files=list(case.glob("evaluation/*/reset_standstill_001.json"))
            if len(gate_files)==1:
                row["reset_gate"]=json.loads(gate_files[0].read_text())
                row["reset_gate_pass"]=row["reset_gate"].get("passed",False)
            if not row["reset_gate_pass"]:
                row.update(native_status(case))
                raise RuntimeError("Post-reset gate unavailable or failed; physical task outcome not invented")
            if not (stage/"screen/summary.json").is_file():
                row.update(native_status(case));raise RuntimeError("Missing screen outcome")
            analyze_batch(block)
            analyzed=json.loads((block/"confirmation_episodes.json").read_text())
            if len(analyzed)!=1:raise RuntimeError("Expected exactly one retained episode")
            row.update(analyzed[0]);enrich(row)
            row["sequence"]=sequence_analysis(row)
            row["provenance_pass"]=row["world_sha256"]==plan["world_sha256"] and row["provenance"]["robot_description_sha256"]=="6e74ef55720b5878ddca1c60fe6a7b4e5d82b7a68aa4934d2d1a026451c4878b"
            row["status"]="completed"
        except Exception as error:
            row["error"]=f"{type(error).__name__}: {error}"
            row["status"]="failed_attempt_no_retry"
        rows.append(row);write(root/"episodes.json",rows);write(root/"attempts_ledger.json",rows)
        print("END",index,"gate",row["reset_gate_pass"],"physical",row.get("physical_pass"),"reporting",row["reporting_pass"],flush=True)
        if row.get("runner_exit")!=0 or not all(row.get(k) for k in ("reset_gate_pass","physical_pass","reporting_pass","provenance_pass")):
            stop="readiness_reporting_provenance_or_physical_failure_stop_no_retry";break
        if not row["sequence"].get("available"):
            stop="new_sequence_report_unavailable_stop_no_retry";break
    changed=[p for p,h in guard.items() if not Path(p).is_file() or sha(Path(p))!=h]
    write(root/"decision.json",dict(status=stop or "four_PI_attempts_complete_repeatability_review_required",attempts=len(rows),
        unattempted=jobs[len(rows):],protected_files=len(guard),changed_protected=changed,
        source_changed=[str(p) for i,p in enumerate(sources) if sha(p)!=sha(root/"source_snapshot"/f"{i:02d}_{p.name}")],
        no_retry=True,new_governor_candidate=False,delay_200ms_rejected=True,training_started=False,
        predictor_started=False,optuna_started=False,hardware_validated=False))
    print((root/"decision.json").read_text(),flush=True)


if __name__=="__main__":main()
