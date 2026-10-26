#!/usr/bin/env python3
"""Audit both bounded ramp maneuvers; no implicit retry or policy promotion."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_governor_contact_timing import first_sustained, stamp


def write(path, data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    attempts=json.loads((args.run/"attempts.json").read_text())
    protocol=json.loads((args.run/"protocol_before_results.json").read_text())
    if len(attempts)!=2 or not all(a["passed"] for a in attempts):
        raise ValueError("Incomplete/failing attempts must be reviewed, not silently dropped")
    # Fixed descriptive diagnostics, not new controller or deployment gates.
    write(args.output/"analysis_protocol.json",dict(threshold_fractions=[.1,.5,.9],sustained_s=.04,
        max_gap_s=.025,baseline_seconds_before_event=[-.30,-.05],events=["brake_7s","recover_8s"],
        final_stop_window_seconds=[11.,12.],qualification="Timing arithmetic only; baseline availability and gaps reported, no H2 promotion"))
    inputs=[args.run/"attempts.json",args.run/"protocol_before_results.json",args.run/"config.yaml"]
    results=[]
    for attempt in attempts:
        logger=Path(attempt["logger"])
        summary_path=Path(attempt["summary"])
        summary=json.loads(summary_path.read_text())
        probe=summary["results"][0]
        t0=probe["started_sim_s"]
        series={label:[] for label in ("body","reference","left_target","right_target","left_wheel","right_wheel")}
        ground=[]
        positive=[]
        for line in (logger/"contact_events.jsonl").open():
            event=json.loads(line)
            if t0<=event["time_s"]<=t0+12. and event.get("named_positive_obstacle"):
                positive.append(event)
        for line in (logger/"samples.jsonl").open():
            row=json.loads(line)
            topic,data=row["topic"],row["data"]
            if topic=="/ground_truth/odom":
                time=stamp(data)
                if not t0<=time<=t0+12.:continue
                series["body"].append((time,data["twist"]["twist"]["linear"]["x"]))
                ground.append((time,data["pose"]["pose"]["position"],data["pose"]["pose"]["orientation"]))
            elif topic=="/nino_drive/diagnostics":
                values=dict(zip(data["layout"]["dim"][0]["label"].split(","),data["data"]))
                time=values["sim_time_s"]
                if not t0<=time<=t0+12.:continue
                series["reference"].append((time,values["executed_linear_m_s"]))
                for side in ("left","right"):
                    for label,field in (("target","target"),("wheel","actual")):
                        series[side+"_"+label].append((time,.0625*values[side+"_"+field+"_rad_s"]))
        for values in series.values():values.sort()
        control_path=next(summary_path.parent.glob("matched_governor_ramp/trace.csv"))
        controls=list(csv.DictReader(control_path.open()))
        changes=[(float(c["governor_input_time_s"]),float(c["governor_requested_linear_m_s"]))
                 for i,c in enumerate(controls) if i==0 or c["governor_requested_linear_m_s"]!=controls[i-1]["governor_requested_linear_m_s"]]
        expected=[(0.,.4),(7.,.384),(7.1,.368),(7.2,.36),(8.,.376),(8.1,.392),(8.2,.4),(10.,0.)]
        schedule_matches=len(changes)==len(expected) and all(abs(t-t0-x)<1e-8 and abs(v-y)<1e-8
            for (t,v),(x,y) in zip(changes,expected))
        events=[]
        for name,offset,target,end in (("brake",7.,.36,8.),("recover",8.,.4,10.)):
            event=dict(name=name,time_s=t0+offset,target_m_s=target,response={})
            for label,values in series.items():
                baseline=[v for t,v in values if t0+offset-.30<=t<=t0+offset-.05]
                if len(baseline)<5:raise ValueError("Insufficient baseline "+label)
                base=statistics.median(baseline)
                sign=1. if target<base else -1.
                responses={}
                for fraction in (.1,.5,.9):
                    response=first_sustained([(t,sign*v) for t,v in values],sign*(base+fraction*(target-base)),
                                              t0+offset,t0+end,.04,.025)
                    if response:
                        response.update(onset_after_command_s=response["begin_s"]-t0-offset,
                                        confirmation_after_command_s=response["confirmed_s"]-t0-offset)
                    responses[str(fraction)]=response
                event["response"][label]=dict(baseline_m_s=base,baseline_span_m_s=max(baseline)-min(baseline),
                                             baseline_samples=len(baseline),fractional_change=responses)
            events.append(event)
        final=[(t,v) for t,v in series["body"] if t0+11.<=t<=t0+12.]
        positions=sorted((t,pos) for t,pos,q in ground if t0+11.<=t<=t0+12.)
        stop=dict(samples=len(final),coverage_s=final[-1][0]-final[0][0] if len(final)>1 else 0.,
                  maximum_abs_body_speed_m_s=max((abs(v) for t,v in final),default=None),
                  displacement_from_first_sample_max_m=max((math.dist(tuple(p[k] for k in ("x","y","z")),
                      tuple(positions[0][1][k] for k in ("x","y","z"))) for t,p in positions),default=None))
        stop["available"]=len(final)>=40 and stop["coverage_s"]>=.95
        stop["within_20mm_20mmps_diagnostic"]=bool(stop["available"] and stop["maximum_abs_body_speed_m_s"]<=.02
            and stop["displacement_from_first_sample_max_m"]<=.02)
        metadata=json.loads((logger/"metadata.json").read_text())
        results.append(dict(attempt=attempt["attempt"],seed=attempt["seed"],start_s=t0,events=events,series=series,
            schedule_matches=schedule_matches,obstacle_contacts=positive,stop=stop,
            robot_description_sha256=sha(logger/"robot_description.urdf"),logger_complete=metadata["complete"],
            raw_sample_gaps_s={k:max((b[0]-a[0] for a,b in zip(v,v[1:])),default=None) for k,v in series.items()},
            clock_error_s=probe["clock_error_s"]))
        inputs.extend([summary_path,control_path,logger/"metadata.json",logger/"samples.jsonl",
                       logger/"contact_events.jsonl",logger/"robot_description.urdf"])
    sources_unchanged=all(sha(path)==digest for path,digest in protocol["source_sha256"].items())
    same_robot=len({r["robot_description_sha256"] for r in results})==1
    decision=dict(exactly_two_attempts=True,source_hashes_unchanged=sources_unchanged,same_robot=same_robot,
        matching_previous_contact_robot=all(r["robot_description_sha256"]=="6e74ef55720b5878ddca1c60fe6a7b4e5d82b7a68aa4934d2d1a026451c4878b" for r in results),
        both_schedules_match=all(r["schedule_matches"] for r in results),
        both_logs_closed=all(r["logger_complete"] for r in results),
        no_obstacle_contacts=all(not r["obstacle_contacts"] for r in results),
        raw_gaps_within_25ms=all(gap is not None and gap<=.025 for r in results for gap in r["raw_sample_gaps_s"].values()),
        final_stop_diagnostic_pass=all(r["stop"]["within_20mm_20mmps_diagnostic"] for r in results),
        H2_quality_validated=False,hardware_verified=False,controller_change_selected=False,
        no_extra_attempts=True,no_tuning=True)
    write(args.output/"response.json",results)
    write(args.output/"verification.json",decision)
    inputs.extend([Path(__file__).resolve(),Path(__file__).with_name("audit_governor_contact_timing.py")])
    write(args.output/"input_sha256.json",{str(path.resolve()):sha(path) for path in inputs})
    print(json.dumps(decision,indent=2))
    for r in results:
        print("ATTEMPT",r["attempt"],"stop",r["stop"])
        for e in r["events"]:
            print(e["name"],"body baseline",e["response"]["body"]["baseline_m_s"],
                {k:{f:round(v["onset_after_command_s"],3) if v else None
                    for f,v in d["fractional_change"].items()} for k,d in e["response"].items()})


if __name__=="__main__":main()
