import importlib.util
from pathlib import Path
import optuna
import pytest
from test_recover_focused_optuna import abandoned_study
from nino_rl.core import load_config
PACKAGE = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('startup_recover', PACKAGE / 'scripts/recover_focused_optuna.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def failed_startup(case, log):
    directory, study, trial = case
    run = directory / 'trial_0001'
    run.mkdir()
    (run / 'train.log').write_text(log)
    trial.set_user_attr('directory', str(run))
    study.tell(trial, state=optuna.trial.TrialState.FAIL)
    return run

def test_startup_failure_queue_preserves_scores_and_is_idempotent(abandoned_study):
    directory, study, trial = abandoned_study
    failed_startup(abandoned_study, 'TimeoutError: Missing /effort_drive/get_parameters')
    backup = module.retry_startup(directory, 'flat', trial.number)
    assert backup.is_file()
    assert study.trials[0].value == 22.0
    assert study.trials[1].state == optuna.trial.TrialState.FAIL
    assert study.trials[2].system_attrs['fixed_params'] == trial.params
    assert module.retry_startup(directory, 'flat', trial.number) is None
    assert len(study.trials) == 3

@pytest.mark.parametrize('failure', ['evaluation', 'partial_model'])
def test_other_failures_are_not_silently_retried(abandoned_study, failure):
    directory, study, trial = abandoned_study
    log = 'RuntimeError: clock diverged' if failure == 'evaluation' else 'TimeoutError: Missing /effort_drive/get_parameters'
    run = failed_startup(abandoned_study, log)
    if failure == 'partial_model':
        path = run / 'train/run'
        path.mkdir(parents=True)
        (path / 'nino_ppo_interrupted.zip').write_bytes(b'preserved')
    with pytest.raises(ValueError, match='Only a known'):
        module.retry_startup(directory, 'flat', trial.number)
    assert len(study.trials) == 2
