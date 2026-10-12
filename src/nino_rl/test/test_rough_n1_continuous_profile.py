"""Check unchanged E1/S1 steering and curvature-limited N1 approach."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import sys
from types import SimpleNamespace

import numpy as np
import yaml

ROOT = Path(__file__).parents[3]
sys.path[:0] = [str(ROOT / "src/nino_rl"), str(ROOT / "src/nino_rl/scripts")]
from rough_n1_continuous_profile import configuration, route_controller_config
from nino_rl.core import make_observation
route_spec = importlib.util.spec_from_file_location("frozen_rough_routes", ROOT / "rl_runs/rough_wall_recovery_v16/python/nino_rl/routes.py")
frozen_routes = importlib.util.module_from_spec(route_spec)
route_spec.loader.exec_module(frozen_routes)
OrderedPathTracker, route_command = frozen_routes.OrderedPathTracker, frozen_routes.route_command


def source():
    return yaml.safe_load((ROOT / "rl_runs/rough_trial8_validation_v1/correction.yaml").read_text())


def test_geometry_scoring_and_s1_alignment_preserved():
    original = source()
    candidate = configuration(original)
    assert candidate["routes"]["stop_align_route_ids"] == ["S1"]
    for key in ("definitions", "gate_radius_m", "gate_spacing_m", "projection_forward_m", "max_yaw_rate_rad_s"):
        assert candidate["routes"][key] == original["routes"][key]
    for key in ("reward_v2", "odometry_assistance", "rough_stall_recovery", "rough_curriculum", "drive_controller"):
        assert candidate[key] == original[key]
    assert route_controller_config(candidate, "N1")["routes"]["steering_lookahead_m"] == .2
    assert route_controller_config(candidate, "N1")["routes"]["curvature_speed_limit"]


def test_original_e1_and_s1_commands_preserved():
    original = source()
    candidate = configuration(original)
    frozen = ROOT / "rl_runs/rough_wall_recovery_v16/python/nino_rl/rough_stall_recovery.py"
    spec = importlib.util.spec_from_file_location("original_recovery", frozen)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    from nino_rl.core import RobotState
    for route_id in ("E1", "S1"):
        route = next(r for r in original["routes"]["definitions"] if r["id"] == route_id)
        path = OrderedPathTracker(route["waypoints"], original["routes"])
        for x,y,yaw in ((1.,.02,.03), (2.4,0.,-.2), (2.5,-.2,-.8)):
            state = RobotState(x=x,y=y,yaw=yaw)
            tracking = make_observation(state,path,original["path"]["lookahead_m"],np.zeros(2))[1]
            expected = route_command(state,path,tracking,old.route_controller_config(original,route_id))
            actual = route_command(state,path,tracking,route_controller_config(candidate,route_id))
            assert np.allclose(actual,expected,rtol=0,atol=1e-12)


def test_n1_preserves_pursuit_curvature_when_yaw_limited():
    candidate = configuration(source())
    config = route_controller_config(candidate,"N1")
    state = SimpleNamespace(x=0.,y=0.,yaw=0.)
    path = SimpleNamespace(point_at=lambda _:np.array([.1,.1]))
    tracking = SimpleNamespace(path_s=0.,distance_remaining=5.,endpoint_distance=5.,heading_error=0.)
    linear,yaw = route_command(state,path,tracking,config)
    assert 0 < linear < .18
    assert np.isclose(yaw/linear,10.)
    assert abs(yaw) <= config["routes"]["max_yaw_rate_rad_s"]
