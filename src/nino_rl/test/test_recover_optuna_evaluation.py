import importlib.util
import json
from pathlib import Path

import optuna
import pytest
from test_tuning_history import historical_case

script = Path(__file__).parents[1] / 'scripts/recover_optuna_evaluation.py'
spec = importlib.util.spec_from_file_location('recover_evaluation', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def failed_trial(case):
    completed = case['source'].best_trial
    case['target'].add_trial(optuna.trial.create_trial(state=optuna.trial.TrialState.FAIL,
        params=completed.params, distributions=completed.distributions,
        user_attrs=completed.user_attrs))
    return case['target'].trials[0], Path(completed.user_attrs['model'])


def test_complete_matching_evaluation_recovers_once_without_retraining(historical_case):
    case = historical_case
    source, model = failed_trial(case)
    original = model.read_bytes()
    score = module.append_observation(case['target'], source, model, case['summary_path'],
                                      case['comparable'], case['objective'])
    failed, recovered = case['target'].trials
    assert failed.state == optuna.trial.TrialState.FAIL and failed.value is None
    assert recovered.value == score == case['source'].best_value
    assert recovered.params == source.params
    assert recovered.user_attrs['evaluation_recovery_of'] == source.number
    assert model.read_bytes() == original
    with pytest.raises(ValueError, match='already'):
        module.append_observation(case['target'], source, model, case['summary_path'],
                                  case['comparable'], case['objective'])
    assert len(case['target'].trials) == 2


@pytest.mark.parametrize('change', ['incomplete', 'wrong_model', 'ablation'])
def test_invalid_evaluation_never_receives_a_recovered_score(historical_case, change):
    case = historical_case
    source, model = failed_trial(case)
    summary = json.loads(case['summary_path'].read_text())
    if change == 'incomplete':
        summary['complete'] = False
    elif change == 'wrong_model':
        summary['model'] = '/not-this-model.zip'
    else:
        summary['action_ablation'] = 'speed_only'
    case['summary_path'].write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        module.append_observation(case['target'], source, model, case['summary_path'],
                                  case['comparable'], case['objective'])
    assert len(case['target'].trials) == 1
