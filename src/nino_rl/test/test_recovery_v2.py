from copy import deepcopy
from dataclasses import replace
import math

import numpy as np
import pytest

from nino_control.residual_velocity import ReferenceLimits, wheels_to_body
from nino_rl.recovery_bank import configuration, sample_layout, write_world
from nino_rl.recovery_contract import AcceptedCommonReference, StartBudget, RecoveryAdapter
from nino_rl.recovery_curriculum import FAMILIES, FamilyCurriculum
from nino_rl.recovery_task import RecoveryBands, RecoveryScore, RecoveryReward
from nino_rl.unknown_step_runtime import UnknownTaskData, RewardSettings
from test_unknown_step_runtime import controller_config, sample, settings, view


def scorer(**changes):
    c = configuration()
    task = settings(obstacle_near_m=None, obstacle_far_m=None, maximum_cross_track_m=.3, **changes)
    budget = StartBudget(.05, .03, .005, .005, .008, .03)
    heading = math.atan2(task.route_m[1][1], task.route_m[1][0])
    return RecoveryScore(task, [dict(id='o1', near_m=.5, far_m=.6)],
                         RecoveryBands(**c['recovery_bands']), budget, (0.,0.,heading))


def point(t, x, y=0., yaw=0., **kwargs):
    p = sample(t, x, **kwargs)
    pose = list(p.pose_m_rad)
    pose[1], pose[5] = y, yaw
    return replace(p, pose_m_rad=tuple(pose))


def test_start_error_that_exhausts_goal_margin_is_rejected():
    s = scorer()
    with pytest.raises(UnknownTaskData, match='start budget'):
        s.reset(point(0., -.03774782188))
    with pytest.raises(ValueError, match='cannot fit'):
        StartBudget(.05, .03, .005, .005, .05, .03)


def test_start_yaw_uncertainty_is_coupled_to_remaining_distance():
    budget = StartBudget(.05, .03, .005, .005, .008, .03)
    geometry = dict(progress_m=0., cross_track_m=0., heading_error_rad=.02)
    with pytest.raises(UnknownTaskData, match='start budget'):
        budget.check(geometry, remaining_path_m=4.)
    result = budget.check(geometry, declared_heading_rad=.02, remaining_path_m=4.)
    assert result['endpoint_error_bound_m'] == 0.
    from nino_rl.recovery_runner import runtime_configuration
    layout = sample_layout(configuration(), 'clean', 1511, 0)
    controller, _, task, _ = runtime_configuration(configuration(), layout)
    assert controller['backend']['initial_pose_xy_yaw'] == task['initial_pose_m_rad']


def test_clearance_is_not_recovery_and_one_frame_is_not_success():
    s = scorer()
    s.reset(point(0., 0.))
    first = s.update(point(.1, .4))
    assert first['recovery_states'][0]['phase'] == 'CROSSING'
    cleared = s.update(point(.2, 1., yaw=.3))
    assert cleared['whole_robot_clear'] and cleared['clearance_events'] == 1
    assert not cleared['all_obstacles_recovered']
    s.update(point(.3, 1.))
    broken = s.update(point(.4, 1., y=.08))
    assert broken['recovery_states'][0]['stable_since_s'] is None
    for i in range(5, 12):
        result = s.update(point(round(i*.1, 8), 1.))
    assert result['all_obstacles_recovered'] and result['recovery_events'] == 1
    assert result['recovery_states'][0]['recovery_time_s'] == pytest.approx(.9)
    result = s.update(point(1.2, .4))
    assert result['clearance_events'] == result['recovery_events'] == 0
    assert not result['whole_robot_clear']
    assert not result['all_obstacles_recovered']
    assert result['recovery_states'][0]['phase'] == 'RECOVERY'
    for i in range(13, 20):
        result = s.update(point(round(i*.1,8), 1.))
        assert result['recovery_events'] == 0
    assert result['all_obstacles_recovered']


def test_backout_never_clears_and_timeout_is_not_recovered():
    s = scorer(maximum_seconds=10.)
    s.reset(point(0., 0.))
    s.update(point(.1, .4))
    assert s.update(point(.2, 0.))['crossing_count'] == 0
    s.update(point(.3, 1., y=.1))
    for i in range(4, 54):
        r = s.update(point(round(i*.1, 8), 1., y=.1))
        if r['terminated']:
            break
    assert r['termination_reason'] == 'recovery_timeout'
    assert not r['task_success']


def test_reverse_motion_matching_speed_norm_is_not_forward_recovery():
    s = scorer(stall_window_s=4.)
    s.reset(point(0., 0.))
    for i in range(1, 8):
        r = s.update(point(round(i*.1,8), 1.2-.02*(i-1),
                           body_speed_norm_m_s=.2, accepted_reference_m_s=(.2,.2)))
    assert r['whole_robot_clear'] and not r['all_obstacles_recovered']
    assert r['truth_forward_velocity_fd_m_s'] == pytest.approx(-.2)


