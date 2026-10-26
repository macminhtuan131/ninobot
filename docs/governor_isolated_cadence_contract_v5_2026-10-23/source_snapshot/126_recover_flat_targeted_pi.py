#!/usr/bin/env python3
"""Recover only missing PI seeds, preserving completed evidence and timing checks."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "rl_runs/course_targeted_corrections_v1/flat"
OUTPUT = ROOT / "rl_runs/flat_targeted_pi_recovery_v2"


def collect_batches(paths, expected_seeds, benchmark):
    """Accept completed rows only, including rows from interrupted batches."""
    from nino_rl.tuning_objective import read_episode_rows
    records = {}
    for summary_path in paths:
        report = json.loads(summary_path.read_text())
        if report["benchmark_id"] != benchmark or report["controller"] != "straight_pi_baseline":
            raise ValueError("Incompatible PI recovery evidence")
        rows = read_episode_rows(summary_path.with_name("episodes.csv"))
        if len(rows) != report["episodes"]:
            raise ValueError("Summary/episode count mismatch")
        for row in rows:
            seed = row["seed"]
            if seed not in expected_seeds or seed in records:
                raise ValueError("Unexpected or duplicate completed seed")
            directory = summary_path.parent / f"episode-{row['episode']:03d}"
            for name in ("metrics.json", "ground_truth/metrics.json", "control_trace.csv", "drive_trace.csv"):
                if not (directory / name).is_file():
                    raise ValueError("Missing completed episode evidence: " + str(directory / name))
            records[seed] = (row, directory, summary_path)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0] = [str(SOURCE / "python"), str(ROOT / "src/nino_rl"), str(Path(__file__).parent)]
    from encoder_history_transport import patch_interface
    from run_course_targeted_corrections import read, write
    from run_flat_seed_repeat import verify, promotion_gates
    from nino_rl.tuning_trials import digest, assert_trial_inputs
    from nino_rl.tuning_objective import read_episode_rows, score_episodes
    from nino_rl.evaluation import summarize, compare_summaries
    from nino_rl.trajectory_metrics import write_csv
    from train_rough_curriculum import Processes, assert_isolated
    plan = read(SOURCE / "targeted_plan.json")
    verify(plan)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    overlay = output / "python"
    with (output / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not overlay.exists():
            temporary = output / "python.preparing"
            if temporary.exists():
                shutil.rmtree(temporary)
            shutil.copytree(SOURCE / "python", temporary, ignore=shutil.ignore_patterns("__pycache__"))
            path = temporary / "nino_rl/ros_interface.py"
            path.write_text(patch_interface(path.read_text()))
            temporary.rename(overlay)
        for p in (overlay / "nino_rl").glob("*.py"):
            old = SOURCE / "python/nino_rl" / p.name
            expected = patch_interface(old.read_text()).encode() if p.name == "ros_interface.py" else old.read_bytes()
            if p.read_bytes() != expected:
                raise ValueError("Undeclared recovery package change: " + p.name)
        assets = {str(p): digest(p) for p in sorted((overlay / "nino_rl").glob("*.py"))}
        contract = dict(revision="flat_encoder_history_recovery_v1", snapshot_assets=assets,
            original=str(SOURCE), original_plan_sha256=digest(SOURCE / "targeted_plan.json"),
            transport_change="joint subscription history 1 -> 100; same BEST_EFFORT reliability",
            estimator="unchanged timestamp interpolation and corridor correction",
            timing="unchanged action duration, clock check and 0.04s motion freshness limit",
            evaluation_config_sha256=digest(SOURCE / "evaluation.yaml"), seeds=plan["evaluation_seeds"],
            workflow_assets={str(p): digest(p) for p in [Path(__file__), Path(__file__).with_name("encoder_history_transport.py")]})
        path = output / "recovery_contract.json"
        if path.exists() and read(path) != contract:
            raise ValueError("Recovery contract changed; use a new directory")
        write(path, contract)
        state = dict(pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat())

        def save(stage, **extra):
            state.update(stage=stage, updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
            write(output / "status.json", state)
            print(stage, flush=True)

        def check():
            verify(plan)
            for group in (contract["snapshot_assets"], contract["workflow_assets"]):
                for p, expected in group.items():
                    if digest(p) != expected:
                        raise ValueError("Frozen recovery input changed: " + p)

        benchmark = plan["evaluation_objective"]["benchmark_id"]
        summaries = list((SOURCE / "pi").glob("*/summary.json")) + list((output / "batches").glob("*/summary.json"))
        records = collect_batches(summaries, plan["evaluation_seeds"], benchmark)
        missing = [s for s in plan["evaluation_seeds"] if s not in records]
        save("prepared", completed_seeds=sorted(records), remaining_seeds=missing)
        if not args.run:
            return
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        env = os.environ.copy()
        env.update(ROS_DOMAIN_ID="79", NINO_ROS_DOMAIN_ID="79", GZ_PARTITION="nino_flat_79",
            ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",
            PYTHONPATH=str(overlay) + os.pathsep + str(ROOT / "src/nino_rl") + os.pathsep + env.get("PYTHONPATH", ""))
        os.environ.update({key: env[key] for key in ("ROS_DOMAIN_ID", "NINO_ROS_DOMAIN_ID", "GZ_PARTITION",
                                                    "ROS_AUTOMATIC_DISCOVERY_RANGE")})
        processes = Processes(env, pi_integrator_profile="conditional_v1")
        try:
            check()
            if missing:
                assert_isolated(79, "nino_flat_79")
                save("evaluating_missing_pi")
                directory = output / "batches"
                processes.world = processes.start(["ros2", "launch", "nino_rl", "training_sim.launch.py",
                    f"world:={plan['source_trial_contract']['world']}", "world_name:=combined_flat_section",
                    "headless:=true", "pi_integrator_profile:=conditional_v1"], output / "gazebo.log")
                processes.run(["ros2", "run", "nino_rl", "wait_for_sim"], output / "readiness.log", timeout=90)
                assert_trial_inputs(plan["source_trial_contract"], live=True)
                processes.run([sys.executable, "src/nino_rl/scripts/wait_for_drive_profile.py", "--config",
                    SOURCE / "evaluation.yaml", "--timeout", 60], output / "profile.log", timeout=65)
                processes.run(["ros2", "run", "nino_rl", "evaluate_baseline", "--config", SOURCE / "evaluation.yaml",
                    "--seeds", *missing, "--control-trace", "--baseline-speed-scale", 1., "--output", directory],
                    output / "evaluation.log")
                processes.close()
            check()
            summaries = list((SOURCE / "pi").glob("*/summary.json")) + list((output / "batches").glob("*/summary.json"))
            records = collect_batches(summaries, plan["evaluation_seeds"], benchmark)
            if set(records) != set(plan["evaluation_seeds"]):
                raise ValueError("Missing PI seeds after recovery")
            merged = output / "pi/merged"
            merged.mkdir(parents=True, exist_ok=True)
            rows, provenance = [], []
            for index, seed in enumerate(plan["evaluation_seeds"], 1):
                row, directory, source = records[seed]
                rows.append({**row, "episode": index})
                link = merged / f"episode-{index:03d}"
                if link.is_symlink() and link.resolve() != directory.resolve():
                    raise ValueError("Merged episode link changed")
                if not link.exists():
                    link.symlink_to(directory.resolve(), target_is_directory=True)
                provenance.append(dict(seed=seed, source_summary=str(source), source_episode=str(directory),
                    source_csv_sha256=digest(source.with_name("episodes.csv")),
                    transport="encoder_history_100" if output in source.parents else "original_history_1"))
            write_csv(merged / "episodes.csv", rows)
            metadata = read(next((SOURCE / "pi").glob("*/metadata.json")))
            report = summarize(rows, {**metadata, "complete": True, "requested_episodes": 24,
                "recovery_provenance": provenance, "transport_recovery_contract": str(path)})
            write(merged / "summary.json", report)
            ppo_paths = list((SOURCE / "ppo").glob("*/summary.json"))
            if len(ppo_paths) != 1 or not read(ppo_paths[0])["complete"]:
                raise ValueError("Expected one completed PPO evaluation")
            result = {"pi": dict(summary=str(merged / "summary.json"), report=report,
                                 objective=score_episodes(rows, plan["evaluation_objective"])),
                      "ppo": dict(summary=str(ppo_paths[0]), report=read(ppo_paths[0]),
                                 objective=score_episodes(read_episode_rows(ppo_paths[0].with_name("episodes.csv")), plan["evaluation_objective"]))}
            result["comparison"] = compare_summaries(report, result["ppo"]["report"])
            result["gates"] = promotion_gates(result, plan)
            result["promote"] = all(result["gates"][k] for k in ("physical_arrival", "completion", "tracking", "quality"))
            reference = read(ROOT / "rl_runs/flat_value_scaled_seed43_v1/comparison.json")
            result["versus_same_seed_reference"] = compare_summaries(reference["ppo"]["report"], result["ppo"]["report"])
            result["correction"] = plan["correction"]
            write(output / "comparison.json", result)
            lines = ["# Recovered flat targeted-slip comparison", "", "Only the nine missing PI seeds were evaluated. "
                     "The first 15 completed rows and full 24-seed PPO batch remain unchanged. "
                     "Fusion/action/physical scoring are unchanged; recovered PI uses encoder history 100 instead of 1.", "",
                     "| Metric | PPO | PI |", "|---|---:|---:|"]
            for metric in ("time_seconds", "truth_path_rmse_m", "rms_vertical_acceleration_m_s2", "rms_wheel_slip"):
                lines.append("| " + metric + " | " + " | ".join(f"{result[k]['report']['metrics_all_episodes'][metric]['mean']:.6f}" for k in ("ppo", "pi")) + " |")
            lines += ["", f"Gates: `{json.dumps(result['gates'])}`. Qualifies: **{result['promote']}**.", "",
                      "Transport histories differ across the recovered batch; provenance is explicit. "
                      "No retraining, reward change or Optuna was performed. No generalization claim.", ""]
            (output / "REPORT.md").write_text("\n".join(lines))
            save("complete", report=str(output / "REPORT.md"), gates=result["gates"])
        except BaseException as error:
            save("cancelled" if isinstance(error, KeyboardInterrupt) else "failed", error=str(error))
            raise
        finally:
            processes.close()


if __name__ == "__main__":
    main()
