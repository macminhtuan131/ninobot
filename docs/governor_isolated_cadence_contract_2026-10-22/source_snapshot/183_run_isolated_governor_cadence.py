#!/usr/bin/env python3
"""New two-logger executor. Offline by default; old budget releases are rejected."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys

from prepare_isolated_cadence_contract import ROOT,validate,sha
from run_governor_h2_replication import LiveAdapter,child_command,collect_attempt,atomic_json
from run_governor_cadence_experiment import run_attempts,synthetic,cadence_trace_check


def command(bundle,job,stage):
    # Arm view provides fixed YAML; root protocol seals the common architecture.
    return child_command(bundle/"arm_views"/job["arm"],job,stage)+[
        "--acquisition-contract",str(bundle/"protocol.json"),
        "--acquisition-job",json.dumps({k:job[k] for k in (
            "attempt","seed","repeat","triad_id","position","arm","profile","cold_start")})]


def collect(bundle,job,attempt):
    case=attempt/"confirmation/height/screen"/f"seed_{job['seed']}_{job['profile']}"
    view=case/"measurement_view"
    # Always retain native outcome/failure, even if acquisition never completed.
    result=collect_attempt(bundle/"arm_views"/job["arm"],job,attempt,
                           measurement_logger=view if view.exists() else None)
    result["arm"]=job["arm"]
    try:
        from nino_rl.acquisition_contract import verify_view
        admission=verify_view(view)
        child=result.get("child_status",{})
        if (child.get("joint_gt_returncode")!=0 or not child.get("acquisition_readiness")
                or Path(child.get("measurement_logger",""))!=view):
            raise ValueError("Acquisition child exit/readiness/view binding is incomplete")
        if admission["protocol_sha256"]!=sha(bundle/"protocol.json"):
            raise ValueError("View belongs to another acquisition contract")
        cadence=cadence_trace_check(Path(result["evaluation"]),job["arm"])
        result["cadence_integrity"]=cadence
        result["measurement_integrity_pass"] &= cadence["valid"]
        # All ordinary failures remain native outcomes; successful runs require
        # all original per-window reports/coverage, never only whole-route data.
        if result.get("physical_success"):
            result["measurement_integrity_pass"] &= result.get("quality_available") is True
        verify_view(view)
    except (OSError,ValueError,KeyError,TypeError,StopIteration) as error:
        result["measurement_integrity_pass"]=False
        result["acquisition_error"]=f"{type(error).__name__}: {error}"
    atomic_json(attempt/"collection.json",result)
    return result


def require_release(bundle,path):
    checked=validate(bundle)
    if path is None:raise ValueError("New acquisition budget is not released")
    r=json.loads(Path(path).read_text())
    if not (r.get("contract")==checked["contract"] and r.get("protocol_sha256")==checked["protocol_sha256"]
            and r.get("executor_sha256")==sha(__file__)
            and r.get("execution_authorized") is True and r.get("budget_released") is True
            and type(r.get("maximum_attempts")) is int and r["maximum_attempts"]==12 and r.get("thresholds_applied") is False
            and isinstance(r.get("authorization_reference"),str) and r["authorization_reference"].strip()):
        raise ValueError("Fresh isolated-acquisition release required; old slots cannot be reused")
    return r


def execute(bundle,output,release,domain):
    binding=require_release(bundle,release);release_hash=sha(release)
    protocol=json.loads((bundle/"protocol.json").read_text())
    def verify():
        if require_release(bundle,release)!=binding or sha(release)!=release_hash:
            raise ValueError("Acquisition execution release drift")
    adapter=LiveAdapter(bundle,domain,collector=lambda b,j,a:collect(b,j,a),
        command_factory=command,environment_overrides={"PYTHONPATH":os.pathsep.join([
            str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control"),os.environ.get("PYTHONPATH","")])})
    def interrupted(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    with open(f"/tmp/nino_h2_executor_domain_{domain}.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if output.exists():raise FileExistsError("No resume/retry/overwrite")
        claims=ROOT/"rl_runs/.governor_isolated_acquisition_budget_claims";claims.mkdir(exist_ok=True)
        claim=claims/(binding["protocol_sha256"]+".consumed.json")
        with claim.open("x") as stream:
            json.dump(dict(output=str(output),release_sha256=release_hash,no_reuse=True),stream)
            stream.flush();os.fsync(stream.fileno())
        return run_attempts(protocol,output,adapter,verify,dry_run=False,authorization=dict(release=binding))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--release",type=Path)
    parser.add_argument("--domain",type=int,default=132)
    args=parser.parse_args();validate(args.bundle)
    if args.release:answer=execute(args.bundle,args.output,args.release,args.domain)
    else:
        answer=run_attempts(json.loads((args.bundle/"protocol.json").read_text()),args.output,
            synthetic,lambda:validate(args.bundle),dry_run=True)
    print(json.dumps(answer,indent=2))
