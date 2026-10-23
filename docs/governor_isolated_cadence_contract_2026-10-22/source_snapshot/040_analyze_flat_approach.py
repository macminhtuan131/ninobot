#!/usr/bin/env python3
"""Compare saved flat evaluation poses; no ROS, simulator or policy execution."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml


def read_trajectory(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    data = np.asarray([[float(row[key]) for key in
                        ("time_s", "x_m", "y_m", "yaw_rad")] for row in rows])
    if (len(data) < 2 or not np.isfinite(data).all()
            or not np.all(np.diff(data[:, 0]) > 0)):
        raise ValueError(f"Need finite, increasing trajectory timestamps: {path}")
    return data


def load_run(path):
    summary = json.loads((path / "summary.json").read_text())
    if not summary.get("complete"):
        raise ValueError(f"Incomplete evaluation: {path}")
    config = yaml.safe_load((path / "config.yaml").read_text())
    if config.get("routes", {}).get("enabled", False):
        raise ValueError("This diagnostic supports the straight flat course only")
    with (path / "episodes.csv").open() as stream:
        rows = {int(row["seed"]): row for row in csv.DictReader(stream)}
    return summary, config, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ppo-run", type=Path, required=True)
    parser.add_argument("--pi-run", type=Path, required=True)
    parser.add_argument("--slow-pi-run", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[61000, 61005, 61019, 61022])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = [("PI", args.pi_run, "#6b7280"),
               ("Slower PI", args.slow_pi_run, "#d97706"),
               ("PPO speed/yaw", args.ppo_run, "#0284c7")]
    loaded = [(label, path, color, *load_run(path)) for label, path, color in sources]
    first_summary = loaded[0][3]
    for _, path, _, summary, _, rows in loaded:
        for key in ("benchmark_id", "seed", "episodes", "phase", "randomized"):
            if summary.get(key) != first_summary.get(key):
                raise ValueError(f"Evaluation mismatch {key}: {path}")
        if not set(args.seeds).issubset(rows):
            raise ValueError(f"Requested seeds missing: {path}")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"runs": {label: str(path.resolve()) for label, path, _ in sources},
              "limitations": [
                  "Speeds are finite differences of saved physical poses, not motor feedback or commands.",
                  "Physical and odometry coordinates assume the common reset origin and heading of these evaluations.",
                  "No time-resolved policy actions, commanded yaw or controller saturation were saved.",
                  "Terminal outcome/endpoint metrics come from episodes.csv; the last overlapping pose sample can precede the scoring sample.",
                  "Plots identify motion and estimation differences; they cannot prove the cause of insufficient steering.",
                  "Comparisons describe one checkpoint on fixed terrain; they are not independent training replicas."],
              "seeds": {}}
    for seed in args.seeds:
        fig, axes = plt.subplots(3, 2, figsize=(13, 11), layout="constrained")
        ax = axes.ravel()
        report["seeds"][str(seed)] = {}
        for label, path, color, summary, config, rows in loaded:
            row = rows[seed]
            episode = path / f"episode-{int(row['episode']):03d}"
            estimated = read_trajectory(episode / "trajectory.csv")
            physical = read_trajectory(episode / "ground_truth" / "trajectory.csv")
            # Compare only their overlapping time range, without extrapolation.
            mask = ((physical[:, 0] >= estimated[0, 0])
                    & (physical[:, 0] <= estimated[-1, 0]))
            physical = physical[mask]
            if len(physical) < 2:
                raise ValueError(f"Insufficient overlapping poses: {episode}")
            t = physical[:, 0]
            estimate_xy = np.column_stack([np.interp(t, estimated[:, 0], estimated[:, j])
                                           for j in (1, 2)])
            estimate_yaw = np.interp(t, estimated[:, 0], np.unwrap(estimated[:, 3]))
            yaw_error = np.arctan2(np.sin(estimate_yaw - physical[:, 3]),
                                   np.cos(estimate_yaw - physical[:, 3]))
            goal = np.asarray(config["navigation"]["goal_pose"][:2])
            truth_distance = np.linalg.norm(physical[:, 1:3] - goal, axis=1)
            estimated_distance = np.linalg.norm(estimate_xy - goal, axis=1)
            position_error = np.linalg.norm(estimate_xy - physical[:, 1:3], axis=1)
            dt = np.diff(t)
            forward_speed = np.diff(physical[:, 1]) / dt
            times_mid = (t[:-1] + t[1:]) / 2
            ax[0].plot(physical[:, 1], physical[:, 2], color=color, label=label)
            ax[1].plot(times_mid, forward_speed, color=color, label=label, alpha=.8)
            ax[2].plot(t, truth_distance, color=color, label=label + " physical")
            ax[2].plot(t, estimated_distance, color=color, linestyle="--", alpha=.6,
                       label=label + " estimated")
            ax[3].plot(t, position_error, color=color, label=label)
            ax[4].plot(t, np.rad2deg(physical[:, 3]), color=color, label=label + " physical")
            ax[4].plot(t, np.rad2deg(estimate_yaw), color=color, linestyle="--", alpha=.6)
            ax[5].plot(t, np.rad2deg(yaw_error), color=color, label=label)
            at_target = min(float(config["target_finish_seconds"]), float(t[-1]))
            report["seeds"][str(seed)][label] = {
                "episode": int(row["episode"]), "termination": row["termination"],
                "time_seconds": float(row["time_seconds"]),
                "mean_speed_scale": float(row["mean_speed_scale"]),
                "physical_path_rmse_m": float(row["truth_path_rmse_m"]),
                "physical_endpoint_error_m": float(row["truth_endpoint_error_m"]),
                "position_error_max_m": float(position_error.max()),
                "physical_goal_distance_at_target_m": float(np.interp(at_target, t, truth_distance)),
                "target_sample_time_s": at_target,
                "physical_goal_distance_last_paired_sample_m": float(truth_distance[-1]),
                "estimated_goal_distance_last_paired_sample_m": float(estimated_distance[-1]),
            }
        goal = loaded[0][4]["navigation"]["goal_pose"]
        ax[0].axhline(0, color="black", linewidth=.8, linestyle=":")
        ax[0].scatter([goal[0]], [goal[1]], marker="*", s=100, color="green", label="Goal")
        ax[0].set(xlabel="Physical x (m)", ylabel="Physical y (m)", title="Physical trajectory")
        titles = [("Derived physical forward speed", "m/s"),
                  ("Goal distance: solid physical, dashed estimated", "m"),
                  ("Estimated versus physical position error", "m"),
                  ("Heading: solid physical, dashed estimated", "degrees"),
                  ("Estimated minus physical heading", "degrees")]
        for axis, (title, unit) in zip(ax[1:], titles):
            axis.set(title=title, xlabel="Simulation time (s)", ylabel=unit)
            axis.axvline(loaded[0][4]["target_finish_seconds"], color="red", linestyle=":")
        ax[2].axhline(loaded[0][4]["goal_tolerance_m"], color="green", linestyle=":")
        for axis in ax:
            axis.grid(alpha=.2)
            axis.legend(fontsize=7)
        outcomes = "; ".join(f"{label}: {rows[seed]['termination']}" for label, _, _, _, _, rows in loaded)
        fig.suptitle(f"Seed {seed} — {outcomes}")
        fig.savefig(args.output / f"seed_{seed}.png", dpi=140)
        plt.close(fig)
    (args.output / "approach_analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {len(args.seeds)} diagnostic figures and approach_analysis.json to {args.output}")


if __name__ == "__main__":
    main()
