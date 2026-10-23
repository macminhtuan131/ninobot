#!/usr/bin/env python3
"""Tune Rocky Hall PPO against one already running Gazebo world.

Run from the repository root in a shell with ROS, the venv, and install/setup.bash
sourced. Each Optuna trial trains and evaluates sequentially.
"""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("src/nino_rl/config/rocky_tracking.yaml"))
    parser.add_argument("--output", type=Path, default=Path("rl_runs/rocky_optuna"))
    parser.add_argument("--trials", type=int, default=12, help="Additional trials to run")
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--eval-episodes", type=int, default=10)
    parser.add_argument("--eval-seed", type=int, default=10_000)
    parser.add_argument("--objective-config", type=Path,
                        default=ROOT / 'src/nino_rl/config/optuna_objective.yaml',
                        help="Fixed evaluation thresholds/weights; changing these requires a new study")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    add_comparable_arguments(parser)
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


def sample_config(trial, base):
    config = deepcopy(base)
    ppo = config['ppo']
    ppo['learning_rate'] = trial.suggest_float('learning_rate', 3e-5, 3e-4, log=True)
    ppo['n_epochs'] = trial.suggest_categorical('n_epochs', [3, 5, 10])
    ppo['batch_size'] = trial.suggest_categorical('batch_size', [128, 256, 512])
    ppo['ent_coef'] = trial.suggest_float('ent_coef', 1e-5, 1e-2, log=True)
    ppo['clip_range'] = trial.suggest_float('clip_range', 0.1, 0.3)
    return config


def main() -> None:
    args = parse_args()
    try:
        import optuna
    except ImportError as error:
        raise SystemExit("Install Optuna in the active venv: python -m pip install optuna") from error

    config_path = args.config.expanduser().resolve()
    base = load_config(config_path)
    rollout = int(base["ppo"]["n_steps"])
    if args.timesteps < rollout:
        raise SystemExit(f"--timesteps must be at least one PPO rollout ({rollout})")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    # A resumed study must still describe the same experiment.
    fixed_objective = make_objective_contract(base, args.objective_config,
        course='rocky', episodes=args.eval_episodes, seed=args.eval_seed)
    comparable = make_trial_contract(ROOT, base, world_path=args.world, model_path=None,
        rollouts=[rollout], requested_steps=args.timesteps, device=args.device, tuner_path=Path(__file__))
    sampler = lambda trial: sample_config(trial, base)
    candidate = current_candidate(base, sampler)
    contract = {
        "comparable_trials": comparable,
        "evaluation_objective_sha256": fixed_objective['sha256'],
        "resolved_config_sha256": hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "timesteps": args.timesteps,
        "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed,
        "device": args.device,
    }
    write_trial_plan(output, comparable, fixed_objective)
    saved_results = write_saved_results_plan(output, candidate,
        [pi_reference(path, fixed_objective) for path in args.pi_reference], args.history_study)
    if args.prepare_only:
        return
    if not args.prepare_study:
        assert_trial_inputs(comparable, live=True)
    study = optuna.create_study(
        study_name="rocky_ppo", direction="maximize",
        storage=f"sqlite:///{(output / 'study.db').as_posix()}", load_if_exists=True,
    )
    if study.user_attrs.get("contract") not in (None, contract):
        raise SystemExit("Study settings changed; use a new --output directory")
    bind_study_objective(study, fixed_objective, output)
    study.set_user_attr("contract", contract)
    study.set_user_attr("pi_references", saved_results['pi_references'])
    apply_saved_results(study, output, comparable, fixed_objective, candidate, args.history_study, sampler)
    if args.prepare_study:
        return

    def objective(trial: optuna.Trial) -> float:
        assert_trial_inputs(comparable, live=True)
        trial_dir = output / f"trial_{trial.number:04d}"
        trial_dir.mkdir(exist_ok=False)
        config = sampler(trial)
        validate_trial_config(config, comparable)
        trial_config = trial_dir / "trial.yaml"
        trial_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        train_dir = trial_dir / "train"
        eval_dir = trial_dir / "eval"
        trial.set_user_attr("directory", str(trial_dir))
        run_logged(train_command(comparable, trial_config, train_dir), trial_dir / "train.log")
        model = only_file(train_dir, "nino_ppo_final.zip")
        trial.set_user_attr("comparable_training", verify_training_result(model, config, comparable))
        assert_trial_inputs(comparable, live=True)
        run_config = model.parent / "ppo.yaml"
        run_logged([
            "ros2", "run", "nino_rl", "evaluate", "--device", args.device,
            "--config", str(run_config), "--model", str(model),
            "--episodes", str(args.eval_episodes), "--seed", str(args.eval_seed),
            "--output", str(eval_dir),
        ], trial_dir / "evaluate.log")
        assert_trial_inputs(comparable, live=True)
        trial.set_user_attr("model", str(model))
        return record_trial_objective(trial, only_file(eval_dir, "summary.json"), fixed_objective)

    try:
        study.optimize(objective, n_trials=args.trials, n_jobs=1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Trial command failed ({error.returncode}); inspect the trial log in {output}") from error
    best = qualified_best_trial(study, output)
    if best is None:
        return
    print(f"Best trial: {best.number}; score={best.value:.3f}; model={best.user_attrs['model']}")
    print(f"Parameters: {best.params}")
    print("Evaluate the selected model on fresh seeds before reporting performance.")


if __name__ == "__main__":
    main()
