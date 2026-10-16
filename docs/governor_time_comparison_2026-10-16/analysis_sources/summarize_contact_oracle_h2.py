#!/usr/bin/env python3
"""Event-aligned H2 results with failed/missing outcomes retained."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from audit_single_cable_screen import analyze, plot_timing


def stats(values):
    values = [v for v in values if v is not None]
    return (dict(n=len(values), mean=float(np.mean(values)), minimum=float(min(values)),
                 maximum=float(max(values)), std=float(np.std(values, ddof=1)) if len(values)>1 else None)
            if values else dict(n=0, mean=None, minimum=None, maximum=None, std=None))


def native_status(case):
    """Contact-analysis failure must not erase an already scored arrival failure."""
    paths = list((Path(case)/"evaluation").glob("*/summary.json"))
    if len(paths) != 1:
        return dict(complete=False, physical_success=None, termination=None)
    summary = json.loads(paths[0].read_text())
    csv_path = paths[0].with_name("episodes.csv")
    rows = list(csv.DictReader(csv_path.open())) if csv_path.exists() else []
    outcome = rows[0] if len(rows)==1 else {}
    return dict(complete=summary.get("complete", False),
                physical_success=(outcome["success"]=="True") if "success" in outcome else None,
                termination=outcome.get("termination"))


def summarize(screen, output, reference_screen=None):
    screen, output = Path(screen), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = json.loads((screen/"summary.json").read_text())
    plan_path=screen/"plan.json"
    plan=json.loads(plan_path.read_text()) if plan_path.exists() else {}
    constant_reference_speed=plan.get("full_reference_speed_m_s")
    cases=list(screen.glob("seed_*"))
    reference_metadata=None
    if reference_screen is not None:
        reference_screen=Path(reference_screen)
        reference=json.loads((reference_screen/"summary.json").read_text())
        if reference["seeds"]!=source["seeds"] or "full" in source["profiles"] or reference["profiles"]!=["full"]:
            raise ValueError("Reference must be the matching-seed Full-only batch")
        reference_metadata=dict(source=str(reference_screen),
            source_summary_sha256=hashlib.sha256((reference_screen/"summary.json").read_bytes()).hexdigest())
        cases+=list(reference_screen.glob("seed_*_full"))
        source["profiles"]=["full", *source["profiles"]]
    results, compact = [], []
    provenance = []
    for case in sorted(cases):
        seed, profile = case.name.split("_")[1:]
        common = dict(seed=int(seed), profile=profile, case=str(case))
        native_fallback = native_status(case)
        try:
            data = analyze(case)
            audit = json.loads((case/"audit.json").read_text())
            native = data.get("outcome") or {}
            control_path = next(Path(data["evaluation"]).glob("episode-*/control_trace.csv"))
            controls = list(csv.DictReader(control_path.open()))
            contact = data.get("first_contact", {}).get("time_s")
            accepted = next((r for r in controls if r.get("oracle_command_time_s")), None)
            command = float(accepted["oracle_command_time_s"]) if accepted else None
            oracle_stamp = float(accepted["oracle_contact_time_s"]) if accepted else None
            event_times=data.get("governor_event_times_s",[])
            decision_time=command if command is not None else (event_times[0] if event_times else None)
            meta = json.loads((Path(data["logger"])/"metadata.json").read_text())
            resolved_path=Path(data["logger"])/"resolved_config.json"
            normalized=json.loads(resolved_path.read_text())
            configured_cruise=normalized.get("navigation",{}).get("straight_speed_m_s")
            normalized.get("governor",{}).get("parameters",{}).pop("profile",None)
            profile_normalized_hash=hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()
            if constant_reference_speed is not None:
                normalized.get("navigation",{}).pop("straight_speed_m_s",None)
            provenance.append(dict(**common, world_sha256=meta.get("world_sha256"),
                robot_description_sha256=meta.get("robot_description_sha256"),
                governor_core_sha256=meta.get("governor_core_sha256"),
                effort_drive_sha256=meta.get("effort_drive_sha256"),
                control_timing_sha256=meta.get("control_timing_sha256"),
                resolved_config_sha256=hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
                config_except_profile_sha256=profile_normalized_hash,
                config_except_planned_treatment_sha256=hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest(),
                oracle_declared=meta.get("governor_has_no_oracle_input") is False))
            clear = data.get("postcontact_until_clearance", {})
            def numeric(key):
                return float(native[key]) if native.get(key) not in (None, "") else None
            row = dict(**common, available=data.get("available", False),
                configured_cruise_m_s=configured_cruise,
                complete=data.get("complete", False),
                physical_success=(native.get("success") == "True") if native else None,
                termination=native.get("termination"), stop_settled=audit.get("post_arrival_stop", {}).get("settled"),
                time_s=numeric("time_seconds"), truth_rmse_m=numeric("truth_path_rmse_m"),
                endpoint_m=numeric("truth_endpoint_error_m"),
                whole_vertical_rms=numeric("rms_vertical_acceleration_m_s2"),
                whole_vertical_peak=numeric("peak_vertical_acceleration_m_s2"),
                whole_slip_rms=numeric("rms_wheel_slip"),
                approach_speed_m_s=data.get("approach_body_speed_m_s"),
                precontact_minimum_scale=data.get("precontact_minimum_scale"),
                first_contact_s=contact, oracle_contact_s=oracle_stamp, oracle_command_s=command,
                contact_to_decision_s=decision_time-contact if decision_time is not None and contact is not None else None,
                governor_event_count=len(event_times),
                precontact_event_count=len(data.get("precontact_governor_event_times_s",[])),
                oracle_stamp_lag_from_first_s=oracle_stamp-contact if oracle_stamp is not None and contact is not None else None,
                motor_target_drop_delay_s=data.get("motor_target_drop_delay_s"),
                first_to_caster_s=data.get("available_time_s"),
                first_to_drive_s=data.get("available_time_to_driven_wheel_s"),
                first_50ms_peak=data.get("first_50ms_acceleration", {}).get("peak"),
                first_50ms_uncontrolled=(decision_time-contact>=.05 if decision_time is not None and contact is not None and profile!="full" else profile=="full"),
                first_50ms_negative_control_eligible=constant_reference_speed is None,
                clearance_available=clear.get("available", False),
                clearance_duration_s=clear.get("duration_s"),
                postcontact_vertical_rms=clear.get("acceleration", {}).get("rms"),
                postcontact_vertical_peak=clear.get("acceleration", {}).get("peak"),
                postcontact_slip_energy_per_m=clear.get("slip_energy_per_m"),
                postcontact_minimum_scale=data.get("postcontact_minimum_scale"),
                recovery_after_first_s=(data["first_recovered_scale_time_s"]-contact
                    if data.get("first_recovered_scale_time_s") is not None else None))
            results.append({**common, **data})
            compact.append(row)
        except Exception as error:
            row = dict(**common, **native_fallback, available=False, reason=f"{type(error).__name__}: {error}")
            compact.append(row)
            results.append(row)
    keys = ("time_s", "truth_rmse_m", "approach_speed_m_s", "whole_vertical_rms", "whole_vertical_peak",
            "whole_slip_rms", "first_50ms_peak", "contact_to_decision_s", "motor_target_drop_delay_s",
            "first_to_caster_s", "first_to_drive_s", "clearance_duration_s", "postcontact_vertical_rms",
            "postcontact_vertical_peak", "postcontact_slip_energy_per_m", "recovery_after_first_s")
    groups = {}
    for profile in source["profiles"]:
        group = [r for r in compact if r["profile"]==profile]
        groups[profile] = dict(requested=len(source["seeds"]), observed=len(group),
            completed=sum(r.get("complete") is True for r in group),
            physical_successes=sum(r.get("physical_success") is True for r in group),
            physical_failures=sum(r.get("physical_success") is False for r in group),
            unavailable=sum(r.get("physical_success") is None for r in group),
            stable_stops=sum(r.get("stop_settled") is True for r in group),
            metrics={key:stats([r.get(key) for r in group]) for key in keys})
    paired = []
    for row in compact:
        if row["profile"]=="full":
            continue
        reference = next((r for r in compact if r["seed"]==row["seed"] and r["profile"]=="full"), None)
        if reference is None:
            continue
        pairs = {key:dict(reference=reference[key], candidate=row[key], delta=row[key]-reference[key],
                        ratio=row[key]/reference[key] if reference[key] else None)
                 for key in keys if row.get(key) is not None and reference.get(key) is not None}
        paired.append(dict(seed=row["seed"], profile=row["profile"], metrics=pairs))
    report = dict(source=str(screen), source_summary_sha256=hashlib.sha256((screen/"summary.json").read_bytes()).hexdigest(),
        full_reference_speed_m_s=constant_reference_speed,
        reference_batch=reference_metadata,
        complete=not source.get("interrupted") and len(compact)==len(source["seeds"])*len(source["profiles"])
            and all(r.get("complete") is True for r in compact),
        contact_analysis_complete=all(r.get("available") is True for r in compact),
        qualification=("Small fixed-geometry, one-speed, "+("contact-oracle" if source.get("oracle_contact") else "sensor-only reactive")+
            " screen. Seeds are cold-start repeats without physical randomization. No identical-state restoration, H1/H3, hardware or generalization claim."),
        groups=groups, episodes=compact, paired_differences=paired, provenance=provenance,
        same_world=len({p["world_sha256"] for p in provenance})==1,
        same_robot=len({p["robot_description_sha256"] for p in provenance})==1,
        same_core=len({p["governor_core_sha256"] for p in provenance})==1,
        same_effort_drive=(bool(provenance) and all(p["effort_drive_sha256"] for p in provenance)
            and len({p["effort_drive_sha256"] for p in provenance})==1),
        same_resolved_config=len({p["resolved_config_sha256"] for p in provenance})==1,
        same_config_except_profile=len({p["config_except_profile_sha256"] for p in provenance})==1,
        same_config_except_planned_treatment=len({p["config_except_planned_treatment_sha256"] for p in provenance})==1,
        training_started=False, optuna_started=False, predictor_started=False)
    (output/"result.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    (output/"contact_analysis.json").write_text(json.dumps(dict(results=results), indent=2, allow_nan=False)+"\n")
    fields = list(dict.fromkeys(key for row in compact for key in row))
    with (output/"episodes.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(compact)
    representative = [r for r in results if r["seed"]==source["seeds"][0] and r.get("available")]
    if representative:
        if constant_reference_speed is not None:
            for row in representative:
                row["controller_label"]=(f"Constant PI {constant_reference_speed:.3f}m/s" if row["profile"]=="full" else "Sensor governor")
        approach_title=("Approach speeds deliberately differ; body slowing includes mechanical impact"
                        if constant_reference_speed is not None else "Full-speed approach; body slowing also includes the mechanical impact")
        plot_timing(representative, output/"timing_first_repeat.png",
            title=f"Single cable — {'simulation-only contact oracle' if source.get('oracle_contact') else 'sensor-only reactive governor'}, seed {source['seeds'][0]}\n{approach_title}")
    print(json.dumps({"complete":report["complete"], "groups":groups}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference-screen",type=Path,help="Matching Full-only cold-start batch")
    args = parser.parse_args()
    summarize(args.screen, args.output, args.reference_screen)
