#!/usr/bin/env python3
"""Backward-only gradient balance from the original first BC-initialized rollout."""
import json
import sys
from pathlib import Path
import gymnasium as gym
import numpy as np
import torch
import yaml
from stable_baselines3 import PPO
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'rl_runs/rough_rate_bc_pilot_v2'
OUTPUT = ROOT / 'docs/rough_phase_anchor_gradient_2026-10-12'
sys.path[:0] = [str(SOURCE / 'python'), str(Path(__file__).parent)]
from prepare_rough_foundations import digest
from rough_phase_anchor import actor_parameters, gradient_vector, load_demonstrations


def fresh(config):
    from nino_rl.rate_actions import policy_spec
    from nino_rl.model_transfer import initialize_actor
    class Dummy(gym.Env):
        observation_space = gym.spaces.Box(-5., 5., shape=(360,), dtype=np.float32)
        action_space = gym.spaces.Discrete(3)
    cls, kwargs = policy_spec(config)
    p = config['ppo']
    model = PPO(cls, Dummy(), policy_kwargs=kwargs, device='cpu', seed=config['seed'],
        **{k: p[k] for k in ('learning_rate','gamma','gae_lambda','n_steps','batch_size','n_epochs','clip_range','ent_coef','vf_coef','max_grad_norm','target_kl')})
    source = PPO.load(SOURCE / 'bc_actor.zip', device='cpu')
    initialize_actor(model, source)
    model.policy.set_training_mode(False)
    return model


def main():
    torch.set_num_threads(2)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load((SOURCE / 'config.yaml').read_text())
    model = fresh(config)
    before = {n: p.detach().clone() for n, p in model.policy.named_parameters()}
    data = [np.load(f) for f in sorted((SOURCE / 'train/actor_capture').glob('*.npz'))[:4]]
    observations = np.concatenate([d['observations'] for d in data])
    records = [json.loads(str(r)) for d in data for r in d['records']]
    # Recorded check_env resets consume 11 steps before attempt 4 starts PPO.
    start = next(i for i, r in enumerate(records) if r['attempt'] == 4 and r['elapsed_s'] < .15)
    n = config['ppo']['n_steps']
    selected = records[start:start+n]
    obs = torch.as_tensor(observations[start:start+n+1])
    actions = torch.tensor([r['rate_action'] for r in selected], dtype=torch.long)
    with torch.no_grad():
        values = model.policy.predict_values(obs).flatten().numpy()
    rewards = np.array([sum(r['reward_terms'].values()) * config['training_reward_scale'] for r in selected])
    dones = np.array([r['terminal'] for r in selected])
    advantages = np.zeros(n)
    last = 0.
    for i in range(n-1, -1, -1):
        continuing = 1. - float(dones[i])
        delta = rewards[i] + model.gamma * values[i+1] * continuing - values[i]
        last = delta + model.gamma * model.gae_lambda * continuing * last
        advantages[i] = last
    targets = advantages + values[:n]
    run = next((SOURCE / 'train').glob('*/nino_ppo_final.zip')).parent
    event_path = next((run / 'tensorboard').glob('*/events.out.tfevents.*'))
    accumulator = EventAccumulator(str(event_path), size_guidance={'scalars': 0})
    accumulator.Reload()
    reference = {}
    for name, actual in [('prediction_mean', np.mean(values[:n])), ('prediction_std', np.std(values[:n])),
                         ('target_mean', np.mean(targets)), ('target_std', np.std(targets))]:
        event = next(e for e in accumulator.Scalars('critic/' + name) if e.step == n)
        reference[name] = dict(reconstructed=float(actual), recorded=event.value, difference=float(actual-event.value))
    if any(abs(v['difference']) > 2e-5 for v in reference.values()):
        raise ValueError('First-rollout reconstruction does not match recorded critic statistics: ' + str(reference))
    demo = dict(demonstrations={str(SOURCE / f'demo_{s}.npz'): digest(SOURCE / f'demo_{s}.npz') for s in (17200,17201,17202)})
    x, y, indices = load_demonstrations(demo)
    rng = np.random.default_rng(17000)
    params = actor_parameters(model.policy)
    critic = [p for name, p in model.policy.named_parameters() if name.startswith(('vf_features_extractor.', 'mlp_extractor.value_net.', 'value_net.'))]
    reports = []
    order = rng.permutation(n)
    for offset in range(0, n, model.batch_size):
        chosen = order[offset:offset+model.batch_size]
        val, logp, entropy = model.policy.evaluate_actions(obs[chosen], actions[chosen])
        adv = torch.as_tensor(advantages[chosen], dtype=torch.float32)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        # At the first update the old and current actors are identical (ratio 1).
        ratio = torch.exp(logp-logp.detach())
        ppo_loss = -(adv*ratio).mean()-model.ent_coef*entropy.mean()
        value_loss = model.vf_coef*(val.flatten()-torch.as_tensor(targets[chosen],dtype=torch.float32)).square().mean()
        demo_idx = np.concatenate([rng.choice(i, 64, replace=True) for i in indices])
        bc_loss = -model.policy.get_distribution(torch.as_tensor(x[demo_idx])).log_prob(torch.as_tensor(y[demo_idx])).mean()
        a, b = gradient_vector(ppo_loss, params), gradient_vector(bc_loss, params)
        c = gradient_vector(value_loss, critic)
        zero = torch.autograd.grad(bc_loss, critic, allow_unused=True, retain_graph=True)
        if any(g is not None and torch.count_nonzero(g).item() for g in zero):
            raise ValueError('BC loss reaches critic')
        reports.append(dict(ppo_actor_gradient=float(a.norm()), bc_actor_gradient=float(b.norm()),
            critic_gradient=float(c.norm()), cosine=float(torch.dot(a,b)/(a.norm()*b.norm()+1e-12)),
            bc_loss=float(bc_loss.detach()), samples=len(chosen)))
    raw_ratio = np.median([r['ppo_actor_gradient']/max(r['bc_actor_gradient'],1e-12) for r in reports])
    coefficient = float(.25*raw_ratio)
    for r in reports:
        r['effective_coefficient'] = min(coefficient, .5*r['ppo_actor_gradient']/max(r['bc_actor_gradient'],1e-12))
        r['weighted_gradient_ratio'] = r['effective_coefficient']*r['bc_actor_gradient']/max(r['ppo_actor_gradient'],1e-12)
    assert all(torch.equal(before[n], p) for n,p in model.policy.named_parameters())
    assert not model.policy.optimizer.state and model.num_timesteps == 0
    result = dict(passed=True, source_actor=str(SOURCE/'bc_actor.zip'), actor_sha256=digest(SOURCE/'bc_actor.zip'),
        source_capture_offset=start, source_rollout_steps=n, reconstruction_checks=reference,
        coefficient=coefficient, intended_median_gradient_ratio=.25, maximum_actor_gradient_ratio=.5,
        phase_filter='Demonstrated pre-action holding/recovering only; 64 samples/action class',
        demonstration_class_counts=[len(i) for i in indices], demonstrations=demo['demonstrations'], batches=reports,
        critic_untouched=True, parameters_unchanged=True, optimizer_empty=True, ppo_steps=0,
        qualification='Reconstructed first initial-BC on-policy rollout; GAE statistics checked against original TensorBoard. Not a claim about later updates.',
        reward_scale=config['training_reward_scale'])
    (OUTPUT/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
