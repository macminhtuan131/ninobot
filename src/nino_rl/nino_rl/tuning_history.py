"""Queue a measured starting candidate; keep incompatible history diagnostic."""
from copy import deepcopy
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import sqlite3

import optuna
from optuna.distributions import (FloatDistribution, CategoricalDistribution,
    distribution_to_json, json_to_distribution)

from nino_rl.core import load_config
from nino_rl.evaluation import benchmark_id
from nino_rl.tuning_objective import read_episode_rows, score_episodes
from nino_rl.tuning_trials import digest, assert_trial_inputs, verify_training_result


class CurrentParameters:
    """Run the real sampler with base values to record its exact search space."""
    def __init__(self, base):
        self.base, self.params, self.distributions = base, {}, {}

    def value(self, name):
        if name.startswith('reward_v2.'):
            return self.base['reward_v2'][name.split('.', 1)[1]]
        if name in ('challenge_entry_bonus', 'challenge_clear_bonus', 'challenge_goal_bonus'):
            return self.base['reward_v2'][name]
        ppo = self.base['ppo']
        if name == 'actor_width':
            return ppo['actor_layers'][0]
        if name == 'critic_width':
            return ppo['critic_layers'][0]
        if name.startswith('initial_action_std_'):
            index = ('speed', 'torque', 'steering').index(name.removeprefix('initial_action_std_'))
            return ppo['initial_action_std'][index]
        return ppo[name]

    def suggest_float(self, name, low, high, *, log=False):
        value = float(self.value(name))
        if not isfinite(value) or not low <= value <= high:
            raise ValueError(f'Current candidate {name}={value} is outside [{low}, {high}]; explicitly revise the search space')
        self.params[name] = value
        self.distributions[name] = FloatDistribution(low=low, high=high, log=log)
        return value

    def suggest_categorical(self, name, choices):
        value = self.value(name)
        if value not in choices:
            raise ValueError(f'Current candidate {name}={value} is outside choices {choices}')
        self.params[name] = value
        self.distributions[name] = CategoricalDistribution(choices)
        return value


def current_candidate(base, sampler):
    probe = CurrentParameters(base)
    if sampler(probe) != base:
        raise ValueError('Sampler cannot reproduce the exact current configuration')
    return {'revision': 'saved_results_v1', 'params': probe.params,
        'distributions': {name: json.loads(distribution_to_json(value))
                          for name, value in probe.distributions.items()},
        'base_config_sha256': hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest(),
        'meaning': 'parameters queued for new training; no inherited score'}


def read_saved_evaluation(path, objective):
    """Validate and rescore saved rows without modifying their directory."""
    path = Path(path).expanduser().resolve()
    summary = json.loads(path.read_text())
    config = load_config(path.parent / 'config.yaml')
    if not summary.get('complete'):
        raise ValueError('Evaluation is incomplete')
    if summary.get('benchmark_id') != objective['benchmark_id'] or benchmark_id(config) != objective['benchmark_id']:
        raise ValueError('Evaluation task/controller/estimator benchmark differs')
    seeds = [item['seed'] for item in objective['scenarios']]
    if summary.get('evaluation_seeds') != seeds or summary.get('episodes') != len(seeds):
        raise ValueError('Evaluation scenarios/count differ')
    if summary.get('phase') != config['curriculum']['fixed_phase'] or summary.get('randomized') != config['domain_randomization']['enabled']:
        raise ValueError('Evaluation metadata differs from its phase/randomization configuration')
    rows = read_episode_rows(path.parent / 'episodes.csv')
    result = score_episodes(rows, objective)
    files = {str(source): digest(source) for source in
             (path, path.parent / 'config.yaml', path.parent / 'episodes.csv')}
    return summary, result, files


def pi_reference(path, objective):
    path = Path(path).expanduser().resolve()
    summary = json.loads(path.read_text())
    if summary.get('controller') not in ('straight_pi_baseline', 'path_pi_baseline') or summary.get('model') is not None:
        raise ValueError(f'Not a PI reference: {path}')
    report = {'summary': str(path), 'role': 'PI reference only; never an Optuna trial',
        'baseline_speed_scale': summary.get('baseline_speed_scale'),
        'episodes': summary.get('episodes'), 'success_rate': summary.get('success_rate'),
        'on_time_success_rate': summary.get('on_time_success_rate'),
        'metrics': summary.get('metrics_all_episodes'), 'per_route': summary.get('per_route'),
        'benchmark_id': summary.get('benchmark_id'), 'summary_sha256': digest(path)}
    try:
        _, result, files = read_saved_evaluation(path, objective)
        report.update(task_and_scenarios_match=True, objective_breakdown=result, files=files)
    except (ValueError, KeyError, OSError) as error:
        report.update(task_and_scenarios_match=False, diagnostic_reason=str(error))
    return report


