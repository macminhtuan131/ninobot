from copy import deepcopy
import json
import pytest
from nino_rl.motion_quality_draft import load,reference_plan


def test_preparation_never_releases_physics_or_accepts_factory_thresholds():
    p=load()
    assert p['release']['allocated_attempts']==0 and not p['release']['physics_allowed']
    assert not p['objective']['accepted'] and not p['decision_rules']['accepted']
    assert len(p['proposed_attempts'])==6 and p['proposed_budget']['task_ticks_max']==960


def test_slow_control_matches_command_segment_time_only():
    result=reference_plan(load())
    assert result['constant_segment_duration_s']==pytest.approx(result['preview_segment_duration_s'])
    assert .18 < result['constant_pace_m_s'] < .2
    assert result['predicted_time_cost_fraction'] < .1
    assert not result['actual_time_matching_verified'] and result['physics_steps']==0


def test_no_silent_change_or_fake_release(tmp_path):
    for key in ('release','objective'):
        p=deepcopy(load())
        p[key]['physics_allowed' if key=='release' else 'accepted']=True
        f=tmp_path/'plan.json';f.write_text(json.dumps(p))
        with pytest.raises(ValueError):load(f)


def test_stop_overlap_and_incomplete_recovery_are_rejected_before_physics():
    p=deepcopy(load());p['reference']['source_stop_s']=6
    with pytest.raises(ValueError):reference_plan(p)
    p=deepcopy(load());p['reference']['preview_progress_zone_m'][1]=1.29
    with pytest.raises(ValueError):reference_plan(p)
