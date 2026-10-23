#!/usr/bin/env python3
"""12-slot executor: offline dry-run by default; live needs a separate release.

No implicit authorization, resume, replacement, retry, or extra smoke episode.
"""
import argparse
from copy import deepcopy
import csv
import fcntl
import json
import math
from pathlib import Path
import signal

from prepare_governor_cadence_experiment import ROOT, ARMS, validate, validate_schedule, sha
from run_governor_h2_replication import atomic_json, classify, LiveAdapter, collect_attempt


def cadence_trace_check(evaluation, arm):
    controls = list(csv.DictReader(next(evaluation.glob("episode-*/control_trace.csv")).open()))
    paths = list(evaluation.glob("episode-*/governor_update_trace.csv"))
    if arm != "reactive_20ms":
        return dict(valid=not paths, micro_updates=0, score_rows=len(controls))
    if len(paths) != 1:
        return dict(valid=False, reason="missing_full20ms_trace")
    rows = list(csv.DictReader(paths[0].open()))
    if len(rows) != 5*len(controls) or not rows:
        return dict(valid=False, reason="not_exactly5_updates_per_score_interval")
    for i,c in enumerate(controls):
        begin, end = float(c["governor_input_time_s"]), float(c["sim_time_s"])
        if not math.isclose(end-begin,.1,abs_tol=1e-8):
            return dict(valid=False,reason="scoring_interval_changed")
        for j,r in enumerate(rows[5*i:5*i+5]):
            t = float(r["governor_input_time_s"])
            if not all(math.isclose(a,b,abs_tol=1e-8) for a,b in (
                    (t,begin+j*.02),(float(r["imu_window_start_s"]),t-.1),
                    (float(r["imu_window_end_s"]),t),(float(r["cadence_update_seconds"]),.02),
                    (float(r["target_acceleration_window_seconds"]),.1))):
                return dict(valid=False,reason="cadence_or_feature_window_changed")
            if any(not -1e-9 <= t-float(r[k]) <= .100000001 for k in (
                    "imu_stamp_s","joint_stamp_s","governor_feedback_stamp_s")):
                return dict(valid=False,reason="stale_or_future_hardware_stamp")
            if r["target_history_ready"] == "True":
                if float(r["target_history_support_s"]) > t-.1+1e-8:
                    return dict(valid=False,reason="target_acceleration_uses_shorter_window")
            elif t-float(rows[0]["governor_input_time_s"]) > .1+1e-8:
                return dict(valid=False,reason="missing_target_history_after_warmup")
    return dict(valid=True,micro_updates=len(rows),score_rows=len(controls),
                qualification="Timestamp/coverage checks only; body response/benefit still needs analysis")


def run_attempts(protocol, output, adapter, verify=lambda:None, *, dry_run=True, authorization=None):
    validate_schedule(protocol["schedule"])
    if not dry_run and not (authorization and authorization.get("release",{}).get("execution_authorized") is True
            and authorization["release"].get("maximum_attempts")==12):
        raise ValueError("Live adapter needs the separately validated execution release")
    output.mkdir(parents=True,exist_ok=False)
    rows = [dict(**job,status="not_attempted",launch_requested=False,adapter_requested=False,
                 result=None,physical_success=None,termination=None,error=None) for job in protocol["schedule"]]
    atomic_json(output/"protocol_snapshot.json",protocol)
    atomic_json(output/"authorization_snapshot.json",authorization or dict(dry_run=True,execution_authorized=False))
    def save():
        atomic_json(output/"ledger.json",dict(maximum_attempts=12,dry_run=dry_run,slots=rows))
    save(); stop=None
    for row in rows:
        try:
            verify()
            row.update(status="starting",adapter_requested=True,launch_requested=not dry_run)
            save()  # assigned attempt durable BEFORE a child could be launched
            attempt=output/f"attempt_{row['attempt']:02d}"
            attempt.mkdir()
            result=adapter(deepcopy(row),attempt)
            row.update(status="collected",result=result,physical_success=result.get("physical_success"),
                       termination=result.get("termination"))
            stop=classify(result)
            if not stop and result.get("stop_pass") is False:
                stop="hard_stop_unstable_stopping"
            save()
            if stop:
                break
        except BaseException as error:
            row.update(status="interrupted_or_error",error=f"{type(error).__name__}: {error}")
            stop="hard_stop_exception_no_retry"
            save(); break
    try:
        verify()
    except BaseException as error:
        stop=f"hard_stop_final_provenance: {type(error).__name__}: {error}"
    summary=dict(mode="offline_synthetic" if dry_run else "descriptive_cadence_experiment",
        status=stop or "twelve_assigned_attempts_complete_unscored",maximum_attempts=12,
        adapter_calls=sum(r["adapter_requested"] for r in rows),
        simulation_launches=sum(r["launch_requested"] for r in rows),
        physical_failures=sum(r["physical_success"] is False for r in rows),
        missing_outcomes=sum(r["adapter_requested"] and r["physical_success"] is None for r in rows),
        unattempted=[r["attempt"] for r in rows if not r["adapter_requested"]],
        retries=0,replacements=0,extra_smoke=0,automatic_extension=False,
        H2_decision="not_assessed",thresholds_applied=False,PPO=False,optuna=False,predictor=False)
    atomic_json(output/"summary.json",summary)
    return summary


