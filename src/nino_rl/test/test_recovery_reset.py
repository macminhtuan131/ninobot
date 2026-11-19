from copy import deepcopy
import json
import sys
import threading
from types import SimpleNamespace

import pytest

from nino_rl import recovery_reset


def messages(t=1., pose=(0., 0., -.00001, 0.)):
    drive = dict(have_wheel_state=1., requested_linear_m_s=0., requested_yaw_rad_s=0.,
                 executed_linear_m_s=0., executed_yaw_rad_s=0., left_target_rad_s=0.,
                 right_target_rad_s=0.)
    truth = dict(pose=list(pose), speed_norm=.0001, yaw_rate=0., roll=0., pitch=0.)
    return {k: dict(stamp_s=t, values=v) for k, v in
            [('truth', truth), ('wheel', [0., 0.]), ('drive', drive)]}


def backend(tmp_path, monkeypatch, *, apply=True, post=None):
    b = SimpleNamespace(lock=threading.RLock(), request=(0., 0.), time=1., clock=1.,
                        messages=messages(), episode_dir=tmp_path, steps=[], waits=[], raw=[],
                        pose=[0., 0., -.00001, 0.], calls=[], pending=None)
    def command(owner, target, z):
        b.calls.append((list(target), z))
        if apply:
            b.pending = [target[0], target[1], z, target[2]]
    monkeypatch.setattr(recovery_reset, '_set_pose_once', command)
    def step(count):
        b.steps.append(count)
        b.time = b.clock = round(b.time+count*.001, 9)
        if b.pending is not None:
            b.pose = b.pending
            b.pending = None
        b.messages = messages(b.time, b.pose)
        if post is not None:
            post(b)
        for channel in ('wheel', 'imu'):
            b.raw.append(dict(channel=channel, stamp_s=b.time, values=[0., 0.]))
    b.step_world = step
    b._wait_feedback = lambda t: b.waits.append(t)
    return b


def test_challenge_and_return_anchor_at_verified_final_stamp_then_collect_prefix(tmp_path, monkeypatch):
    b = backend(tmp_path, monkeypatch)
    result = recovery_reset.reanchor(b, [0., 0., 0.])
    assert b.calls == [([.020, 0., 0.], -.00001), ([0., 0., 0.], -.00001)]
    assert b.steps == [20]*6 and b.waits == [1.02, 1.04, 1.06, 1.08, 1.10, 1.12]
    assert result['command_requests'] == 2
    assert result['source_epoch_s'] == 1.06
    assert result['observed_application_interval_s'] == [1.04, 1.06]
    assert result['prefix_end_time_s'] == 1.12
    assert result['prefix_counts'] == dict(wheel=3, imu=3)
    assert result['application_time_exact'] is False
    assert result['truth_input_to_actor'] is False
    assert result['declared_pose_m_rad'] == [0., 0., 0.]
    assert json.loads((tmp_path/'reanchor.json').read_text())['valid'] is True


