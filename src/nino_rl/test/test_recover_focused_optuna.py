import importlib.util
import json
from pathlib import Path

import optuna
import pytest

script = Path(__file__).parents[1] / 'scripts/recover_focused_optuna.py'
spec = importlib.util.spec_from_file_location('recover_focused', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def abandoned_study(tmp_path):
    study = optuna.create_study(study_name='combined_flat_section', direction='maximize',
                               storage='sqlite:///' + str(tmp_path / 'study.db'))
    study.set_user_attr('starting_candidate', {'params': {'learning_rate': .05}})
    first = study.ask()
    first.suggest_float('learning_rate', .01, .1)
    study.tell(first, 22.)
    second = study.ask()
    second.suggest_float('learning_rate', .01, .1)
    (tmp_path / 'trial_plan.json').write_text(json.dumps({'trials': {
        'assets': {}, 'initialization': {'source': None}}}))
    return tmp_path, study, second


def test_recovery_retains_scores_retries_parameters_and_is_idempotent(abandoned_study):
    directory, study, interrupted = abandoned_study
    result = module.recover(directory, 'flat', apply=True)
    assert result['completed'] == 1 and result['additional_trials_to_target'] == 11
    assert Path(result['backup']).is_file()
    complete, failed, waiting = study.get_trials()
    assert complete.value == 22.
    assert failed.state == optuna.trial.TrialState.FAIL and failed.value is None
    assert waiting.state == optuna.trial.TrialState.WAITING and waiting.value is None
    assert waiting.system_attrs['fixed_params'] == interrupted.params
    assert waiting.user_attrs['shutdown_retry_of'] == interrupted.number
    assert module.recover(directory, 'flat', apply=True)['interrupted_trials'] == []
    assert len(study.get_trials()) == 3


def test_preview_does_not_change_trial_states(abandoned_study):
    directory, study, _ = abandoned_study
    result = module.recover(directory, 'flat')
    assert not result['applied'] and result['backup'] is None
    assert study.get_trials()[-1].state == optuna.trial.TrialState.RUNNING
    assert len(study.get_trials()) == 2


def test_incomplete_sampling_is_rejected_without_failing_trial(abandoned_study):
    directory, study, _ = abandoned_study
    study.set_user_attr('starting_candidate', {'params': {'learning_rate': .05, 'ent_coef': .001}})
    with pytest.raises(ValueError, match='incomplete sampled'):
        module.recover(directory, 'flat', apply=True)
    assert study.get_trials()[-1].state == optuna.trial.TrialState.RUNNING
