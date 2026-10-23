"""Comparable Optuna trial inputs, initialization and completed-step budgets."""
from copy import deepcopy
import hashlib
import json
from math import lcm
import os
from pathlib import Path
import shlex
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from nino_rl.training_contract import training_contract


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def add_comparable_arguments(parser):
    parser.add_argument('--world', type=Path,
        help='Exact launched SDF; defaults to the config world_name in nino_description')
    preparation = parser.add_mutually_exclusive_group()
    preparation.add_argument('--prepare-only', action='store_true',
        help='Audit actor transfer and write a trial plan without ROS calls or tuning')
    preparation.add_argument('--prepare-study', action='store_true',
        help='Prepare the study, queue current parameters and audit/import matching history; do not train')
    parser.add_argument('--pi-reference', type=Path, action='append', default=[],
        help='Saved PI summary.json to retain as a reference, never a PPO trial (repeatable)')
    parser.add_argument('--history-study', type=Path, action='append', default=[],
        help='Historical study.db/directory to audit read-only; import only fully matching trials (repeatable)')


def world_assets(root, world_path, expected_name):
    """Fingerprint the actual SDF and its local referenced meshes/includes."""
    root, world_path = Path(root).resolve(), Path(world_path).resolve()
    document = ET.parse(world_path)
    names = [world.get('name') for world in document.findall('world')]
    if names != [expected_name]:
        raise ValueError(f'SDF world names {names} differ from config {expected_name}')
    assets = {}

    def visit(path):
        path = path.resolve()
        if str(path) in assets:
            return
        assets[str(path)] = digest(path)
        if path.suffix not in ('.sdf', '.world'):
            return
        for node in ET.parse(path).iter('uri'):
            uri = (node.text or '').strip()
            parsed = urlparse(uri)
            if parsed.scheme == 'model' and parsed.netloc == 'nino_description':
                target = root / 'src/nino_description' / unquote(parsed.path).lstrip('/')
            elif parsed.scheme == 'file' and parsed.netloc in ('', 'localhost'):
                target = Path(unquote(parsed.path))
            elif not parsed.scheme:
                target = path.parent / unquote(uri)
            else:
                raise ValueError(f'Cannot fingerprint external world asset: {uri}')
            if target.is_dir():
                model = ET.parse(target / 'model.config').find('sdf')
                if model is None or not model.text:
                    raise ValueError(f'Missing model SDF declaration: {target}')
                assets[str((target / 'model.config').resolve())] = digest(target / 'model.config')
                target = target / model.text.strip()
            visit(target)
    visit(world_path)
    return assets


def audit_actor_initialization(config, model_path):
    """Exercise the real actor-copy code offline, with fresh value/optimizer."""
    import gymnasium as gym
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    from nino_rl.control_v2 import FRAME_SIZE, action_size, validate_model, validate_action_mode
    from nino_rl.model_transfer import initialize_actor
    from nino_rl.policies import policy_spec

    source = PPO.load(model_path, device='cpu')
    size = FRAME_SIZE * int(config['policy_v2']['history_frames'])
    validate_model(source, size, action_size(config))
    validate_action_mode(source, config)
    policy, kwargs = policy_spec(config)
    env = gym.Env()
    env.observation_space = gym.spaces.Box(-5., 5., (size,), dtype=np.float32)
    env.action_space = gym.spaces.Box(-1., 1., (action_size(config),), dtype=np.float32)
    target = PPO(policy, env, policy_kwargs=kwargs, n_steps=8, batch_size=8,
                 seed=int(config['seed']), device='cpu')
    before = deepcopy(target.policy.state_dict())
    keys = initialize_actor(target, source)
    for key, value in target.policy.state_dict().items():
        # SB3 exposes features_extractor as an alias of pi_features_extractor;
        # only the independent value extractor/network belongs to the critic.
        if key.startswith(('vf_features_extractor.', 'mlp_extractor.value_net.', 'value_net.')) and not torch.equal(value, before[key]):
            raise ValueError(f'Actor initialization modified critic tensor {key}')
    if target.num_timesteps != 0 or target.policy.optimizer.state:
        raise ValueError('Actor initialization reused optimizer/counter state')
    return {'source_steps': int(source.num_timesteps), 'copied_actor_tensors': len(keys),
            'source_actions': int(source.action_space.shape[0]),
            'target_contract_revision': training_contract(config)['revision']}


