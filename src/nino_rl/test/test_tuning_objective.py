from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import optuna
import pytest
import yaml

from nino_rl.core import load_config
from nino_rl.evaluation import benchmark_id, prepare_evaluation_config
from nino_rl.tuning_objective import (make_objective_contract, score_episodes,
    bind_study_objective, qualified_best_trial, record_trial_objective)
from nino_rl.trajectory_metrics import write_csv

PACKAGE = Path(__file__).parents[1]
SETTINGS = PACKAGE / 'config/optuna_objective.yaml'


def make_case(course='flat', episodes=20):
    name = 'combined_flat_pi_tracking.yaml' if course == 'flat' else 'rough_e1_n1_s1_fixed.yaml'
    base = load_config(PACKAGE / 'config' / name)
    contract = make_objective_contract(base, SETTINGS, course=course, episodes=episodes, seed=61000)
    rows = [dict(seed=item['seed'], route_id=None if item['route_id']=='straight' else item['route_id'],
                 reward_pose_source='ground_truth', success=True, termination='success',
                 truth_endpoint_error_m=.15, route_gates_passed=9, route_gates_total=9,
                 time_seconds=20., truth_path_rmse_m=.03, rms_vertical_acceleration_m_s2=1.5,
                 rms_wheel_slip=.10) for item in contract['scenarios']]
    return base, contract, rows


def test_arrival_gate_dominates_comfort_and_requires_every_route():
    _, contract, rows = make_case()
    comfortable_failure = deepcopy(rows)
    for row in comfortable_failure:
        row.update(success=False, termination='timeout', time_seconds=.01,
                   rms_vertical_acceleration_m_s2=0., rms_wheel_slip=0., truth_path_rmse_m=0.)
    assert score_episodes(comfortable_failure, contract)['score'] < -1000
    assert score_episodes(rows, contract)['score'] > 0
    # 19/20 qualifies at 95%; 18/20 cannot outrank any qualified policy.
    rows[0].update(success=False, termination='timeout')
    assert score_episodes(rows, contract)['arrival_feasible']
    rows[1].update(success=False, termination='timeout')
    assert not score_episodes(rows, contract)['arrival_feasible']
    _, contract, rows = make_case('rough', episodes=60)
    # Overall 58/60 successes still cannot hide 18/20 on one route.
    for row in [r for r in rows if r['route_id']=='N1'][:2]:
        row.update(success=False, termination='wrong_direction')
    result = score_episodes(rows, contract)
    assert not result['arrival_feasible']
    assert result['per_route']['N1']['physical_arrival_rate'] == .9


@pytest.mark.parametrize('metric,value', [('time_seconds',30.), ('truth_path_rmse_m',.10),
    ('rms_vertical_acceleration_m_s2',3.), ('rms_wheel_slip',.3)])
def test_each_quality_regression_lowers_score(metric, value):
    _, contract, rows = make_case()
    baseline = score_episodes(rows, contract)['score']
    for row in rows:
        row[metric] = value
    assert score_episodes(rows, contract)['score'] < baseline


def test_reward_changes_leave_objective_and_evaluation_identity_fixed():
    base, contract, _ = make_case()
    changed = deepcopy(base)
    changed['reward_v2']['success_bonus'] = 1000000.
    changed['reward_v2']['time_penalty'] = 0.
    changed['reward_v2']['slip_weight'] = 100.
    changed['ppo']['learning_rate'] = .001
    assert make_objective_contract(changed, SETTINGS, course='flat', episodes=20, seed=61000) == contract
    changed['goal_tolerance_m'] = .8
    assert make_objective_contract(changed, SETTINGS, course='flat', episodes=20, seed=61000) != contract


