"""Route coverage, shortcut rejection and closed-loop steering regressions."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

import numpy as np
import pytest

from nino_rl.core import RobotState, load_config, wrap_angle
from nino_rl.control_v2 import BASELINE_ACTION, compute_reward, make_observation
from nino_rl.routes import OrderedPathTracker, RouteSet, route_budget, route_command
from nino_rl.task_geometry import goal_overshot, task_succeeded
from nino_rl.trajectory_metrics import path_metrics
from nino_rl.training_contract import training_contract

CONFIG = load_config(Path(__file__).parents[1] / "config/combined_rough_section.yaml")
ROUTES = CONFIG["routes"]["definitions"]


def tracking(state, path):
    return make_observation(state, path, CONFIG["path"]["lookahead_m"], BASELINE_ACTION)[1]


def test_eight_goals_match_halls_and_balanced_cycles():
    metadata = load_metadata()
    poses = {station["id"]: station["pose"] for station in metadata["goal_stations"]}
    routes = RouteSet(CONFIG)
    rng = np.random.default_rng(42)
    for cycle in range(3):
        selected = [routes.select(rng, cycle * 8 + i)["id"] for i in range(8)]
        assert set(selected) == set(poses)
    for route in ROUTES:
        np.testing.assert_allclose(route["waypoints"][-1], poses[route["id"]][:2])
        assert wrap_angle(np.deg2rad(route["goal_heading_deg"]) - poses[route["id"]][2]) == pytest.approx(0.)
    assert routes.select(rng, 100, "S2")["id"] == "S2"
    with pytest.raises(ValueError, match="Unknown route"):
        routes.select(rng, 0, "missing")


def load_metadata():
    import json
    return json.loads((Path(__file__).parents[2] /
                      "nino_description/worlds/combined_rough_section.json").read_text())


def test_return_leg_and_endpoint_cannot_skip_west_loop():
    route = next(item for item in ROUTES if item["id"] == "W1")
    path = OrderedPathTracker(route["waypoints"], CONFIG["routes"])
    # Even teleporting to the final gate with correct heading cannot succeed.
    state = RobotState(x=-.75, yaw=np.pi)
    for _ in range(50):
        path.advance(state.x, state.y)
    assert path.cursor == 0.
    assert not task_succeeded(tracking(state, path), state, path, CONFIG)
    assert not path.gates_complete
    # Leaving towards the upper terrain is forward progress, although the
    # final goal gets farther away. Actor projection has no side effects.
    before = tracking(RobotState(), path)
    path.advance(.2, .4)
    state = RobotState(x=.2, y=.4, yaw=np.arctan2(.65, .3))
    after = tracking(state, path)
    cursor = path.cursor
    for _ in range(5):
        tracking(RobotState(x=8., y=-3.), path)
    assert path.cursor == cursor
    _, terms = compute_reward(before, after, state, BASELINE_ACTION, BASELINE_ACTION,
                              [0., 0.], .1, {"impact_integral": 0.},
                              {**CONFIG["reward_v2"], "torque_scale_nm": 2.})
    assert terms["progress"] > 0.
    assert after.endpoint_distance > before.endpoint_distance


@pytest.mark.parametrize("route", ROUTES, ids=[r["id"] for r in ROUTES])
@pytest.mark.parametrize("scale", [1., .7])
def test_kinematic_follower_traverses_each_full_route(route, scale):
    """Feasibility only; this does not claim Gazebo/terrain/PPO success."""
    path = OrderedPathTracker(route["waypoints"], CONFIG["routes"])
    state = RobotState()
    target, deadline = route_budget(CONFIG, path.total_length)
    dt, max_distance = .1, 0.
    for step in range(int(deadline / dt)):
        path.advance(state.x, state.y)
        current = tracking(state, path)
        max_distance = max(max_distance, path.corridor_distance(state.x, state.y))
        if task_succeeded(current, state, path, CONFIG):
            break
        assert not goal_overshot(state, path, CONFIG)
        speed, yaw = route_command(state, path, current, CONFIG)
        # Existing effort_drive scales forward and yaw references together.
        state.x += speed * scale * np.cos(state.yaw + yaw * scale * dt / 2.) * dt
        state.y += speed * scale * np.sin(state.yaw + yaw * scale * dt / 2.) * dt
        state.yaw = wrap_angle(state.yaw + yaw * scale * dt)
    assert task_succeeded(tracking(state, path), state, path, CONFIG), (
        route["id"], scale, state.x, state.y, state.yaw, path.cursor, path.next_gate)
    assert max_distance < .6
    assert step * dt <= target
    assert path.gates_complete


def test_budget_is_length_based_and_does_not_mutate_resume_contract():
    before = training_contract(CONFIG)
    short = route_budget(CONFIG, 8.7)
    long = route_budget(CONFIG, 28.)
    assert long[0] > short[0] and long[1] > short[1]
    assert training_contract(CONFIG) == before


def test_ordered_trajectory_metrics_do_not_claim_end_progress_near_start():
    route = next(item for item in ROUTES if item["id"] == "W1")
    metrics = path_metrics([0., .1, .2], [[0., 0.], [-.35, 0.], [-.75, 0.]],
                           route["waypoints"], route_settings=CONFIG["routes"])
    assert metrics["max_progress_fraction"] < .02
    assert metrics["path_max_m"] >= .75


def test_legacy_configuration_keeps_straight_geometry():
    config = deepcopy(CONFIG)
    config.pop("routes")
    assert not RouteSet(config).enabled
    config = deepcopy(CONFIG)
    config["reward_v2"]["progress_metric"] = "endpoint"
    with pytest.raises(ValueError, match="path progress"):
        RouteSet(config)
