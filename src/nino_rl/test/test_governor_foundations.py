import importlib.util
from pathlib import Path
from dataclasses import asdict
import json
import pytest

ROOT=Path(__file__).resolve().parents[1]/"scripts"


def script(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe=script("run_governor_foundation_probe")
audit=script("audit_governor_foundations")


def test_probe_separates_clean_maneuvers_from_contact_case():
    assert "crossing" not in probe.CLEAN_CASES
    assert probe.command("accelerate",.2)==(0.,0.)
    assert probe.command("brake_recover",2.)[0]<probe.command("brake_recover",3.)[0]
    assert probe.command("turn",2.)[1]!=0.
    assert probe.duration("crossing")>probe.duration("turn")


def test_confirmation_rejects_isolated_spike_but_not_sustained_disturbance():
    from nino_control.governor_core import GovernorSettings,GovernorFrame
    from dataclasses import replace
    frame=GovernorFrame(0.,0.,4.8,4.8,4.8,4.8,.3)
    rows=[]
    for index in range(40):
        f=replace(frame,vertical_m_s2=3.) if index==12 else frame
        rows.append({**asdict(f),"dt":.1,"governor_requested_linear_m_s":.3,
                     "governor_requested_yaw_rad_s":0.,"elapsed_s":(index+1)*.1})
    settings=GovernorSettings(confirmation_seconds=.3)
    assert audit.replay(rows,settings)["event_count"]==0
    for index in range(12,22): rows[index]["vertical_m_s2"]=3.
    assert audit.replay(rows,settings)["event_count"]==1


def test_candidate_cannot_run_with_wrong_world_or_unverified_model(tmp_path):
    config={"simulation_model":{"caster_wheel_damping":.001}}
    (tmp_path/"world_metadata.json").write_text(json.dumps({"variant":"clear"}))
    meta=dict(robot_description_validated=True,caster_wheel_damping_observed={"left":.001,"right":.001})
    (tmp_path/"metadata.json").write_text(json.dumps(meta))
    assert probe.verified_logger(tmp_path,config,"clear")==tmp_path
    with pytest.raises(ValueError): probe.verified_logger(tmp_path,config,"cable")
    meta["caster_wheel_damping_observed"]["right"]=.01
    (tmp_path/"metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError): probe.verified_logger(tmp_path,config,"clear")


def test_incomplete_replay_is_not_reported_as_zero_false_triggers():
    from nino_control.governor_core import GovernorSettings
    result=audit.replay([{"dt":.1}],GovernorSettings())
    assert not result["available"]
    assert result["event_count"] is None


def test_aborted_evaluation_is_not_a_success_or_a_zero_impact_episode():
    from nino_rl.evaluation import failure_record
    row=failure_record(RuntimeError("stale wall scan"),0,76000,0)
    assert row["kind"]=="measurement_aborted" and row["episode"]==1
    assert row["success"] is None and not row["task_outcome_available"]
    assert row["completed_episodes"]==0
