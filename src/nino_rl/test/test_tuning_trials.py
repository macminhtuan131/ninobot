"""Verify trial comparability using real PPO checkpoints and local fixtures."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import pytest
import torch
from stable_baselines3 import PPO
import yaml

from nino_rl.core import load_config
from nino_rl.control_v2 import action_size
from nino_rl.model_transfer import initialize_actor
from nino_rl.policies import policy_spec
from nino_rl.training_contract import training_contract, validate_resume
from nino_rl.tuning_trials import (world_assets, make_trial_contract, write_trial_plan,
    validate_trial_config, assert_trial_inputs, running_worlds, train_command,
    verify_training_result, audit_actor_initialization)

PACKAGE = Path(__file__).parents[1]


class OfflineEnv(gym.Env):
    def __init__(self, config):
        self.observation_space = gym.spaces.Box(-5., 5.,
            (60 * int(config['policy_v2']['history_frames']),), dtype=np.float32)
        self.action_space = gym.spaces.Box(-1., 1., (action_size(config),), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return np.zeros(self.observation_space.shape, dtype=np.float32), {}

    def step(self, action):
        return np.zeros(self.observation_space.shape, dtype=np.float32), 1., True, False, {}


def model(config):
    torch.set_num_threads(1)
    policy, kwargs = policy_spec(config)
    return PPO(policy, OfflineEnv(config), policy_kwargs=kwargs,
               n_steps=8, batch_size=8, seed=int(config['seed']), device='cpu')


@pytest.fixture
def case(tmp_path):
    base = load_config(PACKAGE / 'config/combined_flat_pi_tracking.yaml')
    world = tmp_path / 'selected.sdf'
    mesh = tmp_path / 'selected.stl'
    mesh.write_bytes(b'mesh-v1')
    world.write_text(f'<sdf><world name="{base["world_name"]}"><model><link>'
        '<collision><geometry><mesh><uri>selected.stl</uri></mesh></geometry>'
        '</collision></link></model></world></sdf>')
    tuner = tmp_path / 'tuner.py'
    tuner.write_text('# test tuner')
    contract = make_trial_contract(tmp_path, base, world_path=world, model_path=None,
        rollouts=[1024, 2048], requested_steps=20000, device='cpu', tuner_path=tuner)
    return base, contract, mesh


def test_budget_is_aligned_for_all_sampled_rollouts(case):
    _, contract, _ = case
    assert contract['training_steps'] == 20480
    for rollout in contract['rollout_sizes']:
        assert contract['training_steps'] % rollout == 0
    command = train_command(contract, 'trial.yaml', 'train')
    assert command[command.index('--timesteps') + 1] == '20480'
    assert '--resume' not in command and '--init-model' not in command


def test_actual_world_mesh_is_fingerprinted_and_mutation_rejected(case):
    _, contract, mesh = case
    assert str(mesh) in contract['assets']
    assert_trial_inputs(contract)
    mesh.write_bytes(b'mesh-v2')
    with pytest.raises(ValueError, match='asset/code changed'):
        assert_trial_inputs(contract)
    with pytest.raises(ValueError, match='world names'):
        world_assets(mesh.parent, contract['world'], 'wrong_world')


@pytest.mark.parametrize('key,value', [
    ('seed', 19), ('goal_tolerance_m', .8), ('reward_pose_source', 'wheel_odometry'),
    ('odometry_assistance', {'enabled': False}),
    ('drive_controller', {'parameters': {'pi_integrator_profile': 'legacy'}})])
def test_trial_cannot_change_fixed_task_controller_estimator_or_seed(case, key, value):
    base, contract, _ = case
    changed = deepcopy(base)
    changed[key] = value
    with pytest.raises(ValueError, match='Trial changed'):
        validate_trial_config(changed, contract)


def test_reward_and_ppo_search_are_allowed_but_resume_is_not(case):
    base, contract, _ = case
    changed = deepcopy(base)
    changed['reward_v2']['time_penalty'] *= 10
    changed['ppo']['learning_rate'] *= 2
    changed['ppo']['n_steps'] = 1024
    validate_trial_config(changed, contract)
    source = SimpleNamespace(nino_training_contract=training_contract(base))
    with pytest.raises(ValueError, match='contract differs'):
        validate_resume(source, changed)
    for key, value in [('drive_controller', {'parameters': {'pi_integrator_profile': 'legacy'}}),
                       ('odometry_assistance', {'enabled': False})]:
        changed = deepcopy(base)
        changed[key] = value
        with pytest.raises(ValueError, match='contract differs'):
            validate_resume(source, changed)
    changed = deepcopy(base)
    changed['ppo']['n_steps'] = 333
    with pytest.raises(ValueError, match='rollout size'):
        validate_trial_config(changed, contract)


def test_plan_cannot_be_silently_overwritten(case, tmp_path):
    _, contract, _ = case
    output = tmp_path / 'plan'
    write_trial_plan(output, contract, {'fixed': True})
    write_trial_plan(output, contract, {'fixed': True})
    changed = deepcopy(contract)
    changed['initialization']['method'] = 'actor_only'
    with pytest.raises(ValueError, match='inputs changed'):
        write_trial_plan(output, changed, {'fixed': True})
    assert not (output / 'study.db').exists()


def test_live_world_check_handles_rewritten_gz_argv_and_isolation(case, tmp_path, monkeypatch):
    _, contract, _ = case
    proc = tmp_path / 'proc'
    (proc / '1').mkdir(parents=True)
    (proc / '1/cmdline').write_bytes(f'gz sim -r -s {contract["world"]}\0'.encode())
    (proc / '1/environ').write_bytes(b'GZ_PARTITION=testing\0')
    assert running_worlds('testing', proc) == [Path(contract['world'])]
    assert running_worlds('different', proc) == []
    contract['gz_partition'] = 'testing'
    contract['ros_domain_id'] = '78'
    monkeypatch.setenv('NINO_ROS_DOMAIN_ID', '78')
    monkeypatch.setenv('ROS_DOMAIN_ID', '78')
    monkeypatch.setenv('GZ_PARTITION', 'testing')
    monkeypatch.setattr('nino_rl.tuning_trials.running_worlds', lambda _: [Path(contract['world'])])
    assert_trial_inputs(contract, live=True)
    monkeypatch.setattr('nino_rl.tuning_trials.running_worlds', lambda _: [tmp_path / 'wrong.sdf'])
    with pytest.raises(ValueError, match='Expected one Gazebo server'):
        assert_trial_inputs(contract, live=True)
    monkeypatch.setenv('ROS_DOMAIN_ID', '79')
    with pytest.raises(ValueError, match='ROS domain'):
        assert_trial_inputs(contract, live=True)


def test_source_actor_with_old_optimizer_is_audited_and_never_resumed(case, tmp_path):
    config, initial, _ = case
    source = model(config)
    source.nino_training_contract = training_contract(config)
    source.learn(8)
    assert source.policy.optimizer.state
    source_path = tmp_path / 'actor.zip'
    source.save(source_path)
    audit = audit_actor_initialization(config, source_path)
    assert audit['source_steps'] == 8 and audit['copied_actor_tensors'] > 0
    contract = make_trial_contract(tmp_path, config, world_path=initial['world'],
        model_path=source_path, rollouts=[8], requested_steps=16, device='cpu',
        tuner_path=tmp_path / 'tuner.py')
    command = train_command(contract, 'trial.yaml', 'train')
    assert command[-2:] == ['--init-model', str(source_path)] and '--resume' not in command
    source_path.write_bytes(b'changed checkpoint')
    with pytest.raises(ValueError, match='Starting checkpoint changed'):
        assert_trial_inputs(contract)


def test_completed_training_requires_exact_budget_and_contract(case, tmp_path):
    config, initial, _ = case
    config['ppo']['n_steps'] = 8
    config['ppo']['batch_size'] = 8
    contract = make_trial_contract(tmp_path, config, world_path=initial['world'],
        model_path=None, rollouts=[8], requested_steps=16, device='cpu',
        tuner_path=tmp_path / 'tuner.py')
    target = model(config)
    target.nino_training_contract = training_contract(config)
    target.learn(8)
    path = tmp_path / 'nino_ppo_final.zip'
    target.save(path)
    (tmp_path / 'ppo.yaml').write_text(yaml.safe_dump(config))
    metadata = tmp_path / 'run_metadata.json'
    metadata.write_text(json.dumps({'argv': train_command(contract, 'trial.yaml', 'train')}))
    with pytest.raises(ValueError, match='trained 8 steps, expected 16'):
        verify_training_result(path, config, contract)
    target.learn(16)
    target.save(path)
    assert verify_training_result(path, config, contract)['training_steps'] == 16
    metadata.write_text(json.dumps({'argv': ['train', '--resume', str(path)]}))
    with pytest.raises(ValueError, match='initialization method'):
        verify_training_result(path, config, contract)


def test_warm_trial_requires_fresh_transfer_evidence(case, tmp_path):
    config, initial, _ = case
    config['ppo']['n_steps'] = config['ppo']['batch_size'] = 8
    source = model(config)
    source.nino_training_contract = training_contract(config)
    source.learn(8)
    source_path = tmp_path / 'source.zip'
    source.save(source_path)
    contract = make_trial_contract(tmp_path, config, world_path=initial['world'],
        model_path=source_path, rollouts=[8], requested_steps=8, device='cpu',
        tuner_path=tmp_path / 'tuner.py')
    target = model(config)
    initialize_actor(target, source)
    assert not target.policy.optimizer.state and target.num_timesteps == 0
    target.nino_training_contract = training_contract(config)
    target.learn(8)
    path = tmp_path / 'nino_ppo_final.zip'
    target.save(path)
    (tmp_path / 'ppo.yaml').write_text(yaml.safe_dump(config))
    (tmp_path / 'run_metadata.json').write_text(json.dumps(
        {'argv': train_command(contract, 'trial.yaml', 'train')}))
    transfer = {key: contract['initialization'][key] for key in
                ('source_sha256', 'critic', 'optimizer', 'training_counter')}
    evidence = tmp_path / 'actor_transfer.json'
    evidence.write_text(json.dumps(transfer))
    assert verify_training_result(path, config, contract)['training_steps'] == 8
    transfer['optimizer'] = 'resumed'
    evidence.write_text(json.dumps(transfer))
    with pytest.raises(ValueError, match='fixed actor with fresh'):
        verify_training_result(path, config, contract)
    old = load_config(PACKAGE / 'config/combined_rough_section.yaml')
    wrong_actor = model(old)
    wrong_actor.nino_training_contract = training_contract(old)
    wrong_actor.save(tmp_path / 'three_actions.zip')
    with pytest.raises(ValueError):
        audit_actor_initialization(config, tmp_path / 'three_actions.zip')


def test_all_four_tuners_have_preparation_and_result_checks():
    for name in ('tune_split_optuna', 'tune_split_optuna_rough_resume',
                 'tune_combined_optuna', 'tune_rocky_optuna'):
        path = PACKAGE / 'scripts' / (name + '.py')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.make_trial_contract is make_trial_contract
        assert module.verify_training_result is verify_training_result
        assert '--resume' not in path.read_text()
