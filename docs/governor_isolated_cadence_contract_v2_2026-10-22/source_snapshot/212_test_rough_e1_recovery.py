"""Recovery appends one comparable observation and keeps the original FAIL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import optuna
from recover_rough_e1_v16 import append_observation


def test_recovery_preserves_failure_and_is_idempotent():
    study = optuna.create_study(direction='maximize')
    study.add_trial(optuna.trial.create_trial(state=optuna.trial.TrialState.FAIL,
        params={'x': .2}, distributions={'x': optuna.distributions.FloatDistribution(.1, .5)},
        user_attrs={'model': '/saved/model.zip', 'directory': '/saved/trial_0000'}))
    source = study.trials[0]
    number, added = append_observation(study, source, {'arrival_feasible': True}, 12.3, 'recovery-key')
    assert added and number == 1
    assert study.trials[0] == source
    assert study.trials[0].state == optuna.trial.TrialState.FAIL
    assert study.trials[1].state == optuna.trial.TrialState.COMPLETE
    assert study.trials[1].value == 12.3
    assert study.trials[1].params == source.params
    assert study.trials[1].distributions == source.distributions
    assert study.trials[1].user_attrs['recovery_of_trial'] == 0
    assert append_observation(study, source, {}, 12.3, 'recovery-key') == (1, False)
    assert len(study.trials) == 2
