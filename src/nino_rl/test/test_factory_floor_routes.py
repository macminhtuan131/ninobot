"""Factory route endpoints, ordered loop gates and PI reference feasibility."""
from pathlib import Path
import sys

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/nino_rl"))
from nino_rl.core import RobotState, load_config, wrap_angle
from nino_rl.control_v2 import baseline_action, make_observation, decode_control
from nino_rl.evaluation import prepare_evaluation_config
from nino_rl.routes import OrderedPathTracker, RouteSet, route_budget, route_command
from nino_rl.task_geometry import task_succeeded

CONFIG = load_config(ROOT / "src/nino_rl/config/factory_floor_routes_pi_check.yaml")
ROUTES = CONFIG["routes"]["definitions"]


def tracking(state, path):
    return make_observation(state, path, CONFIG["path"]["lookahead_m"], baseline_action(CONFIG))[1]


def test_factory_routes_match_goals_and_preserve_drawn_corners():
    spec = yaml.safe_load((ROOT / "src/nino_description/config/factory_floor_lab.yaml").read_text())
    goals = {hall["id"]: hall["goal_pose"] for hall in spec["goal_halls"]}
    routes = RouteSet(CONFIG)
    assert {r["id"] for r in routes.routes} == set(goals)
    for route in routes.routes:
        assert np.allclose(route["waypoints"][-1], goals[route["id"]][:2])
        assert wrap_angle(np.deg2rad(route["goal_heading_deg"])-goals[route["id"]][2]) == pytest.approx(0.)
        # Keep reference centers and the full robot away from outer walls.
        points = np.array(route["waypoints"])
        assert np.all((points[:,0] > -1.6) & (points[:,0] < 7.6))
        assert np.all((points[:,1] > -3.1) & (points[:,1] < 3.1))
    definitions = {r["id"]: r for r in ROUTES}
    for name, sign in (("N1",1), ("S1",-1)):
        assert definitions[name]["waypoints"] == [[0.,0.],[3.2,0.],[3.2,sign*2.75]]
    west = np.asarray(definitions["W1"]["waypoints"])
    assert west[:,0].max() > 5.45  # Pass beyond last cable before returning.
    assert west[:,1].max() > 1.4 and west[:,1].min() < -1.4


def test_route_pi_has_zero_residuals_and_explicit_selection():
    for route in ROUTES:
        config = prepare_evaluation_config(CONFIG, baseline=True, route=route["id"])
        selected = RouteSet(config).select(np.random.default_rng(0),0)
        assert selected["id"] == route["id"]
        scale, torque, _ = decode_control(baseline_action(config),config,path_remaining=5.)
        assert scale == 1. and np.all(torque == 0.)
    assert CONFIG["research_map"]["training_allowed"] is False
    assert CONFIG["research_map"]["optuna_allowed"] is False
    straight = load_config(ROOT / "src/nino_rl/config/factory_floor_smoke.yaml")
    assert straight["action_mode"] == "speed_yaw_reference"
    assert straight["routes"]["enabled"] is False


def test_factory_west_goal_cannot_skip_loop():
    route = next(r for r in ROUTES if r["id"] == "W1")
    path = OrderedPathTracker(route["waypoints"],CONFIG["routes"])
    state = RobotState(x=-1.,yaw=np.pi)
    for _ in range(50):
        path.advance(state.x,state.y)
    assert path.cursor == 0. and not path.gates_complete
    assert not task_succeeded(tracking(state,path),state,path,CONFIG)


@pytest.mark.parametrize("route",ROUTES,ids=[r["id"] for r in ROUTES])
@pytest.mark.parametrize("scale",[1.,.7])
def test_factory_pi_follows_reference_kinematically(route,scale):
    # Tests steering/reference logic only: no Gazebo, caster, slip or motor lag.
    path = OrderedPathTracker(route["waypoints"],CONFIG["routes"])
    state = RobotState()
    _,deadline = route_budget(CONFIG,path.total_length)
    for _ in range(int(deadline/.1)):
        path.advance(state.x,state.y)
        current = tracking(state,path)
        if task_succeeded(current,state,path,CONFIG):
            break
        assert path.corridor_distance(state.x,state.y) < .6
        speed,yaw = route_command(state,path,current,CONFIG)
        state.x += speed*scale*np.cos(state.yaw+yaw*scale*.05)*.1
        state.y += speed*scale*np.sin(state.yaw+yaw*scale*.05)*.1
        state.yaw = wrap_angle(state.yaw+yaw*scale*.1)
    assert task_succeeded(tracking(state,path),state,path,CONFIG), (
        route["id"],scale,state.x,state.y,state.yaw,path.cursor)
    assert path.gates_complete
