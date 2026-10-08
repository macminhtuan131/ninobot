"""Shared baseline/PPO evaluation and provenance-checked report comparison."""
from __future__ import annotations

import argparse
import csv
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np

from nino_rl.core import load_config
from nino_rl.control_v2 import baseline_action, action_size, validate_model, validate_action_mode
from nino_rl.trajectory_metrics import write_csv

METRICS = ("path_rmse_m", "cross_track_rmse_m", "path_p95_m", "path_max_m",
           "heading_rmse_deg", "endpoint_error_m", "final_progress_fraction",
           "backtracking_m", "time_seconds", "rms_vertical_acceleration_m_s2",
           "peak_vertical_acceleration_m_s2", "rms_wheel_slip", "rms_wheel_torque_nm",
           "challenge_choice_fraction", "challenge_clear_fraction")
TRUTH_METRICS = ("truth_path_rmse_m", "truth_path_p95_m", "truth_endpoint_error_m",
                 "truth_heading_rmse_deg", "odom_truth_position_error_m")


def benchmark_id(config):
    # Reward/PPO differences are allowed; geometry, sensing, task and test
    # perturbations must match. This is not a hash of external Gazebo binaries.
    ignored = {"reward", "reward_v2", "ppo", "device", "seed", "evaluation_baseline",
               "evaluation_speed_only", "evaluation_control_trace"}
    task = {k: v for k, v in config.items() if k not in ignored}
    return hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()


def prepare_evaluation_config(config, *, phase=1, randomized=False, route=None,
                              flat_stage=None, baseline=False, speed_only=False,
                              control_trace=False):
    """Freeze task settings identically for CLI evaluation and tuning scores."""
    config = deepcopy(config)
    if config.get("routes", {}).get("enabled", False):
        config["routes"]["selection"] = "round_robin"
        if route is not None:
            config["routes"]["fixed_route"] = route
    elif route is not None:
        raise ValueError("--route requires an enabled routes configuration")
    from nino_rl.routes import RouteSet
    RouteSet(config)
    config["curriculum"]["fixed_phase"] = phase
    config["domain_randomization"]["enabled"] = randomized
    config["domain_randomization"]["phase_scales"] = [1.0] * 6
    config["evaluation_baseline"] = baseline
    if speed_only and config.get("action_mode", "wheel_torque") != "wheel_torque":
        raise ValueError("--speed-only requires a wheel_torque model/config")
    config["evaluation_speed_only"] = speed_only
    if control_trace:
        config["evaluation_control_trace"] = True
    adaptive = config.get("adaptive_terrain", {})
    flat = config.get("flat_curriculum", {})
    if flat.get("enabled", False):
        selected = flat_stage if flat_stage is not None else flat.get("evaluation_stage", len(flat["stages"]) - 1)
        if not 0 <= selected < len(flat["stages"]):
            raise ValueError("--flat-stage is outside the configured flat curriculum")
        flat["fixed_stage"] = selected
    elif flat_stage is not None:
        raise ValueError("--flat-stage requires an enabled flat_curriculum")
    if adaptive.get("enabled", False):
        adaptive["progress_on_success"] = False
        adaptive["initial_features"] = (int(flat["stages"][flat["fixed_stage"]]["adaptive_features"])
            if flat.get("enabled", False) else int(adaptive.get("evaluation_features", 8)))
    return config


def summarize(rows, metadata):
    successes = [r for r in rows if r["success"]]
    summary = {
        **metadata, "episodes": len(rows),
        "success_rate": float(np.mean([r["success"] for r in rows])),
        "on_time_success_rate": float(np.mean([r["finished_within_target_time"] for r in rows])),
        "termination_counts": {reason: sum(r["termination"] == reason for r in rows)
                               for reason in sorted({r["termination"] for r in rows})},
        "metrics_all_episodes": {}, "metrics_successful_episodes": {},
    }
    route_ids = sorted({row["route_id"] for row in rows if row.get("route_id")})
    if route_ids:
        summary["per_route"] = {}
        for route_id in route_ids:
            selected = [row for row in rows if row.get("route_id") == route_id]
            summary["per_route"][route_id] = {
                "episodes": len(selected),
                "success_rate": float(np.mean([row["success"] for row in selected])),
                "truth_path_rmse_m": float(np.mean([row["truth_path_rmse_m"] for row in selected])),
                "termination_counts": {reason: sum(row["termination"] == reason for row in selected)
                    for reason in sorted({row["termination"] for row in selected})},
            }
    extra = tuple(name for name in TRUTH_METRICS if all(name in row for row in rows))
    for name in METRICS + extra:
        values = np.asarray([r[name] for r in rows], float)
        summary["metrics_all_episodes"][name] = {
            "mean": float(values.mean()), "std": float(values.std()),
            "min": float(values.min()), "max": float(values.max()),
        }
        summary["metrics_successful_episodes"][name] = (
            float(np.mean([r[name] for r in successes])) if successes else None)
    return summary


