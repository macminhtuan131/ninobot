#!/usr/bin/env python3
"""Plot the exact split-course rough STL and the flat episode layout rules."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Circle, Ellipse, Rectangle
import numpy as np
import yaml


DESCRIPTION = Path(__file__).resolve().parents[1]
REPO = DESCRIPTION.parents[1]
OUTPUT = REPO / "docs/split_course_preview.png"


def rough_grid():
    """Recover vertex heights from the binary STL used by both rendering and contact."""
    world = ET.parse(DESCRIPTION / "worlds/combined_rough_section.sdf").getroot().find("world")
    collision = world.find("model[@name='rough_approach_ground']/link/collision")
    uri = collision.findtext("geometry/mesh/uri")
    prefix = "model://nino_description/"
    if not uri.startswith(prefix):
        raise ValueError(f"Unsupported mesh URI: {uri}")
    mesh = DESCRIPTION / uri.removeprefix(prefix)
    dtype = np.dtype([
        ("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)),
        ("attribute", "<u2"),
    ])
    with mesh.open("rb") as stream:
        stream.seek(80)
        count = int(np.fromfile(stream, dtype="<u4", count=1)[0])
        triangles = np.fromfile(stream, dtype=dtype, count=count)
    if len(triangles) != count:
        raise ValueError(f"Incomplete STL: {mesh}")
    vertices = triangles["vertices"].reshape(-1, 3)
    xs = np.unique(vertices[:, 0])
    ys = np.unique(vertices[:, 1])
    heights = np.full((len(ys), len(xs)), np.nan)
    heights[np.searchsorted(ys, vertices[:, 1]),
            np.searchsorted(xs, vertices[:, 0])] = vertices[:, 2]
    if np.isnan(heights).any():
        raise ValueError(f"STL grid has missing vertices: {mesh}")
    pose = collision.find("pose")
    return xs + float(pose.text.split()[0]), ys, heights


def main():
    rough = yaml.safe_load((REPO / "src/nino_rl/config/combined_rough_section.yaml").read_text())
    flat = yaml.safe_load((REPO / "src/nino_rl/config/combined_flat_section.yaml").read_text())
    metadata = json.loads((DESCRIPTION / "worlds/combined_rough_section.json").read_text())
    xs, ys, heights = rough_grid()
    fig, axes = plt.subplots(2, 2, figsize=(16, 8.8), facecolor="#faf9f6",
                             gridspec_kw={"height_ratios": [2.5, 1]})
    fig.subplots_adjust(left=0.065, right=0.95, top=0.87, bottom=0.16,
                        hspace=0.19, wspace=0.29)
    rough_map, flat_map = axes[0]
    rough_profile, flat_profile = axes[1]
    for axis in axes.flat:
        axis.set_facecolor("#faf9f6")

    color = rough_map.pcolormesh(xs, ys, heights, shading="auto", cmap="terrain",
                                 norm=TwoSlopeNorm(vmin=-0.17, vcenter=0, vmax=0.25),
                                 rasterized=True)
    fig.colorbar(color, ax=rough_map, shrink=0.7, pad=0.01, label="Ground height (m)")
    for bowl in metadata["legacy_bowls"] + metadata["features"]:
        rough_map.add_patch(Ellipse((bowl["x_m"], bowl["y_m"]),
                                    2 * bowl["radius_x_m"], 2 * bowl["radius_y_m"],
                                    angle=bowl["angle_deg"], fill=False,
                                    edgecolor="#293da2" if bowl["height_m"] < 0 else "#a54d17", linestyle="--",
                                    linewidth=1.4))
    for hole in metadata["legacy_wheel_bowls"]:
        rough_map.add_patch(Ellipse((hole["x_m"], hole["y_m"]),
                                    2 * hole["radius_x_m"], 2 * hole["radius_y_m"],
                                    fill=False,
                                    edgecolor="#d5312b" if hole["kind"] == "drive_bowl" else "#e58d19",
                                    linewidth=1.8))
    rough_goal = float(rough["navigation"]["goal_pose"][0])
    rough_map.plot([0, rough_goal], [0, 0], color="white", linestyle=":", linewidth=1.7)
    rough_map.scatter([0], [0], s=130, c="#147eaa", edgecolors="white", zorder=5)
    rough_map.scatter([rough_goal], [0], s=190, c="#149457", marker="*",
                      edgecolors="white", zorder=5)
    rough_map.annotate("START", (0, 0), (0.15, -0.40), fontweight="bold")
    rough_map.annotate(f"GOAL\nx={rough_goal:g}", (rough_goal, 0), (rough_goal - 2, -0.65), fontweight="bold")
    rough_map.axvline(xs[-1], color="#ffffff", linestyle="--", linewidth=1.5)
    rough_map.set(title="ROUGH GROUND  •  extended collision/visual STL", xlim=(-0.15, rough_goal + .35),
                  ylim=(ys[0] - .05, ys[-1] + .05), ylabel="Across hall y (m)")

    flat_goal = float(flat["navigation"]["goal_pose"][0])
    flat_map.add_patch(Rectangle((0, -2), flat_goal, 4,
                                 facecolor="#bfc2c5", edgecolor="none"))
    zone_min, zone_max = flat["adaptive_terrain"]["zone_x_m"]
    lateral_min, lateral_max = flat["adaptive_terrain"]["lateral_spawn_range_m"]
    flat_map.add_patch(Rectangle((zone_min, lateral_min), zone_max-zone_min,
                                 lateral_max-lateral_min, facecolor="#ecc782",
                                 edgecolor="#a26015", alpha=0.42, linestyle="--",
                                 linewidth=1.5))
    for cable in flat["course_cable_randomization"]["cables"]:
        x = float(cable["x"])
        flat_map.plot([x, x], [-2, 2], color="#252a30", linewidth=2.2)
        flat_map.text(x, 1.82, f"{x:g}", ha="center", va="top", fontsize=9,
                      bbox={"facecolor": "#faf9f6", "alpha": 0.8, "edgecolor": "none"})
    flat_map.add_patch(Circle((2.9, 0.16), 0.28, fill=False,
                              edgecolor="#b2512a", linestyle=":", linewidth=2))
    flat_map.text(3.0, -0.70, "adaptive items may spawn here\n(initially 1, up to 6)",
                  ha="center", fontsize=10, color="#6e3d14")
    flat_map.plot([0, flat_goal], [0, 0], color="white", linestyle=":", linewidth=1.7)
    flat_map.scatter([0], [0], s=130, c="#147eaa", edgecolors="white", zorder=5)
    flat_map.scatter([flat_goal], [0], s=190, c="#149457", marker="*",
                     edgecolors="white", zorder=5)
    flat_map.annotate("START", (0, 0), (0.14, -0.40), fontweight="bold")
    flat_map.annotate("GOAL\nx=6.45", (flat_goal, 0), (5.54, -0.65), fontweight="bold")
    flat_map.set(title="FLAT CABLE COURSE  •  local coordinates", xlim=(-0.15, 6.75),
                 ylim=(-2.05, 2.05), ylabel="Across hall y (m)")

    centerline = heights[np.argmin(abs(ys)), :]
    rough_profile.plot(xs, centerline, color="#80513c", linewidth=2.2)
    rough_profile.axhline(0, color="#888", linewidth=1)
    rough_profile.set(xlim=(-0.15, rough_goal + .35), ylim=(-0.21, 0.28),
                      xlabel="Travel x (m)", ylabel="Centerline height (m)")
    rough_profile.grid(alpha=0.25)
    flat_profile.plot([0, flat_goal], [0, 0], color="#555c62", linewidth=2.2)
    flat_profile.set(xlim=(-0.15, 6.75), ylim=(-0.21, 0.28),
                     xlabel="Travel x (m)", ylabel="Centerline height (m)")
    flat_profile.grid(alpha=0.25)
    fig.suptitle("Two independently tuned Nino courses — top view and centerline",
                 fontsize=18, fontweight="bold")
    fig.text(0.5, 0.045,
             "Flat cables are drawn at 0° for clarity; each angle is resampled from −30° to +30° per episode. "
             "Adaptive item location and type also change.",
             ha="center", fontsize=10, color="#424a50")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=170, facecolor=fig.get_facecolor())
    print(OUTPUT)


if __name__ == "__main__":
    main()
