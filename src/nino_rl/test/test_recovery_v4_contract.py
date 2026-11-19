from dataclasses import replace
from pathlib import Path
import json
import math

import pytest

from nino_rl.recovery_v4_contract import (
    NEUTRAL_ACTION, EndReason, Health, MissionReference, ProjectionState,
    RewardLabels, RewardSettings, RewardState, SlowdownSettings, end_flags,
    identity, load_config, project_slowdown, require_identity, require_release,
    score_reward, state_metadata,
)

CONFIG = Path(__file__).parents[1] / "config/recovery_v4.yaml"


def health(**changes):
    return replace(Health(True, False, False, 0., 0., 0., 5), **changes)


def steady():
    return ProjectionState((.2, .2), (.2, .2))


@pytest.mark.parametrize("action,slowdown", [(-1., 0.), (0., .01), (1., .02)])
def test_affine_action_and_actual_cost(action, slowdown):
    settings = SlowdownSettings()
    result = project_slowdown(settings, steady(), (.2, 0.), action, .1, health())
    accepted = min(slowdown, settings.wheel_acceleration_m_s2*.1)
    assert result.requested_slowdown_m_s == pytest.approx(slowdown)
    assert result.accepted_slowdown_m_s == pytest.approx(accepted)
    assert result.final_body_reference == pytest.approx((.2 - accepted, 0.))
    update = score_reward(RewardSettings(), RewardState(), RewardLabels(.1, .01, 0., 0., 0., accepted / .02, 0.))
    assert update.terms["action"] == pytest.approx(-.01 * (accepted / .02)**2 * .1)


def test_zero_cannot_start_and_short_history_is_baseline_only():
    stopped = project_slowdown(SlowdownSettings(), ProjectionState(), (0., 0.), 1., .1, health())
    assert stopped.final_body_reference == (0., 0.)
    warm = project_slowdown(SlowdownSettings(), steady(), (.2, 0.), 1., .1, health(history_real_frames=4))
    assert warm.final_body_reference == pytest.approx((.2, 0.))
    assert not warm.learning_eligible
    assert warm.reason == "history_warmup"


@pytest.mark.parametrize("changes", [dict(permission=False), dict(fault=True), dict(emergency_stop=True), dict(imu_age_s=.5), dict(wheel_age_s=.5), dict(command_age_s=.5)])
def test_bad_health_latches_zero(changes):
    result = project_slowdown(SlowdownSettings(), steady(), (.2, 0.), -1., .1, health(**changes))
    assert result.next_state.final_wheel_m_s == (0., 0.)
    assert result.next_state.final_latched
    assert not result.learning_eligible
    restored = project_slowdown(SlowdownSettings(), result.next_state, (.2, 0.), -1., .1, health())
    assert restored.final_body_reference == (0., 0.)


def test_projection_generated_trace_and_serialization():
    settings = SlowdownSettings()
    state = ProjectionState()
    for i in range(150):
        nominal = (.2 if i < 100 else 0., .1 if i < 70 else 0.)
        action = (-1., 0., 1.)[i % 3]
        result = project_slowdown(settings, state, nominal, action, .1, health())
        rebuilt = ProjectionState.from_dict(json.loads(json.dumps(state.to_dict())))
        assert project_slowdown(settings, rebuilt, nominal, action, .1, health()) == result
        if result.learning_eligible:
            left, right = result.next_state.final_wheel_m_s
            assert 0 <= left <= settings.wheel_speed_m_s
            assert 0 <= right <= settings.wheel_speed_m_s
            assert max(abs(a-b) for a,b in zip((left,right),state.final_wheel_m_s)) <= settings.wheel_acceleration_m_s2*.1 + 1e-12
            assert result.final_body_reference[1] == pytest.approx(result.nominal_body_reference[1])
            assert result.final_body_reference[0] <= result.nominal_body_reference[0] + 1e-12
        state = result.next_state


@pytest.mark.parametrize("nominal,action,dt", [((-.1,0.),0.,.1), ((.1,10.),0.,.1), ((math.nan,0.),0.,.1), ((.2,0.),math.nan,.1), ((.2,0.),2.,.1), ((.2,0.),0.,0.)])
def test_invalid_input_or_forward_envelope_fails_closed(nominal, action, dt):
    result = project_slowdown(SlowdownSettings(), steady(), nominal, action, dt, health())
    assert result.final_body_reference == (0., 0.)
    assert result.next_state.final_latched
    assert not result.learning_eligible


