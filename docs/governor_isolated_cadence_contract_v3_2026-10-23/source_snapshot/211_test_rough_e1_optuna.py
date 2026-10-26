"""Check objective integrity and isolation of the new rough study."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
from tune_rough_e1_v16 import bootstrap, PILOT, sample_config
bootstrap()
from nino_rl.core import load_config
from nino_rl.tuning_objective import read_episode_rows
from nino_rl.tuning_trials import assert_trial_inputs, digest
from rough_e1_optuna_objective import make_contract, score, read_report

SETTINGS = ROOT / 'src/nino_rl/config/rough_e1_v16_optuna_objective.yaml'
SUMMARY = ROOT / 'rl_runs/rough_wall_recovery_v16/curriculum/blocks/block_0000/evaluation/original/20261009-111540-895313/summary.json'


@pytest.fixture
def evidence():
    base = load_config(PILOT / 'ppo.yaml')
    return base, make_contract(base, SETTINGS), read_episode_rows(SUMMARY.parent / 'episodes.csv')


def test_objective_independent_of_training_reward(evidence):
    base, contract, _ = evidence
    changed = deepcopy(base)
    changed['reward_v2']['time_penalty'] = .49
    changed['reward_v2']['slip_weight'] = .39
    changed['ppo']['learning_rate'] = .00009
    assert make_contract(changed, SETTINGS) == contract


def test_saved_reports_match_and_are_references(evidence):
    _, contract, _ = evidence
    for path in [SUMMARY,
        ROOT / 'rl_runs/rough_wall_recovery_v16/speed_matched_pi_0.70/20261009-120037-129118/summary.json',
        ROOT / 'rl_runs/rough_wall_recovery_v16/curriculum/baselines/stage_0/original/20261009-113412-803772/summary.json']:
        summary, result = read_report(path, contract)
        assert result['arrival_feasible']
        assert summary['episodes'] == 20


def test_fast_failure_cannot_win_by_low_vibration(evidence):
    _, contract, rows = evidence
    good = score(rows, contract)
    failed = deepcopy(rows)
    for row in failed:
        row.update(success=False, termination='timeout', time_seconds=.1,
                   rms_vertical_acceleration_m_s2=0, peak_vertical_acceleration_m_s2=0, rms_wheel_slip=0)
    result = score(failed, contract)
    assert result['score'] < -1000 < good['score']
    assert result['terms']['peak_acceleration'] == contract['term_cap']


def test_false_physical_arrival_rejected(evidence):
    _, contract, rows = evidence
    rows[0]['truth_endpoint_error_m'] = .21
    with pytest.raises(ValueError, match='outside the physical'):
        score(rows, contract)


def test_empty_or_incomplete_gates_rejected(evidence):
    _, contract, rows = evidence
    rows[0]['route_gates_passed'] = rows[0]['route_gates_total'] = 0
    with pytest.raises(ValueError, match='positive ordered'):
        score(rows, contract)
    rows[0]['route_gates_total'] = 10
    with pytest.raises(ValueError, match='incomplete ordered'):
        score(rows, contract)


def test_single_rollover_fails_despite_95_percent_arrival(evidence):
    _, contract, rows = evidence
    rows[0].update(success=False, termination='rollover')
    result = score(rows, contract)
    assert result['minimum_route_arrival_rate'] == .95
    assert not result['arrival_feasible']
    assert result['score'] < -1000


def test_time_slip_and_peak_have_independent_costs(evidence):
    _, contract, rows = evidence
    original = score(rows, contract)['score']
    for key, factor in [('time_seconds', 1.2), ('rms_wheel_slip', 1.3),
                        ('peak_vertical_acceleration_m_s2', 1.3)]:
        changed = deepcopy(rows)
        for row in changed:
            row[key] *= factor
        assert score(changed, contract)['score'] < original


def test_missing_seed_rejected(evidence):
    _, contract, rows = evidence
    with pytest.raises(ValueError, match='mismatched evaluation'):
        score(rows[:-1], contract)


def test_asset_tampering_rejected(tmp_path):
    asset = tmp_path / 'frozen.py'
    asset.write_text('original')
    contract = {'assets': {str(asset): digest(asset)}, 'initialization': {'source': None}}
    assert_trial_inputs(contract)
    asset.write_text('changed')
    with pytest.raises(ValueError, match='asset/code changed'):
        assert_trial_inputs(contract)


def test_sampling_cannot_change_geometry_or_action_meanings(evidence):
    import optuna
    base, _, _ = evidence
    study = optuna.create_study(sampler=optuna.samplers.RandomSampler(seed=7))
    sampled = sample_config(study.ask(), base)
    assert {k: v for k, v in sampled.items() if k not in ('reward_v2', 'ppo')} == {
        k: v for k, v in base.items() if k not in ('reward_v2', 'ppo')}
    assert sampled['ppo']['actor_layers'] == base['ppo']['actor_layers']
    assert sampled['ppo']['critic_layers'] == base['ppo']['critic_layers']
    assert sampled['ppo']['n_steps'] % sampled['ppo']['batch_size'] == 0
    assert 20480 % sampled['ppo']['n_steps'] == 0
