#!/usr/bin/env python3
"""Tune the combined course against one running Gazebo instance, sequentially."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/nino_rl'))
from nino_rl.core import load_config
from nino_rl.tuning_objective import (make_objective_contract, bind_study_objective,
                                      record_trial_objective, qualified_best_trial)
from nino_rl.tuning_trials import (add_comparable_arguments, make_trial_contract,
    write_trial_plan, assert_trial_inputs, validate_trial_config, train_command,
    verify_training_result)
from nino_rl.tuning_history import (current_candidate, pi_reference,
    write_saved_results_plan, apply_saved_results)
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
    initialization = parser.add_mutually_exclusive_group()
    initialization.add_argument("--init-model", type=Path, default=DEFAULT_MODEL,
                        help="Old actor checkpoint; omitted with --from-scratch")
    initialization.add_argument("--from-scratch", action="store_true",
                        help="Tune policy architecture and initialization without actor transfer")
    parser.add_argument("--trials", type=int, default=12)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--eval-episodes", type=int, default=12)
    parser.add_argument("--eval-seed", type=int, default=20_000)
    parser.add_argument("--objective-config", type=Path,
                        default=ROOT / 'src/nino_rl/config/optuna_objective.yaml',
                        help="Fixed evaluation thresholds/weights; changing these requires a new study")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    add_comparable_arguments(parser)
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
    base = load_config(config_path)
    if base.get("task") != "combined_course":
        raise SystemExit("This tuner requires a combined_course config")
    if args.timesteps < 2048:
        raise SystemExit("Use at least 2048 steps so every trial has a PPO update")
    model_path = None if args.from_scratch else args.init_model.expanduser().resolve()
    if model_path is not None and not model_path.is_file():
        raise SystemExit(f"Missing actor checkpoint: {model_path}")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    fixed_objective = make_objective_contract(base, args.objective_config,
        course='combined', episodes=args.eval_episodes, seed=args.eval_seed, randomized=True)
    comparable = make_trial_contract(ROOT, base, world_path=args.world, model_path=model_path,
        rollouts=[1024, 2048], requested_steps=args.timesteps, device=args.device, tuner_path=Path(__file__))
    sampler = lambda trial: sample_config(trial, base, from_scratch=args.from_scratch)
    candidate = current_candidate(base, sampler)
    contract = {
        "comparable_trials": comparable,
        "evaluation_objective_sha256": fixed_objective['sha256'],
        "resolved_config_sha256": hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest(),
        "config_sha256": digest(config_path),
        "tuner_sha256": digest(Path(__file__)),
        "init_model_sha256": digest(model_path) if model_path else None,
        "timesteps": args.timesteps, "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed, "device": args.device,
        "from_scratch": args.from_scratch,
    }
    write_trial_plan(output, comparable, fixed_objective)
    saved_results = write_saved_results_plan(output, candidate,
        [pi_reference(path, fixed_objective) for path in args.pi_reference], args.history_study)
    if args.prepare_only:
        return
    if not args.prepare_study:
        assert_trial_inputs(comparable, live=True)
    study = optuna.create_study(
        study_name="combined_course", direction="maximize",
        storage=f"sqlite:///{(output / 'study.db').as_posix()}", load_if_exists=True,
    )
    if study.user_attrs.get("contract") not in (None, contract):
        raise SystemExit("Study inputs changed; choose a new --output directory")
    bind_study_objective(study, fixed_objective, output)
    study.set_user_attr("contract", contract)
    study.set_user_attr("pi_references", saved_results['pi_references'])
    apply_saved_results(study, output, comparable, fixed_objective, candidate, args.history_study, sampler)
    if args.prepare_study:
        return

    def objective(trial) -> float:
        assert_trial_inputs(comparable, live=True)
        trial_dir = output / f"trial_{trial.number:04d}"
        trial_dir.mkdir(exist_ok=False)
        config = sampler(trial)
        validate_trial_config(config, comparable)
        trial_config = trial_dir / "trial.yaml"
        trial_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        train_dir, eval_dir = trial_dir / "train", trial_dir / "eval"
        trial.set_user_attr("directory", str(trial_dir))
        command = train_command(comparable, trial_config, train_dir)
        run_logged(command, trial_dir / "train.log")
        model = only_file(train_dir, "nino_ppo_final.zip")
        trial.set_user_attr("comparable_training", verify_training_result(model, config, comparable))
        assert_trial_inputs(comparable, live=True)
        run_logged(["ros2", "run", "nino_rl", "evaluate", "--device", args.device,
                    "--config", str(model.parent / "ppo.yaml"), "--model", str(model),
                    "--episodes", str(args.eval_episodes), "--seed", str(args.eval_seed),
                    "--randomized", "--output", str(eval_dir)], trial_dir / "evaluate.log")
        assert_trial_inputs(comparable, live=True)
        trial.set_user_attr("model", str(model))
        return record_trial_objective(trial, only_file(eval_dir, "summary.json"), fixed_objective)

    try:
        study.optimize(objective, n_trials=args.trials, n_jobs=1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Trial failed ({error.returncode}); inspect logs in {output}") from error
    best = qualified_best_trial(study, output)
    if best is None:
        return
    source = Path(best.user_attrs["directory"]) / "trial.yaml"
    (output / "best_trial.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Best trial: {best.number}, score={best.value:.3f}, model={best.user_attrs['model']}")
    print(f"Best config: {output / 'best_trial.yaml'}")
    print("Validate with new evaluation seeds before a long training run.")


if __name__ == "__main__":
    main()
