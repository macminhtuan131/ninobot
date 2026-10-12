"""Guard conditional correction and strict route admission to the curriculum."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / 'src/nino_rl/scripts'
spec = importlib.util.spec_from_file_location('rough_trial8_validation_test', SCRIPTS / 'run_rough_trial8_validation.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def audit(ev=-.02, actor=2., critic=100., retained=.001):
    def batch(actor, critic, retained):
        return dict(actor_gradient_norm=actor, critic_gradient_norm=critic, clip_retained_fraction=retained)
    return dict(raw_units=dict(explained_variance=ev, batches=[batch(actor, critic, retained)]),
                fresh_critic_candidates={'.1': {'batches': [batch(2., 5., .03)]},
                                         '.03': {'batches': [batch(2., 1., .1)]},
                                         '.01': {'batches': [batch(2., .2, .2)]}})


def test_largest_measured_unit_correction_selected():
    gate = runner.numerical_gate(audit())
    assert gate['confirmed'] and gate['selected_scale'] == .1


@pytest.mark.parametrize('kwargs', [{'ev': .7}, {'critic': 2.}, {'retained': .1}])
def test_bad_fit_alone_does_not_authorize_correction(kwargs):
    gate = runner.numerical_gate(audit(**kwargs))
    assert not gate['confirmed'] and gate['selected_scale'] is None


def route_row(error=.03):
    return dict(success='True', truth_path_rmse_m=error, odom_truth_position_error_m=.003,
                truth_endpoint_error_m=.19, route_gates_passed=7, route_gates_total=7, termination='success')


CONFIG = dict(goal_tolerance_m=.2, rough_curriculum={'gate': {'success_rate': .95, 'max_truth_path_rmse_m': .05}})


def test_n1_arrival_does_not_hide_poor_tracking():
    gate = runner.route_readiness([route_row(.116)] * 3, CONFIG, 3)
    assert gate['physical_arrival_rate'] == 1. and not gate['passed']


@pytest.mark.parametrize('changed', [{'truth_endpoint_error_m': .3}, {'route_gates_passed': 6},
                                   {'odom_truth_position_error_m': .11}, {'termination': 'rollover'}])
def test_independent_physical_evidence_preserved(changed):
    row = route_row()
    row.update(changed)
    assert not runner.route_readiness([row] * 3, CONFIG, 3)['passed']


def test_snapshot_changes_units_without_changing_controller_or_reward(tmp_path, monkeypatch):
    from nino_rl.core import load_config
    from nino_rl.training_contract import training_contract as old_contract
    sys.path.insert(0, str(SCRIPTS))
    original = ROOT / 'rl_runs/rough_wall_recovery_v16'
    overlay = runner.corrected_snapshot(tmp_path, original, .1)
    for name in ('control_v2.py', 'ros_env.py', 'ros_interface.py', 'routes.py', 'rough_stall_recovery.py'):
        assert (overlay / 'nino_rl' / name).read_bytes() == (original / 'python/nino_rl' / name).read_bytes()
    path = overlay / 'nino_rl/training_contract.py'
    isolated = importlib.util.spec_from_file_location('rough_corrected_contract_test', path)
    module = importlib.util.module_from_spec(isolated)
    isolated.loader.exec_module(module)
    cfg = load_config(runner.SOURCE.parent / 'ppo.yaml')
    cfg['training_reward_scale'] = .1
    assert module.training_contract(cfg)['revision'] == 39
    with pytest.raises(ValueError, match='NEW run'):
        module.validate_resume(SimpleNamespace(nino_training_contract=old_contract(cfg)), cfg)
    first = module.training_contract(cfg)
    cfg['rough_runtime']['stage_index'] = 1
    assert module.training_contract(cfg) == first  # Declared stage changes retain the new contract.
    module.validate_resume(SimpleNamespace(nino_training_contract=first), cfg)
