"""Freeze one diagnostic follow-up with only observer source revisions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/"src/nino_rl/scripts"), str(ROOT/"src/nino_rl")]
from prepare_governor_cadence_experiment import dependencies, validate, sha


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+"\n")


def main():
    source = ROOT/"docs/governor_cadence_experiment_2026-10-20"
    output = ROOT/"docs/governor_observer_health_followup_2026-10-20"
    old = json.loads((source/"protocol.json").read_text())
    assert sha(source/"protocol.json") == json.loads((source/"prepared_manifest.json").read_text())["protocol_sha256"]
    for relative, expected in old["bundle_sha256"].items():
        assert sha(source/relative) == expected, relative
    previous, current = old["execution_dependency_sha256"], dependencies()
    logger = "src/nino_rl/nino_rl/governor_logger.py"
    health = "src/nino_rl/nino_rl/observer_health.py"
    assert current.keys()-previous.keys() == {health}
    assert not previous.keys()-current.keys()
    assert {k for k in previous.keys() & current.keys() if previous[k] != current[k]} == {logger}
    output.mkdir(exist_ok=False)
    for name in ("inputs", "arm_views", "source_snapshot"):
        shutil.copytree(source/name, output/name)
    snapshots = output/"source_snapshot"
    shutil.copy2(ROOT/"docs/governor_observer_gap_audit_2026-10-20/executed_governor_logger.py",
                 snapshots/"previous_governor_logger.py")
    assert sha(snapshots/"previous_governor_logger.py") == previous[logger]
    for name in ("governor_logger.py", "observer_health.py"):
        shutil.copy2(ROOT/"src/nino_rl/nino_rl"/name, snapshots/name)
    shutil.copy2(Path(__file__).with_name("health_runner.py"), output/"health_runner.py")
    shutil.copy2(Path(__file__), output/"prepare_followup.py")
    new = deepcopy(old)
    new.update(contract="governor_cadence_observer_health_followup_v1_2026_10_20",
        status="prepared_diagnostic_followup", execution_dependency_sha256=current,
        observer_health=dict(required=True, maximum_records=100000,
            change="In-memory monotonic callback and conversion/encode/write/flush timing, sidecar written after collection. Same raw payload, QoS, sampling, controller and scoring.",
            performance_thresholds="No new duration gate; missing/truncated/overflow/error health data is an integrity fault.",
            parent_batch="Closed at attempt9; not a resume, replacement or completion of its slots10–12",
            fixed_scenarios="Same77600/77601 scenarios, separately recorded repetitions; no unseen/generalization claim"),
        parent=dict(protocol_sha256=sha(source/"protocol.json"), parent_data_not_overwritten=True,
            authorized_source_revisions={logger:dict(previous_sha256=previous[logger], new_sha256=current[logger]),
                                         health:dict(previous_sha256=None,new_sha256=current[health])}),
        budget=dict(maximum_attempts=12,released=False,retries=0,replacements=0,extra_smoke=0,
            cold_start_each_attempt=True,automatic_extension=False,
            authorization="User2026-10-20: continuously follow suggested steps. One bounded observer-instrumented cadence follow-up, stopping on integrity faults; no repeated rescue budget."))
    new["bundle_sha256"] = {str(p.relative_to(output)):sha(p) for p in output.rglob("*") if p.is_file()}
    write(output/"protocol.json", new)
    write(output/"prepared_manifest.json",dict(protocol_sha256=sha(output/"protocol.json"),
        execution_authorized=False,budget_released=False,simulation_attempts=0,thresholds_confirmed=False))
    print(json.dumps(validate(output), indent=2))


if __name__ == "__main__":
    main()
