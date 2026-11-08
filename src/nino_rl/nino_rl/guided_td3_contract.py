"""V3 reward, fresh zero-output initialization and strict task identity.

Torch/SB3 imports stay inside functions, allowing the GUI to inspect hashes
with system Python. No training, ROS or Gazebo starts on import.
"""
import json
import math
from pathlib import Path
import numpy as np
from . import residual_guided_baseline as v3


def zero_initialize(model):
    import torch
    from torch import nn
    if (getattr(model, '_n_updates', 0) or model.num_timesteps or getattr(model, 'nino_zero_initialized', False)
            or model.actor.optimizer.state or model.critic.optimizer.state):
        raise ValueError('Zero initialization is allowed only once on a fresh, untrained model')
    modules = list(model.actor.mu.children())
    if len(modules)<2 or not isinstance(modules[-1], nn.Tanh) or not isinstance(modules[-2], nn.Linear) or modules[-2].out_features!=2:
        raise ValueError('Expected two-output TD3 Linear -> Tanh head')
    with torch.no_grad():
        modules[-2].weight.zero_(); modules[-2].bias.zero_()
        model.actor_target.load_state_dict(model.actor.state_dict())
    model.nino_zero_initialized = True
    return dict(actor_final_linear_zero=True, target_synced=True, optimizer_updates=0,
                scope='Deterministic initial actor only; exploration/warmup actions are not zero')


class LearningScore(v3.BaselineScore):
    def __init__(self, config, parent_protocol, condition, reward):
        super().__init__(config, parent_protocol, condition)
        self.reward_config = reward
        self.previous = np.zeros(2)

    def update(self, info, action, elapsed, physical_failure):
        _, task = super().update(info, elapsed, physical_failure)
        a = np.asarray(action, dtype=float)
        if a.shape!=(2,) or not np.all(np.isfinite(a)) or np.max(np.abs(a))>1+1e-6:
            raise ValueError('Finite normalized proposal required for V3 reward')
        r = self.reward_config; w = r['weights']; dt = self.c['control_interval_s']
        terms = dict(velocity_tracking=-w['velocity']*(task['velocity_error_m_s']/r['velocity_scale_m_s'])**2*dt,
            yaw_tracking=-w['yaw']*(task['yaw_rate_error_rad_s']/r['yaw_rate_scale_rad_s'])**2*dt,
            action_size=-w['action']*float(a@a)*dt,
            action_change=-w['action_change']*float((a-self.previous)@(a-self.previous))/dt)
        self.previous = a.copy()
        if physical_failure: terms['physical_failure'] = -r['penalties']['physical_failure']
        if task['task_deadline']:
            if not task['marker_reached']: terms['missing_marker'] = -r['penalties']['missing_marker']
            if not task['stop_completed']: terms['not_stopped'] = -r['penalties']['not_stopped']
        value = sum(terms.values())
        if not math.isfinite(value): raise ValueError('Nonfinite V3 reward')
        task.update(reward_terms=terms, reward_id=r['id'])
        return value, task


def require_identity(actual, expected):
    if actual != expected:
        raise ValueError('V3 task/baseline/reward/estimator identity mismatch; ABI equality alone is insufficient')


def audit_replay(buffer, rows):
    if buffer.size()!=len(rows): raise ValueError('Replay/trace budget mismatch')
    for i, row in enumerate(rows):
        pairs = [(buffer.actions[i,0],row['policy_proposal']),
                 (buffer.observations[i,0],row['reference_trace']['observation']),
                 (buffer.next_observations[i,0],row['next_observation']),
                 ([buffer.rewards[i,0]],[row['reward']])]
        for actual, expected in pairs:
            np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
        if bool(buffer.dones[i,0])!=row['done'] or bool(buffer.timeouts[i,0])!=row['TimeLimit.truncated']:
            raise ValueError('V3 replay terminal/timeout mismatch')
    return dict(rows_checked=len(rows), action_semantics='policy_proposal_including_warmup_or_exploration',
                projected_action_not_substituted=True)
