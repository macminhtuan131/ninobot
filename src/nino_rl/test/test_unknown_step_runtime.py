"""Synthetic software contracts only; numeric fixtures are not run acceptance."""
from copy import deepcopy
from dataclasses import replace
from itertools import product
import math

import numpy as np
import pytest

from nino_control.residual_velocity import FEATURES
from nino_rl.residual_guidance import PoseSample
from nino_rl.unknown_step_runtime import (
    CONTRACT_ID, EstimatedGoalReference, PhysicalSample, RewardSettings,
    SensorOnlyCommonAdapter, TaskSettings, TraversalReward, TraversalScore,
    UnknownTaskData,
)


def settings(**changes):
    # An invented fixture box, NOT measured Nino geometry or accepted thresholds.
    c = TaskSettings(route_m=((0., 0.), (2., 0.)),
                     envelope_m=tuple(product((-.30, .30), (-.20, .20), (-.05, .20))),
                     envelope_identity='synthetic_fixture_not_robot_geometry',
                     obstacle_near_m=.60, obstacle_far_m=.61, clearance_m=.01,
                     interval_s=.1, maximum_source_age_s=.04, maximum_seconds=10., goal_tolerance_m=.05,
                     goal_heading_tolerance_rad=.2, maximum_cross_track_m=.1,
                     continuous_stop_s=.2, stop_body_speed_m_s=.01,
                     stop_yaw_rad_s=.05, stop_wheel_rad_s=.15,
                     stop_reference_m_s=1e-6, stall_window_s=.5, stall_progress_m=.01,
                     maximum_tilt_rad=.7, minimum_body_z_m=-.15)
    return replace(c, **changes)


def sample(t=0., x=0., **changes):
    return replace(PhysicalSample(stamp_s=t, decision_stamp_s=t, pose_m_rad=(x, 0., .1, 0., 0., 0.),
                                  body_speed_norm_m_s=0., body_yaw_rad_s=0.,
                                  wheel_rad_s=(0., 0.), accepted_reference_m_s=(0., 0.),
                                  motion_requested=False, owner_intervention=False,
                                  drive_fault=False), **changes)


def controller_config():
    return dict(actor=dict(history_frames=5, max_history_gap_s=.15, privileged_inputs=False),
                control_interval_s=.1,
                nominal_geometry=dict(radius_l=.0625, radius_r=.0625, separation=.34273666),
                reference_limits=dict(separation_m=.34273666, wheel_speed_m_s=.4,
                                      forward_m_s=.4, yaw_rad_s=.5,
                                      wheel_acceleration_m_s2=.1, residual_wheel_m_s=.04,
                                      max_age_s=.2))


def view(t, baseline=(.2, 0.)):
    f = {k: 0. for k in FEATURES[:18]}
    f.update(baseline_v_m_s=baseline[0], baseline_yaw_rad_s=baseline[1], accel_z_m_s2=9.80665)
    return dict(features=f, baseline=baseline, stamp_s=t, command_age_s=0.,
                permission=True, sensors_fresh=True, fault=False, emergency_stop=False)


def guidance_config():
    return dict(schema_version=1, baseline_id='unknown_step_fixture',
                pose_source='wheel_imu_odometry', pose_frame_id='odom',
                command_frame_id='base_footprint', clock_id='sim',
                allow_sim_truth_oracle=False, maximum_pose_age_s=.2,
                maximum_corridor_error_m=.4, maximum_goal_overshoot_m=.1,
                path_points_m=[[0., 0.], [2., 0.]], goal_tolerance_m=.05,
                goal_heading_tolerance_deg=15.,
                navigation=dict(straight_speed_m_s=.2, minimum_approach_speed_m_s=.03,
                                goal_stop_tolerance_m=.03, goal_slowdown_distance_m=.4,
                                path_feedback=dict(enabled=True, lookahead_m=.45,
                                                   max_yaw_rate_rad_s=.5,
                                                   residual_fade_distance_m=1.)))


def test_full_robot_clearance_is_not_center_or_drive_axle_clearance():
    s = TraversalScore(settings())
    s.reset(sample())
    r = s.update(sample(.1, .8))
    assert r['progress_m'] > .61 and r['rear_support_m'] == pytest.approx(.5)
    assert not r['whole_robot_clear'] and not r['task_success']
    r = s.update(sample(.2, 1.))
    assert r['whole_robot_clear'] and not r['task_success']


def test_arrival_requires_whole_geometry_and_continuous_actual_stop():
    s = TraversalScore(settings())
    s.reset(sample())
    r = s.update(sample(.1, 2., body_speed_norm_m_s=.05))
    assert r['at_physical_goal'] and not r['quiet_now']
    assert s.update(sample(.2, 2.))['continuous_quiet_s'] == 0.
    assert not s.update(sample(.3, 2.))['terminated']
    r = s.update(sample(.4, 2.))
    assert r['task_success'] and r['terminated'] and not r['truncated']
    with pytest.raises(RuntimeError):
        s.update(sample(.5, 2.))


