"""Opt-in recovery Gym boundary sharing the existing simulator lifecycle."""
from dataclasses import asdict
import hashlib
import json
import math

from .recovery_contract import CONTRACT_ID, RecoveryAdapter, implementation_sources
from .recovery_task import RecoveryScore, RecoveryReward
from .unknown_step_environment import UnknownStepEnv


class RecoveryEnv(UnknownStepEnv):
    def __init__(self, controller_config, backend, task_settings, reward_settings,
                 obstacles, bands, start_budget, recovery_reward, runtime_identity=None):
        super().__init__(controller_config, backend, task_settings, reward_settings)
        self.adapter = RecoveryAdapter(controller_config)
        declared = controller_config.get('backend', {}).get('initial_pose_xy_yaw', [0.,0.,0.])
        self.scorer = RecoveryScore(task_settings, obstacles, bands, start_budget, declared)
        self.recovery_reward = dict(recovery_reward)
        payload = dict(contract_id=CONTRACT_ID, controller=self.adapter.identity,
                       task=asdict(task_settings), reward=asdict(reward_settings),
                       obstacles=obstacles, bands=asdict(bands), start_budget=asdict(start_budget),
                       declared_estimator_initial_pose=declared,
                       runtime_configuration=runtime_identity, controller_configuration=controller_config,
                       recovery_reward=self.recovery_reward,
                       sources=implementation_sources(),
                       hardware_authorized=False, physics_qualified=False)
        self.identity = dict(payload, sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest())

    def reset(self, *, seed=None, options=None):
        observation, info = super().reset(seed=seed, options=options)
        self.reward = RecoveryReward(self.reward_settings, info['task_initial']['goal_distance_m'],
                                     **self.recovery_reward)
        info['task_contract_id'] = CONTRACT_ID
        return observation, info

    def step(self, action):
        observation, reward, term, trunc, info = super().step(action)
        info['task_contract_id'] = CONTRACT_ID
        estimate = info.get('estimator_audit')
        if estimate is not None:
            x, y, yaw = estimate['pose']
            x0, y0 = self.settings.route_m[0]
            heading = self.scorer.heading
            info['estimated_tracking_diagnostic'] = dict(
                cross_track_m=-(x-x0)*math.sin(heading)+(y-y0)*math.cos(heading),
                heading_error_rad=math.atan2(math.sin(yaw-heading), math.cos(yaw-heading)),
                stamp_s=estimate['stamp_s'], physical_clearance_certificate=False)
        return observation, reward, term, trunc, info
