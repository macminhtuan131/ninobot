#!/usr/bin/env python3
"""Descriptive height-mechanism audit; keep failures/unattempted cases and all scores."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from audit_governor_contact_timing import stamp


def write(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")


def mechanism(row):
    if row.get("first_contact_s") is None:
        return dict(available=False,reason="first_contact_unavailable")
    case,tc=Path(row["case"]),row["first_contact_s"]
    logger=next(case.glob("contact/*/metadata.json")).parent
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    controls=list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))
    first={}
    for line in (logger/"contact_events.jsonl").open():
        event=json.loads(line)
        if event.get("named_positive_obstacle") and event["event"]=="begin" and tc-1e-9<=event["time_s"]<=tc+2.:
            first.setdefault(event["component"],event["time_s"])
    loaded={}
    caster={side:dict(rolling_rad_s=[],swivel_rad=[],floor_abs_vertical_wrench_N=[])
            for side in ("left","right")}
    body=[]
    for line in (logger/"samples.jsonl").open():
        packet=json.loads(line)
        topic,data=packet["topic"],packet["data"]
        if topic not in ("/joint_states","/ground_truth/odom") and not topic.startswith("/nino/contact_lab/"):continue
        t=stamp(data)
        if not tc-.3<=t<=tc+2.:continue
        before=tc-.3<=t<=tc-.05
        if topic=="/joint_states" and before:
            v=dict(zip(data["name"],data["velocity"]))
            p=dict(zip(data["name"],data["position"]))
            for side in caster:
                caster[side]["rolling_rad_s"].append(v[f"caster_{side}_wheel_joint"])
                caster[side]["swivel_rad"].append(p[f"caster_{side}_swivel_joint"])
        elif topic=="/ground_truth/odom" and before:
            body.append(data["twist"]["twist"]["linear"]["x"])
        elif topic.startswith("/nino/contact_lab/"):
            component=topic.rsplit("/",1)[-1]
            support=0.
            for contact in data["contacts"]:
                names=contact["collision1"]["name"]+contact["collision2"]["name"]
                if "cable_bumps" in names and t>=tc:
                    for depth,wrench in zip(contact["depths"],contact["wrenches"]):
                        f=wrench["body_1_wrench"]["force"]
                        if depth>0 and math.sqrt(sum(f[k]**2 for k in ("x","y","z")))>1e-6:
                            loaded[component]=min(t,loaded.get(component,t))
                if before and "terrain_collision" in names:
                    support+=sum(abs(w["body_1_wrench"]["force"]["z"]) for w in contact["wrenches"])
            for side in caster:
                if before and component==f"caster_{side}_wheel":
                    caster[side]["floor_abs_vertical_wrench_N"].append(support)
    stats={}
    for side,values in caster.items():
        stats[side]={name:dict(samples=len(series),median=statistics.median(series) if series else None,
                              minimum=min(series) if series else None,maximum=max(series) if series else None)
                     for name,series in values.items()}
    first_time=min(first.values()) if first else None
    loaded_time=min(loaded.values()) if loaded else None
    reduced=next((float(c["governor_input_time_s"]) for c in controls if float(c["governor_scale"])<.999),None)
    return dict(available=bool(first),first_manifold_components=[c for c,t in first.items() if abs(t-first_time)<1e-9],
        first_loaded_components=[c for c,t in loaded.items() if abs(t-loaded_time)<1e-9],
        first_loaded_after_manifold_s=loaded_time-tc if loaded_time is not None else None,
        first_manifold_by_component_after_first_s={c:t-tc for c,t in first.items()},
        first_loaded_by_component_after_first_s={c:t-tc for c,t in loaded.items()},
        precontact_body_median_m_s=statistics.median(body) if body else None,
        precontact_caster=stats,minimum_scale=min(float(c["governor_scale"]) for c in controls),
        maximum_event_count=max(int(c["governor_events"]) for c in controls),
        first_reduced_command_after_manifold_s=reduced-tc if reduced is not None else None,
        qualification="Sensor sampling, not exact first force instant; privileged contact/caster data are diagnostic only. Low caster rotation does not establish slip.")


def pair_ratios(rows):
    pairs=[]
    for height in (.006,.022):
        for seed in (77310,77311):
            arm={r["profile"]:r for r in rows if r["height_m"]==height and r["seed"]==seed}
            pair=dict(height_m=height,seed=seed,available=False,attempted_arms=list(arm))
            if set(arm)=={"full","reactive"} and all(r.get("reporting_pass") and r.get("physical_pass") for r in arm.values()):
                p,g=arm["full"],arm["reactive"]
                metrics={k:(p[k],g[k]) for k in ("time_s","physical_rmse_m","whole_vertical_rms","whole_vertical_peak")}
                metrics["crossing_vertical_rms"]=(p["crossing_vertical"]["rms"],g["crossing_vertical"]["rms"])
                for origin in ("gt_native","primary","shifted"):
                    for label,window,field in (("whole_slip_rms","whole_route","rms"),("crossing_slip2_per_m","crossing","slip_square_per_m")):
                        metrics[origin+"_"+label]=(p[origin][window][field],g[origin][window][field])
                pair.update(available=True,ratios={k:b/a if a is not None and b is not None and a>0 else None
                                                  for k,(a,b) in metrics.items()},
                            governor_events=g.get("mechanism",{}).get("maximum_event_count"))
                pair["slip_grid_ranking_reversal"]=any(
                    (pair["ratios"]["primary_"+key]-1)*(pair["ratios"]["shifted_"+key]-1)<0
                    for key in ("whole_slip_rms","crossing_slip2_per_m")
                    if pair["ratios"]["primary_"+key] is not None and pair["ratios"]["shifted_"+key] is not None)
            pairs.append(pair)
    return pairs


def plot_pairs(pairs,output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(10.5,6.5))
    for ax,key,title in zip(axes.flat,
        ("whole_vertical_rms","crossing_vertical_rms","gt_native_crossing_slip2_per_m","time_s"),
        ("Whole-route vertical RMS","Post-contact vertical RMS","Post-contact slip² integral/metre (GT stamps)","Completion time")):
        for i,pair in enumerate(pairs):
            value=pair.get("ratios",{}).get(key)
            color="#3378b3" if pair["height_m"]==.006 else "#c77b28"
            if value is None:ax.text(i,1.,"unavailable",rotation=90,fontsize=8,ha="center",va="bottom")
            else:
                ax.scatter([i],[value],color=color,s=50,zorder=3)
                ax.annotate(f"{value:.3f}",(i,value),xytext=(0,6),textcoords="offset points",ha="center",fontsize=8)
        ax.axhline(1.,color="#555555",ls="--",lw=1.)
        ax.set_xticks(range(len(pairs)),[f"{round(p['height_m']*1000):d} mm\n{p['seed']}" for p in pairs])
        ax.set_xlim(-.5,len(pairs)-.5)
        ax.margins(y=.25)
        ax.grid(alpha=.2)
        ax.set_ylabel("Governor / paired PI")
        ax.set_title(title,fontsize=10)
    fig.suptitle("Frozen controller, two ridge heights · n=2 paired cold starts per height",fontsize=12)
    fig.text(.5,.015,"Below 1 means a lower measured value. No confidence interval, score replacement, height selection or hardware claim.",ha="center",fontsize=8)
    fig.tight_layout(rect=(0,.04,1,.94))
    fig.savefig(output/"paired_comparison.png",dpi=160)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source=json.loads((args.run/"episodes.json").read_text())
    rows=[]
    for original in source:
        row=dict(original)
        try:row["mechanism"]=mechanism(row)
        except Exception as error:row["mechanism"]=dict(available=False,error=f"{type(error).__name__}: {error}")
        rows.append(row)
    pairs=pair_ratios(rows)
    write(args.output/"episodes.json",rows)
    write(args.output/"paired.json",pairs)
    write(args.output/"decision_snapshot.json",json.loads((args.run/"decision.json").read_text()))
    compact=[]
    for row in rows:
        m=row.get("mechanism",{})
        compact.append(dict(attempt=row["attempt"],height_mm=1000*row["height_m"],seed=row["seed"],profile=row["profile"],
            physical_success=row.get("physical_success"),physical_pass=row.get("physical_pass"),reporting_pass=row.get("reporting_pass"),
            first_manifold="+".join(m.get("first_manifold_components",[])) or None,
            first_loaded="+".join(m.get("first_loaded_components",[])) or None,
            time_s=row.get("time_s"),physical_rmse_m=row.get("physical_rmse_m"),
            whole_vertical_rms=row.get("whole_vertical_rms"),whole_vertical_peak=row.get("whole_vertical_peak"),
            crossing_vertical_rms=(row.get("crossing_vertical") or {}).get("rms"),
            gt_whole_slip_rms=(row.get("gt_native") or {}).get("whole_route",{}).get("rms"),
            gt_cross_slip2_per_m=(row.get("gt_native") or {}).get("crossing",{}).get("slip_square_per_m"),
            governor_events=m.get("maximum_event_count"),minimum_scale=m.get("minimum_scale")))
    with (args.output/"metrics.csv").open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(compact[0]))
        writer.writeheader();writer.writerows(compact)
    plot_pairs(pairs,args.output)
    print(json.dumps(compact,indent=2))
    print("PAIRS",json.dumps(pairs,indent=2))


if __name__=="__main__":main()
