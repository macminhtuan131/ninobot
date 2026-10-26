#!/usr/bin/env python3
"""Audit saved contact/command/speed timing; no simulation or rescoring.

Observed speed drops include obstacle forces. They do not identify actuator
latency or a causal governor effect. All contact/GT data stay diagnostic-only.
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def stamp(data):
    value = data["header"]["stamp"]
    return value["sec"] + value["nanosec"] * 1e-9


def first_sustained(samples, threshold, start, end, duration=.06, max_gap=.025):
    """Return observed begin/confirmation stamps, never bridge missing data."""
    begin = previous = None
    for time, value in samples:
        if not start <= time <= end:
            continue
        if not math.isfinite(value) or value > threshold:
            begin = previous = None
            continue
        if previous is None or time - previous > max_gap or time <= previous:
            begin = time
        previous = time
        if time - begin >= duration - 1e-9:
            return dict(begin_s=begin, confirmed_s=time)
    return None


def sample_before(samples, time, max_age=.025):
    index = bisect.bisect_right([r[0] for r in samples], time) - 1
    if index < 0 or time - samples[index][0] > max_age:
        return None
    return dict(stamp_s=samples[index][0], age_s=time-samples[index][0], value=samples[index][1])


def analyze(episode, protocol):
    case, tc = Path(episode["case"]), episode["first_contact_s"]
    logger = next(case.glob("contact/*/metadata.json")).parent
    evaluation = next(case.glob("evaluation/*/summary.json")).parent
    control_path = next(evaluation.glob("episode-*/control_trace.csv"))
    drive_path = next(evaluation.glob("episode-*/drive_trace.csv"))
    controls = list(csv.DictReader(control_path.open()))
    drive = list(csv.DictReader(drive_path.open()))
    start, end = tc + protocol["window_relative_s"][0], tc + protocol["window_relative_s"][1]
    body, wheels = [], {side: [] for side in ("left", "right")}
    contact_refs = {}
    with (logger / "samples.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            topic, data = row["topic"], row["data"]
            if topic not in ("/ground_truth/odom", "/joint_states") and not topic.startswith("/nino/contact_lab/"):
                continue
            time = stamp(data)
            if not start <= time <= end:
                continue
            if topic == "/ground_truth/odom":
                body.append((time, float(data["twist"]["twist"]["linear"]["x"])))
            elif topic == "/joint_states":
                velocity = dict(zip(data["name"], data["velocity"]))
                for side in wheels:
                    wheels[side].append((time, protocol["wheel_radius_m"] * velocity[f"{side}_wheel_joint"]))
            else:
                for contact in data["contacts"]:
                    if "cable_bumps" not in contact["collision1"]["name"] + contact["collision2"]["name"]:
                        continue
                    component = topic.rsplit("/", 1)[-1]
                    refs = contact_refs.setdefault(component, {})
                    refs["first_manifold_s"] = min(time, refs.get("first_manifold_s", time))
                    loaded = any(depth > 0 and math.sqrt(sum(force["body_1_wrench"]["force"][k]**2
                                  for k in ("x", "y", "z"))) > protocol["nonzero_force_epsilon_N"]
                                 for depth, force in zip(contact["depths"], contact["wrenches"]))
                    if loaded:
                        refs["first_positive_depth_nonzero_force_s"] = min(time, refs.get(
                            "first_positive_depth_nonzero_force_s", time))
    body.sort()
    for series in wheels.values():
        series.sort()
    baseline_start, baseline_end = [tc+x for x in protocol["baseline_relative_s"]]
    def baseline(series):
        values = [v for t, v in series if baseline_start <= t <= baseline_end]
        if len(values) < 5:
            raise ValueError("Insufficient precontact baseline")
        return statistics.median(values)
    baselines = dict(body_m_s=baseline(body), **{f"{s}_wheel_m_s": baseline(v) for s, v in wheels.items()})
    slow = [r for r in controls if tc <= float(r["governor_input_time_s"]) <= end
            and float(r["governor_scale"]) < .999999]
    decision = float(slow[0]["governor_input_time_s"]) if slow else None
    target_rows = [r for r in slow if float(r["governor_scale"]) <= .900001]
    target = float(target_rows[0]["governor_input_time_s"]) if target_rows else None
    executed = [(float(r["sim_time_s"]), float(r["executed_linear_m_s"])) for r in drive]
    executed.sort()
    first_execution = next(((t,v) for t,v in executed if decision is not None and t >= decision
                           and v <= .97*protocol["cruise_m_s"]), None)
    reductions = {}
    for label, series, base in [("body", body, baselines["body_m_s"]), *[
        (s+"_wheel", v, baselines[s+"_wheel_m_s"]) for s,v in wheels.items()]]:
        reductions[label] = {}
        for fraction in protocol["relative_speed_thresholds"]:
            result = first_sustained(series, base*fraction, tc, end,
                                     protocol["sustained_s"], protocol["maximum_sample_gap_s"])
            if result:
                result.update(begin_after_first_manifold_s=result["begin_s"]-tc,
                              begins_before_reduced_command=(result["begin_s"] < decision) if decision is not None else None)
            reductions[label][str(fraction)] = result
    milestones = []
    for component, refs in sorted(contact_refs.items(), key=lambda pair: pair[1]["first_manifold_s"]):
        time = refs["first_manifold_s"]
        milestones.append(dict(component=component, **refs, after_first_manifold_s=time-tc,
            command_scale=next((float(r["governor_scale"]) for r in reversed(controls)
                                if float(r["governor_input_time_s"]) <= time), None),
            executed_command=sample_before(executed, time),
            body=sample_before(body, time), wheels={s:sample_before(v,time) for s,v in wheels.items()},
            target_command_precedes_manifold=(target <= time) if target is not None else None))
    return dict(attempt=episode["attempt"], repeat=episode["repeat"], profile=episode["profile"],
                first_manifold_s=tc, baselines=baselines,
                reduced_command_time_s=decision, target_090_command_time_s=target,
                first_reduced_execution_sample=first_execution,
                observed_speed_drops=reductions, milestones=milestones,
                series=dict(body=body, wheels=wheels, executed_command=executed,
                            scale=[(float(r["governor_input_time_s"]),float(r["governor_scale"]))
                                   for r in controls if start <= float(r["governor_input_time_s"]) <= end]),
                source_files=[str(logger/"samples.jsonl"), str(control_path), str(drive_path)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False, parents=True)
    protocol = dict(window_relative_s=[-.5, 2.], baseline_relative_s=[-.3,-.05],
                    relative_speed_thresholds=[.95,.90], sustained_s=.06,
                    maximum_sample_gap_s=.025, wheel_radius_m=.0625, cruise_m_s=.4,
                    nonzero_force_epsilon_N=1e-6, new_simulation_episodes=0,
                    qualification="Descriptive offline timing, not isolated actuator latency or causal treatment effect. "
                    "Force epsilon distinguishes numerical zero, not a safety threshold. Native metrics/windows unchanged.")
    (args.output/"protocol_before_analysis.json").write_text(json.dumps(protocol,indent=2)+"\n")
    episodes = json.loads((args.run/"episodes.json").read_text())
    if len(episodes) != 4 or not all(e.get("complete") for e in episodes):
        raise ValueError("Expected all four complete frozen repetitions; do not silently omit failures")
    result = [analyze(episode, protocol) for episode in episodes]
    manifest = {str((args.run/"episodes.json").resolve()): hashlib.sha256((args.run/"episodes.json").read_bytes()).hexdigest()}
    for episode in result:
        for name in episode["source_files"]:
            with Path(name).open("rb") as stream:
                manifest[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.output/"timing.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    (args.output/"input_sha256.json").write_text(json.dumps(manifest,indent=2)+"\n")
    for episode in result:
        print(json.dumps({k:episode[k] for k in ("attempt","profile","reduced_command_time_s",
                         "target_090_command_time_s","observed_speed_drops")}))


if __name__ == "__main__":
    main()
