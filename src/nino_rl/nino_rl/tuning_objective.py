"""Fixed physical-task evaluation, independent of PPO's training reward."""
from copy import deepcopy
import csv
import hashlib
import json
from math import isfinite
from pathlib import Path
from statistics import mean

import numpy as np
import yaml

from nino_rl.evaluation import benchmark_id, prepare_evaluation_config
from nino_rl.routes import RouteSet, OrderedPathTracker, route_budget

REVISION = 'physical_arrival_quality_v1'
TERMS = ('duration', 'lateness', 'path_error', 'vibration', 'slip')


def _positive(value, name):
    value = float(value)
    if not isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return value


def make_objective_contract(base, settings_path, *, course, episodes, seed, randomized=False):
    """Resolve task targets once, before Optuna can change reward weights."""
    if base.get('reward_pose_source') != 'ground_truth':
        raise ValueError('Optuna requires independent ground-truth physical arrival scoring')
    if episodes < 1 or seed < 0:
        raise ValueError('Evaluation count must be positive and seed nonnegative')
    settings = yaml.safe_load(Path(settings_path).read_text())
    if settings['revision'] != REVISION:
        raise ValueError('Unsupported Optuna evaluation objective revision')
    arrival = _positive(settings['minimum_physical_arrival_rate'], 'minimum_physical_arrival_rate')
    if arrival > 1:
        raise ValueError('minimum_physical_arrival_rate must be in (0,1]')
    weights = {key: _positive(settings['weights'][key], f'weights.{key}') for key in TERMS}
    cap = _positive(settings['term_cap'], 'term_cap')
    scales = {key: _positive(settings['scales'][course][key], key)
              for key in ('path_rmse_m', 'vibration_m_s2', 'slip')}
    evaluation = prepare_evaluation_config(base, randomized=randomized)
    routes = RouteSet(evaluation)
    scenarios, targets = [], {}
    rng = np.random.default_rng(0)
    active_ids = ({routes.settings['fixed_route']} if routes.settings.get('fixed_route') else
                  {item['id'] for item in routes.routes}) if routes.enabled else {'straight'}
    for index in range(episodes):
        route = routes.select(rng, index) if routes.enabled else None
        route_id = route['id'] if route else 'straight'
        target = (route_budget(evaluation, OrderedPathTracker(route['waypoints'], routes.settings).total_length)[0]
                  if route else evaluation['target_finish_seconds'])
        targets[route_id] = _positive(settings.get('time_targets_seconds', {}).get(route_id, target),
                                      f'time target {route_id}')
        scenarios.append({'seed': seed + index, 'route_id': route_id})
    if set(targets) != active_ids:
        raise ValueError('Evaluation must cover every active route; increase --eval-episodes')
    contract = {'revision': REVISION, 'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'evaluator_sha256': hashlib.sha256(Path(__file__).with_name('evaluation.py').read_bytes()).hexdigest(),
                'benchmark_id': benchmark_id(evaluation), 'scenarios': scenarios,
                'minimum_physical_arrival_rate': arrival, 'weights': weights,
                'term_cap': cap, 'scales': scales, 'time_targets_seconds': targets,
                'arrival_geometry': {'task': base.get('task'),
                    'circle_radius_m': float(base['goal_tolerance_m']),
                    'ordered_route_gates': routes.enabled},
                'aggregation': 'equal route means; failed episode terms charged at maximum',
                'ranking': 'feasible > 0; infeasible < -1000',
                'physical_scoring': 'unchanged task geometry, ground-truth arrival and ordered route gates'}
    contract['sha256'] = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    return contract


def read_episode_rows(path):
    rows = []
    with Path(path).open(newline='') as stream:
        for source in csv.DictReader(stream):
            row = {}
            for key, value in source.items():
                if value is None:
                    raise ValueError('Incomplete episode CSV row')
                if value.lower() in ('true', 'false'):
                    row[key] = value.lower() == 'true'
                elif not value or value.lower() == 'none':
                    row[key] = None
                else:
                    try:
                        row[key] = json.loads(value)
                    except json.JSONDecodeError:
                        row[key] = value
            rows.append(row)
    return rows


