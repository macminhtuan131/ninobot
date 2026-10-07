#!/usr/bin/env python3
"""Plot the actual configured training routes over the collision terrain."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import yaml

from preview_rough_section import draw_goal_halls
from preview_split_worlds import DESCRIPTION, rough_grid


def main():
    root = DESCRIPTION.parents[1]
    config = yaml.safe_load((root / "src/nino_rl/config/combined_rough_section.yaml").read_text())
    metadata = json.loads((DESCRIPTION / "worlds/combined_rough_section.json").read_text())
    x, y, heights = rough_grid()
    norm = TwoSlopeNorm(vmin=min(-.17, heights.min()), vcenter=0., vmax=max(.25, heights.max()))
    fig, axes = plt.subplots(4, 2, figsize=(16, 24), constrained_layout=True)
    for axis, route in zip(axes.flat, config["routes"]["definitions"]):
        # Display sampling only: simulator collision mesh is unchanged.
        axis.pcolormesh(x[::3], y[::3], heights[::3, ::3], cmap="terrain", norm=norm,
                       shading="auto", rasterized=True)
        draw_goal_halls(axis, metadata)
        for label in axis.texts:
            if label.get_text() in ("NORTH GOAL HALL", "SOUTH GOAL HALL"):
                label.set_visible(False)  # Leave room for the goal IDs in each panel.
        points = np.asarray(route["waypoints"])
        length = np.linalg.norm(np.diff(points, axis=0), axis=1).sum()
        axis.plot(*points.T, color="#c71018", linewidth=2.5, zorder=11)
        axis.scatter(*points[0], color="#087ca5", edgecolors="white", s=65, zorder=12)
        axis.scatter(*points[-1], color="#c71018", edgecolors="white", s=150, marker="*", zorder=12)
        for before, after in zip(points[:-1], points[1:]):
            mid = .5 * (before + after)
            direction = (after - before) / np.linalg.norm(after - before)
            axis.annotate("", xy=mid + .15 * direction, xytext=mid - .15 * direction,
                          arrowprops=dict(arrowstyle="->", color="#c71018", lw=2), zorder=12)
        axis.set(title=f"Route {route['id']} — {length:.2f} m", xlabel="World x (m)", ylabel="World y (m)",
                 aspect="equal")
        axis.grid(alpha=.15)
    fig.suptitle("Eight configured rough-terrain routes from your drawings\n"
                 "Red: reference path • Blue: start • Red star: selected goal", fontsize=18)
    output = root / "docs/rough_routes_preview.png"
    fig.savefig(output, dpi=140)
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
