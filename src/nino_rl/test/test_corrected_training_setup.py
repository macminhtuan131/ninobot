from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from nino_rl.core import load_config
from nino_rl.routes import RouteSet
from nino_rl.training_contract import training_contract, validate_resume

CONFIGS = Path(__file__).parents[1] / 'config'


def test_fixed_routes_replay_e1_without_changing_physical_scoring():
    config = load_config(CONFIGS / 'rough_e1_n1_s1_fixed.yaml')
    source = load_config(CONFIGS / 'rough_e1_imu_assisted.yaml')
    routes = RouteSet(config)
    rng = np.random.default_rng(42)
    for cycle in range(5):
        assert sorted(routes.select(rng, cycle * 3 + i)['id'] for i in range(3)) == ['E1', 'N1', 'S1']
    for name in ('goal_tolerance_m', 'goal_heading_tolerance_deg', 'goal_require_stopped',
                 'reward_pose_source', 'reward_v2', 'odometry_assistance'):
        assert config[name] == source[name]
    assert not config['domain_randomization']['enabled']
    assert not config['adaptive_terrain']['enabled']
    with pytest.raises(ValueError, match='contract differs'):
        validate_resume(SimpleNamespace(nino_training_contract=training_contract(source)), config)


def test_flat_profile_requires_new_contract_and_retains_arrival_rule():
    source = load_config(CONFIGS / 'combined_flat_feedback_pilot.yaml')
    config = load_config(CONFIGS / 'combined_flat_pi_tracking.yaml')
    assert config['drive_controller']['parameters']['pi_integrator_profile'] == 'conditional_v1'
    assert training_contract(config)['revision'] == 37
    for key in ('goal_tolerance_m', 'reward_pose_source', 'reward_v2', 'odometry_assistance'):
        assert config[key] == source[key]
    with pytest.raises(ValueError, match='contract differs'):
        validate_resume(SimpleNamespace(nino_training_contract=training_contract(source)), config)
