#!/usr/bin/env python3
"""Tune the combined course against one running Gazebo instance, sequentially."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = ROOT / "artifacts/old_1_5m/nino_ppo_final.zip"
REWARD_WEIGHTS = {
    "progress_weight": (5.0, 20.0),
    "lateral_weight": (0.2, 1.0),
    "heading_weight": (0.1, 0.6),
    "impact_weight": (0.015, 0.15),
    "body_rate_weight": (0.015, 0.15),
    "attitude_weight": (0.2, 1.0),
    "slip_weight": (0.03, 0.3),
    "smoothness_weight": (0.005, 0.08),
    "effort_weight": (0.01, 0.1),
    "saturation_weight": (0.01, 0.1),
    "residual_effort_weight": (0.001, 0.02),
    "torque_rate_weight": (0.005, 0.08),
    "velocity_weight": (0.03, 0.3),
    "overspeed_weight": (0.15, 0.8),
    "yaw_tracking_weight": (0.05, 0.4),
    "goal_braking_weight": (0.05, 0.4),
    "time_penalty": (0.01, 0.1),
    "stall_penalty": (0.2, 1.0),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "src/nino_rl/config/combined_course.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "rl_runs/combined_optuna")
    parser.add_argument("--init-model", type=Path, default=DEFAULT_MODEL,
                        help="Old actor checkpoint; omitted with --from-scratch")
    parser.add_argument("--from-scratch", action="store_true",
                        help="Tune policy architecture and initialization without actor transfer")
    parser.add_argument("--trials", type=int, default=12)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--eval-episodes", type=int, default=12)
    parser.add_argument("--eval-seed", type=int, default=20_000)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    if args.trials < 1 or args.timesteps < 1 or args.eval_episodes < 1:
        parser.error("--trials, --timesteps and --eval-episodes must be positive")
    return args


def sample_config(trial, base: dict, *, from_scratch: bool) -> dict:
    """Keep task geometry and safety thresholds fixed while tuning learning."""
    config = deepcopy(base)
    ppo = config["ppo"]
    reward = config["reward_v2"]
    for name, (low, high) in REWARD_WEIGHTS.items():
        reward[name] = trial.suggest_float(f"reward_v2.{name}", low, high)
    # Preserve the terminal success/failure contract. Physical success is
    # measured separately by evaluate, rather than inferred from return.
    reward["challenge_entry_bonus"] = trial.suggest_float("challenge_entry_bonus", 0.5, 3.0)
    reward["challenge_clear_bonus"] = trial.suggest_float("challenge_clear_bonus", 3.0, 12.0)
    reward["challenge_goal_bonus"] = trial.suggest_float("challenge_goal_bonus", 40.0, 110.0)
    ppo["learning_rate"] = trial.suggest_float("learning_rate", 1e-5, 1e-4, log=True)
    ppo["gamma"] = trial.suggest_categorical("gamma", [0.99, 0.995, 0.997, 0.999])
    ppo["gae_lambda"] = trial.suggest_float("gae_lambda", 0.90, 0.98)
    ppo["n_steps"] = trial.suggest_categorical("n_steps", [1024, 2048])
    ppo["batch_size"] = trial.suggest_categorical("batch_size", [128, 256, 512])
    ppo["n_epochs"] = trial.suggest_categorical("n_epochs", [3, 5, 8])
    ppo["clip_range"] = trial.suggest_float("clip_range", 0.10, 0.25)
    ppo["ent_coef"] = trial.suggest_float("ent_coef", 1e-5, 5e-3, log=True)
    ppo["vf_coef"] = trial.suggest_float("vf_coef", 0.3, 0.8)
    ppo["max_grad_norm"] = trial.suggest_float("max_grad_norm", 0.3, 0.8)
    ppo["target_kl"] = trial.suggest_float("target_kl", 0.01, 0.03)
    if from_scratch:
        width = trial.suggest_categorical("actor_width", [64, 128, 256])
        ppo["actor_layers"] = [width, width]
        ppo["critic_layers"] = [trial.suggest_categorical("critic_width", [128, 256]), 128]
        ppo["history_features"] = trial.suggest_categorical("history_features", [32, 64, 96])
        ppo["activation"] = trial.suggest_categorical("activation", ["elu", "tanh"])
        ppo["initial_speed_scale"] = trial.suggest_float("initial_speed_scale", 0.55, 0.85)
        ppo["initial_action_std"] = [
            trial.suggest_float(f"initial_action_std_{name}", low, high)
            for name, low, high in (("speed", 0.1, 0.35), ("torque", 0.05, 0.25),
                                    ("steering", 0.025, 0.15))
        ]
    return config


def run_logged(command: list[str], logfile: Path) -> None:
    print("Running:", " ".join(command), flush=True)
    with logfile.open("w", encoding="utf-8") as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)


def only_file(directory: Path, name: str) -> Path:
    matches = list(directory.glob(f"*/{name}"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} under {directory}; found {len(matches)}")
    return matches[0]


def main() -> None:
    args = parse_args()
    try:
        import optuna
    except ImportError as error:
        raise SystemExit("Install Optuna: python -m pip install optuna") from error
    config_path = args.config.expanduser().resolve()
    base = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if base.get("task") != "combined_course":
        raise SystemExit("This tuner requires a combined_course config")
    if args.timesteps < 2048:
        raise SystemExit("Use at least 2048 steps so every trial has a PPO update")
    model_path = None if args.from_scratch else args.init_model.expanduser().resolve()
    if model_path is not None and not model_path.is_file():
        raise SystemExit(f"Missing actor checkpoint: {model_path}")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    mesh_path = ROOT / "src/nino_description/terrains/combined_rough_ground.stl"
    if not mesh_path.is_file():
        raise SystemExit("Generate the combined world before tuning")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    contract = {
        "config_sha256": digest(config_path), "mesh_sha256": digest(mesh_path),
        "tuner_sha256": digest(Path(__file__)),
        "init_model_sha256": digest(model_path) if model_path else None,
        "timesteps": args.timesteps, "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed, "device": args.device,
        "from_scratch": args.from_scratch,
    }
    study = optuna.create_study(
        study_name="combined_course", direction="maximize",
        storage=f"sqlite:///{(output / 'study.db').as_posix()}", load_if_exists=True,
    )
    if study.user_attrs.get("contract") not in (None, contract):
        raise SystemExit("Study inputs changed; choose a new --output directory")
    study.set_user_attr("contract", contract)

    def objective(trial) -> float:
        trial_dir = output / f"trial_{trial.number:04d}"
        trial_dir.mkdir(exist_ok=False)
        config = sample_config(trial, base, from_scratch=args.from_scratch)
        trial_config = trial_dir / "trial.yaml"
        trial_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        train_dir, eval_dir = trial_dir / "train", trial_dir / "eval"
        trial.set_user_attr("directory", str(trial_dir))
        command = ["ros2", "run", "nino_rl", "train", "--device", args.device,
                   "--config", str(trial_config), "--timesteps", str(args.timesteps),
                   "--checkpoint-every", str(args.timesteps + 1), "--output", str(train_dir)]
        if model_path:
            command.extend(("--init-model", str(model_path)))
        run_logged(command, trial_dir / "train.log")
        model = only_file(train_dir, "nino_ppo_final.zip")
        run_logged(["ros2", "run", "nino_rl", "evaluate", "--device", args.device,
                    "--config", str(model.parent / "ppo.yaml"), "--model", str(model),
                    "--episodes", str(args.eval_episodes), "--seed", str(args.eval_seed),
                    "--randomized", "--output", str(eval_dir)], trial_dir / "evaluate.log")
        summary = json.loads(only_file(eval_dir, "summary.json").read_text(encoding="utf-8"))
        if not summary.get("complete"):
            raise RuntimeError(f"Incomplete evaluation: {eval_dir}")
        success = float(summary["success_rate"])
        progress = float(summary["metrics_all_episodes"]["final_progress_fraction"]["mean"])
        rmse = float(summary["metrics_all_episodes"]["truth_path_rmse_m"]["mean"])
        trial.set_user_attr("success_rate", success)
        trial.set_user_attr("final_progress_fraction", progress)
        trial.set_user_attr("truth_path_rmse_m", rmse)
        trial.set_user_attr("model", str(model))
        print(f"Trial {trial.number}: success={success:.3f}, progress={progress:.3f}, "
              f"truth RMSE={rmse:.3f} m", flush=True)
        return 100.0 * success + 10.0 * progress - rmse

    try:
        study.optimize(objective, n_trials=args.trials, n_jobs=1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Trial failed ({error.returncode}); inspect logs in {output}") from error
    best = study.best_trial
    source = Path(best.user_attrs["directory"]) / "trial.yaml"
    (output / "best_trial.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Best trial: {best.number}, score={best.value:.3f}, model={best.user_attrs['model']}")
    print(f"Best config: {output / 'best_trial.yaml'}")
    print("Validate with new evaluation seeds before a long training run.")


if __name__ == "__main__":
    main()
