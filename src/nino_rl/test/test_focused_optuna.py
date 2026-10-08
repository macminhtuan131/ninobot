"""The focused search varies active learning settings and preserves the task."""
import importlib.util
from pathlib import Path

import optuna
import pytest

from nino_rl.core import load_config
from nino_rl.tuning_history import current_candidate

PACKAGE = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('focused_split', PACKAGE / 'scripts/tune_split_optuna.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('section,profile', [
    ('flat', 'combined_flat_pi_tracking'), ('rough', 'rough_e1_n1_s1_fixed')])
def test_focused_candidate_and_task_invariants(section, profile):
    base = load_config(PACKAGE / 'config' / (profile + '.yaml'))
    sampler = lambda trial: module.sample_config(trial, base, section=section, search_space='focused')
    candidate = current_candidate(base, sampler)
    assert sampler(optuna.trial.FixedTrial(candidate['params'])) == base
    assert set(candidate['params']) == {
        'learning_rate', 'ent_coef', 'n_steps', 'batch_size', 'n_epochs', 'clip_range',
        *('reward_v2.' + key for key in module.FOCUSED_REWARD_WEIGHTS[section]),
    }
    study = optuna.create_study(sampler=optuna.samplers.RandomSampler(seed=42))
    for _ in range(6):
        trial = study.ask()
        config = sampler(trial)
        assert {k: v for k, v in config.items() if k not in ('ppo', 'reward_v2')} == {
            k: v for k, v in base.items() if k not in ('ppo', 'reward_v2')}
        assert config['ppo']['n_steps'] % config['ppo']['batch_size'] == 0
        for key in ('gamma', 'gae_lambda', 'target_kl', 'initial_action_std', 'policy_kwargs'):
            assert config['ppo'].get(key) == base['ppo'].get(key)
        for key, value in base['reward_v2'].items():
            if key not in module.FOCUSED_REWARD_WEIGHTS[section]:
                assert config['reward_v2'][key] == value
        study.tell(trial, 0.)
