#!/usr/bin/env python3
"""Annotated exact-mesh preview and feature coordinates for drawing routes."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Ellipse
import numpy as np

from preview_split_worlds import DESCRIPTION, rough_grid


DOCS = DESCRIPTION.parents[1] / "docs"


def outline(axis, item, *, label=True, height=False):
    color = "#2849b0" if item["height_m"] < 0 else "#9b3e16"
    axis.add_patch(Ellipse((item["x_m"], item["y_m"]), 2 * item["radius_x_m"],
                          2 * item["radius_y_m"], angle=item["angle_deg"],
                          fill=False, edgecolor=color, linewidth=1.2, zorder=4))
    if not label:
        return
    text = item["id"]
    if height:
        text += f"\n{item['height_m'] * 100:+g} cm"
    location = (item["x_m"], item["y_m"])
    small = item["kind"] in ("drive_bowl", "caster_bowl")
    if small:
        label_y = item["y_m"] + (.32 if item["kind"] == "drive_bowl" and item["y_m"] > 0 else -.32)
        low_y, high_y = axis.get_ylim()
        if label_y < low_y + .35 or label_y > high_y - .35:
            label_y = item["y_m"] - (label_y - item["y_m"])
        location = (item["x_m"], label_y)
        axis.plot([item["x_m"], location[0]], [item["y_m"], location[1]],
                  linewidth=.7, color=color, zorder=5)
    axis.text(*location, text, ha="center", va="center", fontsize=8 if small else 9,
              fontweight="bold", color=color, zorder=6,
              bbox=dict(facecolor="white", alpha=.83, edgecolor="none", pad=1.5))


def draw_goal_halls(axis, metadata):
    for hall in metadata["goal_halls"]:
        left, right = hall["x_m"]
        bottom, top = hall["y_m"]
        axis.add_patch(plt.Rectangle((left, bottom), right - left, top - bottom,
                                     facecolor="#e0e7dc", edgecolor="#a0ab9c", linewidth=.8, zorder=0))
    x_min, x_max = metadata["world_x_m"]
    y_min, y_max = metadata["world_y_m"]
    axis.add_patch(plt.Rectangle((x_min, y_min), x_max - x_min, y_max - y_min,
                                 fill=False, edgecolor="#38423d", linewidth=2, zorder=5))
    axis.axhline(metadata["rough_y_m"][0], color="white", linestyle="--", linewidth=.8)
    axis.axhline(metadata["rough_y_m"][1], color="white", linestyle="--", linewidth=.8)
    for station in metadata["goal_stations"]:
        sx, sy, yaw = station["pose"]
        axis.scatter([sx], [sy], color="#118a40", edgecolors="white", marker="*", s=120, zorder=9)
        axis.text(sx, sy + .40, f"Goal {station['id']}", ha="center", fontsize=9,
                  fontweight="bold", color="#155631", zorder=10)
    axis.set(xlim=(x_min - .3, x_max + .3), ylim=(y_min - .3, y_max + .3))
    axis.text(5.4, y_max - .18, "NORTH GOAL HALL", ha="center", va="top", fontsize=9)
    axis.text(5.4, y_min + .18, "SOUTH GOAL HALL", ha="center", va="bottom", fontsize=9)
    axis.text(x_min + .22, 2., "WEST HALL", rotation=90, ha="center", va="center", fontsize=9)
    axis.text(x_max - .22, 2., "EAST HALL", rotation=90, ha="center", va="center", fontsize=9)


def main():
    metadata = json.loads((DESCRIPTION / "worlds/combined_rough_section.json").read_text())
    x, y, heights = rough_grid()
    terrain_end = metadata["mesh_x_m"][1]
    goal_x = metadata["goal_xy_m"][0]
    norm = TwoSlopeNorm(vmin=min(-.17, float(heights.min())), vcenter=0,
                        vmax=max(.25, float(heights.max())))
    fig, axes = plt.subplots(3, 1, figsize=(16, 15),
                             gridspec_kw=dict(height_ratios=[3, 3.3, 1.3]))
    fig.subplots_adjust(left=.06, right=.91, top=.92, bottom=.09, hspace=.40)
    whole, extension, profiles = axes
    for axis in axes[:2]:
        color = axis.pcolormesh(x, y, heights, cmap="terrain", norm=norm,
                               shading="auto", rasterized=True)
        axis.set(ylim=metadata["mesh_y_m"], ylabel="Across hall y (m)")
        axis.set_xticks(np.arange(0, goal_x + 1, 1))
        axis.grid(alpha=.15)
    draw_goal_halls(whole, metadata)
    whole.set(title="Rough ground surrounded by connected flat goal halls and smooth side ramps")
    whole.add_patch(plt.Rectangle((x[0], -2), metadata["preserved_rough_x_m"][1] - x[0], 4,
                                  fill=False, edgecolor="white", linestyle="--", linewidth=1.2))
    whole.scatter([0], [0], color="#087ca5", s=60, zorder=8)
    whole.text(0, -.65, "START", fontsize=9, ha="center")
    whole.text(goal_x, -.65, "Default goal", fontsize=9, ha="center")
    for item in metadata["legacy_bowls"]:
        outline(whole, item)
    for item in metadata["legacy_wheel_bowls"]:
        outline(whole, item, label=False)
    for item in metadata["features"]:
        outline(whole, item, label=False)
        outline(extension, item, height=True)
    extension.set(xlim=(x[0], terrain_end), ylim=metadata["rough_y_m"],
                  title="Added variety across the hall — labels show carving/rise relative to the rolling ground")
    extension.set_xticks(np.arange(1, terrain_end + .01, 1))
    fig.colorbar(color, ax=axes[:2].tolist(), cax=fig.add_axes([.93, .42, .013, .43]),
                 label="Ground height (m)")
    for lateral, name, color in ((-3.0, "y=-3 m", "#7951a0"),
                                  (-1.05, "y=-1.05 m", "#2656a1"),
                                  (0, "y=0 m", "#85572f"),
                                  (1.05, "y=+1.05 m", "#008d68"),
                                  (3.0, "y=+3 m", "#c57f16")):
        profiles.plot(x, heights[np.argmin(abs(y - lateral))], label=name, color=color, linewidth=1.5)
    profiles.axhline(0, color="#888", linewidth=.7)
    profiles.set(xlim=(0, goal_x + .5), ylim=(min(-.19, heights.min() - .02), max(.27, heights.max() + .02)),
                 xlabel="Along hall x (m)", ylabel="Ground height (m)",
                 title="Height profiles across five lateral corridors (not configured training trajectories)")
    profiles.legend(loc="upper right", ncol=5, fontsize=8)
    profiles.grid(alpha=.25)
    fig.suptitle("Diverse rough terrain — one mesh for visual and collision", fontsize=19, fontweight="bold")
    fig.text(.5, .025, "D: depression • M: mound/plateau • W: drive-wheel bowl • C: caster bowl • S: mound–bowl pair. "
             "Select feature IDs when drawing routes.", ha="center", fontsize=10)
    DOCS.mkdir(parents=True, exist_ok=True)
    output = DOCS / "rough_diverse_preview.png"
    fig.savefig(output, dpi=170)
    plt.close(fig)

    # A separate overview keeps equal metre scales for drawing trajectories.
    overview, axis = plt.subplots(figsize=(11, 10))
    color = axis.pcolormesh(x, y, heights, cmap="terrain", norm=norm, shading="auto", rasterized=True)
    draw_goal_halls(axis, metadata)
    axis.set_aspect("equal", adjustable="box")
    axis.scatter([0], [0], color="#087ca5", s=80, edgecolors="white", zorder=10)
    axis.text(0, -.45, "Default start", fontsize=9, ha="center")
    axis.set(title="Goal halls around the rough map — choose start and goal for each route",
             xlabel="World x (m)", ylabel="World y (m)")
    axis.set_xticks(np.arange(-2, 13, 1))
    axis.set_yticks(np.arange(-7, 8, 1))
    axis.grid(alpha=.15)
    overview.colorbar(color, ax=axis, shrink=.7, label="Ground height (m)")
    overview.text(.5, .02, "Green stars: optional goal stations • Dashed lines: rough-ground side boundaries • "
                  "Side ramps blend to level halls", ha="center", fontsize=9)
    overview.tight_layout(rect=(0, .04, 1, 1))
    overview.savefig(DOCS / "rough_goal_halls_preview.png", dpi=170)
    plt.close(overview)

    lines = ["# Extended rough terrain: feature catalogue", "",
             "Coordinates are in metres. Signed relief is added carving/rise relative to the rolling background, not absolute ground elevation.",
             "The extension uses the original terrain generator for continuous hills, valleys and asymmetric relief between the annotated features.",
             "Blue depressions and brown mounds are sculpted into the shared collision/visual mesh.", "",
             "| ID | Type | x | y | Length × width (m) | Relief (cm) | Angle (°) |",
             "|---|---|---:|---:|---|---:|---:|"]
    for item in metadata["features"]:
        lines.append(f"| {item['id']} | {item['kind'].replace('_', ' ')} | {item['x_m']:g} | {item['y_m']:g} "
                     f"| {2*item['radius_x_m']:g} × {2*item['radius_y_m']:g} | {100*item['height_m']:+g} "
                     f"| {item['angle_deg']:g} |")
    lines += ["", "The original centre strip remains unchanged at x=0.8..5.7 m, y=-2..2 m; its bowl IDs are L1..L9.",
              "The rough patch is 8 m wide (y=-4..4 m). Additional carving fills the old taper corners and both new sides.",
              f"The flat landing is x={terrain_end:g}..{metadata['flat_landing_x_m'][1]:g} m and the default goal is ({goal_x:g}, 0).",
              "Flat, connected goal halls surround it: world x=-2..12 m, y=-7.2..7.2 m.",
              "Side ramps occupy y=4..5.2 m and y=-5.2..-4 m. The side goal halls are 2 m wide.",
              "Five profile lines in the preview are drawing guides, not automatically loaded paths.",
              "The rough training config now samples eight user-drawn routes with ordered route gates.",
              "See ROUGH_DRAWN_ROUTES.md and rough_routes_preview.png for the configured trajectories.", ""]
    lines += ["## Optional goal stations", "",
              "Station markers are visual only. The rough trainer selects a configured route and its goal each episode.", "",
              "| Goal ID | Hall | x (m) | y (m) | Exit heading (degrees) |", "|---|---|---:|---:|---:|"]
    for station in metadata["goal_stations"]:
        sx, sy, yaw = station["pose"]
        lines.append(f"| {station['id']} | {station['hall']} | {sx:g} | {sy:g} | {np.rad2deg(yaw):g} |")
    lines.append("")
    (DOCS / "ROUGH_TERRAIN_FEATURES.md").write_text("\n".join(lines))
    print(output)


if __name__ == "__main__":
    main()
