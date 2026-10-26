#!/usr/bin/env python3
"""Offline detector replay on clean-floor maneuvers. No control or tuning."""
import argparse
import csv
from dataclasses import asdict,fields,replace
import json
from math import remainder,pi,isfinite
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl")]
from nino_control.governor_core import GovernorFrame,GovernorSettings,ReactiveGovernor
from nino_rl.core import load_config


def finite_max(rows,key):
    values=[]
    for row in rows:
        try: value=float(row.get(key,""))
        except (TypeError,ValueError): continue
        if isfinite(value): values.append(value)
    return max(values) if values else None


def contact_health(path):
    """Diagnostic ground truth stays outside the governor input boundary."""
    import numpy as np
    path=Path(path)
    if not (path/"metadata.json").is_file():
        candidates=list(path.glob("*/metadata.json"))
        if not candidates: raise ValueError("No contact logger at "+str(path))
        path=max(candidates,key=lambda item:item.stat().st_mtime).parent
    groups={}
    def stamp(data):
        value=data["header"]["stamp"]
        return value["sec"]+value["nanosec"]*1e-9
    for line in (path/"samples.jsonl").open():
        try: row=json.loads(line)
        except ValueError: continue
        eid=row.get("episode")
        if not eid: continue
        data=row["data"]; topic=row["topic"]
        group=groups.setdefault(eid,dict(case=None,ground=[],joints=[],contacts={}))
        if topic=="/nino/governor/episode" and data.get("event")=="probe_end":
            group["case"]=data["result"]["case"]
        elif topic=="/ground_truth/odom":
            group["ground"].append((stamp(data),data["twist"]["twist"]["linear"]["x"],
                data["twist"]["twist"]["angular"]["z"],data["pose"]["pose"]["position"]["z"]))
        elif topic=="/joint_states":
            group["joints"].append((stamp(data),dict(zip(data["name"],data["velocity"])),
                                   dict(zip(data["name"],data["position"]))))
        elif topic.startswith("/nino/contact_lab/"):
            component=topic.rsplit("/",1)[-1]
            values=group["contacts"].setdefault(component,dict(messages=0,maximum_depth_m=None,peak_abs_force_z_N=None))
            values["messages"]+=1
            for contact in data["contacts"]:
                for depth in contact["depths"]:
                    if depth is not None and isfinite(depth):
                        values["maximum_depth_m"]=max(values["maximum_depth_m"] or 0.,depth)
                for wrench in contact["wrenches"]:
                    force=wrench["body_1_wrench"]["force"]["z"]
                    if force is not None and isfinite(force):
                        values["peak_abs_force_z_N"]=max(values["peak_abs_force_z_N"] or 0.,abs(force))
    results=[]
    for eid,group in groups.items():
        ground=np.asarray(group["ground"],dtype=float)
        if not len(ground) or not group["case"]: continue
        ratios={side:[] for side in ("left","right")}
        for when,velocity,position in group["joints"]:
            nearest=int(np.argmin(np.abs(ground[:,0]-when)))
            if abs(ground[nearest,0]-when)>.05: continue
            speed,yawrate=ground[nearest,1:3]
            if speed<=.25 or abs(yawrate)>.05: continue
            for side in ratios:
                if abs(remainder(position[f"caster_{side}_swivel_joint"],2*pi))>.15: continue
                ratios[side].append(abs(velocity[f"caster_{side}_wheel_joint"])*.016/speed)
        results.append(dict(episode=eid,case=group["case"],
            caster_rolling_ratio={side:dict(samples=len(values),median=float(np.median(values)) if values else None)
                                  for side,values in ratios.items()},
            vertical_position_span_m=float(np.ptp(ground[:,3])),contacts=group["contacts"]))
    return dict(source=str(path),logger_closed=json.loads((path/"metadata.json").read_text()).get("complete",False),
        assumptions="Rolling ratio only when body speed >0.25 m/s, yaw rate <0.05 rad/s, swivel aligned within0.15 rad; simulator diagnostics, not a calibrated slip measurement",
        results=results)


