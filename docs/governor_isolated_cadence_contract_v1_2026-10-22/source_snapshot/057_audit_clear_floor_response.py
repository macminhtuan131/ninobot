#!/usr/bin/env python3
"""Read saved clean-floor maneuvers to separate reference, wheel target and body response.

No plant fitting, simulator calls, scoring changes or extrapolation to hardware.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_governor_contact_timing import first_sustained, stamp


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def analyze(probe, output):
    output.mkdir(parents=True, exist_ok=False)
    plan = json.loads((probe/"plan.json").read_text())
    summary = json.loads((probe/"summary.json").read_text())
    logger = Path(plan["logger"])
    protocol = dict(cases=["accelerate", "brake_recover"], fractions=[.1,.5,.9],
                    sustained_threshold_s=.04, maximum_gap_s=.025,
                    baseline_relative_s=[-.20,-.02], settling_band_m_s=.02,
                    settling_duration_s=.10, wheel_radius_m=.0625,
                    measurement="Original timestamps; no interpolation; threshold onset is retrospective",
                    budget_new_episodes=0, no_tuning=True, no_model_change=True)
    (output/"protocol_before_analysis.json").write_text(json.dumps(protocol,indent=2)+"\n")
    results = {r["case"]:r for r in summary["results"]}
    if not summary["complete"] or any(not r["complete"] or r["terminated"] for r in results.values()):
        raise ValueError("Incomplete/failing source batch must be reviewed, not omitted")
    bounds = {name:(results[name]["started_sim_s"], results[name]["started_sim_s"]+4.)
              for name in protocol["cases"]}
    samples = {name:dict(body=[], reference=[], left_target=[], right_target=[],
                         left_wheel=[], right_wheel=[]) for name in bounds}
    files = [probe/"plan.json", probe/"summary.json", probe/"config.yaml",
             logger/"samples.jsonl", logger/"metadata.json", logger/"contact_events.jsonl",
             logger/"robot_description.urdf"]
    unexpected_contact = []
    for line in (logger/"contact_events.jsonl").open():
        event = json.loads(line)
        if event.get("named_positive_obstacle") and any(a<=event["time_s"]<=b for a,b in bounds.values()):
            unexpected_contact.append(event)
    if unexpected_contact:
        raise ValueError("Obstacle contacts found in alleged clean-floor maneuvers")
    for line in (logger/"samples.jsonl").open():
        row=json.loads(line)
        topic,data=row["topic"],row["data"]
        if topic=="/nino_drive/diagnostics":
            labels=data["layout"]["dim"][0]["label"].split(",")
            values=dict(zip(labels,data["data"]))
            time=values["sim_time_s"]
        elif topic=="/ground_truth/odom":
            time=stamp(data)
        else:
            continue
        for name,(a,b) in bounds.items():
            if not a<=time<=b:
                continue
            if topic=="/ground_truth/odom":
                samples[name]["body"].append((time,data["twist"]["twist"]["linear"]["x"]))
            else:
                samples[name]["reference"].append((time,values["executed_linear_m_s"]))
                for side in ("left","right"):
                    for label,field in (("target","target"),("wheel","actual")):
                        samples[name][side+"_"+label].append((time,protocol["wheel_radius_m"]*values[side+"_"+field+"_rad_s"]))
    events=[]
    for name in protocol["cases"]:
        controls_path=probe/name/"trace.csv"
        files.extend([controls_path,probe/name/"result.json"])
        controls=list(csv.DictReader(controls_path.open()))
        for series in samples[name].values():
            series.sort()
        changes=[(float(r["governor_input_time_s"]),float(r["governor_requested_linear_m_s"]))
                 for i,r in enumerate(controls) if i>0 and
                 r["governor_requested_linear_m_s"]!=controls[i-1]["governor_requested_linear_m_s"]]
        for index,(time,target) in enumerate(changes):
            end=changes[index+1][0] if index+1<len(changes) else bounds[name][1]
            event=dict(case=name,command_time_s=time,command_after_reset_s=time-bounds[name][0],
                       target_m_s=target,end_time_s=end,response={})
            for label,series in samples[name].items():
                before=[v for t,v in series if time-.20<=t<=time-.02]
                if len(before)<5:
                    raise ValueError("Insufficient baseline: "+name+"/"+label)
                base=statistics.median(before)
                delta=target-base
                if abs(delta)<.02:
                    raise ValueError("Command transition too small for selected diagnostics")
                # first_sustained expects <= threshold; negate rising signals.
                sign=-1. if delta>0 else 1.
                thresholds={}
                signed=[(t,sign*v) for t,v in series]
                for fraction in protocol["fractions"]:
                    response=first_sustained(signed,sign*(base+fraction*delta),time,end,
                                             protocol["sustained_threshold_s"],protocol["maximum_gap_s"])
                    if response:
                        response.update(onset_after_command_s=response["begin_s"]-time,
                                        confirmation_after_command_s=response["confirmed_s"]-time)
                    thresholds[str(fraction)]=response
                settling=first_sustained([(t,abs(v-target)) for t,v in series],
                    protocol["settling_band_m_s"],time,end,protocol["settling_duration_s"],protocol["maximum_gap_s"])
                event["response"][label]=dict(baseline_m_s=base,thresholds=thresholds,
                                             settling=settling,
                                             max_gap_s=max((b[0]-a[0] for a,b in zip(series,series[1:])),default=None))
            events.append(event)
    manifest={str(p.resolve()):digest(p) for p in files}
    manifest[str(Path(__file__).resolve())]=digest(__file__)
    manifest[str(Path(__file__).with_name("audit_governor_contact_timing.py"))]=digest(
        Path(__file__).with_name("audit_governor_contact_timing.py"))
    metadata=json.loads((logger/"metadata.json").read_text())
    report=dict(events=events,series=samples,source_probe=str(probe),source_logger=str(logger),
                source_metadata=metadata,obstacle_contacts_in_windows=unexpected_contact,
                source_successes_are_arrivals=False,
                warning="This historical run has matching URDF/core but no complete saved PI code/parameter provenance. "
                        "Reference steps are not governor scale ramps. Do not add these delays to contact timing as a calibrated model.")
    (output/"response.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    (output/"input_sha256.json").write_text(json.dumps(manifest,indent=2)+"\n")
    for event in events:
        print(event["case"],round(event["command_after_reset_s"],3),event["target_m_s"],
              {label:{f:round(r["onset_after_command_s"],3) if r else None
                      for f,r in result["thresholds"].items()}
               for label,result in event["response"].items()})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    analyze(args.probe,args.output)
