"""New acquisition lifecycle, derived authority and original metric gates, offline."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl/scripts"),str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control")]
from nino_rl import acquisition_contract as ac
from nino_rl.acquisition_frames import FrameWriter,atomic_json
from nino_rl.observer_health import ObserverHealth
from nino_rl.slip_reporting import integrate
from prepare_governor_cadence_experiment import schedule,ARMS
from run_isolated_governor_cadence import command,require_release


def session(tmp_path):
    paths=[]
    for name in ("protocol.json","config.yaml","world.sdf"):
        path=tmp_path/name;path.write_text("{}\n");paths.append(path)
    return ac.create_session(tmp_path/"session",*paths,schedule()[0])


def ready(path,role,output):
    life=ac.Lifecycle(path,role,output)
    life.status["pid"]+=1 if role=="joint_gt" else 0
    for topic in ac.SENSOR_TOPICS:life.sample(topic,1_000_000_000)
    life.publish(1_000_000_000)
    return life


@pytest.mark.parametrize("fault",["foreign_session","source_drift","stale_status","stale_sensor",
                                  "future_sensor","missing_stream","error","closed"])
def test_readiness_rejects_missing_stale_or_wrong_process_binding(tmp_path,fault):
    path=session(tmp_path);s=ac.read_session(path)
    life=ready(path,"joint_gt",tmp_path/"capture");value=deepcopy(life.status)
    now=value["monotonic_ns"]
    if fault=="foreign_session":value["session_id"]="other"
    elif fault=="source_drift":value["source_sha256"]={}
    elif fault=="stale_status":now+=3_000_000_000
    elif fault=="stale_sensor":value["latest_source_ns"]["/joint_states"]-=200_000_000
    elif fault=="future_sensor":value["latest_source_ns"]["/joint_states"]+=20_000_000
    elif fault=="missing_stream":value["counts"]["/ground_truth/odom"]=0
    elif fault=="error":value["error"]="disk full"
    else:value["closed"]=True
    with pytest.raises(ValueError):ac.check_status(s,value,"joint_gt",now_mono_ns=now)


def test_both_readiness_and_exact_ack_required_no_world_steps(tmp_path):
    path=session(tmp_path)
    primary=ready(path,"primary",tmp_path/"primary")
    sensor=ready(path,"joint_gt",tmp_path/"capture")
    assert set(ac.wait_pair(path))=={"primary","joint_gt"}
    marker=dict(event="reset",run_id="r",attempt=1,seed=77600,time_s=1.)
    for life in (primary,sensor):life.marker(marker,1_000_000_000)
    assert ac.wait_pair(path,marker=marker)["joint_gt"]["marker"]==marker
    bad=deepcopy(marker);bad["run_id"]="wrong"
    with pytest.raises(ValueError):ac.check_status(ac.read_session(path),
        dict(sensor.status,marker=bad),"joint_gt",marker=marker,
        now_mono_ns=sensor.status["monotonic_ns"])
    with pytest.raises(RuntimeError):ac.wait_pair(path,alive=lambda:False)


def test_delayed_end_receipt_requires_fresh_live_heartbeat_without_world_steps(tmp_path,monkeypatch):
    path=session(tmp_path)
    primary=ready(path,"primary",tmp_path/"primary")
    sensor=ready(path,"joint_gt",tmp_path/"capture")
    marker=dict(event="end",run_id="r",attempt=1,time_s=1.)
    for life in (primary,sensor):life.marker(marker,1_000_000_000)
    receipt=json.loads((path.parent/"primary_end.json").read_text())
    delayed=receipt["monotonic_ns"]+3_000_000_000
    with pytest.raises(ValueError,match="Stale logger status"):
        ac.check_status(ac.read_session(path),receipt,"primary",marker=marker,now_mono_ns=delayed)
    monkeypatch.setattr(ac.time,"monotonic_ns",lambda:delayed)
    for life in (primary,sensor):life.publish(1_000_000_000)
    values=ac.wait_pair(path,marker=marker,pump=lambda:pytest.fail("No stepping or retry needed"))
    assert values["primary"]==receipt
    # Fresh receipt alone cannot replace a stale heartbeat.
    monkeypatch.setattr(ac.time,"monotonic_ns",lambda:delayed+3_000_000_000)
    with pytest.raises(ValueError,match="Stale/future live heartbeat"):
        ac.check_delivery(ac.read_session(path),primary.status,receipt,"primary",marker)


@pytest.mark.parametrize("fault",["future","closed","error","not_ready","pid","output",
    "session","source","foreign_marker","missing_live_marker","receipt_newer","missing_stream","regressed_stream"])
def test_marker_receipt_cannot_hide_live_process_fault(tmp_path,fault):
    path=session(tmp_path);life=ready(path,"primary",tmp_path/"primary")
    marker=dict(event="end",run_id="r",attempt=1,time_s=1.)
    life.marker(marker,1_000_000_000)
    receipt=json.loads((path.parent/"primary_end.json").read_text())
    live=deepcopy(life.status);now=receipt["monotonic_ns"]+3_000_000_000
    live["monotonic_ns"]=now
    if fault=="future":live["monotonic_ns"]+=1
    elif fault=="closed":live["closed"]=True
    elif fault=="error":live["error"]="disk error"
    elif fault=="not_ready":live["ready"]=False
    elif fault=="pid":live["pid"]+=1
    elif fault=="output":live["output"]="/other"
    elif fault=="session":live["session_id"]="other"
    elif fault=="source":live["source_sha256"]={}
    elif fault=="foreign_marker":marker=dict(marker,run_id="other")
    elif fault=="missing_live_marker":live["lifecycle"]=[]
    elif fault=="receipt_newer":receipt["monotonic_ns"]=now+1
    elif fault=="missing_stream":live["counts"]["/joint_states"]=0
    elif fault=="regressed_stream":live["latest_source_ns"]["/joint_states"]-=1
    with pytest.raises(ValueError):
        ac.check_delivery(ac.read_session(path),live,receipt,"primary",marker,now_mono_ns=now)


def test_legacy_publisher_unchanged_end_ack_deferred_to_preserve_native_outcome(tmp_path,monkeypatch):
    publisher=Mock();ros=Mock()
    monkeypatch.delenv("NINO_ACQUISITION_SESSION",raising=False)
    assert ac.episode_publisher(publisher,ros) is publisher
    path=session(tmp_path);monkeypatch.setenv("NINO_ACQUISITION_SESSION",str(path))
    publisher.get_subscription_count.return_value=2
    marker=dict(event="end",run_id="r",attempt=1,time_s=2.)
    monkeypatch.setattr(ac,"wait_pair",lambda *_a,**_k:pytest.fail("End wait must follow native CSV persistence"))
    ac.publish_episode(publisher,marker,ros)
    assert json.loads((path.parent/"expected_end.json").read_text())==marker
    ros.assert_not_called()
    publisher.publish.assert_called_once()


def closed_fixture(tmp_path,*,boundary_pre_reset=False,omit_current_gt=False):
    from rclpy.serialization import serialize_message
    from sensor_msgs.msg import JointState
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    path=session(tmp_path);s=ac.read_session(path)
    primary=tmp_path/"primary";primary.mkdir()
    capture=tmp_path/"joint_gt"
    writer=FrameWriter(capture,metadata=dict(
        acquisition_session_id=s["session_id"],acquisition_protocol_sha256=s["protocol_sha256"],
        source_sha256=s["source_sha256"]["joint_gt"]["isolated_acquisition.py"],
        frames_source_sha256=s["source_sha256"]["joint_gt"]["acquisition_frames.py"]))
    reset=dict(event="reset",run_id="r",attempt=1,seed=s["job"]["seed"],time_s=1.,settings={})
    end=dict(event="end",run_id="r",attempt=1,time_s=2.,
             metrics=dict(termination="timeout",governor_run_id="r"))
    a=JointState();a.header.stamp.sec=1;a.header.stamp.nanosec=20_000_000
    a.name=["left_wheel_joint","right_wheel_joint"];a.velocity=[4.,5.];a.effort=[.3,.4]
    b=Odometry();b.header=a.header;b.twist.twist.linear.x=.3;b.pose.pose.orientation.w=1.
    # Pre-reset data remains raw, but cannot supply view boundary support.
    old=deepcopy(a);old.header.stamp.sec=0
    writer.append(1,serialize_message(old),20_000_000,20_000_000,1,0)
    if boundary_pre_reset:
        old=deepcopy(a);old.header.stamp.sec=1;old.header.stamp.nanosec=0;old.velocity=[999.,999.]
        writer.append(1,serialize_message(old),1_000_000_000,1_000_000_000,2,0)
        old_gt=deepcopy(b);old_gt.header=old.header
        writer.append(2,serialize_message(old_gt),1_000_000_000,1_000_000_000,3,0)
    packets=((3,String(data=json.dumps(reset)),1_000_000_000),
             (1,a,1_020_000_000),(2,b,1_020_000_000),
             (3,String(data=json.dumps(end)),2_000_000_000))
    for n,(topic,message,ns) in enumerate(packets,4):
        if omit_current_gt and topic==2:continue
        writer.append(topic,serialize_message(message),ns,ns,n,1)
    writer.close()
    health=ObserverHealth()
    with health.callback("state","/nino/governor/episode"):pass
    summary=health.close(primary)
    metadata=dict(complete=True,acquisition_session_id=s["session_id"],
        acquisition_protocol_sha256=s["protocol_sha256"],observer_health=summary,
        observer_health_source_sha256=s["source_sha256"]["primary"]["observer_health.py"],
        logger_sha256=s["source_sha256"]["primary"]["governor_logger.py"],
        source_config_sha256=s["config_sha256"],world_sha256=s["world_sha256"])
    atomic_json(primary/"metadata.json",metadata)
    rows=[dict(topic="/nino/governor/episode",data=reset),
        dict(topic="/joint_states",data=dict(velocity=[999.])),
        dict(topic="/nino/contact_lab/chassis",data=dict(contacts=["spike"])),
        dict(topic="/nino/governor/episode",data=end)]
    (primary/"samples.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    for name in ("contact_events.jsonl","robot_description.urdf","source_config.yaml"):
        (primary/name).write_text("raw unchanged\n")
    atomic_json(primary/"world_metadata.json",dict(cables=[dict(x_m=3.1,angle_deg=8.)],fixture=True))
    atomic_json(primary/"resolved_config.json",dict(governor={}))
    pair={}
    for role,output in (("primary",primary),("joint_gt",capture)):
        life=ready(path,role,output);pair[role]=deepcopy(life.status)
        life.marker(reset,1_000_000_000);life.marker(end,2_000_000_000)
        for topic in ac.SENSOR_TOPICS:life.sample(topic,2_000_000_000)
        life.close(2_000_000_000)
    atomic_json(path.parent/"readiness_pair.json",pair)
    atomic_json(path.parent/"expected_end.json",end)
    evaluation=tmp_path/"evaluation";(evaluation/"episode-001").mkdir(parents=True)
    with (evaluation/"episode-001/control_trace.csv").open("w") as f:
        # Real evaluator traces do not carry governor_run_id. Identity lives
        # in the single native outcome and must agree with lifecycle markers.
        w=csv.DictWriter(f,fieldnames=["seed","governor_input_time_s","sim_time_s"])
        w.writeheader();w.writerow(dict(seed=s["job"]["seed"],governor_input_time_s=1.,sim_time_s=2.))
    with (evaluation/"episodes.csv").open("w") as f:
        w=csv.DictWriter(f,fieldnames=["governor_run_id","seed","attempt"])
        w.writeheader();w.writerow(dict(governor_run_id="r",seed=s["job"]["seed"],attempt=1))
    return path,primary,evaluation


def test_full_composition_both_closures_source_hash_epoch_and_no_legacy_patch(tmp_path):
    path,primary,evaluation=closed_fixture(tmp_path)
    before=ac.sha(primary/"samples.jsonl")
    view=ac.finalize_view(tmp_path,evaluation,primary,path)
    manifest=ac.verify_view(view)
    assert manifest["admitted_for_new_contract"] and not manifest["valid_for_existing_scoring"]
    assert manifest["selected_epoch_only"]
    assert not (view/"metadata.json").exists()
    rows=[json.loads(l) for l in (view/"samples.jsonl").open()]
    joints=[r for r in rows if r["topic"]=="/joint_states"]
    assert len(joints)==1 and joints[0]["data"]["velocity"]==[4.,5.]
    assert joints[0]["data"]["effort"]==[.3,.4]
    assert any(r["data"].get("contacts")==["spike"] for r in rows)
    assert ac.sha(primary/"samples.jsonl")==before
    (primary/"samples.jsonl").write_text("tamper")
    with pytest.raises(ValueError,match="input changed"):ac.verify_view(view)


def test_real_trace_schema_binds_native_id_without_fabricating_trace_column(tmp_path):
    path,primary,evaluation=closed_fixture(tmp_path)
    trace=evaluation/"episode-001/control_trace.csv"
    before=trace.read_bytes()
    assert "governor_run_id" not in next(csv.DictReader(trace.open()))
    view=ac.finalize_view(tmp_path,evaluation,primary,path)
    assert ac.verify_view(view)["run_id"]=="r"
    assert trace.read_bytes()==before


@pytest.mark.parametrize("fault",["missing_native","empty_native","duplicate_native","empty_id",
    "foreign_id","wrong_seed","wrong_attempt","foreign_trace_id"])
def test_native_identity_missing_ambiguous_or_foreign_fails_closed(tmp_path,fault):
    path,primary,evaluation=closed_fixture(tmp_path)
    native=evaluation/"episodes.csv"
    if fault=="missing_native":native.unlink()
    elif fault=="empty_native":native.write_text("governor_run_id,seed,attempt\n")
    elif fault=="duplicate_native":
        with native.open("a") as f:f.write("r,77600,1\n")
    elif fault=="foreign_trace_id":
        (evaluation/"episode-001/control_trace.csv").write_text(
            "governor_run_id,governor_input_time_s,sim_time_s\nother,1,2\n")
    else:
        row=dict(governor_run_id="r",seed=77600,attempt=1)
        row[{"empty_id":"governor_run_id","foreign_id":"governor_run_id",
             "wrong_seed":"seed","wrong_attempt":"attempt"}[fault]]={
            "empty_id":"","foreign_id":"other","wrong_seed":77601,"wrong_attempt":2}[fault]
        with native.open("w") as f:
            w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
    with pytest.raises((ValueError,FileNotFoundError)):
        ac.finalize_view(tmp_path,evaluation,primary,path)
    assert not (tmp_path/"measurement_view").exists()


@pytest.mark.parametrize("filename",["episodes.csv","episode-001/control_trace.csv"])
def test_native_identity_and_trace_are_in_view_provenance(tmp_path,filename):
    path,primary,evaluation=closed_fixture(tmp_path)
    view=ac.finalize_view(tmp_path,evaluation,primary,path)
    changed=evaluation/filename
    with changed.open("a") as f:f.write("tamper\n")
    with pytest.raises(ValueError,match="input changed"):ac.verify_view(view)


def test_world_metadata_required_by_quality_analyzer_is_copied_verbatim(tmp_path):
    path,primary,evaluation=closed_fixture(tmp_path)
    view=ac.finalize_view(tmp_path,evaluation,primary,path)
    assert (view/"world_metadata.json").read_bytes()==(primary/"world_metadata.json").read_bytes()
    assert "world_metadata.json" in ac.verify_view(view)["derived_sha256"]


@pytest.mark.parametrize("location",["source","view"])
def test_world_metadata_tamper_blocks_view_admission(tmp_path,location):
    path,primary,evaluation=closed_fixture(tmp_path)
    view=ac.finalize_view(tmp_path,evaluation,primary,path)
    target=(primary if location=="source" else view)/"world_metadata.json"
    target.write_text("changed geometry metadata")
    with pytest.raises(ValueError,match="changed"):ac.verify_view(view)


def test_missing_world_metadata_cannot_make_quality_ready_view(tmp_path):
    path,primary,evaluation=closed_fixture(tmp_path)
    (primary/"world_metadata.json").unlink()
    with pytest.raises(FileNotFoundError):ac.finalize_view(tmp_path,evaluation,primary,path)


def test_paused_clock_boundary_pre_reset_rows_retained_raw_never_supply_view(tmp_path):
    path,primary,evaluation=closed_fixture(tmp_path,boundary_pre_reset=True)
    from nino_rl.acquisition_frames import read_frames
    before=ac.sha(tmp_path/"joint_gt/joint_gt.frames")
    assert sum(f["epoch"]==0 and f["source_ns"]==1_000_000_000
               for f in read_frames(tmp_path/"joint_gt"))==2
    view=ac.finalize_view(tmp_path,evaluation,primary,path)
    rows=[json.loads(line) for line in (view/"samples.jsonl").open()]
    selected=[r for r in rows if r["topic"] in ac.SENSOR_TOPICS]
    assert len(selected)==2 and all(r["episode"]=="r:1" for r in selected)
    assert all(r["data"]["header"]["stamp"]["nanosec"]==20_000_000 for r in selected)
    assert ac.sha(tmp_path/"joint_gt/joint_gt.frames")==before
    # The legacy candidate remains strict. Only the explicit selected-epoch
    # integration path changes; no historical protocol is reinterpreted.
    from nino_rl.isolated_acquisition import decode
    with pytest.raises(ValueError,match="Pre-reset/late-marker"):
        decode(tmp_path/"joint_gt",tmp_path/"legacy_decode","r",1,1_000_000_000,2_000_000_000)


def test_boundary_pre_reset_gt_cannot_replace_missing_current_epoch_stream(tmp_path):
    path,primary,evaluation=closed_fixture(tmp_path,boundary_pre_reset=True,omit_current_gt=True)
    with pytest.raises(ValueError,match="Missing required joint/GT stream"):
        ac.finalize_view(tmp_path,evaluation,primary,path)


@pytest.mark.parametrize("fault",["incomplete_capture","bad_crc","wrong_config","bad_health",
                                  "restart","missing_end","foreign_end","primary_open"])
def test_both_logger_failures_fail_closed_not_legacy_fallback(tmp_path,fault):
    path,primary,evaluation=closed_fixture(tmp_path)
    if fault=="bad_crc":
        p=tmp_path/"joint_gt/joint_gt.frames";p.write_bytes(p.read_bytes()[:-1])
    elif fault=="incomplete_capture":
        p=tmp_path/"joint_gt/capture_manifest.json";v=json.loads(p.read_text());v["complete"]=False;atomic_json(p,v)
    elif fault in ("wrong_config","bad_health","primary_open"):
        p=primary/"metadata.json";v=json.loads(p.read_text())
        if fault=="wrong_config":v["source_config_sha256"]="wrong"
        elif fault=="bad_health":v["observer_health"]["valid"]=False
        else:v["complete"]=False
        atomic_json(p,v)
    else:
        p=path.parent/"joint_gt_status.json";v=json.loads(p.read_text())
        if fault=="restart":v["pid"]+=1
        elif fault=="missing_end":v["lifecycle"].pop()
        else:v["lifecycle"][-1]["run_id"]="foreign"
        atomic_json(p,v)
    with pytest.raises((ValueError,KeyError)):ac.finalize_view(tmp_path,evaluation,primary,path)


def test_coverage_gate_remains_per_window_with_every_spike_no_fill():
    times=np.arange(0,4.00001,.02)
    q=np.ones_like(times);q[30]=40000.  # peak kept, no clipping
    signal=dict(time=times,q=q,xy=np.column_stack((times*.4,times*0)))
    assert integrate(signal,0,4)["available"]
    full=integrate(signal,0,4)["rms"]
    assert full>10
    signal["q"][74:76]=np.nan
    assert integrate(signal,0,4)["available"]  # >98% route
    assert not integrate(signal,1.4,1.6)["available"]  # failed local window cannot be hidden


def test_all_arms_use_same_acquisition_and_no_old_release(monkeypatch,tmp_path):
    bundle=tmp_path/"new_bundle"
    for job in schedule():
        args=command(bundle,job,tmp_path/"stage")
        assert args[args.index("--acquisition-contract")+1]==str(bundle/"protocol.json")
        assert json.loads(args[args.index("--acquisition-job")+1])==job
    import run_isolated_governor_cadence as runner
    monkeypatch.setattr(runner,"validate",lambda _:dict(contract="new",protocol_sha256="newhash"))
    with pytest.raises(ValueError):require_release(bundle,None)
    release=tmp_path/"old_release.json"
    atomic_json(release,dict(execution_authorized=True,budget_released=True,maximum_attempts=12,
        contract="old",protocol_sha256="oldhash",thresholds_applied=False))
    with pytest.raises(ValueError):require_release(bundle,release)


def test_closed_production_batch_cannot_accept_current_sources():
    from prepare_governor_h2_protocol import validate_bundle
    with pytest.raises(ValueError,match="Workspace contract changed"):
        validate_bundle(ROOT/"docs/governor_h2_replication_protocol_2026-10-17")


def test_matching_release_accepts_executor_file_path_and_rejects_drift(monkeypatch,tmp_path):
    import run_isolated_governor_cadence as runner
    monkeypatch.setattr(runner,"validate",lambda _:dict(contract="new",protocol_sha256="newhash"))
    release=tmp_path/"release.json"
    binding=dict(execution_authorized=True,budget_released=True,maximum_attempts=12,
        contract="new",protocol_sha256="newhash",thresholds_applied=False,
        executor_sha256=runner.sha(Path(runner.__file__)),
        authorization_reference="Bounded test release; no simulation")
    atomic_json(release,binding)
    assert runner.require_release(tmp_path,release)==binding
    atomic_json(release,dict(binding,executor_sha256="foreign_executor"))
    with pytest.raises(ValueError):runner.require_release(tmp_path,release)


def test_new_freeze_is_offline_same_inputs_all_arms_and_detects_drift(tmp_path,monkeypatch):
    import subprocess
    import prepare_isolated_cadence_contract as plan
    monkeypatch.setattr(subprocess,"Popen",lambda *_a,**_k:pytest.fail("No simulation in freeze"))
    bundle=tmp_path/"new_contract"
    status=plan.prepare(bundle)
    assert status["simulation_attempts"]==0 and status["budget_released"] is False
    protocol=json.loads((bundle/"protocol.json").read_text())
    assert protocol["acquisition"]["all_arms"]=={arm:"isolated_joint_gt" for arm in ARMS}
    assert protocol["parent"]["slots_reused"] is False
    assert protocol["thresholds_applied"] is False
    for name in protocol["parent_input_sha256"]:
        assert ac.sha(bundle/"inputs"/name)==ac.sha(plan.PARENT/"inputs"/name)
    with pytest.raises(FileExistsError):plan.prepare(bundle)
    (bundle/"inputs/full.yaml").write_text("changed")
    with pytest.raises(ValueError):plan.validate(bundle)


def test_missing_capture_keeps_native_failure_and_cannot_fall_back_to_legacy(tmp_path,monkeypatch):
    import run_isolated_governor_cadence as runner
    job=schedule()[0]
    monkeypatch.setattr(runner,"collect_attempt",lambda *_a,**_k:dict(
        physical_success=False,termination="stall",measurement_integrity_pass=True))
    result=runner.collect(tmp_path,job,tmp_path)
    assert result["physical_success"] is False and result["termination"]=="stall"
    assert result["measurement_integrity_pass"] is False and result["acquisition_error"]


def test_invalid_measurement_blocks_comparison_but_retains_every_assigned_slot(tmp_path,monkeypatch):
    import analyze_isolated_governor_cadence as analysis
    run=tmp_path/"run";run.mkdir()
    slots=[dict(**job,adapter_requested=False,result=None) for job in schedule()]
    slots[0].update(adapter_requested=True,result=dict(physical_success=False,termination="timeout"))
    atomic_json(run/"ledger.json",dict(dry_run=False,slots=slots))
    monkeypatch.setattr(analysis,"validate",lambda _:None)
    result=analysis.analyze(tmp_path,run,tmp_path/"analysis")
    assert result["measurement_valid"] is False
    report=json.loads((tmp_path/"analysis/report.json").read_text())
    assert len(report["all_assigned_slots_and_native_outcomes"])==12
    assert report["all_assigned_slots_and_native_outcomes"][0]["result"]["physical_success"] is False
    assert report["contrasts"] is None and report["H2_decision"]=="not_assessed"
