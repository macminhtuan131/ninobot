#!/usr/bin/env python3
"""Extend the rough specialist with smooth, varied, route-planning features."""

from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from generate_combined_world import POTHOLES, WHEEL_POTHOLES, combined_surface
from generate_rocky_world import add_floor_piece, elevation, smoothstep, X_MIN, X_MAX, PIXELS


ROOT = Path(__file__).resolve().parents[1]
MESH_NAME = "rough_diverse_ground.stl"
END_X = 10.0
GOAL_X = 10.5
LANDING_END_X = 12.0
REVISION = "rough_diverse_v5"
HALF_WIDTH = 4.0
SIDE_TRANSITION_WIDTH = 1.2
GOAL_HALL_WIDTH = 2.0
OUTER_HALF_WIDTH = HALF_WIDTH + SIDE_TRANSITION_WIDTH + GOAL_HALL_WIDTH
PRESERVED_CORE_END_X = 5.7
EXTENSION_MAX_GRADE = .58
GOAL_STATIONS = (
    dict(id="W1", hall="west", pose=[-.75, 0., float(np.pi)]),
    dict(id="E1", hall="east", pose=[GOAL_X, 0., 0.]),
    *tuple(dict(id=f"N{i}", hall="north", pose=[station, 6.2, float(np.pi / 2)])
           for i, station in enumerate((2.5, 5.4, 8.4), 1)),
    *tuple(dict(id=f"S{i}", hall="south", pose=[station, -6.2, float(-np.pi / 2)])
           for i, station in enumerate((2.5, 5.4, 8.4), 1)),
)


def feature(name, kind, x, y, rx, ry, height, angle=0.0):
    return dict(id=name, kind=kind, x_m=x, y_m=y, radius_x_m=rx,
                radius_y_m=ry, height_m=height, angle_deg=angle)


# Signed height is added relief relative to the underlying rolling terrain. All
# features are sculpted into one ground surface, not added as separate objects.
FEATURES = (
    # Redistributed on the final 3.3 m rather than compressing all previous
    # features (which would create overlapping steep walls and narrow holes).
    feature("D1", "round_bowl", 7.45, -1.05, .48, .43, -.025),
    feature("M1", "rounded_mound", 7.50, 0, .42, .40, .035),
    feature("D2", "flat_bottom_bowl", 7.45, 1.05, .48, .45, -.040),
    feature("D3", "angled_trough", 8.30, -1.12, .48, .32, -.045, 25),
    feature("D5", "broad_bowl", 8.38, 0, .50, .45, -.100),
    feature("M4", "angled_ridge", 8.28, 1.05, .48, .36, .070, -25),
    feature("M3", "low_plateau", 9.13, -.98, .50, .45, .080),
    feature("S1+", "saddle_mound", 9.15, .30, .36, .38, .060),
    feature("S1-", "saddle_bowl", 9.55, -.24, .25, .32, -.040),
    feature("M6", "rounded_mound", 9.15, 1.08, .52, .48, .140),
    # Staggered wheel-scale disturbances on the nominal +/-0.171 m tire lines.
    feature("W1", "drive_bowl", 7.98, .171, .16, .13, -.012),
    feature("W2", "drive_bowl", 8.98, -.171, .17, .14, -.020),
    feature("C1", "caster_bowl", 8.00, -.088, .075, .065, -.006),
    # Fill the taper's near-level corners and use both newly widened sides.
    feature("D9", "broad_bowl", 6.20, 1.25, .50, .55, -.050),
    feature("M7", "rounded_mound", 6.20, -1.25, .50, .55, .060),
    feature("D4", "broad_bowl", 1.75, 2.90, .52, .48, -.070),
    feature("M2", "rounded_mound", 3.15, 3.03, .65, .52, .060),
    feature("D6", "broad_bowl", 4.80, 2.95, .78, .58, -.120),
    feature("M5", "rounded_mound", 6.30, 3.05, .66, .54, .100),
    feature("D7", "flat_bottom_bowl", 7.80, 2.85, .57, .52, -.080),
    feature("D8", "angled_trough", 9.05, 3.00, .58, .36, -.060, -25),
    feature("M8", "banked_mound", 1.65, -2.95, .52, .48, .045, 15),
    feature("D10", "round_bowl", 3.00, -3.05, .55, .48, -.045),
    feature("M9", "rounded_mound", 4.60, -2.90, .68, .56, .120),
    feature("D11", "broad_bowl", 6.10, -3.05, .72, .55, -.090),
    feature("M10", "low_plateau", 7.60, -2.95, .60, .55, .090),
    feature("D12", "angled_trough", 9.10, -3.00, .56, .48, -.055, 20),
    # Wheel-scale features are also available on routes across the new sides.
    feature("W3", "drive_bowl", 2.50, 2.471, .18, .145, -.030),
    feature("W4", "drive_bowl", 3.93, -3.600, .24, .20, -.040),
    feature("C2", "caster_bowl", 6.90, 2.488, .085, .075, -.010),
    feature("W5", "drive_bowl", 5.50, 3.350, .17, .14, -.018),
    feature("C3", "caster_bowl", 8.55, -3.388, .075, .065, -.008),
)


