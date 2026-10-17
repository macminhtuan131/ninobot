"""Raw timestamp responses from existing maneuvers, not a fitted plant model."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
data=json.loads((root/"response.json").read_text())
chosen=[e for e in data["events"] if (e["case"]=="accelerate" and e["target_m_s"]==.4)
        or (e["case"]=="brake_recover" and e["target_m_s"] in (.18,.4))]
fig,axes=plt.subplots(1,3,figsize=(13,4.3),sharey=True)
for ax,event in zip(axes,chosen):
    t0=event["command_time_s"]
    series=data["series"][event["case"]]
    for label,key,color,style in (("Executed reference","reference","#2670b9","--"),
                                  ("Left wheel target r·ω","left_target","#777777",":"),
                                  ("Left encoder r·ω","left_wheel","#379568","-"),
                                  ("Body (GT diagnostic)","body","#222222","-")):
        values=[(t-t0,v) for t,v in series[key] if -.2<=t-t0<=min(1.,event["end_time_s"]-t0)]
        ax.plot([t for t,v in values],[v for t,v in values],label=label,color=color,ls=style,lw=1.6)
    ax.axvline(0,color="#aaaaaa",lw=.8)
    ax.grid(alpha=.2)
    ax.set_xlim(-.15,.95)
    ax.set_title({("accelerate",.4):"Start → 0.40 m/s",("brake_recover",.18):"Brake: 0.40 → 0.18 m/s",("brake_recover",.4):"Recover: 0.18 → 0.40 m/s"}[(event["case"],event["target_m_s"])])
    ax.set_xlabel("Time after command (s)")
axes[0].set_ylabel("Speed / wheel tangential reference (m/s)")
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc="upper center",bbox_to_anchor=(.5,.94),ncol=4,fontsize=8)
fig.suptitle("Saved clear-floor response: command ≠ wheel target ≠ body speed",fontsize=13)
fig.text(.5,.015,"One saved maneuver per condition; original timestamps. No obstacle, no governor event, no hardware latency claim.",ha="center",fontsize=8)
fig.tight_layout(rect=(0,.05,1,.85))
fig.savefig(root/"response.png",dpi=160)
print(root/"response.png")
