#!/usr/bin/env python3
"""Inspect existing flat episode summaries without launching ROS or simulation."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN = ROOT / "rl_runs/flat_value_scaled_pilot_v1"


def read_rows(path):
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    indexed = {int(row["seed"]): row for row in rows}
    if len(indexed) != 24 or len(rows) != 24 or sorted(indexed) != list(range(64000, 64024)):
        raise ValueError("Expected exactly the original 24 paired evaluation seeds")
    if any(row["success"].lower() != "true" or row["reward_pose_source"] != "ground_truth"
           for row in rows):
        raise ValueError("Do not interpret comfort without complete physical arrivals")
    return indexed


def analyze(run, output):
    comparison = json.loads((run / "comparison.json").read_text())
    groups = {label: read_rows(Path(comparison[label]["summary"]).with_name("episodes.csv"))
              for label in ("ppo", "pi")}
    pairs = []
    names = ("rms_wheel_slip", "time_seconds", "mean_speed_scale", "mean_ground_speed_m_s",
             "heading_rmse_deg", "truth_path_rmse_m", "rms_wheel_torque_nm",
             "rms_vertical_acceleration_m_s2", "max_abs_wheel_slip")
    for seed in sorted(groups["ppo"]):
        item = {"seed": seed}
        for name in names:
            for label in groups:
                item[f"{label}_{name}"] = float(groups[label][seed][name])
            item[f"delta_{name}"] = item[f"ppo_{name}"] - item[f"pi_{name}"]
        pairs.append(item)
    delta = np.array([row["delta_rms_wheel_slip"] for row in pairs])
    associations = {}
    for name in names[1:]:
        values = np.array([row[f"delta_{name}"] for row in pairs])
        associations[name] = (float(np.corrcoef(delta, values)[0, 1])
                              if np.std(values) > 1e-12 else None)
    rng = np.random.default_rng(42)
    draws = rng.integers(0, 24, size=(10000, 24))
    interval = np.quantile(delta[draws].mean(axis=1), [0.025, 0.975]).tolist()
    top = sorted(pairs, key=lambda row: row["delta_rms_wheel_slip"], reverse=True)[:6]
    result = {
        "source_comparison": str((run / "comparison.json").resolve()),
        "seeds": sorted(groups["ppo"]), "paired_episode_count": 24,
        "mean_slip_difference": float(delta.mean()), "scenario_bootstrap_ci95": interval,
        "episodes_with_more_slip": int(np.sum(delta > 0)),
        "episodes_with_less_slip": int(np.sum(delta < 0)),
        "largest_slip_increases": top, "episode_delta_pearson_associations": associations,
        "phase_attribution_available": False,
        "limitation": "Original runs saved episode-level slip and pose trajectories, not per-action wheel slip/actions. "
                      "Cannot locate the extra slip in crossings, acceleration, steering or approach. "
                      "Correlations are exploratory, not causal; one training seed and asynchronous simulation.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    with (output / "paired_episodes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    lines = ["# Flat saved-slip inspection", "",
             "Read-only analysis of scale-only PPO and matching PI on seeds 64000–64023.", "",
             f"Mean paired RMS slip increase: **{delta.mean():.6f}**; scenario bootstrap 95% interval "
             f"**[{interval[0]:.6f}, {interval[1]:.6f}]**.",
             f"PPO had more slip in **{int(np.sum(delta > 0))}/24** episodes.", "",
             "## Episodes contributing the largest slip increases", "",
             "| Seed | PPO RMS slip | PI RMS slip | Difference | PPO time | PI time |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in top:
        lines.append(f"| {row['seed']} | {row['ppo_rms_wheel_slip']:.4f} | {row['pi_rms_wheel_slip']:.4f} | "
                     f"{row['delta_rms_wheel_slip']:+.4f} | {row['ppo_time_seconds']:.2f} | {row['pi_time_seconds']:.2f} |")
    lines += ["", "## What the saved data can establish", "",
              "Episode totals identify which scenarios account for the mean difference. Pose trajectories do not contain "
              "wheel speed or action-window slip, so they cannot assign that difference to a cable, acceleration, yaw "
              "correction or the final approach. No phase-specific cause is claimed.", "",
              "Exploratory associations are recorded in analysis.json; they do not establish causation. The confidence "
              "interval covers paired evaluation scenarios, not variation across independent training seeds.", "",
              "The second-seed comparison records per-action left/right slip and existing drive diagnostics. This adds "
              "observability to that comparison without changing the reward or physical scoring. It cannot reconstruct "
              "missing traces from the first run.", ""]
    (output / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({key: result[key] for key in ("mean_slip_difference", "scenario_bootstrap_ci95",
                       "episodes_with_more_slip", "phase_attribution_available")}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/flat_saved_slip_2026-10-10")
    args = parser.parse_args()
    analyze(args.run, args.output)


if __name__ == "__main__":
    main()
