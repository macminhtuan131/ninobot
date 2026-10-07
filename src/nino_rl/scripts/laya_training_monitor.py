#!/usr/bin/env python3
"""Summarize live training/evaluation episodes and classify issues with Laya.

Laya is an optional text classifier here. Numeric trends are calculated from
the episode log and are never altered by its answer.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import time


QUESTIONS = {
    "dominant_issue": {
        "type": "choice",
        "instructions": "Which issue should the operator inspect first in the latest robot episodes?",
        "criteria": {
            "goal_accuracy": "The robot reaches the end but misses the goal position or heading.",
            "path_tracking": "The robot drifts off the reference path or path error rises.",
            "stability": "Rollovers, collisions, or large body impacts dominate.",
            "slow_progress": "Timeouts, stalls, or low progress dominate.",
            "odometry_drift": "Wheel odometry disagrees with ground truth enough to make the robot stop away from the physical goal.",
            "no_clear_issue": "Success is strong or the evidence does not identify one dominant issue.",
        },
    },
}


def read_episodes(path: Path) -> list[dict]:
    if path.suffix == ".csv":
        # Evaluation rewrites the CSV after each completed episode. Ignore an
        # unfinished final line if this snapshot catches a write in progress.
        contents = path.read_text(encoding="utf-8")
        if contents and not contents.endswith("\n"):
            contents = contents.rsplit("\n", 1)[0] + "\n" if "\n" in contents else ""
        rows = []
        for raw in csv.DictReader(io.StringIO(contents)):
            if None in raw or any(value is None for value in raw.values()):
                continue
            row = {}
            for key, value in raw.items():
                value = value.strip()
                if not value or value.lower() in ("none", "null"):
                    row[key] = None
                elif value.lower() in ("true", "false"):
                    row[key] = value.lower() == "true"
                else:
                    try:
                        row[key] = json.loads(value)
                    except json.JSONDecodeError:
                        row[key] = value
            if row.get("termination") and isinstance(row.get("success"), (bool, int, float)):
                rows.append(row)
        return rows
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # The trainer may still be writing the final line.
                if not line.endswith("\n"):
                    break
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from None
    return rows


def mean(rows: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return round(sum(values) / len(values), 4) if values else None


def statistics(rows: list[dict]) -> dict:
    return {
        "episodes": len(rows),
        "success_rate": mean(rows, "success"),
        "termination_counts": dict(sorted(Counter(row.get("termination", "unknown") for row in rows).items())),
        "final_progress_fraction": mean(rows, "final_progress_fraction"),
        "truth_path_rmse_m": mean(rows, "truth_path_rmse_m"),
        "path_rmse_m": mean(rows, "path_rmse_m"),
        "truth_endpoint_error_m": mean(rows, "truth_endpoint_error_m"),
        "odometry_endpoint_error_m": mean(rows, "endpoint_error_m"),
        "odom_truth_position_error_m": mean(rows, "odom_truth_position_error_m"),
        "rms_wheel_slip": mean(rows, "rms_wheel_slip"),
        "rms_vertical_acceleration_m_s2": mean(rows, "rms_vertical_acceleration_m_s2"),
    }


def report(rows: list[dict], window: int, active_stage=None) -> dict:
    if not rows:
        raise ValueError("No complete episodes found")
    stage = active_stage if active_stage is not None else rows[-1].get("rough_curriculum_stage")
    stage_rows = [row for row in rows if row.get("rough_curriculum_stage") == stage] if stage is not None else rows
    current = statistics(stage_rows[-window:])
    previous = statistics(stage_rows[-2 * window:-window]) if len(stage_rows) > window else None
    current["per_route"] = {route: statistics([row for row in stage_rows[-window:]
                                              if row.get("route_id") == route])
                            for route in sorted({row["route_id"] for row in stage_rows[-window:]
                                                 if row.get("route_id")})}
    counts = current["termination_counts"]
    failure_groups = {
        "goal_accuracy": counts.get("goal_missed", 0),
        "path_tracking": counts.get("off_path", 0) + counts.get("wrong_direction", 0),
        "stability": counts.get("collision", 0) + counts.get("rollover", 0),
        "slow_progress": counts.get("timeout", 0),
    }
    current["most_common_failure_group"] = (
        max(failure_groups, key=failure_groups.get) if any(failure_groups.values())
        else "no_clear_issue"
    )
    return {"total_episodes": len(rows), "stage_episodes": len(stage_rows), "rough_stage": stage,
            "terrain_variant_id": rows[-1].get("terrain_variant_id"), "window": window,
            "latest_training_step": rows[-1].get("training_step"),
            "current": current, "previous": previous}


def classify(summary: dict, router) -> dict:
    current, previous = summary["current"], summary["previous"]
    state = (
        ("Frozen policy evaluation; episode variation does not mean learning. "
         if summary.get("evaluation") else "Robot training. ")
        + "Choose an issue using failure counts first. "
        f"Latest {current['episodes']} episodes: "
        f"success rate {current['success_rate']}; "
        f"failure counts {current['termination_counts']}; "
        f"goal progress {current['final_progress_fraction']}; "
        f"ground-truth path error {current['truth_path_rmse_m']} m; "
        f"ground-truth endpoint error {current['truth_endpoint_error_m']} m; "
        f"wheel-odometry endpoint error {current['odometry_endpoint_error_m']} m; "
        f"odometry versus ground-truth position difference "
        f"{current['odom_truth_position_error_m']} m; "
        f"wheel slip {current['rms_wheel_slip']}. "
        + (f"Previous {previous['episodes']} episodes: success rate "
           f"{previous['success_rate']}; failures {previous['termination_counts']}; "
           f"ground-truth path error {previous['truth_path_rmse_m']} m."
           if previous else "No previous comparison window yet.")
    )
    if summary.get("curriculum"):
        curriculum = summary["curriculum"]
        state += (f" Active curriculum stage {curriculum['stage_name']}; status {curriculum['status']}. "
                  "Curriculum advancement uses numerical validation; this answer is advisory only.")
    routes = current.get("per_route", {})
    if routes:
        worst = min(routes, key=lambda route: routes[route]["success_rate"] or 0.)
        state += f" Lowest recent route success: {worst}, {routes[worst]['success_rate']}."
    answer = router.predict(state, QUESTIONS)
    decision = answer["answers"]["dominant_issue"]
    return {
        "suggested_issue": decision["choice"],
        "answer_confidence": decision.get("answer_confidence"),
        "matches_most_common_failure_group": (
            decision["choice"] == current["most_common_failure_group"]
        ),
    }


def latest_episode_log(run: Path) -> Path | None:
    if run.is_file() and run.name in ("episodes.jsonl", "episodes.csv"):
        return run
    candidates = [run / "episodes.jsonl", run / "episodes.csv"]
    candidates.extend(run.glob("*/episodes.jsonl"))
    candidates.extend(run.glob("*/episodes.csv"))
    candidates.extend(run.glob("trial_*/train/*/episodes.jsonl"))
    candidates.extend(run.glob("blocks/*/train/*/episodes.jsonl"))
    existing = [path for path in candidates if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def monitored_episodes(run: Path):
    # Curriculum blocks contain consecutive checkpoints of ONE policy. Only
    # aggregate that layout; independent Optuna trials must stay separate.
    paths = sorted(run.glob("blocks/*/train/*/episodes.jsonl"))
    if paths:
        return paths, [row for path in paths for row in read_episodes(path)]
    latest = latest_episode_log(run)
    return ([latest], read_episodes(latest)) if latest else ([], [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path,
                        help="Training/evaluation run, output parent, or Optuna study directory")
    parser.add_argument("--window", type=int, default=100, help="Episodes per comparison window")
    parser.add_argument("--min-episodes", type=int, default=20,
                        help="Minimum latest-window episodes before asking Laya")
    parser.add_argument("--watch", action="store_true", help="Repeat as new episodes arrive")
    parser.add_argument("--interval", type=float, default=300, help="Watch interval in seconds")
    parser.add_argument("--preview", action="store_true", help="Show metrics without loading Laya")
    parser.add_argument("--threads", type=int, default=2, help="CPU threads for Laya; keep simulation capacity free")
    parser.add_argument("--course", choices=("rough", "flat"),
                        help="Label reports from this course")
    parser.add_argument("--output", type=Path,
                        help="Append each new JSON report to this file")
    args = parser.parse_args()
    if args.window < 1 or args.min_episodes < 1 or args.interval <= 0 or args.threads < 1:
        parser.error("--window, --min-episodes and --interval must be positive")
    run = args.run.expanduser().resolve()
    router = None
    if not args.preview:
        try:
            from laya import Router
            import torch
        except ImportError:
            parser.error("Install Laya in this Python environment: python -m pip install laya==0.3.22")
        # Keep the training GPU free when this monitor runs alongside PPO.
        torch.set_num_threads(args.threads)
        router = Router(device="cpu")
    last_seen = None
    while True:
        try:
            paths, rows = monitored_episodes(run)
            state_path = run / "curriculum_state.json"
            curriculum = json.loads(state_path.read_text()) if state_path.exists() else None
            if not rows:
                if curriculum:
                    summary = {"total_episodes": 0, "current": {"episodes": 0}, "previous": None}
                elif args.watch:
                    waiting = (tuple(paths), "waiting")
                    if last_seen != waiting:
                        print(f"Waiting for the first complete episode in {run}", flush=True)
                        last_seen = waiting
                    time.sleep(args.interval)
                    continue
                else:
                    parser.error(f"Missing complete episodes.jsonl or episodes.csv in {run}")
            else:
                summary = report(rows, args.window, curriculum.get("stage_index") if curriculum else None)
            if paths and paths[-1].suffix == ".csv" and rows:
                finished_path = paths[-1].with_name("summary.json")
                try:
                    finished = json.loads(finished_path.read_text()) if finished_path.exists() else {}
                except json.JSONDecodeError:
                    finished = {}
                summary["evaluation"] = {
                    "controller": rows[-1].get("controller"),
                    "latest_episode": rows[-1].get("episode"),
                    "latest_seed": rows[-1].get("seed"),
                    "complete": finished.get("complete", False),
                    "requested_episodes": finished.get("requested_episodes"),
                    "policy_weight_updates": False,
                }
            if curriculum:
                summary["curriculum"] = {key: curriculum.get(key) for key in
                    ("stage_index", "stage_name", "status", "training_steps", "target_steps",
                     "active_block", "last_evaluation", "updated_at")}
        except ValueError as error:
            if args.watch and str(error) == "No complete episodes found":
                time.sleep(args.interval)
                continue
            parser.error(str(error))
        seen = (tuple(paths), summary["total_episodes"], json.dumps(summary.get("curriculum"), sort_keys=True),
                json.dumps(summary.get("evaluation"), sort_keys=True))
        if seen != last_seen:
            summary["sources"] = [str(path) for path in paths]
            summary["source"] = str(paths[-1]) if paths else None
            if args.course:
                summary["course"] = args.course
            if router is not None and summary["current"]["episodes"] >= args.min_episodes:
                try:
                    summary["laya_advisory"] = classify(summary, router)
                except Exception as error:
                    parser.exit(1, f"Laya prediction failed: {error}\n")
            elif router is not None:
                summary["laya_advisory"] = f"Waiting for {args.min_episodes} episodes in the latest window"
            rendered = json.dumps(summary, allow_nan=False)
            if args.output:
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("a", encoding="utf-8") as stream:
                    stream.write(rendered + "\n")
            print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
            last_seen = seen
        if not args.watch:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
