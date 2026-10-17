#!/usr/bin/env python3
"""Offline event context for the two readiness runs; no outcome modification."""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/"src/nino_rl"), str(ROOT/"src/nino_control")]
from nino_control.governor_core import quaternion_rpy, vertical_acceleration
from analyze_governor_experiment import stamp


def audit(case, outcome):
    logger = next(case.glob("contact/*/metadata.json")).parent
    evaluation = next(case.glob("evaluation/*/summary.json")).parent
    controls = list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))
    drives = list(csv.DictReader(next(evaluation.glob("episode-*/drive_trace.csv")).open()))
    start = float(controls[0]["governor_input_time_s"])
    end = float(controls[-1]["sim_time_s"])
    imu, ground, joints = [], [], []
    for line in (logger/"samples.jsonl").open():
        row = json.loads(line)
        d = row["data"]
        if row["topic"] not in ("/imu/data", "/ground_truth/odom", "/joint_states"):
            continue
        t = stamp(d)
        if not start <= t <= end:
            continue
        if row["topic"] == "/imu/data":
            roll, pitch, _ = quaternion_rpy(tuple(d["orientation"][k] for k in ("x", "y", "z", "w")))
            a = tuple(d["linear_acceleration"][k] for k in ("x", "y", "z"))
            imu.append(dict(time_s=t, vertical_m_s2=vertical_acceleration(a, roll, pitch, True),
                            linear_acceleration=a, roll_rad=roll, pitch_rad=pitch))
        elif row["topic"] == "/ground_truth/odom":
            ground.append(dict(time_s=t, position=d["pose"]["pose"]["position"],
                               twist=d["twist"]["twist"]))
        else:
            joints.append(dict(time_s=t, positions=dict(zip(d["name"], d["position"])),
                               velocities=dict(zip(d["name"], d["velocity"]))))
    peak = max(imu, key=lambda v: abs(v["vertical_m_s2"]))
    tp = peak["time_s"]
    command = max((r for r in controls if float(r["governor_input_time_s"]) <= tp),
                  key=lambda r: float(r["governor_input_time_s"]))
    contact_samples = []
    for line in (logger/"samples.jsonl").open():
        row = json.loads(line)
        if not row["topic"].startswith("/nino/contact_lab/"):
            continue
        d = row["data"]
        t = stamp(d)
        if not tp-.05 <= t <= tp+.05:
            continue
        for c in d["contacts"]:
            forces = [w["body_1_wrench"]["force"] for w in c["wrenches"]]
            contact_samples.append(dict(time_s=t, component=row["topic"].rsplit("/",1)[-1],
                collisions=[c["collision1"]["name"],c["collision2"]["name"]],
                maximum_depth_m=max(c["depths"], default=None),
                maximum_force_norm_N=max((float(np.linalg.norm([f[k] for k in ("x","y","z")]))
                                          for f in forces), default=None)))
    events = [json.loads(line) for line in (logger/"contact_events.jsonl").open()]
    nearby = [r for r in events if tp-.2 <= r["time_s"] <= tp+.2]
    ranked = sorted(contact_samples, key=lambda r: r["maximum_force_norm_N"] or 0., reverse=True)
    imu.sort(key=lambda r:r["time_s"])
    t = np.array([r["time_s"] for r in imu])
    a = np.array([r["vertical_m_s2"] for r in imu])
    dt = np.diff(t)
    dt = np.where((dt > 0) & (dt <= .05), dt, 0.)
    weights = np.zeros(len(t))
    weights[:-1] += .5*dt
    weights[1:] += .5*dt
    contributions = weights*a*a
    total = float(contributions.sum())
    result = dict(profile=outcome["profile"], case=str(case), peak=peak,
        peak_after_first_contact_s=tp-outcome["first_contact_s"],
        peak_after_clearance_s=tp-outcome["clearance_s"],
        command_at_peak={k:command[k] for k in ("governor_input_time_s","governor_phase","governor_scale",
                            "governor_requested_linear_m_s","governor_feedback_age_s")},
        nearest_ground_truth=min(ground,key=lambda r: abs(r["time_s"]-tp)),
        nearest_joint_state=min(joints,key=lambda r: abs(r["time_s"]-tp)),
        nearest_drive=min(drives,key=lambda r: abs(float(r["sim_time_s"])-tp)),
        top_contact_force_samples=ranked[:8], contact_events_near_peak=nearby,
        contact_components_with_samples_near_peak=sorted({r["component"] for r in contact_samples}),
        raw_sampled_vertical_square_integral=total,
        largest_two_samples_integral_fraction=float(np.sort(contributions)[-2:].sum()/total) if total else None,
        top_imu_samples=sorted(imu,key=lambda r: abs(r["vertical_m_s2"]),reverse=True)[:8],
        qualification="Temporal co-occurrence, not proven cause; contact force samples are not integrated impulses")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    args = p.parse_args()
    rows = json.loads((args.root/"episodes.json").read_text())
    result = [audit(Path(r["case"]),r) for r in rows if r.get("complete")]
    (args.root/"peak_context.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    for r in result:
        print(r["profile"],r["peak"],r["command_at_peak"],r["top_contact_force_samples"][:1])


if __name__ == "__main__":
    main()
