#!/usr/bin/env python3
"""Build rough ground followed by the long hall's flat cable course."""

from copy import deepcopy
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np

from generate_rocky_world import (
    ROOT, TERRAIN, X_MIN, X_MAX, Y_MIN, Y_MAX, PIXELS,
    add_floor_piece, elevation, smoothstep,
)


ROUGH_TAPER_START_M = 5.8
FIRST_FLAT_CABLE_M = 7.2
GOAL_X_M = 13.0
MESH_NAME = "combined_rough_ground.stl"
MESH_X_SPACING_M = 0.02
# (x, y, radius along route, radius across route, extra depth), metres.
# Subtracted directly from the shared visual/collision ground mesh.
POTHOLES = (
    # Keep the middle bowl on the route; offset the outer two to opposite sides.
    (1.8, 0.30, 0.55, 0.42, 0.07),
    (3.55, 0.0, 0.90, 0.45, 0.07),
    (5.45, -0.10, 0.55, 0.42, 0.07),
    # Extra shallow and deeper bowls span the central 2 m of the hall.
    (1.35, -0.78, 0.32, 0.28, 0.025),
    (2.35, 0.78, 0.43, 0.38, 0.055),
    (2.95, -0.76, 0.44, 0.43, 0.055),
    (3.90, 0.83, 0.36, 0.32, 0.030),
    (4.72, -0.40, 0.46, 0.40, 0.075),
    (5.55, 0.82, 0.40, 0.36, 0.045),
)
# Smaller bowls centered on the actual wheel paths. The drive tires are
# 125 mm across; the casters are 32 mm across. These hollows are wider than
# their respective wheels so a wheel can drop into the ground itself.
WHEEL_POTHOLES = (
    ("drive", 2.55, 0.171, 0.15, 0.125, 0.022),
    ("drive", 4.65, -0.171, 0.15, 0.125, 0.022),
    ("caster", 1.10, 0.088, 0.060, 0.056, 0.006),
    ("caster", 4.35, -0.088, 0.060, 0.056, 0.006),
)


