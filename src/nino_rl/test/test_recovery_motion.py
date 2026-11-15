import math
from dataclasses import replace

import pytest

from nino_control.residual_velocity import ReferenceLimits
from nino_rl.recovery_contract import AcceptedCommonReference
from nino_rl.recovery_motion import MotionEvaluator, MotionTarget
from nino_rl.recovery_terrain import ConnectedRamp
from nino_rl.unknown_step_runtime import RewardSettings, UnknownTaskData
from nino_rl.recovery_task import RecoveryReward, RecoveryScore, RecoveryBands
from nino_rl.recovery_bank import configuration
from nino_rl.recovery_contract import StartBudget
from test_unknown_step_runtime import sample, settings


FLAGS = dict(permission=True, sensors_fresh=True, history_ready=True,
             command_age_s=0., emergency_stop=False, fault=False)


def test_constant_negative_residual_cannot_accumulate_or_reverse_forward_baseline():
    reference = AcceptedCommonReference(ReferenceLimits(.34, .6, .4, 1., .1, .04, .2))
    for _ in range(100):
        trace = reference.compose((.2, 0.), (-.5, 0.), .1, 1., **FLAGS)
        baseline = trace['shaped_baseline_wheel_m_s']
        accepted = trace['accepted_reference_wheel_m_s']
        assert accepted[0] >= 0.
        assert max(abs(a-b) for a,b in zip(accepted, baseline)) <= .02000001
    assert trace['body_reference'][0] == pytest.approx(.18)


def test_policy_does_not_change_independent_baseline_trace():
    limits = ReferenceLimits(.34, .6, .4, 1., .1, .04, .2)
    negative, positive = AcceptedCommonReference(limits), AcceptedCommonReference(limits)
    for _ in range(100):
        a = negative.compose((.2, .02), (-.5, 0.), .1, 1., **FLAGS)
        b = positive.compose((.2, .02), (.5, 0.), .1, 1., **FLAGS)
        assert a['shaped_baseline_wheel_m_s'] == b['shaped_baseline_wheel_m_s']


def metric(previous, current, target=MotionTarget(.2, 0.), ramp=None):
    return MotionEvaluator((1.,0.), settings().envelope_m, ramp).update(previous, current, target)


def test_changing_accepted_reference_cannot_change_target_speed_error():
    previous = sample()
    moving = sample(.1, .01, body_speed_norm_m_s=.1, accepted_reference_m_s=(.1,.1))
    a = metric(previous, moving)
    b = metric(previous, replace(moving, accepted_reference_m_s=(.2,.2)))
    assert a == b
    assert a['target_speed_error_m_s'] == pytest.approx(-.1)
    stopped = metric(previous, sample(.1), target=MotionTarget(.2, 0.))
    assert stopped['target_speed_error_m_s'] == pytest.approx(-.2)


def test_reverse_and_bounce_cannot_masquerade_as_forward_surface_speed():
    backward = metric(sample(), sample(.1, -.02, body_speed_norm_m_s=.2))
    assert backward['truth_surface_velocity_fd_m_s'] == pytest.approx(-.2)
    assert backward['target_speed_error_m_s'] == pytest.approx(-.4)
    bouncing = sample(.1, 0., pose_m_rad=(0.,0.,.12,0.,0.,0.), body_speed_norm_m_s=.2)
    assert metric(sample(), bouncing)['truth_surface_velocity_fd_m_s'] == 0.


@pytest.mark.parametrize('x', [1.3,2.2])
def test_steady_grade_speed_and_macro_attitude_are_not_disturbances(x):
    ramp = ConnectedRamp(1., .6, .3, math.radians(5.))
    gradient = ramp.slope(x)
    v = .2
    step = v*.1/math.sqrt(1+gradient**2)
    previous = sample(0., x-step, pose_m_rad=(x-step,0.,.1+ramp.height(x-step),0.,0.,0.))
    chord = (ramp.height(x+.3)-ramp.height(x-.3))/.6
    current = sample(.1, x, pose_m_rad=(x,0.,.1+ramp.height(x),0.,-math.atan(chord),0.))
    result = metric(previous, current, ramp=ramp)
    assert result['target_speed_error_m_s'] == pytest.approx(0.,abs=1e-10)
    assert result['road_relative_tilt_rad'] < 2e-8
    disturbed = replace(current, pose_m_rad=(*current.pose_m_rad[:3], .1, current.pose_m_rad[4], 0.))
    assert metric(previous, disturbed, ramp=ramp)['road_relative_tilt_rad'] > .099


def test_quiet_goal_does_not_dilute_moving_speed_quality():
    evaluator = MotionEvaluator((1.,0.), settings().envelope_m)
    first = evaluator.update(sample(), sample(.1, .01), MotionTarget(.2,0.))
    for i in range(2,22):
        result = evaluator.update(sample((i-1)*.1,.01), sample(i*.1,.01), MotionTarget(0.,0.))
    assert result['moving_target_speed_rmse_m_s'] == first['moving_target_speed_rmse_m_s']
    assert result['moving_measured_duration_s'] == pytest.approx(.1)


