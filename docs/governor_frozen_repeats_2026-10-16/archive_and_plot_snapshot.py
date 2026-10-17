from pathlib import Path
import csv
import hashlib
import json
import shutil
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path("/home/tuanmac/ninorobot")
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from audit_governor_contact_repeatability import analyze as caster_audit

run=ROOT/"rl_runs/governor_frozen_repeats_2026-10-16"
out=ROOT/"docs/governor_frozen_repeats_2026-10-16"
decision=json.loads((run/"decision.json").read_text())
rows=json.loads((run/"episodes.json").read_text())
out.mkdir(exist_ok=False)
manifest={}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for p in run.rglob("*"):
    if not p.is_file():continue
    manifest[str(p)]=sha(p)
    if p.suffix==".jsonl":continue
    target=out/p.relative_to(run)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,target)
for p in [ROOT/"src/nino_rl/scripts"/n for n in
          ("run_governor_frozen_repeats.py","audit_governor_contact_repeatability.py",
           "audit_governor_readiness_peaks.py","run_frozen_governor_confirmation.py",
           "audit_gt_timestamp_slip.py","audit_governor_phase_slip.py")]:
    (out/"analysis_sources").mkdir(exist_ok=True)
    shutil.copy2(p,out/"analysis_sources"/p.name)
    manifest[str(p)]=sha(p)
shutil.copy2(Path(__file__),out/"archive_and_plot_snapshot.py")
casters=[]
for row in rows:
    try:
        casters.append(dict(attempt=row["attempt"],repeat=row["repeat"],profile=row["profile"],
                            **caster_audit(row["case"])))
    except (OSError,KeyError,ValueError,TypeError,StopIteration) as error:
        casters.append(dict(attempt=row["attempt"],error=str(error)))
(out/"caster_sequence_context.json").write_text(json.dumps(casters,indent=2)+"\n")
guard=json.loads((run/"preservation_before.json").read_text())
changed=[n for n,h in guard.items() if not Path(n).exists() or sha(Path(n))!=h]
expected_old=json.loads((ROOT/"rl_runs/governor_readiness_v1_2026-10-16/episodes.json").read_text())
keys=("robot_description_sha256","governor_core_sha256","effort_drive_sha256","control_timing_sha256")
provenance={k:sorted({r.get("provenance",{}).get(k,"") for r in rows+expected_old}) for k in keys}
owned=[]
for p in Path("/proc").glob("[0-9]*"):
    try:
        if b"GZ_PARTITION=nino_governor_repeatability_101" in (p/"environ").read_bytes().split(b"\0"):
            owned.append(int(p.name))
    except (OSError,PermissionError):pass
checks=dict(attempts=len(rows),expected_attempts=4,
    exact_case_order=[(r["repeat"],r["profile"]) for r in rows]==[(1,"reactive"),(1,"full"),(2,"full"),(2,"reactive")],
    reporting_passes=sum(r.get("reporting_pass",False) for r in rows),
    physical_passes=sum(r.get("physical_pass",False) for r in rows),
    native_replay_passes=sum(r.get("native_replay",{}).get("matches_native",False) for r in rows),
    timestamp_passes=sum(r.get("timestamps",{}).get("passed",False) for r in rows),
    gt_windows_available=sum(all(r.get("gt_native",{}).get(w,{}).get("available",False)
        for w in ("whole_route","crossing")) for r in rows),
    provenance=provenance,fixed_provenance=all(len(v)==1 and v[0] for v in provenance.values()),
    fixed_world_including_previous_pair=len({r.get("world_sha256") for r in rows+expected_old})==1,
    config_sha256=sha(run/"config.yaml"),protected_files=len(guard),changed_protected_files=changed,
    remaining_owned_processes=owned,no_historical_pooling=True,no_scores_rewritten=True)
(out/"verification.json").write_text(json.dumps(checks,indent=2)+"\n")
(out/"source_manifest_sha256.json").write_text(json.dumps(manifest,indent=2)+"\n")
fields=["attempt","repeat","profile","physical_pass","reporting_pass","time_s","physical_rmse_m",
        "whole_vertical_rms","whole_vertical_peak","crossing_rms","crossing_peak","native_slip_rms",
        "gt_whole_slip_rms","gt_crossing_slip2_s_per_m","peak_phase","peak_after_first_contact_s"]
with (out/"episode_metrics.csv").open("w",newline="") as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
    for r in rows:
        result={k:r.get(k) for k in fields[:9]+["native_slip_rms"]}
        result.update(crossing_rms=r.get("crossing_vertical",{}).get("rms"),
            crossing_peak=r.get("crossing_vertical",{}).get("peak"),
            gt_whole_slip_rms=r.get("gt_native",{}).get("whole_route",{}).get("rms"),
            gt_crossing_slip2_s_per_m=r.get("gt_native",{}).get("crossing",{}).get("slip_square_per_m"),
            peak_phase=r.get("peak_context",{}).get("command_at_peak",{}).get("governor_phase"),
            peak_after_first_contact_s=r.get("peak_context",{}).get("peak_after_first_contact_s"))
        writer.writerow(result)
fig,axes=plt.subplots(1,2,figsize=(10,4))
for ax,metric,label in [(axes[0],"rms","Post-contact vertical RMS (m/s²)"),
                       (axes[1],"peak","Post-contact vertical peak (m/s²)")]:
    for arm,shift,color,title in [("full",-.18,"tab:blue","PI"),("reactive",.18,"tab:orange","Governor")]:
        values=[]
        for rep in (1,2):
            matching=[r for r in rows if r["repeat"]==rep and r["profile"]==arm]
            values.append(matching[0]["crossing_vertical"][metric] if matching and matching[0].get("reporting_pass") else float("nan"))
        bars=ax.bar([1+shift,2+shift],values,width=.35,label=title,color=color)
        ax.bar_label(bars,fmt="%.2f",fontsize=8,padding=3)
    ax.set_xticks([1,2],["Repeat 1","Repeat 2"]);ax.set_ylabel(label)
    ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True);ax.legend(fontsize=8)
    ax.margins(y=.2)
fig.suptitle("Four frozen cold starts; one observation per arm/repeat; no pooling with prior pair",fontsize=10)
fig.tight_layout();fig.savefig(out/"repeatability.png",dpi=150);plt.close(fig)
print(json.dumps(checks,indent=2))
for c in casters:
    print("CASTER",c.get("attempt"),c.get("precontact_body_median_m_s"),c.get("precontact_caster"))
