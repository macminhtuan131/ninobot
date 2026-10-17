"""Plot saved timestamps, without resampling or modifying metrics."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
episodes = json.loads((root / "timing.json").read_text())
fig, axes = plt.subplots(2, 2, figsize=(13, 7.5), sharex=True, sharey=True)
for ax, row in zip(axes.flat, episodes):
    tc = row["first_manifold_s"]
    for name, series, color, width in (
        ("Body (GT; diagnostic)", row["series"]["body"], "#222222", 1.7),
        ("Left wheel r·ω", row["series"]["wheels"]["left"], "#db8a16", .9),
        ("Right wheel r·ω", row["series"]["wheels"]["right"], "#41975d", .9),
    ):
        ax.plot([t-tc for t,v in series], [v for t,v in series], color=color, lw=width, label=name)
    command = row["series"]["executed_command"]
    ax.step([t-tc for t,v in command], [v for t,v in command], where="post",
            lw=1.6, ls="--", color="#2865bd", label="Executed speed reference")
    ax.axvline(0, color="#444444", lw=.8)
    for milestone in row["milestones"]:
        component = milestone["component"]
        if component in ("left_wheel", "right_wheel"):
            x = milestone["after_first_manifold_s"]
            ax.axvline(x, color="#765c9b", lw=.9, ls=":")
            ax.text(x+.008, .94, component.split("_")[0]+" drive contact", rotation=90,
                    fontsize=7, va="top", color="#765c9b")
    if row["reduced_command_time_s"] is not None:
        ax.axvline(row["reduced_command_time_s"]-tc, color="#2865bd", ls=":", lw=1)
    controller = "Governor" if row["profile"] == "reactive" else "Fixed PI"
    ax.set_title(f"Repeat {row['repeat']} · {controller} · attempt {row['attempt']}", fontsize=11)
    ax.set_xlim(-.25, 1.5)
    ax.set_ylim(-.1, 1.)
    ax.grid(alpha=.18)
    ax.set_xlabel("Time from first named obstacle manifold (s)")
    ax.set_ylabel("Speed (m/s)")
handles, labels = axes[0, 0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .94), ncol=4, fontsize=9)
fig.suptitle("Body speed drops in governor and fixed-PI runs", fontsize=15)
fig.text(.5, .015, "Original timestamps; no interpolation. Wheel r·ω is not body speed. Cold starts are not identical-state branches.",
         ha="center", fontsize=9)
fig.tight_layout(rect=(0, .04, 1, .89))
fig.savefig(root/"contact_timing.png", dpi=160)
print(root/"contact_timing.png")
