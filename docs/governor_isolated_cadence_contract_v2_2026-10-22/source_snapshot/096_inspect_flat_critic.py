#!/usr/bin/env python3
"""Audit saved value learning and optionally capture a read-only stochastic probe."""
import argparse
import ast
import csv
import json
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'rl_runs/flat_targeted_actor_pilot_v1/train/20261010-002632-975129'


def gae_targets(rewards, values, dones, gamma, gae_lambda):
    import numpy as np
    rewards, values, dones = map(np.asarray, (rewards, values, dones))
    if not len(rewards) or not dones[-1]:
        raise ValueError('Probe must end at an actual episode terminal')
    advantages = np.zeros(len(rewards), dtype=np.float64)
    last = 0.
    for index in range(len(rewards) - 1, -1, -1):
        next_value = values[index + 1] if index + 1 < len(values) else 0.
        continuing = 1. - float(dones[index])
        delta = rewards[index] + gamma * next_value * continuing - values[index]
        last = delta + gamma * gae_lambda * continuing * last
        advantages[index] = last
    return advantages + values


def gradient_audit(model, data, scale=1.):
    """Same parameterization, rescaled value outputs/targets: unit sensitivity.

    This is not a new training update or proof of future critic convergence.
    Actor gradients use standard normalized advantages. No optimizer step.
    """
    import numpy as np
    import torch
    from stable_baselines3.common.utils import explained_variance
    model.policy.set_training_mode(False)
    target = gae_targets(data['rewards'], data['values'], data['dones'], model.gamma, model.gae_lambda)
    rng = np.random.default_rng(42)
    indices = rng.permutation(len(target))
    reports = []
    for start in range(0, len(indices), model.batch_size):
        chosen = indices[start:start + model.batch_size]
        if len(chosen) < 2:
            continue
        tensor = lambda x: torch.as_tensor(x, dtype=torch.float32, device=model.device)
        observations, actions = tensor(data['observations'][chosen]), tensor(data['actions'][chosen])
        old_logp = tensor(data['log_probs'][chosen])
        values, logp, entropy = model.policy.evaluate_actions(observations, actions)
        raw_advantages = target[chosen] - data['values'][chosen]
        advantages = tensor(raw_advantages * scale)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        ratio = torch.exp(logp - old_logp)
        policy_loss = -torch.min(advantages * ratio,
            advantages * torch.clamp(ratio, 1. - model.clip_range(1.), 1. + model.clip_range(1.))).mean()
        value_loss = ((values.flatten() * scale - tensor(target[chosen] * scale)) ** 2).mean()
        loss = policy_loss - model.ent_coef * entropy.mean() + model.vf_coef * value_loss
        model.policy.optimizer.zero_grad()
        loss.backward()
        squares = {'actor': 0., 'critic': 0.}
        for name, parameter in model.policy.named_parameters():
            if parameter.grad is not None:
                group = 'critic' if name.startswith(('vf_features_extractor.', 'mlp_extractor.value_net.', 'value_net.')) else 'actor'
                squares[group] += float(parameter.grad.detach().square().sum().cpu())
        norms = {name: float(np.sqrt(value)) for name, value in squares.items()}
        total = float(np.sqrt(sum(squares.values())))
        reports.append(dict(samples=len(chosen), value_mse=float(value_loss.detach().cpu()),
            actor_gradient_norm=norms['actor'], critic_gradient_norm=norms['critic'],
            global_gradient_norm=total,
            clip_retained_fraction=min(1., model.max_grad_norm / (total + 1e-6))))
    model.policy.optimizer.zero_grad()
    return dict(scale=scale, counterfactual='Value output and target uniformly rescaled at identical model weights',
        explained_variance=float(explained_variance(data['values'], target)),
        prediction_mean=float(np.mean(data['values'] * scale)),
        prediction_std=float(np.std(data['values'] * scale)),
        target_mean=float(np.mean(target * scale)), target_std=float(np.std(target * scale)),
        target_min=float(np.min(target * scale)), target_max=float(np.max(target * scale)), batches=reports)


