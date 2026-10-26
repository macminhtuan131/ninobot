#!/usr/bin/env python3
"""PI-vs-PI repeatability review; no candidate selection, simulation or rescore."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from prepare_governor_contact_sequence import angle_delta


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def balance(sequence):
    if not sequence.get("available"):return dict(available=False)
    a=sequence["approach"]
    maximum=lambda k:max(abs(a[k]["minimum"]),abs(a[k]["maximum"]))
    flags=dict(speed=a["v"]["minimum"]>=.39 and a["v"]["maximum"]<=.41,
        lateral=maximum("y")<=.01,yaw=maximum("yaw")<=math.radians(2.),
        tilt=max(maximum("roll"),maximum("pitch"))<=math.radians(2.),coverage=a["coverage_fraction"]>=.98)
    return dict(available=True,checks=flags,passed=all(flags.values()))


def metrics(r):
    d={k:r[k] for k in ("time_s","physical_rmse_m","whole_vertical_rms","whole_vertical_peak","native_slip_rms")}
    d.update(crossing_vertical_rms=r["crossing_vertical"]["rms"],
        GT_whole_slip_rms=r["gt_native"]["whole_route"]["rms"],GT_crossing_slip2_per_m=r["gt_native"]["crossing"]["slip_square_per_m"])
    for name,values in r["sequence"]["metrics"].items():
        if "slip" in values:
            for k in ("slip_square_integral_s","slip_square_per_m"):
                d[name+"_"+k]=values["slip"].get(k)
            for k in ("rms","peak","p95_abs"):d[name+"_vertical_"+k]=values["vertical"].get(k)
    d["contact_end_relative_s"]=r["sequence"]["windows"]["contact_end_s"]-r["first_contact_s"]
    d["recovery_confirmed_relative_s"]=(r["sequence"]["windows"]["recovery_end_s"]-r["first_contact_s"]
        if r["sequence"]["windows"].get("recovery_available") else None)
    return d


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    rows=json.loads((args.run/"episodes.json").read_text())
    for r in rows:
        r["approach_balance"]=balance(r.get("sequence",{}))
        if r.get("reset_gate_pass"):
            g=r["reset_gate"]
            r["reset_gate_review"]=dict(samples=len(g["samples"]),wait_sim_seconds=g["wait_sim_seconds"],
                quiet_duration_s=g["released_sim_s"]-g["quiet_start_s"],
                all_samples_post_reset=all(min(s[k] for k in ("ground_stamp_s","joint_stamp_s","imu_stamp_s","odom_stamp_s","feedback_stamp_s"))>g["reset_boundary_s"] for s in g["samples"]),
                zero_commands=all(max(abs(s[k]) for k in ("command_v","command_w","executed_v","executed_w"))<=1e-12 for s in g["samples"]))
    pairs=[]
    for seed in (77400,77401):
        selected={r["repeat"]:r for r in rows if r["seed"]==seed}
        pair=dict(seed=seed,available=False,attempted_repeats=list(selected))
        if set(selected)=={1,2} and all(r.get("reporting_pass") and r.get("sequence",{}).get("available") for r in selected.values()):
            a,b=selected[1],selected[2];aa,bb=a["sequence"]["approach"],b["sequence"]["approach"]
            dv=abs(aa["v"]["median"]-bb["v"]["median"]);dy=abs(aa["y"]["median"]-bb["y"]["median"])
            da=abs(angle_delta(aa["yaw"]["median"],bb["yaw"]["median"]))
            first,last=metrics(a),metrics(b)
            pair.update(available=True,coarse_approach_balance=dv<=.005 and dy<=.005 and da<=math.radians(1.),
                speed_difference_m_s=dv,lateral_difference_m=dy,yaw_difference_deg=math.degrees(da),
                differences={k:dict(repeat1=first[k],repeat2=last[k],repeat2_minus_repeat1=last[k]-first[k],
                    repeat2_over_repeat1=last[k]/first[k] if first[k]!=0 else None,
                    observed_max_over_min=max(first[k],last[k])/min(first[k],last[k]) if min(first[k],last[k])>0 else None)
                    for k in first if first[k] is not None and last[k] is not None},
                qualification="Two cold starts perseed; descriptive ranges, not a variance estimate, confidence interval, or identical-state branch.")
        pairs.append(pair)
    ready=len(rows)==4 and all(r.get("physical_pass") and r.get("reporting_pass") and r.get("reset_gate_pass") for r in rows)
    balanced=ready and all(r["approach_balance"].get("passed") for r in rows) and all(p.get("coarse_approach_balance") for p in pairs)
    guard=json.loads((args.run/"preservation_before.json").read_text())
    changed=[p for p,h in guard.items() if not Path(p).is_file() or sha(Path(p))!=h]
    decision=dict(status="batch_incomplete_or_failed_stop_no_retry" if not ready else
        "approach_balance_failed_stop_intervention_planning" if not balanced else
        "readiness_and_coarse_balance_passed_review_PI_ranges_before_new_intervention",
        attempted=len(rows),completed=sum(bool(r.get("physical_pass")) for r in rows),readiness_and_reporting_pass=ready,
        coarse_balance_pass=balanced,changed_protected=changed,protected_files=len(guard),
        new_intervention_selected=False,smallest_worthwhile_effect_fixed=False,
        why_no_automatic_candidate="Four PI runs only bound observed variability; application mechanical/production tolerance is not supplied. Do not manufacture a 10-15% threshold or confidence interval.",
        delay_200ms_rejected=True,detector_changed=False,native_scoring_changed=False,study_scores_changed=False,
        extra_simulation_episodes=0,training_started=False,predictor_started=False,optuna_started=False)
    write(out/"episodes.json",rows);write(out/"PI_pairs.json",pairs);write(out/"decision.json",decision)
    print(json.dumps(dict(decision=decision,pairs=pairs),indent=2))


if __name__=="__main__":main()