def test_goal_before_rear_clearance_cannot_succeed():
    c = settings(route_m=((0., 0.), (.8, 0.)))
    s = TraversalScore(c)
    s.reset(sample())
    for n in range(1, 5):
        r = s.update(sample(n * .1, .8))
        assert r['at_physical_goal'] and not r['whole_robot_clear'] and not r['task_success']


def test_quiet_timer_resets_on_motion_reference_or_goal_departure():
    s = TraversalScore(settings())
    s.reset(sample())
    s.update(sample(.1, 2.))
    s.update(sample(.2, 2., accepted_reference_m_s=(.01, .01)))
    assert s.update(sample(.3, 2.))['continuous_quiet_s'] == 0.
    assert not s.update(sample(.4, 2.))['task_success']
    assert s.update(sample(.5, 2.))['task_success']


def test_stationary_robot_does_not_succeed_merely_because_encoder_or_estimator_says_arrival():
    s = TraversalScore(settings())
    s.reset(sample())
    for n in range(1, 7):
        r = s.update(sample(n * .1, 0., motion_requested=True))
    assert r['termination_reason'] == 'stall' and not r['task_success']


@pytest.mark.parametrize('change,reason', [
    (dict(owner_intervention=True), 'owner_intervention'),
    (dict(drive_fault=True), 'drive_fault'),
    (dict(pose_m_rad=(0., .2, .1, 0., 0., 0.)), 'path_violation'),
    (dict(pose_m_rad=(0., 0., .1, .8, 0., 0.)), 'physical_envelope_failure'),
])
def test_explicit_failures_remain_terminal_outcomes(change, reason):
    s = TraversalScore(settings())
    s.reset(sample())
    r = s.update(sample(.1, **change))
    assert r['terminated'] and not r['task_success'] and r['termination_reason'] == reason


@pytest.mark.parametrize('bad', [sample(.2), sample(0.), sample(-.1),
                                 sample(.1, wheel_rad_s=(float('nan'), 0.)),
                                 sample(.1, wheel_rad_s=None),
                                 sample(.1, accepted_reference_m_s=None),
                                 sample(.1, pose_m_rad=None)])
def test_missing_or_invalid_measurements_are_unknown_not_zero_or_failure(bad):
    s = TraversalScore(settings())
    s.reset(sample())
    with pytest.raises(UnknownTaskData):
        s.update(bad)
    assert not s.done and s.count == 0


def test_clear_floor_needs_goal_and_timeout_is_explicit_finite_task_failure():
    s = TraversalScore(settings(obstacle_near_m=None, obstacle_far_m=None, maximum_seconds=1.))
    s.reset(sample())
    for n in range(1, 11):
        r = s.update(sample(n * .1))
    assert r['whole_robot_clear'] and not r['task_success']
    assert r['termination_reason'] == 'task_timeout' and not r['truncated']


def test_truth_headers_keep_their_actual_ages_and_do_not_become_decision_stamps():
    s = TraversalScore(settings())
    s.reset(sample())
    r = s.update(sample(.09, .1, decision_stamp_s=.1))
    assert r['truth_source_stamp_s'] == .09 and r['decision_stamp_s'] == .1
    r = s.update(sample(.18, .2, decision_stamp_s=.2))
    assert r['measured_elapsed_s'] == pytest.approx(.18)
    with pytest.raises(UnknownTaskData):
        s.update(sample(.25, .3, decision_stamp_s=.3))


def test_footprint_rotates_with_route_heading_and_body_tilt():
    s = TraversalScore(settings(route_m=((0., 0.), (0., 2.))))
    p = sample(pose_m_rad=(0., 0., .1, 0., 0., math.pi / 2))
    assert s.reset(p)['front_support_m'] == pytest.approx(.3)
    tilted = replace(p, pose_m_rad=(0., 0., .1, 0., .4, math.pi / 2))
    assert s.geometry(tilted)['front_support_m'] > .3


@pytest.mark.parametrize('change', [dict(envelope_m=((0., 0., 0.),)),
                                   dict(envelope_identity=''), dict(goal_tolerance_m=float('nan')),
                                   dict(obstacle_near_m=None), dict(interval_s=0.)])
def test_unresolved_or_invalid_contract_is_rejected(change):
    with pytest.raises(ValueError):
        settings(**change)


