#!/usr/bin/env python3
"""Build flat contact experiments using the rough world's true mesh carving.

The mixed map is an integration/drawing fixture. Single-obstacle worlds are
the initial mechanism experiments. One continuous terrain mesh includes both
level ground and depressions. Generating files does not run Gazebo.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import sys
from math import ceil, cos, radians, sin
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import yaml

from generate_rough_section import feature_relief, write_mesh


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "src/nino_rl"))
from nino_rl.carved_floor import continuous_axes, add_level_apron_visuals, add_goal_hall_visuals
from nino_rl.core import load_config, wrap_angle
from nino_rl.routes import RouteSet
SPEC = ROOT / "config/factory_floor_lab.yaml"
ROUTE_CONFIG = REPO / "src/nino_rl/config/factory_floor_routes_pi_check.yaml"
VARIANTS = ("mixed", "clear", "cable", "pothole", "groove", "threshold")
WORLD_NAME = "factory_floor_lab"


def sample_features(spec, variant, *, seed=None):
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant}")
    if seed is not None and variant in ("mixed", "clear"):
        raise ValueError("Seeded layouts currently support isolated obstacles only")
    negatives, cables, thresholds = [], [], []
    if variant == "mixed":
        # Viewing catalogue; training resets still sample the selected stage.
        negatives = deepcopy(spec["depressions"] + spec["grooves"])
        cables = deepcopy(spec["cables"])
    elif variant == "cable":
        cables = [deepcopy(spec["cables"][0])]
    elif variant == "pothole":
        negatives = [deepcopy(spec.get("single_pothole",spec["depressions"][0]))]
    elif variant == "groove":
        negatives = [deepcopy(spec["grooves"][0])]
    elif variant == "threshold":
        thresholds = [deepcopy(spec["threshold"])]
    if variant not in ("mixed", "clear"):
        item = (negatives + cables + thresholds)[0]
        item["x_m"] = float(spec["single_obstacle_x_m"])
        if seed is not None:
            rng = np.random.default_rng(seed)
            settings = spec["randomized_single"]
            for key, limits in (("x_m", "x_range_m"), ("y_m", "y_range_m"),
                                ("angle_deg", "angle_range_deg")):
                item[key] = float(rng.uniform(*settings[limits]))
            if negatives:
                item["depth_m"] = float(rng.uniform(*settings["depth_range_m"]))
            if cables:
                item["radius_m"] = float(rng.uniform(*settings["cable_radius_range_m"]))
    return negatives, cables, thresholds


def patch_bounds(item, spacing):
    angle = radians(item["angle_deg"])
    # Bounding rectangle encloses the rotated footprint, plus a level margin.
    rx, ry = item["radius_x_m"], item["radius_y_m"]
    half_x = abs(cos(angle)) * rx + abs(sin(angle)) * ry + 2 * spacing
    half_y = abs(sin(angle)) * rx + abs(cos(angle)) * ry + 2 * spacing
    return (item["x_m"] - half_x, item["x_m"] + half_x,
            item["y_m"] - half_y, item["y_m"] + half_y)


def depression_surface(item, xx, yy):
    if not 0 < item["depth_m"] <= .04:
        raise ValueError("Initial shallow-floor experiments require depth in (0, 40 mm]")
    if item["kind"] == "groove":
        angle = radians(item["angle_deg"])
        dx, dy = xx - item["x_m"], yy - item["y_m"]
        u = (cos(angle) * dx + sin(angle) * dy) / item["radius_x_m"]
        v = (-sin(angle) * dx + cos(angle) * dy) / item["radius_y_m"]
        # A channel carved BELOW the floor, with smooth shoulders and ends.
        z = -item["depth_m"] * np.maximum(1 - u * u, 0) ** 2 * np.maximum(1 - v * v, 0) ** 2
    else:
        shape = dict(item, height_m=-item["depth_m"])
        z = feature_relief(xx, yy, shape)
    return z


def patch_surface(item, spacing):
    bounds = patch_bounds(item, spacing)
    x = np.linspace(bounds[0], bounds[1], ceil((bounds[1] - bounds[0]) / spacing) + 1)
    y = np.linspace(bounds[2], bounds[3], ceil((bounds[3] - bounds[2]) / spacing) + 1)
    z = depression_surface(item, *np.meshgrid(x, y))
    if z.max() > 1e-12 or any(np.any(edge != 0) for edge in (z[0], z[-1], z[:, 0], z[:, -1])):
        raise ValueError("A depression must be nonpositive and meet the floor at zero")
    return x, y, z


def floor_tiles(bounds, patches):
    """Partition level floor, omitting EVERY rectangle replaced by a mesh."""
    x0, x1, y0, y1 = bounds
    for a, b, c, d in patches:
        if not x0 < a < b < x1 or not y0 < c < d < y1:
            raise ValueError("Depression patch must fit strictly inside the floor")
    for i, a in enumerate(patches):
        for b in patches[i + 1:]:
            if max(a[0], b[0]) < min(a[1], b[1]) and max(a[2], b[2]) < min(a[3], b[3]):
                raise ValueError("Overlapping patches require a shared carved mesh")
    xs = sorted({x0, x1, *(v for p in patches for v in p[:2])})
    ys = sorted({y0, y1, *(v for p in patches for v in p[2:])})
    tiles = []
    for a, b in zip(xs, xs[1:]):
        for c, d in zip(ys, ys[1:]):
            mx, my = (a + b) / 2, (c + d) / 2
            if not any(p[0] < mx < p[1] and p[2] < my < p[3] for p in patches):
                tiles.append((a, b, c, d))
    return tiles


def material(element, color):
    node = ET.SubElement(element, "material")
    for channel in ("ambient", "diffuse"):
        ET.SubElement(node, channel).text = color


def friction(element, coefficient=1.):
    ode = ET.SubElement(ET.SubElement(ET.SubElement(element, "surface"), "friction"), "ode")
    for name in ("mu", "mu2"):
        ET.SubElement(ode, name).text = str(coefficient)


def box_pair(link, name, pose, size, color="0.42 0.44 0.47 1"):
    for tag in ("collision", "visual"):
        node = ET.SubElement(link, tag, name=f"{name}_{tag}")
        ET.SubElement(node, "pose").text = pose
        box = ET.SubElement(ET.SubElement(node, "geometry"), "box")
        ET.SubElement(box, "size").text = size
        friction(node) if tag == "collision" else material(node, color)


def add_display_items(ground, items):
    """Use flat-course positive item geometry; reset replaces these examples."""
    for item in items:
        link = ET.SubElement(ground, "link", name=item["id"])
        if item["kind"] == "cable":
            parts = [(item["radius_m"], item["length_m"],
                      f"{item['x_m']} {item['y_m']} {item['radius_m']} 1.57079632679 0 0")]
            color = "0.08 0.08 0.08 1"
        elif item["kind"] == "bump":
            # Same five 5-mm steps as the existing adaptive bump spawner.
            parts = [(item["radius_m"]*(5-layer)/5, .005*(layer+1),
                      f"{item['x_m']} {item['y_m']} {.0025*(layer+1)} 0 0 0")
                     for layer in range(5)]
            color = "0.90 0.38 0.04 1"
        else:
            raise ValueError("Display item must be a flat-course bump or short cable")
        for i,(radius,length,pose) in enumerate(parts):
            for tag in ("collision", "visual"):
                node = ET.SubElement(link,tag,name=f"{item['id']}_{i}_{tag}")
                ET.SubElement(node,"pose").text = pose
                cylinder = ET.SubElement(ET.SubElement(node,"geometry"),"cylinder")
                ET.SubElement(cylinder,"radius").text = str(radius)
                ET.SubElement(cylinder,"length").text = str(length)
                friction(node,.9 if item["kind"] == "cable" else 1.) if tag == "collision" else material(node,color)


def make_world(spec, negatives, cables, thresholds, mesh_dir, contact_lab=False):
    root = deepcopy(ET.parse(ROOT / "worlds/combined_rough_section.sdf").getroot())
    world = root.find("world")
    world.set("name", WORLD_NAME)
    if contact_lab:
        # Load before robot creation: model-time plugin loading can miss the
        # EachNew contact-sensor components in Gazebo's first update.
        ET.SubElement(world,"plugin",filename="gz-sim-contact-system",name="gz::sim::systems::Contact")
    physics = world.find("physics")
    physics.set("name", "1ms_contact_lab")
    physics.find("max_step_size").text = str(spec["floor"]["physics_step_seconds"])
    dart = ET.SubElement(physics, "dart")
    ET.SubElement(dart, "collision_detector").text = "bullet"
    ground_template = deepcopy(world.find("model[@name='rough_approach_ground']"))
    if ground_template is None:
        raise ValueError("Rough world must contain its dedicated terrain ground")
    for name in ("rough_approach_ground", "rough_goal_markers", "cable_bumps", "spawn_clear_zone"):
        node = world.find(f"model[@name='{name}']")
        if node is not None:
            world.remove(node)
    structure = world.find("model[@name='enclosed_hall']/link[@name='structure']")
    # Rebuild the floor and boundaries; never retain the original solid floor.
    for node in list(structure):
        structure.remove(node)
    x0, x1 = spec["floor"]["x_m"]
    y0, y1 = spec["floor"]["y_m"]
    bounds = (x0, x1, y0, y1)
    for name, pose, size in (
        ("rear_wall", f"{x0-.1} 0 1.35 0 0 0", f".2 {y1-y0+.4} 3.3"),
        ("front_wall", f"{x1+.1} 0 1.35 0 0 0", f".2 {y1-y0+.4} 3.3"),
        ("left_wall", f"{(x0+x1)/2} {y1+.1} 1.35 0 0 0", f"{x1-x0+.4} .2 3.3"),
        ("right_wall", f"{(x0+x1)/2} {y0-.1} 1.35 0 0 0", f"{x1-x0+.4} .2 3.3"),
    ):
        box_pair(structure, name, pose, size, "0.60 0.63 0.67 1")
    # Keep the roof off for inspecting depressions in the GUI.
    for lamp in list(world.findall("light")):
        lx, ly = map(float, lamp.find("pose").text.split()[:2])
        if not x0 <= lx <= x1 or not y0 <= ly <= y1:
            world.remove(lamp)
    lamp_template = world.find("light")
    if lamp_template is not None:
        for hall in spec["goal_halls"]:
            if hall["direction"] not in ("north", "south"):
                continue
            lamp = deepcopy(lamp_template)
            lamp.set("name", f"factory_goal_lamp_{hall['id']}")
            gx, gy = hall["goal_pose"][:2]
            lamp.find("pose").text = f"{gx:g} {gy:g} 2.7 0 0 0"
            world.append(lamp)
    spacing = spec["floor"]["mesh_spacing_m"]
    patches = [patch_bounds(item, spacing) for item in negatives]
    x, y = continuous_axes(bounds, patches, spacing, spec["floor"]["flat_mesh_spacing_m"])
    xx, yy = np.meshgrid(x, y)
    z = np.zeros_like(xx)
    for item in negatives:
        z = np.minimum(z, depression_surface(item, xx, yy))
    signature = hashlib.sha256(json.dumps(
        ["continuous_mesh_v1", negatives, bounds, spacing, spec["floor"]["flat_mesh_spacing_m"]],
        sort_keys=True).encode()).hexdigest()[:16]
    mesh_name = f"terrain_{signature}.stl"
    mesh_path = mesh_dir / mesh_name
    write_mesh(x, y-(y0+y1)/2, z, mesh_path)
    mesh_info = dict(mesh=mesh_name, bounds_xy_m=list(bounds),
        mesh_sha256=hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
        triangles=2*(len(x)-1)*(len(y)-1),
        representation="continuous_mesh", depression_spacing_m=spacing,
        flat_spacing_m=spec["floor"]["flat_mesh_spacing_m"],
        sampled_depth_m=float(-z.min()))
    # Keep walls independent so a reset can replace the entire floor safely.
    ground = ground_template
    ground.set("name", "factory_contact_floor")
    world.append(ground)
    floor_link = ground.find("link")
    floor_link.set("name", "terrain")
    for tag in ("collision", "visual"):
        node = floor_link.find(tag)
        node.set("name", f"terrain_{tag}")
        node.find("pose").text = f"{(x0+x1)/2:.9f} {(y0+y1)/2:.9f} 0 0 0 0"
        node.find("geometry/mesh/uri").text = f"model://nino_description/terrains/factory_floor_lab/{mesh_name}"
    add_level_apron_visuals(ground,bounds,spec["floor"].get("terrain_view_bounds_xy_m"))
    add_goal_hall_visuals(ground,bounds,spec.get("goal_halls"))
    patch_info = []
    for item in negatives:
        x, y, z = patch_surface(item, spacing)
        zy, zx = np.gradient(z, y, x)
        patch_info.append(dict(item, bounds_xy_m=list(patch_bounds(item, spacing)),
            mesh=mesh_name, mesh_sha256=mesh_info["mesh_sha256"],
            sampled_depth_m=float(-z.min()), maximum_grade=float(np.hypot(zx, zy).max()),
            mesh_spacing_m=[float(np.diff(x).max()), float(np.diff(y).max())]))
    # Name retained so the flat-course cable spawn/remove API can be reused
    # later. Default configs retain these static obstacles exactly as generated.
    cable_model = ET.SubElement(world, "model", name="cable_bumps")
    ET.SubElement(cable_model, "static").text = "true"
    link = ET.SubElement(cable_model, "link", name="cables")
    for item in cables:
        for tag in ("collision", "visual"):
            node = ET.SubElement(link, tag, name=f"{item['id']}_{tag}")
            ET.SubElement(node, "pose").text = (
                f"{item['x_m']} {item['y_m']} {item['radius_m']} 1.57079632679 0 {radians(item['angle_deg'])}")
            cylinder = ET.SubElement(ET.SubElement(node, "geometry"), "cylinder")
            ET.SubElement(cylinder, "radius").text = str(item["radius_m"])
            ET.SubElement(cylinder, "length").text = str(item["length_m"])
            friction(node, .9) if tag == "collision" else material(node, "0.08 0.08 0.08 1")
    if not cables:
        world.remove(cable_model)
    for item in thresholds:
        model = ET.SubElement(world, "model", name="isolated_threshold")
        ET.SubElement(model, "static").text = "true"
        link = ET.SubElement(model, "link", name=item["id"])
        # Isolated low rounded obstacle, no broad terrain mound.
        for tag in ("collision", "visual"):
            node = ET.SubElement(link, tag, name=f"{item['id']}_{tag}")
            ET.SubElement(node, "pose").text = (
                f"{item['x_m']} {item['y_m']} 0 1.57079632679 0 {radians(item['angle_deg'])}")
            cylinder = ET.SubElement(ET.SubElement(node, "geometry"), "cylinder")
            ET.SubElement(cylinder, "radius").text = str(item["height_m"])
            ET.SubElement(cylinder, "length").text = str(item["length_m"])
            friction(node) if tag == "collision" else material(node, "0.40 0.30 0.16 1")
    markers = ET.SubElement(world, "model", name="task_markers")
    ET.SubElement(markers, "static").text = "true"
    link = ET.SubElement(markers, "link", name="markers")
    marks = [("start", spec["floor"]["start_xy_m"], "0.08 0.34 0.12 1")]
    marks += [(f"goal_{hall['id']}", hall["goal_pose"][:2], "0.10 0.80 0.28 1")
              for hall in spec["goal_halls"]]
    for name, xy, color in marks:
        node = ET.SubElement(link, "visual", name=name)
        ET.SubElement(node, "pose").text = f"{xy[0]} {xy[1]} .001 0 0 0"
        cylinder = ET.SubElement(ET.SubElement(node, "geometry"), "cylinder")
        ET.SubElement(cylinder, "radius").text = ".20"
        ET.SubElement(cylinder, "length").text = ".001"
        material(node, color)
    return root, patch_info, mesh_info


def generate(variant, seed=None, root=ROOT, *, contact_lab=False):
    root = Path(root)
    spec = yaml.safe_load(SPEC.read_text())
    routes = deepcopy(RouteSet(load_config(ROUTE_CONFIG)).routes)
    goals = {hall["id"]: hall["goal_pose"] for hall in spec["goal_halls"]}
    if {route["id"] for route in routes} != set(goals):
        raise ValueError("Factory routes must match all four goal halls")
    for route in routes:
        gx, gy, heading = goals[route["id"]]
        if (not np.allclose(route["waypoints"][-1], [gx, gy])
                or abs(wrap_angle(radians(route["goal_heading_deg"])-heading)) > 1e-6):
            raise ValueError(f"Route {route['id']} must end at its hall goal")
    negatives, cables, thresholds = sample_features(spec, variant, seed=seed)
    mesh_dir = root / "terrains/factory_floor_lab"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    world_dir = root / "worlds"
    world_dir.mkdir(parents=True, exist_ok=True)
    xml, patches, terrain_mesh = make_world(spec, negatives, cables, thresholds, mesh_dir,contact_lab)
    display_items = deepcopy(spec.get("display_items", [])) if variant == "mixed" else []
    if display_items:
        add_display_items(xml.find("world/model[@name='factory_contact_floor']"), display_items)
    suffix = variant + (f"_seed_{seed}" if seed is not None else "")
    if contact_lab:
        suffix += "_contact_lab"
    filename = f"factory_floor_{suffix}.sdf"
    tree = ET.ElementTree(xml)
    ET.indent(tree, space="  ")
    tree.write(world_dir / filename, encoding="utf-8", xml_declaration=True)
    metadata = dict(revision=spec["revision"], variant=variant, seed=seed,
        world_name=WORLD_NAME, world_file=filename, floor=spec["floor"],
        goal_halls=spec["goal_halls"],
        drawn_routes=routes, route_config="src/nino_rl/config/factory_floor_routes_pi_check.yaml",
        adaptive_zone=spec["adaptive_zone"],
        depressions=patches, cables=cables, thresholds=thresholds, display_items=display_items,
        floor_tiles_xy_m=[], terrain_mesh=terrain_mesh,
        world_sha256=hashlib.sha256((world_dir / filename).read_bytes()).hexdigest(),
        terrain_background="exactly level z=0 outside carved patches",
        terrain_template="combined_rough_section.sdf: rough_approach_ground",
        obstacles_physically_validated=False, generator_starts_simulator=False,
        randomization="seeded offline geometry generation" if seed is not None else "fixed layout",
        per_episode_randomization=False, training_allowed=False, optuna_allowed=False,
        first_contact_detection_implemented=False, snapshot_branching_implemented=False,
        contact_instrumentation=contact_lab,
        notes=["One continuous terrain mesh for visual and collision, with no underlying floor box.",
               "Depth/grade values describe geometry, not confirmed traversability.",
               "Static obstacle coordinates are simulator/analysis data, not deployable supervisor inputs."])
    (world_dir / f"factory_floor_{suffix}.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"{filename}: {len(patches)} carved depressions, {len(cables)} rigid cables, "
          f"{len(thresholds)} isolated thresholds; no rolling hills")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=(*VARIANTS, "all"), default="all")
    parser.add_argument("--seed", type=int, help="Offline randomization for a single-obstacle variant")
    parser.add_argument("--contact-lab",action="store_true",help="Instrumented world with early-loaded contact system")
    parser.add_argument("--output-root", type=Path, default=ROOT,
                        help="Description-style root with worlds/ and terrains/ directories")
    args = parser.parse_args()
    if args.seed is not None and args.variant in ("all", "mixed", "clear"):
        parser.error("--seed requires cable, pothole, groove or threshold")
    for variant in VARIANTS if args.variant == "all" else (args.variant,):
        generate(variant, args.seed, args.output_root,contact_lab=args.contact_lab)


if __name__ == "__main__":
    main()
