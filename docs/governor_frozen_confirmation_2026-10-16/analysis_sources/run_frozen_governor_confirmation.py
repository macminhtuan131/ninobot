#!/usr/bin/env python3
"""Preregistered instrumentation gate and bounded frozen-governor confirmation."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/"src/nino_rl"))
from nino_rl.core import load_config
from nino_rl.slip_reporting import replay_native_trace


def make_world(destination, scenario):
    """Only two pose elements change; floor, collision and friction stay identical."""
    source = ROOT/"src/nino_description/worlds/factory_floor_cable_box_capsule_contact_lab.sdf"
    tree = ET.parse(source)
    cable = tree.getroot().find("world/model[@name='cable_bumps']/link")
    for kind in ("collision", "visual"):
        pose = cable.find(f"{kind}/pose")
        values = pose.text.split()
        values[0], values[5] = str(scenario["x_m"]), str(math.radians(scenario["angle_deg"]))
        pose.text = " ".join(values)
    tree.write(destination, encoding="utf-8", xml_declaration=True)
    metadata = json.loads(source.with_suffix(".json").read_text())
    metadata["cables"][0].update(x_m=scenario["x_m"], angle_deg=scenario["angle_deg"])
    metadata.update(world_file=destination.name, revision="frozen_confirmation_position_yaw_only_v1",
                    parent_world_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    scenario=scenario, per_episode_randomization=False,
                    notes=["Solid box contact floor and capsule collision retained from parent.",
                           "Only cable collision/visual x and yaw changed. Geometry is evaluation-only."])
    destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2)+"\n")


def clearance_time(ground, first, scenario):
    theta = math.radians(scenario["angle_deg"])
    plane = (ground[:,3]-scenario["x_m"])*math.cos(theta)+ground[:,4]*math.sin(theta)
    after = (ground[:,0] >= first) & (plane >= .5)
    return float(ground[np.flatnonzero(after)[0],0]) if after.any() else None


def batch(root):
    gate = json.loads((root/"instrumentation_gate.json").read_text())
    if not gate["batch_permitted"]:
        raise ValueError("Instrumentation did not pass; no confirmation runs permitted")
    protocol = json.loads((root/"protocol_before_results.json").read_text())
    folder = root/"confirmation"
    folder.mkdir(exist_ok=False)
    for scenario in protocol["scenarios"]:
        stage = folder/scenario["id"]
        stage.mkdir()
        make_world(stage/"scenario.sdf", scenario)
    execution = dict(parallel_scenarios=4, ros_domains=[90,91,92,93],
        reason="Independent cold-start blocks;80 logical CPUs/approximately50GB available at preregistration",
        repeated_grid_reversal="At least2 of8 paired blocks reverse whole RMS or crossing slip2/m comparison between primary and10ms-shift grids",
        frozen_config_sha256=hashlib.sha256((root/"frozen_config.yaml").read_bytes()).hexdigest(),
        no_extra_episodes_or_retries=True)
    (folder/"execution_before_results.json").write_text(json.dumps(execution, indent=2)+"\n")
    def run_one(item):
        i, scenario = item
        stage = folder/scenario["id"]
        environment = os.environ.copy()
        environment.update(ROS_DOMAIN_ID=str(90+i), NINO_ROS_DOMAIN_ID=str(90+i),
                           ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST", GZ_PARTITION=f"nino_frozen_confirmation_{90+i}")
        command = [sys.executable, str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
                   "--variant", "cable_box_capsule", "--config", str(root/"frozen_config.yaml"),
                   "--profiles", "full", "reactive", "--full-reference-speed", ".388",
                   "--seeds", *map(str, scenario["seeds"]), "--shuffle-order", "--order-seed", str(76950+i),
                   "--world", str(stage/"scenario.sdf"), "--output", str(stage/"screen")]
        with (stage/"run.log").open("w") as stream:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        print("SCENARIO END", scenario["id"], result.returncode, flush=True)
        return dict(scenario=scenario["id"], returncode=result.returncode)
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(run_one, enumerate(protocol["scenarios"])))
    (folder/"execution_result.json").write_text(json.dumps(result, indent=2)+"\n")


def analyze_batch(root):
    from audit_single_cable_screen import analyze
    from audit_governor_phase_slip import load
    from analyze_governor_experiment import stamp, energy
    from nino_control.governor_core import quaternion_rpy, vertical_acceleration
    from nino_rl.slip_reporting import synchronized_windows
    from summarize_contact_oracle_h2 import native_status
    protocol = json.loads((root/"protocol_before_results.json").read_text())
    results = []
    for scenario in protocol["scenarios"]:
        stage = root/"confirmation"/scenario["id"]
        try:
            screen = json.loads((stage/"screen/summary.json").read_text())
        except (OSError, ValueError) as error:
            screen = dict(results=[dict(seed=seed, profile=profile, passed=False,
                                        error=f"screen unavailable: {error}")
                                   for seed in scenario["seeds"] for profile in ("full", "reactive")])
        for status in screen["results"]:
            case = stage/"screen"/f"seed_{status['seed']}_{status['profile']}"
            row = dict(scenario=scenario["id"], seed=status["seed"], profile=status["profile"],
                       physical_pass=status["passed"], **native_status(case), case=str(case),
                       available=False, error=status.get("error"))
            try:
                raw = analyze(case)
                data = load(case, {**raw, **row})
                # The plane normal is perpendicular to the tilted cable axis.
                clear = clearance_time(data["ground"], data["first"], scenario)
                windows = {"whole_route": (data["start"], data["end"]),
                           "crossing": (data["first"]+.05, clear) if clear is not None else None}
                _, primary = synchronized_windows(data, windows)
                _, shifted = synchronized_windows(data, windows, offset=.01)
                native = data["native"]
                replay = replay_native_trace(data["controls"])
                replay["matches_native"] = replay["available"] and np.isclose(replay["rms"], float(native["rms_wheel_slip"]), rtol=1e-10, atol=1e-10)
                timing = timestamps(data["controls"])
                imu = []
                includes_gravity = load_config(data["evaluation"]/"config.yaml")["policy_v2"]["imu_includes_gravity"]
                for line in (data["logger"]/"samples.jsonl").open():
                    packet = json.loads(line)
                    if packet["topic"] != "/imu/data": continue
                    d = packet["data"]; t = stamp(d)
                    if data["first"] <= t <= (clear or data["end"]):
                        roll,pitch,_ = quaternion_rpy(tuple(d["orientation"][k] for k in ("x","y","z","w")))
                        imu.append((t, vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x","y","z")), roll, pitch,
                                                           includes_gravity)))
                meta = json.loads((data["logger"]/"metadata.json").read_text())
                row.update(available=True, native_outcome=native, time_s=float(native["time_seconds"]),
                    physical_rmse_m=float(native["truth_path_rmse_m"]),
                    native_slip_rms=float(native["rms_wheel_slip"]),
                    whole_vertical_rms=float(native["rms_vertical_acceleration_m_s2"]),
                    whole_vertical_peak=float(native["peak_vertical_acceleration_m_s2"]),
                    crossing_vertical=energy(imu, data["first"]+.05, clear, .05) if clear else None,
                    first_50ms=raw["first_50ms_acceleration"],
                    primary=primary, shifted=shifted, native_replay=replay, timestamps=timing,
                    first_contact_s=data["first"], clearance_s=clear,
                    precontact_events=raw.get("precontact_governor_event_times_s"),
                    contact_to_decision_s=(raw["postcontact_first_reduced_command_s"]-data["first"]
                        if raw.get("postcontact_first_reduced_command_s") else None),
                    recovery_after_contact_s=(raw["first_recovered_scale_time_s"]-data["first"]
                        if raw.get("first_recovered_scale_time_s") else None),
                    world_sha256=meta.get("world_sha256"), provenance={k:meta.get(k) for k in
                        ("robot_description_sha256", "governor_core_sha256", "effort_drive_sha256", "control_timing_sha256")})
            except Exception as error:
                row["analysis_error"] = f"{type(error).__name__}: {error}"
            results.append(row)
    def clean(value):
        if isinstance(value, dict): return {k:clean(v) for k,v in value.items()}
        if isinstance(value, list): return [clean(v) for v in value]
        if isinstance(value, np.generic): return value.item()
        return value
    (root/"confirmation_episodes.json").write_text(json.dumps(clean(results), indent=2, allow_nan=False)+"\n")
    print("ANALYZED", len(results), "episodes", flush=True)


def evaluate_results(rows):
    """Apply the frozen criteria; no successful-only subset or score substitution."""
    pairs = []
    for seed in sorted({r["seed"] for r in rows}):
        arms = {r["profile"]:r for r in rows if r["seed"]==seed}
        pair = dict(seed=seed, scenario=next(iter(arms.values()))["scenario"], available=False)
        if set(arms)=={"full","reactive"} and all(r.get("available") for r in arms.values()):
            pair["ratios"] = {}
            for origin in ("primary", "shifted"):
                ratios = {}
                for key, window, field in (("whole_rms", "whole_route", "rms"), ("crossing_per_m", "crossing", "slip_square_per_m")):
                    a, b = (arms[p][origin][window].get(field) for p in ("full","reactive"))
                    ratios[key] = b/a if a is not None and b is not None and a>0 else None
                pair["ratios"][origin] = ratios
            pair["available"] = all(v is not None for origin in pair["ratios"].values() for v in origin.values())
            pair["grid_reversal"] = pair["available"] and any(
                (pair["ratios"]["primary"][key]-1)*(pair["ratios"]["shifted"][key]-1)<0
                for key in ("whole_rms","crossing_per_m"))
        pairs.append(pair)
    def means(selected):
        result = {}
        for profile in ("full","reactive"):
            arm = [r for r in selected if r["profile"]==profile]
            if not arm or not all(r.get("available") for r in arm): return None
            result[profile] = dict(n=len(arm), time_s=float(np.mean([r["time_s"] for r in arm])),
                physical_rmse_m=float(np.mean([r["physical_rmse_m"] for r in arm])),
                native_slip_rms=float(np.mean([r["native_slip_rms"] for r in arm])),
                whole_vertical_rms=float(np.mean([r["whole_vertical_rms"] for r in arm])),
                whole_vertical_peak=float(np.mean([r["whole_vertical_peak"] for r in arm])))
            for origin in ("primary","shifted"):
                result[profile][origin] = {}
                for key,window,field in (("whole_rms","whole_route","rms"), ("crossing_per_m","crossing","slip_square_per_m"),
                                         ("whole_integral_s","whole_route","slip_square_integral_s")):
                    values = [r[origin][window].get(field) for r in arm]
                    result[profile][origin][key] = float(np.mean(values)) if all(v is not None for v in values) else None
        return result
    def slip_pass(group):
        return group is not None and all(group[p][origin][key] is not None
            for p in ("full","reactive") for origin in ("primary","shifted") for key in ("whole_rms","crossing_per_m")) and all(
            group["reactive"][origin][key]<group["full"][origin][key]
            for origin in ("primary","shifted") for key in ("whole_rms","crossing_per_m"))
    aggregate = means(rows)
    scenarios = {s:means([r for r in rows if r["scenario"]==s]) for s in sorted({r["scenario"] for r in rows})}
    reporting = len(rows)==16 and all(r.get("available") and r.get("native_replay",{}).get("matches_native")
        and r.get("timestamps",{}).get("passed") and all(r[o][w]["available"]
        for o in ("primary","shifted") for w in ("whole_route","crossing")) for r in rows)
    provenance = len(rows)==16 and all(all(r.get("provenance",{}).get(k) for k in
        ("robot_description_sha256","governor_core_sha256","effort_drive_sha256","control_timing_sha256")) for r in rows)
    if provenance:
        provenance = all(len({r["provenance"][k] for r in rows})==1 for k in rows[0]["provenance"])
        provenance = provenance and all(r.get("world_sha256") for r in rows) and all(
            len({r.get("world_sha256") for r in rows if r["scenario"]==s})==1 for s in scenarios)
    gates = dict(reporting=bool(reporting), physical_arrival_stop=len(rows)==16 and all(r["physical_pass"] for r in rows),
                 fixed_robot_pi_core_provenance=bool(provenance),
                 time=aggregate is not None and aggregate["reactive"]["time_s"]<=1.05*aggregate["full"]["time_s"],
                 tracking=aggregate is not None and aggregate["reactive"]["physical_rmse_m"]<=1.05*aggregate["full"]["physical_rmse_m"],
                 slip_both_origins=slip_pass(aggregate), scenarios_improved=sum(slip_pass(s) for s in scenarios.values())>=3)
    reversal_count = sum(p.get("grid_reversal",False) for p in pairs)
    overall_reversal = aggregate is not None and any(
        all(aggregate[p][o][k] is not None for p in ("full","reactive") for o in ("primary","shifted"))
        and (aggregate["reactive"]["primary"][k]-aggregate["full"]["primary"][k])*
            (aggregate["reactive"]["shifted"][k]-aggregate["full"]["shifted"][k])<0
        for k in ("whole_rms","crossing_per_m"))
    if not reporting or overall_reversal or reversal_count>=2:
        decision = "measurement_first_no_tuning"
    elif all(gates.values()):
        decision = "eligible_for_future_bounded_classical_tuning_not_started"
    else:
        decision = "one_saved_trace_audit_before_continue_or_stop"
    return dict(decision=decision, gates=gates, aggregate=aggregate, scenario_means=scenarios,
                paired= pairs, grid_reversal_pairs=reversal_count, overall_grid_reversal=bool(overall_reversal),
                physical_failures=sum(r.get("physical_success") is False for r in rows),
                unavailable_native_outcomes=sum(r.get("physical_success") is None for r in rows),
                no_extra_simulations=True, tuning_started=False, training_started=False)


def decide(root):
    rows = json.loads((root/"confirmation_episodes.json").read_text())
    result = evaluate_results(rows)
    (root/"decision.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(result["decision"], result["gates"], flush=True)


def timestamps(rows):
    fields = ["slip_joint_stamp_s", "slip_ground_truth_stamp_s", "slip_joint_age_s",
              "slip_ground_truth_age_s", "slip_joint_minus_ground_stamp_s"]
    try:
        values = np.array([[float(r[k]) for k in fields] for r in rows])
        if not len(values) or not np.isfinite(values).all():
            raise ValueError("missing/nonfinite timestamps")
    except (ValueError, KeyError, TypeError) as error:
        return dict(passed=False, reason=str(error))
    joints, gt, skew = values[:, 2], values[:, 3], values[:, 4]
    checks = dict(no_future=bool(min(joints.min(), gt.min()) >= -.001-1e-9),
                  joint_age=bool(joints.max() <= .010+1e-9),
                  ground_age=bool(gt.max() <= .040+1e-9),
                  skew=bool(abs(skew).max() <= .040+1e-9))
    return dict(passed=all(checks.values()), checks=checks, samples=len(rows),
                joint_age_range_s=[float(joints.min()), float(joints.max())],
                ground_age_range_s=[float(gt.min()), float(gt.max())],
                skew_range_s=[float(skew.min()), float(skew.max())])


def instrumentation_gate(root):
    from summarize_contact_oracle_h2 import summarize
    from report_synchronized_slip import run
    stage = root/"instrumentation"
    summarize(stage/"screen", stage/"analysis")
    artifacts = ROOT/"docs/governor_frozen_confirmation_2026-10-16"
    bundle = run(stage, artifacts/"instrumentation_report")
    screen = json.loads((stage/"screen/summary.json").read_text())
    result = []
    for row in bundle["episodes"]:
        case = Path(row["case"])
        rows = list(csv.DictReader(next(case.glob("evaluation/*/episode-*/control_trace.csv")).open()))
        replay = replay_native_trace(rows)
        replay["matches_native"] = bool(replay["available"] and np.isclose(
            replay["rms"], row["native_rms_wheel_slip"], rtol=1e-10, atol=1e-10))
        timing = timestamps(rows)
        coverage = all(row["synchronized"][key]["available"]
                       for key in ("whole_route", "post_contact_to_clearance"))
        result.append(dict(seed=row["seed"], profile=row["profile"], replay=replay,
                           timestamps=timing, coverage_pass=coverage,
                           passed=replay["matches_native"] and timing["passed"] and coverage))
    provenance = json.loads((stage/"analysis/result.json").read_text())
    same = {key: provenance[key] for key in ("same_world", "same_robot", "same_core", "same_effort_drive", "same_config_except_planned_treatment")}
    gate = dict(passed=len(result)==2 and screen["all_passed"] and all(r["passed"] for r in result) and all(same.values()),
                physical_arrival_stop_pass=screen["all_passed"], provenance=same, episodes=result,
                batch_permitted=False, no_retry=True, training=False, tuning=False)
    gate["batch_permitted"] = gate["passed"]
    (root/"instrumentation_gate.json").write_text(json.dumps(gate, indent=2, allow_nan=False)+"\n")
    (artifacts/"instrumentation_gate.json").write_text(json.dumps(gate, indent=2, allow_nan=False)+"\n")
    print(json.dumps(gate, indent=2), flush=True)
    return gate


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    selected = ROOT/"docs/classical_governor_crossing_tune_2026-10-16/selected_candidate.yaml"
    config = load_config(selected)
    (root/"frozen_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    protocol = dict(contract="frozen_governor_reporting_confirmation_v1", maximum_episodes=18,
        instrumentation=dict(seed=76800, profiles=["full", "reactive"], episodes=2,
            gate="Native replay tolerance1e-10; finite sensor stamps, no future beyond1ms; joint age<=10ms, GT age<=40ms, abs skew<=40ms; common-grid whole/crossing coverage>=98%; both physical arrival/2s-stop pass. Fail means STOP without retry or parameter change."),
        scenarios=[dict(id=f"s{i}", x_m=x, angle_deg=a, seeds=[76900+2*i, 76901+2*i])
                   for i, (x, a) in enumerate([(2.5, -10), (2.5, 10), (3.3, -10), (3.3, 10)])],
        controllers=dict(reference="constant PI cruise0.388", candidate="reactive cruise0.400 target0.90 maxhold1.0; frozen config"),
        order="shuffle within paired cold-start blocks; order RNG76850 for instrumentation,76950+i for scenarios; not identical snapshots",
        measurement="Same 50Hz grid and offset+10ms for whole/crossing. Crossing first+50ms to GT body normal-plane distance0.50m beyond cable. Native vertical and fixed2s event vibration retained; no true impulse claim.",
        gates=dict(arrival_stop="All reference/candidate arrivals and2s-stops; failed outcomes retained",
            tracking="mean candidate physical RMSE<=1.05*PI", time="mean candidate time<=1.05*PI; not a time-matched claim",
            slip="mean whole RMS and postcontact slip2/m ratios<1 on both grid origins; >=3/4 scenario means improve both metrics at both origins",
            decision="All gates pass: eligible for future bounded classical tuning, never automatic. Grid reversal: measurement-first. Otherwise one saved-trace audit; no extra simulations."),
        reporting_thresholds_qualification="Design limits for this simulation screen based on existing2ms wheel/20ms GT cadence, not hardware or industry standards",
        parameters_frozen_before_results=True, training=False, optuna=False, automatic_retry=False,
        selected_config_sha256=hashlib.sha256(selected.read_bytes()).hexdigest(),
        constraints="Physics, PI, robot, detector, ramp and scoring fixed. Only cable position/yaw differ across four novel scenarios; traversal not presumed. No test-based selection.")
    (root/"protocol_before_results.json").write_text(json.dumps(protocol, indent=2)+"\n")
    (root/"runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    print(root, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "instrumentation-gate", "batch", "analyze", "decide"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.output.resolve())
    elif args.phase == "instrumentation-gate":
        instrumentation_gate(args.output.resolve())
    elif args.phase == "batch":
        batch(args.output.resolve())
    elif args.phase == "analyze":
        analyze_batch(args.output.resolve())
    else:
        decide(args.output.resolve())


if __name__ == "__main__":
    main()
