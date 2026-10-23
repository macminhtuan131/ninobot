"""Bounded route recovery using localized XY, IMU and encoders only."""
from collections import deque
import json
import math
import os


def route_controller_config(config, route_id):
    """Only the explicitly qualified S1 turn uses the new pursuit limiter."""
    if route_id in config['routes'].get('stop_align_route_ids', []):
        return config
    return {**config, 'routes': {**config['routes'], 'curvature_speed_limit': False}}


class CornerAlignment:
    """Reach sharp drawn vertices and align before entering the next slope."""
    def __init__(self):
        self.completed = set()
        self.vertex = None
        self.started = None
        self.failed = False

    def command(self, t, state, path, tracking, linear, angular):
        for index in range(1, len(path.points)-1):
            if index in self.completed:
                continue
            before, after = path.delta[index-1], path.delta[index]
            turn = abs(math.atan2(before[0]*after[1]-before[1]*after[0],
                                  before[0]*after[0]+before[1]*after[1]))
            if turn < math.radians(60):
                self.completed.add(index)
                continue
            if tracking.path_s < path.cumulative[index]-.65:
                return linear, angular, False
            self.vertex = index
            dx, dy = path.points[index]-[state.x, state.y]
            distance = math.hypot(dx, dy)
            if distance > .10 and self.started is None:
                error = math.atan2(math.sin(math.atan2(dy, dx)-state.yaw),
                                   math.cos(math.atan2(dy, dx)-state.yaw))
                return min(.18, max(.04, .8*distance))*max(0., math.cos(error)), max(-.45, min(.45, 1.5*error)), True
            if self.started is None:
                self.started = t
            desired = math.atan2(after[1], after[0])
            error = math.atan2(math.sin(desired-state.yaw), math.cos(desired-state.yaw))
            if abs(error) < .08:
                self.completed.add(index)
                self.started = None
                return linear, angular, False
            if t-self.started > 8.:
                self.failed = True
                return 0., 0., True
            return 0., max(-.45, min(.45, 1.5*error)), True
        return linear, angular, False


class StallRecovery:
    def __init__(self, config):
        numeric = [value for key, value in config.items() if key != 'revision']
        if not all(math.isfinite(value) and value > 0 for value in numeric):
            raise ValueError('Recovery settings must be finite and positive')
        if (config['backoff_speed_m_s'] > .08 or config['backoff_distance_m'] > .15
                or config['backoff_seconds'] > 2.5 or config['retry_speed_m_s'] > .18
                or config['maximum_attempts'] > 3 or int(config['maximum_attempts']) != config['maximum_attempts']):
            raise ValueError('Recovery settings exceed the bounded controller contract')
        self.cfg = config
        self.samples = deque()
        self.mode = "tracking"
        self.attempts = 0
        self.stationary_since = None
        self.phase_started = 0.
        self.origin = (0., 0.)
        self.last_time = None

    def event(self, t, state, kind):
        filename = os.environ.get("NINO_ROUGH_RECOVERY_LOG")
        if filename:
            with open(filename, "a") as stream:
                stream.write(json.dumps(dict(time=t, x=state.x, y=state.y, yaw=state.yaw,
                    roll=state.roll, pitch=state.pitch, event=kind, attempts=self.attempts)) + "\n")

    def command(self, t, state, tracking, linear, angular):
        """Return command + override flag. No ground-truth fields are read."""
        if not math.isfinite(t) or self.last_time is not None and t < self.last_time:
            raise ValueError("Recovery simulation clock must be finite and monotonic")
        self.last_time = t
        cfg = self.cfg
        if not getattr(state, "localization_valid", True):
            return 0., 0., True
        if self.mode == "exhausted":
            return 0., 0., True
        if max(abs(state.roll), abs(state.pitch)) >= cfg["maximum_tilt_rad"]:
            self.stationary_since = None
            if self.mode != "tracking":
                self.mode = "exhausted"
                self.event(t, state, "unsafe_recovery_attitude")
                return 0., 0., True
            return linear, angular, False
        if self.mode == "backoff":
            distance = math.hypot(state.x-self.origin[0], state.y-self.origin[1])
            if distance < cfg["backoff_distance_m"] and t-self.phase_started < cfg["backoff_seconds"]:
                return -cfg["backoff_speed_m_s"], 0., True
            self.mode = "retry"
            self.phase_started = t
            self.samples.clear()
            self.stationary_since = None
            self.event(t, state, "retry_turn")
        if self.mode == "retry":
            if t-self.phase_started < cfg["retry_seconds"]:
                return min(linear, cfg["retry_speed_m_s"]), angular, True
            self.mode = "tracking"
            self.samples.clear()
            self.event(t, state, "tracking_resumed")
        self.samples.append((t, state.x, state.y))
        while len(self.samples) > 1 and t-self.samples[1][0] >= cfg["window_seconds"]:
            self.samples.popleft()
        span = t-self.samples[0][0]
        wheel_speed = cfg["wheel_radius_m"] * max(abs(state.left_wheel_velocity), abs(state.right_wheel_velocity))
        movement = math.hypot(state.x-self.samples[0][1], state.y-self.samples[0][2])
        stationary = (span >= cfg["window_seconds"]-.01 and movement/span < cfg["stationary_speed_m_s"]
            and wheel_speed > cfg["wheel_spin_speed_m_s"] and linear > .05
            and tracking.endpoint_distance > cfg["goal_exclusion_m"])
        if not stationary:
            self.stationary_since = None
            return linear, angular, False
        if self.stationary_since is None:
            self.stationary_since = t
        if t-self.stationary_since < cfg["trigger_seconds"]:
            return linear, angular, False
        if self.attempts >= cfg["maximum_attempts"]:
            self.mode = "exhausted"
            self.event(t, state, "recovery_exhausted")
            return 0., 0., True
        self.attempts += 1
        self.mode = "backoff"
        self.phase_started = t
        self.origin = (state.x, state.y)
        self.event(t, state, "backoff_started")
        return -cfg["backoff_speed_m_s"], 0., True


