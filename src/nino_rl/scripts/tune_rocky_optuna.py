#!/usr/bin/env python3
"""Tune Rocky Hall PPO against one already running Gazebo world.

Run from the repository root in a shell with ROS, the venv, and install/setup.bash
sourced. Each Optuna trial trains and evaluates sequentially.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("src/nino_rl/config/rocky_tracking.yaml"))
    parser.add_argument("--output", type=Path, default=Path("rl_runs/rocky_optuna"))
    parser.add_argument("--trials", type=int, default=12, help="Additional trials to run")
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--eval-episodes", type=int, default=10)
    parser.add_argument("--eval-seed", type=int, default=10_000)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args()
    if args.trials < 1 or args.eval_episodes < 1:
        parser.error("--trials and --eval-episodes must be positive")
    return args


def run_logged(command: list[str], log_path: Path) -> None:
    print("Running:", " ".join(command), flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def only_file(directory: Path, name: str) -> Path:
    matches = list(directory.glob(f"*/{name}"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} in {directory}; found {len(matches)}")
    return matches[0]


def main() -> None:
    args = parse_args()
    try:
        import optuna
    except ImportError as error:
        raise SystemExit("Install Optuna in the active venv: python -m pip install optuna") from error

    config_path = args.config.expanduser().resolve()
    base = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    rollout = int(base["ppo"]["n_steps"])
    if args.timesteps < rollout:
        raise SystemExit(f"--timesteps must be at least one PPO rollout ({rollout})")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    # A resumed study must still describe the same experiment.
    contract = {
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "timesteps": args.timesteps,
        "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed,
        "device": args.device,
    }
    study = optuna.create_study(
        study_name="rocky_ppo", direction="maximize",
        storage=f"sqlite:///{(output / 'study.db').as_posix()}", load_if_exists=True,
    )
    if study.user_attrs.get("contract") not in (None, contract):
        raise SystemExit("Study settings changed; use a new --output directory")
    study.set_user_attr("contract", contract)

    def objective(trial: optuna.Trial) -> float:
        trial_dir = output / f"trial_{trial.number:04d}"
        trial_dir.mkdir(exist_ok=False)
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        ppo = config["ppo"]
        ppo["learning_rate"] = trial.suggest_float("learning_rate", 3e-5, 3e-4, log=True)
        ppo["n_epochs"] = trial.suggest_categorical("n_epochs", [3, 5, 10])
        ppo["batch_size"] = trial.suggest_categorical("batch_size", [128, 256, 512])
        ppo["ent_coef"] = trial.suggest_float("ent_coef", 1e-5, 1e-2, log=True)
        ppo["clip_range"] = trial.suggest_float("clip_range", 0.1, 0.3)
        trial_config = trial_dir / "trial.yaml"
        trial_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        train_dir = trial_dir / "train"
        eval_dir = trial_dir / "eval"
        trial.set_user_attr("directory", str(trial_dir))
        run_logged([
            "ros2", "run", "nino_rl", "train", "--device", args.device,
            "--config", str(trial_config), "--timesteps", str(args.timesteps),
            "--checkpoint-every", str(args.timesteps + 1), "--output", str(train_dir),
        ], trial_dir / "train.log")
        model = only_file(train_dir, "nino_ppo_final.zip")
        run_config = model.parent / "ppo.yaml"
        run_logged([
            "ros2", "run", "nino_rl", "evaluate", "--device", args.device,
            "--config", str(run_config), "--model", str(model),
            "--episodes", str(args.eval_episodes), "--seed", str(args.eval_seed),
            "--output", str(eval_dir),
        ], trial_dir / "evaluate.log")
        summary = json.loads(only_file(eval_dir, "summary.json").read_text(encoding="utf-8"))
        if not summary.get("complete"):
            raise RuntimeError(f"Incomplete evaluation in {eval_dir}")
        success = float(summary["success_rate"])
        progress = float(summary["metrics_all_episodes"]["final_progress_fraction"]["mean"])
        rmse = float(summary["metrics_all_episodes"]["truth_path_rmse_m"]["mean"])
        trial.set_user_attr("success_rate", success)
        trial.set_user_attr("final_progress_fraction", progress)
        trial.set_user_attr("truth_path_rmse_m", rmse)
        trial.set_user_attr("model", str(model))
        print(f"Trial {trial.number}: success={success:.3f}, progress={progress:.3f}, "
              f"truth RMSE={rmse:.3f} m", flush=True)
        # Give success rate most of the weight; progress and tracking error
        # help order trials with similar success rates.
        return 100.0 * success + progress - 0.1 * rmse

    try:
        study.optimize(objective, n_trials=args.trials, n_jobs=1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Trial command failed ({error.returncode}); inspect the trial log in {output}") from error
    best = study.best_trial
    print(f"Best trial: {best.number}; score={best.value:.3f}; model={best.user_attrs['model']}")
    print(f"Parameters: {best.params}")
    print("Evaluate the selected model on fresh seeds before reporting performance.")


if __name__ == "__main__":
    main()
