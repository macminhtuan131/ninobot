"""Synthetic-only H2 decisions; no historical trace reads or subprocesses."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from prepare_governor_h2_protocol import ROOT,make_schedule,sha
from analyze_governor_h2_replication import evaluate,timing_evidence,analyze_run,read_evidence,markdown_report


@pytest.fixture(autouse=True)
def forbid_processes(monkeypatch):
    import subprocess
    def forbidden(*a,**k):raise AssertionError("Synthetic analysis cannot launch processes")
    monkeypatch.setattr(subprocess,"Popen",forbidden)
    monkeypatch.setattr(subprocess,"run",forbidden)


def synthetic_batch():
    protocol=dict(schedule=make_schedule())
    criteria=dict(status="confirmed",primary_metric="postcontact_GT_slip_square_per_m",
        minimum_relative_improvement=.1,maximum_added_route_seconds=.5,
        requirement_origin="user_accepted_engineering_assumption",synthetic_only=True)
    slots=[];evidence={}
    for job in protocol["schedule"]:
        g=job["profile"]=="reactive";base=[10.,12.,8.,11.][job["repeat"]-1]
        slip=base*(.8 if g else 1.)
        sample=lambda **kw:dict(available=True,**kw)
        approach={key:dict(minimum=value-.0001,maximum=value+.0001,median=value) for key,value in
            (("v",.4),("y",0.),("yaw",0.),("roll",0.),("pitch",0.))}
        approach["coverage_fraction"]=1.
        old=dict(time_s=16.+job["repeat"]*.01+(.2 if g else 0.),physical_rmse_m=.005,
            whole_vertical_rms=1.9 if g else 2.,whole_vertical_peak=10.,native_slip_rms=.029 if g else .03,
            gt_native=dict(whole_route=sample(rms=.019 if g else .02),crossing=sample(slip_square_per_m=slip)),
            crossing_vertical=sample(rms=1.9 if g else 2.),
            sequence=dict(available=True,approach=approach,metrics=dict(whole_contact_sequence=dict(
                slip=sample(slip_square_per_m=slip),vertical=sample(rms=1.9 if g else 2.)))))
        post=dict(available=True,GT_slip=sample(slip_square_per_m=slip,slip_square_integral_s=slip,distance_m=1.),
            vertical=sample(rms=1.9 if g else 2.,peak=10.),grid20ms=sample(slip_square_per_m=slip),
            shifted10ms=sample(slip_square_per_m=slip))
        result=dict(seed=job["seed"],profile=job["profile"],physical_success=True,stop_pass=True,termination="success",
            setup_pass=True,provenance_pass=True,measurement_integrity_pass=True,physical_state_valid=True,
            quality_available=True,cleanup_confirmed=True,runner_exit=0,
            native_outcome=dict(success="True",termination="success",synthetic_only=True),
            quality=dict(existing_reports=old,postcontact=post))
        slots.append(dict(**job,status="collected",result=result))
        evidence[job["attempt"]]=dict(available=True,timing_pass=True,precontact_reduction=False,
            synthetic_only=True,response_snapshots="synthetic, not physical data")
    return protocol,slots,criteria,evidence


def decision(data):
    p,s,c,e=data
    return evaluate(p,s,c,e)


def governors(data,seed=None):
    return [r["result"] for r in data[1] if r["profile"]=="reactive" and (seed is None or r["seed"]==seed)]


def test_pass_requires_all_gates_and_keeps_eight_distinct_pairs():
    report=decision(synthetic_batch())
    assert report["decision"]=="dat" and all(v is True for v in report["gates"].values())
    assert len(report["pairs"])==8 and report["counts"]["assigned"]==16
    assert report["estimates"]["post_slip"]["aggregate"]["relative_benefit"]==pytest.approx(.2)
    assert not report["automatic_execution"] and report["synthetic_result_is_not_robot_validation"]


def test_bootstrap_resamples_intact_pairs_and_equal_weights_blocks_not_frames():
    data=synthetic_batch()
    for r in governors(data,77501):
        for key in ("GT_slip","grid20ms","shifted10ms"):
            r["quality"]["postcontact"][key]["slip_square_per_m"]*=.75  # block benefit40%
    report=decision(data);m=report["estimates"]["post_slip"]
    assert m["aggregate"]["relative_benefit"]==pytest.approx(.3)
    assert m["aggregate"]["benefit_CI95"]==pytest.approx([.3,.3])
    assert report["bootstrap"]["draws"]==10000 and report["bootstrap"]["seed"]==20261018
    assert report==decision(data)


def test_arrival_failure_stays_counted_even_with_censored_metrics():
    data=synthetic_batch();r=data[1][0]["result"]
    r.update(physical_success=False,stop_pass=None,termination="timeout",quality=None,quality_available=False)
    report=decision(data)
    assert report["decision"]=="khong_dat" and report["counts"]["physical_failures"]==1
    assert report["counts"]["missing_metric_counts"]["post_slip"]==1
    assert report["estimates"]["post_slip"]["aggregate"]["full_mean"] is None
    assert len(report["pairs"])==8


def test_missing_metric_is_not_zero_filled_or_success_only_averaged():
    data=synthetic_batch();data[1][0]["result"]["quality"]["postcontact"]["GT_slip"]["slip_square_per_m"]=None
    report=decision(data)
    assert report["decision"]=="chua_du_bang_chung"
    assert report["estimates"]["post_slip"]["aggregate"]["available"] is False
    assert report["estimates"]["post_slip"]["blocks"]["77501"]["available_pairs"]==3
    assert report["counts"]["physical_failures"]==0


def test_incomplete_ledger_retains_all_assigned_slots_and_unknown_outcomes():
    data=synthetic_batch()
    for row in data[1][2:]:row.update(status="not_attempted",result=None)
    report=decision(data)
    assert report["decision"]=="chua_du_bang_chung" and report["counts"]["native_unknown"]==14
    assert report["counts"]["attempted"]==2 and len(report["episodes"])==16


def test_primary_interval_overlap_is_inconclusive_even_if_point_benefit_exceeds_minimum():
    data=synthetic_batch()
    for row in data[1]:
        base=10.;value=[5.,9.,10.,10.][row["repeat"]-1] if row["profile"]=="reactive" else base
        for key in ("GT_slip","grid20ms","shifted10ms"):
            row["result"]["quality"]["postcontact"][key]["slip_square_per_m"]=value
    report=decision(data)
    assert report["estimates"]["post_slip"]["aggregate"]["relative_benefit"]==pytest.approx(.15)
    assert report["gates"]["worthwhile_primary_benefit"] is None
    assert report["decision"]=="chua_du_bang_chung"


@pytest.mark.parametrize("factor",[.95,1.,1.05])
def test_clearly_insufficient_or_harmful_primary_fails(factor):
    data=synthetic_batch()
    for row in data[1]:
        value=[10.,12.,8.,11.][row["repeat"]-1]*(factor if row["profile"]=="reactive" else 1.)
        for key in ("GT_slip","grid20ms","shifted10ms"):
            row["result"]["quality"]["postcontact"][key]["slip_square_per_m"]=value
    assert decision(data)["decision"]=="khong_dat"


def test_grid_reversal_cannot_be_hidden_by_favorable_GT_primary():
    data=synthetic_batch()
    for row in data[1]:
        if row["profile"]=="reactive":
            row["result"]["quality"]["postcontact"]["shifted10ms"]["slip_square_per_m"]*=1.5
    report=decision(data)
    assert report["gates"]["worthwhile_primary_benefit"] is True
    assert report["decision"]=="chua_du_bang_chung" and len(report["sampling_reversals"])==3


def test_reversal_in_one_block_is_reported_even_if_aggregate_grid_still_improves():
    data=synthetic_batch()
    for r in governors(data,77500):r["quality"]["postcontact"]["shifted10ms"]["slip_square_per_m"]*=1.3
    report=decision(data)
    assert report["decision"]=="chua_du_bang_chung"
    assert any(v["level"]=="77500" for v in report["sampling_reversals"])


@pytest.mark.parametrize("metric",["GT_slip","shifted10ms"])
def test_zero_denominators_have_no_epsilon_rescue(metric):
    data=synthetic_batch()
    for row in data[1]:row["result"]["quality"]["postcontact"][metric]["slip_square_per_m"]=0.
    report=decision(data)
    assert report["decision"]=="chua_du_bang_chung"


def test_undefined_bootstrap_draws_are_not_discarded():
    data=synthetic_batch()
    for row in data[1]:
        value=[0.,0.,0.,10.][row["repeat"]-1]*(.8 if row["profile"]=="reactive" else 1.)
        row["result"]["quality"]["postcontact"]["GT_slip"]["slip_square_per_m"]=value
    report=decision(data)
    assert report["estimates"]["post_slip"]["blocks"]["77500"]["undefined_bootstrap_denominators"]>0
    assert report["estimates"]["post_slip"]["aggregate"]["benefit_CI95"] is None
    assert report["decision"]=="chua_du_bang_chung"


@pytest.mark.parametrize("value",[None,float("nan"),float("inf"),-1.,True])
def test_nonfinite_invalid_or_missing_values_are_unavailable(value):
    data=synthetic_batch();data[1][0]["result"]["quality"]["postcontact"]["vertical"]["rms"]=value
    assert decision(data)["decision"]=="chua_du_bang_chung"


@pytest.mark.parametrize("field,value",[("whole_vertical_rms",2.01),("physical_rmse_m",.006),("time_s",17.)])
def test_existing_point_quality_time_tracking_gates_fail_without_rescoring(field,value):
    data=synthetic_batch()
    for r in governors(data):r["quality"]["existing_reports"][field]=value
    assert decision(data)["decision"]=="khong_dat"


def test_added_time_clearly_above_budget_fails_and_overlap_is_inconclusive():
    data=synthetic_batch()
    for r in governors(data):r["quality"]["existing_reports"]["time_s"]+=.4  # extra0.6s
    report=decision(data)
    assert report["decision"]=="khong_dat" and report["gates"]["application_added_time"] is False
    data=synthetic_batch()
    for row in data[1]:
        row["result"]["quality"]["existing_reports"]["time_s"]=16.+([0.,.1,.2,.9][row["repeat"]-1] if row["profile"]=="reactive" else 0.)
    report=decision(data)
    assert report["gates"]["application_added_time"] is None
    assert report["decision"]=="chua_du_bang_chung"


def test_whole_sequence_harm_cannot_be_hidden_by_fixed_window_improvement():
    data=synthetic_batch()
    for r in governors(data):r["quality"]["existing_reports"]["sequence"]["metrics"]["whole_contact_sequence"]["slip"]["slip_square_per_m"]*=1.5
    assert decision(data)["decision"]=="khong_dat"


@pytest.mark.parametrize("case",["approach","precontact","missing_timing","integrity","proposed_criteria","hard_stop"])
def test_invalid_comparison_or_pending_criteria_cannot_pass(case):
    data=synthetic_batch();row=data[1][0]
    if case=="approach":row["result"]["quality"]["existing_reports"]["sequence"]["approach"]["v"]["minimum"]=.2
    elif case=="precontact":data[3][2]["precontact_reduction"]=True
    elif case=="missing_timing":data[3][2]=dict(available=False)
    elif case=="integrity":row["result"]["measurement_integrity_pass"]=False
    elif case=="proposed_criteria":data[2]["status"]="proposed"
    elif case=="hard_stop":row["status"]="hard_stopped"
    assert decision(data)["decision"]=="chua_du_bang_chung"


def test_complete_but_inactive_governor_fails_timing_gate():
    data=synthetic_batch();data[3][2]["timing_pass"]=False
    assert decision(data)["decision"]=="khong_dat"


@pytest.mark.parametrize("case",["duplicate","reordered","foreign_seed"])
def test_pair_identity_and_chronological_order_cannot_be_silently_changed(case):
    data=synthetic_batch()
    if case=="duplicate":data[1][15]=deepcopy(data[1][14])
    elif case=="reordered":data[1][0],data[1][1]=data[1][1],data[1][0]
    else:data[1][0]["result"]["seed"]=77400
    report=decision(data)
    assert report["decision"]=="chua_du_bang_chung" and report["issues"]


def test_synthetic_criteria_and_unsealed_context_cannot_produce_real_batch_pass():
    p,s,c,e=synthetic_batch()
    report=evaluate(p,s,c,e,source_kind="new_batch",context_issues=["criteria_not_sealed_in_batch_authorization"])
    assert report["decision"]=="chua_du_bang_chung"
    assert "synthetic_criteria_cannot_validate_a_real_batch" in report["issues"]


def test_inconsistent_native_success_and_termination_cannot_pass():
    data=synthetic_batch();data[1][0]["result"]["termination"]="timeout"
    assert decision(data)["decision"]=="chua_du_bang_chung"


def timing_inputs():
    controls=[];drive=[]
    for t in np.arange(0.,5.001,.1):
        t=round(float(t),6);scale=.9 if 1.1<=t<1.8 else 1.
        controls.append(dict(governor_input_time_s=t,governor_scale=scale,governor_requested_linear_m_s=.4))
    for t in np.arange(0.,5.001,.02):
        t=round(float(t),6);received=round(math_floor(t/.1+1e-7)*.1,6)
        scale=.9 if 1.1<=received<1.8 else 1.;v=.4*scale
        drive.append(dict(sim_time_s=t,command_received_sim_s=received,requested_linear_m_s=v,executed_linear_m_s=v,
            left_target_rad_s=v/.0625,right_target_rad_s=v/.0625))
    names=lambda c:["cable_bumps::cables::C1_collision",c]
    events=[dict(time_s=t,component=c,event=event,collisions=names(c),named_positive_obstacle=True)
        for t,c,event in ((1.,"caster_left_wheel","begin"),(1.2,"caster_left_wheel","end"),
                          (1.3,"caster_right_wheel","begin"),(1.5,"caster_right_wheel","end"))]
    loads=[dict(time_s=t,component=c,collisions=names(c)) for t,c in ((1.01,"caster_left_wheel"),(1.15,"caster_left_wheel"),(1.31,"caster_right_wheel"))]
    ground=[(round(float(t),6),dict(linear=dict(x=.4))) for t in np.arange(0.,5.001,.02)]
    joints=[(round(float(t),6),dict(left_wheel_joint=6.4,right_wheel_joint=6.4)) for t in np.arange(0.,5.001,.002)]
    return controls,drive,events,loads,ground,joints,1.,"reactive"


def math_floor(v):return int(np.floor(v))


def test_timing_requires_new_loaded_contact_and_causal_sensor_support():
    report=timing_evidence(*timing_inputs())
    assert report["available"] and report["timing_pass"] and not report["precontact_reduction"]
    assert report["first_executed"]["time_s"]<report["next_loaded_contact"]["manifold"]["time_s"]
    assert report["next_loaded_contact"]["manifold"]["component"]=="caster_right_wheel"
    assert all(s["body"]["age_s"]>=0 and s["joints"]["age_s"]>=0 for s in report["response_snapshots"].values())


@pytest.mark.parametrize("case",["continuing_contact","command_only","target_not_changed","no_loaded_contact"])
def test_requested_action_or_ongoing_manifold_alone_does_not_prove_authority(case):
    args=list(timing_inputs())
    if case=="continuing_contact":args[2]=args[2][:2]
    elif case=="command_only":
        for d in args[1]:d["executed_linear_m_s"]=.4
    elif case=="target_not_changed":
        for d in args[1]:d.update(left_target_rad_s=6.4,right_target_rad_s=6.4)
    else:args[3]=[p for p in args[3] if p["component"]=="caster_left_wheel"]
    report=timing_evidence(*args)
    assert report["available"] and report["timing_pass"] is False


@pytest.mark.parametrize("index",[0,1,4,5])
def test_missing_timing_support_is_unknown_not_a_timing_failure(index):
    args=list(timing_inputs());args[index]=[]
    report=timing_evidence(*args)
    assert report["available"] is False and report["timing_pass"] is None


def test_future_command_receipt_cannot_be_used_as_evidence():
    args=list(timing_inputs());args[1][60]["command_received_sim_s"]=2.
    report=timing_evidence(*args)
    assert not report["available"] and "future_or_nonfinite" in report["error"]


def test_analysis_of_offline_plan_stays_inconclusive_and_does_not_modify_input(tmp_path):
    bundle=ROOT/"docs/governor_h2_replication_protocol_2026-10-17"
    plan=ROOT/"docs/governor_h2_executor_2026-10-17/offline_plan"
    before=sha(plan/"ledger.json")
    report=analyze_run(bundle,plan,bundle/"application_requirements.json",tmp_path/"report")
    assert report["decision"]=="chua_du_bang_chung" and report["counts"]["attempted"]==0
    assert sha(plan/"ledger.json")==before


def test_missing_ledger_returns_unknown_assigned_slots_not_fabricated_failures(tmp_path):
    bundle=ROOT/"docs/governor_h2_replication_protocol_2026-10-17"
    empty=tmp_path/"empty_batch";empty.mkdir()
    report=analyze_run(bundle,empty,bundle/"application_requirements.json",tmp_path/"report")
    assert report["decision"]=="chua_du_bang_chung" and report["counts"]["native_unknown"]==16
    assert report["counts"]["physical_failures"]==0


def test_vibration_primary_uses_its_own_threshold_and_sequence_metric():
    data=synthetic_batch();data[2]["primary_metric"]="postcontact_vertical_sample_rms_m_s2"
    for r in governors(data):
        r["quality"]["postcontact"]["vertical"]["rms"]=1.6
        r["quality"]["existing_reports"]["sequence"]["metrics"]["whole_contact_sequence"]["vertical"]["rms"]=1.6
    report=decision(data)
    assert report["decision"]=="dat"
    assert "DỮ LIỆU TỔNG HỢP" in markdown_report(report)
    assert "CI95" in markdown_report(report)


@pytest.mark.parametrize("loaded",[True,False])
def test_read_only_timing_reader_uses_header_load_and_deduplicates_synthetic_sensors(tmp_path,loaded):
    import csv
    args=timing_inputs();cs,ds,events,loads,ground,joints,tc,profile=args
    case=tmp_path/"new_batch/attempt_01/case";ev=case/"evaluation/synthetic/episode-001";logger=case/"contact/synthetic"
    ev.mkdir(parents=True);logger.mkdir(parents=True)
    for path,rows in ((ev/"control_trace.csv",cs),(ev/"drive_trace.csv",ds)):
        with path.open("w") as stream:
            w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (logger/"contact_events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
    def packet(t,topic,data):
        ns=round(t*1e9);data=dict(data,header=dict(stamp=dict(sec=ns//10**9,nanosec=ns%10**9)))
        return json.dumps(dict(topic=topic,receipt_time_s=9999.,data=data))+"\n"
    with (logger/"samples.jsonl").open("w") as stream:
        for t,v in ground:stream.write(packet(t,"/ground_truth/odom",dict(twist=dict(twist=v))))
        for t,v in joints:stream.write(packet(t,"/joint_states",dict(name=list(v),velocity=list(v.values()))))
        for c in loads:
            force=1. if loaded or c["component"]=="caster_left_wheel" else 0.
            contact=dict(collision1=dict(name=c["collisions"][0]),collision2=dict(name=c["collisions"][1]),
                depths=[.001],wrenches=[dict(body_1_wrench=dict(force=dict(x=0.,y=0.,z=force)))])
            stream.write(packet(c["time_s"],"/nino/contact_lab/"+c["component"],dict(contacts=[contact])))
        # A duplicate stamp follows earlier messages; keep-last matches sensor protocol.
        stream.write(packet(1.2,"/ground_truth/odom",dict(twist=dict(twist=dict(linear=dict(x=.39))))))
    row=dict(attempt=1,profile=profile,result=dict(case=str(case),quality=dict(existing_reports=dict(first_contact_s=tc))))
    report,hashes=read_evidence(row,tmp_path/"new_batch")
    assert report["available"] and report["timing_pass"] is loaded
    assert len(hashes)==4


def test_timing_reader_refuses_a_case_outside_the_selected_batch(tmp_path):
    row=dict(result=dict(case=str(tmp_path/"other_batch")))
    with pytest.raises(ValueError,match="outside selected new batch"):
        read_evidence(row,tmp_path/"selected_batch")
