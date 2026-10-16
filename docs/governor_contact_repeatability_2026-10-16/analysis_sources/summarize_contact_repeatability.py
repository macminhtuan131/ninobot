#!/usr/bin/env python3
"""Summarize cold-start blocks without treating frames as independent trials."""
import argparse
import hashlib
from itertools import product
import json
from math import isfinite
from pathlib import Path
from statistics import mean


METRICS=("time_s", "truth_rmse_m", "first_50ms_peak", "postcontact_vertical_rms",
         "postcontact_vertical_peak", "postcontact_slip_energy_per_m",
         "whole_vertical_rms", "whole_slip_rms")


def exact_sign_flip(deltas):
    """Exploratory two-sided mean-difference test under within-block exchangeability."""
    if not deltas:
        return None
    observed=abs(mean(deltas))
    distribution=[abs(mean(s*d for s,d in zip(signs,deltas)))
                  for signs in product((-1,1),repeat=len(deltas))]
    return dict(n_blocks=len(deltas),observed_mean_delta=mean(deltas),
        favorable_blocks=sum(d<0 for d in deltas),ties=sum(d==0 for d in deltas),
        minimum_delta=min(deltas),maximum_delta=max(deltas),
        two_sided_p=sum(d>=observed-1.e-12 for d in distribution)/len(distribution),
        permutations=len(distribution))


def paired_metrics(episodes,seeds):
    output={}
    for metric in METRICS:
        pairs=[];missing=[]
        for seed in seeds:
            rows={r["profile"]:r for r in episodes if r["seed"]==seed}
            values=[rows.get(p,{}).get(metric) for p in ("full","moderate")]
            if any(v is None or not isfinite(v) for v in values):
                missing.append(seed)
                continue
            full,candidate=values
            # This prefix is a negative control only before intervention in both runs.
            if metric=="first_50ms_peak" and not all(
                    rows[p].get("first_50ms_uncontrolled") is True for p in ("full","moderate")):
                missing.append(seed)
                continue
            pairs.append(dict(seed=seed,full=full,moderate=candidate,delta=candidate-full))
        output[metric]=dict(requested_blocks=len(seeds),available_blocks=len(pairs),
            unavailable_or_ineligible_seeds=missing,pairs=pairs,
            exploratory_sign_flip=exact_sign_flip([p["delta"] for p in pairs]))
    return output


def plot_blocks(metrics,path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure,axes=plt.subplots(2,2,figsize=(10,7),constrained_layout=True)
    panels=(("postcontact_vertical_rms","Post-contact vertical RMS (m/s²)"),
            ("postcontact_vertical_peak","Post-contact sampled peak (m/s²)"),
            ("postcontact_slip_energy_per_m","Post-contact slip² integral/distance (s/m)"),
            ("time_s","Completion time (s)"))
    for ax,(key,label) in zip(axes.flat,panels):
        pairs=metrics[key]["pairs"]
        for i,pair in enumerate(pairs):
            ax.plot([i-.12,i+.12],[pair["full"],pair["moderate"]],color="0.7",linewidth=1,zorder=1)
        ax.scatter([i-.12 for i in range(len(pairs))],[p["full"] for p in pairs],
                   color="black",marker="o",label="Full PI",zorder=2)
        ax.scatter([i+.12 for i in range(len(pairs))],[p["moderate"] for p in pairs],
                   color="#1670b8",marker="s",label="Sensor governor",zorder=2)
        ax.set_xticks(range(len(pairs)),[str(p["seed"]) for p in pairs])
        ax.set_ylabel(label);ax.set_xlabel("Cold-start seed block")
        ax.grid(alpha=.25)
        if not pairs:ax.text(.5,.5,"Unavailable",ha="center",transform=ax.transAxes)
    axes[0,0].legend()
    figure.suptitle("Single rigid cable — fixed PI, sensor governor and physics\n"
        "Randomized order within five blocks; separate cold starts, not identical snapshots")
    figure.savefig(path,dpi=170)
    plt.close(figure)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen",type=Path,required=True)
    parser.add_argument("--crossing",type=Path,required=True)
    parser.add_argument("--timing",type=Path,required=True)
    parser.add_argument("--geometry",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    plan=json.loads((args.screen/"plan.json").read_text())
    crossing=json.loads(args.crossing.read_text())
    timing=json.loads(args.timing.read_text())
    geometry=json.loads(args.geometry.read_text())
    auxiliary=[]
    for seed in plan["seeds"]:
        for profile in plan["profiles"]:
            name=f"seed_{seed}_{profile}"
            row=next((r for r in crossing["episodes"] if r["seed"]==seed and r["profile"]==profile),{})
            observed=next((r for r in timing["results"] if Path(r["case"]).name==name),{})
            spatial=next((r for r in geometry["results"] if Path(r["case"]).name==name),{})
            auxiliary.append(dict(seed=seed,profile=profile,
                physical_success=row.get("physical_success"),stop_settled=row.get("stop_settled"),
                first_50ms_uncontrolled=row.get("first_50ms_uncontrolled"),
                timing=observed.get("timing"),precontact_caster=observed.get("precontact_caster"),
                distant_positive_points=spatial.get("distant_positive_points")))
    result=dict(protocol=plan,groups=crossing["groups"],
        block_metrics=paired_metrics(crossing["episodes"],plan["seeds"]),
        auxiliary=auxiliary,complete=crossing["complete"],
        same_world=crossing["same_world"],same_robot=crossing["same_robot"],
        same_core=crossing["same_core"],same_effort_drive=crossing.get("same_effort_drive"),
        same_resolved_config=crossing.get("same_resolved_config"),
        same_config_except_profile=crossing.get("same_config_except_profile"),
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (args.screen/"plan.json",args.crossing,args.timing,args.geometry)},
        qualification="Five randomized-order cold-start blocks, not identical snapshots or physical randomization. Sign flips are exploratory under within-block exchangeability, unadjusted across metrics. With five blocks minimum two-sided p is 0.0625. Missing metrics remain unavailable; native failures are retained. No automatic promotion or causal attribution from caster covariates.")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    plot_blocks(result["block_metrics"],args.output.with_name("paired_blocks.png"))
    print("Saved",args.output)


if __name__=="__main__":main()
