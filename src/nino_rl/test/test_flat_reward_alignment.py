"""Verify new reward units and the executable snapshot's contract boundaries."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / 'src/nino_rl/scripts'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


helper = load(SCRIPTS / 'flat_reward_alignment.py', 'flat_reward_alignment_test')
CFG = dict(impact_mode=helper.REVISION, impact_weight=.03,
           impact_acceleration_sigma_m_s2=3., impact_reference_seconds=.1,
           peak_impact_weight=.25, peak_acceleration_sigma_m_s2=20.)


def test_energy_keeps_distinguishing_spikes_above_old_saturation():
    costs = [helper.impact_terms(dict(square_integral=a*a*.1, peak=a,
                                    previous_episode_peak=0.), CFG)['impact']
             for a in (6., 12., 24.)]
    assert costs[1] == pytest.approx(4 * costs[0])
    assert costs[2] == pytest.approx(4 * costs[1])
    assert [min((a/2)**4, 81) for a in (6., 12., 24.)] == [81, 81, 81]


def test_timestamp_energy_and_peak_cost_do_not_depend_on_window_splits():
    total = dict(impact=0., peak_impact=0.)
    previous = 0.
    for dt, peak in ((.03, 12.), (.07, 12.), (.04, 24.), (.06, 24.)):
        terms = helper.impact_terms(dict(square_integral=peak*peak*dt,
            peak=peak, previous_episode_peak=previous), CFG)
        previous = max(previous, peak)
        for key in total:
            total[key] += terms[key]
    whole = helper.impact_terms(dict(square_integral=12**2*.1 + 24**2*.1,
        peak=24., previous_episode_peak=0.), CFG)
    assert total == pytest.approx(whole)
    assert helper.impact_terms(dict(square_integral=0., peak=12., previous_episode_peak=24.), CFG)['peak_impact'] == 0.
    assert helper.impact_terms(dict(square_integral=0., peak=12., previous_episode_peak=0.), CFG)['peak_impact'] < 0.


@pytest.mark.parametrize('key,value', [('square_integral', float('nan')), ('peak', -1.),
                                      ('previous_episode_peak', float('inf'))])
def test_invalid_measurements_fail(key, value):
    imu = dict(square_integral=1., peak=2., previous_episode_peak=0.)
    imu[key] = value
    with pytest.raises(ValueError):
        helper.impact_terms(imu, CFG)


@pytest.mark.parametrize('scale', [0., -1., float('nan'), float('inf')])
def test_invalid_reward_units_fail(scale):
    with pytest.raises(ValueError):
        helper.validate_scale(scale)


def test_reward_wrapper_preserves_raw_monitor_and_physical_info():
    import gymnasium as gym
    from stable_baselines3.common.monitor import Monitor

    class OneStep(gym.Env):
        observation_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)
        action_space = gym.spaces.Box(-1., 1., (1,), dtype=np.float32)

        def reset(self, **kwargs):
            return np.array([.2], dtype=np.float32), {}

        def step(self, action):
            return np.array([.3], dtype=np.float32), 100., True, False, {'physical_arrival': True}

    env = helper.scaled_environment(Monitor(OneStep()), .01)
    env.reset()
    observation, reward, terminated, truncated, info = env.step([0.])
    assert observation == pytest.approx([.3])
    assert reward == 1. and terminated and not truncated
    assert info['episode']['r'] == 100. and info['physical_arrival']


def test_executable_snapshot_preserves_terminal_and_resume_boundaries(tmp_path, monkeypatch):
    from nino_rl.core import load_config, RobotState, TrackingState
    from nino_rl.control_v2 import compute_reward as original_reward
    from nino_rl.training_contract import training_contract as original_contract
    runner = load(SCRIPTS / 'run_flat_reward_pilot.py', 'flat_reward_runner_test')
    overlay = runner.make_snapshot(tmp_path)
    monkeypatch.setitem(sys.modules, 'nino_rl.alignment_helpers', helper)
    control = load(overlay / 'nino_rl/control_v2.py', 'isolated_reward_control')
    contract = load(overlay / 'nino_rl/training_contract.py', 'isolated_reward_contract')
    cfg = load_config(ROOT / 'src/nino_rl/config/combined_flat_energy_scaled_pilot.yaml')
    # NinoGazeboEnv supplies this actuator normalization before compute_reward.
    cfg['reward_v2']['torque_scale_nm'] = 5.
    legacy = deepcopy(cfg['reward_v2'])
    legacy.pop('impact_mode')
    args = (TrackingState(0., .02, .01, 1., 1.), TrackingState(.01, .02, .01, .99, .99),
            RobotState(), [0., 0.], [0., 0.], [0., 0.], .1,
            dict(impact_integral=8.1, square_integral=57.6, peak=24., previous_episode_peak=12.))
    for outcome in ({'succeeded': True}, {'succeeded': True, 'failed': 'off_path'}, {'timed_out': True}):
        keywords = dict(outcome, challenge_total=2, challenge_cleared_total=2)
        old_reward, old_terms = original_reward(*args, legacy, **keywords)
        assert control.compute_reward(*args, legacy, **keywords) == (old_reward, old_terms)
        new_reward, new_terms = control.compute_reward(*args, cfg['reward_v2'], **keywords)
        for key in old_terms:
            if key != 'impact':
                assert new_terms[key] == old_terms[key]
        assert new_reward == pytest.approx(sum(new_terms.values()))
        if outcome == {'succeeded': True}:
            assert new_terms['terminal'] == 100. and new_terms['challenge_goal'] == 90.
        if outcome.get('failed'):
            assert new_terms['terminal'] < 0 and new_terms['challenge_goal'] == 0.
    model = SimpleNamespace(nino_training_contract=original_contract(cfg))
    with pytest.raises(ValueError, match='NEW run'):
        contract.validate_resume(model, cfg)
    model.nino_training_contract = contract.training_contract(cfg)
    assert model.nino_training_contract['revision'] == 38
    contract.validate_resume(model, cfg)
    changed = deepcopy(cfg)
    changed['training_reward_scale'] = .02
    with pytest.raises(ValueError):
        contract.validate_resume(model, changed)


def test_gae_does_not_bootstrap_across_terminal_episodes():
    audit = load(SCRIPTS / 'inspect_flat_critic.py', 'flat_critic_test')
    targets = audit.gae_targets([1., 100., 1., 200.], [0., 0., 0., 0.],
                               [False, True, False, True], 1., 1.)
    assert targets == pytest.approx([101., 100., 201., 200.])
