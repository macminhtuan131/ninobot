"""Opt-in estimated-pose path feedback for the straight flat specialist."""
from math import atan2, cos, sin
import numpy as np
from nino_rl.task_geometry import approach_speed


def flat_motion_command(state, path, tracking, config, policy_yaw=0.):
    nav = config['navigation']
    feedback = nav.get('path_feedback', {})
    speed = approach_speed(tracking.endpoint_distance, tracking.distance_remaining,
                           tracking.heading_error, config)
    if not feedback.get('enabled', False):
        return speed, float(policy_yaw)
    lookahead = float(feedback.get('lookahead_m', .45))
    limit = float(feedback.get('max_yaw_rate_rad_s', .8))
    fade = float(feedback.get('residual_fade_distance_m', 1.0))
    if not np.isfinite([lookahead, limit, fade, policy_yaw]).all() or min(lookahead, limit, fade) <= 0:
        raise ValueError('Flat feedback requires positive finite lookahead, yaw limit and fade')
    if speed == 0.:
        return 0., 0.
    dx, dy = path.point_at(tracking.path_s + lookahead) - [state.x, state.y]
    local_x = cos(state.yaw) * dx + sin(state.yaw) * dy
    local_y = -sin(state.yaw) * dx + cos(state.yaw) * dy
    alpha = atan2(local_y, local_x)
    yaw = speed * 2. * local_y / max(dx * dx + dy * dy, .01)
    if abs(alpha) > np.deg2rad(70.):
        speed = min(speed, .06)
        yaw = 1.5 * alpha
    # Policy yaw is a bounded residual, progressively removed at docking.
    # Along-path distance prevents authority returning after overshoot.
    stop = float(nav.get('goal_stop_tolerance_m', config['goal_tolerance_m']))
    if fade <= stop:
        raise ValueError('Flat yaw residual fade must exceed the stop tolerance')
    factor = float(np.clip((tracking.distance_remaining - stop) / (fade - stop), 0., 1.))
    return float(speed), float(np.clip(yaw + factor * policy_yaw, -limit, limit))
