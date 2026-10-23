#!/usr/bin/env python3
"""Saved-data detector separation audit; never executes candidate motor commands."""
import argparse
import csv
import json
from math import hypot
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/"src/nino_control"), str(ROOT/"src/nino_rl"), str(Path(__file__).parent)]
from nino_control.governor_core import quaternion_rpy, vertical_acceleration
from nino_rl.control_v2 import ImuWindow
from nino_rl.core import load_config
from analyze_governor_experiment import stamp


def describe(values):
    return dict(n=len(values), median=float(np.median(values)), p95=float(np.percentile(values, 95)),
                maximum=float(max(values))) if values else dict(n=0, median=None, p95=None, maximum=None)


def analyze(case):
    case = Path(case)
    evaluation = next((case/"evaluation").glob("*/summary.json")).parent
    logger = next((case/"contact").glob("*/metadata.json")).parent
    summary = json.loads((evaluation/"summary.json").read_text())
    if not summary["complete"]:
        return dict(case=str(case), available=False, reason="incomplete_evaluation")
    config = load_config(evaluation/"config.yaml")
    rows = list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))
    origin = float(rows[0]["governor_input_time_s"])
    end = float(rows[-1]["sim_time_s"])
    contacts = [json.loads(line) for line in (logger/"contact_events.jsonl").open()]
    first = min((r["time_s"] for r in contacts if r["event"] == "begin" and
                 r.get("named_positive_obstacle") and origin <= r["time_s"] <= end), default=None)
    imu = []
    for line in (logger/"samples.jsonl").open():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row["topic"] != "/imu/data":
            continue
        data = row["data"]
        t = stamp(data)
        if not origin-.15 <= t <= end:
            continue
        r, p, _ = quaternion_rpy(tuple(data["orientation"][k] for k in ("x", "y", "z", "w")))
        vertical = vertical_acceleration(tuple(data["linear_acceleration"][k] for k in ("x", "y", "z")),
                                         r, p, config["policy_v2"]["imu_includes_gravity"])
        imu.append((t, vertical, hypot(data["angular_velocity"]["x"], data["angular_velocity"]["y"])))
    imu.sort()
    window = ImuWindow()
    for t, value, _ in imu:
        window.add(t, value)
    imu_times = np.asarray([r[0] for r in imu])
    settings = config["governor"]["parameters"]
    threshold = settings["vertical_trigger_m_s2"]
    rms_filtered = 0.
    previous = None
    records = []
    for row in rows:
        t = float(row["governor_input_time_s"])
        dt = .1 if previous is None else t-previous[0]
        measured = window.measure(t-.1, t)
        coverage = measured["duration"]/.1
        rms = np.sqrt(measured["square_integral"]/measured["duration"]) if coverage >= .8 else None
        if rms is not None:
            rms_filtered += dt/(settings.get("filter_seconds", .05)+dt)*(rms-rms_filtered)
        cmd = float(row["governor_requested_linear_m_s"])*float(row["governor_scale"])
        acceleration = (cmd-previous[1])/dt if previous is not None else None
        eligible = (t-origin >= settings.get("startup_seconds", .8) and
                    cmd >= settings.get("minimum_trigger_speed_m_s", .1))
        pre = first is None or t < first
        native = float(row["governor_filtered_vertical_m_s2"] or 0.)
        at = int(np.searchsorted(imu_times, t+1.e-8, side="right"))-1
        body_rate = imu[at][2] if at>=0 and t-imu[at][0]<=.1 else None
        wheel_ratio = float(row["governor_wheel_error_m_s"] or 0.)/float(row["governor_wheel_error_threshold_m_s"] or 1.)
        nonvertical = (body_rate is not None and body_rate>=settings["body_rate_trigger_rad_s"]) or wheel_ratio>=1.
        records.append(dict(time_s=t, elapsed_s=t-origin, precontact=pre, eligible=eligible,
            command_m_s=cmd, command_acceleration_m_s2=acceleration,
            approximately_steady_command=(acceleration is not None and abs(acceleration)<.05 and
                abs(float(row["governor_requested_yaw_rad_s"]))<.05),
            native_filtered_peak_feature_m_s2=native,
            native_vertical_condition=native>=threshold,
            reconstructed_body_rate_rad_s=body_rate, native_wheel_error_ratio=wheel_ratio,
            nonvertical_condition=nonvertical,
            reconstructed_interval_rms_m_s2=float(rms) if rms is not None else None,
            reconstructed_interval_peak_m_s2=measured["peak"] if coverage>=.8 else None,
            reconstructed_rms_only_filtered_m_s2=float(rms_filtered) if rms is not None else None,
            interval_coverage=coverage))
        previous = t, cmd
    negative = [r for r in records if r["precontact"] and r["eligible"]]
    positive = [r for r in records if first is not None and first<=r["time_s"]<=first+.5]
    return dict(case=str(case), available=True, first_positive_contact_s=first,
        negative_frames=len(negative), native_vertical_negative_frames=sum(r["native_vertical_condition"] for r in negative),
        native_vertical_negative_steady_frames=sum(r["native_vertical_condition"] and r["approximately_steady_command"] for r in negative),
        nonvertical_negative_frames=sum(r["nonvertical_condition"] for r in negative),
        negative_body_rate=describe([r["reconstructed_body_rate_rad_s"] for r in negative if r["reconstructed_body_rate_rad_s"] is not None]),
        first_half_second_body_rate=describe([r["reconstructed_body_rate_rad_s"] for r in positive if r["reconstructed_body_rate_rad_s"] is not None]),
        first_nonvertical_condition_delay_s=next((r["time_s"]-first for r in records
            if first is not None and r["time_s"]>=first and r["time_s"]<=first+.5 and r["nonvertical_condition"]), None),
        negative_native_feature=describe([r["native_filtered_peak_feature_m_s2"] for r in negative]),
        negative_reconstructed_rms=describe([r["reconstructed_interval_rms_m_s2"] for r in negative if r["reconstructed_interval_rms_m_s2"] is not None]),
        first_half_second_native_feature=describe([r["native_filtered_peak_feature_m_s2"] for r in positive]),
        first_half_second_reconstructed_rms=describe([r["reconstructed_interval_rms_m_s2"] for r in positive if r["reconstructed_interval_rms_m_s2"] is not None]),
        records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for case in args.cases:
        try:
            results.append(analyze(case))
        except Exception as error:
            results.append(dict(case=str(case), available=False, reason=f"{type(error).__name__}: {error}"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(results=results,
        qualification="Native feature exceedances, not closed-loop false-event counts. RMS reconstruction uses saved samples, not identical DDS callback order. RMS-only is diagnostic, not a validated correction.",
        controller_changed=False, tuning_started=False), indent=2, allow_nan=False)+"\n")
    print("Saved", args.output)


if __name__ == "__main__":
    main()
