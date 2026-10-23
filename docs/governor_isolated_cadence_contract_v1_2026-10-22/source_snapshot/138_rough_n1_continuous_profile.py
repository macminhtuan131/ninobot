"""Route-specific continuous N1 corner approach; S1 alignment remains unchanged."""
from copy import deepcopy

REVISION = "n1_continuous_corner_v18"


def configuration(original):
    if original["routes"]["stop_align_route_ids"] != ["S1"]:
        raise ValueError("Use the original qualified S1-only profile")
    config = deepcopy(original)
    config["routes"]["revision"] = REVISION
    config["routes"]["curvature_limit_route_ids"] = ["N1", "S1"]
    config["routes"]["route_lookahead_m"] = {"N1": 0.20}
    config.pop("training_reward_scale", None)
    return config


def route_controller_config(config, route_id):
    """Select estimated-pose pursuit settings; never inspect physical truth."""
    routes = dict(config["routes"])
    qualified = routes.get("curvature_limit_route_ids", routes.get("stop_align_route_ids", []))
    routes["curvature_speed_limit"] = bool(routes.get("curvature_speed_limit", False) and route_id in qualified)
    lookahead = routes.get("route_lookahead_m", {}).get(route_id)
    if lookahead is not None:
        routes["steering_lookahead_m"] = float(lookahead)
    return {**config, "routes": routes}
