"""Drawn route selection, ordered projection and odometry-only path steering."""
from math import atan2, cos, sin

import numpy as np

from nino_rl.core import PathTracker, wrap_angle
from nino_rl.task_geometry import approach_speed


class OrderedPathTracker(PathTracker):
    """Project near the last visited arc position; nearby return legs cannot win.

    Projection is read-only: noisy actor samples must never advance the cursor.
    Call advance once per fresh physical/odometry sample on separate trackers.
    Ordered spatial gates prevent skipping a route by jumping to its endpoint.
    """

    def __init__(self, points, settings):
        super().__init__(points)
        self.forward_window = float(settings.get("projection_forward_m", .8))
        self.backward_window = float(settings.get("projection_backward_m", .5))
        self.gate_radius = float(settings.get("gate_radius_m", .6))
        spacing = float(settings.get("gate_spacing_m", 1.0))
        if not np.isfinite([self.forward_window, self.backward_window,
                            self.gate_radius, spacing]).all() or min(
                                self.forward_window, self.backward_window,
                                self.gate_radius, spacing) <= 0:
            raise ValueError("Route projection windows/gate settings must be positive and finite")
        self.cursor = 0.0
        self.gate_s = np.unique(np.r_[np.arange(spacing, self.total_length, spacing),
                                     self.cumulative[1:-1]])
        self.next_gate = 0

    def project(self, x, y):
        low = max(0., self.cursor - self.backward_window)
        high = min(self.total_length, self.cursor + self.forward_window)
        indices = np.flatnonzero((self.cumulative[:-1] < high)
                                 & (self.cumulative[1:] > low))
        start = self.points[indices]
        delta = self.delta[indices]
        lengths = self.lengths[indices]
        position = np.asarray([x, y], dtype=float)
        fractions = np.sum((position - start) * delta, axis=1) / lengths**2
        fractions = np.clip(fractions, np.maximum(0., (low - self.cumulative[indices]) / lengths),
                            np.minimum(1., (high - self.cumulative[indices]) / lengths))
        projections = start + fractions[:, None] * delta
        errors = position - projections
        closest = int(np.argmin(np.sum(errors**2, axis=1)))
        index = indices[closest]
        tangent = self.delta[index] / self.lengths[index]
        s = self.cumulative[index] + fractions[closest] * self.lengths[index]
        lateral = tangent[0] * errors[closest, 1] - tangent[1] * errors[closest, 0]
        return float(s), float(lateral), atan2(tangent[1], tangent[0]), projections[closest]

    def advance(self, x, y):
        s, _, _, projection = self.project(x, y)
        # Do not creep the cursor along the route while the robot is far away.
        if np.linalg.norm(np.asarray([x, y]) - projection) <= self.gate_radius:
            self.cursor = max(self.cursor, s)
        while self.next_gate < len(self.gate_s):
            gate = self.gate_s[self.next_gate]
            if (abs(gate - self.cursor) > self.forward_window
                    or np.linalg.norm(np.asarray([x, y]) - self.point_at(gate)) > self.gate_radius):
                break
            self.next_gate += 1

    @property
    def gates_complete(self):
        return self.next_gate == len(self.gate_s)

    def corridor_distance(self, x, y):
        return float(np.linalg.norm(np.asarray([x, y]) - self.project(x, y)[3]))


