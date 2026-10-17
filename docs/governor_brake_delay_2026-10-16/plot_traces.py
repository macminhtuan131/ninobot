"""Saved-data figure: same first-manifold alignment, no resampling GT."""
from pathlib import Path
import csv
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series

out=Path(__file__).resolve().parent
rows=json.loads((out/"episodes.json").read_text())
colors=dict(full="#444444",frozen_reactive="#1676aa",delayed_200ms="#c35019")
fig,axes=plt.subplots(3,2,figsize=(12,8),sharex=True,constrained_layout=True)
for col,seed in enumerate((77320,77321)):
    for r in (r for r in rows if r["seed"]==seed and r.get("reporting_pass")):
        case=Path(r["case"])
        evaluation=next(case.glob("evaluation/*/summary.json")).parent
        logger=next(case.glob("contact/*/metadata.json")).parent
        d=load(case,dict(evaluation=str(evaluation),logger=str(logger),seed=seed,profile=r["profile"]))
        s=gt_timestamp_series(d)
        drive=list(csv.DictReader(next(evaluation.glob("episode-*/drive_trace.csv")).open()))
        origin=r["first_contact_s"]
        color=colors[r["arm"]]
        axes[0,col].plot([float(c["sim_time_s"])-origin for c in drive],
                         [float(c["executed_linear_m_s"]) for c in drive],color=color,label=r["arm"])
        axes[1,col].plot(d["ground"][:,0]-origin,d["ground"][:,1],color=color)
        axes[2,col].plot(s["time"]-origin,np.sqrt(s["q"]),color=color,lw=.9)
    axes[0,col].set_title(f"Seed {seed}; rigid 6 mm ridge")
    for ax in axes[:,col]:
        ax.set_xlim(-.3,2.5)
        ax.axvline(0.,color="black",ls=":",lw=.8)
        ax.grid(alpha=.2)
    axes[0,col].legend(fontsize=8)
    axes[2,col].set_xlabel("Time since each run's first manifold (s)")
axes[0,0].set_ylabel("Executed speed reference (m/s)")
axes[1,0].set_ylabel("GT body speed (m/s)")
axes[2,0].set_ylabel("GT-aligned slip RMS proxy")
fig.suptitle("200 ms timing hypothesis: paired cold starts, not identical-state branches")
fig.savefig(out/"event_aligned_traces.png",dpi=160)
