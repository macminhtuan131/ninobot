"""The rough approach must meet a genuinely flat, cable-bearing road."""

import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import torch
import yaml
from gymnasium import spaces

from nino_rl.model_transfer import initialize_actor
from nino_rl.policies import policy_spec
from nino_rl.ros_env import NinoGazeboEnv
from nino_rl.training_contract import training_contract, validate_resume


ROOT = Path(__file__).parents[2]


def test_old_actor_transfer_preserves_new_task_value_function():
    config = yaml.safe_load((ROOT / "nino_rl/config/combined_course.yaml").read_text())
    policy_class, kwargs = policy_spec(config)
    observation_space = spaces.Box(-1.0, 1.0, shape=(300,), dtype=np.float32)
    action_space = spaces.Box(-1.0, 1.0, shape=(3,), dtype=np.float32)
    torch.manual_seed(1)
    source = policy_class(observation_space, action_space, lambda _: 3e-5, **kwargs)
    torch.manual_seed(2)
    target = policy_class(observation_space, action_space, lambda _: 3e-5, **kwargs)
    observation = torch.randn(4, 300)
    critic_before = target.predict_values(observation).detach().clone()
    keys = initialize_actor(type("Model", (), {"policy": target})(),
                            type("Model", (), {"policy": source})())

    assert len(keys) == 13
    assert torch.equal(target.get_distribution(observation).distribution.mean,
                       source.get_distribution(observation).distribution.mean)
    assert torch.equal(target.log_std, source.log_std)
    assert torch.equal(target.predict_values(observation), critic_before)
    assert not torch.equal(target.predict_values(observation),
                           source.predict_values(observation))


def test_combined_world_has_one_contact_surface_and_level_flat_join():
    world = ET.parse(ROOT / "nino_description/worlds/combined_hall.sdf")
    metadata = json.loads((ROOT / "nino_description/worlds/combined_hall.json").read_text())
    rough = world.find(".//model[@name='rough_approach_ground']")
    uri = "model://nino_description/terrains/combined_rough_ground.stl"
    assert rough.findtext(".//collision/geometry/mesh/uri") == uri
    assert rough.findtext(".//visual/geometry/mesh/uri") == uri
    assert rough.findtext(".//collision/pose") == rough.findtext(".//visual/pose")
    assert world.find(".//collision[@name='floor_collision']") is None
    flat = world.find(".//collision[@name='flat_cable_floor_collision']")
    center = float(flat.findtext("pose").split()[0])
    length = float(flat.findtext("geometry/box/size").split()[0])
    assert center - length / 2 == pytest.approx(metadata["rough_x_m"][1])
    assert metadata["flat_join_height_m"] == 0.0
    assert metadata["height_range_m"][0] < -0.1
    assert metadata["height_range_m"][1] > 0.1
    assert metadata["maximum_surface_grade"] < 0.60
    assert len(metadata["potholes"]) == 9
    assert all(-1.0 <= pot["y_m"] <= 1.0 for pot in metadata["potholes"])
    assert min(pot["additional_depth_m"] for pot in metadata["potholes"]) <= 0.025
    assert max(pot["additional_depth_m"] for pot in metadata["potholes"]) >= 0.075
    assert len(metadata["wheel_potholes"]) == 4
    assert metadata["mesh_spacing_m"][0] <= 0.0201
    assert metadata["mesh_spacing_m"][1] <= 0.016
    cable_x = [float(c.findtext("pose").split()[0])
               for c in world.findall(".//model[@name='cable_bumps']/link/collision")]
    assert min(cable_x) > metadata["rough_x_m"][1]
    assert set(cable_x) == {7.2, 8.0, 9.0, 10.0, 11.0, 12.0}
    assert max(cable_x) < metadata["goal_xy_m"][0]
    config = yaml.safe_load((ROOT / "nino_rl/config/combined_course.yaml").read_text())
    static_specs = sorted((float(c.findtext("pose").split()[0]),
                           float(c.findtext("geometry/cylinder/radius")))
                          for c in world.findall(".//model[@name='cable_bumps']/link/collision"))
    episode_specs = sorted((item["x"], item["radius"])
                           for item in config["course_cable_randomization"]["cables"])
    assert static_specs == episode_specs
    mesh = (ROOT / "nino_description/terrains/combined_rough_ground.stl").read_bytes()
    facets = struct.unpack_from("<I", mesh, 80)[0]
    assert len(mesh) == 84 + 50 * facets


def test_small_holes_have_real_center_relief_on_wheel_tracks(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "nino_description/scripts"))
    from generate_combined_world import WHEEL_POTHOLES, combined_surface

    x, y, surface = combined_surface()
    for wheel, cx, cy, radius_x, radius_y, depth in WHEEL_POTHOLES:
        centerline = surface[np.argmin(abs(y - cy))]
        height = lambda station: np.interp(station, x, centerline)
        relief = (height(cx - radius_x) + height(cx + radius_x)) / 2 - height(cx)
        assert relief > depth / 2, (wheel, cx, relief)
        assert radius_x > (0.0625 if wheel == "drive" else 0.016)
        assert radius_y > (0.0625 if wheel == "drive" else 0.016)


