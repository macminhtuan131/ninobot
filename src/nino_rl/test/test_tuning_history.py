"""Saved observations must remain distinct from references and queued params."""
from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path
import sqlite3

import gymnasium as gym
import numpy as np
import optuna
import pytest
from stable_baselines3 import PPO
import torch
import yaml

from nino_rl.core import load_config
from nino_rl.evaluation import benchmark_id, prepare_evaluation_config
from nino_rl.policies import policy_spec
from nino_rl.training_contract import training_contract
from nino_rl.trajectory_metrics import write_csv
from nino_rl.tuning_trials import make_trial_contract, train_command, verify_training_result, digest
from nino_rl.tuning_objective import make_objective_contract, score_episodes
from nino_rl.tuning_history import (current_candidate, pi_reference, read_history,
    apply_saved_results, compatibility_reasons, write_saved_results_plan)

PACKAGE = Path(__file__).parents[1]


def tuner(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('section,profile', [('flat','combined_flat_pi_tracking'), ('rough','rough_e1_n1_s1_fixed')])
def test_current_candidate_reproduces_real_course_configuration_exactly(section, profile):
    base = load_config(PACKAGE / 'config' / (profile + '.yaml'))
    for name in ('tune_split_optuna', 'tune_split_optuna_rough_resume'):
        module = tuner(name)
        sampler = lambda trial: module.sample_config(trial, base, section=section)
        candidate = current_candidate(base, sampler)
        assert sampler(optuna.trial.FixedTrial(candidate['params'])) == base
        assert candidate['params']['learning_rate'] == base['ppo']['learning_rate']
        assert candidate['params']['n_steps'] == base['ppo']['n_steps']


def test_combined_architecture_and_rocky_candidates_are_exact():
    module = tuner('tune_combined_optuna')
    base = load_config(PACKAGE / 'config/combined_course.yaml')
    for fresh in (False, True):
        sampler = lambda trial: module.sample_config(trial, base, from_scratch=fresh)
        candidate = current_candidate(base, sampler)
        assert sampler(optuna.trial.FixedTrial(candidate['params'])) == base
    module = tuner('tune_rocky_optuna')
    base = load_config(PACKAGE / 'config/rocky_tracking.yaml')
    assert current_candidate(base, lambda trial: module.sample_config(trial, base))['params']['clip_range'] == base['ppo']['clip_range']


def test_out_of_range_current_value_is_not_silently_clipped_or_omitted():
    module = tuner('tune_split_optuna')
    base = load_config(PACKAGE / 'config/combined_flat_pi_tracking.yaml')
    base['ppo']['learning_rate'] = .1
    with pytest.raises(ValueError, match='outside'):
        current_candidate(base, lambda trial: module.sample_config(trial, base, section='flat'))


class OfflineEnv(gym.Env):
    observation_space = gym.spaces.Box(-5., 5., (300,), dtype=np.float32)
    action_space = gym.spaces.Box(-1., 1., (2,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return np.zeros(300, dtype=np.float32), {}

    def step(self, action):
        return np.zeros(300, dtype=np.float32), 1., True, False, {}


@pytest.fixture
def historical_case(tmp_path):
    torch.set_num_threads(1)
    base = load_config(PACKAGE / 'config/combined_flat_pi_tracking.yaml')
    base['ppo']['n_steps'] = base['ppo']['batch_size'] = 8
    world = tmp_path / 'world.sdf'
    world.write_text('<sdf><world name="combined_flat_section"/></sdf>')
    script = tmp_path / 'tuner.py'
    script.write_text('# fixed test sampler')
    comparable = make_trial_contract(tmp_path, base, world_path=world, model_path=None,
        rollouts=[8], requested_steps=8, device='cpu', tuner_path=script)
    objective = make_objective_contract(base, PACKAGE / 'config/optuna_objective.yaml',
        course='flat', episodes=2, seed=61000)
    def sampler(trial):
        config = deepcopy(base)
        config['ppo']['learning_rate'] = trial.suggest_float('learning_rate', 1e-5, 7e-5, log=True)
        return config
    candidate = current_candidate(base, sampler)
    trial_dir = tmp_path / 'old/trial_0000'
    run = trial_dir / 'train/run'
    evaluation = trial_dir / 'eval/run'
    run.mkdir(parents=True)
    evaluation.mkdir(parents=True)
    (trial_dir / 'trial.yaml').write_text(yaml.safe_dump(base))
    (run / 'ppo.yaml').write_text(yaml.safe_dump(base))
    (run / 'run_metadata.json').write_text(json.dumps({'argv': train_command(comparable, trial_dir/'trial.yaml', run)}))
    policy, kwargs = policy_spec(base)
    model = PPO(policy, OfflineEnv(), policy_kwargs=kwargs, n_steps=8, batch_size=8, device='cpu', seed=42)
    model.nino_training_contract = training_contract(base)
    model.learn(8)
    model_path = run / 'nino_ppo_final.zip'
    model.save(model_path)
    evaluation_config = prepare_evaluation_config(base)
    (evaluation / 'config.yaml').write_text(yaml.safe_dump(evaluation_config))
    rows = [dict(seed=item['seed'],route_id=None,reward_pose_source='ground_truth',success=True,
        termination='success',truth_endpoint_error_m=.15,time_seconds=20.,truth_path_rmse_m=.03,
        rms_vertical_acceleration_m_s2=1.5,rms_wheel_slip=.10) for item in objective['scenarios']]
    write_csv(evaluation / 'episodes.csv', rows)
    result = score_episodes(rows, objective)
    summary = {'complete':True,'benchmark_id':benchmark_id(evaluation_config),'episodes':2,
        'evaluation_seeds':[61000,61001],'phase':1,'randomized':False,
        'controller':'ppo','model':str(model_path),'action_ablation':'none','success_rate':1.}
    summary_path = evaluation / 'summary.json'
    summary_path.write_text(json.dumps(summary))
    source_path = tmp_path / 'old/study.db'
    source = optuna.create_study(study_name='old',direction='maximize',storage='sqlite:///'+str(source_path))
    source.set_user_attr('contract',{'comparable_trials':comparable})
    source.set_user_attr('evaluation_objective',objective)
    source.set_user_attr('starting_candidate',candidate)
    attrs = {'directory':str(trial_dir),'model':str(model_path),'evaluation_summary':str(summary_path),
        'evaluation_objective':result,'arrival_feasible':result['arrival_feasible'],
        'comparable_training':verify_training_result(model_path,base,comparable)}
    distributions = {key:optuna.distributions.json_to_distribution(json.dumps(value))
        for key,value in candidate['distributions'].items()}
    source.add_trial(optuna.trial.create_trial(value=result['score'],params=candidate['params'],
        distributions=distributions,user_attrs=attrs))
    output = tmp_path / 'new'
    output.mkdir()
    target = optuna.create_study(direction='maximize')
    return dict(base=base,comparable=comparable,objective=objective,candidate=candidate,
        sampler=sampler,source=source,source_path=source_path,output=output,target=target,summary_path=summary_path)


def apply(case):
    return apply_saved_results(case['target'],case['output'],case['comparable'],case['objective'],
        case['candidate'],[case['source_path']],case['sampler'])


def test_matching_score_imported_once_and_queue_never_invents_a_result(historical_case):
    case = historical_case
    before = digest(case['source_path'])
    report = apply(case)
    assert report['imported'] == 1 and report['pi_scores_imported'] == 0
    waiting, completed = case['target'].trials
    assert waiting.state == optuna.trial.TrialState.WAITING and waiting.value is None
    assert waiting.system_attrs['fixed_params'] == case['candidate']['params']
    assert completed.value == case['source'].best_value
    assert completed.user_attrs['inherited_score']
    assert apply(case)['imported'] == 0 and len(case['target'].trials) == 2
    assert digest(case['source_path']) == before


@pytest.mark.parametrize('field', ['evaluation_objective','contract','starting_candidate'])
def test_incompatible_or_legacy_conditions_are_diagnostic_only(historical_case, field):
    case = historical_case
    case['source'].set_user_attr(field,{})
    report = apply(case)
    assert report['imported'] == 0 and len(case['target'].trials) == 1
    assert report['sources'][0]['studies'][0]['reasons']
    assert case['source'].best_value is not None


@pytest.mark.parametrize('change', ['score','pi','ablation','seeds','model','partial_training','params'])
def test_false_or_mismatched_observations_are_never_imported(historical_case, change):
    case = historical_case
    summary = json.loads(case['summary_path'].read_text())
    if change == 'score':
        with (case['summary_path'].parent/'episodes.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        rows[0]['time_seconds'] = '21.0'
        write_csv(case['summary_path'].parent/'episodes.csv',rows)
    elif change == 'pi':
        summary.update(controller='straight_pi_baseline',model=None)
    elif change == 'ablation':
        summary['action_ablation'] = 'speed_only'
    elif change == 'seeds':
        summary['evaluation_seeds'] = [1,2]
    elif change == 'model':
        summary['model'] = '/missing/model.zip'
    elif change == 'partial_training':
        path = Path(case['source'].best_trial.user_attrs['model'])
        model = PPO.load(path,device='cpu')
        model.num_timesteps = 7
        model.save(path)
    elif change == 'params':
        path = Path(case['source'].best_trial.user_attrs['directory'])/'trial.yaml'
        config = load_config(path)
        config['ppo']['learning_rate'] *= .5
        path.write_text(yaml.safe_dump(config))
    case['summary_path'].write_text(json.dumps(summary))
    report = apply(case)
    assert report['imported'] == 0
    assert report['sources'][0]['studies'][0]['trials'][0]['status'] == 'diagnostic_only_rejected'


def test_pi_references_are_comparisons_not_ppo_observations(historical_case):
    case = historical_case
    summary = json.loads(case['summary_path'].read_text())
    summary.update(controller='straight_pi_baseline',model=None,baseline_speed_scale=.78)
    case['summary_path'].write_text(json.dumps(summary))
    config_path = case['summary_path'].parent/'config.yaml'
    config = load_config(config_path)
    config['evaluation_baseline'] = True
    config_path.write_text(yaml.safe_dump(config))
    reference = pi_reference(case['summary_path'],case['objective'])
    assert reference['task_and_scenarios_match'] and reference['baseline_speed_scale'] == .78
    assert 'never an Optuna trial' in reference['role']
    assert apply(case)['imported'] == 0
    summary['evaluation_seeds'] = [61001]
    case['summary_path'].write_text(json.dumps(summary))
    assert not pi_reference(case['summary_path'],case['objective'])['task_and_scenarios_match']


def test_read_only_missing_database_does_not_create_one(tmp_path):
    path = tmp_path/'absent.db'
    with pytest.raises(sqlite3.OperationalError):
        read_history(path)
    assert not path.exists()


def test_matching_failed_policy_score_is_still_useful_to_sampler(historical_case):
    case = historical_case
    from nino_rl.tuning_objective import read_episode_rows
    path = case['summary_path'].parent/'episodes.csv'
    rows = read_episode_rows(path)
    for row in rows:
        row.update(success=False,termination='timeout')
    write_csv(path,rows)
    summary = json.loads(case['summary_path'].read_text())
    summary['success_rate'] = 0.
    case['summary_path'].write_text(json.dumps(summary))
    result = score_episodes(rows,case['objective'])
    original = case['source'].best_trial
    attrs = deepcopy(original.user_attrs)
    attrs.update(evaluation_objective=result,arrival_feasible=False)
    case['source'].add_trial(optuna.trial.create_trial(value=result['score'],
        params=original.params,distributions=original.distributions,user_attrs=attrs))
    report = apply(case)
    # The original positive value no longer matches the edited fixture; only
    # the accurately recorded failed-policy observation can be imported.
    assert report['imported'] == 1
    assert case['target'].best_value < -1000
    assert not case['target'].best_trial.user_attrs['arrival_feasible']