def synthetic(job,attempt):
    return dict(synthetic=True,setup_pass=True,provenance_pass=True,measurement_integrity_pass=True,
        cleanup_confirmed=True,runner_exit=0,physical_success=True,termination="success",
        physical_state_valid=True,quality_available=True,stop_pass=True)


def require_release(bundle, release):
    valid=validate(bundle)
    r=json.loads(release.read_text())
    if not (r.get("execution_authorized") is True and r.get("budget_released") is True
            and r.get("maximum_attempts")==12 and r.get("mode")=="descriptive_cadence_experiment"
            and r.get("protocol_sha256")==valid["protocol_sha256"]
            and r.get("thresholds_applied") is False
            and isinstance(r.get("authorization_reference"),str) and r["authorization_reference"].strip()):
        raise ValueError("No matching12-attempt release; preparation is not permission to simulate")
    return r


def execute(bundle, output, release, domain):
    r=require_release(bundle,release)
    release_hash=sha(release)
    protocol=json.loads((bundle/"protocol.json").read_text())
    def verify():
        if require_release(bundle,release)!=r or sha(release)!=release_hash:
            raise ValueError("Execution release drift")
    def collector(view,job,attempt):
        result=collect_attempt(view,job,attempt)
        try:
            check=cadence_trace_check(Path(result["evaluation"]),job["arm"])
        except (OSError,ValueError,KeyError,StopIteration) as error:
            check=dict(valid=False,reason=f"{type(error).__name__}: {error}")
        result["cadence_integrity"]=check
        result["measurement_integrity_pass"] &= check["valid"]
        result["arm"]=job["arm"]
        return result
    def adapter(job,attempt):
        print(f"ATTEMPT {job['attempt']}/12 seed={job['seed']} repeat={job['repeat']} arm={job['arm']}",flush=True)
        return LiveAdapter(bundle/"arm_views"/job["arm"],domain,collector=collector)(job,attempt)
    def interrupted(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    with open(f"/tmp/nino_h2_executor_domain_{domain}.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if output.exists():
            raise FileExistsError("No overwrite/resume/retry")
        claims=ROOT/"rl_runs/.governor_cadence_budget_claims";claims.mkdir(exist_ok=True)
        marker=claims/(r["protocol_sha256"]+".consumed.json")
        with marker.open("x") as f:
            json.dump(dict(maximum_attempts=12,output=str(output),release_sha256=sha(release)),f)
            f.flush()
            import os
            os.fsync(f.fileno())
        return run_attempts(protocol,output,adapter,verify,dry_run=False,
            authorization=dict(release=r,release_sha256=release_hash,release_claim=str(marker),
                               domain=domain,partition=f"nino_h2_replication_{domain}"))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--release",type=Path,help="Explicit separate12-attempt authorization; absent means synthetic only")
    p.add_argument("--domain",type=int,default=130)
    a=p.parse_args()
    validate(a.bundle)
    if a.release:
        answer=execute(a.bundle,a.output,a.release,a.domain)
    else:
        answer=run_attempts(json.loads((a.bundle/"protocol.json").read_text()),a.output,synthetic,
                            lambda:validate(a.bundle),dry_run=True)
    print(json.dumps(answer,indent=2))
