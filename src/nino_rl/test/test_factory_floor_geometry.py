"""Protect physical hole geometry and avoid phantom floor collisions."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/nino_description/scripts"))
from generate_factory_floor_lab import (SPEC, VARIANTS, floor_tiles, generate,
                                       patch_surface, sample_features)
sys.path.insert(0, str(ROOT / "src/nino_rl"))
from nino_rl.core import load_config


def test_floor_has_no_collision_under_any_depression(tmp_path):
    metadata = generate("mixed", root=tmp_path)
    assert metadata["floor_tiles_xy_m"] == []
    assert metadata["terrain_mesh"]["bounds_xy_m"] == [-2., 8., -3.5, 3.5]
    xml = ET.parse(tmp_path / "worlds/factory_floor_mixed.sdf")
    structure = xml.find("world/model[@name='enclosed_hall']/link")
    assert structure.find("collision[@name='flat_cable_floor_collision']") is None
    floor = xml.find("world/model[@name='factory_contact_floor']")
    assert len(floor.findall("link/collision/geometry/mesh")) == 1
    assert floor.findall("link/collision/geometry/box") == []
    assert floor.find("link[@name='level_apron_visuals']/collision") is None
    assert len(metadata["display_items"]) == 2
    assert not metadata["thresholds"]


def test_mesh_matches_visual_and_real_negative_height(tmp_path):
    metadata = generate("mixed", root=tmp_path)
    xml = ET.parse(tmp_path / "worlds/factory_floor_mixed.sdf")
    record = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    for item in metadata["depressions"]:
        link = xml.find("world/model[@name='factory_contact_floor']/link[@name='terrain']")
        assert link.find("collision/geometry/mesh/uri").text == link.find("visual/geometry/mesh/uri").text
        assert link.find("collision/pose").text == link.find("visual/pose").text
        path = tmp_path / "terrains/factory_floor_lab" / item["mesh"]
        with path.open("rb") as f:
            f.seek(80)
            count = int(np.frombuffer(f.read(4), dtype="<u4")[0])
            triangles = np.frombuffer(f.read(), dtype=record)
        assert len(triangles) == count
        assert np.all(triangles["normal"][:, 2] > 0)
        z = triangles["vertices"][:, :, 2]
        assert z.max() == 0
        assert abs(z.min() + max(r["depth_m"] for r in metadata["depressions"])) < .0001
        pose = [float(v) for v in link.find("collision/pose").text.split()]
        vertices = triangles["vertices"].reshape(-1, 3)
        bounds = metadata["terrain_mesh"]["bounds_xy_m"]
        assert np.allclose([vertices[:, 0].min() + pose[0], vertices[:, 0].max() + pose[0],
                            vertices[:, 1].min() + pose[1], vertices[:, 1].max() + pose[1]], bounds, atol=1e-6)
        # Complete shared grid: each cell has two upward-facing triangles;
        # projected triangle area covers the entire floor exactly once.
        cross = np.cross(triangles["vertices"][:, 1]-triangles["vertices"][:, 0],
                         triangles["vertices"][:, 2]-triangles["vertices"][:, 0])
        assert np.isclose(cross[:, 2].sum()/2, 70., atol=1e-5)
        assert len(triangles) == metadata["terrain_mesh"]["triangles"]
        world_vertices = vertices + np.array(pose[:3])
        outside = np.ones(len(world_vertices), dtype=bool)
        for feature in metadata["depressions"]:
            a,b,c,d = feature["bounds_xy_m"]
            outside &= ((world_vertices[:,0] < a) | (world_vertices[:,0] > b)
                        | (world_vertices[:,1] < c) | (world_vertices[:,1] > d))
        assert np.all(world_vertices[outside, 2] == 0)
        center = np.hypot(world_vertices[:, 0]-item["x_m"],world_vertices[:,1]-item["y_m"]) < .005
        assert np.any(center)
        assert abs(world_vertices[center,2].min()+item["depth_m"]) < .0001
        assert all(np.all(world_vertices[np.isclose(world_vertices[:, axis], edge), 2] == 0)
                   for axis, edges in ((0, bounds[:2]), (1, bounds[2:])) for edge in edges)
        x, y, heights = patch_surface(item, .005)
        assert all(np.all(e == 0) for e in (heights[0], heights[-1], heights[:, 0], heights[:, -1]))
        assert np.diff(x).max() <= .005 + 1e-10
        assert np.diff(y).max() <= .005 + 1e-10


def test_isolated_variants_and_seeded_physical_layouts(tmp_path):
    spec = yaml.safe_load(SPEC.read_text())
    for name in VARIANTS:
        metadata = generate(name, root=tmp_path)
        if name not in ("mixed", "clear"):
            assert len(metadata["depressions"] + metadata["cables"] + metadata["thresholds"]) == 1
        if name == "clear":
            assert not metadata["depressions"] + metadata["cables"] + metadata["thresholds"]
    a = sample_features(spec, "pothole", seed=75000)
    assert a == sample_features(spec, "pothole", seed=75000)
    assert a != sample_features(spec, "pothole", seed=75001)
    for seed in range(75000, 75010):
        item = sample_features(spec, "groove", seed=seed)[0][0]
        x, y, z = patch_surface(item, .005)
        assert z.min() < 0 and z.max() == 0
        floor_tiles((-2., 8., -2., 2.), [(x[0], x[-1], y[0], y[-1])])


def test_pi_config_preserves_static_geometry_and_world_bounds():
    config = load_config(ROOT / "src/nino_rl/config/factory_floor_pi_check.yaml")
    assert config["world_name"] == "factory_floor_lab"
    for key in ("adaptive_terrain", "terrain_curriculum", "flat_curriculum", "course_cable_randomization"):
        assert config[key]["enabled"] is False
    assert config["policy_v2"]["simulation_physics_step_seconds"] == .001
    assert config["policy_v2"]["require_terrain_preview"] is False
    assert config["odometry_assistance"]["corridor_lidar"]["bounds_xy_m"] == [-2., 8., -3.5, 3.5]
    assert config["navigation"]["goal_pose"] == [6.45, 0., 0.]


def test_restored_corridor_and_adaptive_progression(tmp_path):
    from nino_rl.flat_curriculum import FlatCourseCurriculum
    from nino_rl.carved_floor import floor_model, negative_items, grouped_bounds, level_tiles
    metadata = generate("mixed", root=tmp_path)
    assert [r["x_m"] for r in metadata["cables"]] == [.65,1.45,2.45,3.45,4.45,5.45]
    assert all(r["length_m"] == 4 for r in metadata["cables"])
    assert len(metadata["depressions"]) == 5
    assert {r["kind"] for r in metadata["depressions"]} == {
        "round_bowl", "flat_bottom_bowl", "angled_trough", "groove"}
    config = load_config(ROOT / "src/nino_rl/config/factory_floor_curriculum.yaml")
    curriculum = FlatCourseCurriculum(config["flat_curriculum"], config["course_cable_randomization"]["cables"],6)
    for level in range(6):
        assert curriculum.stage["adaptive_features"] == level+1
        assert len(curriculum.sample_cables(np.random.default_rng(level),level)) == 6
        for _ in range(30):
            curriculum.record(True,level)
    assert curriculum.stage_index == 5
    assert config["reward_pose_source"] == "ground_truth"
    # Even overlapping holes and a separate groove use ONE continuous floor.
    features = [("pothole",2.9,.17,.3),("pothole",3.1,.10,.3),("groove",4.,0.,.05)]
    sdf,paths = floor_model(features,config["adaptive_terrain"],tmp_path / "runtime")
    xml = ET.fromstring(sdf)
    assert len(paths) == 1
    assert xml.find("model").get("name") == "factory_contact_floor"
    assert len(xml.findall("model/link/collision")) == 1
    assert xml.find("model/link/collision/geometry/box") is None
    for path in paths:
        assert Path(path).is_file()
    items = negative_items(features,config["adaptive_terrain"])
    groups = grouped_bounds(items,.005)
    tiles = level_tiles((-2.,8.,-2.,2.),groups)
    assert abs(sum((r[1]-r[0])*(r[3]-r[2]) for r in tiles+groups)-40) < 1e-8
    # Reset with no items still creates a complete floor (never an empty model).
    clear,paths = floor_model([],config["adaptive_terrain"],tmp_path / "runtime")
    assert len(paths) == 1
    with Path(paths[0]).open("rb") as stream:
        stream.seek(80)
        assert int(np.frombuffer(stream.read(4), dtype="<u4")[0]) == 2
    assert len(ET.fromstring(clear).findall("model/link/collision")) == 1


def test_four_halls_remain_connected_and_supported_after_reset(tmp_path):
    from nino_rl.carved_floor import floor_model
    metadata = generate("clear", root=tmp_path)
    config = load_config(ROOT / "src/nino_rl/config/factory_floor_curriculum.yaml")
    halls = metadata["goal_halls"]
    assert halls == config["adaptive_terrain"]["goal_halls"]
    assert {h["direction"] for h in halls} == {"north", "south", "east", "west"}
    assert {h["id"] for h in halls} == {"N1", "S1", "E1", "W1"}
    bounds = metadata["terrain_mesh"]["bounds_xy_m"]
    assert bounds == config["adaptive_terrain"]["floor_bounds_xy_m"]
    assert bounds == config["odometry_assistance"]["corridor_lidar"]["bounds_xy_m"]
    xml = ET.parse(tmp_path / "worlds/factory_floor_clear.sdf")
    markers = xml.findall("world/model[@name='task_markers']/link/visual")
    assert {m.get("name") for m in markers} == {"start", "goal_N1", "goal_S1", "goal_E1", "goal_W1"}
    assert xml.find("world/model[@name='task_markers']/link/collision") is None
    structure = xml.find("world/model[@name='enclosed_hall']/link")
    # Only the four outer walls: no partitions blocking entry into a hall.
    assert len(structure.findall("collision")) == 4
    for wall, coordinate in (("left", 3.6), ("right", -3.6)):
        pose = structure.find(f"collision[@name='{wall}_wall_collision']/pose")
        assert float(pose.text.split()[1]) == coordinate
    sdf, paths = floor_model([], config["adaptive_terrain"], tmp_path / "runtime")
    runtime = ET.fromstring(sdf)
    assert len(runtime.findall("model/link[@name='goal_hall_visuals']/visual")) == 4
    assert runtime.find("model/link[@name='goal_hall_visuals']/collision") is None
    assert len(runtime.findall("model/link/collision")) == 1
    record = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    with Path(paths[0]).open("rb") as stream:
        stream.seek(84)
        vertices = np.frombuffer(stream.read(), dtype=record)["vertices"].reshape(-1, 3)
    # Runtime replacement is a level rectangle covering every goal hall.
    assert np.all(vertices[:, 2] == 0)
    assert np.allclose([np.ptp(vertices[:, 0]), np.ptp(vertices[:, 1])], [10., 7.])


def test_rough_ground_template_and_cables_really_rest_on_mesh(tmp_path):
    from generate_factory_floor_lab import depression_surface
    metadata = generate("mixed", root=tmp_path)
    xml = ET.parse(tmp_path / "worlds/factory_floor_mixed.sdf")
    ground = xml.find("world/model[@name='factory_contact_floor']/link[@name='terrain']")
    original = ET.parse(ROOT / "src/nino_description/worlds/combined_rough_section.sdf")
    rough_visual = original.find("world/model[@name='rough_approach_ground']/link/visual")
    assert ET.tostring(ground.find("visual/material")) == ET.tostring(rough_visual.find("material"))
    assert xml.find("world/model[@name='rough_approach_ground']") is None
    assert xml.find("world/model[@name='rough_goal_markers']") is None
    # Sample the bottom contact line of every full-width and short cable.
    for cable in metadata["cables"] + [r for r in metadata["display_items"] if r["kind"] == "cable"]:
        angle = np.deg2rad(cable.get("angle_deg", 0.))
        distance = np.linspace(-cable["length_m"]/2,cable["length_m"]/2,401)
        x = cable["x_m"]-distance*np.sin(angle)
        y = cable["y_m"]+distance*np.cos(angle)
        assert all(np.all(depression_surface(pit,x,y) == 0) for pit in metadata["depressions"])
    # All sculpted features occupy the five gaps, never a cable footprint.
    gaps = set()
    for pit in metadata["depressions"]:
        gap = np.searchsorted([r["x_m"] for r in metadata["cables"]],pit["x_m"])-1
        gaps.add(int(gap))
        assert metadata["cables"][gap]["x_m"] < pit["bounds_xy_m"][0]
        assert pit["bounds_xy_m"][1] < metadata["cables"][gap+1]["x_m"]
    assert gaps == set(range(5))


def test_continuous_grid_refines_depressions_without_seams():
    from nino_rl.carved_floor import continuous_axes, carve_on_grid
    bounds = (-2., 8., -2., 2.)
    patches = [(2.59, 3.21, -.09, .43)]
    x, y = continuous_axes(bounds, patches, .005, .04)
    for axis, lower, upper in ((x, 2.59, 3.21), (y, -.09, .43)):
        assert np.all(np.diff(axis) > 0)
        fine = axis[(axis >= lower) & (axis <= upper)]
        assert np.diff(fine).max() <= .005 + 1e-10
        assert np.diff(axis).max() <= .04 + 1e-10
    z = carve_on_grid([dict(kind="pothole", x=2.9, y=.17, rx=.3, ry=.252, depth=.018)], x, y)
    assert -.018 <= z.min() < -.0179 and z.max() == 0
    assert all(np.all(edge == 0) for edge in (z[0], z[-1], z[:, 0], z[:, -1]))


def test_runtime_flat_bottom_matches_rough_carving():
    from nino_rl.carved_floor import negative_items, carve_on_grid
    from generate_rough_section import feature_relief
    config = dict(pothole_shape="flat_bottom_bowl",pothole_depth_m=.018)
    items = negative_items([("pothole",2.9,.17,.3)],config)
    x,y = np.linspace(2.5,3.3,161),np.linspace(-.2,.5,141)
    runtime = carve_on_grid(items,x,y)
    rough = feature_relief(*np.meshgrid(x,y),dict(kind="flat_bottom_bowl",x_m=2.9,y_m=.17,
        radius_x_m=.3,radius_y_m=.252,height_m=-.018,angle_deg=0.))
    assert np.allclose(runtime,rough,atol=1e-14)
    assert runtime.min() == -.018 and runtime.max() == 0
    with pytest.raises(ValueError,match="Pothole shape"):
        negative_items([("pothole",2.9,.17,.3)],dict(pothole_shape="mound"))


def test_random_potholes_clear_actual_angled_cables_and_cover_all_gaps():
    from nino_rl.carved_floor import sample_pothole_in_cable_gap
    config = load_config(ROOT / "src/nino_rl/config/factory_floor_curriculum.yaml")
    specs = config["course_cable_randomization"]["cables"]
    radius = config["adaptive_terrain"]["pothole_radius_m"]
    clearance = config["adaptive_terrain"]["pothole_cable_clearance_m"]
    theta = np.linspace(0, 2*np.pi, 721)
    gaps, positions = set(), []
    for seed in range(500):
        rng = np.random.default_rng(seed)
        angles = rng.uniform(-np.pi/6, np.pi/6, len(specs))
        # Also exercise the two opposing extreme angle layouts.
        if seed < 2:
            angles = np.array([(-1)**(i+seed)*np.pi/6 for i in range(len(specs))])
        cables = [(r["x"], r["radius"], a) for r, a in zip(specs, angles)]
        x, y = sample_pothole_in_cable_gap(rng, cables, radius, [.55, 5.65], [-.5, .5])
        assert .55 <= x <= 5.65 and -.5 <= y <= .5
        # Independent boundary check against the physical cylinder axis:
        # every point of the ellipse clears every cable, not just its center.
        px, py = x+radius*np.cos(theta), y+.84*radius*np.sin(theta)
        for cx, cr, a in cables:
            distances = np.abs((px-cx)*np.cos(a) + py*np.sin(a)) - cr
            assert distances.min() >= clearance - 1e-10
        intersections = np.array([cx-np.tan(a)*y for cx, _, a in cables])
        gap = int(np.searchsorted(intersections, x) - 1)
        assert 0 <= gap < 5
        gaps.add(gap)
        positions.append((x, y))
    assert gaps == set(range(5))
    assert len(set(positions)) == 500
    assert min(y for _, y in positions) < -.45
    assert max(y for _, y in positions) > .45


def test_gap_sampling_is_seeded_and_rejects_unusable_layouts():
    from nino_rl.carved_floor import sample_pothole_in_cable_gap
    cables = [(.65, .011, 0), (1.45, .012, 0)]
    def sample(seed):
        rng = np.random.default_rng(seed)
        return [sample_pothole_in_cable_gap(rng, cables, .3, [.55, 5.65], [-.5, .5])
                for _ in range(10)]
    assert sample(75000) == sample(75000)
    assert sample(75000) != sample(75001)
    with pytest.raises(ValueError, match="No sampled cable gap fits"):
        sample_pothole_in_cable_gap(np.random.default_rng(0), cables, 1., [.55, 5.65], [-.5, .5])
    with pytest.raises(ValueError, match="at least two ordered episode cables"):
        sample_pothole_in_cable_gap(np.random.default_rng(0), cables[:1], .3, [.55, 5.65], [-.5, .5])


def test_episode_sampler_uses_cable_gaps_for_selected_potholes():
    # Exercise the actual environment method without opening ROS or Gazebo.
    import ast
    from types import SimpleNamespace
    from nino_rl.carved_floor import sample_pothole_in_cable_gap
    from nino_rl.flat_curriculum import FlatCourseCurriculum
    source = ROOT / "src/nino_rl/nino_rl/ros_env.py"
    cls = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_adaptive_terrain_features")
    namespace = dict(np=np, sample_pothole_in_cable_gap=sample_pothole_in_cable_gap)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
    generate_features = namespace[method.name]
    config = load_config(ROOT / "src/nino_rl/config/factory_floor_curriculum.yaml")
    curriculum = FlatCourseCurriculum(config["flat_curriculum"], config["course_cable_randomization"]["cables"], 6)
    env = SimpleNamespace(config=config, adaptive_terrain_enabled=True, terrain_feature_count=6)
    for seed in range(30):
        env.np_random = np.random.default_rng(seed)
        cables = curriculum.sample_cables(env.np_random, 5)
        features = generate_features(env, cables)
        assert len(features) == 6
        assert {f[0] for f in features} == {"pothole", "groove", "bump", "cable"}
        for kind, x, y, size in features:
            if kind != "pothole":
                continue
            for cx, cr, a in cables:
                support = size*np.sqrt(np.cos(a)**2 + (.84*np.sin(a))**2)
                distance = abs((x-cx)*np.cos(a) + y*np.sin(a))
                padding = np.sqrt(2)*config["adaptive_terrain"]["mesh_spacing_m"]
                assert distance - support - cr >= .03 + padding - 1e-10
    with pytest.raises(ValueError, match="this episode's sampled cables"):
        generate_features(env)


@pytest.mark.parametrize("failure", [None, "remove", "spawn"])
def test_floor_replacement_keeps_physics_paused_even_on_service_failure(tmp_path, failure):
    from types import SimpleNamespace
    from nino_rl.ros_interface import RosRobotInterface
    state = dict(paused=False, stopped=False)
    events = []
    def pause(value, **kwargs):
        assert state["stopped"]
        state["paused"] = value
        events.append("pause")
    def control(*values):
        assert values == (0., 0., 0.)
        state["stopped"] = True
    def service(client, factory, timeout, operation):
        assert state["paused"]  # No physics step may occur while support is absent.
        request = factory()
        kind = "remove" if hasattr(request, "entity") else "spawn"
        if kind == "spawn":
            assert request.entity_factory.pose.orientation.w == 1.0
        events.append(kind)
        return SimpleNamespace(success=kind != failure)
    ros = SimpleNamespace(
        world_name="factory_floor_lab",
        delete_entity=SimpleNamespace(wait_for_service=lambda **kwargs: True),
        spawn_entity=SimpleNamespace(wait_for_service=lambda **kwargs: True),
        _carved_floor_cache=tmp_path, _carved_floor_history=[],
        publish_straight_command=lambda speed: None,
        publish_control=control, set_world_paused=pause,
        _call_idempotent_service=service,
    )
    config = load_config(ROOT / "src/nino_rl/config/factory_floor_curriculum.yaml")
    if failure:
        with pytest.raises(RuntimeError):
            RosRobotInterface._configure_carved_floor(ros, [("pothole", 2.9, .1, .3)], config["adaptive_terrain"], 5.)
    else:
        RosRobotInterface._configure_carved_floor(ros, [("pothole", 2.9, .1, .3)], config["adaptive_terrain"], 5.)
    assert state["paused"]
    assert events == (["pause", "remove"] if failure == "remove" else ["pause", "remove", "spawn"])
