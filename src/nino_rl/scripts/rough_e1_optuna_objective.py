"""E1 evaluation score with fixed time, tracking, RMS/peak impact and slip."""
from copy import deepcopy
import hashlib
import json
from math import isfinite
from pathlib import Path
from statistics import mean

import yaml

from nino_rl.evaluation import benchmark_id
from nino_rl.tuning_objective import make_objective_contract, read_episode_rows, score_episodes

REVISION = 'rough_e1_physical_quality_v2'


def make_contract(base, settings_path, episodes=20, seed=10000):
    contract = make_objective_contract(base, settings_path, course='rough',
                                       episodes=episodes, seed=seed, randomized=False)
    if {item['route_id'] for item in contract['scenarios']} != {'E1'}:
        raise ValueError('This study must evaluate fixed E1 only')
    settings = yaml.safe_load(Path(settings_path).read_text())
    for key in ('peak_acceleration_weight', 'peak_acceleration_scale_m_s2'):
        value = float(settings[key])
        if not isfinite(value) or value <= 0:
            raise ValueError(f'{key} must be positive and finite')
        contract[key] = value
    if settings['maximum_rollover_rate'] != 0:
        raise ValueError('The validated zero-rollover requirement remains fixed')
    contract.update(revision=REVISION, maximum_rollover_rate=0.0,
        score_implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        settings_sha256=hashlib.sha256(Path(settings_path).read_bytes()).hexdigest())
    contract.pop('sha256')
    contract['sha256'] = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    return contract


def score(rows, contract):
    if contract['revision'] != REVISION:
        raise ValueError('Unsupported E1 objective contract')
    result = score_episodes(rows, contract)
    peaks = []
    for row in rows:
        value = float(row['peak_vertical_acceleration_m_s2'])
        if not isfinite(value) or value < 0:
            raise ValueError('Peak acceleration must be finite and nonnegative')
        if row['success'] and row['route_gates_total'] <= 0:
            raise ValueError('E1 arrival requires positive ordered route gate count')
        peaks.append(min(contract['term_cap'], value / contract['peak_acceleration_scale_m_s2'])
                     if row['success'] else contract['term_cap'])
    peak = mean(peaks)
    result['terms']['peak_acceleration'] = peak
    result['per_route']['E1']['terms']['peak_acceleration'] = peak
    cost = result['quality_cost'] + contract['peak_acceleration_weight'] * peak
    rollover_rate = mean(row['termination'] == 'rollover' for row in rows)
    feasible = result['arrival_feasible'] and rollover_rate <= contract['maximum_rollover_rate']
    deficit = max(0., (contract['minimum_physical_arrival_rate'] - result['minimum_route_arrival_rate'])
                  / contract['minimum_physical_arrival_rate'])
    result.update(quality_cost=cost, rollover_rate=rollover_rate, arrival_feasible=feasible,
        objective_revision=REVISION,
        score=(100. / (1. + cost) if feasible else
               -1000. - 1000. * deficit - 100. * cost / (1. + cost)))
    return result


def read_report(summary_path, contract):
    summary_path = Path(summary_path)
    summary = json.loads(summary_path.read_text())
    config = yaml.safe_load((summary_path.parent / 'config.yaml').read_text())
    if not summary.get('complete'):
        raise ValueError('Incomplete evaluation cannot receive a score')
    if summary['benchmark_id'] != contract['benchmark_id'] or benchmark_id(config) != contract['benchmark_id']:
        raise ValueError('Evaluation task differs from the fixed study benchmark')
    seeds = [item['seed'] for item in contract['scenarios']]
    if summary.get('evaluation_seeds') != seeds or summary['episodes'] != len(seeds):
        raise ValueError('Evaluation seeds/count differ from fixed scenarios')
    rows = read_episode_rows(summary_path.parent / 'episodes.csv')
    return summary, score(rows, contract)


def record(trial, summary_path, contract):
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != contract['score_implementation_sha256']:
        raise ValueError('Scoring implementation changed; use a new study')
    summary, result = read_report(summary_path, contract)
    if summary.get('controller') != 'ppo' or summary.get('action_ablation') != 'none':
        raise ValueError('Only full PPO evaluation can score a trial')
    (Path(summary_path).parent / 'optuna_objective.json').write_text(
        json.dumps(result, indent=2, allow_nan=False) + '\n')
    for key, value in dict(evaluation_objective=result, arrival_feasible=result['arrival_feasible'],
        success_rate=summary['success_rate'], evaluation_summary=str(summary_path)).items():
        trial.set_user_attr(key, deepcopy(value))
    print(f'Trial {trial.number}: score={result["score"]:.3f}, qualified={result["arrival_feasible"]}', flush=True)
    return result['score']