def install_recovery(package):
    """Install in the frozen rough copy; live flat sources are untouched."""
    interface = package / "ros_interface.py"
    content = interface.read_text()
    original = 'if not isfinite(linear_m_s) or linear_m_s < 0.0:'
    if content.count(original) != 1:
        raise RuntimeError("Motion command guard changed")
    content = content.replace(original,
        'if not isfinite(linear_m_s) or linear_m_s < getattr(self, "_reverse_limit", 0.0):')
    anchor = '    def straight_reference_valid('
    method = '''    def publish_recovery_command(self, linear, angular):
        if not isfinite(linear) or not -.08 <= linear <= .18 or not isfinite(angular) or abs(angular) > .45:
            raise ValueError("Recovery reference exceeds fixed command limits")
        self._reverse_limit = -.08
        try:
            self.publish_motion_command(linear, angular)
        finally:
            self._reverse_limit = 0.0

'''
    if content.count(anchor) != 1:
        raise RuntimeError("Reference declaration changed")
    interface.write_text(content.replace(anchor, method+anchor))
    environment = package / "ros_env.py"
    content = environment.read_text()
    # Insert after __future__ imports, if any.
    anchor = 'from nino_rl.routes import OrderedPathTracker, RouteSet, route_command, route_budget'
    if content.count(anchor) != 1:
        raise RuntimeError("Route import changed")
    content = content.replace(anchor, anchor+'\nfrom nino_rl.rough_stall_recovery import StallRecovery, CornerAlignment, route_controller_config')
    anchor = '        self.stall_window = StallWindow()'
    content = content.replace(anchor, anchor+'\n        self.rough_recovery = StallRecovery(self.config["rough_stall_recovery"])\n        self.rough_corner = CornerAlignment()')
    original = '            self.ros.publish_motion_command(linear, angular)'
    route_call = '''            linear, angular = route_command(
                self.previous_robot_state, self.path, self.previous_tracking, self.config)'''
    if content.count(route_call) != 1:
        raise RuntimeError('Route controller call changed')
    content = content.replace(route_call, '''            route_config = route_controller_config(self.config, self.episode_route['id'])
            linear, angular = route_command(
                self.previous_robot_state, self.path, self.previous_tracking, route_config)''')
    added = '''            corner_override = False
            if self.episode_route['id'] in self.config['routes'].get('stop_align_route_ids', []):
                linear, angular, corner_override = self.rough_corner.command(
                    started_sim-self.episode_started_sim, self.previous_robot_state,
                    self.path, self.previous_tracking, linear, angular)
            linear, angular, recovery_override = self.rough_recovery.command(
                started_sim-self.episode_started_sim, self.previous_robot_state,
                self.previous_tracking, linear, angular)
            if recovery_override or corner_override:
                scale = 1.0
                torque[:] = 0.0
                action = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
                self.ros.publish_recovery_command(linear, angular)
            else:
                self.ros.publish_motion_command(linear, angular)'''
    if content.count(original) != 2:
        raise RuntimeError("Route command sites changed")
    content = content.replace(original, added, 1)
    original = '        navigation_invalid = ('
    if content.count(original) != 1:
        raise RuntimeError("Localization terminal patch missing")
    content = content.replace(original,
        '        recovery_exhausted = self.rough_recovery.mode == "exhausted" or self.rough_corner.failed\n'+original)
    content = content.replace('"navigation_invalid" if navigation_invalid',
        '"recovery_exhausted" if recovery_exhausted else "navigation_invalid" if navigation_invalid')
    content = content.replace('            or navigation_invalid',
        '            or recovery_exhausted\n            or navigation_invalid')
    for indent in ('            ', '                '):
        # Exact line start avoids matching a deeper control-trace indentation.
        original = '\n'+indent+'"speed_scale": scale,'
        content = content.replace(original,
            '\n'+indent+'"rough_recovery_mode": self.rough_recovery.mode,\n'
            +indent+'"rough_recovery_attempts": self.rough_recovery.attempts,\n'
            +indent+'"speed_scale": scale,')
    environment.write_text(content)
    routes = package/'routes.py'
    content = routes.read_text()
    original = '    if speed == 0.:\n        yaw = 0.\n    return float(speed), yaw'
    added = '''    if settings.get("curvature_speed_limit", False) and abs(alpha) <= np.deg2rad(70.):
        # Preserve pursuit curvature when yaw authority saturates. Merely
        # clipping yaw at unchanged forward speed widens the corner.
        if abs(curvature) > 1e-9:
            speed = min(speed, yaw_limit / abs(curvature))
            yaw = float(np.clip(speed * curvature, -yaw_limit, yaw_limit))
    if speed == 0.:
        yaw = 0.
    return float(speed), yaw'''
    if content.count(original) != 1:
        raise RuntimeError('Route command return changed')
    routes.write_text(content.replace(original, added))
