"""N1-only early braking and moving corner pursuit from estimated pose."""
from copy import deepcopy
from math import atan2, cos, hypot, isfinite, sin

REVISION = "n1_early_braking_v19"
SETTINGS = dict(braking_distance_m=1.20, corner_speed_m_s=.06,
                steering_lookahead_m=.30, exit_distance_m=.70)


def configuration(original):
    if original["routes"]["stop_align_route_ids"] != ["S1"]:
        raise ValueError("Expected the original qualified S1-only profile")
    candidate = deepcopy(original)
    candidate["routes"]["revision"] = REVISION
    candidate["routes"]["n1_corner_anticipation"] = dict(SETTINGS)
    candidate.pop("training_reward_scale", None)
    return candidate


def route_controller_config(config, route_id):
    routes = dict(config["routes"])
    routes["curvature_speed_limit"] = bool(routes.get("curvature_speed_limit", False)
        and route_id in routes.get("stop_align_route_ids", []))
    anticipation = routes.pop("n1_corner_anticipation", None)
    if route_id == "N1":
        if anticipation != SETTINGS:
            raise ValueError("Unexpected N1 braking settings")
        routes["n1_corner_anticipation"] = anticipation
        routes["curvature_speed_limit"] = True
        routes["steering_lookahead_m"] = anticipation["steering_lookahead_m"]
        routes["turn_speed_m_s"] = anticipation["corner_speed_m_s"]
    return {**config, "routes": routes}


def anticipated_command(state, path, tracking, config, original_command):
    settings = config["routes"].get("n1_corner_anticipation")
    if settings is None:
        return original_command(state, path, tracking, config)
    if settings != SETTINGS:
        raise ValueError("Unexpected corner anticipation contract")
    linear, angular = original_command(state, path, tracking, config)
    cap = float(config["navigation"]["straight_speed_m_s"])
    for index in range(1, len(path.points) - 1):
        before, after = path.delta[index-1], path.delta[index]
        turn = abs(atan2(before[0]*after[1]-before[1]*after[0],
                         before[0]*after[0]+before[1]*after[1]))
        if turn < 1.0471975512:
            continue
        distance = float(path.cumulative[index]) - tracking.path_s
        if distance >= 0:
            fraction = min(1., distance / settings["braking_distance_m"])
        else:
            fraction = min(1., -distance / settings["exit_distance_m"])
        # Smoothly brake before the vertex and accelerate on the outgoing leg.
        smooth = fraction*fraction*(3.-2.*fraction)
        cap = min(cap, settings["corner_speed_m_s"] +
                  (config["navigation"]["straight_speed_m_s"]-settings["corner_speed_m_s"])*smooth)
    if linear > cap and linear > 0:
        angular *= cap / linear  # preserve pursuit curvature under braking
        linear = cap
    # While heading far away from the target, retain steering authority with
    # a small moving command, never the old 0.18m/s minimum-turn branch.
    target = path.point_at(tracking.path_s + settings["steering_lookahead_m"])
    dx, dy = target - [state.x, state.y]
    alpha = atan2(-sin(state.yaw)*dx + cos(state.yaw)*dy,
                  cos(state.yaw)*dx + sin(state.yaw)*dy)
    if abs(alpha) > 1.2217304764 and linear > 0:
        linear = min(linear, settings["corner_speed_m_s"])
        angular = max(-config["routes"]["max_yaw_rate_rad_s"],
                      min(config["routes"]["max_yaw_rate_rad_s"], 1.5*alpha))
    if not all(isfinite(v) for v in (linear, angular)):
        raise ValueError("Nonfinite N1 command")
    return linear, angular


def patch_routes(code):
    signature = "def route_command(state, path, tracking, config):"
    if code.count(signature) != 1:
        raise ValueError("Unexpected frozen route command")
    return code.replace(signature, "def _original_route_command(state, path, tracking, config):") + (
        "\n\ndef route_command(state, path, tracking, config):\n"
        "    from nino_rl.n1_anticipation_profile import anticipated_command\n"
        "    return anticipated_command(state, path, tracking, config, _original_route_command)\n")
