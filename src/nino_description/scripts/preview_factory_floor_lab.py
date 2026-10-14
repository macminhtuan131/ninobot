#!/usr/bin/env python3
"""Preview the restored six-cable corridor and real carved adaptive item."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Rectangle, Polygon, Circle
import numpy as np

from generate_factory_floor_lab import ROOT, REPO, depression_surface


def route_preview(data):
    """One panel per user-drawn route, with arrows indicating traversal order."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 12))
    floor = data["floor"]
    for ax, route in zip(axes.flat, data["drawn_routes"]):
        ax.set_facecolor("#b6c3b0")
        a,b,c,d = floor["terrain_view_bounds_xy_m"]
        ax.add_patch(Rectangle((a,c), b-a, d-c, facecolor="#a68564"))
        for item in data["cables"]:
            angle = np.deg2rad(item["angle_deg"])
            delta = np.array([-np.sin(angle), np.cos(angle)])*item["length_m"]/2
            center = np.array([item["x_m"], item["y_m"]])
            ax.plot(*np.array([center-delta, center+delta]).T,color="#313639",linewidth=1.5)
        for item in data["depressions"]:
            ax.add_patch(Ellipse((item["x_m"],item["y_m"]),2*item["radius_x_m"],
                2*item["radius_y_m"],angle=item["angle_deg"],facecolor="#b5d6e5",
                edgecolor="#175b86",linestyle=":"))
        for item in data.get("display_items",[]):
            if item["kind"] == "bump":
                ax.add_patch(Circle((item["x_m"],item["y_m"]),item["radius_m"],facecolor="#c6620b"))
            else:
                ax.plot([item["x_m"]]*2,
                        [item["y_m"]-item["length_m"]/2,item["y_m"]+item["length_m"]/2],
                        color="#242628",linewidth=2)
        points = np.asarray(route["waypoints"])
        ax.plot(*points.T,color="#c21d16",linewidth=2.7,zorder=5)
        for start, end in zip(points[:-1],points[1:]):
            delta = end-start
            ax.annotate("",xy=start+.65*delta,xytext=start+.40*delta,
                        arrowprops=dict(arrowstyle="->",color="#c21d16",lw=2),zorder=6)
        ax.scatter(*points[0],s=65,c="#367da7",edgecolors="white",zorder=7)
        for hall in data["goal_halls"]:
            gx,gy,_ = hall["goal_pose"]
            ax.scatter(gx,gy,s=100,marker="*",c="#27864f",edgecolors="white",zorder=7)
            ax.text(gx,gy+.25,hall["id"],ha="center",color="#245b37",fontweight="bold")
        length = np.linalg.norm(np.diff(points,axis=0),axis=1).sum()
        ax.set(xlim=floor["x_m"],ylim=floor["y_m"],xlabel="x (m)",ylabel="y (m)",
               title=f"{route['id']} — reference route ({length:.2f} m)")
        ax.set_aspect("equal",adjustable="box")
        ax.grid(alpha=.12)
    fig.suptitle("FACTORY COURSE • drawn routes to four goal halls",fontsize=16)
    fig.text(.5,.02,"Red lines are ordered references, not floor obstacles. Controller rounds corners locally.\n"
             "PI traversal and contact performance have not yet been validated in Gazebo.",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.96),h_pad=3.)
    output = REPO / "docs/factory_floor_routes_preview.png"
    fig.savefig(output,dpi=170)
    plt.close(fig)
    print(output)


