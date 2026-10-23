"""Review the corrected-logger batch without repairing missing samples or scores."""
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl")]
from audit_governor_phase_slip import load
from audit_gt_timestamp_slip import gt_timestamp_series


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    bundle=ROOT/"docs/governor_corrected_logger_cadence_2026-10-21"
    run=ROOT/"rl_runs/governor_corrected_logger_cadence_2026-10-21"
    output=bundle/"execution_review";output.mkdir(exist_ok=False)
    ledger=json.loads((run/"ledger.json").read_text())
    result=ledger["slots"][0]["result"]
    logger,evaluation=Path(result["logger"]),Path(result["evaluation"])
    inputs={run/"ledger.json",run/"summary.json",run/"authorization_snapshot.json",
            run/"attempt_01/result.json",bundle/"protocol.json",bundle/"execution_release.json",
            logger/"samples.jsonl",logger/"observer_health.jsonl",logger/"metadata.json",
            logger/"observer_health_summary.json",Path(__file__).resolve()}
    inputs.update(evaluation.glob("episode-*/*trace.csv"));inputs.add(evaluation/"episodes.csv")
    before={str(p):sha(p) for p in inputs}
    data=load(Path(result["case"]),dict(seed=77600,profile="full",evaluation=str(evaluation),logger=str(logger)))
    signal=gt_timestamp_series(data)
    q=result["quality"];old=q["existing_reports"]
    start=old["first_contact_s"]+.05;end=old["clearance_s"]
    gap=[]
    times=data["joints"][:,0]
    for i in np.where((times[:-1]<end)&(times[1:]>start)&(np.diff(times)>.010001))[0]:
        gap.append(dict(start_s=float(times[i]),end_s=float(times[i+1]),gap_s=float(times[i+1]-times[i])))
    mask=(signal["time"]>=start)&(signal["time"]<=end)&(~np.isfinite(signal["q"]))
    health=[json.loads(line) for line in (logger/"observer_health.jsonl").open()]
    slow=max(health,key=lambda x:x["duration_ns"])
    index=health.index(slow)
    drive_path=next(evaluation.glob("episode-*/drive_trace.csv"))
    drive=list(csv.DictReader(drive_path.open()))
    during=[r for r in drive if gap[0]["start_s"]<float(r["sim_time_s"])<gap[0]["end_s"]]
    evidence=dict(summary=json.loads((run/"summary.json").read_text()),
        all_assigned_attempts=[dict(attempt=s["attempt"],seed=s["seed"],repeat=s["repeat"],
            arm=s["arm"],status=s["status"],physical_success=s["physical_success"]) for s in ledger["slots"]],
        corrected_logger_Gazebo_closure_validated=True,
        passed_checks={k:result[k] for k in ("setup_pass","provenance_pass","measurement_integrity_pass",
            "physical_success","stop_pass","cleanup_confirmed")},
        cadence_integrity=result["cadence_integrity"],
        health_integrity=result["observer_health_integrity"],
        quality_available=result["quality_available"],
        whole_GT=result["integrity"]["whole_GT"],native_replay=result["integrity"]["native_replay"],
        crossing=old["gt_native"]["crossing"],postcontact=q["postcontact"],
        missing_joint_intervals=gap,invalid_GT_slip_stamps_s=signal["time"][mask].tolist(),
        callback_neighborhood=health[max(0,index-4):index+8],
        original_drive_records_during_joint_gap=during,
        decision="Keep the batch stopped at attempt1. No fast-governor run or cadence benefit estimate. Logger closure passes; crossing measurement fails.",
        next_proposal="Decouple high-rate joint/GT acquisition from synchronous contact conversion; first verify capture/ordering/no-loss with injected callback stalls offline. No queue/rate/coverage/controller changes or new simulation in this review.",
        causal_limit="Measured time lies within contact message conversion, including any GC/descheduling. This does not uniquely identify CPU conversion, GC, DDS or OS scheduling, nor prove the older3.32s gap had the same cause.",
        simulation_launches_by_review=0,metrics_changed=False,thresholds_applied=False,H2_decision="not_assessed")
    assert len(gap)==1 and abs(gap[0]["gap_s"]-.036)<1e-9
    assert np.allclose(evidence["invalid_GT_slip_stamps_s"],[14.92,14.94],rtol=0,atol=1e-9)
    assert all(evidence["passed_checks"].values()) and not evidence["quality_available"]
    assert evidence["crossing"]["coverage_fraction"]<.98
    assert evidence["whole_GT"]["coverage_fraction"]>=.98
    assert sum(s["launch_requested"] for s in ledger["slots"])==1
    assert all(s["status"]=="not_attempted" for s in ledger["slots"][1:])
    for path,h in before.items():assert sha(Path(path))==h,path
    (output/"report.json").write_text(json.dumps(evidence,indent=2,allow_nan=False)+"\n")
    (output/"inputs_sha256.json").write_text(json.dumps(dict(sorted(before.items())),indent=2)+"\n")
    print(json.dumps(dict(attempted=1,unattempted=11,closure_valid=True,
        crossing_coverage=evidence["crossing"]["coverage_fraction"],
        joint_gap_s=gap[0]["gap_s"],inputs_unchanged=True),indent=2))


if __name__=="__main__":
    main()
