#!/usr/bin/env python3
"""Repeat the frozen scale-only pilot with a new training seed and paired PI."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
ORIGINAL = ROOT / "rl_runs/flat_value_scaled_pilot_v1"
STEPS = 20480
SEEDS = list(range(64000, 64024))


def read(path):
    return json.loads(Path(path).read_text())


def process_identity(pid):
    try:
        proc = Path("/proc") / str(pid)
        command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
        start = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
        return command, start
    except (OSError, IndexError):
        return None


def repeat_config(original, seed):
    config = deepcopy(original)
    if seed < 0 or seed == int(config["seed"]):
        raise ValueError("Repeat requires a different nonnegative training seed")
    config.pop("reward_alignment_experiment", None)
    config["seed"] = seed
    return config


def trace_snapshot(code):
    before = '                "sim_time_s": ended_sim, "elapsed_s": elapsed,\n'
    if code.count(before) != 1:
        raise ValueError("Frozen trace insertion point changed")
    return code.replace(before, before +
        '                "slip_left": slip_left, "slip_right": slip_right,\n'
        '                "imu_square_integral": imu["square_integral"],\n')


def verify(plan):
    import yaml
    from nino_rl.tuning_trials import digest, assert_trial_inputs
    for group in (plan["original_assets"], plan["snapshot_assets"], plan["workflow_assets"]):
        for path, expected in group.items():
            if digest(path) != expected:
                raise ValueError(f"Frozen repeat input changed: {path}")
    if digest(plan["source_actor"]) != plan["source_actor_sha256"]:
        raise ValueError("Starting actor changed")
    output = Path(next(iter(plan["snapshot_assets"]))).parents[2]
    for filename, key in (("pilot.yaml", "training_config"), ("evaluation.yaml", "evaluation_config")):
        if yaml.safe_load((output / filename).read_text()) != plan[key]:
            raise ValueError(f"Prepared configuration changed: {filename}")
    assert_trial_inputs(plan["source_trial_contract"])


def prepare(output, seed):
    import yaml
    from nino_rl.tuning_trials import digest, assert_trial_inputs
    from nino_rl.evaluation import benchmark_id, prepare_evaluation_config
    old_plan = read(ORIGINAL / "pilot_plan.json")
    old_exp = old_plan["experiment"]
    if old_exp["training_steps"] != STEPS or old_exp["training_reward_scale"] != 0.01:
        raise ValueError("Expected original frozen 20,480-step scale-only profile")
    for path, expected in old_exp["snapshot_assets"].items():
        if digest(path) != expected:
            raise ValueError(f"Original snapshot changed: {path}")
    study = read(ROOT / "rl_runs/flat_focused_optuna_v1/trial_plan.json")["trials"]
    assert_trial_inputs(study)
    if study["sha256"] != old_plan["source_trial_contract"]:
        raise ValueError("Original study inputs changed")
    original_config = yaml.safe_load((ORIGINAL / "pilot.yaml").read_text())
    config = repeat_config(original_config, seed)
    evaluation = yaml.safe_load((ORIGINAL / "evaluation.yaml").read_text())
    if benchmark_id(prepare_evaluation_config(evaluation, control_trace=True)) != old_plan["evaluation_objective"]["benchmark_id"]:
        raise ValueError("Trace logging changed the physical benchmark")
    expected = deepcopy(original_config)
    expected.pop("reward_alignment_experiment", None)
    expected["seed"] = seed
    if config != expected or config["reward_v2"].get("impact_mode") is not None:
        raise ValueError("Only the training seed may change")
    output.mkdir(parents=True, exist_ok=True)
    overlay = output / "python"
    if not overlay.exists():
        temporary = output / "python.preparing"
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(ORIGINAL / "python", temporary, ignore=shutil.ignore_patterns("__pycache__"))
        path = temporary / "nino_rl/ros_env.py"
        path.write_text(trace_snapshot(path.read_text()))
        for path in (temporary / "nino_rl").glob("*.py"):
            compile(path.read_text(), str(path), "exec")
        temporary.rename(overlay)
    for path in (overlay / "nino_rl").glob("*.py"):
        original = ORIGINAL / "python/nino_rl" / path.name
        expected_bytes = (trace_snapshot(original.read_text()).encode() if path.name == "ros_env.py"
                          else original.read_bytes())
        if path.read_bytes() != expected_bytes:
            raise ValueError(f"Repeat differs beyond trace logging: {path.name}")
    workflow_paths = [Path(__file__), Path(__file__).with_name("train_rough_curriculum.py"),
                      Path(__file__).with_name("wait_for_drive_profile.py")]
    original_paths = [ORIGINAL / name for name in ("pilot_plan.json", "pilot.yaml", "evaluation.yaml", "comparison.json")]
    plan = dict(revision="flat_scale_seed_repeat_v1", original_run=str(ORIGINAL),
        source_actor=old_exp["source_actor"], source_actor_sha256=old_exp["source_actor_sha256"],
        original_training_seed=int(original_config["seed"]), training_seed=seed,
        actor="full original actor copied", critic="fresh", optimizer="fresh", training_counter=0,
        training_steps=STEPS, evaluation_seeds=SEEDS, training_reward_scale=0.01,
        source_trial_contract=study, evaluation_objective=old_plan["evaluation_objective"],
        promotion_gates=old_plan["promotion_gates"],
        original_assets={str(p): digest(p) for p in original_paths},
        snapshot_assets={str(p): digest(p) for p in sorted((overlay / "nino_rl").glob("*.py"))},
        workflow_assets={str(p): digest(p) for p in workflow_paths},
        trace_change="Only adds end-of-action left/right slip and IMU square integral to optional control trace",
        training_config=config, evaluation_config=evaluation)
    path = output / "repeat_plan.json"
    if path.exists() and read(path) != plan:
        raise ValueError("Repeat plan changed; preserve this run and use a new output directory")
    path.write_text(json.dumps(plan, indent=2) + "\n")
    for name, settings in (("pilot.yaml", config), ("evaluation.yaml", evaluation)):
        path = output / name
        content = yaml.safe_dump(settings, sort_keys=False)
        if path.exists() and path.read_text() != content:
            raise ValueError(f"Prepared repeat configuration changed: {path}")
        path.write_text(content)
    verify(plan)
    return plan


def promotion_gates(comparison, plan):
    metrics = comparison["comparison"]["metrics"]
    limits = plan["promotion_gates"]
    ratio = lambda name: metrics[name]["candidate"] / metrics[name]["baseline"]
    vibration, slip = ratio("rms_vertical_acceleration_m_s2"), ratio("rms_wheel_slip")
    quality = ((vibration <= limits["comfort_or_slip_ratio_max"] and slip <= limits["other_metric_ratio_max"])
               or (slip <= limits["comfort_or_slip_ratio_max"] and vibration <= limits["other_metric_ratio_max"]))
    return dict(physical_arrival=comparison["ppo"]["report"]["success_rate"] == 1.,
        completion=metrics["time_seconds"]["candidate"] <= limits["mean_completion_seconds"],
        tracking=ratio("truth_path_rmse_m") <= limits["physical_rmse_ratio_max"],
        quality=quality, vibration_ratio=vibration, slip_ratio=slip)


def run(output, plan, save):
    from nino_rl.tuning_trials import assert_trial_inputs, digest
    from nino_rl.tuning_objective import read_episode_rows, score_episodes
    from nino_rl.evaluation import compare_summaries
    from train_rough_curriculum import Processes, assert_isolated, complete_evaluation, checkpoint_steps
    os.environ.update(ROS_DOMAIN_ID="79", NINO_ROS_DOMAIN_ID="79", GZ_PARTITION="nino_flat_79",
                      ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(output / "python") + os.pathsep + str(ROOT / "src/nino_rl") + os.pathsep + env.get("PYTHONPATH", "")
    assert_isolated(79, "nino_flat_79")
    processes = Processes(env, pi_integrator_profile="conditional_v1")

    def launch(directory, config):
        verify(plan)
        processes.world = processes.start(["ros2", "launch", "nino_rl", "training_sim.launch.py",
            f"world:={plan['source_trial_contract']['world']}", "world_name:=combined_flat_section", "headless:=true",
            "pi_integrator_profile:=conditional_v1"], directory / "gazebo.log")
        processes.run(["ros2", "run", "nino_rl", "wait_for_sim"], directory / "readiness.log", timeout=90)
        assert_trial_inputs(plan["source_trial_contract"], live=True)
        processes.run([sys.executable, "src/nino_rl/scripts/wait_for_drive_profile.py", "--config", config,
                       "--timeout", 60], directory / "profile.log", timeout=65)

    try:
        models = list((output / "train").glob("*/nino_ppo_final.zip"))
        if len(models) > 1:
            raise ValueError("Ambiguous repeat model")
        if not models:
            if list((output / "train").glob("*/nino_ppo_interrupted.zip")):
                raise ValueError("Interrupted repeat preserved; review before any optimizer resume")
            save("training")
            launch(output / "train", output / "pilot.yaml")
            processes.run(["ros2", "run", "nino_rl", "train", "--config", output / "pilot.yaml", "--device", "cuda",
                "--init-model", plan["source_actor"], "--timesteps", STEPS, "--checkpoint-every", 10240,
                "--preflight-timeout", 60, "--output", output / "train"], output / "train/training.log")
            processes.close()
            models = list((output / "train").glob("*/nino_ppo_final.zip"))
        if len(models) != 1 or checkpoint_steps(models[0]) != STEPS:
            raise ValueError("Repeat did not complete exactly 20,480 steps")
        transfer = read(models[0].with_name("actor_transfer.json"))
        if transfer["source_sha256"] != plan["source_actor_sha256"] or any(
            transfer[key] != plan[key] for key in ("critic", "optimizer", "training_counter")):
            raise ValueError("Live transfer differs from actor-only initialization plan")
        import yaml
        live_config = yaml.safe_load(models[0].with_name("ppo.yaml").read_text())
        if live_config != plan["training_config"]:
            raise ValueError("Actual training configuration differs from the frozen new-seed plan")
        result = {}
        for label in ("ppo", "pi"):
            save("evaluating_" + label)
            directory = output / label
            cached = complete_evaluation(directory, 24)
            if cached is None:
                launch(directory, output / "evaluation.yaml")
                command = ["ros2", "run", "nino_rl", "evaluate_baseline" if label == "pi" else "evaluate",
                    "--config", output / "evaluation.yaml", "--seeds", *SEEDS, "--control-trace", "--output", directory]
                command += ["--baseline-speed-scale", 1.] if label == "pi" else ["--model", models[0], "--device", "cuda"]
                processes.run(command, directory / "evaluation.log")
                processes.close()
                cached = complete_evaluation(directory, 24)
            if cached is None or cached[1]["evaluation_seeds"] != SEEDS or not cached[1].get("control_trace"):
                raise ValueError("Incomplete or incompatible traced evaluation")
            if cached[1]["benchmark_id"] != plan["evaluation_objective"]["benchmark_id"]:
                raise ValueError("Evaluation physical benchmark changed")
            paths = [p for p in directory.glob("*/summary.json") if read(p) == cached[1]]
            if len(paths) != 1:
                raise ValueError("Ambiguous evaluation evidence")
            for episode in range(1, 25):
                for name in ("control_trace.csv", "drive_trace.csv"):
                    if not (paths[0].parent / f"episode-{episode:03d}" / name).is_file():
                        raise ValueError("Missing per-action comparison trace")
            result[label] = dict(summary=str(paths[0]), report=cached[1],
                objective=score_episodes(read_episode_rows(paths[0].with_name("episodes.csv")), plan["evaluation_objective"]))
        result["comparison"] = compare_summaries(result["pi"]["report"], result["ppo"]["report"])
        result["gates"] = promotion_gates(result, plan)
        result["promote"] = all(result["gates"][key] for key in ("physical_arrival", "completion", "tracking", "quality"))
        result["training_seed"] = plan["training_seed"]
        result["model_sha256"] = digest(models[0])
        result["original_seed_comparison"] = str(ORIGINAL / "comparison.json")
        result["both_training_seeds_qualified"] = bool(read(ORIGINAL / "comparison.json")["promote"] and result["promote"])
        (output / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        lines = ["# Flat scale-only independent-seed repeat", "",
                 f"Training seed {plan['training_seed']}; original seed {plan['original_training_seed']}. "
                 "Same starting actor, fresh critic/optimizer, exactly 20,480 steps.", "",
                 "| Metric | Repeat PPO | Matching PI |", "|---|---:|---:|"]
        for name in ("time_seconds", "truth_path_rmse_m", "rms_vertical_acceleration_m_s2", "rms_wheel_slip"):
            vals = [result[label]["report"]["metrics_all_episodes"][name]["mean"] for label in ("ppo", "pi")]
            lines.append(f"| {name} | {vals[0]:.6f} | {vals[1]:.6f} |")
        lines += ["", f"Physical arrivals: PPO {round(result['ppo']['report']['success_rate'] * 24)}/24; "
                  f"PI {round(result['pi']['report']['success_rate'] * 24)}/24.", "",
                  f"Original gates: `{json.dumps(result['gates'])}`. Qualifies: **{result['promote']}**.", "",
                  f"Both training seeds qualify: **{result['both_training_seeds_qualified']}**. "
                  "The original run failed its quality gate; a passing repeat alone cannot establish consistent qualification.", "",
                  "Two training seeds can expose repeatability problems; they do not establish broad generalization. "
                  "Saved control and drive traces support action-window slip inspection. No Optuna or longer training "
                  "is started automatically.", ""]
        (output / "REPORT.md").write_text("\n".join(lines))
        save("complete", report=str(output / "REPORT.md"), gates=result["gates"])
    finally:
        processes.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-seed", type=int, default=43)
    parser.add_argument("--output", type=Path, default=ROOT / "rl_runs/flat_value_scaled_seed43_v1")
    parser.add_argument("--wait-for-rough-pid", type=int)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT / "src/nino_rl"), str(Path(__file__).parent)]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = prepare(output, args.training_seed)
        state = dict(pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat(), training_seed=args.training_seed)

        def save(stage, **extra):
            state.update(stage=stage, updated_utc=datetime.now(timezone.utc).isoformat(), **extra)
            temporary = output / "status.tmp"
            temporary.write_text(json.dumps(state, indent=2) + "\n")
            temporary.replace(output / "status.json")
            print(stage, flush=True)

        if not args.run:
            print("Prepared only; no simulation started:", output / "repeat_plan.json")
            return
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            identity = process_identity(args.wait_for_rough_pid) if args.wait_for_rough_pid else None
            if identity and "run_rough_trial8_validation.py" not in identity[0]:
                raise ValueError("Refusing to wait for an unrelated process")
            if identity:
                save("waiting_for_rough", waited_pid=args.wait_for_rough_pid)
                while process_identity(args.wait_for_rough_pid) == identity:
                    time.sleep(2)
            verify(plan)
            run(output, plan, save)
        except KeyboardInterrupt:
            save("cancelled")
            raise
        except Exception as error:
            save("failed", error=str(error))
            raise


if __name__ == "__main__":
    main()