def read_history(path):
    """Read SQLite directly in read-only mode; never migrate the old database."""
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        path = path / 'study.db'
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        studies = []
        for study_id, name in connection.execute('SELECT study_id,study_name FROM studies'):
            attrs = {key: json.loads(value) for key, value in connection.execute(
                'SELECT key,value_json FROM study_user_attributes WHERE study_id=?', (study_id,))}
            directions = [direction for (direction,) in connection.execute(
                'SELECT direction FROM study_directions WHERE study_id=? ORDER BY objective', (study_id,))]
            trials = []
            for trial_id, number, state in connection.execute(
                'SELECT trial_id,number,state FROM trials WHERE study_id=? ORDER BY number', (study_id,)):
                values = [(value, kind) for value, kind in connection.execute(
                    'SELECT value,value_type FROM trial_values WHERE trial_id=? ORDER BY objective', (trial_id,))]
                distributions, params = {}, {}
                for key, value, encoded in connection.execute(
                    'SELECT param_name,param_value,distribution_json FROM trial_params WHERE trial_id=?', (trial_id,)):
                    distribution = json_to_distribution(encoded)
                    distributions[key] = distribution
                    params[key] = distribution.to_external_repr(value)
                user_attrs = {key: json.loads(value) for key, value in connection.execute(
                    'SELECT key,value_json FROM trial_user_attributes WHERE trial_id=?', (trial_id,))}
                trials.append({'number': number, 'state': state, 'values': values,
                    'params': params, 'distributions': distributions, 'user_attrs': user_attrs})
            studies.append({'name': name, 'attrs': attrs, 'directions': directions, 'trials': trials})
        return path, studies
    finally:
        connection.close()


def compatibility_reasons(source, comparable, objective, candidate):
    reasons = []
    if source['directions'] != ['MAXIMIZE']:
        reasons.append('Study direction is not single-objective maximize')
    if source['attrs'].get('evaluation_objective') != objective:
        reasons.append('Missing or different fixed evaluation objective; legacy scores cannot be imported')
    source_contract = source['attrs'].get('contract')
    if not isinstance(source_contract, dict) or source_contract.get('comparable_trials') != comparable:
        reasons.append('Missing or different comparable training conditions/checkpoint/budget/assets')
    if source['attrs'].get('starting_candidate') != candidate:
        reasons.append('Missing or different base/search-space contract')
    return reasons


def write_saved_results_plan(output, candidate, references, histories):
    output = Path(output)
    plan = {'candidate': candidate, 'pi_references': references,
            'history_sources': [str(Path(path).expanduser().resolve()) for path in histories],
            'history_policy': 'read-only audit; import only fully matching completed PPO trials'}
    path = output / 'saved_results_plan.json'
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError('Saved-results inputs changed; use a new --output directory')
    path.write_text(json.dumps(plan, indent=2, allow_nan=False) + '\n')
    return plan


