"""Versioned TD3 parameters. Validation/preparation never releases a training job.

SB3 uses one learning-rate schedule for actor and critics. Unequal proposed
rates are rejected here rather than silently ignored. History changes are ABI
changes; they require a new backend validation and checkpoint.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import yaml


def profiles_path():
    path = Path(__file__).resolve().parents[1] / 'config/td3_parameter_profiles.yaml'
    if not path.is_file():
        from ament_index_python.packages import get_package_share_directory
        path = Path(get_package_share_directory('nino_rl')) / 'config/td3_parameter_profiles.yaml'
    return path


def load_profiles(path=None):
    data = yaml.safe_load(Path(path or profiles_path()).read_text())
    if (not isinstance(data, dict) or set(data) != {'schema_version', 'profiles'}
            or type(data['schema_version']) is not int or data['schema_version'] != 1
            or not isinstance(data['profiles'], dict) or not data['profiles']):
        raise ValueError('TD3 parameter catalog schema_version=1 required')
    for name, profile in data['profiles'].items():
        validate_profile(profile)
        if name != profile['profile_id']:
            raise ValueError('Profile key/identity mismatch')
    return data['profiles']


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be finite in [{low}, {high}]')


def validate_profile(profile):
    expected = {'profile_id', 'status', 'algorithm', 'observation', 'action', 'evaluation'}
    if not isinstance(profile, dict) or set(profile) != expected:
        raise ValueError('TD3 profile needs exactly ' + str(sorted(expected)))
    if not isinstance(profile['profile_id'], str) or not profile['profile_id']:
        raise ValueError('Nonempty versioned profile_id required')
    if profile['status'] not in ('software_smoke_only', 'research_proposal'):
        raise ValueError('A parameter profile cannot authorize hardware or training')
    a = profile['algorithm']
    if not all(isinstance(profile[k],dict) for k in ('algorithm','observation','action','evaluation')):
        raise ValueError('Profile sections must be mappings')
    keys = {'actor_lr', 'critic_lr', 'gamma', 'tau', 'batch_size', 'buffer_size', 'learning_starts',
            'policy_delay', 'target_policy_noise', 'target_noise_clip', 'exploration_noise',
            'train_freq', 'gradient_steps', 'network_arch'}
    if set(a) != keys:
        raise ValueError('Unknown/missing algorithm parameters: ' + str(set(a) ^ keys))
    for key in ('actor_lr', 'critic_lr'):
        number(a[key], key, 1e-8, 1.)
    if a['actor_lr'] != a['critic_lr']:
        raise ValueError('Current SB3 adapter supports shared actor/critic LR only; unequal rates need a separately tested adapter')
    for key in ('gamma', 'tau'):
        number(a[key], key, 1e-8, 1.)
    for key in ('target_policy_noise', 'target_noise_clip', 'exploration_noise'):
        number(a[key], key, 0., 1.)
    for key in ('batch_size', 'buffer_size', 'policy_delay', 'train_freq', 'gradient_steps'):
        if type(a[key]) is not int or a[key] < 1:
            raise ValueError(key + ' must be a positive integer')
    if type(a['learning_starts']) is not int or not 0 <= a['learning_starts'] < a['buffer_size']:
        raise ValueError('Warm-up must fit in replay buffer')
    if a['batch_size'] > a['buffer_size']:
        raise ValueError('Batch must fit in replay buffer')
    if not isinstance(a['network_arch'], list) or not a['network_arch'] or any(type(n) is not int or not 1 <= n <= 4096 for n in a['network_arch']):
        raise ValueError('Invalid network_arch')
    o = profile['observation']
    if set(o) != {'history_len', 'policy_rate_hz', 'normalization', 'missing_data'}:
        raise ValueError('Unknown/missing observation contract')
    if type(o['history_len']) is not int or not 1 <= o['history_len'] <= 64:
        raise ValueError('Invalid history length')
    number(o['policy_rate_hz'], 'policy_rate_hz', 1., 100.)
    if o['normalization'] != 'fixed_physical_scales_v1' or o['missing_data'] != 'reject_and_refill_history':
        raise ValueError('Mask/train-stat normalization is not implemented in the current feature ABI')
    action = profile['action']
    if set(action) != {'schema', 'projection_required', 'hardware_residual_scale'} or action != {
            'schema': 'common_differential_wheel_linear_v1', 'projection_required': True,
            'hardware_residual_scale': None}:
        raise ValueError('Preserve current wheel residual/projection ABI; hardware scale remains unknown')
    e = profile['evaluation']
    if set(e) != {'seeds', 'grouped_splits', 'baseline', 'minimum_effect_accepted'}:
        raise ValueError('Unknown/missing evaluation contract')
    if not isinstance(e['seeds'], list) or not e['seeds'] or any(type(s) is not int or s < 0 for s in e['seeds']) or len(set(e['seeds'])) != len(e['seeds']):
        raise ValueError('Distinct nonnegative learner seeds required')
    if e['grouped_splits'] != ['session', 'layout', 'payload_block'] or e['baseline'] != 'same_backend_classical' or e['minimum_effect_accepted'] is not None:
        raise ValueError('Evaluation proposal must preserve grouped holdout/baseline; no accepted effect is supplied')
    canonical = json.dumps(profile, sort_keys=True, allow_nan=False, separators=(',', ':'))
    return {'schema_version': 1, 'profile_id': profile['profile_id'], 'sha256': hashlib.sha256(canonical.encode()).hexdigest(),
            'valid': True, 'training_authorized': False, 'hardware_authorized': False,
            'observation_frames': o['history_len'], 'history_span_s': (o['history_len']-1)/o['policy_rate_hz'],
            'note': 'Valid parameters are not evidence of control benefit or permission to run.'}


def apply_profile(config, name):
    p = load_profiles()[name]
    evidence = validate_profile(p)
    c = deepcopy(config)
    if c.get('experiment_contract') != 'nino_residual_velocity_v1' or c.get('algorithm') != 'TD3':
        raise ValueError('Profile is only for the current residual TD3 contract')
    if c.get('hardware_authority', 0.) != 0.:
        raise ValueError('Parameter preparation cannot enable hardware authority')
    a = p['algorithm']
    params = {k: a[k] for k in ('gamma', 'tau', 'batch_size', 'buffer_size', 'learning_starts',
              'policy_delay', 'target_policy_noise', 'target_noise_clip', 'train_freq', 'gradient_steps')}
    params.update(learning_rate=a['actor_lr'], policy_kwargs={'net_arch': a['network_arch']}, device='cpu')
    c.setdefault('algorithm_parameters', {})['TD3'] = params
    c['exploration_sigma'] = a['exploration_noise']
    c['actor']['history_frames'] = p['observation']['history_len']
    c['control_interval_s'] = 1. / p['observation']['policy_rate_hz']
    if c['control_interval_s'] > c['actor']['max_history_gap_s']:
        raise ValueError('Profile rate incompatible with causal history gap')
    # A profile edit invalidates the previous training release/validation pointer.
    c['training'] = dict(allowed=False, backend_validation_artifact=None, budget_transitions=None)
    c['parameter_profile'] = evidence
    return c


def validate_runtime(config):
    """Validate actual effective kwargs, including legacy configs, before SB3 creation."""
    a = config.get('algorithm_parameters', {}).get('TD3', {})
    p = deepcopy(load_profiles()['nino_td3_research_h5_v1'])
    mapping = {'learning_rate': 'actor_lr', 'buffer_size': 'buffer_size', 'learning_starts': 'learning_starts',
               'batch_size': 'batch_size', 'tau': 'tau', 'gamma': 'gamma', 'train_freq': 'train_freq',
               'gradient_steps': 'gradient_steps', 'policy_delay': 'policy_delay',
               'target_policy_noise': 'target_policy_noise', 'target_noise_clip': 'target_noise_clip'}
    allowed = set(mapping) | {'policy_kwargs', 'device'}
    if set(a) - allowed:
        raise ValueError('Unsupported TD3 kwargs: ' + str(sorted(set(a)-allowed)))
    for key, target in mapping.items():
        if key in a:
            p['algorithm'][target] = a[key]
    p['algorithm']['critic_lr'] = p['algorithm']['actor_lr']
    policy = a.get('policy_kwargs', {})
    if set(policy) - {'net_arch'}:
        raise ValueError('Unsupported TD3 policy kwargs')
    p['algorithm']['network_arch'] = policy.get('net_arch', [64, 64])
    p['algorithm']['exploration_noise'] = config.get('exploration_sigma', .1)
    p['observation']['history_len'] = config['actor']['history_frames']
    p['observation']['policy_rate_hz'] = 1./config['control_interval_s']
    validate_profile(p)
    evidence=config.get('parameter_profile')
    if evidence is not None:
        name=evidence.get('profile_id')
        actual=load_profiles().get(name)
        if actual is None or evidence.get('sha256')!=validate_profile(actual)['sha256']:
            raise ValueError('Stale/unknown parameter profile hash')
        expected=apply_profile(config,name)
        for key in ('algorithm_parameters','exploration_sigma','control_interval_s'):
            if config[key]!=expected[key]:raise ValueError('Effective TD3 parameters differ from named profile: '+key)
        if config['actor']['history_frames']!=expected['actor']['history_frames']:
            raise ValueError('History differs from named parameter profile')
    return deepcopy(a)


def prepare_profile(name, output, base=None):
    from .core import load_config
    from .residual_experiment import experiment_contract
    profile=load_profiles()[name]
    config=apply_profile(load_config(base or profiles_path().with_name('residual_velocity_td3.yaml')),name)
    out=Path(output).expanduser().resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'profile.yaml').write_text(yaml.safe_dump(profile,sort_keys=False))
    (out/'effective_config.yaml').write_text(yaml.safe_dump(config,sort_keys=False))
    contract=experiment_contract(config)
    (out/'contract.json').write_text(json.dumps(contract,indent=2,allow_nan=False)+'\n')
    return dict(validate_profile(profile),output=str(out),abi_sha256=contract['abi_sha256'])


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Prepare a TD3 parameter/ABI draft. No training, ROS or hardware.')
    parser.add_argument('--profile',choices=list(load_profiles()),required=True)
    parser.add_argument('--base',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    print(json.dumps(prepare_profile(args.profile,args.output,args.base),indent=2))


if __name__=='__main__':main()