def test_same_mission_state_same_target_and_deadline_observed():
    mission = MissionReference()
    assert mission.target(.1, .5) == mission.target(.1, .5)
    assert mission.target(2., .5) == pytest.approx(.2)
    assert mission.target(40., .5) == 0.
    metadata = state_metadata(steady(), health(), mission, RewardState(), 3., .5)
    assert metadata["remaining_time_fraction"] == pytest.approx(.925)
    assert metadata["mission_target_m_s"] == .2
    altered = state_metadata(replace(steady(),final_wheel_m_s=(.19,.19)), health(), mission, RewardState(), 3., .5)
    assert metadata != altered


def test_high_water_is_bounded_and_loops_cannot_harvest_progress():
    state = RewardState()
    earned = 0.
    for index, s in enumerate([0., .1, 0., .1, 0., .1, 20.]):
        update = score_reward(RewardSettings(), state, RewardLabels((index+1)*.1, s, 0., 0., 0., 0., 0.))
        earned += update.terms["progress"]
        state = update.next_state
    assert earned == pytest.approx(1.)
    assert state.highest_credited_progress_m == 4.
    outside = score_reward(RewardSettings(), RewardState(), RewardLabels(.1, 2., .2, 0., 0., 0., 0.))
    assert outside.terms["progress"] == 0.
    state = RewardState()
    total = 0.
    for i,s in enumerate([0., .1, 0., .1, 0.]):
        update = score_reward(RewardSettings(),state,RewardLabels((i+1)*.1,s,0.,0.,0.,0.,0.))
        total += update.terms["progress"]
        state=update.next_state
    assert total == pytest.approx(.1/4.)


def test_action_derivative_integral_and_terminal_once():
    settings=RewardSettings()
    coarse=score_reward(settings,RewardState(),RewardLabels(.2,0.,0.,0.,0.,1.,0.))
    first=score_reward(settings,RewardState(),RewardLabels(.1,0.,0.,0.,0.,.5,0.))
    second=score_reward(settings,first.next_state,RewardLabels(.2,0.,0.,0.,0.,1.,0.))
    assert coarse.terms["action_change"] == pytest.approx(first.terms["action_change"]+second.terms["action_change"])
    final=score_reward(settings,RewardState(),RewardLabels(.1,4.,0.,0.,0.,0.,0.,EndReason.SUCCESS))
    assert final.terms["terminal"] == 5.
    with pytest.raises(ValueError):
        score_reward(settings,final.next_state,RewardLabels(.2,4.,0.,0.,0.,0.,0.,EndReason.SUCCESS))
    assert final.total == pytest.approx(sum(final.terms.values()))


@pytest.mark.parametrize("changes", [dict(elapsed_s=0.),dict(elapsed_s=math.nan),dict(progress_m=math.nan),dict(accepted_slowdown_fraction=2.),dict(stability_cost=-1.),dict(end_reason=EndReason.INVALID_SOURCE)])
def test_bad_labels_do_not_advance_state(changes):
    state=RewardState()
    with pytest.raises(ValueError):
        score_reward(RewardSettings(),state,replace(RewardLabels(.1,0.,0.,0.,0.,0.,0.),**changes))
    assert state == RewardState()


def test_terminal_and_censoring_have_distinct_bootstrap_contracts():
    for reason in (EndReason.SUCCESS,EndReason.PHYSICAL_FAILURE,EndReason.INTRINSIC_DEADLINE):
        flags=end_flags(reason)
        assert flags.terminated and not flags.truncated and not flags.bootstrap
    for reason in (EndReason.EXTERNAL_SAMPLING,EndReason.CAMPAIGN_CUTOFF):
        flags=end_flags(reason)
        assert flags.truncated and not flags.terminated and flags.bootstrap
    assert not end_flags(EndReason.INVALID_SOURCE).valid_transition


