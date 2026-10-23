"""Deploy a PPO motor or PI-reference policy through ROS 2."""

from __future__ import annotations

import argparse
from math import ceil
from pathlib import Path
import sys
from time import monotonic

from ament_index_python.packages import get_package_share_directory
import numpy as np
import rclpy

from nino_rl.core import (
    NavReference,
    PathTracker,
    goal_reached,
    is_wrong_direction,
    load_config,
)
from nino_rl.ros_interface import RosRobotInterface
from nino_rl.task_geometry import approach_speed, goal_overshot, task_succeeded
from nino_rl.flat_feedback import flat_motion_command
from nino_rl.routes import OrderedPathTracker, RouteSet, route_command, route_budget
from nino_rl.control_v2 import (
    BASELINE_ACTION, STOP_ACTION, ObservationHistory, make_observation,
    decode_control, validate_model, validate_action_mode, action_size, history_action,
)


def arguments() -> argparse.Namespace:
    share = Path(get_package_share_directory("nino_rl"))
    parser = argparse.ArgumentParser(description="Run a trained Nino PPO control policy")
    parser.add_argument("--model", type=Path,
                        default=share / "models" / "completed_train" / "nino_ppo_final.zip")
    parser.add_argument("--config", type=Path, default=share / "models" / "completed_train" / "ppo.yaml")
    parser.add_argument("--path", type=Path, default=share / "config" / "path.yaml")
    parser.add_argument("--route", help="Run a configured drawn route (default: E1 when routes are enabled)")
    parser.add_argument("--use-sim-time", action="store_true")
    parser.add_argument("--device", default="cpu", help="cuda, cpu, or auto (default: cpu)")
    return parser.parse_args(sys.argv[1:])


