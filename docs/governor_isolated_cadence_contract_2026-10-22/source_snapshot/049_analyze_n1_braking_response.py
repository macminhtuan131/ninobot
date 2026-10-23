#!/usr/bin/env python3
"""Compare saved N1 physical paths and command response across corner repairs."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "docs/n1_braking_response_2026-10-10"
RUNS = {"v18 late turn": "rough_n1_continuous_v18", "v19 early braking": "rough_n1_anticipation_v19",
        "v20 heading + braking": "rough_n1_heading_braking_v20"}


def samples(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    return {key:np.array([float(row[key]) for row in rows]) for key in rows[0] if key != "rough_recovery_mode"}


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    fig, axes = plt.subplots(1,3,figsize=(14,4.8),layout="constrained")
    result = {}
    colors = ["#a94340", "#bc820d", "#176aa0"]
    for (label,run),color in zip(RUNS.items(),colors):
        paths = list((ROOT / "rl_runs" / run / "route_pi/N1/screen").glob("*/summary.json"))
        if len(paths) != 1:
            raise ValueError("Expected one saved screen: " + run)
        summary = json.loads(paths[0].read_text())
        if not summary["complete"] or summary["evaluation_seeds"] != [13000,13001,13002]:
            raise ValueError("Require complete matching N1 screen seeds")
        episode = paths[0].parent / "episode-001"
        control = samples(episode / "control_trace.csv")
        drive = samples(episode / "drive_trace.csv")
        origin = control["sim_time_s"][0]-control["elapsed_s"][0]
        elapsed = drive["sim_time_s"]-origin
        axes[0].plot(control["physical_x_m"],control["physical_y_m"],color=color,label=label)
        axes[1].plot(control["elapsed_s"],control["physical_speed_m_s"],color=color,label=label+" physical")
        axes[1].plot(elapsed,drive["executed_linear_m_s"],color=color,ls="--",alpha=.8)
        axes[2].plot(control["elapsed_s"],control["physical_yaw_rate_rad_s"],color=color)
        axes[2].plot(elapsed,drive["executed_yaw_rad_s"],color=color,ls="--",alpha=.8)
        selected = (control["physical_y_m"] < 1.5) & (control["physical_x_m"] > 1.3)
        peak = float(np.max(control["physical_x_m"][selected]))
        result[label] = dict(summary=str(paths[0]), physical_arrivals=round(summary["success_rate"]*3),
            mean_physical_rmse_m=summary["metrics_all_episodes"]["truth_path_rmse_m"]["mean"],
            first_episode_peak_turn_x_m=peak, first_episode_x_overshoot_m=max(0.,peak-2.5),
            matching_seed=13000, settings="Geometry and 0.05m readiness RMSE limit unchanged")
    axes[0].plot([0,2.5,2.5],[0,0,6.2],"k--",label="drawn reference")
    axes[0].set(xlim=(1.3,3.7),ylim=(-.15,1.5),xlabel="Physical x (m)",ylabel="Physical y (m)",title="N1 corner, seed 13000")
    axes[0].set_aspect("equal",adjustable="box")
    axes[0].legend(fontsize=8)
    axes[1].set(xlim=(3,21),xlabel="Episode time (s)",ylabel="Forward speed (m/s)",title="Solid: physical; dashed: executed reference")
    axes[2].set(xlim=(3,21),xlabel="Episode time (s)",ylabel="Yaw rate (rad/s)",title="Solid: physical; dashed: executed reference")
    for ax in axes:
        ax.grid(alpha=.25)
    fig.savefig(OUTPUT / "n1_corner_response.png",dpi=160)
    plt.close(fig)
    (OUTPUT / "analysis.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
