"""Train a PPO motor or PI-reference policy against the running Gazebo world."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import yaml

from ament_index_python.packages import get_package_share_directory
import numpy as np

from nino_rl.core import load_config
from nino_rl.control_v2 import validate_model, validate_action_mode, action_size
from nino_rl.training_contract import training_contract, validate_resume


def arguments() -> argparse.Namespace:
    default_config = Path(get_package_share_directory("nino_rl")) / "config" / "ppo.yaml"
    parser = argparse.ArgumentParser(description="Train a Nino PPO control policy")
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--timesteps", type=int, default=600_000)
    parser.add_argument("--output", type=Path, default=Path("rl_runs"))
    checkpoint_group = parser.add_mutually_exclusive_group()
    checkpoint_group.add_argument("--resume", type=Path,
                                  help="Continue the same task, optimizer and step count")
    checkpoint_group.add_argument("--init-model", type=Path,
                                  help="Copy a compatible actor into a fresh task/run; critic stays fresh")
    checkpoint_group.add_argument("--init-speed-model", type=Path,
                                  help="Transfer two-/three-action features and speed into a new two-action policy; reset yaw, critic and optimizer")
    parser.add_argument("--checkpoint-every", type=int, default=25_000)
    parser.add_argument("--check-env", action="store_true")
    parser.add_argument("--phase", type=int, choices=range(1, 7),
                        help="Fixed hard-to-easy cable phase (1=hardest, 6=easiest)")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"))
    parser.add_argument("--route", help="Train one configured route ID; omit to sample all drawn routes")
    parser.add_argument("--preflight-timeout", type=float, default=30.0)
    return parser.parse_args(sys.argv[1:])


def main() -> None:
    args = arguments()
    if args.timesteps <= 0:
        raise SystemExit("--timesteps phải lớn hơn 0")
    try:
        import torch as th
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
        from stable_baselines3.common.env_checker import check_env
        from stable_baselines3.common.monitor import Monitor
        from nino_rl.policies import policy_spec
    except ImportError as error:
        raise SystemExit(
            "Thiếu thư viện RL. Kích hoạt .venv và chạy: "
            "pip install -r src/nino_rl/requirements.txt"
        ) from error

    config = load_config(args.config)
    if args.route is not None:
        if not config.get("routes", {}).get("enabled", False):
            raise SystemExit("--route requires an enabled routes configuration")
        config["routes"]["fixed_route"] = args.route
    from nino_rl.routes import RouteSet
    RouteSet(config)
    if args.phase is not None:
        config["curriculum"]["fixed_phase"] = args.phase
    if args.init_speed_model and config.get("action_mode") != "speed_yaw_reference":
        raise SystemExit("--init-speed-model requires action_mode: speed_yaw_reference")
    # auto means CUDA for this GPU training workflow; never silently fall back.
    device = args.device or str(config.get("device", "cuda"))
    if device == "auto":
        device = "cuda"
    if device.startswith("cuda") and not th.cuda.is_available():
        raise SystemExit(
            "Cấu hình yêu cầu CUDA nhưng torch.cuda.is_available() = False. "
            "Chạy `ros2 run nino_rl check_cuda` để chẩn đoán."
        )
    if device.startswith("cuda"):
        try:
            # Fail before starting ROS/Gazebo if the installed wheel and NVIDIA
            # driver cannot actually execute a CUDA kernel.
            probe = th.ones((32, 32), device=device)
            _ = probe @ probe
            th.cuda.synchronize()
        except (RuntimeError, AssertionError) as error:
            raise SystemExit(f"CUDA was detected but a CUDA operation failed: {error}") from error
        print(
            f"CUDA ready: {th.cuda.get_device_name(th.cuda.current_device())}",
            flush=True,
        )

    speed_source = None
    if args.init_speed_model:
        speed_source = PPO.load(args.init_speed_model, device=device)
        source_actions = speed_source.action_space.shape[0]
        if source_actions not in (2, 3):
            raise SystemExit('Speed initialization requires a two- or three-action checkpoint')
        validate_model(speed_source, 60 * config["policy_v2"]["history_frames"], source_actions)
        validate_action_mode(speed_source, {'action_mode': 'speed_yaw_reference' if source_actions == 2 else 'wheel_torque',
            'navigation': getattr(speed_source, 'nino_training_contract', {}).get('navigation', {})})

    from nino_rl.ros_env import NinoGazeboEnv
    from nino_rl.preflight import run_preflight

    print("Running mandatory 12-point straight-line RL preflight...", flush=True)
    try:
        preflight_results = run_preflight(config, args.preflight_timeout)
    except (RuntimeError, TimeoutError) as error:
        raise SystemExit(f"PREFLIGHT FAILED; training was not started: {error}") from error
    for result in preflight_results:
        print(f"PASS: {result}", flush=True)

    class TrainingMetricsCallback(BaseCallback):
        """Expose reward components and endpoint metrics in TensorBoard."""

        def __init__(self) -> None:
            super().__init__()
            self.reward_terms: dict[str, list[float]] = {}

        def _on_rollout_start(self) -> None:
            env.resume_callback_dispatch()
            self.reward_terms.clear()

        def _on_step(self) -> bool:
            actions = self.locals.get("actions")
            if actions is not None:
                self.logger.record_mean("policy/action_clip_fraction", float(np.mean(np.abs(actions) > 1.0)))
            for info in self.locals.get("infos", []):
                for name, value in info.get("reward_terms", {}).items():
                    self.reward_terms.setdefault(name, []).append(float(value))
                metrics = info.get("episode_metrics")
                if metrics is not None:
                    # Preserve each outcome instead of only rollout averages;
                    # this also survives an interrupted/incomplete PPO rollout.
                    with (run_dir / "episodes.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"training_step": self.num_timesteps,
                                                 **metrics}) + "\n")
                    for reason in ("timeout", "off_path", "collision", "rollover",
                                   "wrong_direction", "navigation_invalid", "goal_missed"):
                        self.logger.record_mean(
                            f"episode/{reason}_failure", float(metrics["termination"] == reason))
                    if metrics.get("route_id"):
                        route_id = metrics["route_id"]
                        for name in ("success", "truth_path_rmse_m", "time_seconds",
                                     "route_gates_passed", "route_gates_total"):
                            self.logger.record_mean(f"routes/{route_id}/{name}", float(metrics[name]))
                    if "rough_curriculum_stage" in metrics:
                        self.logger.record_mean("curriculum/rough_stage", metrics["rough_curriculum_stage"])
                        self.logger.record_mean("curriculum/terrain_level", metrics["terrain_randomization_level"])
                    for name, value in metrics["reward_totals"].items():
                        self.logger.record_mean(f"episode_reward/{name}", float(value))
                    for name in (
                        "return",
                        "clock_elapsed_seconds",
                        "max_clock_error_seconds",
                        "max_motion_sensor_lag_seconds",
                        "curriculum_phase",
                        "terrain_height_scale",
                        "success",
                        "finished_within_target_time",
                        "time_seconds",
                        "endpoint_distance_m",
                        "heading_error_deg",
                        "final_abs_lateral_drift_m",
                        "final_speed_m_s",
                        "mean_abs_lateral_error_m",
                        "rms_path_deviation_m",
                        "max_path_deviation_m",
                        "path_rmse_m",
                        "truth_path_rmse_m",
                        "truth_path_p95_m",
                        "truth_endpoint_error_m",
                        "truth_heading_rmse_deg",
                        "odom_truth_position_error_m",
                        "path_p95_m",
                        "heading_rmse_deg",
                        "final_progress_fraction",
                        "max_tilt_deg",
                        "rms_wheel_slip",
                        "rms_wheel_torque_nm",
                        "mean_imu_angular_xy_rad_s",
                        "peak_vertical_acceleration_m_s2",
                        "rms_vertical_acceleration_m_s2",
                        "adaptive_terrain_features",
                        "next_adaptive_terrain_features",
                        "adaptive_terrain_rolling_success",
                        "adaptive_terrain_window_episodes",
                        "adaptive_terrain_level_advanced",
                        "difficult_path_chosen",
                        "challenges_chosen",
                        "challenges_cleared",
                        "traversable_challenges",
                        "challenge_choice_fraction",
                        "challenge_clear_fraction",
                        "mean_speed_scale",
                        "min_speed_scale",
                        "max_speed_scale",
                        "mean_ground_speed_m_s",
                    ):
                        self.logger.record_mean(f"episode/{name}", float(metrics[name]))
                    if metrics.get("flat_curriculum_stage") is not None:
                        self.logger.record_mean(
                            "episode/flat_curriculum_stage", float(metrics["flat_curriculum_stage"])
                        )
                        self.logger.record_mean(
                            "episode/next_flat_curriculum_stage",
                            float(metrics["next_flat_curriculum_stage"]),
                        )
            return True

        def _on_rollout_end(self) -> None:
            labels = (("speed", "yaw_reference") if action_size(config) == 2
                      else ("speed", "common_torque", "steering"))
            for index, name in enumerate(labels):
                self.logger.record(f"policy/std_{name}", float(self.model.policy.log_std[index].detach().exp().cpu()))
            if config.get("action_mode") in ("yaw_reference", "speed_yaw_reference"):
                yaw_index = 1 if action_size(config) == 2 else 2
                self.logger.record("policy/std_yaw_reference_rad_s", float(
                    self.model.policy.log_std[yaw_index].detach().exp().cpu())
                    * float(config["navigation"]["max_policy_yaw_rate_rad_s"]))
            # Do not leave the policy driving during an arbitrarily long PPO update.
            env.ros.publish_control(0.0, 0.0, 0.0)
            # The lockstep environment is already paused between every action,
            # so optimizer wall time cannot consume episode simulation time.
            env.suspend_callback_dispatch()
            for name, values in self.reward_terms.items():
                if values:
                    self.logger.record(f"reward_terms/{name}", float(np.mean(values)))

    def sync_adaptive_terrain_state(model, environment) -> None:
        model.nino_adaptive_terrain_state = environment.adaptive_terrain_state()

    class AdaptiveCheckpointCallback(CheckpointCallback):
        """Keep rolling curriculum progress inside each normal PPO checkpoint."""

        def _on_step(self) -> bool:
            if self.n_calls % self.save_freq == 0:
                sync_adaptive_terrain_state(self.model, env)
            return super()._on_step()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = args.output.expanduser().resolve() / stamp
    checkpoint_dir = run_dir / "checkpoints"
    tensorboard_dir = run_dir / "tensorboard"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    tensorboard_dir.mkdir(parents=True, exist_ok=True)
    config["device"] = device
    with (run_dir / "ppo.yaml").open("w") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)

    import json
    import platform
    from importlib.metadata import version
    (run_dir / "run_metadata.json").write_text(json.dumps({
        "argv": sys.argv, "python": platform.python_version(), "device": device,
        "gpu": th.cuda.get_device_name(0) if device.startswith("cuda") else None,
        "packages": {name: version(name) for name in ("torch", "stable-baselines3", "gymnasium", "numpy")},
    }, indent=2) + "\n")
    env = NinoGazeboEnv(config, total_training_steps=args.timesteps)
    try:
        if args.check_env:
            initial_adaptive_state = env.adaptive_terrain_state()
            check_env(env, warn=True)
            env.restore_adaptive_terrain_state(initial_adaptive_state)
            env.global_steps = 0  # API validation does not consume the curriculum.
        monitored = Monitor(env, filename=str(run_dir / "monitor.csv"))
        ppo = config["ppo"]
        if args.resume:
            model = PPO.load(args.resume, device=device)
            validate_model(model, env.history.size, action_size(config))
            validate_resume(model, config)
            env.restore_adaptive_terrain_state(
                getattr(model, "nino_adaptive_terrain_state", None)
            )
            model.set_env(monitored)
            model.tensorboard_log = str(tensorboard_dir)
            env.global_steps = int(model.num_timesteps)
            env.total_training_steps = int(model.num_timesteps) + args.timesteps
            reset_num_timesteps = False
        else:
            policy_class, policy_kwargs = policy_spec(config)
            model = PPO(
                policy_class,
                monitored,
                learning_rate=float(ppo["learning_rate"]),
                gamma=float(ppo["gamma"]),
                gae_lambda=float(ppo["gae_lambda"]),
                n_steps=int(ppo["n_steps"]),
                batch_size=int(ppo["batch_size"]),
                n_epochs=int(ppo["n_epochs"]),
                clip_range=float(ppo["clip_range"]),
                ent_coef=float(ppo["ent_coef"]),
                vf_coef=float(ppo["vf_coef"]),
                max_grad_norm=float(ppo["max_grad_norm"]),
                target_kl=float(ppo["target_kl"]),
                policy_kwargs=policy_kwargs,
                tensorboard_log=str(tensorboard_dir),
                device=device,
                seed=int(config["seed"]),
                verbose=1,
            )
            if args.init_model:
                source = PPO.load(args.init_model, device=device)
                validate_model(source, env.history.size, action_size(config))
                from nino_rl.model_transfer import initialize_actor
                validate_action_mode(source, config)
                actor_keys = initialize_actor(model, source)
                import hashlib
                actor_transfer = dict(source=str(args.init_model.resolve()),
                    source_sha256=hashlib.sha256(args.init_model.read_bytes()).hexdigest(),
                    source_steps=int(source.num_timesteps), copied=list(actor_keys),
                    critic="fresh", optimizer="fresh", training_counter=0)
                (run_dir / "actor_transfer.json").write_text(
                    json.dumps(actor_transfer, indent=2) + "\n")
                print(f"Initialized {len(actor_keys)} actor tensors from {args.init_model}; "
                      "critic and optimizer are fresh; starting new task at step 0.",
                      flush=True)
            if speed_source is not None:
                from nino_rl.model_transfer import initialize_speed_yaw_actor
                actor_keys = initialize_speed_yaw_actor(model, speed_source)
                import hashlib
                transfer = dict(source=str(args.init_speed_model.resolve()),
                                source_sha256=hashlib.sha256(args.init_speed_model.read_bytes()).hexdigest(),
                                source_steps=int(speed_source.num_timesteps),
                                copied=list(actor_keys), source_actions=int(speed_source.action_space.shape[0]),
                                yaw_mean="zero", source_yaw_discarded=True,
                                critic="fresh", optimizer="fresh", training_counter=0)
                (run_dir / "actor_transfer.json").write_text(json.dumps(transfer, indent=2) + "\n")
                print(f"Transferred speed/features from {args.init_speed_model}; "
                      "new zero-mean yaw head, fresh critic/optimizer, new step count.", flush=True)
            model.nino_training_contract = training_contract(config)
            sync_adaptive_terrain_state(model, env)
            reset_num_timesteps = True

        checkpoint_callback = AdaptiveCheckpointCallback(
            save_freq=max(1, int(args.checkpoint_every)),
            save_path=str(checkpoint_dir),
            name_prefix="nino_ppo",
            save_replay_buffer=False,
            save_vecnormalize=True,
        )
        sync_adaptive_terrain_state(model, env)
        print(
            f"Training is active on {model.device}; results: {run_dir}",
            flush=True,
        )
        print(
            f"Collecting {model.n_steps} environment steps before each PPO "
            "update; episode-end lines are live rollout progress.",
            flush=True,
        )
        model.learn(
            total_timesteps=args.timesteps,
            callback=[checkpoint_callback, TrainingMetricsCallback()],
            reset_num_timesteps=reset_num_timesteps,
            progress_bar=False,
        )
        final_path = run_dir / "nino_ppo_final"
        sync_adaptive_terrain_state(model, env)
        model.save(final_path)
        print(f"Đã lưu policy: {final_path}.zip")
    except KeyboardInterrupt:
        if "model" in locals():
            interrupted = run_dir / "nino_ppo_interrupted"
            sync_adaptive_terrain_state(model, env)
            model.save(interrupted)
            print(f"Saved {interrupted}.zip; unfinished rollout is discarded on resume.")
        print("Training interrupted cleanly; robot stopped and simulator released.")
    except (RuntimeError, TimeoutError):
        if "model" in locals():
            interrupted = run_dir / "nino_ppo_interrupted"
            sync_adaptive_terrain_state(model, env)
            model.save(interrupted)
            print(f"Saved {interrupted}.zip; unfinished rollout is discarded on resume.")
        raise
    finally:
        env.close()


if __name__ == "__main__":
    main()
