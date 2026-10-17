"""Plot the two executed clean-floor ramps at original timestamps."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
rows=json.loads((root/"response.json").read_text())
fig,axes=plt.subplots(2,2,figsize=(12,6.5),sharex=True,sharey=True)
for row,axs in zip(rows,axes):
    for event,ax in zip(row["events"],axs):
        for key,label,color,style in (("body","Body (GT diagnostic)","#222222","-"),
                                      ("reference","Executed reference","#2865bd","--"),
                                      ("left_target","Left wheel target r·ω","#9561a1",":"),
                                      ("left_wheel","Left encoder r·ω","#408d5e","-"),
                                      ("right_wheel","Right encoder r·ω","#d68b28","-")):
            selected=[(t-event["time_s"],v) for t,v in row["series"][key]
                      if -.2<=t-event["time_s"]<=.85]
            ax.plot([t for t,v in selected],[v for t,v in selected],label=label,color=color,ls=style,lw=1.4)
        ax.axvline(0,color="#aaaaaa",lw=.8)
        ax.grid(alpha=.2)
        ax.set_xlim(-.1,.8)
        ax.set_title(f"Cold start {row['attempt']} · {event['name']}")
        ax.set_xlabel("Time after first ramp command (s)")
        ax.set_ylabel("Speed (m/s)")
handles,labels=axes[0,0].get_legend_handles_labels()
fig.legend(handles,labels,loc="upper center",bbox_to_anchor=(.5,.94),ncol=5,fontsize=8)
fig.suptitle("Current PI/robot executes the frozen governor ramp on clear floor",fontsize=13)
fig.text(.5,.015,"Two scripted maneuvers, not arrival/cable-quality validation. Original timestamps; no fitted motor delay or hardware claim.",ha="center",fontsize=8)
fig.tight_layout(rect=(0,.04,1,.88))
fig.savefig(root/"response.png",dpi=160)
print(root/"response.png")
