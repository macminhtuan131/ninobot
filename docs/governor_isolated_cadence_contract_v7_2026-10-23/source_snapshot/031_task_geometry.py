"""Goal approach geometry shared by training and deployment."""
import numpy as np
from copy import copy
from nino_rl.core import goal_reached


def objective_state(state, config):
    """Privileged simulator pose for scoring only, never an actor input."""
    source = config.get("reward_pose_source", "wheel_odometry")
    if source == "wheel_odometry":
        return state
    if source != "ground_truth":
        raise ValueError(f"Unknown reward_pose_source: {source}")
    result = copy(state)
    result.x, result.y, result.yaw = state.ground_x, state.ground_y, state.ground_yaw
    return result


def task_succeeded(tracking, state, path, config):
    """Rocky tracking ends at a bounded goal gate; legacy uses its circle."""
    if config.get("routes", {}).get("enabled", False):
        if (not getattr(path, "gates_complete", False)
                or tracking.distance_remaining > float(config["goal_tolerance_m"])):
            return False
    if config.get("task", "goal_arrival") != "rocky_tracking":
        return goal_reached(tracking, state, config)
    tangent = path.delta[-1] / path.lengths[-1]
    offset = np.array([state.x, state.y]) - path.points[-1]
    forward = float(offset @ tangent)
    lateral = float(tangent[0] * offset[1] - tangent[1] * offset[0])
    return bool(
        0.0 <= forward <= float(config["goal_overshoot_limit_m"])
        and abs(lateral) <= float(config["goal_lateral_tolerance_m"])
        and abs(tracking.heading_error) <= np.deg2rad(config["goal_heading_tolerance_deg"])
    )


def approach_speed(endpoint_distance, path_remaining, heading_error, config):
    """Keep steering authority near arrival; never accelerate after overshoot."""
    nav = config["navigation"]
    if config.get("task", "goal_arrival") == "rocky_tracking":
        # Traverse the 6 m line at a controlled speed, then stop on termination.
        # This task has no docking or in-circle alignment maneuver.
        return float(nav["straight_speed_m_s"])
    tolerance = float(config["goal_tolerance_m"])
    # Aim inside the scoring circle so modest odometry error does not stop
    # motion at its outer edge. This uses estimated pose only; success remains
    # independently scored by task_succeeded(). Old configs retain their stop.
    stop_tolerance = float(nav.get("goal_stop_tolerance_m", tolerance))
    if not np.isfinite(stop_tolerance) or not 0.0 <= stop_tolerance <= tolerance:
        raise ValueError("navigation.goal_stop_tolerance_m must be between zero and goal_tolerance_m")
    cruise = float(nav["straight_speed_m_s"])
    minimum = float(nav.get("minimum_approach_speed_m_s", .03))
    slowdown = max(float(nav["goal_slowdown_distance_m"]), tolerance)
    if endpoint_distance <= stop_tolerance and abs(heading_error) <= np.deg2rad(
        config["goal_heading_tolerance_deg"]
    ):
        return 0.0
    # A lateral miss must not make the cruise command grow again. Keep a
    # small forward command so residual steering is still enabled by the PI
    # controller until success or the overshoot failure boundary.
    remaining = min(float(endpoint_distance), max(0., float(path_remaining)))
    return float(max(minimum, cruise * np.clip((remaining - stop_tolerance) / slowdown, 0., 1.)))


def goal_overshot(state, path, config):
    """A forward-only mission cannot recover an arbitrarily missed goal."""
    if config.get("routes", {}).get("enabled", False):
        # A route can cross the final goal's infinite plane much earlier.
        if getattr(path, "cursor", 0.) < path.total_length - 1.0:
            return False
    tangent = path.delta[-1] / path.lengths[-1]
    beyond = float(np.dot(np.array([state.x, state.y]) - path.points[-1], tangent))
    return beyond > float(config.get("goal_overshoot_limit_m", .30))
