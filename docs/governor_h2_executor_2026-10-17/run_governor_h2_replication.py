#!/usr/bin/env python3
"""Bounded H2 executor. Default is offline planning; live mode needs a sealed release.

No resume, retries, replacement episodes, training, tuning or automatic promotion.
Importing this module does not import ROS or start subprocesses.
"""
import argparse
from copy import deepcopy
import csv
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import yaml

from prepare_governor_h2_protocol import (
    ROOT, application_issues, sha, validate_bundle, validate_schedule,
)

ORDINARY_FAILURES = {"timeout", "stall", "off_path", "wrong_direction", "goal_missed"}


def execution_dependencies():
    """Supplement the original bundle with launch and indirect helper sources."""
    folders=("src/nino_rl/nino_rl","src/nino_rl/scripts","src/nino_rl/launch",
             "src/nino_control/nino_control","src/nino_description/launch","src/nino_description/urdf")
    return {str(p.relative_to(ROOT)):sha(p) for folder in folders for p in sorted((ROOT/folder).rglob("*"))
            if p.is_file() and p.suffix in (".py",".xacro",".urdf") and "__pycache__" not in p.parts}


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix+".tmp")
    with temporary.open("w") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+"\n")
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,path)
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(parent)
    finally:os.close(parent)


def append_event(root, event):
    with (root/"events.jsonl").open("a") as stream:
        stream.write(json.dumps(event,allow_nan=False)+"\n")
        stream.flush();os.fsync(stream.fileno())


def require_release(bundle, release_path):
    """An application proposal/filled form is not an execution authorization."""
    validate_bundle(bundle)
    if release_path is None:
        raise ValueError("No budget release; offline preparation only")
    release=json.loads(release_path.read_text())
    required=(release.get("budget_released") is True and release.get("execution_authorized") is True
        and type(release.get("maximum_attempts")) is int and release["maximum_attempts"]==16
        and release.get("protocol_sha256")==sha(bundle/"protocol.json")
        and release.get("executor_sha256")==sha(Path(__file__))
        and release.get("application_sha256")==sha(bundle/"application_requirements.json")
        and release.get("execution_dependency_sha256")==execution_dependencies()
        and release.get("application_confirmed") is True
        and isinstance(release.get("authorization_reference"),str) and bool(release["authorization_reference"].strip()))
    if not required:
        raise ValueError("Budget/application/executor release is missing, unconfirmed or mismatched")
    application=json.loads((bundle/"application_requirements.json").read_text())
    if application.get("status")!="confirmed" or application_issues(application):
        raise ValueError("Application criteria are pending/proposed, not confirmed")
    return release


def claim_release(release_path, output, claim_directory=None):
    """Consume the whole budget once; a crash/interruption does not permit reuse."""
    directory=claim_directory or release_path.parent
    directory.mkdir(parents=True,exist_ok=True)
    marker=directory/("budget_"+sha(release_path)+".consumed.json")
    with marker.open("x") as stream:
        stream.write(json.dumps(dict(release_sha256=sha(release_path),output=str(output),
            maximum_attempts=16,no_resume=True,no_reuse=True),indent=2)+"\n")
        stream.flush();os.fsync(stream.fileno())
    return marker


def classify(result):
    """Quality failure and sensor-integrity failure are different outcomes."""
    for key in ("setup_pass","provenance_pass","measurement_integrity_pass","cleanup_confirmed"):
        if result.get(key) is not True:
            return "hard_stop_"+key
    if result.get("runner_exit") != 0 or result.get("hard_stop_reason"):
        return result.get("hard_stop_reason") or "hard_stop_child_exit"
    outcome=result.get("physical_success")
    if outcome is None:
        return "hard_stop_native_outcome_unavailable"
    if type(outcome) is not bool or (outcome is True and result.get("termination")!="success"):
        return "hard_stop_inconsistent_native_outcome"
    if outcome is False and result.get("termination") not in ORDINARY_FAILURES:
        return "hard_stop_physical_or_controller_fault"
    if result.get("physical_state_valid") is not True:
        return "hard_stop_invalid_physical_state"
    # Censored quality in a normal failed task remains unavailable, not a new
    # sensor fault or fabricated zero. A successful traversal needs its reports.
    if outcome is True and result.get("quality_available") is not True:
        return "hard_stop_missing_successful_traversal_reporting"
    if outcome is True and result.get("stop_pass") is None:
        return "hard_stop_missing_stop_measurement"
    return None


