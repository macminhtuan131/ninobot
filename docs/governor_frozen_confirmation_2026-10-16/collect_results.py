"""Archive this bounded experiment without copying/modifying large raw logs."""
import csv
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/"rl_runs/governor_frozen_confirmation_2026-10-16"
OUT = Path(__file__).resolve().parent


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""): result.update(chunk)
    return result.hexdigest()


def main():
    for name in ("protocol_before_results.json", "frozen_config.yaml", "instrumentation_gate.json",
                 "confirmation_episodes.json", "decision.json"):
        shutil.copy2(RUN/name, OUT/name)
    for name in ("execution_before_results.json", "execution_result.json"):
        shutil.copy2(RUN/"confirmation"/name, OUT/name)
    rows = json.loads((RUN/"confirmation_episodes.json").read_text())
    decision = json.loads((RUN/"decision.json").read_text())
    with (OUT/"episodes.csv").open("w", newline="") as stream:
        keys = ["scenario", "seed", "profile", "available", "physical_success", "physical_pass",
                "time_s", "physical_rmse_m", "native_slip_rms", "whole_vertical_rms", "whole_vertical_peak",
                "whole_rms", "crossing_slip2_per_m", "shifted_whole_rms", "shifted_crossing_slip2_per_m",
                "crossing_vertical_rms", "crossing_vertical_peak", "error"]
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
        for r in rows:
            flat = {key:r.get(key) for key in keys}
            for prefix, origin in (("", "primary"), ("shifted_", "shifted")):
                flat[prefix+"whole_rms"] = r.get(origin,{}).get("whole_route",{}).get("rms")
                flat[prefix+"crossing_slip2_per_m"] = r.get(origin,{}).get("crossing",{}).get("slip_square_per_m")
            for suffix in ("rms","peak"):
                flat["crossing_vertical_"+suffix] = (r.get("crossing_vertical") or {}).get(suffix)
            writer.writerow(flat)
    figure, axes = plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
    pairs = decision["paired"]
    for ax,key,title in zip(axes,("whole_rms","crossing_per_m"),("Whole-route slip RMS", "Post-contact slip² integral/metre")):
        for offset, origin, label in ((-.08,"primary","50 Hz primary grid"),(.08,"shifted","50 Hz grid +10 ms")):
            values = [p.get("ratios",{}).get(origin,{}).get(key) for p in pairs]
            ax.scatter([i+offset for i,v in enumerate(values) if v is not None],
                       [v for v in values if v is not None], label=label, s=45)
        ax.axhline(1.,color="black",ls="--",lw=1)
        ax.set_ylabel("Governor / paired PI"); ax.set_title(title); ax.grid(alpha=.2)
        ax.set_xticks(range(len(pairs)),[f"{p['scenario']}\n{p['seed']}" for p in pairs])
    axes[0].legend(ncol=2); axes[-1].set_xlabel("Scenario and independent cold-start repeat")
    figure.suptitle("Frozen governor: all eight paired blocks retained; below1 favours governor\nNo retuning, impact/safety claim or sensor-frequency reconstruction")
    figure.savefig(OUT/"paired_sampling_sensitivity.png",dpi=160);plt.close(figure)
    sources = OUT/"analysis_sources"; sources.mkdir(exist_ok=True)
    for path in [ROOT/"src/nino_rl/scripts/run_frozen_governor_confirmation.py",
                 ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py",ROOT/"src/nino_rl/nino_rl/slip_reporting.py",
                 ROOT/"src/nino_rl/nino_rl/ros_env.py",ROOT/"src/nino_rl/nino_rl/evaluation.py",
                 ROOT/"src/nino_rl/nino_rl/governor_logger.py",ROOT/"src/nino_control/nino_control/governor_core.py",
                 ROOT/"src/nino_rl/launch/factory_floor_governor.launch.py",ROOT/"src/nino_rl/launch/factory_floor_training.launch.py"]:
        shutil.copy2(path,sources/path.name)
    cases = []
    for stage in [RUN/"instrumentation", *sorted((RUN/"confirmation").glob("s*"))]:
        for case in sorted((stage/"screen").glob("seed_*")):
            loggers = list(case.glob("contact/*/metadata.json"))
            evaluations = list(case.glob("evaluation/*/summary.json"))
            target = OUT/"cases"/stage.name/case.name;target.mkdir(parents=True,exist_ok=True)
            record = dict(case=str(case.relative_to(ROOT)), raw_sha256={})
            if loggers:
                logger = loggers[0].parent
                for name in ("metadata.json","resolved_config.json","world_metadata.json","robot_description.urdf"):
                    if (logger/name).exists():shutil.copy2(logger/name,target/name)
                for name in ("samples.jsonl","contact_events.jsonl"):
                    if (logger/name).exists():record["raw_sha256"][str((logger/name).relative_to(ROOT))]=sha(logger/name)
            if evaluations:
                for name in ("episodes.csv","summary.json","metadata.json"):
                    path = evaluations[0].parent/name
                    if path.exists():shutil.copy2(path,target/("evaluation_"+name))
            if (case/"audit.json").exists():shutil.copy2(case/"audit.json",target/"audit.json")
            cases.append(record)
    guard = json.loads(Path("/tmp/nino_slip_reporting_preservation_guard.json").read_text())
    changed = [p for p,digest in guard.items() if sha(ROOT/p)!=digest]
    assert not changed, changed
    (OUT/"preservation_check.json").write_text(json.dumps(dict(guarded_files=len(guard),changed=changed,unchanged=True),indent=2)+"\n")
    (OUT/"raw_manifest.json").write_text(json.dumps(dict(cases=cases,total_cases=len(cases)),indent=2)+"\n")
    print("Archived",len(cases),"cases; old278-file guard unchanged")


if __name__=="__main__":main()
