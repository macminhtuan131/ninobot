from copy import deepcopy
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from nino_rl.real_velocity_replay import aligned_session
from nino_rl.real_velocity_sim import RealReferenceBackend, compare, validate_schedule
from nino_rl.factory_velocity_backend import FactoryVelocityBackend


def session():
    origin = 1_000_000_000
    stamps = [origin+i*20_000_000 for i in range(100)]
    return dict(integrity='ok', source_sha256='a'*64, source_sha256_after='a'*64,
                commands=[[t, .1 if i >= 10 else 0., 0.] for i, t in enumerate(stamps)],
                motor=[[t, t, ['right_wheel', 'left_wheel'], [], [2., 1.], []] for t in stamps])


def test_causal_asof_and_named_mapping():
    source = session()
    source['commands'][10][0] += 1_000_000
    rows, qc = aligned_session(source)
    assert rows[10, 1] == 0.
    assert rows[11, 1] == .1
    np.testing.assert_array_equal(rows[:, 3:5], np.tile([1., 2.], (100, 1)))
    assert qc['eligible'] and not qc['interpolation']


def test_missing_internal_reference_is_not_filled_or_hidden():
    source = session()
    source['commands'] = source['commands'][:20]+source['commands'][40:]
    _, qc = aligned_session(source)
    assert not qc['eligible']
    assert qc['unsupported_internal_samples'] > 0
    assert qc['maximum_aligned_gap_s'] > .15


@pytest.mark.parametrize('mutation', ['hash', 'duplicate', 'wheel_mapping'])
def test_invalid_sources_rejected(mutation):
    source = session()
    if mutation == 'hash':
        source['source_sha256_after'] = 'b'*64
    elif mutation == 'duplicate':
        source['motor'][1][1] = source['motor'][0][1]
    else:
        source['motor'][0][2] = ['left_wheel', 'left_wheel']
    with pytest.raises(ValueError):
        aligned_session(source)


def test_sim_schedule_is_bounded_and_diagnostic():
    schedule = dict(schema_version=1, purpose='matched_real_reference_gazebo_diagnostic',
                    interval_s=.1, physical_calibration_accepted=False, td3_replay_eligible=False,
                    rows=[dict(time_s=i*.1, comparison_time_s=(i+1)*.1, v_m_s=.05, yaw_rad_s=0.,
                               real_feedback_age_s=.02, reported_wheel_rad_s=[1., 1.]) for i in range(20)])
    assert len(validate_schedule(schedule)) == 20
    bad = deepcopy(schedule); bad['rows'][5]['v_m_s'] = 2.
    with pytest.raises(ValueError):
        validate_schedule(bad)
    bad = deepcopy(schedule); bad['td3_replay_eligible'] = True
    with pytest.raises(ValueError):
        validate_schedule(bad)


def test_comparison_uses_each_reported_wheel_after_startup():
    rows = [dict(time_s=i*.1, real_reported_wheel_rad_s=[1., 2.],
                 sim_reported_wheel_rad_s=[1.5, 1.]) for i in range(20)]
    result = compare(rows)
    assert result['comparison_samples'] == 10
    assert result['wheel_rmse_rad_s'] == [.5, 1.]


def test_external_replay_does_not_run_or_replace_reference_with_goal_follower(monkeypatch):
    backend = RealReferenceBackend.__new__(RealReferenceBackend)
    backend.active, backend.time, backend.cached_view = True, 2., None
    backend.bootstrap_report = dict(valid=True)
    backend.lock, backend.request = threading.RLock(), (.12, .3)
    backend.gconf = dict(clock_id='gazebo_simulation_clock')
    backend.estimator = SimpleNamespace(advance=lambda _: [], estimate=lambda: dict(stamp_s=2.))
    backend.goal_reference = None
    monkeypatch.setattr(FactoryVelocityBackend, 'view', lambda _: dict(stamp_s=2., features={}))
    view = backend.view()
    assert view['baseline'] == (.12, .3)
    assert view['guidance_audit']['follower_active'] is False
    assert backend.goal_reference is None


def test_wheel_diagnostic_labels_its_post_settle_epoch_without_pose_reconstruction(monkeypatch, tmp_path):
    backend = RealReferenceBackend.__new__(RealReferenceBackend)
    backend.active, backend.time, backend.cached_view = True, 2., None
    backend.bootstrap_report = None
    backend.episode_dir = tmp_path
    backend.lock, backend.request = threading.RLock(), (0., 0.)
    backend.gconf = dict(clock_id='gazebo_simulation_clock')
    backend.estimator = SimpleNamespace(advance=lambda _: [], estimate=lambda: dict(stamp_s=2.))
    monkeypatch.setattr(FactoryVelocityBackend, 'view', lambda _: dict(stamp_s=2., features={}))
    backend.view()
    assert backend.bootstrap_report['spawn_to_task_pose_reconstructed'] is False
    assert backend.bootstrap_report['estimator_used_for_command_or_score'] is False
    assert backend.bootstrap_report['startup_gap_changes_training_qualification'] is False
