#!/usr/bin/env python3
"""Tune one rough or flat section against its own running Gazebo world."""

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
    initialization = parser.add_mutually_exclusive_group()
    initialization.add_argument("--init-model", type=Path, default=DEFAULT_MODEL,
                        help="Old actor checkpoint; omitted with --from-scratch")
    initialization.add_argument("--from-scratch", action="store_true",
                        help="Use a new actor with the fixed section policy architecture")
    parser.add_argument("--trials", type=int, default=12)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--eval-episodes", type=int, default=12)
    parser.add_argument("--eval-seed", type=int, default=20_000)
    parser.add_argument("--objective-config", type=Path,
                        default=ROOT / 'src/nino_rl/config/optuna_objective.yaml',
                        help="Fixed evaluation thresholds/weights; changing these requires a new study")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--randomized-eval", action="store_true",
                        help="Evaluate with residual-channel and observation perturbations")
    add_comparable_arguments(parser)
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


def main() -> None:
    args = parse_args()
    try:
        import optuna
    except ImportError as error:
        raise SystemExit("Install Optuna: python -m pip install optuna") from error
    config_path = (args.config or ROOT / f"src/nino_rl/config/combined_{args.section}_section.yaml").expanduser().resolve()
    base = load_config(config_path)
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
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    fixed_objective = make_objective_contract(base, args.objective_config,
        course=args.section, episodes=args.eval_episodes, seed=args.eval_seed, randomized=args.randomized_eval)
    comparable = make_trial_contract(ROOT, base, world_path=args.world, model_path=model_path,
        rollouts=[1024, 2048], requested_steps=args.timesteps, device=args.device, tuner_path=Path(__file__))
    sampler = lambda trial: sample_config(trial, base, section=args.section)
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
        "from_scratch": args.from_scratch, "randomized_eval": args.randomized_eval,
    }
    write_trial_plan(output, comparable, fixed_objective)
    saved_results = write_saved_results_plan(output, candidate,
        [pi_reference(path, fixed_objective) for path in args.pi_reference], args.history_study)
    if args.prepare_only:
        return
    if not args.prepare_study:
        assert_trial_inputs(comparable, live=True)
    study = optuna.create_study(
        study_name=world_name, direction="maximize",
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
        evaluate_command = ["ros2", "run", "nino_rl", "evaluate", "--device", args.device,
                    "--config", str(model.parent / "ppo.yaml"), "--model", str(model),
                    "--episodes", str(args.eval_episodes), "--seed", str(args.eval_seed),
                    "--output", str(eval_dir)]
        if args.randomized_eval:
            evaluate_command.append("--randomized")
        run_logged(evaluate_command, trial_dir / "evaluate.log")
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