def replay(rows,settings):
    governor=ReactiveGovernor(settings)
    events=[]
    previous=0
    for row in rows:
        try:
            frame=GovernorFrame(**{field.name:float(row[field.name]) for field in fields(GovernorFrame)})
            decision=governor.update(frame,float(row["dt"]),float(row["governor_requested_linear_m_s"]),
                                     float(row["governor_requested_yaw_rad_s"]))
        except (KeyError,TypeError,ValueError) as error:
            return dict(available=False,events=events,event_count=None,fault="missing_or_invalid_trace",error=str(error))
        if decision["phase"]=="FAILSAFE":
            return dict(available=False,events=events,event_count=None,fault=decision["fault"])
        if decision["events"]>previous:
            sources=[]
            if decision.get("filtered_vertical_m_s2",0)>=settings.vertical_trigger_m_s2: sources.append("vertical")
            if frame.body_rate_rad_s>=settings.body_rate_trigger_rad_s: sources.append("body_rate")
            if decision.get("wheel_error_m_s",0)>=decision.get("wheel_error_threshold_m_s",float("inf")):
                sources.append("wheel_error")
            events.append(dict(elapsed_s=float(row["elapsed_s"]),sources=sources,
                vertical_rms_m_s2=frame.vertical_rms_m_s2,vertical_peak_m_s2=frame.vertical_peak_m_s2,
                body_rate_rad_s=frame.body_rate_rad_s))
        previous=decision["events"]
    return dict(available=True,events=events,event_count=len(events),fault=governor.fault)


def audit(directory):
    directory=Path(directory)
    if not (directory/"summary.json").is_file():
        candidates=list(directory.glob("*/summary.json"))
        if not candidates: raise ValueError("No probe summary at "+str(directory))
        directory=max(candidates,key=lambda item:item.stat().st_mtime).parent
    summary=json.loads((directory/"summary.json").read_text())
    config=load_config(directory/"config.yaml")
    original=GovernorSettings(**{**config["governor"]["parameters"],"profile":"reactive"})
    # A small declared diagnostic comparison, not a search over the test bank.
    candidates={"original":original,
                "confirmation_020":replace(original,confirmation_seconds=.20),
                "confirmation_030":replace(original,confirmation_seconds=.30)}
    results=[]
    for result in summary["results"]:
        path=directory/result["case"]/"trace.csv"
        rows=list(csv.DictReader(path.open()))
        results.append(dict(case=result["case"],steps=len(rows),complete=result["complete"],
            physically_terminated=result["terminated"],termination=result["termination"],
            maximum_interval_vertical_peak_m_s2=finite_max(rows,"vertical_peak_m_s2"),
            maximum_interval_vertical_rms_m_s2=finite_max(rows,"vertical_rms_m_s2"),
            replays={name:replay(rows,settings) for name,settings in candidates.items()}))
    complete=bool(summary["complete"] and len(results)==3 and
                  all(row["complete"] and not row["physically_terminated"] for row in results))
    return dict(qualification="Offline shadow replay; changed actions were not physically executed",
        source=str(directory),complete_clean_floor_screen=complete,
        candidate_parameters={name:asdict(settings) for name,settings in candidates.items()},
        any_candidate_release=False,physical_arrival_validated=False,
        positive_contact_detection_validated=False,H2_validated=False,training_started=False,optuna_started=False,
        results=results,
        next="A candidate needs closed-loop clean-floor confirmation and positive-contact detection before H2.")


def report(data):
    lines=["# Governor clean-floor diagnostic", "",data["qualification"],"",
        "Full-speed runs physically executed; reactive decisions below are offline replay, not new motor commands.","",
        "| Maneuver | Steps | Max interval peak m/s² | Original events | Confirm .20 s | Confirm .30 s | Physical termination |",
        "|---|---:|---:|---:|---:|---:|---|"]
    for row in data["results"]:
        counts=[row["replays"][name]["event_count"] for name in ("original","confirmation_020","confirmation_030")]
        peak=row["maximum_interval_vertical_peak_m_s2"]
        peak_text=f"{peak:.3f}" if peak is not None else "unavailable"
        lines.append(f"| {row['case']} | {row['steps']} | {peak_text} | "
                     +" | ".join(str(value) if value is not None else "unavailable" for value in counts)+f" | {row['termination'] or 'none'} |")
    if "contact_health" in data:
        lines += ["","## Contact/rolling diagnostics","",data["contact_health"]["assumptions"],"",
                  "| Maneuver | Left median | Right median |","|---|---:|---:|"]
        for row in data["contact_health"]["results"]:
            values=[row["caster_rolling_ratio"][side]["median"] for side in ("left","right")]
            lines.append("| "+row["case"]+" | "+" | ".join(f"{value:.3f}" if value is not None else "unavailable" for value in values)+" |")
    lines += ["","No physical arrival, positive-contact detection, H2, training or Optuna release is claimed.",
              data["next"],""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--logger",type=Path)
    args=parser.parse_args()
    data=audit(args.directory)
    if args.logger: data["contact_health"]=contact_health(args.logger)
    output=args.output or Path(data["source"])/"detector_audit.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
    output.with_suffix(".md").write_text(report(data))
    print("Saved "+str(output)+" and "+str(output.with_suffix(".md")))


if __name__=="__main__": main()
