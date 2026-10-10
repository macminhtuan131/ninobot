"""Recovery must react to independent motion and stop after bounded retries."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import pytest
import yaml
import importlib.util
import shutil
import py_compile
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src/nino_rl/scripts'))
from rough_stall_recovery import StallRecovery, CornerAlignment, route_controller_config
from rough_stall_recovery import install_recovery


def recovery():
    return StallRecovery(yaml.safe_load((ROOT/'src/nino_rl/config/rough_turn_recovery_candidate.yaml').read_text())['rough_stall_recovery'])


def state(x=0., y=0., **kw):
    return NS(x=x, y=y, yaw=0., roll=0., pitch=0., localization_valid=True,
              left_wheel_velocity=3., right_wheel_velocity=3., **kw)


def test_sideways_translation_and_slow_motion_do_not_trigger():
    for axis in ('x', 'y'):
        r = recovery()
        for i in range(50):
            assert r.command(i*.1, state(**{axis:i*.006}), NS(endpoint_distance=2.), .18, -.45)[2] is False
        assert r.attempts == 0


def test_spin_triggers_bounded_backoff_and_resumes_tracking():
    r = recovery()
    for i in range(15):
        command = r.command(i*.1, state(), NS(endpoint_distance=2.), .18, -.45)
        if r.mode == 'backoff':
            break
    assert command == (-.08, 0., True)
    assert r.attempts == 1
    t = i*.1
    assert r.command(t+.1, state(x=-.16), NS(endpoint_distance=2.), .18, -.45) == (.18, -.45, True)
    assert r.mode == 'retry'
    assert r.command(t+1.2, state(x=-.15), NS(endpoint_distance=2.), .18, -.45) == (.18, -.45, False)


def test_no_motion_caps_attempts_and_holds_stop():
    r = recovery()
    for i in range(250):
        command = r.command(i*.1, state(), NS(endpoint_distance=2.), .18, -.45)
        if r.mode == 'exhausted':
            break
    assert r.attempts == 3
    assert r.mode == 'exhausted'
    assert command == (0., 0., True)
    assert r.command(i*.1+.1, state(), NS(endpoint_distance=2.), .18, -.45) == (0., 0., True)


def test_goal_approach_does_not_trigger_and_reset_has_no_history():
    r = recovery()
    for i in range(30):
        r.command(i*.1, state(), NS(endpoint_distance=.3), .18, -.45)
    assert r.attempts == 0
    fresh = recovery()
    assert len(fresh.samples) == 0 and fresh.attempts == 0 and fresh.mode == 'tracking'


def test_invalid_localization_and_clock_cannot_drive_reverse():
    r = recovery()
    s = state()
    s.localization_valid = False
    assert r.command(1., s, NS(endpoint_distance=2.), .18, -.45) == (0., 0., True)
    with pytest.raises(ValueError):
        r.command(0., s, NS(endpoint_distance=2.), .18, -.45)


def test_unsafe_settings_rejected():
    cfg = recovery().cfg.copy()
    cfg['maximum_attempts'] = 4
    with pytest.raises(ValueError):
        StallRecovery(cfg)


def test_unsafe_attitude_stops_active_recovery():
    r = recovery()
    for i in range(15):
        r.command(i*.1, state(), NS(endpoint_distance=2.), .18, -.45)
    assert r.mode == 'backoff'
    s = state()
    s.roll = .51
    assert r.command(1.5, s, NS(endpoint_distance=2.), .18, -.45) == (0., 0., True)
    assert r.mode == 'exhausted'


def test_corner_alignment_finishes_turn_before_forward_motion():
    corner = CornerAlignment()
    path = NS(points=np.array([[0., 0.], [2.5, 0.], [2.5, -6.2]]),
              delta=np.array([[2.5, 0.], [0., -6.2]]), cumulative=np.array([0., 2.5, 8.7]))
    tracking = NS(path_s=2.45)
    s = state(x=2.45)
    assert corner.command(0., s, path, tracking, .2, -.45) == (0., -.45, True)
    s.yaw = -np.pi/2
    assert corner.command(3.5, s, path, tracking, .2, -.45) == (.2, -.45, False)
    assert 1 in corner.completed


def test_corner_alignment_cannot_spin_indefinitely():
    corner = CornerAlignment()
    path = NS(points=np.array([[0., 0.], [2.5, 0.], [2.5, -6.2]]),
              delta=np.array([[2.5, 0.], [0., -6.2]]), cumulative=np.array([0., 2.5, 8.7]))
    corner.command(0., state(x=2.5), path, NS(path_s=2.5), .2, -.45)
    assert corner.command(8.1, state(x=2.5), path, NS(path_s=2.5), .2, -.45) == (0., 0., True)
    assert corner.failed


def test_s1_turn_profile_does_not_change_n1_or_mutate_training_config():
    cfg = {'routes': {'curvature_speed_limit':True, 'stop_align_route_ids':['S1']}}
    assert route_controller_config(cfg, 'S1') is cfg
    n1 = route_controller_config(cfg, 'N1')
    assert n1['routes']['curvature_speed_limit'] is False
    assert cfg['routes']['curvature_speed_limit'] is True


def test_frozen_route_respects_curvature_and_exhaustion_is_scored(tmp_path):
    sys.path.insert(0, str(ROOT/'src/nino_rl'))
    from nino_rl.core import load_config
    for filename in ('ros_env.py', 'ros_interface.py', 'routes.py'):
        shutil.copy2(ROOT/'src/nino_rl/nino_rl'/filename, tmp_path/filename)
    environment = tmp_path/'ros_env.py'
    text = environment.read_text()
    text = text.replace('navigation_invalid = self.nav_invalid_seconds >= float(self.config["navigation_invalid_hold_seconds"])',
        'navigation_invalid = (self.nav_invalid_seconds >= float(self.config["navigation_invalid_hold_seconds"]))')
    environment.write_text(text)
    install_recovery(tmp_path)
    for filename in ('ros_env.py', 'ros_interface.py', 'routes.py'):
        py_compile.compile(str(tmp_path/filename), doraise=True)
    text = environment.read_text()
    # Exhaustion must be represented in the failure flag, log and episode
    # metrics, rather than appearing as an early timeout or a success.
    assert text.count('"recovery_exhausted" if recovery_exhausted') == 3
    spec = importlib.util.spec_from_file_location('candidate_routes', tmp_path/'routes.py')
    routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes)
    cfg = load_config(ROOT/'src/nino_rl/config/rough_turn_recovery_candidate.yaml')
    tracking = NS(path_s=0., distance_remaining=5., endpoint_distance=5., heading_error=0.)
    path = NS(point_at=lambda _: np.array([.2, -.4]))
    speed, yaw = routes.route_command(state(), path, tracking, cfg)
    assert yaw == pytest.approx(-cfg['routes']['max_yaw_rate_rad_s'])
    assert yaw/speed == pytest.approx(-4.)
    speed_line, yaw_line = routes.route_command(state(), NS(point_at=lambda _: np.array([1., 0.])), tracking, cfg)
    assert yaw_line == 0.
    assert speed_line == cfg['navigation']['straight_speed_m_s']
