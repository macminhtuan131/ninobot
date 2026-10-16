"""Preserve physical scoring when a cable legitimately exceeds clear-floor tilt."""
import importlib.util
from pathlib import Path
import sys
import json

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location("repeat_screen",SCRIPTS/"run_clear_floor_repeat.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def example(**overrides):
    data=dict(completed_evaluation=True,physical_success_rate=1.,maximum_abs_roll_deg=1.,
        maximum_abs_pitch_deg=13.,post_arrival_stop=dict(settled=True))
    return {**data,**overrides}


def test_cable_tilt_does_not_override_independent_physical_success():
    assert module.motion_screen_passed(example(),0,clear_floor=False)
    assert not module.motion_screen_passed(example(),0,clear_floor=True)


def test_physical_failure_is_not_promoted_by_successful_stopping():
    assert not module.motion_screen_passed(example(physical_success_rate=0.),0,clear_floor=False)


def test_missing_stop_window_is_not_promoted():
    assert not module.motion_screen_passed(example(post_arrival_stop=dict(settled=None)),0,clear_floor=False)


def test_missing_contact_analysis_keeps_native_arrival_failure(tmp_path):
    from summarize_contact_oracle_h2 import native_status
    evaluation=tmp_path/"evaluation"/"run"
    evaluation.mkdir(parents=True)
    (evaluation/"summary.json").write_text(json.dumps(dict(complete=True)))
    (evaluation/"episodes.csv").write_text("success,termination\nFalse,rollover\n")
    assert native_status(tmp_path)==dict(complete=True,physical_success=False,termination="rollover")


def test_randomized_schedule_preserves_seed_blocks_and_all_cases():
    seeds=[76400,76401,76402,76403,76404];profiles=["full","moderate"]
    first=module.case_schedule(seeds,profiles,True,76450)
    assert first==module.case_schedule(seeds,profiles,True,76450)
    for i,seed in enumerate(seeds):
        assert sorted(first[2*i:2*i+2])==[(seed,"full"),(seed,"moderate")]
    assert profiles==["full","moderate"]


def test_constant_reference_does_not_slow_the_adaptive_arm():
    from copy import deepcopy
    common=dict(navigation=dict(straight_speed_m_s=.4),
                governor=dict(parameters=dict(profile="moderate",minimum_scale=.55)))
    reference=deepcopy(common);adaptive=deepcopy(common)
    module.configure_profile(reference,"full",.388)
    module.configure_profile(adaptive,"moderate",.388)
    assert reference["navigation"]["straight_speed_m_s"]==.388
    assert adaptive["navigation"]["straight_speed_m_s"]==.4
    assert reference["governor"]["parameters"]["profile"]=="full"
    assert adaptive["governor"]["parameters"]["minimum_scale"]==.55
