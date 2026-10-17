"""Archive closed-run reliability and hashes; no native/study rescore."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
run=ROOT/"rl_runs/governor_brake_delay_2026-10-16"
rows=json.loads((out/"episodes.json").read_text())
phases=json.loads((out/"phase_slip.json").read_text())
evidence=dict(episodes=len(rows),physical_passes=sum(bool(r["physical_pass"]) for r in rows),
    reporting_passes=sum(bool(r["reporting_pass"]) for r in rows),
    native_replays=sum(bool(r["native_replay"]["matches_native"]) for r in rows),
    timestamp_passes=sum(bool(r["timestamps"]["passed"]) for r in rows),
    feedback_age_range_s=[min(r["readiness"]["age_range_s"][0] for r in rows),max(r["readiness"]["age_range_s"][1] for r in rows)],
    minimum_diagnostics_per_action=min(r["readiness"]["min_interval_samples"] for r in rows),
    minimum_GT_whole_coverage=min(r["gt_native"]["whole_route"]["coverage_fraction"] for r in rows),
    minimum_GT_crossing_coverage=min(r["gt_native"]["crossing"]["coverage_fraction"] for r in rows),
    first_50ms_unavailable=sum(not r["first_50ms"]["available"] for r in rows),
    same_world=len({r["world_sha256"] for r in rows})==1,
    same_provenance=all(len({r["provenance"][k] for r in rows})==1 for k in rows[0]["provenance"]),
    precontact_events=[r["precontact_events"] for r in rows],
    first_loaded_components=[r["mechanism"]["first_loaded_components"] for r in rows],
    phase_coverage_and_conservation=all(v["coverage_pass"] and v["conservation_pass"] for p in phases for v in p["arms"].values()),
    phase_excess_pending_delay=[])
for p in phases:
    a=p["arms"]["delayed_200ms"]
    for reference in ("full","frozen_reactive"):
        b=p["arms"][reference]
        excess={k:v["slip_square_integral_s"]-b["phases"][k]["slip_square_integral_s"] for k,v in a["phases"].items()}
        evidence["phase_excess_pending_delay"].append(dict(seed=p["seed"],reference=reference,
            excess_integral_s=excess,total_excess_s=a["phase_sum_s"]-b["phase_sum_s"]))
(out/"reliability.json").write_text(json.dumps(evidence,indent=2,allow_nan=False)+"\n")
inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in run.rglob("*")
        if p.is_file() and p.suffix in (".json",".jsonl",".csv",".yaml",".sdf",".urdf",".py")}
(out/"input_sha256.json").write_text(json.dumps(inputs,indent=2)+"\n")
print(json.dumps(evidence,indent=2))
print("Input files hashed:",len(inputs))