def fresh_scaled_critic_audit(model, data, config, scale=.01):
    """Exercise the actual proposed fresh-critic initialization, without learning."""
    import gymnasium as gym
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    from nino_rl.policies import policy_spec
    from nino_rl.model_transfer import initialize_actor

    class SpaceOnly(gym.Env):
        observation_space = model.observation_space
        action_space = model.action_space

    policy, kwargs = policy_spec(config)
    ppo = config['ppo']
    fresh = PPO(policy, SpaceOnly(), policy_kwargs=kwargs, device=model.device,
                seed=int(config['seed']), n_steps=int(ppo['n_steps']), batch_size=int(ppo['batch_size']),
                gamma=float(ppo['gamma']), gae_lambda=float(ppo['gae_lambda']),
                clip_range=float(ppo['clip_range']), ent_coef=float(ppo['ent_coef']),
                vf_coef=float(ppo['vf_coef']), max_grad_norm=float(ppo['max_grad_norm']))
    initialize_actor(fresh, model)
    fresh.policy.set_training_mode(False)
    changed = dict(data)
    changed['rewards'] = data['rewards'] * scale
    with torch.no_grad():
        observations = torch.as_tensor(data['observations'], device=fresh.device)
        changed['values'] = fresh.policy.predict_values(observations).flatten().cpu().numpy()
        actions = torch.as_tensor(data['actions'], device=fresh.device)
        _, logp, _ = fresh.policy.evaluate_actions(observations, actions)
        if not np.allclose(logp.cpu().numpy(), data['log_probs'], atol=1e-3):
            raise ValueError('Fresh-critic diagnostic changed actor behavior')
    result = gradient_audit(fresh, changed)
    if fresh.num_timesteps != 0 or fresh.policy.optimizer.state:
        raise ValueError('Diagnostic performed a learning update')
    result.update(training_reward_multiplier=scale, actor='unchanged copied actor', critic='fresh',
                  optimizer='fresh', training_updates=0,
                  counterfactual='Actual proposed fresh critic with scaled raw reward; no optimizer steps')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Run 3 read-only stochastic episodes; never optimize weights')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/flat_reward_critic_diagnostic_2026-10-10')
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / 'src/nino_rl'))
    from nino_rl.core import load_config
    from nino_rl.evaluation import prepare_evaluation_config
    from nino_rl.tuning_trials import digest, assert_trial_inputs
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    from flat_reward_alignment import impact_terms

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model_path = RUN / 'nino_ppo_final.zip'
    comparison = json.loads((ROOT / 'rl_runs/flat_targeted_actor_pilot_v1/comparison.json').read_text())
    config = load_config(RUN / 'ppo.yaml')
    corrected = load_config(ROOT / 'src/nino_rl/config/combined_flat_energy_scaled_pilot.yaml')
    events = EventAccumulator(str(RUN / 'tensorboard/PPO_1')); events.Reload()
    curves = {name: [dict(step=row.step, value=row.value) for row in events.Scalars(name)]
        for name in events.Tags()['scalars'] if name.startswith('train/') or name in
        ('episode/return', 'episode_reward/impact', 'episode_reward/terminal', 'episode_reward/challenge_goal')}
    result = dict(source_model=str(model_path), source_sha256=digest(model_path), learning_curves=curves,
        saved_rollout_observations_available=False, reconstruction='Energy inferred as episode time * RMS squared; estimated-window coverage is full by the frozen profile')
    result['saved_reward_audit'] = {}
    for label in ('ppo', 'pi'):
        rows = list(csv.DictReader(Path(comparison[label]['summary']).with_name('episodes.csv').open()))
        old_cost, energy_cost, peak_cost, repriced_return = [], [], [], []
        for row in rows:
            terms = ast.literal_eval(row['reward_totals'])
            new = impact_terms(dict(square_integral=float(row['time_seconds']) * float(row['rms_vertical_acceleration_m_s2']) ** 2,
                peak=float(row['peak_vertical_acceleration_m_s2']), previous_episode_peak=0.), corrected['reward_v2'])
            old_cost.append(-terms['impact']); energy_cost.append(-new['impact']); peak_cost.append(-new['peak_impact'])
            repriced_return.append(float(row['return']) - terms['impact'] + sum(new.values()))
        average = lambda values: sum(values) / len(values)
        result['saved_reward_audit'][label] = dict(episodes=len(rows), old_impact_cost=average(old_cost),
            proposed_energy_cost=average(energy_cost), proposed_peak_cost=average(peak_cost),
            repriced_mean_return=average(repriced_return),
            note='Offline repricing of saved outcomes, not a new trained policy result')
    (output / 'audit.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print('Saved log/reward audit:', output / 'audit.json', flush=True)
    if not args.capture:
        return
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    from nino_rl.ros_env import NinoGazeboEnv
    from train_rough_curriculum import Processes, assert_isolated
    plan = json.loads((ROOT / 'rl_runs/flat_focused_optuna_v1/trial_plan.json').read_text())['trials']
    assert_trial_inputs(plan)
    os.environ.update(ROS_DOMAIN_ID='79', NINO_ROS_DOMAIN_ID='79', GZ_PARTITION='nino_flat_79',
                      ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    envvars = os.environ.copy()
    envvars['PYTHONPATH'] = str(ROOT / 'src/nino_rl') + os.pathsep + envvars.get('PYTHONPATH', '')
    assert_isolated(79, 'nino_flat_79')
    processes = Processes(envvars, pi_integrator_profile='conditional_v1')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    data = {name: [] for name in ('observations', 'actions', 'values', 'log_probs', 'rewards', 'dones', 'seeds')}
    summary = []
    environment = None
    try:
        processes.world = processes.start(['ros2', 'launch', 'nino_rl', 'training_sim.launch.py',
            f'world:={plan["world"]}', 'world_name:=combined_flat_section', 'headless:=true',
            'pi_integrator_profile:=conditional_v1'], output / 'gazebo.log')
        processes.run(['ros2', 'run', 'nino_rl', 'wait_for_sim'], output / 'readiness.log', timeout=90)
        assert_trial_inputs(plan, live=True)
        processes.run([sys.executable, 'src/nino_rl/scripts/wait_for_drive_profile.py',
            '--config', RUN / 'ppo.yaml', '--timeout', 60], output / 'profile.log', timeout=65)
        environment = NinoGazeboEnv(prepare_evaluation_config(config), total_training_steps=1)
        model = PPO.load(model_path, device='cuda')
        model.policy.set_training_mode(False)
        for seed in (63000, 63001, 63002):
            torch.manual_seed(seed)
            observation, _ = environment.reset(seed=seed)
            while True:
                with torch.no_grad():
                    actions, values, logp = model.policy(torch.as_tensor(observation[None], device=model.device))
                action = actions.cpu().numpy()[0]
                data['observations'].append(observation.copy()); data['actions'].append(action.copy())
                data['values'].append(float(values.cpu().item())); data['log_probs'].append(float(logp.cpu().item()))
                data['seeds'].append(seed)
                observation, reward, terminated, truncated, info = environment.step(np.clip(action, -1., 1.))
                data['rewards'].append(reward); data['dones'].append(terminated or truncated)
                if terminated or truncated:
                    summary.append(info['episode_metrics'])
                    print('Probe seed', seed, 'completed:', info['episode_metrics']['termination'], flush=True)
                    break
    finally:
        if environment is not None:
            environment.close()
        processes.close()
    if digest(model_path) != result['source_sha256']:
        raise ValueError('Read-only probe changed source checkpoint')
    data = {name: np.asarray(values) for name, values in data.items()}
    np.savez_compressed(output / 'probe.npz', **data)
    result['probe'] = dict(seeds=[63000, 63001, 63002], observations=len(data['rewards']),
        behavior='Stochastic frozen actor, raw Gaussian actions stored, clipped only for execution',
        training_updates=0, episodes=summary,
        raw_units=gradient_audit(model, data), scaled_units_sensitivity=gradient_audit(model, data, .01),
        fresh_scaled_critic=fresh_scaled_critic_audit(model, data, config))
    (output / 'audit.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print('Read-only critic/gradient probe finished:', output / 'audit.json', flush=True)


if __name__ == '__main__':
    main()