def feature_relief(xx, yy, item):
    """Compact smooth footprint, including smooth flat-bottom transitions."""
    angle = np.deg2rad(item["angle_deg"])
    dx, dy = xx - item["x_m"], yy - item["y_m"]
    u = (np.cos(angle) * dx + np.sin(angle) * dy) / item["radius_x_m"]
    v = (-np.sin(angle) * dx + np.cos(angle) * dy) / item["radius_y_m"]
    radius_squared = u * u + v * v
    if item["kind"] in ("flat_bottom_bowl", "low_plateau"):
        t = np.clip((np.sqrt(radius_squared) - .25) / .75, 0., 1.)
        shape = 1. - (6. * t**5 - 15. * t**4 + 10. * t**3)
    else:
        shape = np.maximum(1. - radius_squared, 0.) ** 2
    if item["kind"] == "banked_mound":
        shape *= 1. + .55 * v
    return item["height_m"] * shape


def extension_layers(x, y, seam_x):
    """Continue the original terrain style and blend in the local features."""
    coarse_x = np.linspace(X_MIN, X_MAX, PIXELS)
    rolling = np.stack([np.interp(x, coarse_x, row) for row in elevation(42)[::2]])
    # The old section ends level; lead/tail envelopes join it and the landing
    # smoothly. Between them, the whole floor undulates, including between the
    # annotated features. Use the same hill/noise/relief generator as x=1..6.
    rolling *= (smoothstep((x - seam_x) / .8)
                * smoothstep((END_X - x) / .85))[None, :]
    xx, yy = np.meshgrid(x, y)
    relief = sum(feature_relief(xx, yy, item) for item in FEATURES)

    def fits(scale):
        candidate = scale * rolling + relief
        dy, dx = np.gradient(candidate, y, x)
        return np.max(np.hypot(dx, dy)) <= EXTENSION_MAX_GRADE and np.max(abs(candidate)) <= .26

    # Keep wheel-sized carving depths intact. If superposed slopes become too
    # steep, reduce only the background's amplitude, never clip the heightfield.
    low, high = 0., 1.
    if fits(high):
        low = high
    else:
        if not fits(low):
            raise ValueError("Local features alone exceed the extension slope/height limit")
        for _ in range(20):
            middle = (low + high) / 2.
            if fits(middle):
                low = middle
            else:
                high = middle
    return low * rolling, relief, low