def test_speed_penalty_rewards_target_tracking_and_rejects_missing_labels():
    weights = RewardSettings(1., .1, .1, .02, .01, .001, 5., 10., .05, .5)
    outcome = dict(measurement_valid=True, elapsed_s=.1, goal_distance_m=1.9,
                   cross_track_m=0., heading_error_rad=0., terminated=False, task_success=False,
                   stability_cost=0., clearance_events=0, recovery_events=0)
    slow = RecoveryReward(weights,2.,0.,.2,.01)
    exact = RecoveryReward(weights,2.,0.,.2,.01)
    with pytest.raises(UnknownTaskData, match='motion reward'):
        slow.update(outcome,0.)
    a, at = slow.update(dict(outcome,target_speed_error_m_s=-.1),0.)
    b, bt = exact.update(dict(outcome,target_speed_error_m_s=0.),0.)
    assert at['target_speed'] == pytest.approx(-.04)
    assert bt['target_speed'] == 0. and b > a
    assert a == pytest.approx(sum(at.values()))


def test_motion_quality_is_required_for_success_even_when_goal_is_reached():
    config = configuration()
    scorer = RecoveryScore(settings(obstacle_near_m=None,obstacle_far_m=None), [],
                           RecoveryBands(**config['recovery_bands']), StartBudget(**config['start_budget']),
                           motion_quality=config['motion_quality'])
    scorer.reset(sample())
    scorer.update(sample(.1,2.), MotionTarget(.2,0.))
    scorer.update(sample(.2,2.), MotionTarget(0.,0.))
    result = scorer.update(sample(.3,2.), MotionTarget(0.,0.))
    assert result['terminated'] and not result['task_success']
    assert result['termination_reason'] == 'motion_quality_violation'


def test_cruise_setting_is_consumed_by_follower_and_backend():
    from nino_rl.recovery_runner import runtime_configuration
    c = configuration()
    c['cruise_m_s'] = .15
    controller, guidance, _, _ = runtime_configuration(c, dict(initial_pose_xy_yaw=[0.,0.,0.]))
    assert controller['backend']['cruise_m_s'] == guidance['navigation']['straight_speed_m_s'] == .15


def test_reset_removes_independent_baseline_and_residual_history():
    reference = AcceptedCommonReference(ReferenceLimits(.34, .6, .4, 1., .1, .04, .2))
    for _ in range(50):
        reference.compose((.2,0.),(.5,0.),.1,1.,**FLAGS)
    reference.reset()
    trace = reference.compose((0.,0.),(.5,0.),.1,1.,**FLAGS)
    assert trace['body_reference'] == trace['shaped_baseline_wheel_m_s'] == (0.,0.)


def test_baseline_direction_reversal_keeps_slew_and_reports_transient():
    reference = AcceptedCommonReference(ReferenceLimits(.34, .6, .4, 1., .1, .04, .2))
    for _ in range(30):
        reference.compose((-.2,0.),(-.5,0.),.1,1.,**FLAGS)
    transients = 0
    for _ in range(100):
        previous = reference.previous
        trace = reference.compose((.2,0.),(-.5,0.),.1,1.,**FLAGS)
        assert max(abs(a-b) for a,b in zip(previous,reference.previous)) <= .01000001
        transients += trace['direction_transition_due_to_slew']
    assert transients and not reference.latched
    assert trace['body_reference'][0] == pytest.approx(.18)


def test_projection_retains_boolean_health_validation_and_optional_history_default():
    limits = ReferenceLimits(.34, .6, .4, 1., .1, .04, .2)
    reference = AcceptedCommonReference(limits)
    trace = reference.compose((.2,0.),(.5,0.),.1,1.,**dict(FLAGS,fault=0))
    assert reference.latched and trace['body_reference'] == (0.,0.)
    reference.reset()
    flags = {k:v for k,v in FLAGS.items() if k != 'history_ready'}
    trace = reference.compose((.2,0.),(.5,0.),.1,1.,**flags)
    assert not reference.latched
    assert trace['accepted_policy_delta_wheel_m_s'] == (0.,0.)


def test_terrain_metadata_changes_labels_but_not_actor_observations():
    from nino_rl.recovery_environment import RecoveryEnv
    from test_unknown_step_environment import ToyBackend
    from test_unknown_step_runtime import controller_config
    config = configuration()
    args = dict(task_settings=settings(obstacle_near_m=None,obstacle_far_m=None),
                reward_settings=RewardSettings(**config['task_reward']), obstacles=[],
                bands=RecoveryBands(**config['recovery_bands']), start_budget=StartBudget(**config['start_budget']),
                recovery_reward=config['recovery_reward'], motion_quality=config['motion_quality'])
    from dataclasses import asdict
    a = RecoveryEnv(controller_config(),ToyBackend(),**args)
    b = RecoveryEnv(controller_config(),ToyBackend(),macro_ramp=asdict(ConnectedRamp(1.,.2,.1,math.radians(3.))),**args)
    try:
        oa, _ = a.reset()
        ob, _ = b.reset()
        assert oa.tolist() == ob.tolist()
        for _ in range(5):
            ra, rb = a.step([.2]),b.step([.2])
            assert ra[0].tolist() == rb[0].tolist()
            assert ra[4]['replay_action'] == rb[4]['replay_action']
        with pytest.raises(ValueError,match='identity'):
            a.require_checkpoint(b.identity)
    finally:
        a.close()
        b.close()
