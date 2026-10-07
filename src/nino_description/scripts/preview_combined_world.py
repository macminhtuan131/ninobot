#!/usr/bin/env python3
"""Render a quick preview of the generated combined course geometry."""

from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Ellipse
import numpy as np

from generate_combined_world import GOAL_X_M, POTHOLES, WHEEL_POTHOLES, combined_surface


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parents[1] / "docs/combined_world_preview.png"


def callout(axis, label, point, text_position, *, color="#263238"):
    axis.annotate(
        label, xy=point, xytext=text_position, fontsize=10, color=color,
        ha="center", va="center", zorder=7,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "#fffefa",
              "edgecolor": color, "linewidth": 0.9, "alpha": 0.94},
        arrowprops={"arrowstyle": "->", "color": color, "linewidth": 1.25,
                    "shrinkA": 5, "shrinkB": 4},
    )


def main() -> None:
    x, y, heights = combined_surface()
    world = ET.parse(ROOT / "worlds/combined_hall.sdf")
    cables = []
    for collision in world.findall(".//model[@name='cable_bumps']/link/collision"):
        pose = [float(value) for value in collision.findtext("pose").split()]
        if pose[0] > GOAL_X_M:
            continue
        length = float(collision.findtext("geometry/cylinder/length"))
        cables.append((pose[0], pose[1], pose[5], length))

    fig, (ax, profile) = plt.subplots(2, 1, figsize=(15, 8), facecolor="#faf9f6",
                                      gridspec_kw={"height_ratios": [2.2, 1]}, sharex=True)
    fig.subplots_adjust(left=0.075, right=0.96, top=0.87, bottom=0.12, hspace=0.20)
    ax.set_facecolor("#faf9f6")
    profile.set_facecolor("#faf9f6")
    ax.axvspan(x[-1], 13.6, color="#9fa4aa", alpha=0.7)
    color = ax.pcolormesh(x, y, heights, cmap="terrain",
                          norm=TwoSlopeNorm(vmin=-0.16, vcenter=0, vmax=0.25),
                          shading="auto", rasterized=True)
    fig.colorbar(color, ax=ax, shrink=0.8, label="Ground height (m)", pad=0.015)
    for cx, cy, yaw, length in cables:
        t = np.linspace(-length / 2, length / 2, 30)
        ax.plot(cx - np.sin(yaw) * t, cy + np.cos(yaw) * t,
                color="#242424", linewidth=2.2)
    ax.scatter([0], [0], color="#1782a6", s=110, marker="o", label="Start", zorder=4)
    ax.scatter([13], [0], color="#19a05b", s=150, marker="*", label="Goal", zorder=4)
    for cx, cy, rx, ry, _ in POTHOLES:
        ax.add_patch(Ellipse((cx, cy), 2 * rx, 2 * ry, fill=False,
                             edgecolor="#3549b1", linestyle="--", linewidth=1.5, zorder=5))
    for wheel, cx, cy, rx, ry, _ in WHEEL_POTHOLES:
        ax.add_patch(Ellipse((cx, cy), 2 * rx, 2 * ry, fill=False,
                             edgecolor="#f54036" if wheel == "drive" else "#ff9c21",
                             linewidth=2.3, zorder=5))
    ax.axvline(x[-1], color="white", linestyle="--", linewidth=1.8)
    ax.text(1.15, 1.85, "ROUGH GROUND", ha="center", fontsize=11,
            fontweight="bold", bbox={"facecolor": "#faf9f6", "alpha": 0.85,
                                      "edgecolor": "none"})
    ax.text(10.6, 1.85, "FLAT CABLE COURSE", ha="center", fontsize=11,
            fontweight="bold", bbox={"facecolor": "#faf9f6", "alpha": 0.85,
                                      "edgecolor": "none"})
    callout(ax, "Shallow bowl\n2.5 cm added depth", (1.35, -0.78), (1.25, -1.52))
    callout(ax, "Caster-size hole", (1.10, 0.088), (0.95, 0.82), color="#a95b00")
    callout(ax, "Middle bowl\ny = 0 m", (POTHOLES[1][0], POTHOLES[1][1]),
            (3.55, 1.50), color="#3549b1")
    callout(ax, "Drive-wheel hole", (4.65, -0.171), (4.75, -1.58), color="#b52a20")
    callout(ax, "Rough → flat seam\nx = 6.72 m", (x[-1], 0.0), (7.55, -1.52))
    callout(ax, "Original static cables", (8.0, 0.0), (9.15, 1.35))
    ax.set(xlim=(-0.5, 13.6), ylim=(-2.1, 2.1), ylabel="Across hall y (m)")
    ax.legend(loc="lower left", ncol=2)
    centerline = heights[np.argmin(abs(y)), :]
    profile.plot(x, centerline, color="#80533f", linewidth=2)
    profile.axhline(0, color="#777777", linewidth=1)
    profile.axvspan(x[-1], 13.6, color="#9fa4aa", alpha=0.7)
    profile.axvline(x[-1], color="#555555", linestyle="--")
    callout(profile, "Middle bowl", (3.55, float(np.interp(3.55, x, centerline))),
            (2.75, 0.23), color="#3549b1")
    callout(profile, "Gentler uphill exit", (4.15, float(np.interp(4.15, x, centerline))),
            (4.80, 0.23), color="#80533f")
    profile.set(xlabel="Travel x (m)", ylabel="Centerline height (m)", ylim=(-0.20, 0.30))
    profile.grid(alpha=0.25)
    fig.text(0.5, 0.96, "Combined hall — geometry preview (top view)", ha="center", va="top",
             fontsize=19, fontweight="bold", color="#263238")
    fig.text(0.5, 0.025,
             "Blue dashed rings: nine bowls across the hall  •  Red: drive-wheel holes  •  Orange: caster holes",
             ha="center", va="bottom", fontsize=11, color="#47515a")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=170, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(OUTPUT)


if __name__ == "__main__":
    main()
