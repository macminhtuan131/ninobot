from dataclasses import replace
from pathlib import Path
import math

import pytest

from nino_rl.recovery_v4_contract import (
    EndReason, Health, ProjectionState, RewardLabels, RewardSettings, RewardState,
    SlowdownSettings, identity, load_config, project_slowdown, score_reward,
)


CONFIG = Path(__file__).parents[1] / "config/recovery_v4.yaml"


def fresh():
    return Health(permission=True, emergency_stop=False, fault=False,
                  imu_age_s=0., wheel_age_s=0., command_age_s=0., history_real_frames=5)


def test_new_profile_keeps_existing_sim_reference_authority():
    config = load_config(CONFIG)
    assert config.projection.wheel_speed_m_s == .4
    assert config.projection.forward_m_s == .4
    assert config.projection.yaw_rad_s == .5
    assert config.projection.wheel_acceleration_m_s2 == .1
    assert config.projection.separation_m == .34273666
    assert config.mission.startup_acceleration_m_s2 == .1


def test_proposed_slowdown_remains_visible_when_low_speed_limits_acceptance():
    result = project_slowdown(SlowdownSettings(), ProjectionState(), (.005, 0.), 1., .1, fresh())
    assert result.requested_slowdown_m_s == .02
    assert result.accepted_slowdown_m_s <= .005
    assert result.final_body_reference[0] >= 0.


def test_code_identity_pins_implementation_bytes():
    import hashlib
    import nino_rl.recovery_v4_contract as core

    ident = identity(load_config(CONFIG))
    assert ident["implementation_sha256"] == hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest()


def test_long_control_gap_cannot_earn_fresh_projection_authority():
    result = project_slowdown(SlowdownSettings(), ProjectionState(), (.2, 0.), -1., 10., fresh())
    assert not result.learning_eligible
    assert result.next_state.final_latched
    assert result.final_body_reference == (0., 0.)


@pytest.mark.parametrize("field", ["progress_m", "cross_error_m", "heading_error_rad", "speed_error_m_s", "stability_cost"])
def test_extreme_finite_reward_labels_cannot_produce_nonfinite_transition(field):
    labels = RewardLabels(elapsed_s=.1, progress_m=0., cross_error_m=0.,
                          heading_error_rad=0., speed_error_m_s=0.,
                          accepted_slowdown_fraction=0., stability_cost=0.)
    try:
        value = score_reward(RewardSettings(), RewardState(), replace(labels, **{field: 1e308}))
    except ValueError:
        return
    assert math.isfinite(value.total)
    assert all(math.isfinite(term) for term in value.terms.values())


def test_success_after_intrinsic_deadline_is_not_success():
    labels = RewardLabels(elapsed_s=41., progress_m=4., cross_error_m=0.,
                          heading_error_rad=0., speed_error_m_s=0.,
                          accepted_slowdown_fraction=0., stability_cost=0., end_reason=EndReason.SUCCESS)
    with pytest.raises(ValueError):
        score_reward(RewardSettings(), RewardState(), labels)


def test_outside_corridor_progress_cannot_be_caught_up_on_reentry():
    settings = RewardSettings()
    outside = score_reward(settings, RewardState(), RewardLabels(.1, 2., .2, 0., 0., 0., 0.))
    reentry = score_reward(settings, outside.next_state, RewardLabels(.2, 2., 0., 0., 0., 0., 0.))
    advance = score_reward(settings, reentry.next_state, RewardLabels(.3, 2.1, 0., 0., 0., 0., 0.))
    assert outside.terms["progress"] == reentry.terms["progress"] == 0.
    assert advance.terms["progress"] == pytest.approx(.1 / 4.)


def test_full_slowdown_projection_is_a_valid_reward_input():
    settings = SlowdownSettings()
    state = ProjectionState((.1, .1), (.1, .1))
    for _ in range(2):
        result = project_slowdown(settings, state, (.1, 0.), 1., .1, fresh())
        state = result.next_state
    q = result.accepted_slowdown_m_s / settings.max_slowdown_m_s
    assert 0 <= q <= 1
    reward = score_reward(RewardSettings(), RewardState(), RewardLabels(.1, 0., 0., 0., 0., q, 0.))
    assert math.isfinite(reward.total)


def test_configured_slowdown_fits_reference_envelope():
    with pytest.raises(ValueError):
        SlowdownSettings(max_slowdown_m_s=1e308)