def run(baseline=False):
    from ament_index_python.packages import get_package_share_directory
    parser = argparse.ArgumentParser(description="Evaluate PI baseline or deterministic PPO on matching seeds")
    parser.add_argument("--config", type=Path,
        default=Path(get_package_share_directory("nino_rl")) / "config/ppo.yaml")
    if baseline:
        parser.add_argument("--baseline-speed-scale", type=float, default=1.0,
                            help="Fixed PI speed/yaw scaling in (0,1]; preserves task references and deadlines")
    if not baseline:
        parser.add_argument("--model", required=True, type=Path)
        parser.add_argument("--device", choices=("cuda", "cpu", "auto"), default="cuda")
        parser.add_argument("--speed-only", action="store_true",
                            help="Keep PPO speed scaling and disable its torque corrections (evaluation only)")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--phase", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--seed", type=int, default=10000)
    parser.add_argument("--seeds", type=int, nargs="+",
                        help="Explicit scenario seeds for a targeted replay")
    parser.add_argument("--control-trace", action="store_true",
                        help="Save policy and stamped motor-controller diagnostic CSVs")
    parser.add_argument("--flat-stage", type=int,
                        help="Evaluate a specific zero-based flat curriculum stage; default is its final stage")
    parser.add_argument("--randomized", action="store_true",
                        help="Enable full-strength residual/sensor perturbations")
    parser.add_argument("--route", help="Evaluate one drawn route ID; omit for round-robin route coverage")
    parser.add_argument("--output", type=Path, default=Path("rl_runs/baseline" if baseline else "rl_runs/evaluation"))
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")
    if baseline and not 0.0 < args.baseline_speed_scale <= 1.0:
        parser.error("--baseline-speed-scale must be finite and in (0,1]")
    seeds = args.seeds if args.seeds is not None else list(range(args.seed, args.seed + args.episodes))
    if len(set(seeds)) != len(seeds) or any(seed < 0 for seed in seeds):
        parser.error("--seeds must contain distinct nonnegative integers")
    args.episodes = len(seeds)
    args.seed = seeds[0]
    speed_only = not baseline and args.speed_only
    try:
        config = prepare_evaluation_config(load_config(args.config), phase=args.phase,
            randomized=args.randomized, route=args.route, flat_stage=args.flat_stage,
            baseline=baseline, speed_only=speed_only, control_trace=args.control_trace)
    except ValueError as error:
        parser.error(str(error))
    model = None
    if not baseline:
        import torch
        from stable_baselines3 import PPO
        device = "cuda" if args.device == "auto" else args.device
        if device == "cuda" and not torch.cuda.is_available():
            parser.error("CUDA unavailable; run ros2 run nino_rl check_cuda")
        model = PPO.load(args.model, device=device)
        validate_model(model, 60 * config["policy_v2"]["history_frames"], action_size(config))
        validate_action_mode(model, config)
    output = args.output.expanduser().resolve() / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True, exist_ok=False)
    import yaml
    (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    metadata = {
        "schema_version": 1, "controller": ("path_pi_baseline" if config.get("routes", {}).get("enabled", False)
                                             else "straight_pi_baseline") if baseline else (
                                                 "ppo_speed_only" if speed_only else "ppo"),
        "action_ablation": "speed_only" if speed_only else "none",
        "baseline_speed_scale": args.baseline_speed_scale if baseline else None,
        "model": str(args.model.resolve()) if not baseline else None,
        "phase": args.phase, "seed": args.seed, "randomized": args.randomized,
        "evaluation_seeds": seeds, "control_trace": args.control_trace,
        "benchmark_id": benchmark_id(config),
        "pose_source": ("imu_encoder_odometry" if config.get("odometry_assistance", {}).get("enabled", False)
                        else "wheel_odometry"),
        "metric_weighting": "simulation_time_trapezoid",
        "reference": "configured drawn routes with ordered spatial gates in odom" if
                     config.get("routes", {}).get("enabled", False) else
                     "fixed straight line from configured start_pose to goal_pose in odom",
        "per_episode_plot": "trajectory.png; raw samples are in trajectory.csv",
    }
    if config.get('odometry_assistance', {}).get('corridor_lidar', {}).get('enabled', False):
        metadata['pose_source'] = 'imu_encoder_lidar_odometry'
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    # Create ROS only after validating the model/config.
    from nino_rl.ros_env import NinoGazeboEnv
    env = NinoGazeboEnv(config, total_training_steps=1)
    rows = []
    try:
        for episode, scenario_seed in enumerate(seeds):
            observation, reset_info = env.reset(seed=scenario_seed)
            episode_output = output / f"episode-{episode+1:03d}"
            trace_files = []
            if args.control_trace:
                episode_output.mkdir(parents=True, exist_ok=True)
                trace_files = [(episode_output / name).open("w", newline="", encoding="utf-8")
                               for name in ("control_trace.csv", "drive_trace.csv")]
            trace_writers = [None, None]
            while True:
                action = baseline_action(config) if baseline else model.predict(observation, deterministic=True)[0]
                if baseline:
                    action[0] = 2.0 * args.baseline_speed_scale - 1.0
                start_sim = env.lockstep_sim_time
                try:
                    observation, _, terminated, truncated, info = env.step(action)
                    if args.control_trace:
                        samples = env.ros.drive_diagnostics(start_sim, env.lockstep_sim_time)
                        if not samples:
                            raise RuntimeError("No stamped drive diagnostics for this action; restart the flat simulator with the updated effort_drive")
                        sample_sets = ([info["control_trace"]], samples)
                        for index, sample_rows in enumerate(sample_sets):
                            for sample in sample_rows:
                                sample = {"seed": scenario_seed, **sample}
                                if trace_writers[index] is None:
                                    trace_writers[index] = csv.DictWriter(trace_files[index], fieldnames=list(sample))
                                    trace_writers[index].writeheader()
                                trace_writers[index].writerow(sample)
                            trace_files[index].flush()
                except BaseException:
                    for stream in trace_files:
                        stream.close()
                    raise
                if terminated or truncated:
                    break
            for stream in trace_files:
                stream.close()
            row = dict(info["episode_metrics"])
            row.update(episode=episode + 1, seed=scenario_seed,
                       controller=metadata["controller"], phase=args.phase,
                       cable_count=reset_info["cable_count"],
                       cable_diameter_m=reset_info["cable_diameter_m"],
                       cable_angle_deg=reset_info["cable_angle_deg"])
            rows.append(row)
            env.trajectory.save(output / f"episode-{episode+1:03d}")
            env.truth_trajectory.save(output / f"episode-{episode+1:03d}" / "ground_truth")
            # Persist each completed episode, so a later transport failure does
            # not lose previous measurements. No success row for a broken run.
            write_csv(output / "episodes.csv", rows)
            print(
                f"{episode+1}: reached={row['goal_reached']}; "
                f"time={row['time_seconds']:.2f}s, "
                f"endpoint={row['endpoint_distance_m']:.3f}m, "
                f"challenges={row['challenges_cleared']}/{row['traversable_challenges']}, "
                f"lateral drift={row['final_abs_lateral_drift_m']:.3f}m, "
                f"path RMSE={row['path_rmse_m']:.3f}m"
            )
    finally:
        env.close()
        if rows:
            summary = summarize(rows, {**metadata, "complete": len(rows) == args.episodes,
                                       "requested_episodes": args.episodes})
            (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(f"Saved evaluation: {output}")


def compare_summaries(baseline, candidate):
    for report in (baseline, candidate):
        if not report.get("complete"):
            raise ValueError("Do not compare incomplete evaluations")
    for key in ("schema_version", "benchmark_id", "phase", "seed", "episodes", "randomized", "pose_source"):
        if baseline.get(key) != candidate.get(key):
            raise ValueError(f"Evaluation mismatch: {key}; rerun with identical test settings")
    expected_seeds = lambda report: report.get("evaluation_seeds", list(range(report["seed"], report["seed"] + report["episodes"])))
    if expected_seeds(baseline) != expected_seeds(candidate):
        raise ValueError("Evaluation mismatch: evaluation_seeds")
    result = {"phase": baseline["phase"], "episodes": baseline["episodes"],
              "baseline_speed_scale": baseline.get("baseline_speed_scale", 1.0),
              "delta_convention": "candidate minus baseline; negative error/time is better",
              "success_rate": {"baseline": baseline["success_rate"], "candidate": candidate["success_rate"],
                               "delta": candidate["success_rate"] - baseline["success_rate"]},
              "metrics": {}}
    extra = tuple(name for name in TRUTH_METRICS
                  if name in baseline['metrics_all_episodes'] and name in candidate['metrics_all_episodes'])
    for name in METRICS + extra:
        b = baseline["metrics_all_episodes"][name]["mean"]
        c = candidate["metrics_all_episodes"][name]["mean"]
        result["metrics"][name] = {"baseline": b, "candidate": c, "delta": c-b}
    result["interpretation"] = (
        "Compare success first, then errors and comfort. Early failure can lower RMSE/time. "
        "Seeds match terrain draws; ROS/Gazebo transport is still asynchronous. "
        "No statistical significance or physical ground-truth accuracy is claimed.")
    return result


def compare_main():
    parser = argparse.ArgumentParser(description="Compare complete, matching evaluation summaries")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("comparison.json"))
    args = parser.parse_args()
    try:
        result = compare_summaries(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