def test_prepared_bank_detects_changed_scorer_metadata(tmp_path):
    import hashlib
    import json
    from nino_rl.recovery_runner import require_bank, sources
    from nino_rl.recovery_bank import CONFIG
    inputs = tmp_path/'inputs'
    inputs.mkdir()
    bank = dict(config=configuration(), config_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(), layouts=[])
    (inputs/'bank.json').write_text(json.dumps(bank))
    (inputs/'source_pins.json').write_text(json.dumps(sources()))
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    (inputs/'manifest.json').write_text(json.dumps(manifest))
    require_bank(tmp_path)
    bank['config']['recovery_reward']['recovery_bonus'] = 999.
    (inputs/'bank.json').write_text(json.dumps(bank))
    with pytest.raises(ValueError, match='manifest'):
        require_bank(tmp_path)


def test_mixed_requires_component_evidence_before_launch(tmp_path):
    from nino_rl.recovery_runner import require_components
    require_components(tmp_path, 'clean')
    with pytest.raises(ValueError, match='qualified component'):
        require_components(tmp_path, 'mixed')


def test_reset_discards_previous_success_and_failure_state():
    s = scorer()
    s.reset(point(0., 0.))
    s.update(point(.1, .4))
    s.update(point(.2, 1.))
    s.reset(point(0., 0.))
    assert s.phases[0]['phase'] == 'APPROACH' and not s.post_rows


@pytest.mark.parametrize('angle', [0., math.pi/2, math.pi, -math.pi/2])
def test_physical_recovery_is_rotation_invariant(angle):
    route = ((0.,0.), (2.*math.cos(angle), 2.*math.sin(angle)))
    s = scorer(route_m=route)
    def rotated(t, distance):
        return point(t, distance*math.cos(angle), distance*math.sin(angle), angle)
    s.reset(rotated(0., 0.))
    for i in range(1, 9):
        result = s.update(rotated(round(i*.1, 8), 1.))
    assert result['whole_robot_clear'] and result['all_obstacles_recovered']


def test_recovery_reward_is_once_only_and_failure_takes_precedence():
    s = scorer()
    weights = RewardSettings(1., .1, .1, .02, .01, .001, 5., 10., .05, .5)
    reward = RecoveryReward(weights, 2., 0., .2, .01)
    s.reset(point(0.,0.))
    bonuses = []
    for i in range(1, 12):
        r = s.update(point(round(i*.1,8), 1.))
        value, terms = reward.update(r, 0.)
        assert value == pytest.approx(sum(terms.values()))
        bonuses.append(terms['recovery'])
    assert sum(bonuses) == pytest.approx(.2)
    s.reset(point(0.,0.))
    for i in range(1, 6):
        s.update(point(round(i*.1,8), 1.))
    r = s.update(point(.6, 1., drive_fault=True))
    assert r['termination_reason'] == 'drive_fault' and r['recovery_events'] == 0
    fresh = RecoveryReward(weights, 2., 1., .2, .01)
    r.update(elapsed_s=.1, clearance_events=1, recovery_events=1,
             termination_reason='reference_intervention')
    _, terms = fresh.update(r, 0.)
    assert terms['clearance'] == terms['recovery'] == 0.


def test_accepted_common_never_changes_baseline_yaw():
    limits = ReferenceLimits(.34273666, .6, .4, 1., .1, .04, .2)
    r = AcceptedCommonReference(limits)
    r.previous = (.2, .2)
    trace = r.compose((.2, .06), (-.5, 0.), .1, 1., permission=True,
                      sensors_fresh=True, history_ready=True, command_age_s=0.,
                      emergency_stop=False, fault=False)
    base_yaw = wheels_to_body(*trace['shaped_baseline_wheel_m_s'], limits.separation_m)[1]
    assert trace['body_reference'][1] == pytest.approx(base_yaw)
    dl, dr = trace['accepted_policy_delta_wheel_m_s']
    assert dl == dr
    assert max(abs(a-b) for a, b in zip(trace['accepted_reference_wheel_m_s'], (.2,.2))) <= .010000001


def test_scalar_projection_fuzz_respects_speed_yaw_slew_stop_and_owner():
    rng = np.random.default_rng(113)
    c = ReferenceLimits(.34, .5, .3, .7, .4, .04, .2)
    r = AcceptedCommonReference(c)
    flags = dict(permission=True, sensors_fresh=True, history_ready=True, command_age_s=0.,
                 emergency_stop=False, fault=False)
    for _ in range(1000):
        before = r.previous
        trace = r.compose(tuple(rng.uniform([-.4,-1.], [.4,1.])), (rng.uniform(-1,1),0.), .1, 1., **flags)
        wheels = trace['accepted_reference_wheel_m_s']
        assert max(map(abs, wheels)) <= c.wheel_speed_m_s+1e-8
        assert abs(trace['body_reference'][0]) <= c.forward_m_s+1e-8
        assert abs(trace['body_reference'][1]) <= c.yaw_rad_s+1e-8
        assert max(abs(a-b) for a,b in zip(wheels,before)) <= .04000001
        assert trace['accepted_policy_delta_wheel_m_s'][0] == trace['accepted_policy_delta_wheel_m_s'][1]
    assert r.compose((0.,0.), (1.,0.), .1, 1., **flags)['accepted_policy_delta_wheel_m_s'] == (0.,0.)
    flags['permission'] = False
    assert r.compose((.2,0.), (1.,0.), .1, 1., **flags)['body_reference'] == (0.,0.)
    assert r.latched


