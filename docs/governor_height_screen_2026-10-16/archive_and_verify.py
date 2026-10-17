"""Archive small files and verify completed attempts, without rerunning simulation."""
from pathlib import Path
import json
import hashlib
import shutil

ROOT=Path(__file__).resolve().parents[2]
root=ROOT/"rl_runs/governor_height_screen_2026-10-16"
out=Path(__file__).resolve().parent
rows=json.loads((out/"episodes.json").read_text())
manifest={}


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def copy(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)
    manifest[str(src.resolve())]=sha(src)


def write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


for name in ("protocol_before_results.json","prepared_protocol_snapshot.json","decision.json","config.yaml","preservation_before.json"):
    copy(root/name,out/name)
for src in (root/"source_snapshot").iterdir():copy(src,out/"source_snapshot"/src.name)
for row in rows:
    block=root/f"attempt_{row['attempt']:02d}"
    case=Path(row["case"])
    log=next(case.glob("contact/*/metadata.json")).parent
    evaluation=next(case.glob("evaluation/*/summary.json")).parent
    selected=[block/"run.log",block/"protocol_before_results.json",block/"confirmation/height/scenario.sdf",
              block/"confirmation/height/scenario.json",case/"audit.json",case/"config.yaml",case/"evaluate.log",
              evaluation/"summary.json",evaluation/"episodes.csv"]
    selected+=list(evaluation.glob("episode-*/*trace.csv"))
    selected +=[log/name for name in ("metadata.json","world_metadata.json","resolved_config.json","robot_description.urdf")]
    for src in selected:
        if src.is_file():copy(src,out/"cases"/f"attempt_{row['attempt']:02d}"/src.relative_to(block))
    for src in (log/"samples.jsonl",log/"contact_events.jsonl"):manifest[str(src.resolve())]=sha(src)
for src in (ROOT/"src/nino_rl/scripts/audit_governor_height_screen.py",ROOT/"src/nino_rl/test/test_governor_height_screen.py"):
    copy(src,out/"analysis_sources"/src.name)
write(out/"input_manifest_sha256.json",manifest)
prior=json.loads((root/"preservation_before.json").read_text())
changed=[name for name,digest in prior.items() if not Path(name).is_file() or sha(name)!=digest]
remaining=[]
for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():continue
    try:
        if b"GZ_PARTITION=nino_height_screen_105" in (proc/"environ").read_bytes().split(b"\0"):
            remaining.append(dict(pid=int(proc.name),command=(proc/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")))
    except OSError:pass
checks=dict(eight_attempts=len(rows)==8,all_arrival_stop=all(r["physical_pass"] for r in rows),
    all_reporting=all(r["reporting_pass"] for r in rows),all_native_replay=all(r["native_replay"]["matches_native"] for r in rows),
    all_timestamps=all(r["timestamps"]["passed"] for r in rows),
    all_logs_closed=all(json.loads(next(Path(r["case"]).glob("contact/*/metadata.json")).read_text())["complete"] for r in rows),
    same_robot=len({r["provenance"]["robot_description_sha256"] for r in rows})==1,
    same_PI_core_timing=all(len({r["provenance"][key] for r in rows})==1 for key in ("effort_drive_sha256","control_timing_sha256","governor_core_sha256")),
    same_world_within_height=all(len({r["world_sha256"] for r in rows if r["height_m"]==height})==1 for height in (.006,.022)),
    different_height_worlds=len({r["world_sha256"] for r in rows})==2,
    all_mechanism_available=all(r["mechanism"]["available"] for r in rows),
    protected_unchanged=not changed,owned_processes_closed=not remaining)
verification=dict(checks=checks,all_pass=all(checks.values()),protected_files=len(prior),changed_protected=changed,
    raw_input_and_snapshot_files=len(manifest),remaining_owned_processes=remaining,
    feedback_age_range_s=[min(r["readiness"]["age_range_s"][0] for r in rows),max(r["readiness"]["age_range_s"][1] for r in rows)],
    minimum_interval_samples=min(r["readiness"]["min_interval_samples"] for r in rows),
    minimum_GT_whole_coverage=min(r["gt_native"]["whole_route"]["coverage_fraction"] for r in rows),
    minimum_GT_cross_coverage=min(r["gt_native"]["crossing"]["coverage_fraction"] for r in rows),
    geometry_protocol_tests_passed=4,extra_attempts=False,hardware_validated=False)
write(out/"verification.json",verification)
research=Path("/home/tuanmac/.codex/attachments/08d8744c-610a-4653-afef-78a42030823d/Pasted text.txt")
write(out/"research_alignment.json",dict(source=str(research),sha256=sha(research),
    sections=["Thí nghiệm đầu tiên: quyền điều khiển và timing của H2","Điều kiện vào tuning, RL và robot thật"],
    applied=["H2 before H1/predictor/H3","Classical scripted/sensor interventions, no PPO",
             "Keep PI/physics and record final executed commands","Separate obstacle regimes and retain failures/uncertainty",
             "Bounded budget then offline audit and go/no-go"],
    limits="Eight-case height mechanism screen, not the full proposed multi-family matrix or a hardware validation."))
print(json.dumps(verification,indent=2))
assert verification["all_pass"]