class RouteSet:
    def __init__(self, config):
        self.settings = config.get("routes", {})
        self.enabled = bool(self.settings.get("enabled", False))
        self.routes = self.settings.get("definitions", []) if self.enabled else []
        self.bag = []
        if not self.enabled:
            return
        if not self.routes:
            raise ValueError("Enabled routes need definitions")
        ids = [item["id"] for item in self.routes]
        if len(set(ids)) != len(ids):
            raise ValueError("Route IDs must be unique")
        start = np.asarray(config["navigation"]["start_pose"][:2])
        for item in self.routes:
            path = OrderedPathTracker(item["waypoints"], self.settings)
            if not np.allclose(path.points[0], start, atol=1e-6, rtol=0):
                raise ValueError(f"Route {item['id']} must begin at navigation.start_pose")
            if not np.isfinite(float(item["goal_heading_deg"])):
                raise ValueError("Route goal heading must be finite")
            if abs(wrap_angle(np.deg2rad(item["goal_heading_deg"]) - atan2(
                    path.delta[-1, 1], path.delta[-1, 0]))) > 1e-6:
                raise ValueError(f"Route {item['id']} final heading must match its final segment")
        if self.settings.get("selection", "balanced_shuffle") not in ("balanced_shuffle", "round_robin"):
            raise ValueError("Route selection must be balanced_shuffle or round_robin")
        fixed = self.settings.get("fixed_route")
        if fixed is not None and fixed not in ids:
            raise ValueError(f"Unknown route {fixed}; choose from {ids}")
        if config.get("action_mode", "wheel_torque") != "wheel_torque":
            raise ValueError("Drawn routes currently require wheel_torque actions")
        if config["reward_v2"].get("progress_metric") != "path":
            raise ValueError("Drawn routes require path progress, not endpoint progress")
        for key in ("target_seconds_per_m", "target_slack_seconds", "deadline_slack_seconds",
                    "steering_lookahead_m", "max_yaw_rate_rad_s", "turn_speed_m_s"):
            value = float(self.settings[key])
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"routes.{key} must be positive and finite")
        from nino_rl.rough_curriculum import curriculum_stage
        stage = curriculum_stage(config)
        if stage is not None:
            self.routes = [item for item in self.routes if item["id"] in stage["route_ids"]]
            if fixed is not None and fixed not in stage["route_ids"]:
                raise ValueError("Fixed route is not active in the current rough curriculum stage")

    def select(self, rng, episode_index, requested=None):
        fixed = requested or self.settings.get("fixed_route")
        if fixed is not None:
            for route in self.routes:
                if route["id"] == fixed:
                    return route
            raise ValueError(f"Unknown route {fixed}")
        if self.settings.get("selection", "balanced_shuffle") == "round_robin":
            return self.routes[episode_index % len(self.routes)]
        if not self.bag:
            self.bag = list(rng.permutation(len(self.routes)))
        return self.routes[self.bag.pop()]


def route_budget(config, length):
    settings = config["routes"]
    target = max(float(config["target_finish_seconds"]),
                 length * settings["target_seconds_per_m"] + settings["target_slack_seconds"])
    deadline = max(float(config["max_episode_seconds"]), target + settings["deadline_slack_seconds"])
    return float(target), float(deadline)


def route_command(state, path, tracking, config):
    """Pure-pursuit yaw baseline; PPO retains speed and left/right residuals."""
    settings = config["routes"]
    lookahead = float(settings.get("steering_lookahead_m", .45))
    yaw_limit = float(settings.get("max_yaw_rate_rad_s", .8))
    minimum_turn_speed = float(settings.get("turn_speed_m_s", .12))
    if not np.isfinite([lookahead, yaw_limit, minimum_turn_speed]).all() or min(
            lookahead, yaw_limit, minimum_turn_speed) <= 0:
        raise ValueError("Route steering settings must be positive and finite")
    target = path.point_at(tracking.path_s + lookahead)
    dx, dy = target - [state.x, state.y]
    local_x = cos(state.yaw) * dx + sin(state.yaw) * dy
    local_y = -sin(state.yaw) * dx + cos(state.yaw) * dy
    alpha = atan2(local_y, local_x)
    # Endpoint distance alone would slow/stop the west loop at its start.
    near_finish = tracking.distance_remaining <= config["navigation"]["goal_slowdown_distance_m"]
    remaining = tracking.distance_remaining
    speed = approach_speed(tracking.endpoint_distance if near_finish else remaining,
                           remaining, tracking.heading_error, config)
    cruise = config["navigation"]["straight_speed_m_s"]
    speed = min(speed, max(minimum_turn_speed, cruise * max(0., cos(alpha))))
    curvature = 2. * local_y / max(dx * dx + dy * dy, .01)
    yaw = float(np.clip(speed * curvature, -yaw_limit, yaw_limit))
    if abs(alpha) > np.deg2rad(70.):
        # Retain the existing PI loop's moving-command steering authority.
        speed = min(speed, minimum_turn_speed)
        yaw = float(np.clip(1.5 * alpha, -yaw_limit, yaw_limit))
    if speed == 0.:
        yaw = 0.
    return float(speed), yaw
