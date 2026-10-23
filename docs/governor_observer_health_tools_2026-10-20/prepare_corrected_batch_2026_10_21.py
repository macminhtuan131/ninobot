"""Freeze the explicitly authorized corrected-logger cadence batch, no launch."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl")]
from prepare_governor_cadence_experiment import dependencies,validate,sha


def write(path,value):
    path.write_text(json.dumps(value,indent=2)+"\n")


def main():
    parent=ROOT/"docs/governor_observer_health_followup_2026-10-20"
    output=ROOT/"docs/governor_corrected_logger_cadence_2026-10-21"
    old=json.loads((parent/"protocol.json").read_text())
    assert sha(parent/"protocol.json")==json.loads((parent/"prepared_manifest.json").read_text())["protocol_sha256"]
    for relative,h in old["bundle_sha256"].items():
        assert sha(parent/relative)==h,relative
    previous,current=old["execution_dependency_sha256"],dependencies()
    allowed={"src/nino_rl/nino_rl/governor_logger.py","src/nino_rl/nino_rl/observer_health.py"}
    assert previous.keys()==current.keys()
    assert {k for k in current if current[k]!=previous[k]}==allowed
    verification=json.loads((parent/"offline_shutdown_fix/verification.json").read_text())
    assert verification["tests_passed"]==49 and verification["synthetic_ROS_checks_passed"]==2
    for relative in allowed:
        assert sha(ROOT/relative)==sha(parent/"offline_shutdown_fix"/Path(relative).name)
    output.mkdir(exist_ok=False)
    for name in ("inputs","arm_views","source_snapshot"):
        shutil.copytree(parent/name,output/name)
    for relative in allowed:
        name=Path(relative).name
        shutil.copy2(parent/"source_snapshot"/name,output/"source_snapshot"/("before_shutdown_fix_"+name))
        shutil.copy2(ROOT/relative,output/"source_snapshot"/name)
    shutil.copy2(parent/"health_runner.py",output/"health_runner.py")
    shutil.copy2(Path(__file__),output/"prepare_corrected_batch.py")
    shutil.copy2(parent/"offline_shutdown_fix/verification.json",output/"offline_verification.json")
    new=deepcopy(old)
    new.update(contract="corrected_logger_cadence_v1_2026_10_21",status="frozen_before_execution",
        execution_dependency_sha256=current,
        parent=dict(protocol_sha256=sha(parent/"protocol.json"),parent_data_not_overwritten=True,
            closed_at_attempt=1,not_a_retry_or_resume=True,
            authorized_source_revisions={k:dict(previous_sha256=previous[k],new_sha256=current[k]) for k in sorted(allowed)}),
        budget=dict(maximum_attempts=12,released=False,retries=0,replacements=0,extra_smoke=0,
            cold_start_each_attempt=True,automatic_extension=False,
            authorization="User2026-10-21: validate corrected logger in fresh bounded cadence batch, at most12 attempts; first PI and20ms attempts are integration within budget; hard stop on integrity fault, no retries."))
    new["observer_health"]["parent_batch"]="Both previous batches remain closed; no missing slots replaced or reused"
    new["observer_health"]["shutdown_revision"]="Logger owns SIGINT/SIGTERM stop request; close and health sidecar before context shutdown. Offline+synthetic ROS checked; Gazebo integration tested inside this budget."
    assert [j["arm"] for j in new["schedule"][:2]]==["full","reactive_20ms"]
    new["integration_checks"]+=" First PI and20ms health/metadata closure checks must pass before subsequent assigned attempt; health sidecar overflow/error/truncation is integrity failure. No observer timing duration threshold changes scoring."
    new["bundle_sha256"]={str(p.relative_to(output)):sha(p) for p in output.rglob("*") if p.is_file()}
    write(output/"protocol.json",new)
    write(output/"prepared_manifest.json",dict(protocol_sha256=sha(output/"protocol.json"),
        execution_authorized=False,budget_released=False,simulation_attempts=0,thresholds_confirmed=False))
    answer=validate(output)
    # All actual experiment inputs are byte-identical to the previous protocol.
    for path in (output/"inputs").iterdir():
        assert sha(path)==sha(parent/"inputs"/path.name)
    print(json.dumps(answer,indent=2))


if __name__=="__main__":
    main()
