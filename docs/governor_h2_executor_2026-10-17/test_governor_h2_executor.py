"""Offline only: fake adapter/processes; accidental subprocess launch is forbidden."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import signal
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import run_governor_h2_replication as executor
from prepare_governor_h2_protocol import ROOT,make_schedule,sha,write


@pytest.fixture(autouse=True)
def no_real_processes(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError("Offline tests must not start subprocesses")
    monkeypatch.setattr(executor.subprocess,"Popen",forbidden)
    monkeypatch.setattr(executor.subprocess,"run",forbidden)


@pytest.fixture
def protocol():
    return dict(schedule=make_schedule())


@pytest.fixture
def bundle(tmp_path):
    path=tmp_path/"bundle"
    shutil.copytree(ROOT/"docs/governor_h2_replication_protocol_2026-10-17",path)
    return path


def good(job,**updates):
    return dict(seed=job["seed"],profile=job["profile"],physical_success=True,termination="success",
        stop_pass=True,setup_pass=True,provenance_pass=True,measurement_integrity_pass=True,
        physical_state_valid=True,quality_available=True,cleanup_confirmed=True,runner_exit=0,**updates)


def changed(job,**updates):
    result=good(job);result.update(updates);return result


def test_exact_16_slots_in_locked_order_committed_before_each_fake_cold_start(tmp_path,protocol):
    root=tmp_path/"run";calls=[]
    def fake(job,attempt):
        rows=json.loads((root/"ledger.json").read_text())["slots"]
        assert len(rows)==16 and rows[job["attempt"]-1]["status"]=="starting"
        assert rows[job["attempt"]-1]["launch_requested"] is True
        assert all(r["status"]=="not_attempted" for r in rows[job["attempt"]:])
        assert job["cold_start"] is True and not attempt.exists()
        attempt.mkdir();(attempt/"fake_closed.txt").write_text("closed before return")
        calls.append(job);return good(job)
    result=executor.run_attempts(protocol,root,fake,lambda:None)
    assert calls==protocol["schedule"] and result["attempted"]==16
    assert result["retries"]==result["replacements"]==0
    assert result["all_physical_arrivals_and_stops"]
    assert not result["automatic_promotion"] and result["H2_decision"]=="not_assessed"
    assert len((root/"events.jsonl").read_text().splitlines())==32


@pytest.mark.parametrize("reason",["timeout","stall","off_path","wrong_direction","goal_missed"])
def test_ordinary_failure_is_retained_and_does_not_replace_or_truncate_remaining_slots(tmp_path,protocol,reason):
    calls=[]
    def fake(job,attempt):
        calls.append(job)
        return changed(job,physical_success=False,termination=reason,stop_pass=None,quality_available=False,quality=None) if job["attempt"]==1 else good(job)
    result=executor.run_attempts(protocol,tmp_path/"run",fake,lambda:None)
    assert len(calls)==16 and result["physical_failures"]==1
    assert not result["all_physical_arrivals_and_stops"]
    rows=json.loads((tmp_path/"run/ledger.json").read_text())["slots"]
    assert rows[0]["physical_success"] is False and rows[0]["result"]["quality"] is None
    assert rows[0]["termination"]==reason


@pytest.mark.parametrize("field",["setup_pass","provenance_pass","measurement_integrity_pass","cleanup_confirmed","physical_state_valid"])
def test_integrity_failure_stops_without_retry_and_keeps_remaining_slots(tmp_path,protocol,field):
    calls=[]
    def fake(job,attempt):
        calls.append(job);return changed(job,**{field:False}) if job["attempt"]==2 else good(job)
    result=executor.run_attempts(protocol,tmp_path/"run",fake,lambda:None)
    assert len(calls)==2 and result["attempted"]==2
    assert result["unattempted"]==list(range(3,17)) and result["retries"]==0


def test_missing_native_outcome_is_not_converted_into_arrival_failure(tmp_path,protocol):
    result=executor.run_attempts(protocol,tmp_path/"run",lambda job,p:changed(job,physical_success=None,termination=None),lambda:None)
    assert result["attempted"]==1 and result["native_outcomes_unavailable"]==1
    assert result["physical_failures"]==0 and result["status"]=="hard_stop_native_outcome_unavailable"


def test_rollover_stops_and_the_failed_arrival_stays_counted(tmp_path,protocol):
    result=executor.run_attempts(protocol,tmp_path/"run",lambda job,p:changed(job,physical_success=False,termination="rollover"),lambda:None)
    assert result["attempted"]==result["physical_failures"]==1
    assert result["status"]=="hard_stop_physical_or_controller_fault"


def test_stopping_failure_is_retained_without_rewriting_successful_arrival(tmp_path,protocol):
    result=executor.run_attempts(protocol,tmp_path/"run",lambda job,p:changed(job,stop_pass=False),lambda:None)
    assert result["physical_successes"]==16 and result["physical_failures"]==0
    assert result["stop_failures"]==16 and not result["all_physical_arrivals_and_stops"]


@pytest.mark.parametrize("error",[RuntimeError("adapter fault"),KeyboardInterrupt()])
def test_interruption_or_adapter_error_finalizes_ledger_without_a_retry(tmp_path,protocol,error):
    def fake(job,attempt):raise error
    result=executor.run_attempts(protocol,tmp_path/"run",fake,lambda:None)
    rows=json.loads((tmp_path/"run/ledger.json").read_text())["slots"]
    assert result["attempted"]==1 and len(result["unattempted"])==15
    assert rows[0]["status"] in ("error_no_retry","interrupted_no_retry")
    assert rows[0]["physical_success"] is None


def test_output_reuse_and_prelaunch_drift_cannot_start_another_process(tmp_path,protocol):
    root=tmp_path/"existing";root.mkdir()
    def forbidden(*args):raise AssertionError("Should not launch")
    with pytest.raises(FileExistsError):
        executor.run_attempts(protocol,root,forbidden,lambda:None)
    def drift():raise ValueError("source drift")
    result=executor.run_attempts(protocol,tmp_path/"drift",forbidden,drift)
    assert result["attempted"]==1 and result["launch_requests"]==0


def test_postrun_drift_keeps_observed_native_failure(tmp_path,protocol):
    count=0
    def verify():
        nonlocal count
        count+=1
        if count==2:raise ValueError("source drift after run")
    result=executor.run_attempts(protocol,tmp_path/"run",lambda job,p:changed(job,physical_success=False,termination="timeout"),verify)
    assert result["attempted"]==result["physical_failures"]==1


def test_default_cli_only_creates_plan_and_starts_zero_processes(tmp_path,bundle,monkeypatch):
    output=tmp_path/"plan"
    monkeypatch.setattr(sys,"argv",["executor","--protocol",str(bundle),"--output",str(output)])
    executor.main()
    summary=json.loads((output/"summary.json").read_text())
    assert summary["processes_started"]==summary["attempted"]==0
    assert len(summary["unattempted"])==16
    assert not (output/"attempt_01").exists()


def test_execute_with_pending_or_proposed_criteria_fails_before_output_creation(tmp_path,bundle,monkeypatch):
    output=tmp_path/"forbidden_run"
    monkeypatch.setattr(sys,"argv",["executor","--protocol",str(bundle),"--output",str(output),"--execute"])
    with pytest.raises(ValueError,match="No budget release"):
        executor.main()
    assert not output.exists()
    with pytest.raises(ValueError):executor.require_release(bundle,None)


def accepted_release(bundle,tmp_path):
    write(bundle/"application_requirements.json",dict(status="confirmed",primary_metric="postcontact_GT_slip_square_per_m",
        minimum_relative_improvement=.1,maximum_added_route_seconds=.5,requirement_origin="user_accepted_engineering_assumption"))
    release=tmp_path/"test_only_release.json"
    value=dict(budget_released=True,execution_authorized=True,maximum_attempts=16,
        protocol_sha256=sha(bundle/"protocol.json"),executor_sha256=sha(Path(executor.__file__)),
        execution_dependency_sha256=executor.execution_dependencies(),
        application_sha256=sha(bundle/"application_requirements.json"),application_confirmed=True,
        authorization_reference="SYNTHETIC OFFLINE TEST ONLY")
    write(release,value);return release,value


def test_release_hash_application_and_single_use_budget_are_enforced(tmp_path,bundle):
    release,value=accepted_release(bundle,tmp_path)
    assert executor.require_release(bundle,release)==value
    executor.claim_release(release,tmp_path/"synthetic_output")
    with pytest.raises(FileExistsError):executor.claim_release(release,tmp_path/"another_output")
    copy=tmp_path/"copied_release.json";shutil.copy2(release,copy)
    with pytest.raises(FileExistsError):executor.claim_release(copy,tmp_path/"copied_budget_output")
    write(bundle/"application_requirements.json",dict(status="proposed"))
    with pytest.raises(ValueError):executor.require_release(bundle,release)


@pytest.mark.parametrize("key,value",[("maximum_attempts",17),("maximum_attempts",16.),("application_confirmed",False),("executor_sha256","drift"),("authorization_reference","")])
def test_invalid_release_never_authorizes_a_budget(tmp_path,bundle,key,value):
    path,release=accepted_release(bundle,tmp_path);release[key]=value;write(path,release)
    with pytest.raises(ValueError):executor.require_release(bundle,path)


class FakeProcess:
    def __init__(self):self.returncode=None;self.signals=[]
    def wait(self,timeout):self.returncode=0;return 0
    def poll(self):return self.returncode
    def send_signal(self,signum):self.signals.append(signum)


def test_one_child_per_call_has_one_seed_arm_and_owned_partition(tmp_path,bundle):
    calls=[]
    def popen(command,**kwargs):calls.append((command,kwargs));return FakeProcess()
    job=make_schedule()[0]
    adapter=executor.LiveAdapter(bundle,108,popen=popen,collector=lambda b,j,p:good(j))
    result=adapter(job,tmp_path/"attempt")
    assert len(calls)==1 and result["cleanup_confirmed"]
    command,kw=calls[0]
    assert command[command.index("--profiles")+1]==job["profile"]
    assert command[command.index("--seeds")+1]==str(job["seed"])
    assert "--shuffle-order" not in command and "--oracle-contact" not in command
    assert kw["start_new_session"] and kw["env"]["GZ_PARTITION"]=="nino_h2_replication_108"


def test_interrupted_live_adapter_cleans_owned_child_and_preserves_collected_outcome(tmp_path,bundle):
    class Interrupted(FakeProcess):
        def wait(self,timeout):
            if not self.signals:raise KeyboardInterrupt
            self.returncode=130;return 130
    process=Interrupted();job=make_schedule()[0]
    adapter=executor.LiveAdapter(bundle,108,popen=lambda *a,**k:process,collector=lambda b,j,p:changed(j,physical_success=False,termination="timeout"))
    result=adapter(job,tmp_path/"attempt")
    assert process.signals==[signal.SIGINT]
    assert result["physical_success"] is False and result["hard_stop_reason"]=="interrupted_no_retry"


def test_collector_keeps_native_failure_when_measurement_artifacts_are_missing(tmp_path,bundle):
    job=make_schedule()[0];attempt=tmp_path/"attempt"
    case=attempt/"confirmation/height/screen"/f"seed_{job['seed']}_{job['profile']}"
    evaluation=case/"evaluation/synthetic";evaluation.mkdir(parents=True)
    write(evaluation/"summary.json",dict(complete=True))
    (evaluation/"episodes.csv").write_text("success,termination,seed\nFalse,timeout,"+str(job["seed"])+"\n")
    result=executor.collect_attempt(bundle,job,attempt)
    assert result["physical_success"] is False and result["termination"]=="timeout"
    assert result["measurement_integrity_pass"] is False and result["quality"] is None


@pytest.mark.parametrize("updates",[dict(physical_success=0),dict(physical_success=True,termination="timeout"),dict(stop_pass=None)])
def test_invalid_native_types_or_missing_stop_measurements_fail_closed(tmp_path,protocol,updates):
    result=executor.run_attempts(protocol,tmp_path/"run",lambda job,p:changed(job,**updates),lambda:None)
    assert result["attempted"]==1 and result["unattempted"]==list(range(2,17))


@pytest.mark.parametrize("success",[True,False])
def test_collector_distinguishes_censored_failure_from_integrity_and_collects_fixed_window(tmp_path,bundle,monkeypatch,success):
    """Synthetic new artifacts only; no historical trace audit or simulation."""
    import numpy as np
    import yaml
    sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
    from nino_rl.evaluation import prepare_evaluation_config
    import nino_rl.slip_reporting as slip
    import run_frozen_governor_confirmation as confirm
    import audit_governor_phase_slip as phase
    import run_governor_frozen_repeats as repeats
    import prepare_governor_contact_sequence as sequence
    job=make_schedule()[0];attempt=tmp_path/"attempt"
    case=attempt/"confirmation/height/screen"/f"seed_{job['seed']}_{job['profile']}"
    evaluation=case/"evaluation/synthetic";logger=case/"contact/synthetic"
    evaluation.mkdir(parents=True);logger.mkdir(parents=True);(evaluation/"episode-001").mkdir()
    base=yaml.safe_load((bundle/f"inputs/{job['profile']}.yaml").read_text())
    (case/"config.yaml").write_text(yaml.safe_dump(base))
    (evaluation/"config.yaml").write_text(yaml.safe_dump(prepare_evaluation_config(base,route="E1",baseline=True,control_trace=True)))
    write(evaluation/"summary.json",dict(complete=True))
    (evaluation/"episodes.csv").write_text("success,termination,seed,rms_wheel_slip\n"+f"{success},{'success' if success else 'timeout'},{job['seed']},0.0\n")
    write(evaluation/"reset_standstill_001.json",dict(passed=True))
    write(logger/"resolved_config.json",base)
    shutil.copy2(bundle/"inputs/reference_robot.urdf",logger/"robot_description.urdf")
    write(logger/"metadata.json",dict(complete=True,world_sha256=sha(bundle/"inputs/scenario.sdf"),
        robot_description_sha256=sha(bundle/"inputs/reference_robot.urdf"),robot_description_validated=True,
        governor_has_no_oracle_input=True,governor_core_sha256=sha(ROOT/"src/nino_control/nino_control/governor_core.py"),
        effort_drive_sha256=sha(ROOT/"src/nino_control/nino_control/effort_drive.py"),
        control_timing_sha256=sha(ROOT/"src/nino_control/nino_control/control_timing.py")))
    write(case.parent/"summary.json",dict(seeds=[job["seed"]],profiles=[job["profile"]],interrupted=False,
        results=[dict(seed=job["seed"],profile=job["profile"],evaluation_returncode=0,
            audit=dict(post_arrival_stop=dict(settled=True)))]))
    cp=evaluation/"episode-001/control_trace.csv"
    cp.write_text("governor_feedback_age_s,drive_interval_latest_age_s,drive_interval_sample_count,governor_fault\n0.0,0.0,4,\n")
    times=np.arange(0.,5.001,.02)
    ground=np.column_stack([times,np.full(len(times),.4),np.zeros(len(times)),times*.4,np.zeros(len(times))])
    joint_times=np.arange(0.,5.001,.002)
    joints=np.column_stack([joint_times,np.full(len(joint_times),6.4),np.full(len(joint_times),6.4)])
    monkeypatch.setattr(phase,"load",lambda *a,**k:dict(start=0.,end=5.,ground=ground,joints=joints))
    monkeypatch.setattr(slip,"replay_native_trace",lambda rows:dict(available=True,rms=0.))
    monkeypatch.setattr(confirm,"timestamps",lambda rows:dict(passed=True))
    def analyzed(root):
        write(root/"confirmation_episodes.json",[dict(available=True,case=str(case),seed=job["seed"],profile=job["profile"],
            first_contact_s=1.,clearance_s=2. if success else None)])
    monkeypatch.setattr(confirm,"analyze_batch",analyzed)
    monkeypatch.setattr(repeats,"enrich",lambda row:row.update(reporting_pass=True))
    monkeypatch.setattr(sequence,"analyze",lambda row:dict(available=True))
    with (logger/"samples.jsonl").open("w") as stream:
        for t in times:
            ns=round(t*1e9)
            packet=dict(topic="/imu/data",data=dict(header=dict(stamp=dict(sec=ns//10**9,nanosec=ns%10**9)),
                orientation=dict(x=0.,y=0.,z=0.,w=1.),linear_acceleration=dict(x=0.,y=0.,z=9.80665)))
            stream.write(json.dumps(packet)+"\n")
    result=executor.collect_attempt(bundle,job,attempt)
    assert "collection_error" not in result
    assert result["setup_pass"] and result["provenance_pass"] and result["measurement_integrity_pass"]
    assert result["physical_success"] is success
    assert result["quality_available"] is success
    if success:
        assert result["quality"]["postcontact"]["start_s"]==1.05
        assert result["quality"]["postcontact"]["end_s"]==4.
    else:
        assert result["quality"]["postcontact"]["available"] is False