def soften_central_rise(surface, x, y):
    """Spread the ascent after the central basin without blurring wheel holes."""
    spacing = x[1] - x[0]
    sigma_x = 0.35
    half_width = int(np.ceil(3.0 * sigma_x / spacing))
    offsets = np.arange(-half_width, half_width + 1)
    kernel = np.exp(-0.5 * (offsets * spacing / sigma_x) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(surface, ((0, 0), (half_width, half_width)), mode="edge")
    smoothed = sum(
        weight * padded[:, offset:offset + len(x)]
        for offset, weight in enumerate(kernel)
    )
    xx, yy = np.meshgrid(x, y)
    blend = np.exp(-0.5 * ((xx - 3.95) / 0.65) ** 2
                   -0.5 * ((yy - 0.08) / 0.55) ** 2)
    return surface * (1.0 - blend) + smoothed * blend


def combined_surface(seed=42):
    """Use the Rocky Hall surface up to a smooth, level flat-road seam."""
    coarse_x = np.linspace(X_MIN, X_MAX, PIXELS)
    coarse_y = np.linspace(Y_MIN, Y_MAX, PIXELS)
    end = 2 * int(np.ceil(np.searchsorted(coarse_x, 6.65) / 2))
    join_x = float(coarse_x[end])
    x = np.linspace(X_MIN, join_x, int(np.ceil((join_x - X_MIN) / MESH_X_SPACING_M)) + 1)
    y = coarse_y[::2]
    # The original 58 mm travel spacing cannot represent a caster-sized hole.
    # Resample broad hills first, then carve the small holes at 20 mm spacing.
    surface = np.stack([
        np.interp(x, coarse_x[:end + 1], row)
        for row in elevation(seed)[::2, :end + 1]
    ])
    fade = smoothstep((join_x - x) / (join_x - ROUGH_TAPER_START_M))
    surface *= fade[None, :]
    surface = soften_central_rise(surface, x, y)
    xx, yy = np.meshgrid(x, y)
    for center_x, center_y, radius_x, radius_y, depth in POTHOLES:
        radial_squared = ((xx - center_x) / radius_x) ** 2 + ((yy - center_y) / radius_y) ** 2
        # A smooth dish has no vertical lip and no separate collision object.
        surface -= depth * np.maximum(1.0 - radial_squared, 0.0) ** 2
    for _, center_x, center_y, radius_x, radius_y, depth in WHEEL_POTHOLES:
        radial_squared = ((xx - center_x) / radius_x) ** 2 + ((yy - center_y) / radius_y) ** 2
        surface -= depth * np.maximum(1.0 - radial_squared, 0.0) ** 2
    surface[:, -1] = 0.0
    return x, y, surface


def write_mesh(x, y, surface, path):
    """One open STL surface used identically for rendering and contact."""
    xx, yy = np.meshgrid(x - (x[0] + x[-1]) / 2, y)
    points = np.stack((xx, yy, surface), axis=-1).astype(np.float32)
    rows, columns = points.shape[:2]
    with path.open("wb") as mesh:
        mesh.write(b"Nino rough-to-flat ground".ljust(80, b"\0"))
        mesh.write(struct.pack("<I", 2 * (rows - 1) * (columns - 1)))
        for row in range(rows - 1):
            for column in range(columns - 1):
                a, b = points[row, column], points[row, column + 1]
                c, d = points[row + 1, column], points[row + 1, column + 1]
                for triangle in ((a, b, d), (a, d, c)):
                    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
                    normal /= np.linalg.norm(normal)
                    mesh.write(struct.pack("<12fH", *normal, *triangle[0],
                                           *triangle[1], *triangle[2], 0))


def add_mesh(link, join_x):
    geometry = ET.Element("geometry")
    ET.SubElement(ET.SubElement(geometry, "mesh"), "uri").text = (
        f"model://nino_description/terrains/{MESH_NAME}"
    )
    pose = f"{(X_MIN + join_x) / 2:.6f} 0 0 0 0 0"
    collision = ET.SubElement(link, "collision", name="rough_collision")
    ET.SubElement(collision, "pose").text = pose
    collision.append(deepcopy(geometry))
    ode = ET.SubElement(ET.SubElement(ET.SubElement(collision, "surface"), "friction"), "ode")
    ET.SubElement(ode, "mu").text = "1.0"
    ET.SubElement(ode, "mu2").text = "1.0"
    visual = ET.SubElement(link, "visual", name="rough_visual")
    ET.SubElement(visual, "pose").text = pose
    visual.append(geometry)
    material = ET.SubElement(visual, "material")
    ET.SubElement(material, "ambient").text = "0.55 0.43 0.32 1"
    ET.SubElement(material, "diffuse").text = "0.65 0.52 0.39 1"


def generate(seed=42):
    TERRAIN.mkdir(parents=True, exist_ok=True)
    x, y, surface = combined_surface(seed)
    write_mesh(x, y, surface, TERRAIN / MESH_NAME)
    tree = ET.parse(ROOT / "worlds/long_hall.sdf")
    world = tree.getroot().find("world")
    world.set("name", "combined_hall")
    ET.SubElement(world.find("scene"), "grid").text = "false"

    structure = world.find("model[@name='enclosed_hall']/link[@name='structure']")
    for wall in ("left_wall", "right_wall", "rear_wall", "front_wall"):
        for suffix in ("collision", "visual"):
            element = structure.find(f"*[@name='{wall}_{suffix}']")
            coords = element.find("pose").text.split()
            coords[2] = "1.35"
            element.find("pose").text = " ".join(coords)
            dimensions = element.find("geometry/box/size").text.split()
            dimensions[2] = "3.3"
            element.find("geometry/box/size").text = " ".join(dimensions)
    for name in ("floor_collision", "floor_visual"):
        structure.remove(structure.find(f"*[@name='{name}']"))
    add_floor_piece(structure, "spawn_floor", -2.0, X_MIN, "0.38 0.36 0.32 1")
    add_floor_piece(structure, "flat_cable_floor", float(x[-1]), 32.0,
                    "0.42 0.44 0.47 1")

    # Keep only the cables between the rough section and the goal. Remove
    # both collision and visual elements beyond the goal.
    cables = world.find("model[@name='cable_bumps']/link[@name='cables']")
    removed = 0
    for element in list(cables):
        if element.tag not in ("collision", "visual"):
            continue
        cable_x = float(element.find("pose").text.split()[0])
        if cable_x < FIRST_FLAT_CABLE_M - 1e-6 or cable_x > GOAL_X_M + 1e-6:
            cables.remove(element)
            if element.tag == "collision":
                removed += 1

    rough = ET.SubElement(world, "model", name="rough_approach_ground")
    ET.SubElement(rough, "static").text = "true"
    add_mesh(ET.SubElement(rough, "link", name="ground"), float(x[-1]))
    ET.indent(tree, space="  ")
    tree.write(ROOT / "worlds/combined_hall.sdf", encoding="utf-8", xml_declaration=True)

    dy, dx = np.gradient(surface, y[1] - y[0], x[1] - x[0])
    metadata = {
        "seed": seed, "rough_x_m": [float(x[0]), float(x[-1])],
        "flat_x_m": [float(x[-1]), 32.0], "goal_xy_m": [GOAL_X_M, 0.0],
        "first_flat_cable_x_m": FIRST_FLAT_CABLE_M,
        "static_cables_removed": removed,
        "static_cables_remaining": len(cables.findall("collision")),
        "height_range_m": [float(surface.min()), float(surface.max())],
        "maximum_surface_grade": float(np.max(np.hypot(dx, dy))),
        "terrain_type": "shared collision and visual mesh",
        "potholes": [
            {"x_m": cx, "y_m": cy, "radius_x_m": rx, "radius_y_m": ry,
             "additional_depth_m": depth}
            for cx, cy, rx, ry, depth in POTHOLES
        ],
        "wheel_potholes": [
            {"wheel": wheel, "x_m": cx, "y_m": cy, "radius_x_m": rx,
             "radius_y_m": ry, "additional_depth_m": depth}
            for wheel, cx, cy, rx, ry, depth in WHEEL_POTHOLES
        ],
        "mesh_spacing_m": [float(x[1] - x[0]), float(y[1] - y[0])],
        "flat_join_height_m": 0.0,
    }
    (ROOT / "worlds/combined_hall.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Generated rough x={x[0]:.2f}..{x[-1]:.2f} m, then flat cables; "
          f"height {metadata['height_range_m']}, grade {metadata['maximum_surface_grade']:.3f}.")


if __name__ == "__main__":
    generate()