def initialize(root, protocol):
    validate_schedule(protocol["schedule"])
    root.mkdir(parents=True,exist_ok=False)  # no overwrite/resume/retry
    rows=[dict(**job,status="not_attempted",launch_requested=False,physical_success=None,
        termination=None,stop_pass=None,result=None,error=None) for job in protocol["schedule"]]
    atomic_json(root/"protocol_snapshot.json",protocol)
    atomic_json(root/"ledger.json",dict(maximum_attempts=16,slots=rows))
    return rows


def summarize(rows, stop):
    attempted=[r for r in rows if r["status"]!="not_attempted"]
    return dict(status=stop or "sixteen_attempts_collected_unscored",maximum_attempts=16,
        attempted=len(attempted),launch_requests=sum(r["launch_requested"] for r in rows),
        unattempted=[r["attempt"] for r in rows if r["status"]=="not_attempted"],
        physical_successes=sum(r["physical_success"] is True for r in attempted),
        physical_failures=sum(r["physical_success"] is False for r in attempted),
        native_outcomes_unavailable=sum(r["physical_success"] is None for r in attempted),
        stop_failures=sum(r["stop_pass"] is False for r in attempted),
        all_physical_arrivals_and_stops=len(attempted)==16 and all(r["physical_success"] is True and r["stop_pass"] is True for r in attempted),
        retries=0,replacements=0,automatic_promotion=False,H2_decision="not_assessed",
        predictor_started=False,PPO_started=False,optuna_started=False,
        note="Collection status only. All assigned slots, task failures and null/censored metrics are retained. No success-only decision or automatic budget extension.")


def run_attempts(protocol, root, adapter, verify, execution_metadata=None):
    """Serial orchestration; adapter is injectable for offline fault tests."""
    rows=initialize(root,protocol);stop=None
    if execution_metadata is not None:
        atomic_json(root/"authorization_snapshot.json",execution_metadata)
    try:
        for row in rows:
            row["status"]="starting"
            atomic_json(root/"ledger.json",dict(maximum_attempts=16,slots=rows))
            append_event(root,dict(event="attempt_committed_before_launch",attempt=row["attempt"],seed=row["seed"],profile=row["profile"]))
            try:
                verify()
                row["launch_requested"]=True
                atomic_json(root/"ledger.json",dict(maximum_attempts=16,slots=rows))
                result=adapter(deepcopy({k:row[k] for k in protocol["schedule"][0]}),root/f"attempt_{row['attempt']:02d}")
                row["result"]=result  # preserve even a foreign/malformed result for diagnosis
                if (result.get("seed"),result.get("profile")) != (row["seed"],row["profile"]):
                    raise ValueError("Child result identity does not match assigned slot")
                row.update(result=result,physical_success=result.get("physical_success"),
                    termination=result.get("termination"),stop_pass=result.get("stop_pass"),status="collected")
                stop=classify(result)
                verify()  # drift after a run stops later attempts; preserve outcome
            except KeyboardInterrupt:
                row.update(status="interrupted_no_retry",error="KeyboardInterrupt")
                stop="interrupted_no_retry"
            except Exception as error:
                row.update(status="error_no_retry",error=f"{type(error).__name__}: {error}")
                stop="executor_or_contract_error_no_retry"
            if stop and row["status"]=="collected":
                row["status"]="hard_stopped"
            atomic_json(root/"ledger.json",dict(maximum_attempts=16,slots=rows))
            append_event(root,dict(event="attempt_finalized",attempt=row["attempt"],status=row["status"],stop_reason=stop))
            if stop:
                break
    finally:
        summary=summarize(rows,stop)
        atomic_json(root/"ledger.json",dict(maximum_attempts=16,slots=rows))
        atomic_json(root/"summary.json",summary)
    return summary


def child_command(bundle, job, stage):
    return [sys.executable,str(ROOT/"src/nino_rl/scripts/run_clear_floor_repeat.py"),
        "--variant","cable_box_capsule","--config",str(bundle/f"inputs/{job['profile']}.yaml"),
        "--world",str(stage/"scenario.sdf"),"--profiles",job["profile"],
        "--seeds",str(job["seed"]),"--output",str(stage/"screen")]


