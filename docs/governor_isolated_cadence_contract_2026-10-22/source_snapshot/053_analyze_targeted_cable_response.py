#!/usr/bin/env python3
"""Inspect saved second-cable actions and drive response; no new simulation."""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src/nino_rl")]
from nino_rl.tuning_objective import read_episode_rows


def samples(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Empty response trace: " + str(path))
    return {key: np.array([float(row[key]) for row in rows]) for key in rows[0]
            if key != "rough_recovery_mode"}


def bootstrap(values):
    values = np.asarray(values)
    rng = np.random.default_rng(42)
    draws = rng.integers(0, len(values), (10000, len(values)))
    return np.quantile(values[draws].mean(axis=1), [.025, .975]).tolist()


def inspect(directory):
    summary = json.loads((directory / "summary.json").read_text())
    rows = read_episode_rows(directory / "episodes.csv")
    if not summary["complete"] or len(rows) != 24 or [r["seed"] for r in rows] != list(range(64000,64024)):
        raise ValueError("Require complete matching 24-seed evidence")
    if any(not r["success"] or r["reward_pose_source"] != "ground_truth" for r in rows):
        raise ValueError("Require consistent physical arrivals")
    by_seed, pooled = {}, {}
    for row in rows:
        episode = directory / f"episode-{row['episode']:03d}"
        control = samples(episode / "control_trace.csv")
        drive = samples(episode / "drive_trace.csv")
        x, t = control["physical_x_m"], control["sim_time_s"]
        square = .5*(control["slip_left"]**2+control["slip_right"]**2)
        if not np.isclose(np.sqrt(np.mean(square)), row["rms_wheel_slip"], atol=1e-6):
            raise ValueError("Trace does not reproduce recorded episode slip")
        second = abs(x-4.45) <= .35
        first = abs(x-2.45) <= .35
        approach = (control["physical_goal_distance_m"] <= .5) & ~first & ~second
        start = (control["elapsed_s"] <= 1.) & ~first & ~second & ~approach
        phases = dict(start=start, cable1=first, cable2=second, approach=approach,
                      remaining=~(start|first|second|approach))
        contributions = {name:float(np.sum(square[mask])/len(square)) for name,mask in phases.items()}
        drive_x = np.interp(drive["sim_time_s"], t, x)
        selected = ((abs(drive_x-4.45) <= .35) & (drive["sim_time_s"] >= t[0])
                    & (drive["sim_time_s"] <= t[-1]))
        crossing = dict(action_windows=int(second.sum()),
            window_seconds=float(second.sum()*.1),
            mean_speed_scale=float(np.mean(control["speed_scale"][second])),
            physical_speed_m_s=float(np.mean(control["physical_speed_m_s"][second])),
            absolute_physical_yaw_rad_s=float(np.mean(abs(control["physical_yaw_rate_rad_s"][second]))),
            crossing_rms_slip=float(np.sqrt(np.mean(square[second]))),
            requested_linear_m_s=float(np.mean(drive["requested_linear_m_s"][selected])),
            executed_linear_m_s=float(np.mean(drive["executed_linear_m_s"][selected])),
            left_target_rad_s=float(np.mean(drive["left_target_rad_s"][selected])),
            right_target_rad_s=float(np.mean(drive["right_target_rad_s"][selected])),
            left_actual_rad_s=float(np.mean(drive["left_actual_rad_s"][selected])),
            right_actual_rad_s=float(np.mean(drive["right_actual_rad_s"][selected])),
            absolute_requested_yaw_rad_s=float(np.mean(abs(drive["requested_yaw_rad_s"][selected]))),
            common_applied_torque_nm=float(np.mean(.5*(drive["left_applied_nm"]+drive["right_applied_nm"])[selected])),
            absolute_differential_torque_nm=float(np.mean(abs(.5*(drive["right_applied_nm"]-drive["left_applied_nm"]))[selected])),
            wheel_tracking_rmse_rad_s=float(np.sqrt(np.mean(.5*((drive["left_actual_rad_s"]-drive["left_target_rad_s"])**2+
                (drive["right_actual_rad_s"]-drive["right_target_rad_s"])**2)[selected]))),
            limiter_flag_fraction=float(np.mean(.5*(drive["left_limited"]+drive["right_limited"])[selected])))
        by_seed[row["seed"]] = dict(phase_mean_square_contributions=contributions, second_cable=crossing,
                                   episode_slip=row["rms_wheel_slip"])
    for name in by_seed[64000]["second_cable"]:
        pooled[name] = float(np.mean([item["second_cable"][name] for item in by_seed.values()]))
    return dict(source=str(directory), benchmark=summary["benchmark_id"], episodes=by_seed,
                second_cable_episode_means=pooled,
                phase_mean_square_contributions={name:float(np.mean([item["phase_mean_square_contributions"][name]
                    for item in by_seed.values()])) for name in phases})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, default=ROOT / "rl_runs/flat_targeted_pi_recovery_v2/comparison.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/targeted_cable_response_2026-10-10")
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text())
    reference = json.loads((ROOT / "rl_runs/flat_value_scaled_seed43_v1/comparison.json").read_text())
    groups = {name:inspect(Path(report["summary"]).parent) for name,report in
              [("targeted_ppo",comparison["ppo"]),("pi",comparison["pi"]),("reference_ppo",reference["ppo"])]}
    if len({g["benchmark"] for g in groups.values()}) != 1:
        raise ValueError("Mismatched physical benchmarks")
    differences = {}
    for baseline in ("pi","reference_ppo"):
        differences[baseline] = {}
        for name in ("episode_slip", "crossing_rms_slip", "common_applied_torque_nm", "physical_speed_m_s", "absolute_requested_yaw_rad_s"):
            values = [groups["targeted_ppo"]["episodes"][seed]["episode_slip"]-groups[baseline]["episodes"][seed]["episode_slip"]
                      if name == "episode_slip" else
                      groups["targeted_ppo"]["episodes"][seed]["second_cable"][name]-groups[baseline]["episodes"][seed]["second_cable"][name]
                      for seed in range(64000,64024)]
            differences[baseline][name] = dict(mean_difference=float(np.mean(values)), scenario_ci95=bootstrap(values))
    result = dict(groups=groups, paired_differences=differences,
        phase_definition="Physical x within +/-0.35m of 2.45m/4.45m cables; goal distance <=0.5m approach; first second startup",
        weighting="Equal episode means; phase contributions sum to mean episode mean-square slip",
        limitation="Scenario bootstrap uses one targeted training seed; command/response associations do not establish causality. "
                   "Drive pose interpolation is limited to the recorded control-time range; limiter flags do not identify the limiting mechanism.",
        recommendation="Do not increase slip reward again based on these data alone; examine bounded crossing acceleration/reference response before another pilot.")
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output / "analysis.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    lines = ["# Second-cable response after targeted slip reward", "",
             "Saved data only. Each column averages the same 24 seeds; cable window x=4.45 +/-0.35m.", "",
             "| Second-cable metric | Previous PPO | Targeted PPO | PI |", "|---|---:|---:|---:|"]
    for name in groups["pi"]["second_cable_episode_means"]:
        lines.append("| " + name + " | " + " | ".join(f"{groups[k]['second_cable_episode_means'][name]:.6f}" for k in
            ("reference_ppo","targeted_ppo","pi")) + " |")
    lines += ["", "| Phase mean-square slip contribution | Previous PPO | Targeted PPO | PI |", "|---|---:|---:|---:|"]
    for phase in groups["pi"]["phase_mean_square_contributions"]:
        lines.append("| " + phase + " | " + " | ".join(f"{groups[k]['phase_mean_square_contributions'][phase]:.8f}" for k in
            ("reference_ppo","targeted_ppo","pi")) + " |")
    lines += ["", "Paired differences and 95% scenario bootstrap intervals are in analysis.json.", "",
              result["limitation"], "", result["recommendation"], ""]
    (args.output / "REPORT.md").write_text("\n".join(lines))
    print("Saved",args.output / "REPORT.md")


if __name__ == "__main__":
    main()