def test_history_has_no_stop_schedule_or_metadata_and_preserves_requested_action():
    a, b = SensorOnlyCommonAdapter(controller_config()), SensorOnlyCommonAdapter(controller_config())
    for n in range(30):
        v = view(n * .1)
        altered = deepcopy(v)
        altered.update(obstacle_x_m=123., truth_pose=[99., 0., 0.], time_to_stop_s=-99., layout_seed=77)
        np.testing.assert_array_equal(a.observe(v), b.observe(altered))
        assert a.pipeline.observation == b.pipeline.observation
        ta, tb = a.project([1.]), b.project([1.])
        assert ta == tb
    assert len(a.pipeline.observation) == 100
    assert ta['requested_scalar_action'] == ta['replay_action'] == [1.]
    assert ta['inherited_proposal'] == [.5, 0.]
    assert ta['requested_common_m_s'] == .02
    assert abs(ta['accepted_common_normalized']) <= 1.
    assert ta['task_contract_id'] == CONTRACT_ID and not a.identity['planned_stop_features']


def test_zero_baseline_cannot_start_robot_and_stale_permission_latches_zero():
    a = SensorOnlyCommonAdapter(controller_config())
    for n in range(5):
        a.observe(view(n * .1, baseline=(0., 0.)))
        trace = a.project([1.])
    assert trace['body_reference'] == (0., 0.)
    assert trace['accepted_common_normalized'] == 0.
    v = view(.5)
    v['sensors_fresh'] = False
    a.observe(v)
    trace = a.project([1.])
    assert trace['body_reference'] == (0., 0.) and a.pipeline.reference.latched


def test_feature_injection_bad_action_sequence_and_old_checkpoint_are_rejected():
    a = SensorOnlyCommonAdapter(controller_config())
    v = view(0.)
    v['features']['time_to_contact_s'] = 1.
    with pytest.raises(ValueError):
        a.observe(v)
    a.observe(view(0.))
    with pytest.raises(RuntimeError):
        a.observe(view(.1))
    with pytest.raises(ValueError):
        a.project([1., 0.])
    a.project([0.])
    with pytest.raises(ValueError, match='ABI'):
        a.require_checkpoint(dict(engine='common103_v2'))
    a.require_checkpoint(deepcopy(a.identity))


def test_estimator_only_follower_has_no_fixed_six_or_eight_second_stop():
    g = EstimatedGoalReference(guidance_config(), epoch='fixture')
    for t in (0., 6., 8., 12.):
        g.update_pose(PoseSample(.5, 0., 0., t, t, 'odom', 'wheel_imu_odometry', 'sim', 'fixture'))
        r = g.command(t, permission=True)
        assert r['valid'] and r['reference'][0] > 0 and not g.stopped
    g.update_pose(PoseSample(2., 0., 0., 13., 13., 'odom', 'wheel_imu_odometry', 'sim', 'fixture'))
    r = g.command(13., permission=True)
    assert r['valid'] and r['reference'] == [0., 0.] and g.stopped
    g.update_pose(PoseSample(1.9, 0., 0., 13.1, 13.1, 'odom', 'wheel_imu_odometry', 'sim', 'fixture'))
    r = g.command(13.1, permission=True)
    assert r['valid'] and r['permission'] and not r['fault'] and r['reference'] == [0., 0.]
    r = g.command(14., permission=True)
    assert not r['valid'] and r['fault'] and r['reference'] == [0., 0.]


def test_truth_cannot_be_selected_as_goal_follower_source():
    c = guidance_config()
    c.update(pose_source='sim_truth_oracle', allow_sim_truth_oracle=True)
    with pytest.raises(ValueError, match='Truth'):
        EstimatedGoalReference(c, epoch='fixture')


def test_new_reward_rewards_goal_progress_and_never_charges_unapplied_request():
    c = RewardSettings(progress=1., cross_track=.1, heading=.1, time=.01,
                       accepted_action=.01, accepted_action_change=.001,
                       success=2., failure=3., cross_scale_m=.1, heading_scale_rad=.2)
    reward = TraversalReward(c, 2.)
    s = TraversalScore(settings())
    s.reset(sample())
    r = s.update(sample(.1, .1))
    value, terms = reward.update(r, 0.)  # Requested action can be nonzero; only accepted correction is penalized.
    assert terms['progress'] == pytest.approx(.1) and value > 0.
    assert terms['accepted_action'] == terms['accepted_action_change'] == 0.
    s = TraversalScore(settings())
    s.reset(sample())
    failure = s.update(sample(.1, drive_fault=True))
    reward = TraversalReward(c, 2.)
    _, terms = reward.update(failure, 0.)
    assert terms['outcome'] == -3.
    with pytest.raises(UnknownTaskData):
        TraversalReward(c, 2.).update(dict(measurement_valid=False), 0.)
