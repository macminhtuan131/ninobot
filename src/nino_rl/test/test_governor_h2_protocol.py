from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from prepare_governor_h2_protocol import (
    application_issues, arm_config, make_schedule, prepare, validate_bundle,
    validate_schedule, write,
)


def test_random_schedule_balances_both_arms_each_seed_and_each_round():
    for seed in (0,1,17,20261017):
        schedule=make_schedule(seed)
        validate_schedule(schedule)
        assert schedule==make_schedule(seed)
    assert make_schedule(0)!=make_schedule(17)


def test_duplicate_arm_or_broken_pair_cannot_be_silently_used():
    schedule=make_schedule()
    schedule[1]["profile"]=schedule[0]["profile"]
    with pytest.raises(ValueError):
        validate_schedule(schedule)
    schedule=make_schedule()
    schedule[1],schedule[2]=schedule[2],schedule[1]
    for i,row in enumerate(schedule,1):row["attempt"]=i
    with pytest.raises(ValueError,match="Pair must remain adjacent"):
        validate_schedule(schedule)


def test_arms_differ_only_in_profile_without_mutating_base():
    base=dict(navigation=dict(straight_speed_m_s=.4),governor=dict(parameters=dict(profile="reactive",target_scale=.9,trigger_to_brake_delay_seconds=0.)))
    saved=deepcopy(base)
    a,b=arm_config(base,"full"),arm_config(base,"reactive")
    a["governor"]["parameters"]["profile"]="reactive"
    assert a==b==base==saved


def test_missing_nonfinite_or_unconfirmed_application_values_block_readiness():
    assert application_issues({})
    app=dict(primary_metric="postcontact_vertical_sample_rms_m_s2",minimum_relative_improvement=.1,
             maximum_added_route_seconds=.5,requirement_origin="user_factory_requirement")
    assert not application_issues(app)
    for value in (None,float("nan"),float("inf"),True,0.,1.):
        assert application_issues(dict(app,minimum_relative_improvement=value))


@pytest.fixture
def bundle(tmp_path):
    folder=tmp_path/"protocol"
    prepare(folder)
    return folder


def test_prepared_protocol_stays_unfunded_even_if_application_form_is_completed(bundle):
    result=validate_bundle(bundle)
    assert result["structure_valid"] and result["pending_application_fields"]
    write(bundle/"application_requirements.json",dict(primary_metric="postcontact_GT_slip_square_per_m",
        minimum_relative_improvement=.1,maximum_added_route_seconds=.5,requirement_origin="user_accepted_engineering_assumption"))
    result=validate_bundle(bundle)
    assert not result["pending_application_fields"]
    assert not result["run_allowed"] and not result["execution_authorized"] and not result["budget_released"]


def test_config_or_protocol_hash_drift_is_rejected(bundle):
    p=bundle/"inputs/reactive.yaml";old=p.read_text()
    p.write_text(old+"\n# drift\n")
    with pytest.raises(ValueError,match="Frozen bundle changed"):
        validate_bundle(bundle)
    p.write_text(old)
    p=bundle/"protocol.json";p.write_text(p.read_text()+"\n")
    with pytest.raises(ValueError,match="Prepared protocol changed"):
        validate_bundle(bundle)