class PolicyNode(RosRobotInterface):
    def __init__(self, args: argparse.Namespace) -> None:
        self.config = load_config(args.config)
        if (self.config.get("action_mode") == "speed_yaw_reference"
                and self.config.get("routes", {}).get("enabled", False)):
            raise ValueError("speed_yaw_reference requires a straight course without drawn routes")
        super().__init__(
            world_name=str(self.config.get("world_name", "long_hall")),
            subscribe_plan=False,
            use_sim_time=args.use_sim_time,
            node_name="nino_rl_policy",
            cmd_vel_topic=str(self.config["navigation"].get("cmd_vel_topic", "/cmd_vel")),
            terrain_height_threshold_m=float(self.config["policy_v2"].get("terrain_height_threshold_m", .006)),
            odometry_assistance=self.config.get("odometry_assistance"),
        )
        self.imu_includes_gravity = bool(self.config["policy_v2"]["imu_includes_gravity"])
        self.history = ObservationHistory(self.config["policy_v2"]["history_frames"])
        try:
            from stable_baselines3 import PPO
        except ImportError as error:
            raise RuntimeError("Thiếu stable-baselines3; xem README_VI.md") from error

        self.route_set = RouteSet(self.config)
        self.route_id = None
        self.target_seconds = float(self.config["target_finish_seconds"])
        self.deadline_seconds = float(self.config["max_episode_seconds"])
        if self.route_set.enabled:
            selected = self.route_set.select(np.random.default_rng(0), 0,
                                            args.route or self.route_set.settings.get("fixed_route") or "E1")
            self.route_id = selected["id"]
            self.path = OrderedPathTracker(selected["waypoints"], self.route_set.settings)
            self.target_seconds, self.deadline_seconds = route_budget(self.config, self.path.total_length)
            self.path_source = f"drawn route {self.route_id}"
        else:
            if args.route is not None:
                raise ValueError("--route requires an enabled routes configuration")
            path_config = load_config(args.path)
            self.path = PathTracker(path_config["waypoints"])
            self.path_source = "YAML"
        self.path_started_at = None
        self.deadline_reported = False
        self.wrong_direction_reported = False
        self.wrong_direction_steps = 0
        self.wrong_direction_required_steps = max(
            1,
            ceil(
                float(self.config["wrong_direction_hold_seconds"])
                * float(self.config["control_hz"])
            ),
        )
        self.previous_action = BASELINE_ACTION.copy()
        self.straight_speed = float(self.config["navigation"]["straight_speed_m_s"])
        self.minimum_approach_speed = float(
            self.config["navigation"].get("minimum_approach_speed_m_s", 0.03)
        )
        self.goal_slowdown_distance = float(
            self.config["navigation"]["goal_slowdown_distance_m"]
        )
        self.action_scale = float(self.config["max_wheel_torque_nm"])
        self.lookahead = list(self.config["path"]["lookahead_m"])
        self.collision_distance = float(self.config["lidar_collision_m"])
        self.off_path_limit = float(self.config["off_path_limit_m"])
        self.rollover_limit = np.deg2rad(float(self.config["rollover_limit_deg"]))
        device = args.device or str(self.config.get("device", "cuda"))
        self.model = PPO.load(args.model, device=device)
        validate_model(self.model, self.history.size, action_size(self.config))
        validate_action_mode(self.model, self.config)
        self.timer = self.create_timer(1.0 / float(self.config["control_hz"]), self._control)
        self.get_logger().info(
            f"PPO policy loaded on {self.model.device}; {self.path_source}, Nav2 disabled"
        )

    def _control(self) -> None:
        if not self.sensors_ready():
            self._stop_policy()
            return
        if self.path_started_at is None:
            self.path_started_at = self.get_clock().now().nanoseconds * 1e-9
        state = self.snapshot()
        if self.route_set.enabled:
            self.path.advance(state.x, state.y)
        finite_ranges = [value for value in state.lidar_ranges if np.isfinite(value)]
        if finite_ranges and min(finite_ranges) <= self.collision_distance:
            self._stop_policy()
            return
        _, tracking = make_observation(
            state, self.path, self.lookahead, self.previous_action
        )
        speed = approach_speed(tracking.endpoint_distance, tracking.distance_remaining,
                               tracking.heading_error, self.config)
        if self.route_set.enabled:
            speed, angular = route_command(state, self.path, tracking, self.config)
            self.publish_motion_command(speed, angular)
        elif self.config.get("action_mode", "wheel_torque") in ("yaw_reference", "speed_yaw_reference"):
            # Match the training observation's previous executed yaw reference.
            previous = (self.previous_action[[0, 2]]
                        if action_size(self.config) == 2 else self.previous_action)
            _, _, previous_yaw = decode_control(previous, self.config)
            linear, angular = flat_motion_command(state, self.path, tracking, self.config, previous_yaw)
            self.publish_motion_command(linear, angular)
        else:
            self.publish_straight_command(speed)
        elapsed = self.get_clock().now().nanoseconds * 1e-9 - self.path_started_at
        desired_linear, desired_angular = self.desired_twist()
        # Match the environment's configured waypoint reference/budget.
        spacing = self.config["navigation"]["waypoint_spacing_m"]
        waypoint_s = min(self.path.total_length, (int(tracking.path_s / spacing) + 1) * spacing)
        budget = (self.config["navigation"]["waypoint_slack_seconds"]
                  + self.config["navigation"]["waypoint_budget_seconds_per_m"] * waypoint_s)
        if waypoint_s >= self.path.total_length:
            budget = self.target_seconds
        reference = NavReference(
            desired_linear_velocity=desired_linear,
            desired_angular_velocity=desired_angular,
            local_waypoint_distance=max(0.0, waypoint_s - tracking.path_s),
            final_goal_distance=tracking.endpoint_distance,
            waypoint_time_remaining_fraction=float(
                np.clip(
                    (
                        float(budget)
                        - elapsed
                    )
                    / max(float(budget), 1.0),
                    -1.0,
                    1.0,
                )
            ),
            valid=self.straight_reference_valid(
                float(self.config["navigation"]["stale_seconds"])
            ),
        )
        preview = self.terrain_preview(self.config["policy_v2"]["preview_timeout_seconds"])
        if (self.config["policy_v2"]["require_terrain_preview"] and not preview[-1]
                or self.control_publisher.get_subscription_count() == 0):
            self._stop_policy()
            return
        try:
            frame, tracking = make_observation(
                state, self.path, self.lookahead, self.previous_action, reference,
                preview, self.imu_includes_gravity,
                action_mode=self.config.get("action_mode", "wheel_torque"))
        except ValueError:
            self._stop_policy()
            return
        observation = self.history.append(frame)
        timed_out = elapsed >= self.deadline_seconds
        wrong_direction_sample = (
            elapsed
            >= float(self.config["wrong_direction_grace_seconds"])
            and is_wrong_direction(tracking, state, self.config)
        )
        if wrong_direction_sample:
            self.wrong_direction_steps += 1
        else:
            self.wrong_direction_steps = 0
            self.wrong_direction_reported = False
        wrong_direction = (
            self.wrong_direction_steps >= self.wrong_direction_required_steps
        )
        if (
            task_succeeded(tracking, state, self.path, self.config)
            or goal_overshot(state, self.path, self.config)
            or timed_out
            or wrong_direction
            or (self.path.corridor_distance(state.x, state.y) if self.route_set.enabled
                else abs(tracking.lateral_error)) >= self.off_path_limit
            or max(abs(state.roll), abs(state.pitch)) >= self.rollover_limit
            or not reference.valid
        ):
            self._stop_policy()
            if timed_out and not self.deadline_reported:
                self.get_logger().warning(
                    "Quá thời gian chạy tối đa; giữ mô-men hai bánh ở 0"
                )
                self.deadline_reported = True
            if wrong_direction and not self.wrong_direction_reported:
                self.get_logger().error(
                    "Hủy attempt: robot chạy ngược hoặc lệch quá xa hướng /plan"
                )
                self.wrong_direction_reported = True
            return
        action, _ = self.model.predict(observation, deterministic=True)
        action = np.clip(np.asarray(action, dtype=np.float32), -1.0, 1.0)
        if not np.all(np.isfinite(action)):
            self.get_logger().error("Policy returned non-finite action; commanding zero torque")
            self._stop_policy()
            return
        scale, torque, yaw_reference = decode_control(
            action, self.config, path_remaining=tracking.distance_remaining)
        if self.config.get("action_mode", "wheel_torque") in ("yaw_reference", "speed_yaw_reference"):
            linear, angular = flat_motion_command(state, self.path, tracking, self.config, yaw_reference)
            self.publish_motion_command(linear, angular)
        self.publish_control(scale, float(torque[0]), float(torque[1]))
        self.previous_action = history_action(action, self.config)

    def _stop_policy(self):
        self.publish_control(0.0, 0.0, 0.0)
        self.publish_straight_command(0.0)
        self.previous_action = STOP_ACTION.copy()
        self.history.values.clear()


def main() -> None:
    args = arguments()
    rclpy.init(args=[])
    node = None
    try:
        node = PolicyNode(args)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node._stop_policy()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