def test_on_target_noop_ack_cannot_pass_the_challenge(tmp_path, monkeypatch):
    b = backend(tmp_path, monkeypatch, apply=False)
    with pytest.raises(ValueError, match='differs from declared target'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    report = json.loads((tmp_path/'reanchor.json').read_text())
    assert report['valid'] is False and report['command_requests'] == 1
    assert report['legs'][0]['command_accepted'] is True
    assert b.steps == [20]


def test_noop_return_after_real_challenge_is_rejected(tmp_path, monkeypatch):
    b = backend(tmp_path, monkeypatch)
    def command(owner, target, z):
        b.calls.append(target)
        if len(b.calls) == 1:
            b.pending = [target[0], target[1], z, target[2]]
    monkeypatch.setattr(recovery_reset, '_set_pose_once', command)
    with pytest.raises(ValueError, match='differs from declared target'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert b.steps == [20, 20, 20]


def test_late_application_and_pre_epoch_motion_do_not_move_verified_anchor(tmp_path, monkeypatch):
    def post(b):
        if len(b.steps) == 3:
            b.messages['truth']['stamp_s'] = 1.059
    b = backend(tmp_path, monkeypatch, post=post)
    b.raw = [dict(channel=k, stamp_s=t, values=[999., 999.])
             for k in ('wheel', 'imu') for t in (.1, .9, 1.058)]
    result = recovery_reset.reanchor(b, [0., 0., 0.])
    assert result['source_epoch_s'] == 1.059
    assert result['post_application_time_s'] == 1.06
    assert result['prefix_end_time_s'] == 1.12
    assert result['prefix_counts'] == dict(wheel=4, imu=4)
    assert result['declared_pose_m_rad'] == [0., 0., 0.]
    assert result['source_epoch_s'] > max(r['stamp_s'] for r in b.raw if r['values'][0] == 999.)


@pytest.mark.parametrize('mutation', ['stale', 'nonquiet', 'drive_ack', 'requested', 'nan'])
def test_unready_physical_state_cannot_issue_reset(tmp_path, monkeypatch, mutation):
    b = backend(tmp_path, monkeypatch)
    if mutation == 'stale':
        b.messages['wheel']['stamp_s'] = .9
    elif mutation == 'nonquiet':
        b.messages['truth']['values']['speed_norm'] = .1
    elif mutation == 'drive_ack':
        b.messages['drive']['values']['have_wheel_state'] = 0.
    elif mutation == 'requested':
        b.request = (.1, 0.)
    else:
        b.messages['truth']['values']['pose'][0] = float('nan')
    with pytest.raises(ValueError):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert b.calls == [] and b.steps == []
    assert json.loads((tmp_path/'reanchor.json').read_text())['valid'] is False


def test_fresh_truth_is_required_for_each_application(tmp_path, monkeypatch):
    def post(b):
        b.messages['truth']['stamp_s'] = 1.
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='fresh bounded'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert len(b.calls) == 1 and b.steps == [20]


def test_prefix_collection_rechecks_quiet(tmp_path, monkeypatch):
    def post(b):
        if len(b.steps) == 6:
            b.messages['truth']['values']['speed_norm'] = .1
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='physical quiet'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert len(b.calls) == 2 and b.steps == [20]*6


def test_prefix_requires_two_actual_gyro_samples_after_verified_epoch(tmp_path, monkeypatch):
    b = backend(tmp_path, monkeypatch)
    step = b.step_world
    def missing_gyro(count):
        step(count)
        b.raw = [r for r in b.raw if r['channel'] != 'imu' or r['stamp_s'] not in (1.08, 1.10)]
    b.step_world = missing_gyro
    with pytest.raises(ValueError, match='post-epoch support: imu'):
        recovery_reset.reanchor(b, [0., 0., 0.])



def test_pose_change_twist_is_retained_but_quiet_uses_the_next_fresh_interval(tmp_path, monkeypatch):
    def post(b):
        if len(b.steps) in (1, 3):
            b.messages['truth']['values']['speed_norm'] = 2.0623553794688028
    b = backend(tmp_path, monkeypatch, post=post)
    result = recovery_reset.reanchor(b, [0., 0., 0.])
    for leg in result['legs']:
        assert leg['verification']['observed_speed_norm_m_s'] == 2.0623553794688028
        assert leg['verification']['twist_quiet_verified'] is False
        assert leg['quiet_verification']['twist_quiet_verified'] is True
        assert leg['quiet_verification']['truth_stamp_s'] > leg['verification']['truth_stamp_s']
    assert result['source_epoch_s'] == 1.06
    assert result['post_reset_quiet']['truth_stamp_s'] == 1.08
    assert result['prefix_counts'] == dict(wheel=3, imu=3)
    assert b.steps == [20]*6 and len(b.calls) == 2



@pytest.mark.parametrize('mutation', ['moving_wheel', 'missing_zero_ack'])
def test_application_interval_still_requires_wheel_quiet_and_zero_ack(tmp_path, monkeypatch, mutation):
    def post(b):
        if len(b.steps) == 1:
            b.messages['truth']['values']['speed_norm'] = 2.0623553794688028
            if mutation == 'moving_wheel':
                b.messages['wheel']['values'][0] = .16
            else:
                b.messages['drive']['values']['requested_linear_m_s'] = .01
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='physical quiet and zero drive ACK'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert len(b.calls) == 1 and b.steps == [20]


@pytest.mark.parametrize('leg_step', [2, 4])
def test_real_motion_in_the_next_post_application_interval_is_rejected(tmp_path, monkeypatch, leg_step):
    def post(b):
        if len(b.steps) == leg_step:
            b.messages['truth']['values']['speed_norm'] = .0101
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='physical quiet'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert len(b.steps) == leg_step and len(b.calls) == leg_step//2
    assert json.loads((tmp_path/'reanchor.json').read_text())['valid'] is False


def test_post_application_quiet_requires_a_strictly_newer_truth_sample(tmp_path, monkeypatch):
    def post(b):
        if len(b.steps) == 2:
            b.messages['truth']['stamp_s'] = 1.02
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='fresh bounded truth/wheel/drive'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert len(b.calls) == 1 and b.steps == [20, 20]



def test_two_delayed_truth_samples_cannot_prove_a_post_application_quiet_interval(tmp_path, monkeypatch):
    def post(b):
        if len(b.steps) in (1, 2):
            b.messages['truth']['stamp_s'] = 1.+len(b.steps)*.001
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='fresh bounded truth/wheel/drive evidence: truth'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert b.steps == [20, 20] and len(b.calls) == 1


@pytest.mark.parametrize('channel', ['wheel', 'drive'])
@pytest.mark.parametrize('phase_step', [1, 2])
def test_zero_wheel_and_drive_ack_must_be_newer_than_the_phase_boundary(
        tmp_path, monkeypatch, channel, phase_step):
    def post(b):
        if len(b.steps) == phase_step:
            b.messages[channel]['stamp_s'] = 1.+(phase_step-1)*.02
    b = backend(tmp_path, monkeypatch, post=post)
    with pytest.raises(ValueError, match='fresh bounded truth/wheel/drive evidence: '+channel):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert b.steps == [20]*phase_step and len(b.calls) == 1


def test_gyro_gap_during_post_application_quiet_is_not_removed_by_a_later_epoch(tmp_path, monkeypatch):
    b = backend(tmp_path, monkeypatch)
    step = b.step_world
    def missing_gyro(count):
        step(count)
        if len(b.steps) >= 4:
            b.raw = [r for r in b.raw if r['channel'] != 'imu' or r['stamp_s'] not in (1.08, 1.10)]
    b.step_world = missing_gyro
    with pytest.raises(ValueError, match='post-epoch support: imu'):
        recovery_reset.reanchor(b, [0., 0., 0.])
    report = json.loads((tmp_path/'reanchor.json').read_text())
    assert report['source_epoch_s'] == 1.06
    assert report['post_reset_quiet']['truth_stamp_s'] == 1.08


def test_reset_failure_has_no_retry_or_application_steps(tmp_path, monkeypatch):
    b = backend(tmp_path, monkeypatch)
    calls = []
    def reject(*args):
        calls.append(args)
        raise TimeoutError('missing ACK')
    monkeypatch.setattr(recovery_reset, '_set_pose_once', reject)
    with pytest.raises(TimeoutError):
        recovery_reset.reanchor(b, [0., 0., 0.])
    assert len(calls) == 1 and b.steps == []
    report = json.loads((tmp_path/'reanchor.json').read_text())
    assert report['command_accepted'] is False and report['valid'] is False


def test_heading_verification_wraps_at_pi():
    result = recovery_reset.verify_reset_state(messages(1., (0., 0., 0., -3.1415926535)),
                                               now_s=1., declared_pose=[0., 0., 3.1415926535])
    assert result['heading_error_rad'] < 1e-8


@pytest.mark.parametrize('accepted', [True, False])
def test_pose_service_issues_one_declared_model_request_and_releases_client(accepted, monkeypatch):
    def request_factory():
        return SimpleNamespace(entity=SimpleNamespace(MODEL=2), pose=SimpleNamespace(
            position=SimpleNamespace(), orientation=SimpleNamespace()))
    monkeypatch.setitem(sys.modules, 'ros_gz_interfaces.msg', SimpleNamespace(Entity=SimpleNamespace(MODEL=2)))
    monkeypatch.setitem(sys.modules, 'ros_gz_interfaces.srv',
                        SimpleNamespace(SetEntityPose=SimpleNamespace(Request=request_factory)))
    requests = []
    destroyed = []
    future = SimpleNamespace(done=lambda: True, result=lambda: SimpleNamespace(success=accepted))
    client = SimpleNamespace(wait_for_service=lambda **kw: True,
                             call_async=lambda request: requests.append(request) or future)
    node = SimpleNamespace(create_client=lambda *args: client,
                           destroy_client=lambda value: destroyed.append(value))
    b = SimpleNamespace(node=node)
    if accepted:
        recovery_reset._set_pose_once(b, [2., 3., .4], -.00001)
    else:
        with pytest.raises(RuntimeError, match='rejected'):
            recovery_reset._set_pose_once(b, [2., 3., .4], -.00001)
    assert len(requests) == 1 and destroyed == [client]
    request = requests[0]
    assert request.entity.name == 'nino' and request.entity.type == request.entity.MODEL
    assert request.pose.position.x == 2. and request.pose.position.y == 3.
    assert request.pose.position.z == -.00001
    assert request.pose.orientation.z == pytest.approx(.19866933079506122)
