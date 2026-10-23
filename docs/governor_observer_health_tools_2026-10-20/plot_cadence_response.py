"""Event-aligned new-batch traces. No resampling, filtering, gates or rescoring."""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series


def analyze(run,analysis,output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output.mkdir(parents=True,exist_ok=False)
    slots=json.loads((run/"ledger.json").read_text())["slots"]
    report=json.loads((analysis/"report.json").read_text())
    results=[]
    colors={"full":"#555555","reactive_100ms":"#1f77b4","reactive_20ms":"#d55e00"}
    for seed in (77600,77601):
        for repeat in (1,2):
            fig,axes=plt.subplots(4,1,figsize=(12,11),sharex=True,layout="constrained")
            entries=[]
            for slot in slots:
                if (slot["seed"],slot["repeat"])!=(seed,repeat):continue
                r=slot.get("result") or {};t=report["timing"].get(str(slot["attempt"]),{})
                tc=t.get("first_contact_s")
                entry=dict(attempt=slot["attempt"],arm=slot["arm"],available=False,
                           measurement_integrity_pass=r.get("measurement_integrity_pass"))
                entries.append(entry)
                if tc is None or not r.get("logger"):continue
                try:
                    data=load(Path(r["case"]),dict(seed=seed,profile=slot["profile"],
                        evaluation=r["evaluation"],logger=r["logger"]))
                    signal=gt_timestamp_series(data)
                    g=data["ground"];j=data["joints"]
                    drive=list(csv.DictReader(next(Path(r["evaluation"]).glob("episode-*/drive_trace.csv")).open()))
                    d=np.array([[float(row[k]) for k in ("sim_time_s","executed_linear_m_s",
                        "left_target_rad_s","right_target_rad_s","left_applied_nm","right_applied_nm")] for row in drive])
                    c=colors[slot["arm"]];name=slot["arm"]
                    for samples,axis,column,label in ((g,axes[0],1,name+" body"),):
                        mask=(samples[:,0]>=tc-.3)&(samples[:,0]<=tc+3.)
                        axis.plot(samples[mask,0]-tc,samples[mask,column],color=c,label=label,lw=1)
                    mask=(d[:,0]>=tc-.3)&(d[:,0]<=tc+3.)
                    axes[0].step(d[mask,0]-tc,d[mask,1],where="post",color=c,ls="--",alpha=.7,label=name+" executed ref")
                    m=(j[:,0]>=tc-.3)&(j[:,0]<=tc+3.)
                    axes[1].plot(j[m,0]-tc,.0625*(j[m,1]+j[m,2])/2,color=c,lw=.8,label=name+" wheel mean")
                    axes[1].step(d[mask,0]-tc,.0625*(d[mask,2]+d[mask,3])/2,where="post",color=c,ls="--",label=name+" target mean")
                    m=(signal["time"]>=tc-.3)&(signal["time"]<=tc+3.)
                    axes[2].plot(signal["time"][m]-tc,signal["q"][m],color=c,lw=1,label=name)
                    axes[3].plot(d[mask,0]-tc,d[mask,4],color=c,lw=.8,label=name+" left")
                    axes[3].plot(d[mask,0]-tc,d[mask,5],color=c,lw=.8,ls="--",label=name+" right")
                    publication=(t.get("first_executed") or {}).get("time_s")
                    if publication is not None:
                        for ax in axes:ax.axvline(publication-tc,color=c,ls=":",alpha=.6)
                    entry.update(available=True,first_contact_s=tc,command_publication_offset_s=
                        publication-tc if publication is not None else None,
                        response_snapshots=t.get("response_snapshots"),
                        native_or_quality_integrity_not_overridden=True)
                except (OSError,ValueError,KeyError,StopIteration) as error:
                    entry["reason"]=f"{type(error).__name__}: {error}"
            for ax in axes:
                ax.axvline(0,color="black",lw=1);ax.grid(alpha=.2)
                if ax.lines:ax.legend(fontsize=7,ncol=3)
            for ax,label in zip(axes,("Body / reference (m/s)","Wheel rim mean (m/s)","GT-aligned slip mean square","Applied torque command (Nm)")):
                ax.set_ylabel(label)
            axes[-1].set_xlabel("Seconds from this arm's first contact")
            fig.suptitle(f"Seed{seed}, repeat{repeat}: original saved samples, all in-window spikes\n"
                "Dashed: reference/right torque; dotted: first observed reduced drive publication. Contact states differ between runs.")
            path=output/f"seed_{seed}_repeat_{repeat}.png"
            fig.savefig(path,dpi=150);plt.close(fig)
            results.append(dict(seed=seed,repeat=repeat,arms=entries,figure=path.name))
    (output/"index.json").write_text(json.dumps(dict(triads=results,
        qualification="Descriptive plots use original sample times/values. Connecting lines are visualization, not interpolation for scoring. No onset threshold, causal motor latency estimate or new performance gate. Integrity failures remain excluded from valid quality claims, not hidden."),indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("run","analysis","output"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();analyze(a.run.resolve(),a.analysis.resolve(),a.output.resolve())