def test_strict_profile_identity_release_and_old_v3_rejected(tmp_path):
    config=load_config(CONFIG)
    ident=identity(config)
    assert len({ident[key] for key in ("action_sha256","projection_sha256","reward_sha256","observation_spec_sha256")})==4
    require_identity(config,ident)
    with pytest.raises(ValueError):
        require_identity(config,{"contract_id":"nino_recovery_history100_accepted_common_v3"})
    for operation in ("gazebo","optimizer","hardware"):
        with pytest.raises(PermissionError):
            require_release(config,operation)
    require_release(config,"software_contract")
    text=CONFIG.read_text()
    for bad in (text.replace("learning_rate: 0.0003","actor_lr: 0.0003"),text.replace("learning_rate: 0.0003","learning_rate: null"),text.replace("learning_rate: 0.0003","learning_rate: REVIEW_REQUIRED"),text.replace("maximum_stage: 0","maximum_stage: 1"),text+"unknown: 2\n"):
        path=tmp_path/"bad.yaml";path.write_text(bad)
        with pytest.raises(ValueError):
            load_config(path)


def test_off_corridor_travel_cannot_earn_catchup_on_reentry():
    settings = RewardSettings()
    outside = score_reward(settings, RewardState(), RewardLabels(.1, 2., .2, 0., 0., 0., 0.))
    reenter = score_reward(settings, outside.next_state, RewardLabels(.2, 2., 0., 0., 0., 0., 0.))
    assert reenter.terms["progress"] == 0.
    new = score_reward(settings, reenter.next_state, RewardLabels(.3, 2.1, 0., 0., 0., 0., 0.))
    assert new.terms["progress"] == pytest.approx(.1/4)


@pytest.mark.parametrize("field,value", [("final_wheel_m_s", [float("nan"),0.]), ("final_wheel_m_s", [1.,1.]), ("final_wheel_m_s", [0.]), ("baseline_latched", 1), ("final_latched", True)])
def test_serialized_state_falsification_rejected(field,value):
    state = steady().to_dict()
    state[field] = value
    with pytest.raises(ValueError):
        ProjectionState.from_dict(state)


def test_deadline_is_intrinsic_terminal_even_at_campaign_cutoff():
    update = score_reward(RewardSettings(), RewardState(), RewardLabels(40., 2., 0., 0., 0., 0., 0., EndReason.CAMPAIGN_CUTOFF))
    assert update.end_reason is EndReason.INTRINSIC_DEADLINE
    assert update.end.terminated and not update.end.bootstrap


def test_duplicate_config_key_and_inconsistent_reconstructed_wheels_rejected(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text(CONFIG.read_text() + "release: software_contract_only\n")
    with pytest.raises(ValueError):
        load_config(path)
    data = steady().to_dict()
    data["final_wheel_m_s"] = [.19, .2]
    with pytest.raises(ValueError):
        ProjectionState.from_dict(data)


def test_neutral_requests_zero_but_retained_slew_tail_pays_actual_cost():
    settings = replace(SlowdownSettings(), wheel_acceleration_m_s2=.05)
    state = ProjectionState((.2, .2), (.18, .18))
    result = project_slowdown(settings, state, (.2, 0.), NEUTRAL_ACTION, .1, health())
    assert result.requested_slowdown_m_s == 0.
    assert result.accepted_slowdown_m_s == pytest.approx(.015)
    q = result.accepted_slowdown_m_s / settings.max_slowdown_m_s
    update = score_reward(RewardSettings(), RewardState(), RewardLabels(.1, 0., 0., 0., 0., q, 0.))
    assert update.terms["action"] == pytest.approx(-.01*.75**2*.1)


def test_float_high_water_from_measured_clean_run_keeps_its_own_invariant():
    state = RewardState(.001305677927972648, .5, .9877800941467285,
                        highest_seen_progress_m=.001305677927972648)
    result = score_reward(RewardSettings(), state, RewardLabels(
        .5999999999999999, .0034620391014356234, .0017421075386503896,
        .0038239251769355406, -.038436388265370255, .9877800941467283,
        1.29479760246929e-10))
    assert result.next_state.highest_credited_progress_m <= result.next_state.highest_seen_progress_m
    score_reward(RewardSettings(), result.next_state, RewardLabels(.7, .006, 0., 0., 0., 0., 0.))


def test_many_small_forward_credits_do_not_create_an_invalid_reward_state():
    import numpy as np
    rng = np.random.default_rng(1511)
    for _ in range(100):
        state = RewardState()
        progress = 0.
        for index in range(399):
            progress = min(4., progress+float(rng.uniform(0., .03)))
            result = score_reward(RewardSettings(), state, RewardLabels(
                (index+1)*.1, progress, 0., 0., 0., 0., 0.))
            state = result.next_state
            assert state.highest_credited_progress_m <= state.highest_seen_progress_m <= 4.
