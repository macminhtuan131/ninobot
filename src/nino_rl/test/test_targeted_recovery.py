"""Guard evidence recovery, synchronized feedback, and route isolation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from threading import Lock

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).parents[3]
sys.path[:0] = [str(ROOT / "src/nino_rl"), str(ROOT / "src/nino_rl/scripts")]
from encoder_history_transport import patch_interface
from rough_n1_anticipation_profile import configuration, route_controller_config, anticipated_command
from nino_rl.assisted_odometry import ImuEncoderOdometry
from nino_rl.core import RobotState, make_observation


def frozen(name):
    spec = importlib.util.spec_from_file_location("reference_" + name,
        ROOT / "rl_runs/rough_wall_recovery_v16/python/nino_rl" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source():
    return yaml.safe_load((ROOT / "rl_runs/rough_trial8_validation_v1/correction.yaml").read_text())


def test_encoder_history_avoids_false_fusion_staleness_without_extrapolation():
    # A paused action ends at .100s. IMU's last sample is .080s.
    # Deliver the encoder chunk first: a depth-one queue keeps only .100s,
    # which cannot be interpolated yet; retaining .060-.100 lets fusion reach
    # the valid .080 boundary with exactly the same measurements/math.
    def delivery(depth):
        estimator = ImuEncoderOdometry({})
        estimator.add_imu(.038, 0., 0.)
        estimator.add_imu(.058, 0., 0.)
        estimator.add_joint(.058, .058, .058)
        samples = np.arange(.060, .101, .002)
        for t in samples[-depth:]:
            estimator.add_joint(float(t), float(t), float(t))
        estimator.add_imu(.080, 0., 0.)
        return estimator
    lost, retained = delivery(1), delivery(100)
    assert .100-lost.stamp > .04
    assert .100-retained.stamp <= .04
    assert retained.stamp <= .080+1e-9  # no extrapolated/fabricated timestamp


def test_transport_patch_preserves_the_motion_and_clock_checks():
    code = (ROOT / "rl_runs/course_targeted_corrections_v1/flat/python/nino_rl/ros_interface.py").read_text()
    patched = patch_interface(code)
    start = code.index("    def wait_for_motion_state(")
    end = code.index("    def wait_for_v2_controller(", start)
    assert code[start:end] in patched
    assert 'depth=100' in patched and 'self._joint_callback, JOINT_QOS)' in patched
    with pytest.raises(ValueError):
        patch_interface(patched)


def test_fresh_raw_sensors_still_do_not_allow_stale_fused_pose(monkeypatch):
    import nino_rl.ros_interface as transport
    state = RobotState(odom_stamp_s=1.,ground_truth_stamp_s=1.,joint_stamp_s=1.,imu_stamp_s=1.)
    ros = SimpleNamespace(_lock=Lock(),_state=state,_assisted_odometry=SimpleNamespace(stamp=.958),
                          _assisted_error=None)
    ticks = iter([0.,1.])
    monkeypatch.setattr(transport,"monotonic",lambda:next(ticks))
    with pytest.raises(RuntimeError,match="assisted_odom"):
        transport.RosRobotInterface.wait_for_motion_state(ros,1.,timeout=.1,max_lag=.04)


@pytest.mark.parametrize("module_name", ["rough_n1_anticipation_profile", "rough_n1_heading_braking_profile"])
def test_n1_changes_preserve_geometry_scoring_and_e1_s1_commands(module_name):
    import importlib
    profile = importlib.import_module(module_name)
    original = source()
    candidate = profile.configuration(original)
    for key in original:
        if key not in ("routes", "training_reward_scale"):
            assert candidate[key] == original[key]
    for key in ("definitions", "gate_radius_m", "max_yaw_rate_rad_s", "stop_align_route_ids"):
        assert candidate["routes"][key] == original["routes"][key]
    routes, recovery = frozen("routes"), frozen("rough_stall_recovery")
    for route_id in ("E1", "S1"):
        route = next(r for r in original["routes"]["definitions"] if r["id"] == route_id)
        path = routes.OrderedPathTracker(route["waypoints"], original["routes"])
        for x,y,yaw in ((1.,.02,.03),(2.4,0.,-.2),(2.5,-.2,-.8)):
            state = RobotState(x=x,y=y,yaw=yaw)
            tracking = make_observation(state,path,original["path"]["lookahead_m"],np.zeros(2))[1]
            expected = routes.route_command(state,path,tracking,recovery.route_controller_config(original,route_id))
            actual = profile.anticipated_command(state,path,tracking,profile.route_controller_config(candidate,route_id),routes.route_command)
            assert actual == expected


def test_n1_brakes_before_turn_and_never_uses_old_fast_high_angle_floor():
    original = source()
    cfg = route_controller_config(configuration(original), "N1")
    routes = frozen("routes")
    route = next(r for r in original["routes"]["definitions"] if r["id"] == "N1")
    path = routes.OrderedPathTracker(route["waypoints"], original["routes"])
    commands = []
    for x in (1.4,1.8,2.1,2.3,2.45):
        tracking = SimpleNamespace(path_s=x,distance_remaining=8.7-x,endpoint_distance=6.2,heading_error=0.)
        state = RobotState(x=x,y=0.,yaw=0.)
        commands.append(anticipated_command(state,path,tracking,cfg,routes.route_command))
    assert commands[1][0] < .3  # braking begins before the pursuit turn
    assert commands[-1][0] <= .06
    assert 0 < commands[-1][1] <= .45
    assert all(0 < v <= .4 and abs(w) <= .45 for v,w in commands)


def test_heading_braking_uses_measured_overspeed_without_weakening_yaw():
    import rough_n1_heading_braking_profile as profile
    original = source()
    config = profile.route_controller_config(profile.configuration(original),"N1")
    routes = frozen("routes")
    route = next(r for r in original["routes"]["definitions"] if r["id"] == "N1")
    path = routes.OrderedPathTracker(route["waypoints"],original["routes"])
    tracking = SimpleNamespace(path_s=2.3,distance_remaining=6.4,endpoint_distance=6.2,heading_error=0.)
    state = RobotState(x=2.3,y=.02,yaw=.1,linear_velocity=.03)
    slow = profile.anticipated_command(state,path,tracking,config,routes.route_command)
    state.linear_velocity=.20
    fast = profile.anticipated_command(state,path,tracking,config,routes.route_command)
    assert 0 < fast[0] < slow[0] < .1
    assert fast[1] == slow[1] and 0 < fast[1] <= .45