def make_trial_contract(root, base, *, world_path, model_path, rollouts,
                        requested_steps, device, tuner_path):
    root = Path(root).resolve()
    rollouts = sorted(set(int(value) for value in rollouts))
    if not rollouts or min(rollouts) < 2 or requested_steps < max(rollouts):
        raise ValueError('Training budget must cover every sampled rollout size')
    quantum = lcm(*rollouts)
    steps = ((requested_steps + quantum - 1) // quantum) * quantum
    world_path = Path(world_path or root / 'src/nino_description/worlds' /
                      (base['world_name'] + '.sdf')).expanduser().resolve()
    assets = world_assets(root, world_path, base['world_name'])
    for directory, pattern in (
        ('src/nino_rl/nino_rl', '*.py'), ('src/nino_control/nino_control', '*.py'),
        ('src/nino_description/urdf', '*'), ('src/nino_description/meshes', '*'),
        ('src/nino_description/config', '*.yaml')):
        for path in sorted((root / directory).rglob(pattern)):
            if path.is_file():
                assets[str(path.resolve())] = digest(path)
    assets[str(Path(tuner_path).resolve())] = digest(tuner_path)
    initialization = {'method': 'actor_only' if model_path else 'from_scratch',
                      'critic': 'fresh', 'optimizer': 'fresh', 'training_counter': 0,
                      'source': str(Path(model_path).resolve()) if model_path else None,
                      'source_sha256': digest(model_path) if model_path else None}
    if model_path:
        initialization.update(audit_actor_initialization(base, model_path))
    invariant = deepcopy(base)
    for key in ('reward', 'reward_v2', 'ppo', 'device'):
        invariant.pop(key, None)
    contract = {'revision': 'comparable_trials_v1', 'world': str(world_path),
        'world_name': base['world_name'], 'assets': assets, 'fixed_training_config': invariant,
        'initialization': initialization, 'training_seed': int(base['seed']),
        'requested_steps': requested_steps, 'training_steps': steps, 'rollout_sizes': rollouts,
        'device': device, 'ros_domain_id': os.environ.get('NINO_ROS_DOMAIN_ID', '77'),
        'gz_partition': os.environ.get('GZ_PARTITION', ''),
        'budget_unit': 'completed environment steps; each trial starts at zero'}
    contract['sha256'] = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    return contract


def write_trial_plan(output, contract, objective):
    """A preparation run must not silently replace an existing experiment."""
    output = Path(output)
    plan = {'trials': contract, 'evaluation_objective': objective}
    path = output / 'trial_plan.json'
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError('Prepared trial inputs changed; use a new --output directory')
    output.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2) + '\n')
    print(f"Comparable trial plan: {path}; {contract['requested_steps']} requested -> "
          f"{contract['training_steps']} steps per trial; initialization="
          f"{contract['initialization']['method']}, fresh critic/optimizer", flush=True)


def validate_trial_config(config, contract):
    invariant = deepcopy(config)
    for key in ('reward', 'reward_v2', 'ppo', 'device'):
        invariant.pop(key, None)
    if invariant != contract['fixed_training_config']:
        raise ValueError('Trial changed controller, estimator, terrain, seed or physical criteria')
    if int(config['ppo']['n_steps']) not in contract['rollout_sizes']:
        raise ValueError('Trial rollout size is outside the aligned training budget')


