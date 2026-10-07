"""Behavioral checks for reaching the goal while practicing wheel control."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from nino_rl.core import PathTracker, RobotState, TrackingState
from nino_rl.control_v2 import BASELINE_ACTION, ChallengeRegion, ChallengeTracker, compute_reward, decode_control
from nino_rl.task_geometry import approach_speed, goal_overshot, objective_state, task_succeeded

CONFIG = yaml.safe_load((Path(__file__).parents[1] / 'config/ppo.yaml').read_text())


def test_final_approach_never_accelerates_after_missing_goal():
    assert approach_speed(.5, .5, 0., CONFIG) > .03
    for error in (.2, .5, 1., 3.):
        assert approach_speed(error, 0., 0., CONFIG) == .03
    assert approach_speed(.09, .08, 0., CONFIG) == 0.
    # Inside the position circle but not yet aligned: retain steering authority.
    assert approach_speed(.09, .08, .3, CONFIG) == .03


def test_overshoot_is_a_failure_boundary_not_a_false_success():
    path = PathTracker([(0., 0.), (6., 0.)])
    assert not goal_overshot(RobotState(x=6.2, y=.5), path, CONFIG)
    assert goal_overshot(RobotState(x=6.31, y=.5), path, CONFIG)
    assert not goal_overshot(RobotState(x=5.8, y=.5), path, CONFIG)


def test_odometry_stop_margin_keeps_motion_until_physical_goal_can_be_reached():
    config = yaml.safe_load((Path(__file__).parents[1] /
                            'config/combined_flat_curriculum_goal_margin.yaml').read_text())
    path = PathTracker([(0., 0.), (6.45, 0.)])
    # Recorded failure: estimated distance 17 cm, physical distance 35 cm.
    state = RobotState(x=6.28, ground_x=6.10)
    physical = objective_state(state, config)
    tracking = TrackingState(6.10, 0., 0., .35, .35)
    assert not task_succeeded(tracking, physical, path, config)
    assert approach_speed(.17, .17, 0., config) > 0.
    assert approach_speed(.049, .049, 0., config) == 0.
    assert approach_speed(.4, 0., 0., config) == .03
    assert config['goal_tolerance_m'] == .20


@pytest.mark.parametrize('margin', [-.01, .21, float('nan')])
def test_invalid_odometry_stop_margin_is_rejected(margin):
    config = {**CONFIG, 'goal_tolerance_m': .2,
              'navigation': {**CONFIG['navigation'], 'goal_stop_tolerance_m': margin}}
    with pytest.raises(ValueError, match='goal_stop_tolerance_m'):
        approach_speed(.17, .17, 0., config)


def test_goal_residual_guard_leaves_course_authority_but_yields_to_pi_slowdown():
    config = {**CONFIG, 'max_wheel_torque_nm': 2.0, 'goal_tolerance_m': .2,
              'navigation': {**CONFIG['navigation'],
                             'goal_stop_tolerance_m': .05,
                             'goal_residual_fade_distance_m': .5}}
    action = [0.4, 0.4, 0.1]
    # Independent left/right commands remain available away from arrival.
    speed, torque, _ = decode_control(action, config, path_remaining=1.0)
    assert speed == pytest.approx(.7)
    np.testing.assert_allclose(torque, [.6, 1.0])
    _, half, _ = decode_control(action, config, path_remaining=.275)
    np.testing.assert_allclose(half, torque * .5)
    # Recorded misses were still physically moving at 0.19–0.22 m/s beyond
    # the goal despite a 0.03 m/s PI reference. Residual authority must not
    # recover after the estimated along-path distance reaches zero.
    for remaining in (.05, 0.0, -.4):
        _, limited, _ = decode_control(action, config, path_remaining=remaining)
        np.testing.assert_allclose(limited, [0., 0.])
    assert config['goal_tolerance_m'] == .2


def test_goal_residual_guard_is_opt_in_and_requires_estimated_geometry():
    old = decode_control([0.4, 0.4, 0.1], CONFIG)
    with_distance = decode_control([0.4, 0.4, 0.1], CONFIG, path_remaining=0.0)
    np.testing.assert_array_equal(old[1], with_distance[1])
    guarded = {**CONFIG, 'navigation': {**CONFIG['navigation'],
                                      'goal_residual_fade_distance_m': .5}}
    for distance in (None, float('nan')):
        with pytest.raises(ValueError, match='path_remaining'):
            decode_control([0.4, 0.4, 0.1], guarded, path_remaining=distance)


@pytest.mark.parametrize('fade', [-.1, 0., .05, float('inf'), float('nan')])
def test_invalid_goal_residual_fade_is_rejected(fade):
    config = {**CONFIG, 'navigation': {**CONFIG['navigation'],
                                     'goal_stop_tolerance_m': .05,
                                     'goal_residual_fade_distance_m': fade}}
    with pytest.raises(ValueError, match='goal_residual_fade_distance_m'):
        decode_control([0.4, 0.4, 0.1], config, path_remaining=.3)


def test_nominal_approach_allows_initial_policy_to_finish_before_target():
    # Kinematic feasibility only: Gazebo validation covers dynamics/terrain.
    remaining = 6.0
    dt = 1. / CONFIG['control_hz']
    for step in range(round(CONFIG['target_finish_seconds'] / dt)):
        remaining -= CONFIG['ppo']['initial_speed_scale'] * approach_speed(
            remaining, remaining, 0., CONFIG) * dt
        if remaining <= CONFIG['goal_tolerance_m']:
            break
    assert remaining <= CONFIG['goal_tolerance_m']


def progress(before, after):
    # Path projection is clamped at 6 m in both cases; endpoint distance isn't.
    _, terms = compute_reward(TrackingState(6., 0., 0., 0., before),
        TrackingState(6., 0., 0., 0., after), RobotState(), BASELINE_ACTION,
        BASELINE_ACTION, [0., 0.], .1, {'impact_integral': 0.},
        {**CONFIG['reward_v2'], 'torque_scale_nm': 2.})
    return terms['progress']


def test_endpoint_reward_penalizes_leaving_goal_and_rewards_approaching():
    assert progress(.2, .3) < 0.
    assert progress(.3, .2) > 0.
    assert progress(.2, .3) + progress(.3, .2) == pytest.approx(0.)


def test_chassis_passing_over_tiny_bump_does_not_count_as_wheel_challenge():
    center_bump = ChallengeRegion('center', 'bump', 2., 0., .12)
    tracker = ChallengeTracker([center_bump], wheel_separation=.34273666)
    for x in np.linspace(1.5, 2.6, 50):
        tracker.update((x-.03, 0.), (x, 0.))
    assert not tracker.chosen and not tracker.cleared
    wheel_bump = ChallengeRegion('left', 'bump', 2., .34273666/2, .12)
    tracker = ChallengeTracker([wheel_bump], wheel_separation=.34273666)
    for x in np.linspace(1.5, 2.6, 50):
        tracker.update((x-.03, 0.), (x, 0.))
    assert tracker.chosen == tracker.cleared == {'left'}