def main():
    data = json.loads((ROOT / "worlds/factory_floor_mixed.json").read_text())
    floor, zone = data["floor"], data["adaptive_zone"]
    x = np.linspace(*floor["x_m"], 2001)
    y = np.linspace(*floor["y_m"], 1401)
    xx, yy = np.meshgrid(x, y)
    z = np.zeros_like(xx)
    for item in data["depressions"]:
        z = np.minimum(z,depression_surface(item,xx,yy))
    fig, (ax, profile) = plt.subplots(2, 1, figsize=(9, 9),
        gridspec_kw={"height_ratios": [4, 1]})
    ax.set_facecolor("#c2c5c8")
    ta,tb,tc,td = floor["terrain_view_bounds_xy_m"]
    ax.add_patch(Rectangle((ta,tc),tb-ta,td-tc,facecolor="#a68564",zorder=0))
    for hall in data["goal_halls"]:
        left,right,bottom,top = hall["bounds_xy_m"]
        ax.add_patch(Rectangle((left,bottom),right-left,top-bottom,
                              facecolor="#b6c3b0",zorder=0))
        label_y = bottom+.25 if hall["direction"] == "south" else top-.25
        ax.text((left+right)/2,label_y,f"{hall['direction'].upper()} GOAL HALL",
                ha="center",va="center",fontsize=9,color="#335940")
    a, b = zone["x_m"]
    c, d = zone["y_m"]
    ax.add_patch(Rectangle((a, c), b-a, d-c, facecolor="#d4bd80", alpha=.55,
                          edgecolor="#aa8140", linestyle="--", linewidth=1.7, zorder=1))
    ax.pcolormesh(x, y, np.ma.masked_where(z >= -1e-8, z), cmap="Blues_r",
                  vmin=-.03, vmax=0, shading="auto", rasterized=True, zorder=2)
    for i,item in enumerate(data["depressions"]):
        if item["kind"] == "groove":
            corners = np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*np.array([item["radius_x_m"],item["radius_y_m"]])
            angle = np.deg2rad(item["angle_deg"])
            rotation = np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            patch = Polygon(corners@rotation.T+np.array([item["x_m"],item["y_m"]]))
        else:
            patch = Ellipse((item["x_m"], item["y_m"]), 2*item["radius_x_m"],
                2*item["radius_y_m"], angle=item["angle_deg"])
        patch.set(fill=False,edgecolor="#175b86",linestyle=":",linewidth=1.8,zorder=4)
        ax.add_patch(patch)
        ax.text(item["x_m"], .87+.26*(i%2), f"{item['id']}: {item['depth_m']*1000:g} mm",
                ha="center", fontsize=9, color="#17476c")
    for item in data.get("display_items",[]):
        if item["kind"] == "bump":
            ax.add_patch(Circle((item["x_m"],item["y_m"]),item["radius_m"],facecolor="#c6620b",zorder=7))
        else:
            ax.plot([item["x_m"]]*2,[item["y_m"]-item["length_m"]/2,item["y_m"]+item["length_m"]/2],
                color="#242628",linewidth=3,zorder=7)
    for item in data["cables"]:
        angle = np.deg2rad(item["angle_deg"])
        dx = -np.sin(angle) * item["length_m"]/2
        dy = np.cos(angle) * item["length_m"]/2
        ax.plot([item["x_m"]-dx, item["x_m"]+dx], [item["y_m"]-dy, item["y_m"]+dy],
                color="#313639", linewidth=2.5, zorder=5)
        ax.text(item["x_m"], 1.77, f"{item['x_m']:.2f}", ha="center", va="center",
                bbox=dict(facecolor="white", edgecolor="none", alpha=.9, pad=4), zorder=6)
    start, goal = floor["start_xy_m"], floor["goal_xy_m"]
    ax.plot([start[0], goal[0]], [0, 0], ":", color="white", linewidth=2, zorder=3)
    ax.scatter([start[0]], [0], c="#367da7", edgecolors="white", s=100, zorder=8)
    for hall in data["goal_halls"]:
        gx,gy,_ = hall["goal_pose"]
        ax.scatter([gx],[gy],c="#27864f",edgecolors="white",marker="*",s=140,zorder=8)
        ax.text(gx,gy+.26,f"Goal {hall['id']}",ha="center",fontsize=10,
                color="#245b37",fontweight="bold",zorder=8)
    ax.text(start[0]+.1, -.38, "START", ha="left", fontweight="bold")
    ax.text((a+b)/2, -.65, "Runtime adaptive items: 1 to 6\nPotholes randomized between cables",
            ha="center", va="top", fontsize=10, color="#764b20", zorder=7)
    ax.set(xlim=(floor["x_m"][0]-.05,floor["x_m"][1]+.05),
           ylim=(floor["y_m"][0]-.05,floor["y_m"][1]+.05),
           xlabel="Local x (m)", ylabel="y (m)",
           title="FACTORY COURSE  •  four connected halls, one goal per hall")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks(np.arange(-2, 9))
    ax.set_yticks(np.arange(-3.5, 3.6, .5))
    for lateral, name in ((.171, "Left drive-wheel floor"), (-.171, "Right drive-wheel floor")):
        row = np.argmin(abs(y-lateral))
        profile.plot(x, z[row]*1000, linewidth=1.4, label=name)
    for item in data["cables"]:
        offsets = np.linspace(-item["radius_m"], item["radius_m"], 41)
        height = item["radius_m"] + np.sqrt(np.maximum(item["radius_m"]**2-offsets**2, 0))
        profile.plot(item["x_m"]+offsets, height*1000, color="#313639", linewidth=1.5)
    profile.axhline(0, color="#888", linewidth=.8)
    profile.set(xlim=(-.15, 6.75), ylim=(-32, 42), xlabel="Local x (m)", ylabel="Height (mm)",
                title="Physical floor depression and six cable cross-sections")
    profile.grid(alpha=.25)
    profile.legend(loc="upper right", fontsize=8)
    fig.text(.5, .025, "Dedicated terrain ground copied from rough; level background, sculpted shallow bowls and groove.\n"
             "Shown catalogue is for viewing. Runtime resets replace it with the selected stage's sampled items.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, 1))
    output = REPO / "docs/factory_floor_lab_preview.png"
    fig.savefig(output, dpi=170)
    plt.close(fig)
    print(output)
    route_preview(data)


if __name__ == "__main__":
    main()