def diverse_surface(return_background=False):
    # Preserve the original centre through x=5.7 m, including its fine wheel
    # holes. Sample the wider terrain at <=20 mm x and 15.625 mm y so the new
    # caster bowls remain physically resolved.
    old_x, old_y, old_surface = combined_surface(42)
    count = int(np.ceil((END_X - old_x[-1]) / .02))
    extension_x = np.linspace(old_x[-1], END_X, count + 1)[1:]
    extension_background, _, _ = extension_layers(extension_x, old_y, old_x[-1])
    x = np.concatenate((old_x, extension_x))
    # Retain the original centre strip, while matching its heights exactly at
    # y=+/-2 m. The extra sides are continuous rolling ground, not flat wings.
    y = np.linspace(-HALF_WIDTH, HALF_WIDTH, int(2 * HALF_WIDTH / (old_y[1] - old_y[0])) + 1)
    core_background = np.concatenate((old_surface, extension_background), axis=1)
    edge = np.stack([np.interp(y, old_y, column) for column in core_background.T], axis=1)
    xx, yy = np.meshgrid(x, y)
    relief = sum(feature_relief(xx, yy, item) for item in FEATURES)
    coarse_x = np.linspace(X_MIN, X_MAX, PIXELS)
    coarse_y = np.linspace(-2., 2., PIXELS)
    source = elevation(74)
    lateral = np.stack([np.interp(y / 2., coarse_y, column) for column in source.T], axis=1)
    rolling = np.stack([np.interp(x + .4 * np.sin(.7 * side), coarse_x, row)
                        for side, row in zip(y, lateral)])
    rolling *= (smoothstep((x - X_MIN) / .65)
                * smoothstep((END_X - x) / .85))[None, :]
    blend = smoothstep((np.abs(y) - 2.) / 1.25)[:, None]

    def wing_background(scale):
        return edge * (1. - blend) + scale * rolling * blend

    def fits(scale):
        candidate = wing_background(scale) + relief
        dy, dx = np.gradient(candidate, y, x)
        return np.max(np.hypot(dx, dy)) <= EXTENSION_MAX_GRADE and np.max(abs(candidate)) <= .30

    low, high = 0., 1.
    if fits(high):
        low = high
    else:
        if not fits(low):
            raise ValueError("Widened terrain features exceed slope/height limits")
        for _ in range(20):
            middle = (low + high) / 2.
            if fits(middle):
                low = middle
            else:
                high = middle
    background = wing_background(low)
    result = (x, y, background + relief)
    if return_background:
        return (*result, background)
    return result


def terrain_surface(return_background=False):
    """Keep rough ground and join its sides to level goal halls with ramps."""
    x, y, heights, background = diverse_surface(return_background=True)
    dy = y[1] - y[0]
    count = int(np.ceil(SIDE_TRANSITION_WIDTH / dy))
    distances = np.linspace(0., SIDE_TRANSITION_WIDTH, count + 1)[1:]
    t = distances[:, None] / SIDE_TRANSITION_WIDTH
    edge_weight = 1. - 3. * t**2 + 2. * t**3
    slope_weight = t - 2. * t**2 + t**3

    def apron(field, side):
        edge = field[-1] if side > 0 else field[0]
        slope = ((field[-1] - field[-2]) if side > 0 else (field[0] - field[1])) / dy
        ramp = edge_weight * edge[None, :] + SIDE_TRANSITION_WIDTH * slope_weight * slope[None, :]
        ramp[-1] = 0.  # Exact flat-floor join, including floating-point roundoff.
        return ramp if side > 0 else ramp[::-1]

    extended_y = np.concatenate((-HALF_WIDTH - distances[::-1], y, HALF_WIDTH + distances))
    surface = np.concatenate((apron(heights, -1), heights, apron(heights, 1)), axis=0)
    result = (x, extended_y, surface)
    if return_background:
        return (*result, np.concatenate((apron(background, -1), background, apron(background, 1)), axis=0))
    return result


def add_goal_hall(link, name, x_min, x_max, y_min, y_max, color):
    """Rectangular floor with its top at z=0; never under the rough ground."""
    add_floor_piece(link, name, x_min, x_max, color)
    for suffix in ("collision", "visual"):
        floor = link.find(f"{suffix}[@name='{name}_{suffix}']")
        floor.find("pose").text = f"{(x_min + x_max) / 2:g} {(y_min + y_max) / 2:g} -0.05 0 0 0"
        floor.find("geometry/box/size").text = f"{x_max - x_min:g} {y_max - y_min:g} 0.1"


def write_mesh(x, y, surface, path):
    """Write upward-facing binary STL in batches to bound memory and CPU cost."""
    xx, yy = np.meshgrid(x - (x[0] + x[-1]) / 2., y)
    points = np.stack((xx, yy, surface), axis=-1).astype("<f4")
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)),
                      ("attribute", "<u2")])
    triangles = 2 * (len(x) - 1) * (len(y) - 1)
    with path.open("wb") as stream:
        stream.write(b"Nino rough terrain with goal halls v5".ljust(80, b"\0"))
        stream.write(np.array([triangles], dtype="<u4").tobytes())
        for row in range(0, len(y) - 1, 32):
            stop = min(row + 32, len(y) - 1)
            a, b = points[row:stop, :-1], points[row:stop, 1:]
            c, d = points[row + 1:stop + 1, :-1], points[row + 1:stop + 1, 1:]
            vertices = np.stack((np.stack((a, b, d), axis=-2),
                                 np.stack((a, d, c), axis=-2)), axis=-3).reshape(-1, 3, 3)
            records = np.zeros(len(vertices), dtype=dtype)
            normal = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
            records["normal"] = normal / np.linalg.norm(normal, axis=1)[:, None]
            records["vertices"] = vertices
            stream.write(records.tobytes())