def test_new_adapter_rejects_old_identity_and_oracle_features():
    from nino_rl.unknown_step_runtime import SensorOnlyCommonAdapter
    config = controller_config()
    new = RecoveryAdapter(config)
    with pytest.raises(ValueError):
        new.require_checkpoint(SensorOnlyCommonAdapter(config).identity)
    bad = view(0.)
    bad['features']['obstacle_x'] = 1.
    with pytest.raises(ValueError, match='sensor/command'):
        new.observe(bad)
    for i in range(5):
        obs = new.observe(view(i*.1))
        trace = new.project([1.])
    assert obs.shape == (100,) and trace['replay_action'] == [1.]
    assert trace['task_contract_id'].endswith('v2')


def test_four_families_sample_distinct_physical_geometry_reproducibly():
    config = configuration()
    layouts = {f: sample_layout(config, f, 11, 2) for f in FAMILIES}
    assert not layouts['clean']['obstacles']
    assert {r['kind'] for r in layouts['short_obstacle']['obstacles']} == {'cable'}
    assert {r['kind'] for r in layouts['pothole']['obstacles']} == {'pothole'}
    assert {r['kind'] for r in layouts['mixed']['obstacles']} == {'cable','pothole'}
    assert layouts['mixed'] == sample_layout(config, 'mixed', 11, 2)
    assert layouts['mixed']['id'] != sample_layout(config, 'mixed', 11, 2, 'test')['id']
    assert all(not r['metadata_actor_input'] for r in layouts.values())


def test_pothole_world_has_negative_mesh_and_no_supporting_box(tmp_path):
    import xml.etree.ElementTree as ET
    source = tmp_path/'source.sdf'
    source.write_text('<sdf><world name="test"><model name="controlled_box_floor"/></world></sdf>')
    target = tmp_path/'hole.sdf'
    layout = sample_layout(configuration(), 'pothole', 11, 0)
    meshes = write_world(source, target, layout, tmp_path/'meshes')
    tree = ET.parse(target)
    assert tree.find('.//model[@name="controlled_box_floor"]') is None
    assert tree.find('.//collision/geometry/mesh/uri') is not None
    vertices = []
    import struct
    data = __import__('pathlib').Path(meshes[0]).read_bytes()
    for offset in range(84, len(data), 50):
        row = struct.unpack_from('<12fH', data, offset)
        vertices.extend(row[i] for i in (5, 8, 11))
    assert min(vertices) < 0 and max(vertices) == 0.


def test_curricula_are_independent_restore_rng_and_require_full_success():
    c = configuration()['curriculum']
    a, b = (FamilyCurriculum(f, 11, c) for f in FAMILIES[:2])
    good = dict(measurement_valid=True, task_success=True, all_obstacles_recovered=True,
                terminated=True, truncated=False)
    for i in range(c['minimum_episodes']):
        a.record(str(i), 0, good)
    assert a.stage == 1 and b.stage == 0 and not b.results
    clone = FamilyCurriculum('clean', 11, c)
    clone.restore(a.state())
    assert [a.sample_stage() for _ in range(30)] == [clone.sample_stage() for _ in range(30)]
    with pytest.raises(ValueError, match='already'):
        a.record('0', 1, good)
    for i in range(20):
        b.record(str(i), 0, dict(good, all_obstacles_recovered=False))
    assert b.stage == 0


def test_recovery_environment_keeps_oracle_out_of_history_and_versions_identity():
    from nino_rl.recovery_environment import RecoveryEnv
    from test_unknown_step_environment import ToyBackend
    c = configuration()
    reward = RewardSettings(1., .1, .1, .02, .01, .001, 5., 10., .05, .5)
    task = settings(obstacle_near_m=None, obstacle_far_m=None)
    budget = StartBudget(.05, .03, .005, .005, .008, .03)
    args = (controller_config(), ToyBackend(), task, reward, [],
            RecoveryBands(**c['recovery_bands']), budget, c['recovery_reward'])
    a = RecoveryEnv(*args)
    b = RecoveryEnv(controller_config(), ToyBackend(), task, reward,
                    [dict(id='hidden', near_m=.6, far_m=.61)],
                    RecoveryBands(**c['recovery_bands']), budget, c['recovery_reward'])
    try:
        oa, _ = a.reset(seed=11)
        ob, _ = b.reset(seed=11)
        np.testing.assert_array_equal(oa, ob)
        for _ in range(5):
            ra, rb = a.step([.1]), b.step([.1])
            np.testing.assert_array_equal(ra[0], rb[0])
            assert ra[4]['replay_action'] == rb[4]['replay_action']
        with pytest.raises(ValueError, match='identity'):
            a.require_checkpoint(b.identity)
    finally:
        a.close()
        b.close()
