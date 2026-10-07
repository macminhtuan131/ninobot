#!/usr/bin/env python3
"""Tune one rough or flat section against its own running Gazebo world."""

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
    "rough": {
        "progress_weight": (7.0, 15.0), "lateral_weight": (0.3, 0.8),
        "impact_weight": (0.02, 0.12), "attitude_weight": (0.3, 0.9),
        "slip_weight": (0.05, 0.25),
    },
    "flat": {
        "progress_weight": (7.0, 15.0), "lateral_weight": (0.3, 0.8),
        "heading_weight": (0.15, 0.5), "slip_weight": (0.05, 0.25),
        "goal_braking_weight": (0.08, 0.3),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=("rough", "flat"), required=True)
    parser.add_argument("--config", type=Path, help="Override the section's base YAML")
    parser.add_argument("--output", type=Path, help="Separate persistent study directory")
    parser.add_argument("--init-model", type=Path, default=DEFAULT_MODEL,
                        help="Old actor checkpoint; omitted with --from-scratch")
    parser.add_argument("--from-scratch", action="store_true",
                        help="Use a new actor with the fixed section policy architecture")
    parser.add_argument("--trials", type=int, default=12)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--eval-episodes", type=int, default=12)
    parser.add_argument("--eval-seed", type=int, default=20_000)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--randomized-eval", action="store_true",
                        help="Evaluate with residual-channel and observation perturbations")
    args = parser.parse_args()
    if args.trials < 1 or args.timesteps < 1 or args.eval_episodes < 1:
        parser.error("--trials, --timesteps and --eval-episodes must be positive")
    return args


def sample_config(trial, base: dict, *, section: str) -> dict:
    """Keep task geometry and safety thresholds fixed while tuning learning."""
    config = deepcopy(base)
    ppo = config["ppo"]
    reward = config["reward_v2"]
    for name, (low, high) in REWARD_WEIGHTS[section].items():
        reward[name] = trial.suggest_float(f"reward_v2.{name}", low, high)
    # Keep endpoint success criteria and architecture fixed, so a small study
    # can compare policies on the same physical task and old actor can transfer.
    ppo["learning_rate"] = trial.suggest_float("learning_rate", 1e-5, 7e-5, log=True)
    ppo["gamma"] = trial.suggest_categorical("gamma", [0.995, 0.997, 0.999])
    ppo["n_steps"] = trial.suggest_categorical("n_steps", [1024, 2048])
    ppo["ent_coef"] = trial.suggest_float("ent_coef", 1e-4, 3e-3, log=True)
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


def full_curriculum_config(tuned_config: dict) -> dict:
    """Carry selected PPO/reward settings into an unlocked flat curriculum."""
    config = deepcopy(tuned_config)
    flat = config.get("flat_curriculum", {})
    if not flat.get("enabled", False) or "fixed_stage" not in flat:
        raise ValueError("Flat curriculum Optuna config must fix one tuning stage")
    flat.pop("fixed_stage")
    flat["evaluation_stage"] = len(flat["stages"]) - 1
    return config


def main() -> None:
    args = parse_args()
    try:
        import optuna
    except ImportError as error:
        raise SystemExit("Install Optuna: python -m pip install optuna") from error
    config_path = (args.config or ROOT / f"src/nino_rl/config/combined_{args.section}_section.yaml").expanduser().resolve()
    base = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    world_name = f"combined_{args.section}_section"
    if base.get("task") != world_name or base.get("world_name") != world_name:
        raise SystemExit(f"This tuner requires task and world_name = {world_name}")
    if args.timesteps < 2048:
        raise SystemExit("Use at least 2048 steps so every trial has a PPO update")
    model_path = None if args.from_scratch else args.init_model.expanduser().resolve()
    if model_path is not None and not model_path.is_file():
        raise SystemExit(f"Missing actor checkpoint: {model_path}")
    output = (args.output or ROOT / f"rl_runs/combined_{args.section}_optuna").expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    mesh_path = ROOT / "src/nino_description/terrains/combined_rough_ground.stl"
    world_path = ROOT / f"src/nino_description/worlds/{world_name}.sdf"
    if not world_path.is_file() or (args.section == "rough" and not mesh_path.is_file()):
        raise SystemExit("Generate the split worlds before tuning")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    contract = {
        "config_sha256": digest(config_path), "world_sha256": digest(world_path),
        "mesh_sha256": digest(mesh_path) if args.section == "rough" else None,
        "tuner_sha256": digest(Path(__file__)),
        "init_model_sha256": digest(model_path) if model_path else None,
        "timesteps": args.timesteps, "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed, "device": args.device,
        "from_scratch": args.from_scratch, "randomized_eval": args.randomized_eval,
    }
    study = optuna.create_study(
        study_name=world_name, direction="maximize",
        storage=f"sqlite:///{(output / 'study.db').as_posix()}", load_if_exists=True,
    )
    if study.user_attrs.get("contract") not in (None, contract):
        raise SystemExit("Study inputs changed; choose a new --output directory")
    study.set_user_attr("contract", contract)

    def objective(trial) -> float:
        trial_dir = output / f"trial_{trial.number:04d}"
        trial_dir.mkdir(exist_ok=False)
        config = sample_config(trial, base, section=args.section)
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
        evaluate_command = ["ros2", "run", "nino_rl", "evaluate", "--device", args.device,
                    "--config", str(model.parent / "ppo.yaml"), "--model", str(model),
                    "--episodes", str(args.eval_episodes), "--seed", str(args.eval_seed),
                    "--output", str(eval_dir)]
        if args.randomized_eval:
            evaluate_command.append("--randomized")
        run_logged(evaluate_command, trial_dir / "evaluate.log")
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
    best_config = yaml.safe_load(source.read_text(encoding="utf-8"))
    (output / "best_trial.yaml").write_text(
        yaml.safe_dump(best_config, sort_keys=False), encoding="utf-8"
    )
    (output / "best_model.txt").write_text(best.user_attrs["model"] + "\n", encoding="utf-8")
    flat_curriculum = best_config.get("flat_curriculum", {})
    if flat_curriculum.get("enabled", False):
        (output / "best_curriculum.yaml").write_text(
            yaml.safe_dump(full_curriculum_config(best_config), sort_keys=False), encoding="utf-8"
        )
        print(f"Full curriculum config: {output / 'best_curriculum.yaml'}")
    print(f"Best trial: {best.number}, score={best.value:.3f}, model={best.user_attrs['model']}")
    print(f"Best config: {output / 'best_trial.yaml'}")
    print("Validate with new evaluation seeds before a long training run.")


if __name__ == "__main__":
    main()