def apply_saved_results(study, output, comparable, objective, candidate, histories, sampler):
    """Queue current params and import only scores backed by matching artifacts."""
    saved = study.user_attrs.get('starting_candidate')
    if saved is not None and saved != candidate:
        raise ValueError('Starting candidate/search space changed; use a new study')
    study.set_user_attr('starting_candidate', deepcopy(candidate))
    study.enqueue_trial(candidate['params'], user_attrs={
        'candidate_kind': 'current_configuration', 'inherited_score': False,
        'comparable_contract_sha256': comparable['sha256']}, skip_if_exists=True)
    report = {'imported': 0, 'sources': [], 'pi_scores_imported': 0,
              'starting_candidate': 'queued once; no score until trained/evaluated'}
    imported = {trial.user_attrs.get('history_key') for trial in study.trials}
    target_db = (Path(output) / 'study.db').resolve()
    for source_path in histories:
        path = Path(source_path).expanduser().resolve()
        if path.is_dir():
            path = path / 'study.db'
        entry = {'database': str(path), 'studies': []}
        report['sources'].append(entry)
        if path == target_db:
            entry['diagnostic_reason'] = 'Cannot import the target study into itself'
            continue
        try:
            _, sources = read_history(path)
        except (OSError, ValueError, sqlite3.Error) as error:
            entry['diagnostic_reason'] = str(error)
            continue
        for source in sources:
            states = {}
            for trial in source['trials']:
                states[trial['state']] = states.get(trial['state'], 0) + 1
            diagnostic = {'study': source['name'], 'states': states,
                'reasons': compatibility_reasons(source, comparable, objective, candidate),
                'trials': []}
            entry['studies'].append(diagnostic)
            completed = [trial for trial in source['trials'] if trial['state'] == 'COMPLETE'
                and len(trial['values']) == 1 and trial['values'][0][1] == 'FINITE'
                and trial['values'][0][0] is not None and isfinite(trial['values'][0][0])]
            if completed:
                choose = min if source['directions'] == ['MINIMIZE'] else max
                historical_best = choose(completed, key=lambda trial: trial['values'][0][0])
                diagnostic['historical_best_not_a_current_score'] = {
                    'trial': historical_best['number'], 'stored_score': historical_best['values'][0][0],
                    'params': historical_best['params']}
            if diagnostic['reasons']:
                diagnostic['role'] = 'incompatible diagnostic record; no scores imported'
                continue
            for trial in source['trials']:
                item = {'source_trial': trial['number'], 'state': trial['state']}
                diagnostic['trials'].append(item)
                key = json.dumps([str(path), source['name'], trial['number']])
                if key in imported:
                    item['status'] = 'already_imported'
                    continue
                if trial['state'] != 'COMPLETE':
                    item['status'] = 'diagnostic_only_incomplete_trial'
                    continue
                try:
                    if len(trial['values']) != 1 or trial['values'][0][1] != 'FINITE':
                        raise ValueError('Score is not a finite scalar')
                    value = trial['values'][0][0]
                    distributions = {name: json.loads(distribution_to_json(distribution))
                        for name, distribution in trial['distributions'].items()}
                    if distributions != candidate['distributions']:
                        raise ValueError('Trial parameter distributions differ')
                    attrs = trial['user_attrs']
                    summary, result, _ = read_saved_evaluation(attrs['evaluation_summary'], objective)
                    if summary.get('model') is None or summary.get('controller') != 'ppo':
                        raise ValueError('Historical score is not a full PPO policy evaluation')
                    if summary.get('action_ablation') != 'none':
                        raise ValueError('Historical evaluation used an action ablation')
                    evaluation_config = load_config(Path(attrs['evaluation_summary']).parent / 'config.yaml')
                    if evaluation_config.get('evaluation_baseline') or evaluation_config.get('evaluation_speed_only'):
                        raise ValueError('Evaluation config is baseline/ablated rather than full PPO')
                    if Path(summary['model']).resolve() != Path(attrs['model']).resolve():
                        raise ValueError('Evaluated model differs from the trial model')
                    if not isfinite(value) or not isclose(value, result['score'], rel_tol=1e-10, abs_tol=1e-10):
                        raise ValueError('Stored score differs from the fixed objective recomputation')
                    if attrs.get('evaluation_objective') != result:
                        raise ValueError('Stored objective breakdown differs')
                    if attrs.get('arrival_feasible') != result['arrival_feasible']:
                        raise ValueError('Stored physical-arrival qualification differs')
                    trial_config = load_config(Path(attrs['directory']) / 'trial.yaml')
                    if trial_config != sampler(optuna.trial.FixedTrial(trial['params'])):
                        raise ValueError('Historical trial configuration differs from its sampled parameters')
                    expected_training = verify_training_result(attrs['model'], trial_config, comparable)
                    if attrs.get('comparable_training') != expected_training:
                        raise ValueError('Training evidence differs from the comparable contract')
                    assert_trial_inputs(comparable)
                    attrs = deepcopy(attrs)
                    attrs.update(history_key=key, history_database=str(path), history_study=source['name'],
                        history_trial_number=trial['number'], inherited_score=True)
                    study.add_trial(optuna.trial.create_trial(value=value,
                        params=trial['params'], distributions=trial['distributions'], user_attrs=attrs))
                    imported.add(key)
                    report['imported'] += 1
                    item['status'] = 'imported_matching_completed_ppo_trial'
                except (ValueError, KeyError, OSError, TypeError) as error:
                    item.update(status='diagnostic_only_rejected', reason=str(error))
    (Path(output) / 'history_import_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Current parameter candidate queued; imported {report['imported']} compatible historical PPO trials; "
          'PI references are not Optuna observations.', flush=True)
    return report
