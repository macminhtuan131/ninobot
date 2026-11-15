from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest

from nino_rl.factory_velocity_backend import FactoryVelocityBackend
from nino_rl.unknown_step_gazebo import UnknownStepBackend
from test_unknown_step_runtime import guidance_config, view


def fake_backend(t):
    b = UnknownStepBackend.__new__(UnknownStepBackend)
    b.active, b.time, b.start_time = True, t, 0.
    b.cached_view = b.goal_reference = None
    b.gconf = guidance_config()
    b.protocol = dict(warmup_s=.5, command_until_s=6.)
    b.lock = threading.RLock()
    b.estimator = SimpleNamespace(epoch='test', advance=lambda now: [],
        estimate=lambda: dict(pose=[.5, 0., 0.], stamp_s=t, epoch='test'))
    b._store = lambda *args: None
    return b


@pytest.mark.parametrize('t', [6., 8., 12.])
def test_gazebo_view_replaces_planned_stop_with_estimator_goal_reference(monkeypatch, t):
    b = fake_backend(t)
    raw = view(t, baseline=(0., 0.))
    raw['source_samples'] = dict(baseline=dict(frame='base_footprint'))
    monkeypatch.setattr(FactoryVelocityBackend, 'view', lambda self: deepcopy(raw))
    result = b.view()
    assert result['baseline'][0] > 0 and result['guidance_audit']['profile_phase'] == 'path_following'
    assert result['guidance_audit']['pose_source'] == 'wheel_imu_odometry'
    assert 'truth' not in result['source_samples']
    assert b.view() == result  # Duplicate caller cannot advance the estimator/follower tick.


def test_physical_boundary_uses_actual_truth_header_and_request_ack():
    b = fake_backend(1.)
    b.config = dict(nominal_geometry=dict(separation=.34273666))
    b.messages = dict(
        truth=dict(stamp_s=.99, values=dict(pose=[.4, .01, .02, .03], speed_norm=.15,
                                          yaw_rate=.02, roll=.01, pitch=-.02)),
        drive=dict(stamp_s=.985, values=dict(requested_linear_m_s=.12, requested_yaw_rad_s=.1)),
        wheel=dict(stamp_s=.998, values=[1.5, 1.6]))
    p = b._physical(view(1.), motion_requested=True)
    assert p.stamp_s == .99 and p.decision_stamp_s == 1.
    assert p.pose_m_rad == (.4, .01, .02, .01, -.02, .03)
    assert p.wheel_rad_s == (1.5, 1.6)
    assert p.accepted_reference_m_s == pytest.approx((.12-.34273666*.1/2, .12+.34273666*.1/2))
