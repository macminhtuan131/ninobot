"""Actor-only phase-selective imitation, bounded relative to PPO actor gradients."""
from pathlib import Path
import hashlib
import numpy as np
import torch as th

ACTOR_PREFIXES = ('pi_features_extractor.', 'mlp_extractor.policy_net.', 'action_net.')


def actor_parameters(policy):
    return [p for name, p in policy.named_parameters() if name.startswith(ACTOR_PREFIXES)]


def gradient_vector(loss, parameters):
    gradients = th.autograd.grad(loss, parameters, retain_graph=True, allow_unused=True)
    return th.cat([(g if g is not None else th.zeros_like(p)).reshape(-1) for p, g in zip(parameters, gradients)])


def load_demonstrations(config):
    observations, actions = [], []
    for path, expected in config['demonstrations'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen demonstration changed: ' + path)
        with np.load(path) as data:
            x, y = data['observations'], data['actions']
            extras = x.reshape(-1, 5, 72)[:, -1, -16:]
            mask = (extras[:, 6] > .5) | (extras[:, 7] > .5)
            observations.append(x[mask].copy())
            actions.append(y[mask].copy())
    x, y = np.concatenate(observations), np.concatenate(actions)
    indices = [np.flatnonzero(y == i) for i in range(3)]
    if any(len(i) < 3 for i in indices):
        raise ValueError('Missing demonstrated holding/recovery action class')
    return x, y, indices


def anchor_terms(model, ppo_actor_loss):
    config = model.nino_bc_anchor
    if not hasattr(model, '_bc_anchor_data'):
        model._bc_anchor_data = load_demonstrations(config)
        model._anchor_generator = np.random.default_rng(config['sampling_seed'])
    x, y, indices = model._bc_anchor_data
    chosen = np.concatenate([model._anchor_generator.choice(i, config['samples_per_class'], replace=True) for i in indices])
    distribution = model.policy.get_distribution(th.as_tensor(x[chosen], device=model.device))
    loss = -distribution.log_prob(th.as_tensor(y[chosen], device=model.device)).mean()
    parameters = actor_parameters(model.policy)
    ppo_gradient, bc_gradient = gradient_vector(ppo_actor_loss, parameters), gradient_vector(loss, parameters)
    ppo_norm, bc_norm = ppo_gradient.norm(), bc_gradient.norm()
    coefficient = min(config['coefficient'], config['maximum_actor_gradient_ratio'] * float(ppo_norm.detach()) / max(float(bc_norm.detach()), 1e-12))
    cosine = float(th.dot(ppo_gradient, bc_gradient).detach() / (ppo_norm * bc_norm + 1e-12))
    return coefficient * loss, dict(loss=float(loss.detach()), coefficient=coefficient,
        ppo_actor_gradient=float(ppo_norm.detach()), bc_actor_gradient=float(bc_norm.detach()),
        weighted_gradient_ratio=coefficient * float(bc_norm.detach()) / max(float(ppo_norm.detach()), 1e-12),
        cosine=cosine)