def running_worlds(partition, proc=Path('/proc')):
    """Read local Gazebo server launch arguments, without advancing simulation."""
    worlds = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / 'cmdline').read_bytes()
            args = [part.decode(errors='replace') for part in raw.split(b'\0') if part]
            if args and args[0].startswith('gz sim '):
                args = shlex.split(args[0]) + args[1:]
            if len(args) < 2 or Path(args[0]).name != 'gz' or args[1] != 'sim' or '-g' in args:
                continue
            env = dict(part.split(b'=', 1) for part in (entry / 'environ').read_bytes().split(b'\0') if b'=' in part)
            if env.get(b'GZ_PARTITION', b'').decode() != partition:
                continue
            for arg in args[2:]:
                if arg.endswith('.sdf'):
                    path = Path(arg)
                    if not path.is_absolute():
                        path = (entry / 'cwd').resolve() / path
                    worlds.append(path.resolve())
        except (OSError, ValueError):
            continue
    return worlds


def assert_trial_inputs(contract, *, live=False):
    for path, expected in contract['assets'].items():
        if digest(path) != expected:
            raise ValueError(f'Trial asset/code changed: {path}; prepare a new study')
    initialization = contract['initialization']
    if initialization['source'] and digest(initialization['source']) != initialization['source_sha256']:
        raise ValueError('Starting checkpoint changed; prepare a new study')
    if live:
        domain = os.environ.get('NINO_ROS_DOMAIN_ID', '77')
        if domain != contract['ros_domain_id'] or os.environ.get('ROS_DOMAIN_ID', domain) != domain:
            raise ValueError('ROS domain differs from the prepared trial plan')
        if os.environ.get('GZ_PARTITION', '') != contract['gz_partition']:
            raise ValueError('Gazebo partition differs from the prepared trial plan')
        worlds = running_worlds(contract['gz_partition'])
        if worlds != [Path(contract['world'])]:
            raise ValueError(f'Expected one Gazebo server using {contract["world"]}; found {worlds}')


def train_command(contract, config_path, output):
    steps = contract['training_steps']
    command = ['ros2', 'run', 'nino_rl', 'train', '--device', contract['device'],
        '--config', str(config_path), '--timesteps', str(steps),
        '--checkpoint-every', str(steps + 1), '--output', str(output)]
    if contract['initialization']['source']:
        command.extend(('--init-model', contract['initialization']['source']))
    return command


def verify_training_result(model_path, config, contract):
    """Reject partial budgets, optimizer resume or a different source actor."""
    from stable_baselines3 import PPO
    from nino_rl.core import load_config
    model_path = Path(model_path)
    metadata = json.loads((model_path.parent / 'run_metadata.json').read_text())
    argv = metadata['argv']
    if '--resume' in argv or '--init-speed-model' in argv:
        raise ValueError('Trial initialization method differs from the prepared plan')
    initialization = contract['initialization']
    if initialization['source']:
        transfer = json.loads((model_path.parent / 'actor_transfer.json').read_text())
        if any(transfer.get(key) != initialization[key] for key in
               ('source_sha256', 'critic', 'optimizer', 'training_counter')):
            raise ValueError('Trial did not use the fixed actor with fresh critic/optimizer')
    elif '--init-model' in argv or (model_path.parent / 'actor_transfer.json').exists():
        raise ValueError('From-scratch trial imported checkpoint state')
    saved_config = load_config(model_path.parent / 'ppo.yaml')
    validate_trial_config(saved_config, contract)
    if training_contract(saved_config) != training_contract(config):
        raise ValueError('Completed trial used a different training reward/policy contract')
    model = PPO.load(model_path, device='cpu')
    if int(model.num_timesteps) != contract['training_steps']:
        raise ValueError(f'Trial trained {model.num_timesteps} steps, expected {contract["training_steps"]}')
    if getattr(model, 'nino_training_contract', None) != training_contract(saved_config):
        raise ValueError('Completed checkpoint does not match its training contract')
    return {'training_steps': int(model.num_timesteps), 'contract_sha256': contract['sha256'],
            'initialization': deepcopy(initialization)}