def generate(source_root=None):
    if source_root is None:
        source_root = ET.parse(ROOT / "worlds/combined_hall.sdf").getroot()
    root = deepcopy(source_root)
    world = root.find("world")
    if world is None or world.get("name") != "combined_hall":
        raise ValueError("Expected combined_hall source")
    world.set("name", "combined_rough_section")
    structure = world.find("model[@name='enclosed_hall']/link[@name='structure']")
    ground = world.find("model[@name='rough_approach_ground']/link[@name='ground']")
    if structure is None or ground is None:
        raise ValueError("Missing hall structure or rough mesh")
    world.remove(world.find("model[@name='cable_bumps']"))
    for suffix in ("collision", "visual"):
        hall_center = (LANDING_END_X - 2.) / 2.
        hall_length = LANDING_END_X + 2.
        structure.remove(structure.find(f"{suffix}[@name='flat_cable_floor_{suffix}']"))
        structure.remove(structure.find(f"{suffix}[@name='spawn_floor_{suffix}']"))
    flat_side = HALF_WIDTH + SIDE_TRANSITION_WIDTH
    halls = (
        ("spawn_floor", "west", -2., X_MIN, -OUTER_HALF_WIDTH, OUTER_HALF_WIDTH, "0.43 0.48 0.55 1"),
        ("rough_landing_floor", "east", END_X, LANDING_END_X, -OUTER_HALF_WIDTH, OUTER_HALF_WIDTH, "0.42 0.50 0.43 1"),
        ("north_goal_hall", "north", X_MIN, END_X, flat_side, OUTER_HALF_WIDTH, "0.45 0.51 0.44 1"),
        ("south_goal_hall", "south", X_MIN, END_X, -OUTER_HALF_WIDTH, -flat_side, "0.45 0.51 0.44 1"),
    )
    for name, _, x_min, x_max, y_min, y_max, color in halls:
        add_goal_hall(structure, name, x_min, x_max, y_min, y_max, color)

    markers = ET.SubElement(world, "model", name="rough_goal_markers")
    ET.SubElement(markers, "static").text = "true"
    marks = ET.SubElement(markers, "link", name="floor_markings")
    for station in GOAL_STATIONS:
        # Painted markers are visual only; goals are coordinates, not obstacles.
        visual = ET.SubElement(marks, "visual", name=f"goal_{station['id']}")
        sx, sy, _ = station["pose"]
        ET.SubElement(visual, "pose").text = f"{sx:g} {sy:g} 0.001 0 0 0"
        cylinder = ET.SubElement(ET.SubElement(visual, "geometry"), "cylinder")
        ET.SubElement(cylinder, "radius").text = "0.22"
        ET.SubElement(cylinder, "length").text = "0.001"
        material = ET.SubElement(visual, "material")
        for channel in ("ambient", "diffuse", "emissive"):
            ET.SubElement(material, channel).text = "0.10 0.80 0.28 1"

    # Close the hall at the end of its landing, rather than leave a floorless
    # continuation to the original combined hall's front wall at x=32 m.
    for suffix in ("collision", "visual"):
        for side in ("left", "right"):
            wall = structure.find(f"{suffix}[@name='{side}_wall_{suffix}']")
            pose = wall.find("pose").text.split()
            pose[0] = f"{hall_center:g}"
            pose[1] = f"{(OUTER_HALF_WIDTH + .1) * (1 if side == 'left' else -1):g}"
            wall.find("pose").text = " ".join(pose)
            wall.find("geometry/box/size").text = f"{hall_length + .4:g} 0.2 3.3"
        front = structure.find(f"{suffix}[@name='front_wall_{suffix}']/pose")
        front.text = f"{LANDING_END_X + .1:g} 0 1.35 0 0 0"
        for name in ("front_wall", "rear_wall"):
            wall = structure.find(f"{suffix}[@name='{name}_{suffix}']/geometry/box/size")
            wall.text = f"0.2 {2 * OUTER_HALF_WIDTH + .4:g} 3.3"
        ceiling = structure.find(f"{suffix}[@name='ceiling_{suffix}']")
        ceiling.find("pose").text = f"{hall_center:g} 0 3.05 0 0 0"
        ceiling.find("geometry/box/size").text = f"{hall_length:g} {2 * OUTER_HALF_WIDTH:g} 0.1"
    for light in list(world.findall("light")):
        if float(light.find("pose").text.split()[0]) > LANDING_END_X:
            world.remove(light)
    template = world.find("light")
    for side, sign in (("north", 1), ("south", -1)):
        lamp = deepcopy(template)
        lamp.set("name", f"goal_hall_lamp_{side}")
        lamp.find("pose").text = f"5.4 {sign * 5.8:g} 2.7 0 0 0"
        world.append(lamp)

    x, y, heights = terrain_surface()
    mesh_dir = ROOT / "terrains"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    write_mesh(x, y, heights, mesh_dir / MESH_NAME)
    for element in (ground.find("collision"), ground.find("visual")):
        element.find("pose").text = f"{(x[0] + x[-1]) / 2:.6f} 0 0 0 0 0"
        element.find("geometry/mesh/uri").text = f"model://nino_description/terrains/{MESH_NAME}"
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    target = ROOT / "worlds/combined_rough_section.sdf"
    tree.write(target, encoding="utf-8", xml_declaration=True)

    dy, dx = np.gradient(heights, y, x)
    grade = np.hypot(dx, dy)
    metadata = dict(
        revision=REVISION, world_name="combined_rough_section", seed=42,
        mesh=MESH_NAME, mesh_x_m=[float(x[0]), float(x[-1])], mesh_y_m=[float(y[0]), float(y[-1])],
        rough_y_m=[-HALF_WIDTH, HALF_WIDTH],
        world_x_m=[-2., LANDING_END_X], world_y_m=[-OUTER_HALF_WIDTH, OUTER_HALF_WIDTH],
        side_transition_width_m=SIDE_TRANSITION_WIDTH,
        goal_halls=[dict(name=name, side=side, x_m=[x_min, x_max], y_m=[y_min, y_max])
                    for name, side, x_min, x_max, y_min, y_max, _ in halls],
        goal_stations=list(GOAL_STATIONS),
        preserved_rough_x_m=[float(x[0]), PRESERVED_CORE_END_X],
        preserved_core_y_m=[-2., 2.],
        original_rough_x_m=[float(x[0]), float(combined_surface(42)[0][-1])],
        flat_landing_x_m=[END_X, LANDING_END_X], start_xy_m=[0., 0.], goal_xy_m=[GOAL_X, 0.],
        height_range_m=[float(heights.min()), float(heights.max())],
        maximum_surface_angle_deg=float(np.rad2deg(np.arctan(grade.max()))),
        extension_maximum_surface_angle_deg=float(np.rad2deg(np.arctan(grade[:, x >= 7.].max()))),
        maximum_mesh_spacing_m=[float(np.diff(x).max()), float(np.diff(y).max())],
        legacy_bowls=[feature(f"L{i}", "legacy_bowl", *values[:-1], -values[-1])
                      for i, values in enumerate(POTHOLES, 1)],
        legacy_wheel_bowls=[feature(f"LW{i}", f"{wheel}_bowl", cx, cy, rx, ry, -depth)
                            for i, (wheel, cx, cy, rx, ry, depth) in enumerate(WHEEL_POTHOLES, 1)],
        features=list(FEATURES),
        terrain_style="wide rolling hills, asymmetric basins, banked mounds and embedded wheel-scale relief",
        notes=["One shared mesh for visual and collision; no floor below its bowls.",
               "Connected flat goal halls surround the rough patch, joined by smooth side ramps.",
               "Goal station markers are visual only; station selection is not automatic in the current trainer.",
               "Extension heights are added relief relative to its rolling background, not absolute elevations.",
               "Feature footprints are route-planning annotations, not mandatory reward checkpoints.",
               "The default RL route is still straight; custom drawn trajectories need explicit path integration."])
    (ROOT / "worlds/combined_rough_section.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"{target}: {len(FEATURES)} new features, mesh x={x[0]:.2f}..{x[-1]:.2f}, "
          f"goal x={GOAL_X}; extension slope <= {metadata['extension_maximum_surface_angle_deg']:.1f} deg")


if __name__ == "__main__":
    generate()
