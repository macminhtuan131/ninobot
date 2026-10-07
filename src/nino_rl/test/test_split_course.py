"""The flat specialist must score the same route its actor observes."""

from pathlib import Path
import json
import xml.etree.ElementTree as ET

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_flat_route_and_obstacles_share_local_coordinates():
    config = yaml.safe_load((ROOT / "src/nino_rl/config/combined_flat_section.yaml").read_text())
    world = ET.parse(ROOT / "src/nino_description/worlds/combined_flat_section.sdf").getroot().find("world")
    start_x = config["navigation"]["start_pose"][0]
    goal_x = config["navigation"]["goal_pose"][0]
    static_cables = sorted(float(item.find("pose").text.split()[0]) for item in
                           world.findall("model[@name='cable_bumps']/link/collision"))
    episode_cables = sorted(item["x"] for item in config["course_cable_randomization"]["cables"])
    zone_min, zone_max = config["adaptive_terrain"]["zone_x_m"]
    assert start_x == 0.0  # Gazebo resets the actor's wheel odometry to zero.
    assert goal_x == config["path"]["default_goal_x_m"] == 6.45
    assert static_cables == episode_cables
    assert all(start_x < x < goal_x for x in static_cables)
    assert start_x < zone_min < zone_max < goal_x


def test_rough_section_has_matched_collision_and_visual_without_cables():
    config = yaml.safe_load((ROOT / "src/nino_rl/config/combined_rough_section.yaml").read_text())
    world = ET.parse(ROOT / "src/nino_description/worlds/combined_rough_section.sdf").getroot().find("world")
    rough = world.find("model[@name='rough_approach_ground']/link[@name='ground']")
    assert rough is not None
    assert rough.find("collision/geometry/mesh/uri").text == rough.find("visual/geometry/mesh/uri").text
    assert world.find("model[@name='cable_bumps']") is None
    assert config["navigation"]["start_pose"][0] == 0.0


def test_extended_rough_mesh_preserves_old_ground_and_has_feasible_new_slopes(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "src/nino_description/scripts"))
    from generate_combined_world import combined_surface
    from generate_rough_section import diverse_surface

    old_x, old_y, old_height = combined_surface()
    x, y, height = diverse_surface()
    assert np.array_equal(x[:len(old_x)], old_x)
    core_rows = np.flatnonzero(abs(y) <= 2.)
    retained_columns = np.flatnonzero(old_x <= 5.7)
    assert np.array_equal(y[core_rows], old_y)
    assert np.array_equal(height[np.ix_(core_rows, retained_columns)], old_height[:, retained_columns])
    assert (y[0], y[-1]) == (-4., 4.)
    assert x[-1] == 10.0
    assert np.diff(x).max() <= .0201
    dy, dx = np.gradient(height, y, x)
    assert np.max(np.hypot(dx, dy)[:, x >= 7.]) < .60
    assert np.max(np.hypot(dx, dy)) < .60
    assert np.all(height[:, -1] == 0.)
    # The interior between labelled features must remain terrain, rather than
    # flat floor with isolated objects. Check the independent background.
    _, _, _, background = diverse_surface(return_background=True)
    interior = background[:, (x >= 7.4) & (x <= 9.3)]
    assert np.std(interior) > .025
    assert np.mean(abs(interior) > .005) > .85
    assert np.max(abs(height[core_rows, len(old_x)] - height[core_rows, len(old_x) - 1])) < .001


def test_extended_rough_goal_has_supported_landing_and_no_stale_challenges():
    metadata = json.loads((ROOT / "src/nino_description/worlds/combined_rough_section.json").read_text())
    config = yaml.safe_load((ROOT / "src/nino_rl/config/combined_rough_section.yaml").read_text())
    world = ET.parse(ROOT / "src/nino_description/worlds/combined_rough_section.sdf").getroot().find("world")
    landing = world.find("model/link/collision[@name='rough_landing_floor_collision']")
    center = float(landing.findtext("pose").split()[0])
    length = float(landing.findtext("geometry/box/size").split()[0])
    assert center - length / 2 == metadata["mesh_x_m"][1]
    assert center + length / 2 == metadata["flat_landing_x_m"][1]
    goal = config["navigation"]["goal_pose"][0]
    assert center - length / 2 < goal < center + length / 2
    assert goal == config["path"]["default_goal_x_m"] == metadata["goal_xy_m"][0]
    assert config["terrain_geometry_id"] == metadata["revision"]
    assert config["fixed_terrain_challenges"] == []
    assert not config["adaptive_terrain"]["progress_on_success"]
    assert world.find(".//collision[@name='flat_cable_floor_collision']") is None
    assert float(landing.findtext("geometry/box/size").split()[1]) == 14.4
    structure = world.find("model[@name='enclosed_hall']/link")
    for side, sign in (("left", 1), ("right", -1)):
        wall = structure.find(f"collision[@name='{side}_wall_collision']")
        centre_y = float(wall.findtext("pose").split()[1])
        thickness = float(wall.findtext("geometry/box/size").split()[1])
        assert abs(centre_y - sign * thickness / 2 - sign * 7.2) < 1e-8
    for side in (-1, 1):
        outer = [f for f in metadata["features"] if side * f["y_m"] > 2.]
        assert len(outer) >= 7
        assert any(f["height_m"] > 0 for f in outer)
        assert any(f["height_m"] < 0 for f in outer)
        assert min(f["x_m"] for f in outer) < 2.
        assert max(f["x_m"] for f in outer) > 9.