def score_episodes(rows, contract):
    expected = [(item['seed'], item['route_id']) for item in contract['scenarios']]
    observed = [(row['seed'], row.get('route_id') or 'straight') for row in rows]
    if len(observed) != len(set(observed)) or sorted(observed) != sorted(expected):
        raise ValueError('Incomplete, duplicated or mismatched evaluation scenarios')
    groups = {route: [] for route in contract['time_targets_seconds']}
    cap, scales = contract['term_cap'], contract['scales']
    for row in rows:
        if row.get('reward_pose_source') != 'ground_truth':
            raise ValueError('Episode arrival was not scored independently using physical pose')
        if not isinstance(row['success'], bool) or row['success'] != (row['termination'] == 'success'):
            raise ValueError('Inconsistent physical arrival/termination record')
        geometry = contract['arrival_geometry']
        if row['success']:
            if geometry['task'] != 'rocky_tracking':
                endpoint = float(row['truth_endpoint_error_m'])
                if not isfinite(endpoint) or not 0 <= endpoint <= geometry['circle_radius_m'] + 1e-6:
                    raise ValueError('Claimed arrival is outside the physical goal circle')
            if geometry['ordered_route_gates'] and row['route_gates_passed'] != row['route_gates_total']:
                raise ValueError('Claimed physical arrival has incomplete ordered route gates')
        values = {key: float(row[key]) for key in ('time_seconds', 'truth_path_rmse_m',
                     'rms_vertical_acceleration_m_s2', 'rms_wheel_slip')}
        if any(not isfinite(value) or value < 0 for value in values.values()):
            raise ValueError('Objective measurements must be finite and nonnegative')
        route = row.get('route_id') or 'straight'
        ratio = values['time_seconds'] / contract['time_targets_seconds'][route]
        path = values['truth_path_rmse_m'] / scales['path_rmse_m']
        terms = {'duration': min(cap, ratio),
                 'lateness': min(cap, max(0., ratio - 1.)) + float(ratio > 1.),
                 'path_error': min(cap, max(0., path - 1.)) + .25 * min(cap, path),
                 'vibration': min(cap, values['rms_vertical_acceleration_m_s2'] / scales['vibration_m_s2']),
                 'slip': min(cap, values['rms_wheel_slip'] / scales['slip'])}
        if not row['success']:
            # A failed/stationary robot cannot earn comfort points by doing nothing.
            terms = dict(duration=cap, lateness=cap+1., path_error=1.25*cap, vibration=cap, slip=cap)
        groups[route].append((row['success'], terms))
    per_route = {}
    for route, samples in groups.items():
        per_route[route] = {'episodes': len(samples), 'physical_arrival_rate': mean(item[0] for item in samples),
            'terms': {term: mean(item[1][term] for item in samples) for term in TERMS}}
    terms = {term: mean(report['terms'][term] for report in per_route.values()) for term in TERMS}
    cost = sum(contract['weights'][term] * terms[term] for term in TERMS)
    minimum = contract['minimum_physical_arrival_rate']
    worst_rate = min(report['physical_arrival_rate'] for report in per_route.values())
    feasible = worst_rate >= minimum
    deficit = max(0., (minimum - worst_rate) / minimum)
    score = 100. / (1. + cost) if feasible else -1000. - 1000.*deficit - 100.*cost/(1.+cost)
    return {'score': score, 'arrival_feasible': feasible, 'minimum_route_arrival_rate': worst_rate,
            'quality_cost': cost, 'terms': terms, 'per_route': per_route,
            'objective_sha256': contract['sha256'], 'objective_revision': REVISION}


def record_trial_objective(trial, summary_path, contract):
    if hashlib.sha256(Path(__file__).with_name('evaluation.py').read_bytes()).hexdigest() != contract['evaluator_sha256']:
        raise ValueError('Evaluation implementation changed during tuning; use a new study')
    directory = Path(summary_path).parent
    summary = json.loads(Path(summary_path).read_text())
    config = yaml.safe_load((directory / 'config.yaml').read_text())
    if not summary.get('complete'):
        raise ValueError('Incomplete evaluation cannot receive an Optuna score')
    if summary['benchmark_id'] != contract['benchmark_id'] or benchmark_id(config) != contract['benchmark_id']:
        raise ValueError('Evaluation task changed from the fixed Optuna objective contract')
    rows = read_episode_rows(directory / 'episodes.csv')
    if summary['episodes'] != len(rows) or summary.get('evaluation_seeds') != [item['seed'] for item in contract['scenarios']]:
        raise ValueError('Summary scenario coverage differs from the fixed objective')
    result = score_episodes(rows, contract)
    (directory / 'optuna_objective.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    trial.set_user_attr('evaluation_objective', result)
    trial.set_user_attr('arrival_feasible', result['arrival_feasible'])
    trial.set_user_attr('success_rate', summary['success_rate'])
    for name in ('time_seconds', 'truth_path_rmse_m', 'rms_vertical_acceleration_m_s2', 'rms_wheel_slip'):
        if name in summary.get('metrics_all_episodes', {}):
            trial.set_user_attr(name, summary['metrics_all_episodes'][name]['mean'])
    trial.set_user_attr('evaluation_summary', str(Path(summary_path).resolve()))
    print(f"Trial {trial.number}: arrival feasible={result['arrival_feasible']}; "
          f"worst route={result['minimum_route_arrival_rate']:.3f}; quality cost={result['quality_cost']:.3f}; "
          f"score={result['score']:.3f}", flush=True)
    return result['score']


def bind_study_objective(study, contract, output):
    """Do not mix legacy scores or objective implementations in one study."""
    saved = study.user_attrs.get('evaluation_objective')
    if saved != contract and (saved is not None or study.trials):
        raise ValueError('Evaluation objective changed or this is a legacy study; use a new --output directory')
    study.set_user_attr('evaluation_objective', deepcopy(contract))
    (Path(output) / 'evaluation_objective.json').write_text(json.dumps(contract, indent=2)+'\n')


def qualified_best_trial(study, output):
    best = study.best_trial
    if not best.user_attrs.get('arrival_feasible', False):
        (Path(output) / 'best_infeasible.json').write_text(json.dumps(
            {'trial': best.number, 'score': best.value, 'params': best.params,
             'evaluation_objective': best.user_attrs.get('evaluation_objective'),
             'reason': 'No trial met every route physical-arrival requirement'}, indent=2)+'\n')
        print('No arrival-qualified trial. Inspect best_infeasible.json; no best policy/config exported.', flush=True)
        return None
    return best
