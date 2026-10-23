#!/usr/bin/env python3
"""Audit saved contact positions against a deliberately generous robot envelope.

Contact headers omit frame_id. World-position interpretation is an explicit
diagnostic assumption, checked against ordinary floor contacts near the robot;
this is not a calibrated contact-force/impulse measurement.
"""
import argparse
import bisect
import csv
import json
from math import hypot
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from analyze_governor_experiment import stamp


def analyze(case, envelope_m=.75):
    case=Path(case)
    evaluation=next((case/"evaluation").glob("*/summary.json")).parent
    logger=next((case/"contact").glob("*/metadata.json")).parent
    traces=list(evaluation.glob("episode-*/control_trace.csv"))
    if not traces:
        return dict(case=str(case),available=False,reason="no_control_trace")
    trace=list(csv.DictReader(traces[0].open()))
    lo=float(trace[0]["governor_input_time_s"]); hi=float(trace[-1]["sim_time_s"])
    ground=[]; contacts=[]
    for line in (logger/"samples.jsonl").open():
        try: row=json.loads(line)
        except ValueError: continue
        data=row["data"]
        if "header" not in data: continue
        t=stamp(data)
        if not lo<=t<=hi: continue
        if row["topic"]=="/ground_truth/odom":
            p=data["pose"]["pose"]["position"]
            ground.append((t,p["x"],p["y"]))
        elif row["topic"].startswith("/nino/contact_lab/"):
            for contact in data["contacts"]:
                pair=[contact["collision1"]["name"],contact["collision2"]["name"]]
                positive=any("cable_bumps" in name or "training_cable" in name for name in pair)
                for p in contact["positions"]:
                    contacts.append((t,row["topic"].rsplit("/",1)[1],pair,positive,p))
    ground.sort(); times=[r[0] for r in ground]
    counts={"cable":0,"floor_or_other":0}; far=[]; maximum={"cable":0.,"floor_or_other":0.}; unaligned=0
    for t,component,pair,positive,p in contacts:
        at=bisect.bisect_left(times,t)
        candidates=[i for i in (at-1,at) if 0<=i<len(times)]
        if not candidates: unaligned+=1; continue
        i=min(candidates,key=lambda i:abs(times[i]-t))
        if abs(times[i]-t)>.025: unaligned+=1; continue
        distance=hypot(p["x"]-ground[i][1],p["y"]-ground[i][2])
        group="cable" if positive else "floor_or_other"
        counts[group]+=1
        maximum[group]=max(maximum[group],distance)
        if distance>envelope_m:
            far.append(dict(time_s=t,component=component,collisions=pair,positive_obstacle=positive,
                position=p,body_xy_m=ground[i][1:],horizontal_distance_m=distance))
    return dict(case=str(case),available=bool(ground),assumed_position_frame="world; message frame_id empty",
        diagnostic_body_disk_radius_m=envelope_m,point_counts=counts,unaligned_points=unaligned,
        maximum_horizontal_distance_m=maximum,distant_point_count=len(far),
        distant_positive_points=sum(r["positive_obstacle"] for r in far),
        distant_point_examples=far[:12],
        qualification="Positions beyond a generous .75m body disk are diagnostic anomalies, not proof of their engine/root cause. No force magnitude treated as whole-robot net force.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    results=[]
    for case in sorted(args.screen.glob("seed_*")):
        try: results.append(analyze(case))
        except Exception as error:
            results.append(dict(case=str(case),available=False,reason=f"{type(error).__name__}: {error}"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(results=results),indent=2,allow_nan=False)+"\n")
    print("Saved",args.output)


if __name__=="__main__": main()
