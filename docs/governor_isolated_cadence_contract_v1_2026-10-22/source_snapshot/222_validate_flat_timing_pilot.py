#!/usr/bin/env python3
"""Wait for the specified pilot, then evaluate its final frozen policy once."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time


def process_identity(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-pid", type=int, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if (os.environ.get("ROS_DOMAIN_ID") != "79"
            or os.environ.get("GZ_PARTITION") != "nino_flat_79"):
        parser.error("Use ROS_DOMAIN_ID=79 and GZ_PARTITION=nino_flat_79")
    status_path = run / "validation_status.json"
    if status_path.exists() and json.loads(status_path.read_text()).get("stage") == "complete":
        print("Final validation already completed; no repeat requested.")
        return
    cmdline = Path(f"/proc/{args.training_pid}/cmdline")
    if not cmdline.exists() or b"/nino_rl/train" not in cmdline.read_bytes():
        parser.error("The specified PID must be the active nino_rl train process")
    identity = process_identity(args.training_pid)

    def status(stage, **details):
        status_path.write_text(json.dumps({"stage": stage,
            "updated_at": datetime.now().isoformat(), "training_pid": args.training_pid,
            **details}, indent=2) + "\n")

    status("waiting_for_training")
    while process_identity(args.training_pid) == identity:
        time.sleep(15)
    model = run / "nino_ppo_final.zip"
    if not model.exists():
        status("training_stopped_without_final_model")
        return
    from stable_baselines3 import PPO
    final_model = PPO.load(model, device="cpu")
    if final_model.num_timesteps < 50000:
        status("training_incomplete", steps=final_model.num_timesteps)
        return
    del final_model
    output = run / "final_validation"
    status("evaluating_final_policy", model=str(model))
    command = ["ros2", "run", "nino_rl", "evaluate", "--device", "cuda",
        "--config", str(run / "ppo.yaml"), "--model", str(model),
        "--flat-stage", "2", "--phase", "1", "--episodes", "24",
        "--seed", "61000", "--control-trace", "--output", str(output)]
    with (run / "final_validation.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        status("evaluation_failed", returncode=result.returncode)
        return
    candidate_path = max(output.glob("*/summary.json"), key=lambda p: p.stat().st_mtime)
    candidate = json.loads(candidate_path.read_text())
    from nino_rl.evaluation import compare_summaries
    baselines = {
        "fast_pi": Path("rl_runs/flat_speed_yaw_pilot_pi/20261007-155635-991948/summary.json"),
        "slow_pi": Path("rl_runs/flat_pi_slow_078_check/20261007-171835-555212/summary.json"),
        "original_ppo": Path("rl_runs/flat_speed_yaw_pilot_eval/20261007-160707-136898/summary.json")}
    reports = {label: json.loads(path.read_text()) for label, path in baselines.items()}
    for label, baseline in reports.items():
        comparison = compare_summaries(baseline, candidate)
        (run / f"final_comparison_vs_{label}.json").write_text(json.dumps(comparison, indent=2) + "\n")
    mean = lambda report, metric: report["metrics_all_episodes"][metric]["mean"]
    fast = reports["fast_pi"]
    gates = {
        "arrival_count_at_least_fast_pi": candidate["success_rate"] >= fast["success_rate"],
        "on_time_count_at_least_fast_pi": candidate["on_time_success_rate"] >= fast["on_time_success_rate"],
        "physical_path_rmse_within_pi_plus_1cm": mean(candidate, "truth_path_rmse_m") <= mean(fast, "truth_path_rmse_m") + .01,
        "vertical_rms_20_percent_below_fast_pi": mean(candidate, "rms_vertical_acceleration_m_s2") <= .8 * mean(fast, "rms_vertical_acceleration_m_s2"),
        "slip_no_worse_than_slow_pi": mean(candidate, "rms_wheel_slip") <= mean(reports["slow_pi"], "rms_wheel_slip")}
    status("complete", candidate_summary=str(candidate_path), gates=gates,
           all_gates_met=all(gates.values()),
           interpretation="Fixed validation-suite gates; not statistical proof or held-out generalization.")


if __name__ == "__main__":
    main()