def test_binary_rough_surface_has_real_relief_and_upward_faces(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "src/nino_description/scripts"))
    from preview_split_worlds import rough_grid
    from generate_rough_section import terrain_surface

    mesh = ROOT / "src/nino_description/terrains/rough_diverse_ground.stl"
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    with mesh.open("rb") as stream:
        stream.seek(80)
        count = int(np.fromfile(stream, dtype="<u4", count=1)[0])
        records = np.fromfile(stream, dtype=dtype)
    assert len(records) == count
    assert mesh.stat().st_size == 84 + 50 * count
    assert np.isfinite(records["vertices"]).all()
    assert np.all(records["normal"][:, 2] > 0.)
    x, y, heights = rough_grid()
    generated_x, generated_y, _, background = terrain_surface(return_background=True)
    assert np.allclose(x, generated_x, atol=1e-6)
    assert np.allclose(y, generated_y, atol=1e-6, rtol=0)
    metadata = json.loads((ROOT / "src/nino_description/worlds/combined_rough_section.json").read_text())
    for item in metadata["features"]:
        if item["id"].startswith("S1"):
            continue  # The saddle deliberately sums two overlapping profiles.
        row, column = np.argmin(abs(y - item["y_m"])), np.argmin(abs(x - item["x_m"]))
        # Positive/negative relief must be physically present in the STL,
        # measured against the background, including overlapping features.
        actual = heights[row, column] - background[row, column]
        assert actual * np.sign(item["height_m"]) > abs(item["height_m"]) / 4, (item["id"], actual)


def test_goal_hall_ramps_are_continuous_and_stations_have_collision_floor(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "src/nino_description/scripts"))
    from generate_rough_section import diverse_surface, terrain_surface

    x, rough_y, rough = diverse_surface()
    mesh_x, mesh_y, height = terrain_surface()
    centre_rows = np.flatnonzero(abs(mesh_y) <= 4.)
    assert np.array_equal(x, mesh_x)
    assert np.array_equal(mesh_y[centre_rows], rough_y)
    assert np.array_equal(height[centre_rows], rough)
    assert np.all(height[[0, -1]] == 0.)
    assert (mesh_y[0], mesh_y[-1]) == (-5.2, 5.2)
    dy, dx = np.gradient(height, mesh_y, mesh_x)
    assert np.max(np.hypot(dx, dy)) < .60

    metadata = json.loads((ROOT / "src/nino_description/worlds/combined_rough_section.json").read_text())
    world = ET.parse(ROOT / "src/nino_description/worlds/combined_rough_section.sdf").getroot().find("world")
    structure = world.find("model[@name='enclosed_hall']/link")
    rectangles = []
    for hall in metadata["goal_halls"]:
        floor = structure.find(f"collision[@name='{hall['name']}_collision']")
        pose = [float(v) for v in floor.findtext("pose").split()]
        size = [float(v) for v in floor.findtext("geometry/box/size").split()]
        assert abs(pose[2] + size[2] / 2) < 1e-10
        bounds = [pose[0] - size[0]/2, pose[0] + size[0]/2, pose[1] - size[1]/2, pose[1] + size[1]/2]
        assert np.allclose(bounds, [*hall["x_m"], *hall["y_m"]])
        # A hall floor may share a boundary with the mesh, never cover its bowls.
        assert min(bounds[1], mesh_x[-1]) <= max(bounds[0], mesh_x[0]) or min(bounds[3], mesh_y[-1]) <= max(bounds[2], mesh_y[0])
        rectangles.append(bounds)
    assert {hall["side"] for hall in metadata["goal_halls"]} == {"west", "east", "north", "south"}
    assert len(metadata["goal_stations"]) == 8
    for station in metadata["goal_stations"]:
        sx, sy, _ = station["pose"]
        assert any(left < sx < right and bottom < sy < top for left, right, bottom, top in rectangles)
    assert world.find("model[@name='rough_goal_markers']/link/collision") is None