def test_shifted_middle_pothole_has_a_gentler_uphill_exit(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "nino_description/scripts"))
    from generate_combined_world import POTHOLES, combined_surface

    x, y, surface = combined_surface()
    uphill = np.gradient(surface, x[1] - x[0], axis=1)
    bowl_x, bowl_y = POTHOLES[1][:2]
    bowl_band = (y >= bowl_y - 0.20) & (y <= bowl_y + 0.20)
    exit_band = (x >= bowl_x) & (x <= 4.5)
    assert uphill[np.ix_(bowl_band, exit_band)].max() < 0.35
    assert surface[np.argmin(abs(y - bowl_y)), np.argmin(abs(x - bowl_x))] < -0.12


def test_fixed_challenge_centers_follow_the_relocated_potholes():
    metadata = json.loads((ROOT / "nino_description/worlds/combined_hall.json").read_text())
    expected = [(p["x_m"], p["y_m"]) for p in metadata["potholes"][:3]]
    assert expected == [(1.8, 0.30), (3.55, 0.0), (5.45, -0.10)]
    config = yaml.safe_load((ROOT / "nino_rl/config/combined_course.yaml").read_text())
    actual = [(r["x"], r["y"]) for r in config["fixed_terrain_challenges"]
              if r["kind"] == "pothole"]
    assert actual == expected


def test_extra_potholes_lower_the_actual_combined_contact_mesh(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "nino_description/scripts"))
    import generate_combined_world as terrain

    all_potholes = terrain.POTHOLES
    x, y, with_bowls = terrain.combined_surface()
    monkeypatch.setattr(terrain, "POTHOLES", all_potholes[:3])
    _, _, without_bowls = terrain.combined_surface()
    for cx, cy, _, _, depth in all_potholes[3:]:
        row, column = np.argmin(abs(y - cy)), np.argmin(abs(x - cx))
        assert without_bowls[row, column] - with_bowls[row, column] == pytest.approx(
            depth, abs=0.003
        )


def test_combined_optuna_preserves_transfer_shape_until_training_from_scratch(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "nino_rl/scripts"))
    from tune_combined_optuna import sample_config

    class FirstSuggestion:
        def suggest_float(self, name, low, high, **kwargs):
            return low

        def suggest_categorical(self, name, choices):
            return choices[0]

    base = yaml.safe_load((ROOT / "nino_rl/config/combined_course.yaml").read_text())
    warm = sample_config(FirstSuggestion(), base, from_scratch=False)
    cold = sample_config(FirstSuggestion(), base, from_scratch=True)
    for key in ("actor_layers", "critic_layers", "history_features", "activation",
                "initial_action_std", "initial_speed_scale"):
        assert warm["ppo"][key] == base["ppo"][key]
    assert cold["ppo"]["actor_layers"] != base["ppo"]["actor_layers"]
    assert warm["reward_v2"]["progress_weight"] != base["reward_v2"]["progress_weight"]
    assert warm["navigation"] == base["navigation"]


def test_combined_course_counts_real_hollows_and_rejects_old_resume():
    config = yaml.safe_load((ROOT / "nino_rl/config/combined_course.yaml").read_text())
    assert config["navigation"]["goal_pose"][:2] == [13.0, 0.0]
    assert config["action_mode"] == "wheel_torque"
    assert config["terrain_curriculum"]["enabled"] is False
    assert config["adaptive_terrain"]["enabled"] is True
    assert config["adaptive_terrain"]["initial_features"] == 1
    assert config["adaptive_terrain"]["progress_on_success"] is True
    assert config["adaptive_terrain"]["max_features"] == 6
    assert config["adaptive_terrain"]["lateral_spawn_range_m"] == [-0.5, 0.5]
    assert config["reward_pose_source"] == "ground_truth"
    env = object.__new__(NinoGazeboEnv)
    env.config = config
    tracker = env._make_challenge_tracker([], [])
    assert tracker.total == len(config["fixed_terrain_challenges"]) == 5
    assert sum(r.kind == "pothole" for r in tracker.regions) == 3
    env.np_random = np.random.default_rng(42)
    cables = env._random_course_cables()
    cable_specs = config["course_cable_randomization"]["cables"]
    assert [(x, radius) for x, radius, _ in cables] == [
        (item["x"], item["radius"]) for item in cable_specs
    ]
    assert all(-np.pi / 6 <= angle <= np.pi / 6 for _, _, angle in cables)
    assert len({round(angle, 6) for _, _, angle in cables}) == len(cables)
    assert env._make_challenge_tracker(cables, []).total == 11
    env.adaptive_terrain_enabled = True
    env.terrain_feature_count = 6
    features = env._adaptive_terrain_features()
    assert len(features) == 6
    assert {kind for kind, *_ in features} == {"pothole", "bump", "cable", "groove"}
    assert all(7.1 <= x <= 12.2 and -0.5 <= y <= 0.5 for _, x, y, _ in features)
    assert any(abs(y) > config["adaptive_terrain"]["wheel_separation_m"] / 2
               for _, _, y, _ in features)
    old = yaml.safe_load((ROOT / "nino_rl/config/ppo.yaml").read_text())
    old_model = type("OldModel", (), {"nino_training_contract": training_contract(old)})()
    with pytest.raises(ValueError, match="Checkpoint reward/policy/PPO contract differs"):
        validate_resume(old_model, config)
