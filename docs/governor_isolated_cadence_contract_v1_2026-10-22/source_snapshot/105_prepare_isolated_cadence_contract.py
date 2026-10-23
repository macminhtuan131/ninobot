#!/usr/bin/env python3
"""Freeze a new isolated-acquisition contract; no budget release or ROS launch."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl/scripts")]
from prepare_governor_h2_protocol import sha,write
from run_governor_h2_replication import execution_dependencies
from prepare_governor_cadence_experiment import validate_schedule,ARMS
from nino_rl.acquisition_contract import SCHEMA

PARENT=ROOT/"docs/governor_corrected_logger_cadence_2026-10-21"


def validate(bundle):
    bundle=Path(bundle)
    p=json.loads((bundle/"protocol.json").read_text())
    manifest=json.loads((bundle/"prepared_manifest.json").read_text())
    if sha(bundle/"protocol.json")!=manifest["protocol_sha256"]:
        raise ValueError("New acquisition protocol hash drift")
    if (p["contract"]!="isolated_joint_gt_cadence_v1_2026_10_22"
            or p["acquisition"]["schema"]!=SCHEMA
            or p["acquisition"]["all_arms"]!={a:"isolated_joint_gt" for a in ARMS}
            or p["budget"]["released"] is not False or p["thresholds_applied"] is not False
            or p["budget"]["maximum_attempts"]!=12):
        raise ValueError("Acquisition architecture/budget/threshold contract drift")
    validate_schedule(p["schedule"])
    for name,expected in p["bundle_sha256"].items():
        if sha(bundle/name)!=expected:raise ValueError("Frozen bundle drift: "+name)
    if execution_dependencies()!=p["execution_dependency_sha256"]:
        raise ValueError("Runtime/source dependencies changed; new freeze required")
    for name,expected in p["parent_input_sha256"].items():
        if sha(bundle/"inputs"/name)!=expected:
            raise ValueError("Physical/controller input differs from closed parent")
    for arm in ARMS:
        profile="full" if arm=="full" else "reactive"
        if (sha(bundle/f"arm_views/{arm}/inputs/{profile}.yaml")!=sha(bundle/f"inputs/{arm}.yaml")
                or json.loads((bundle/f"arm_views/{arm}/protocol.json").read_text())["fixed"]!=p["fixed"]):
            raise ValueError("Arm view differs from common contract")
    return dict(valid=True,contract=p["contract"],protocol_sha256=manifest["protocol_sha256"],
        execution_authorized=False,budget_released=False,simulation_attempts=0,
        live_integration_validated=False,application_thresholds="proposal_only")


def prepare(output):
    old=json.loads((PARENT/"protocol.json").read_text())
    if sha(PARENT/"protocol.json")!=json.loads((PARENT/"prepared_manifest.json").read_text())["protocol_sha256"]:
        raise ValueError("Closed parent protocol changed")
    for name,expected in old["bundle_sha256"].items():
        if sha(PARENT/name)!=expected:raise ValueError("Closed parent bundle changed: "+name)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for name in ("inputs","arm_views"):
        shutil.copytree(PARENT/name,output/name)
    new=deepcopy(old)
    new.update(contract="isolated_joint_gt_cadence_v1_2026_10_22",status="software_prepared_no_budget_release",
        parent=dict(protocol_sha256=sha(PARENT/"protocol.json"),closed_batch_remains_closed=True,
                    slots_reused=False,parent_data_not_overwritten=True),
        parent_input_sha256={p.name:sha(p) for p in (PARENT/"inputs").iterdir() if p.is_file()},
        acquisition=dict(schema=SCHEMA,all_arms={a:"isolated_joint_gt" for a in ARMS},
            authority={"joint_gt":"isolated_process_only","imu_contact_aux":"primary_observer_only"},
            readiness="Both source-bound processes fresh <=100ms, live status <=2s; discovery before reset; exact reset/end ACK, no world steps while waiting;10s wall deadline, no retry",
            closure="Both closed manifests/status + primary health + capture CRC/SHA/epoch; immutable source hashes; no legacy metadata masquerade or gap fill",
            scoring="Unchanged100ms native replay, GT-header sampling/joint interpolation,98percent coverage EACH original window,20ms/+10ms sensitivity and2s stopping",
            evidence_order=["earlier_reduced_command","earlier_actual_wheel_body_before_next_contact","crossing_quality_tracking_time"],
            live_integration_validated=False),
        budget=dict(maximum_attempts=12,released=False,retries=0,replacements=0,extra_smoke=0,
            cold_start_each_attempt=True,automatic_extension=False,
            status="proposal_after_software_verification_requires_new_release_no_old_slots"),
        execution_dependency_sha256=execution_dependencies())
    new["fixed"]["acquisition_architecture"]="isolated_joint_gt_common_to_all_arms"
    new["observer_health"]["parent_batch"]="All earlier cadence batches remain closed; this contract has no released slots"
    new["observer_health"]["shutdown_revision"]="Both recorder processes own orderly close; offline and synthetic ROS only. Gazebo integration remains unvalidated."
    new["integration_checks"]+=" Both process readiness/reset/end/closure and provenance mandatory; all arms use isolated joint/GT authority with no legacy fill. First live checks, if separately funded, stay inside the new budget."
    for arm in ARMS:
        write(output/f"arm_views/{arm}/protocol.json",dict(fixed=new["fixed"]))
    snapshot=output/"source_snapshot";snapshot.mkdir()
    for index,(relative,digest) in enumerate(new["execution_dependency_sha256"].items()):
        path=snapshot/(f"{index:03d}_"+Path(relative).name)
        shutil.copy2(ROOT/relative,path)
    new["bundle_sha256"]={str(p.relative_to(output)):sha(p) for p in output.rglob("*") if p.is_file()}
    write(output/"protocol.json",new)
    write(output/"prepared_manifest.json",dict(protocol_sha256=sha(output/"protocol.json"),
        execution_authorized=False,budget_released=False,simulation_attempts=0,thresholds_confirmed=False))
    return validate(output)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output",type=Path);group.add_argument("--validate",type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output) if args.output else validate(args.validate),indent=2))
