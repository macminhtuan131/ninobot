"""Archive the completed bounded study without rerunning any episode."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/"rl_runs/classical_governor_crossing_tune_2026-10-16"
OUT=Path(__file__).resolve().parent
decision=json.loads((RAW/"decision.json").read_text())
contract=json.loads((RAW/"contract.json").read_text())
assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha
           for path,sha in contract["source_sha256"].items()),"Frozen runtime source changed"
for name in ("contract.json","decision.json","protocol_before_results.md","tuner_snapshot.py",
             "selection_before_validation.json","study.sqlite3"):
    if (RAW/name).exists():shutil.copy2(RAW/name,OUT/name)
summaries=[];manifest=[];observed=passed=0
for folder in [*sorted(RAW.glob("trial_*")),RAW/"validation"]:
    if not folder.is_dir():continue
    dest=OUT/folder.name;dest.mkdir(exist_ok=True)
    for name in ("score.json","config.yaml"):
        if (folder/name).exists():shutil.copy2(folder/name,dest/name)
    analysis=folder/"analysis"
    if (analysis/"result.json").exists():
        for name in ("result.json","episodes.csv","contact_analysis.json","timing_first_repeat.png"):
            shutil.copy2(analysis/name,dest/name)
        result=json.loads((analysis/"result.json").read_text())
        costs=[]
        for pair in result["paired_differences"]:
            m=pair["metrics"]
            keys=("time_s","postcontact_slip_energy_per_m","truth_rmse_m")
            if not all(k in m for k in keys):continue
            t,s,p=(m[k]["ratio"] for k in keys)
            costs.append(dict(seed=pair["seed"],time_ratio=t,slip_ratio=s,path_ratio=p,
                time_term=.5*t,slip_term=.5*s,tracking_excess=max(0,p-1.05),
                total=.5*(t+s)+max(0,p-1.05)))
        summaries.append(dict(stage=folder.name,score=json.loads((folder/"score.json").read_text()),
            groups=result["groups"],paired_costs=costs,episodes=result["episodes"]))
    screen=folder/"screen"
    for name in ("plan.json","summary.json","runner_snapshot.py"):
        if (screen/name).exists():shutil.copy2(screen/name,dest/("screen_"+name))
    if (screen/"summary.json").exists():
        rows=json.loads((screen/"summary.json").read_text())["results"]
        observed+=len(rows);passed+=sum(r["passed"] for r in rows)
    for case in sorted(screen.glob("seed_*")):
        matches=list(case.glob("contact/*/metadata.json"))
        if len(matches)!=1:continue
        logger=matches[0].parent;meta=json.loads(matches[0].read_text())
        case_dest=dest/"provenance"/case.name;case_dest.mkdir(parents=True,exist_ok=True)
        for name in ("metadata.json","resolved_config.json","source_config.yaml","robot_description.urdf",
                     "effort_drive_source.py","control_timing_source.py","world_metadata.json"):
            shutil.copy2(logger/name,case_dest/name)
        evaluation=list(case.glob("evaluation/*/summary.json"))
        if len(evaluation)==1:
            for name in ("summary.json","episodes.csv"):
                shutil.copy2(evaluation[0].parent/name,case_dest/("evaluation_"+name))
        manifest.append(dict(case=str(case.relative_to(ROOT)),logger_closed=meta.get("complete"),
            world_sha256=meta.get("world_sha256"),robot_sha256=meta.get("robot_description_sha256"),
            core_sha256=meta.get("governor_core_sha256"),pi_sha256=meta.get("effort_drive_sha256"),
            raw_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (logger/"samples.jsonl",logger/"contact_events.jsonl")}))
(OUT/"study_results.json").write_text(json.dumps(dict(decision=decision,stages=summaries,
    observed_episodes=observed,native_motion_passes=passed,budget=contract["max_episodes"],
    qualification="Three fixed queued candidates, two dev blocks and at most three separate validation blocks; fixed geometry, no impact or deployment promotion."),indent=2)+"\n")
sources=OUT/"analysis_sources";sources.mkdir(exist_ok=True)
for path in ("src/nino_control/nino_control/governor_core.py",
             "src/nino_description/worlds/factory_floor_cable_box_capsule_contact_lab.sdf"):
    shutil.copy2(ROOT/path,sources/Path(path).name)
for name in ("tune_classical_governor.py","run_clear_floor_repeat.py","summarize_contact_oracle_h2.py",
             "audit_single_cable_screen.py","analyze_governor_experiment.py"):
    shutil.copy2(ROOT/"src/nino_rl/scripts"/name,sources/name)
(OUT/"manifest.json").write_text(json.dumps(dict(cases=manifest,archived_sha256={
    str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="manifest.json"}),indent=2)+"\n")
print("Collected",observed,"native outcomes; motion passed",passed)