def test_invalid_partial_estimated_only_and_nonfinite_results_are_rejected():
    _, contract, rows = make_case()
    for invalid in (rows[:-1], rows + rows[:1]):
        with pytest.raises(ValueError, match='scenarios'):
            score_episodes(invalid, contract)
    rows[0]['reward_pose_source'] = 'wheel_odometry'
    with pytest.raises(ValueError, match='physical pose'):
        score_episodes(rows, contract)
    rows[0]['reward_pose_source'] = 'ground_truth'
    rows[0]['rms_wheel_slip'] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        score_episodes(rows, contract)
    base = load_config(PACKAGE / 'config/rough_e1_n1_s1_fixed.yaml')
    with pytest.raises(ValueError, match='cover every active route'):
        make_objective_contract(base, SETTINGS, course='rough', episodes=2, seed=0)


def test_estimated_arrival_and_skipped_physical_gates_cannot_count_as_success():
    _, contract, rows = make_case()
    rows[0]['truth_endpoint_error_m']=.35
    with pytest.raises(ValueError, match='physical goal circle'):
        score_episodes(rows,contract)
    _, contract, rows = make_case('rough',episodes=12)
    rows[0]['route_gates_passed']=0
    with pytest.raises(ValueError, match='ordered route gates'):
        score_episodes(rows,contract)


def test_frozen_study_rejects_legacy_and_changed_objective(tmp_path):
    _, contract, _ = make_case()
    study = optuna.create_study(direction='maximize')
    bind_study_objective(study, contract, tmp_path)
    bind_study_objective(study, contract, tmp_path)
    changed = deepcopy(contract)
    changed['weights']['slip'] = 10.
    with pytest.raises(ValueError, match='objective changed'):
        bind_study_objective(study, changed, tmp_path)
    legacy = optuna.create_study(direction='maximize')
    legacy.optimize(lambda _: 100., n_trials=1)
    with pytest.raises(ValueError, match='legacy study'):
        bind_study_objective(legacy, contract, tmp_path)


def test_unqualified_best_is_not_exported_and_successful_best_is_eligible(tmp_path):
    study = optuna.create_study(direction='maximize')
    def failed(trial):
        trial.set_user_attr('arrival_feasible',False)
        return -1500.
    study.optimize(failed, n_trials=1)
    assert qualified_best_trial(study,tmp_path) is None
    assert (tmp_path/'best_infeasible.json').exists()
    def passed(trial):
        trial.set_user_attr('arrival_feasible',True)
        return 20.
    study.optimize(passed, n_trials=1)
    assert qualified_best_trial(study,tmp_path).number == 1


def test_trial_record_checks_frozen_task_and_saves_breakdown(tmp_path):
    base, contract, rows = make_case()
    config = prepare_evaluation_config(base)
    (tmp_path/'config.yaml').write_text(yaml.safe_dump(config))
    summary = dict(complete=True,benchmark_id=benchmark_id(config),episodes=20,
                   evaluation_seeds=[r['seed'] for r in rows],success_rate=1.)
    path = tmp_path/'summary.json'
    path.write_text(json.dumps(summary))
    write_csv(tmp_path/'episodes.csv',rows)
    study = optuna.create_study(direction='maximize')
    study.optimize(lambda trial:record_trial_objective(trial,path,contract),n_trials=1)
    assert study.best_trial.user_attrs['arrival_feasible']
    assert json.loads((tmp_path/'optuna_objective.json').read_text())['score']==study.best_value
    summary['complete']=False
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='Incomplete'):
        record_trial_objective(study.ask(),path,contract)


def test_all_tuners_use_shared_objective_and_resolve_inherited_profiles():
    for name in ('tune_split_optuna.py','tune_split_optuna_rough_resume.py','tune_combined_optuna.py','tune_rocky_optuna.py'):
        path=PACKAGE/'scripts'/name
        spec=importlib.util.spec_from_file_location(name[:-3],path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.record_trial_objective is record_trial_objective
        assert module.load_config(PACKAGE/'config/combined_flat_pi_tracking.yaml')['reward_pose_source']=='ground_truth'
