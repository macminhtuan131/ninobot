#!/usr/bin/env python3
"""Execute the four preregistered cold starts, sequentially; no tuning/retry."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/"src/nino_rl"), str(ROOT/"src/nino_control")]
from nino_rl.slip_reporting import integrate
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series
from audit_governor_readiness_peaks import audit as peak_audit
from run_frozen_governor_confirmation import make_world, analyze_batch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def enrich(row):
    case = Path(row["case"])
    evaluation = next(case.glob("evaluation/*/summary.json")).parent
    logger = Path(row["logger"]) if row.get("logger") else next(case.glob("contact/*/metadata.json")).parent
    data = load(case, dict(evaluation=str(evaluation), logger=str(logger),
                          seed=row["seed"], profile=row["profile"]))
    signal = gt_timestamp_series(data)
    row["gt_native"] = dict(whole_route=integrate(signal, data["start"], data["end"]),
        crossing=integrate(signal, row["first_contact_s"]+.05, row["clearance_s"]))
    controls = data["controls"]
    ages = [float(c[k]) for c in controls for k in
            ("governor_feedback_age_s", "drive_interval_latest_age_s")]
    row["readiness"] = dict(no_failsafe=all(not c["governor_fault"] for c in controls),
        age_range_s=[min(ages), max(ages)],
        min_interval_samples=min(int(c["drive_interval_sample_count"]) for c in controls))
    row["reporting_pass"] = bool(row.get("complete") and row.get("available")
        and row.get("native_replay", {}).get("matches_native")
        and row.get("timestamps", {}).get("passed") and row["readiness"]["no_failsafe"]
        and all(-1e-9 <= age <= .100000001 for age in ages)
        and all(row["gt_native"][w]["available"] for w in ("whole_route", "crossing"))
        and row.get("crossing_vertical", {}).get("available"))
    row["peak_context"] = peak_audit(case, row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    frozen = ROOT/"rl_runs/governor_readiness_v1_2026-10-16"
    plan_path = ROOT/"docs/governor_readiness_v1_2026-10-16/next_repeatability_protocol.json"
    plan = json.loads(plan_path.read_text())
    if sha(frozen/"config.yaml") != plan["fixed_config_sha256"]:
        raise ValueError("Frozen configuration changed")
    for name in ("ros_interface.py", "ros_env.py", "evaluation.py"):
        if sha(ROOT/"src/nino_rl/nino_rl"/name) != sha(frozen/"after_sources"/name):
            raise ValueError("Readiness source changed: "+name)
    shutil.copy2(plan_path, root/"prepared_protocol_snapshot.json")
    shutil.copy2(frozen/"config.yaml", root/"config.yaml")
    (root/"runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    source_paths = [ROOT/"src/nino_rl/nino_rl"/name for name in
        ("ros_interface.py", "ros_env.py", "evaluation.py", "slip_reporting.py")]
    source_paths += [ROOT/"src/nino_control/nino_control"/name for name in
                     ("governor_core.py", "effort_drive.py")]
    guard = {}
    for folder in (ROOT/"docs/governor_readiness_v1_2026-10-16",
                   ROOT/"docs/gt_governor_optuna_v2_2026-10-16",
                   ROOT/"src/nino_rl/config", ROOT/"src/nino_control"):
        for path in folder.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                guard[str(path)] = sha(path)
    guard.update({str(p):sha(p) for p in source_paths})
    write(root/"preservation_before.json", guard)
    jobs = [(repeat, arm) for repeat, arms in enumerate(plan["order"], 1) for arm in arms]
    protocol = dict(prepared_protocol=plan, case_order=jobs, domain=101,
        source_sha256={str(p):sha(p) for p in source_paths},
        decision_rule="Stop immediately on missing reporting/physical failure; otherwise compare both fixed pairs and stop expansion on inconsistent quality ranking. No score/candidate selection.",
        comparison="Crossing RMS and whole-route peak rankings are descriptive; no significance or hardware fidelity claim from two repetitions")
    write(root/"protocol_before_results.json", protocol)
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID="101", NINO_ROS_DOMAIN_ID="101",
        ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST", GZ_PARTITION="nino_governor_repeatability_101")
    rows = []
    stop = None
    for index, (repeat, arm) in enumerate(jobs, 1):
        block = root/f"attempt_{index:02d}"
        stage = block/"confirmation/repeat"
        stage.mkdir(parents=True)
        scenario = dict(id="repeat", x_m=plan["scenario"]["x_m"],
                        angle_deg=plan["scenario"]["angle_deg"], seeds=[plan["scenario"]["seed"]])
        write(block/"protocol_before_results.json", dict(scenarios=[scenario]))
        make_world(stage/"scenario.sdf", scenario)
        cmd = [sys.executable, str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
            "--variant", "cable_box_capsule", "--config", str(root/"config.yaml"),
            "--profiles", arm, "--seeds", str(plan["scenario"]["seed"]),
            "--world", str(stage/"scenario.sdf"), "--output", str(stage/"screen")]
        if arm == "full":
            cmd += ["--full-reference-speed", ".4"]
        print("START", index, "repeat", repeat, arm, flush=True)
        with (block/"run.log").open("w") as stream:
            result = subprocess.run(cmd, env=env, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        analyze_batch(block)
        result_rows = json.loads((block/"confirmation_episodes.json").read_text())
        if len(result_rows) != 1:
            raise RuntimeError("Expected one attempted case; no outcome may be silently dropped")
        row = dict(result_rows[0], repeat=repeat, attempt=index, runner_exit=result.returncode)
        try:
            enrich(row)
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            row["analysis_error"] = f"{type(error).__name__}:{error}"
            row["reporting_pass"] = False
        rows.append(row)
        write(root/"episodes.json", rows)
        print("END", index, "physical", row.get("physical_pass"), "reporting", row.get("reporting_pass"), flush=True)
        if result.returncode or not row.get("reporting_pass") or not row.get("physical_pass"):
            stop = "reporting_or_physical_gate_failed_no_retry"
            break
    pairs = []
    for repeat in (1, 2):
        arms = {r["profile"]:r for r in rows if r["repeat"] == repeat}
        pair = dict(repeat=repeat, available=False)
        if set(arms) == {"full", "reactive"} and all(r.get("reporting_pass") for r in arms.values()):
            p, g = arms["full"], arms["reactive"]
            pair.update(available=True, ratios=dict(time=g["time_s"]/p["time_s"],
                tracking=g["physical_rmse_m"]/p["physical_rmse_m"],
                whole_vertical_rms=g["whole_vertical_rms"]/p["whole_vertical_rms"],
                whole_vertical_peak=g["whole_vertical_peak"]/p["whole_vertical_peak"],
                crossing_vertical_rms=g["crossing_vertical"]["rms"]/p["crossing_vertical"]["rms"],
                gt_whole_slip=g["gt_native"]["whole_route"]["rms"]/p["gt_native"]["whole_route"]["rms"],
                gt_crossing_slip=g["gt_native"]["crossing"]["slip_square_per_m"]/p["gt_native"]["crossing"]["slip_square_per_m"]))
        pairs.append(pair)
    complete = len(rows) == 4 and all(p["available"] for p in pairs)
    reversal = complete and any((pairs[0]["ratios"][k]-1)*(pairs[1]["ratios"][k]-1) < 0
        for k in ("crossing_vertical_rms", "whole_vertical_peak"))
    repeated_recovery = complete and all(p["ratios"]["crossing_vertical_rms"] > 1
        and p["ratios"]["whole_vertical_peak"] > 1 for p in pairs) and all(
        r["peak_context"]["command_at_peak"]["governor_phase"] == "RECOVER"
        and r["peak_context"]["peak_after_first_contact_s"] > 0 for r in rows if r["profile"] == "reactive")
    decision = dict(status=stop or ("inconsistent_quality_stop_expansion" if reversal else
        "repeated_recovery_deficit_investigate_one_correction" if repeated_recovery else
        "screen_complete_review_quality_without_automatic_promotion"), attempts=len(rows),
        planned_attempts=4, unattempted=jobs[len(rows):], pairs=pairs,
        quality_ranking_reversal=bool(reversal), repeated_recovery_temporal_pattern=bool(repeated_recovery),
        historical_instrumentation_pair_not_pooled=True, no_causal_claim=True,
        tuning_started=False, training_started=False, predictor_started=False,
        parameter_changes=False, extra_attempts=False)
    write(root/"decision.json", decision)
    print(json.dumps(decision,indent=2), flush=True)


if __name__ == "__main__":
    main()