def stop_child(process):
    if process.poll() is None:
        # The child runner owns its evaluator/Gazebo sessions and handles SIGINT
        # in finally blocks. Never kill unrelated simulator processes.
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=100)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=10)
            return False  # nested cleanup not confirmed; hard stop, no next launch
    return process.returncode==0


class LiveAdapter:
    def __init__(self,bundle,domain,popen=None,collector=None):
        self.bundle=bundle;self.domain=domain;self.popen=popen or subprocess.Popen
        self.collector=collector or collect_attempt

    def __call__(self,job,attempt):
        stage=attempt/"confirmation/height";stage.mkdir(parents=True,exist_ok=False)
        for name in ("scenario.sdf","scenario.json"):
            shutil.copy2(self.bundle/"inputs"/name,stage/name)
        atomic_json(attempt/"protocol_before_results.json",dict(scenarios=[dict(id="height",x_m=3.1,angle_deg=8.,seeds=[job["seed"]])]))
        command=child_command(self.bundle,job,stage)
        environment=os.environ.copy()
        environment.update(ROS_DOMAIN_ID=str(self.domain),NINO_ROS_DOMAIN_ID=str(self.domain),
            ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",GZ_PARTITION=f"nino_h2_replication_{self.domain}")
        atomic_json(attempt/"launch_plan.json",dict(command=command,cold_start=True,maximum_child_episodes=1,
            domain=self.domain,partition=environment["GZ_PARTITION"],retry_allowed=False))
        process=None;cleanup=False;interrupted=False;error=None
        try:
            with (attempt/"run.log").open("w") as stream:
                process=self.popen(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                process.wait(timeout=1500)
        except KeyboardInterrupt:
            interrupted=True;error="KeyboardInterrupt"
        except Exception as exc:
            error=f"{type(exc).__name__}: {exc}"
        finally:
            if process is not None:
                cleanup=stop_child(process)
        result=self.collector(self.bundle,job,attempt)
        result.update(runner_exit=process.returncode if process else None,cleanup_confirmed=cleanup)
        if interrupted:
            result["hard_stop_reason"]="interrupted_no_retry"
        elif error:
            result["hard_stop_reason"]="child_process_failure_no_retry"
        result["child_error"]=error
        atomic_json(attempt/"result.json",result)
        return result


def one(paths, description):
    paths=list(paths)
    if len(paths)!=1:
        raise ValueError(f"Expected exactly one {description}; found {len(paths)}")
    return paths[0]


def collect_attempt(bundle,job,attempt):
    """Read only this new child output; never fill absent arms or launch analysis."""
    sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
    from summarize_contact_oracle_h2 import native_status
    case=attempt/"confirmation/height/screen"/f"seed_{job['seed']}_{job['profile']}"
    result=dict(seed=job["seed"],profile=job["profile"],case=str(case),physical_success=None,
        termination=None,stop_pass=None,setup_pass=False,provenance_pass=False,
        measurement_integrity_pass=False,physical_state_valid=False,quality_available=False,
        quality=None,native_outcome=None)
    try:
        # Preserve the native failure even if subsequent provenance/analysis fails.
        status=native_status(case)
        result.update(physical_success=status["physical_success"],termination=status["termination"])
        screen=json.loads((case.parent/"summary.json").read_text())
        if len(screen["results"])!=1 or screen.get("seeds")!=[job["seed"]] or screen.get("profiles")!=[job["profile"]]:
            raise ValueError("Child must contain exactly one assigned seed/arm, no fallback rows")
        child=screen["results"][0]
        if (child["seed"],child["profile"])!=(job["seed"],job["profile"]):
            raise ValueError("Child identity mismatch")
        result["child_status"]=child
        gate=json.loads(one(case.glob("evaluation/*/reset_standstill_001.json"),"reset gate").read_text())
        result["reset_gate"]=gate
        result["setup_pass"]=gate.get("passed") is True and child.get("evaluation_returncode")==0 and not child.get("error") and not screen.get("interrupted")
        logger=one(case.glob("contact/*/metadata.json"),"logger metadata").parent
        evaluation=one(case.glob("evaluation/*/summary.json"),"evaluation summary").parent
        result["evaluation"]=str(evaluation);result["logger"]=str(logger)
        metadata=json.loads((logger/"metadata.json").read_text())
        protocol=json.loads((bundle/"protocol.json").read_text())
        expected=yaml.safe_load((bundle/f"inputs/{job['profile']}.yaml").read_text())
        resolved=json.loads((logger/"resolved_config.json").read_text())
        from nino_rl.evaluation import prepare_evaluation_config
        evaluated=yaml.safe_load((evaluation/"config.yaml").read_text())
        expected_evaluation=prepare_evaluation_config(expected,route="E1",baseline=True,control_trace=True)
        source_paths={"governor_core_sha256":ROOT/"src/nino_control/nino_control/governor_core.py",
            "effort_drive_sha256":ROOT/"src/nino_control/nino_control/effort_drive.py",
            "control_timing_sha256":ROOT/"src/nino_control/nino_control/control_timing.py"}
        checks=dict(world=metadata.get("world_sha256")==sha(bundle/"inputs/scenario.sdf"),
            robot=metadata.get("robot_description_sha256")==protocol["fixed"]["robot_expected_sha256"],
            actual_robot=sha(logger/"robot_description.urdf")==protocol["fixed"]["robot_expected_sha256"],
            logger_closed=metadata.get("complete") is True,robot_validated=metadata.get("robot_description_validated") is True,
            no_oracle=metadata.get("governor_has_no_oracle_input") is True,
            config=resolved==expected,case_config=yaml.safe_load((case/"config.yaml").read_text())==expected,
            evaluated_config=evaluated==expected_evaluation,
            **{key:metadata.get(key)==sha(path) for key,path in source_paths.items()})
        result["provenance_checks"]=checks;result["provenance_pass"]=all(checks.values())
        controls=list(csv.DictReader(one(evaluation.glob("episode-*/control_trace.csv"),"control trace").open()))
        native=list(csv.DictReader((evaluation/"episodes.csv").open()))
        if len(native)!=1 or not controls:
            raise ValueError("Missing single native outcome/control trace")
        result["native_outcome"]=native[0]  # native values, unmodified, including failures
        if int(native[0]["seed"])!=job["seed"]:
            result["provenance_pass"]=False
            raise ValueError("Native episode seed does not match assigned slot")
        from run_frozen_governor_confirmation import timestamps, analyze_batch
        from nino_rl.slip_reporting import replay_native_trace, integrate, synchronized_series
        from audit_governor_phase_slip import load
        from audit_gt_timestamp_slip import gt_timestamp_series
        data=load(case,dict(seed=job["seed"],profile=job["profile"],evaluation=str(evaluation),logger=str(logger)))
        gt=gt_timestamp_series(data)
        whole=integrate(gt,data["start"],data["end"])
        replay=replay_native_trace(controls)
        stamp_check=timestamps(controls)
        native_match=replay.get("available") and math.isclose(replay["rms"],float(native[0]["rms_wheel_slip"]),rel_tol=1e-10,abs_tol=1e-10)
        ages=[float(c[k]) for c in controls for k in ("governor_feedback_age_s","drive_interval_latest_age_s")]
        result["integrity"]=dict(native_replay=replay,native_match=bool(native_match),timestamps=stamp_check,
            whole_GT=whole,ages_s=[min(ages),max(ages)])
        result["measurement_integrity_pass"]=bool(status["complete"] and native_match and stamp_check["passed"] and whole["available"]
            and all(math.isfinite(a) and -1e-9<=a<=.100000001 for a in ages)
            and all(not c["governor_fault"] and int(c["drive_interval_sample_count"])>=1 for c in controls))
        result["physical_state_valid"]=result["termination"] in ORDINARY_FAILURES|{"success"}
        stop=child.get("audit",{}).get("post_arrival_stop",{})
        result["stop_pass"]=stop.get("settled") if result["physical_success"] else None
        # Existing read-only analyzer is called only after one-result summary
        # validation; it cannot invent an absent opposite arm for this attempt.
        analyze_batch(attempt)
        rows=json.loads((attempt/"confirmation_episodes.json").read_text())
        if len(rows)!=1:
            raise ValueError("Analysis must retain exactly the assigned attempt")
        row=dict(rows[0],arm=job["profile"])
        result["quality"]=dict(existing_reports=row,postcontact=dict(available=False,
            reason="missing_or_censored_contact_window_not_zero"))
        if row.get("available") and row.get("clearance_s") is not None and row.get("first_contact_s") is not None:
            from prepare_governor_contact_sequence import analyze as sequence_analysis,signal_stats
            from run_governor_frozen_repeats import enrich
            from nino_control.governor_core import quaternion_rpy,vertical_acceleration
            enrich(row);row["sequence"]=sequence_analysis(row)
            tc=row["first_contact_s"];a,b=tc+.05,tc+3.
            imu=[]
            for line in (logger/"samples.jsonl").open():
                packet=json.loads(line)
                if packet["topic"]!="/imu/data":continue
                d=packet["data"];s=d["header"]["stamp"];t=s["sec"]+s["nanosec"]*1e-9
                r,p,_=quaternion_rpy(tuple(d["orientation"][k] for k in ("x","y","z","w")))
                imu.append((t,vertical_acceleration(tuple(d["linear_acceleration"][k] for k in ("x","y","z")),r,p,expected["policy_v2"]["imu_includes_gravity"])))
            imu.sort()
            post=dict(available=b<=data["end"],start_s=a,end_s=b)
            if post["available"]:
                post.update(GT_slip=integrate(gt,a,b),vertical=signal_stats(imu,a,b),
                    grid20ms=integrate(synchronized_series(data),a,b),
                    shifted10ms=integrate(synchronized_series(data,offset=.01),a,b))
                post["available"]=all(post[k]["available"] for k in ("GT_slip","vertical","grid20ms","shifted10ms"))
            else:
                post["reason"]="fixed_postcontact_window_censored_not_zero"
            result["quality"]=dict(existing_reports=row,postcontact=post)
            result["quality_available"]=bool(row["reporting_pass"] and row["sequence"].get("available") and post["available"])
        atomic_json(attempt/"collection.json",result)
    except Exception as error:
        result["collection_error"]=f"{type(error).__name__}: {error}"
        result["measurement_integrity_pass"]=False
        atomic_json(attempt/"collection.json",result)
    return result


def offline_plan(bundle, output):
    validation=validate_bundle(bundle)
    protocol=json.loads((bundle/"protocol.json").read_text())
    rows=initialize(output,protocol)
    for row in rows:
        job={k:row[k] for k in protocol["schedule"][0]}
        stage=output/f"attempt_{row['attempt']:02d}/confirmation/height"
        row["planned_command"]=child_command(bundle,job,stage)
    atomic_json(output/"ledger.json",dict(maximum_attempts=16,slots=rows))
    summary=summarize(rows,"offline_plan_only_no_processes")
    summary.update(validation=validation,simulation_episodes=0,processes_started=0,release_consumed=False)
    atomic_json(output/"summary.json",summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--execute",action="store_true",help="Future live mode: sealed application and separate budget release required")
    parser.add_argument("--release",type=Path)
    parser.add_argument("--domain",type=int,default=108)
    args=parser.parse_args();bundle=args.protocol.resolve();output=args.output.resolve()
    if not args.execute:
        print(json.dumps(offline_plan(bundle,output),indent=2));return
    if not 0<=args.domain<=232:
        parser.error("ROS domain must be0..232")
    # No release file is generated by this executor. Pending/proposed criteria
    # fail here before directory creation, lock acquisition or Popen.
    release=require_release(bundle,args.release)
    protocol=json.loads((bundle/"protocol.json").read_text())
    def verify():
        require_release(bundle,args.release)
        if json.loads(args.release.read_text())!=release:
            raise ValueError("Budget release changed during batch")
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    with open(f"/tmp/nino_h2_executor_domain_{args.domain}.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if output.exists():
            raise FileExistsError("Output already exists; no resume or replacement budget")
        verify()
        claim=claim_release(args.release,output,bundle/"budget_claims")
        metadata=dict(release=release,application=json.loads((bundle/"application_requirements.json").read_text()),
            release_claim=str(claim),domain=args.domain,partition=f"nino_h2_replication_{args.domain}")
        summary=run_attempts(protocol,output,LiveAdapter(bundle,args.domain),verify,metadata)
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
