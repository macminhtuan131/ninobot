"""Archive measured source/config provenance; leave large raw streams in rl_runs."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/"rl_runs/governor_contact_repeatability_2026-10-16"
OUT=Path(__file__).resolve().parent
archive=OUT/"provenance";archive.mkdir(exist_ok=True)
for name in ("plan.json","summary.json","runner_snapshot.py"):
    shutil.copy2(RAW/name,archive/name)
manifest=[]
for case in sorted(RAW.glob("seed_*")):
    logger=next(case.glob("contact/*/metadata.json")).parent
    dest=archive/case.name;dest.mkdir(exist_ok=True)
    meta=json.loads((logger/"metadata.json").read_text())
    for name in ("metadata.json","source_config.yaml","resolved_config.json","robot_description.urdf",
                 "effort_drive_source.py","control_timing_source.py","world_metadata.json"):
        shutil.copy2(logger/name,dest/name)
    for name in ("effort_drive","control_timing"):
        assert hashlib.sha256((dest/(name+"_source.py")).read_bytes()).hexdigest()==meta[name+"_sha256"]
    core=ROOT/"src/nino_control/nino_control/governor_core.py"
    assert hashlib.sha256(core.read_bytes()).hexdigest()==meta["governor_core_sha256"]
    world=ROOT/"src/nino_description/worlds/factory_floor_cable_box_capsule_contact_lab.sdf"
    assert hashlib.sha256(world.read_bytes()).hexdigest()==meta["world_sha256"]
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    for name in ("summary.json","episodes.csv"):
        shutil.copy2(evaluation/name,dest/("evaluation_"+name))
    for name in ("audit.json","config.yaml"):
        shutil.copy2(case/name,dest/name)
    manifest.append(dict(case=str(case.relative_to(ROOT)),raw_sha256={
        str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (logger/"samples.jsonl",logger/"contact_events.jsonl")}))
shutil.copy2(core,archive/"governor_core.py")
shutil.copy2(world,archive/world.name)
shutil.copy2(ROOT/"docs/CONTACT_REPEATABILITY_TIMING_2026-10-16.md",archive/"protocol_and_report.md")
sources=OUT/"analysis_sources";sources.mkdir(exist_ok=True)
for name in ("audit_pi_contact_repeatability.py","audit_single_cable_screen.py",
             "analyze_governor_experiment.py","summarize_contact_oracle_h2.py",
             "audit_cable_contact_geometry.py","summarize_contact_repeatability.py"):
    shutil.copy2(ROOT/"src/nino_rl/scripts"/name,sources/name)
(archive/"manifest.json").write_text(json.dumps(dict(raw_runs=manifest,archived_sha256={
    str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
    for base in (archive,sources) for p in sorted(base.rglob("*"))
    if p.is_file() and p.name!="manifest.json"}),indent=2)+"\n")
print("Archived source/config/native outcomes and raw stream hashes")
