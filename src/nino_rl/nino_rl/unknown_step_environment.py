"""Gym interface for the new goal task, tested with a synthetic backend only.

The Gazebo lifecycle does not yet emit this module's typed physical_sample
boundary. No launcher/Studio training engine is registered by this module.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import gymnasium as gym
import numpy as np

from .unknown_step_runtime import (CONTRACT_ID, PhysicalSample, SensorOnlyCommonAdapter,
                                   TraversalReward, TraversalScore, UnknownTaskData)


class UnknownStepEnv(gym.Env):
    """Backend: reset -> (view, info), advance_reference -> standard 5-tuple.

    Required info['physical_sample'] is a PhysicalSample built from source-stamped
    simulation labels plus final reference and drive/owner evidence. Never build
    it from encoder odometry, requested motion, or a copied decision timestamp.
    Caller owns the frozen layout, geometry/settings, reward weights and budget.
    """
    observation_space = gym.spaces.Box(-5., 5., shape=(100,), dtype=np.float32)
    action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)

    def __init__(self, controller_config, backend, task_settings, reward_settings):
        super().__init__()
        if controller_config['control_interval_s'] != task_settings.interval_s:
            raise ValueError('Controller and task decision intervals must agree')
        self.adapter = SensorOnlyCommonAdapter(controller_config)
        self.backend = backend
        self.settings, self.reward_settings = task_settings, reward_settings
        self.scorer = TraversalScore(task_settings)
        payload = dict(contract_id=CONTRACT_ID, controller=self.adapter.identity,
                       task=asdict(task_settings), reward=asdict(reward_settings),
                       environment_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       gazebo_integration_verified=False, hardware_authorized=False)
        self.identity = dict(payload, sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest())
        self.reward = None
        self.current_observation = None
        self.done, self.closed = True, False

    @staticmethod
    def _sample(view, info):
        if info.get('truth_used_for_guidance') is not False:
            raise UnknownTaskData('Explicit non-oracle guidance evidence required')
        value = info.get('physical_sample')
        if not isinstance(value, PhysicalSample):
            raise UnknownTaskData('Typed physical_sample boundary is required; no fabricated labels')
        if abs(value.decision_stamp_s - view['stamp_s']) > 1e-8:
            raise UnknownTaskData('Controller and evaluation decision clocks differ')
        return value

    def require_checkpoint(self, identity):
        if identity != self.identity:
            raise ValueError('Full task/reward/controller/environment identity mismatch')

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self.closed:
            raise RuntimeError('Environment closed')
        self.done = True
        self.adapter.reset()
        view, info = self.backend.reset(seed=seed)
        physical = self._sample(view, info)
        initial = self.scorer.reset(physical)
        self.reward = TraversalReward(self.reward_settings, initial['goal_distance_m'])
        self.current_observation = self.adapter.observe(view)
        self.done = False
        return self.current_observation.copy(), dict(info, physical_sample=asdict(physical),
                                                     task_contract_id=CONTRACT_ID,
                                                     task_initial=initial,
                                                     abi_sha256=self.adapter.identity['abi_sha256'])

    def step(self, action):
        if self.done or self.closed:
            raise RuntimeError('Reset before stepping a terminal or closed environment')
        before = self.current_observation.copy()
        trace = self.adapter.project(action)
        try:
            view, _, backend_terminal, backend_truncated, info = self.backend.advance_reference(
                *trace['body_reference'], self.settings.interval_s)
            physical = self._sample(view, info)
            outcome = self.scorer.update(physical)
            if self.adapter.pipeline.reference.latched:
                # Projection/ownership faults are explicit failures when the
                # measurement boundary itself is valid, never hidden successes.
                outcome.update(task_success=False, terminated=True,
                               termination_reason='reference_intervention')
            if backend_terminal and not outcome['terminated']:
                raise UnknownTaskData('Backend terminal lacks a classified physical task outcome')
            if backend_truncated and not outcome['terminated']:
                outcome.update(truncated=True, termination_reason='external_cutoff', right_censored=True)
            value, terms = self.reward.update(outcome, trace['accepted_common_normalized'])
            self.done = bool(outcome['terminated'] or outcome['truncated'])
            self.current_observation = self.adapter.observe(view)
        except Exception:
            self.done = True  # The failed step is not a valid replay transition.
            raise
        return self.current_observation.copy(), value, bool(outcome['terminated']), bool(outcome['truncated']), dict(
            info, physical_sample=asdict(physical), task=outcome, reward_terms=terms,
            task_contract_id=CONTRACT_ID, abi_sha256=self.adapter.identity['abi_sha256'],
            observation=before.tolist(), next_observation=self.current_observation.tolist(),
            requested_scalar_action=trace['requested_scalar_action'],
            replay_action=trace['replay_action'], reference_trace=trace,
            truth_used_for_guidance=False)

    def close(self):
        if not self.closed:
            self.done, self.closed = True, True
            self.backend.close()
