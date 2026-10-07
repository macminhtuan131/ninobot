#!/usr/bin/env python3
"""Generate immutable, bounded rough terrains with disjoint dataset seeds."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import numpy as np
import yaml

import generate_combined_world as combined
import generate_rough_section as rough


LEVELS = {
    1: dict(relief_fraction=.10, radius_fraction=.10, position_m=0., angle_deg=0.),
    2: dict(relief_fraction=.15, radius_fraction=.12, position_m=.15, angle_deg=15.),
    3: dict(relief_fraction=.20, radius_fraction=.15, position_m=.25, angle_deg=25.),
}


def vary_feature(item, rng, settings):
    result = deepcopy(item)
    result["height_m"] *= rng.uniform(1. - settings["relief_fraction"], 1. + settings["relief_fraction"])
    for radius in ("radius_x_m", "radius_y_m"):
        result[radius] *= rng.uniform(1. - settings["radius_fraction"], 1. + settings["radius_fraction"])
    for coordinate in ("x_m", "y_m"):
        result[coordinate] += rng.uniform(-settings["position_m"], settings["position_m"])
    result["angle_deg"] += rng.uniform(-settings["angle_deg"], settings["angle_deg"])
    return result


def build_surface(seed, level):
    """Sculpt varied existing bowls/mounds; no extra obstacle objects or floors."""
    rng, settings = np.random.default_rng(seed), LEVELS[level]
    saved_features = rough.FEATURES
    saved_bowls, saved_wheels = combined.POTHOLES, combined.WHEEL_POTHOLES
    try:
        # The legacy generator has axis-aligned bowls; retain that orientation.
        bowls = [vary_feature(rough.feature(f"L{i}", "legacy_bowl", *row[:-1], -row[-1]), rng, settings)
                 for i, row in enumerate(saved_bowls)]
        wheels = [vary_feature(rough.feature(f"LW{i}", wheel + "_bowl", x, y, rx, ry, -depth), rng, settings)
                  for i, (wheel, x, y, rx, ry, depth) in enumerate(saved_wheels)]
        combined.POTHOLES = tuple((b["x_m"], b["y_m"], b["radius_x_m"], b["radius_y_m"], -b["height_m"])
                                 for b in bowls)
        combined.WHEEL_POTHOLES = tuple((row[0], b["x_m"], b["y_m"], b["radius_x_m"],
                                        b["radius_y_m"], -b["height_m"])
                                       for row, b in zip(saved_wheels, wheels))
        rough.FEATURES = tuple(vary_feature(item, rng, settings) for item in saved_features)
        x, y, heights = rough.terrain_surface()
        dy, dx = np.gradient(heights, y, x)
        grade = float(np.hypot(dx, dy).max())
        if grade > .60 or float(np.abs(heights).max()) > .33:
            raise ValueError("Variant exceeds whole-mesh grade/height bounds")
        if not np.allclose(heights[[0, -1]], 0., atol=1e-9):
            raise ValueError("Side goal-hall joins are not flat")
        return x, y, heights, dict(max_grade=grade, max_abs_height_m=float(np.abs(heights).max()),
                                  features=list(rough.FEATURES), legacy_bowls=bowls, legacy_wheels=wheels)
    finally:
        rough.FEATURES = saved_features
        combined.POTHOLES, combined.WHEEL_POTHOLES = saved_bowls, saved_wheels


def write_world(template, mesh, target):
    root = ET.parse(template).getroot()
    ground = root.find("world/model[@name='rough_approach_ground']/link")
    for kind in ("visual", "collision"):
        ground.find(f"{kind}/geometry/mesh/uri").text = mesh.resolve().as_uri()
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)


def route_exposure(x, y, heights, routes):
    """Check that each route still encounters relief; not wheel-contact proof."""
    result = {}
    for route in routes:
        values = []
        for start, stop in zip(route["waypoints"][:-1], route["waypoints"][1:]):
            a, b = np.asarray(start), np.asarray(stop)
            tangent = (b - a) / np.linalg.norm(b - a)
            normal = np.array([-tangent[1], tangent[0]])
            for point in np.linspace(a, b, max(2, int(np.linalg.norm(b-a) / .05) + 1)):
                for offset in (-.171, 0., .171):
                    px, py = point + offset * normal
                    if x[0] <= px <= x[-1] and y[0] <= py <= y[-1]:
                        values.append(float(heights[np.argmin(abs(y-py)), np.argmin(abs(x-px))]))
        span = max(values) - min(values) if values else 0.
        if span < .03:
            raise ValueError(f"Route {route['id']} lost meaningful terrain relief")
        result[route["id"]] = dict(height_span_m=span)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("rl_runs/rough_terrain_bank_v1"))
    parser.add_argument("--train-per-level", type=int, default=3)
    parser.add_argument("--validation-per-level", type=int, default=1)
    parser.add_argument("--test-per-level", type=int, default=2)
    args = parser.parse_args()
    if min(args.train_per_level, args.validation_per_level, args.test_per_level) < 1:
        parser.error("Each split needs at least one variant per level")
    output = args.output.expanduser().resolve()
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        print(f"Existing immutable bank: {manifest_path}; choose another directory to regenerate.")
        return
    for directory in ("worlds", "meshes"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    template = rough.ROOT / "worlds/combined_rough_section.sdf"
    routes = yaml.safe_load((rough.ROOT.parent / "nino_rl/config/combined_rough_section.yaml").read_text())["routes"]["definitions"]
    entries = []
    def register(name, level, split, seed, details):
        mesh, world = output / "meshes" / f"{name}.stl", output / "worlds" / f"{name}.sdf"
        write_world(template, mesh, world)
        entry = dict(id=name, level=level, split=split, seed=seed, **details)
        for key, path in (("world", world), ("mesh", mesh)):
            entry[key] = str(path.relative_to(output))
            entry[key + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(entry)
        print(f"Built {name} ({split}), maximum grade {details['max_grade']:.3f}", flush=True)
    x, y, heights = rough.terrain_surface()
    dy, dx = np.gradient(heights, y, x)
    shutil.copy2(rough.ROOT / "terrains" / rough.MESH_NAME, output / "meshes/original.stl")
    register("original", 0, "original", 42, dict(max_grade=float(np.hypot(dx,dy).max()),
        max_abs_height_m=float(abs(heights).max()), route_exposure=route_exposure(x,y,heights,routes)))
    for split, count, seed_start in (("train", args.train_per_level, 100000),
                                      ("validation", args.validation_per_level, 200000),
                                      ("test", args.test_per_level, 300000)):
        for level in LEVELS:
            for index in range(count):
                for attempt in range(100):
                    seed = seed_start + level * 10000 + index * 100 + attempt
                    try:
                        x, y, surface, details = build_surface(seed, level)
                        details["route_exposure"] = route_exposure(x,y,surface,routes)
                        break
                    except ValueError:
                        continue
                else:
                    raise RuntimeError(f"Could not generate a bounded {split}/R{level} variant")
                name = f"R{level}_{split}_{index:02d}"
                rough.write_mesh(x, y, surface, output / "meshes" / f"{name}.stl")
                register(name, level, split, seed, details)
    manifest = dict(schema_version=1, revision="bounded_rough_bank_v1", levels=LEVELS,
                    world_name="combined_rough_section", variants=entries)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(manifest_path)


if __name__ == "__main__":
    main()
