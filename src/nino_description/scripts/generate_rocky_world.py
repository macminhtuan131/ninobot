#!/usr/bin/env python3
"""Build a rolling, uneven road with one shared contact and visual mesh."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "terrains"
PIXELS = 513
X_MIN, X_MAX = 0.8, 30.5
Y_MIN, Y_MAX = -2.0, 2.0
VERTICAL_RANGE_M = 0.60
MAX_GRADE = 0.60
BASE_MAX_HEIGHT_M = 0.18
BASE_MAX_GRADE = 0.40
HILL_AMPLITUDE_M = 0.13
ROUGH_AMPLITUDE_M = 0.012
# (travel x, lateral y, height, length along x, width across y), in metres.
# Positive patches are raised ground; negative ones are shallow hollows.
SPOTS = (
    (2.4, 0.7, -0.060, 0.65, 0.55),
    (4.4, -0.5, 0.065, 0.70, 0.60),
    (6.3, 0.5, -0.055, 0.75, 0.55),
    (8.5, -0.7, 0.060, 0.75, 0.65),
    (10.7, 0.7, -0.065, 0.70, 0.55),
    (13.2, -0.5, 0.060, 0.80, 0.60),
    (15.4, 0.8, -0.060, 0.70, 0.60),
    (18.2, -0.8, 0.055, 0.75, 0.55),
    (20.8, 0.4, -0.060, 0.75, 0.65),
    (23.3, -0.4, 0.060, 0.75, 0.60),
    (26.1, 0.7, -0.055, 0.70, 0.55),
    (28.5, -0.6, 0.055, 0.75, 0.60),
)
# Smaller hollows and mounds cross the robot's centerline (y ~= 0).
# Several are inside the first 6 m used by the tracking task.
TRACK_SPOTS = (
    (1.8, 0.05, -0.070, 0.33, 0.32),
    (2.7, -0.12, 0.065, 0.38, 0.35),
    (3.55, 0.08, -0.065, 0.40, 0.38),
    (4.55, 0.10, 0.065, 0.38, 0.34),
    (5.55, -0.08, -0.055, 0.38, 0.35),
    (7.4, 0.12, 0.040, 0.45, 0.37),
    (9.4, -0.10, -0.040, 0.42, 0.36),
    (11.4, 0.10, 0.035, 0.40, 0.34),
    (13.5, -0.08, -0.045, 0.42, 0.38),
    (16.1, 0.08, 0.040, 0.43, 0.35),
    (18.7, -0.12, -0.040, 0.42, 0.36),
    (21.3, 0.10, 0.035, 0.42, 0.34),
    (24.0, -0.08, -0.045, 0.42, 0.38),
    (26.7, 0.10, 0.040, 0.45, 0.36),
    (28.9, -0.10, -0.040, 0.40, 0.34),
)
DENSE_SPOT_COLUMNS = 32


def smoothstep(value):
    clipped = np.clip(value, 0.0, 1.0)
    return clipped * clipped * (3.0 - 2.0 * clipped)


def value_noise(rng, rows, columns, cells_y, cells_x):
    """Bilinearly interpolate seeded random values with smoothstep weights."""
    grid = rng.random((cells_y + 1, cells_x + 1))
    fy = np.linspace(0, cells_y, rows)
    fx = np.linspace(0, cells_x, columns)
    iy = np.minimum(fy.astype(int), cells_y - 1)
    ix = np.minimum(fx.astype(int), cells_x - 1)
    ty = smoothstep(fy - iy)[:, None]
    tx = smoothstep(fx - ix)[None, :]
    low = grid[np.ix_(iy, ix)] * (1 - tx) + grid[np.ix_(iy, ix + 1)] * tx
    high = grid[np.ix_(iy + 1, ix)] * (1 - tx) + grid[np.ix_(iy + 1, ix + 1)] * tx
    return low * (1 - ty) + high * ty


def dense_spots(seed):
    """Scatter varied bowls and mounds, including one per route station."""
    rng = np.random.default_rng(seed + 101)
    spots = []
    positions = []

    def add_spot(center_x, center_y, is_mound):
        height = (rng.uniform(0.065, 0.10) if is_mound
                  else -rng.uniform(0.025, 0.050))
        spots.append((center_x, center_y, height,
                      rng.uniform(0.27, 0.42), rng.uniform(0.22, 0.34),
                      rng.uniform(-np.pi, np.pi),
                      rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45)))
        positions.append((center_x, center_y))

    for station_index, station_x in enumerate(np.linspace(1.35, 29.85, DENSE_SPOT_COLUMNS)):
        add_spot(station_x + rng.uniform(-0.27, 0.27),
                 rng.uniform(-0.17, 0.17), station_index % 2 == 1)
        for _ in range(3):
            for _attempt in range(200):
                center_x = rng.uniform(1.25, 30.05)
                center_y = rng.choice((-1.0, 1.0)) * rng.uniform(0.43, 1.75)
                if all(((center_x - other_x) / 0.48) ** 2 +
                       ((center_y - other_y) / 0.38) ** 2 > 1.0
                       for other_x, other_y in positions):
                    break
            add_spot(center_x, center_y, rng.random() < 0.5)
    return tuple(spots)


def spot_relief(x, y, spots):
    """Smooth local rises and dips, each confined to one part of the road."""
    relief = np.zeros((len(y), len(x)))
    for center_x, center_y, height, radius_x, radius_y in spots:
        distance = ((x[None, :] - center_x) / radius_x) ** 2 + (
            (y[:, None] - center_y) / radius_y
        ) ** 2
        relief += height * np.exp(-0.5 * distance)
    return relief


def dense_relief(x, y, spots):
    """Make asymmetric mounds and shallow bowls with gently raised rims."""
    relief = np.zeros((len(y), len(x)))
    for center_x, center_y, height, radius_x, radius_y, angle, skew_x, skew_y in spots:
        xx = x[None, :] - center_x
        yy = y[:, None] - center_y
        along = (np.cos(angle) * xx + np.sin(angle) * yy) / radius_x
        across = (-np.sin(angle) * xx + np.cos(angle) * yy) / radius_y
        squared_radius = along ** 2 + across ** 2
        primary = np.exp(-0.5 * squared_radius)
        offset = np.exp(-0.5 * ((along - skew_x) ** 2 +
                                (across - skew_y) ** 2))
        shape = 0.7 * primary + 0.3 * offset
        if height > 0:
            relief += height * shape
        else:
            rim = np.exp(-0.5 * ((np.sqrt(squared_radius) - 1.7) / 0.35) ** 2)
            relief += height * shape - 0.12 * height * rim
    return relief


def elevation(seed, return_dense_scale=False):
    rng = np.random.default_rng(seed)
    x = np.linspace(X_MIN, X_MAX, PIXELS)
    y = np.linspace(Y_MIN, Y_MAX, PIXELS)
    # Broad, changing hills give the road the rolling side profile of the
    # reference sketch. Small two-dimensional noise keeps it from looking
    # like a perfectly extruded sine wave.
    phase = 2 * np.pi * (x - X_MIN) / 3.8
    hills = HILL_AMPLITUDE_M * (0.88 + 0.12 * np.sin(0.37 * phase + 0.8)) * (
        np.sin(phase) + 0.16 * np.sin(2 * phase + 0.4)
    )
    cells_y = max(1, int((Y_MAX - Y_MIN) / 0.45))
    cells_x = max(1, int((X_MAX - X_MIN) / 0.65))
    coarse = value_noise(rng, PIXELS, PIXELS, cells_y, cells_x)
    fine = value_noise(rng, PIXELS, PIXELS, 2 * cells_y, 2 * cells_x)
    rough = (2 * (coarse + 0.5 * fine) / 1.5 - 1) * ROUGH_AMPLITUDE_M
    lead = smoothstep((x - X_MIN) / 0.65)
    tail = smoothstep((X_MAX - x) / 0.80)
    envelope = lead[None, :] * tail[None, :]
    base = (hills[None, :] + rough +
            spot_relief(x, y, (*SPOTS, *TRACK_SPOTS))) * envelope
    step_y = (Y_MAX - Y_MIN) / (PIXELS - 1)
    step_x = (X_MAX - X_MIN) / (PIXELS - 1)
    dy, dx = np.gradient(base, step_y, step_x)
    base_grade = float(np.max(np.hypot(dx, dy)))
    base *= min(1.0, BASE_MAX_HEIGHT_M / float(np.max(np.abs(base))),
                BASE_MAX_GRADE / base_grade)
    dense = dense_relief(x, y, dense_spots(seed)) * envelope
    # Preserve the existing rolling profile. Reduce only the new relief if
    # needed to keep the road inside its height and slope limits.
    def fits(scale):
        candidate = base + scale * dense
        if np.max(np.abs(candidate)) > VERTICAL_RANGE_M / 2:
            return False
        dy, dx = np.gradient(candidate, step_y, step_x)
        return np.max(np.hypot(dx, dy)) <= MAX_GRADE

    if fits(1.0):
        dense_scale = 1.0
    else:
        low, high = 0.0, 1.0
        for _ in range(18):
            middle = (low + high) / 2
            if fits(middle):
                low = middle
            else:
                high = middle
        dense_scale = low
    surface = base + dense_scale * dense
    surface[:, 0] = surface[:, -1] = 0.0
    return (surface, dense_scale) if return_dense_scale else surface


def add_floor_piece(link, name, x_min, x_max, color):
    center = 0.5 * (x_min + x_max)
    size = f"{x_max - x_min:.6f} 4 0.1"
    pose = f"{center:.6f} 0 -0.05 0 0 0"
    geometry = ET.Element("geometry")
    ET.SubElement(ET.SubElement(geometry, "box"), "size").text = size
    collision = ET.SubElement(link, "collision", name=name + "_collision")
    ET.SubElement(collision, "pose").text = pose
    collision.append(deepcopy(geometry))
    ode = ET.SubElement(ET.SubElement(ET.SubElement(collision, "surface"), "friction"), "ode")
    ET.SubElement(ode, "mu").text = "1.0"
    ET.SubElement(ode, "mu2").text = "1.0"
    visual = ET.SubElement(link, "visual", name=name + "_visual")
    ET.SubElement(visual, "pose").text = pose
    visual.append(geometry)
    material = ET.SubElement(visual, "material")
    ET.SubElement(material, "ambient").text = color
    ET.SubElement(material, "diffuse").text = color


def add_terrain_mesh(link):
    template = ET.Element("geometry")
    mesh = ET.SubElement(template, "mesh")
    ET.SubElement(mesh, "uri").text = "model://nino_description/terrains/rocky_ground.stl"
    collision = ET.SubElement(link, "collision", name="terrain_collision")
    ET.SubElement(collision, "pose").text = f"{(X_MIN + X_MAX) / 2:g} 0 0 0 0 0"
    collision.append(deepcopy(template))
    ode = ET.SubElement(ET.SubElement(ET.SubElement(collision, "surface"), "friction"), "ode")
    ET.SubElement(ode, "mu").text = "1.0"
    ET.SubElement(ode, "mu2").text = "1.0"
    visual = ET.SubElement(link, "visual", name="terrain_visual")
    ET.SubElement(visual, "pose").text = f"{(X_MIN + X_MAX) / 2:g} 0 0 0 0 0"
    visual.append(template)
    material = ET.SubElement(visual, "material")
    ET.SubElement(material, "ambient").text = "0.55 0.43 0.32 1"
    ET.SubElement(material, "diffuse").text = "0.65 0.52 0.39 1"
    ET.SubElement(material, "specular").text = "0.05 0.05 0.05 1"


def save_terrain_mesh(surface):
    """Write the single STL surface shared by Gazebo physics and rendering."""
    vertices = surface[::2, ::2]
    width = vertices.shape[0]
    points = np.empty((width, width, 3), dtype=np.float32)
    for row in range(width):
        y = Y_MIN + (Y_MAX - Y_MIN) * row / (width - 1)
        for column in range(width):
            x = X_MIN + (X_MAX - X_MIN) * column / (width - 1) - (X_MIN + X_MAX) / 2
            points[row, column] = (x, y, vertices[row, column])
    path = TERRAIN / "rocky_ground.stl"
    with path.open("wb") as mesh:
        mesh.write(b"Continuous Nino uneven ground".ljust(80, b"\0"))
        mesh.write(struct.pack("<I", 2 * (width - 1) ** 2))
        for row in range(width - 1):
            for column in range(width - 1):
                a = points[row, column]
                b = points[row, column + 1]
                c = points[row + 1, column]
                d = points[row + 1, column + 1]
                for triangle in ((a, b, d), (a, d, c)):
                    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
                    normal /= np.linalg.norm(normal)
                    mesh.write(struct.pack("<12fH", *normal, *triangle[0],
                                           *triangle[1], *triangle[2], 0))


def generate(seed=42):
    TERRAIN.mkdir(parents=True, exist_ok=True)
    surface, dense_scale = elevation(seed, return_dense_scale=True)
    grayscale = np.uint8(np.clip(np.rint((surface + VERTICAL_RANGE_M / 2) / VERTICAL_RANGE_M * 255.0), 0, 255))
    Image.fromarray(grayscale, "L").save(TERRAIN / "rocky_height.png")
    save_terrain_mesh(surface)

    tree = ET.parse(ROOT / "worlds/long_hall.sdf")
    world = tree.getroot().find("world")
    world.set("name", "rocky_hall")
    ET.SubElement(world.find("scene"), "grid").text = "false"
    world.remove(world.find("model[@name='cable_bumps']"))
    structure = world.find("model[@name='enclosed_hall']/link[@name='structure']")
    # Valleys fall below the old flat floor, so the walls must reach below them.
    for wall in ("left_wall", "right_wall", "rear_wall", "front_wall"):
        for suffix in ("collision", "visual"):
            element = structure.find(f"*[@name='{wall}_{suffix}']")
            pose = element.find("pose")
            coords = pose.text.split()
            coords[2] = "1.35"
            pose.text = " ".join(coords)
            size = element.find("geometry/box/size")
            dimensions = size.text.split()
            dimensions[2] = "3.3"
            size.text = " ".join(dimensions)
    for name in ("floor_collision", "floor_visual"):
        structure.remove(structure.find(f"*[@name='{name}']"))
    add_floor_piece(structure, "spawn_floor", -2.0, X_MIN, "0.38 0.36 0.32 1")
    add_floor_piece(structure, "goal_floor", X_MAX, 32.0, "0.38 0.36 0.32 1")
    terrain = ET.SubElement(world, "model", name="continuous_rocky_ground")
    ET.SubElement(terrain, "static").text = "true"
    add_terrain_mesh(ET.SubElement(terrain, "link", name="ground"))
    ET.indent(tree, space="  ")
    tree.write(ROOT / "worlds/rocky_hall.sdf", encoding="utf-8", xml_declaration=True)

    dy, dx = np.gradient(surface, (Y_MAX-Y_MIN)/(PIXELS-1), (X_MAX-X_MIN)/(PIXELS-1))
    scattered = dense_spots(seed)
    meta = {"seed": seed, "heightmap_pixels": PIXELS, "active_x_m": [X_MIN, X_MAX],
            "clear_width_m": 4.0, "goal_xy_m": [6.0, 0.0],
            "caster_radius_m": 0.016,
            "height_range_m": [float(surface.min()), float(surface.max())],
            "maximum_surface_grade": float(np.max(np.hypot(dx, dy))),
            "floor_join_height_m": 0.0, "terrain_type": "shared collision and visual mesh",
            "profile": "rolling hills with dense mounds and shallow hollows",
            "dense_spot_shape": "asymmetric mounds and shallow rimmed bowls",
            "local_spot_count": len(SPOTS),
            "track_spot_count": len(TRACK_SPOTS),
            "dense_spot_count": len(scattered),
            "dense_mound_count": sum(spot[2] > 0 for spot in scattered),
            "dense_hollow_count": sum(spot[2] < 0 for spot in scattered),
            "route_dense_mound_count": sum(spot[2] > 0 for spot in scattered[::4]),
            "route_dense_hollow_count": sum(spot[2] < 0 for spot in scattered[::4]),
            "dense_relief_scale": dense_scale}
    (ROOT / "worlds/rocky_hall.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Generated one continuous {PIXELS}x{PIXELS} ground: "
          f"height {meta['height_range_m']}, grade {meta['maximum_surface_grade']:.3f}.")


if __name__ == "__main__":
    generate()
