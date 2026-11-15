"""Opt-in recovery Gym boundary sharing the existing simulator lifecycle."""
from dataclasses import asdict
import hashlib
import json
import math

from .recovery_contract import CONTRACT_ID, RecoveryAdapter, implementation_sources
from .recovery_task import RecoveryScore, RecoveryReward
from .recovery_motion import MotionTarget
from .unknown_step_environment import UnknownStepEnv
from .unknown_step_runtime import UnknownTaskData


class RecoveryEnv(UnknownStepEnv):
    def __init__(self, controller_config, backend, task_settings, reward_settings,
                 obstacles, bands, start_budget, recovery_reward, runtime_identity=None,
                 *, macro_ramp=None, motion_quality):
        if motion_quality is None:
            raise ValueError('Recovery environment requires explicit motion quality bounds')
        super().__init__(controller_config, backend, task_settings, reward_settings)
        self.adapter = RecoveryAdapter(controller_config)
        declared = controller_config.get('backend', {}).get('initial_pose_xy_yaw', [0.,0.,0.])
        self.scorer = RecoveryScore(task_settings, obstacles, bands, start_budget, declared,
                                    macro_ramp=macro_ramp, motion_quality=motion_quality)
        self.recovery_reward = dict(recovery_reward)
        self.startup_initialization = controller_config.get('backend', {}).get('startup_initialization')
        payload = dict(contract_id=CONTRACT_ID, controller=self.adapter.identity,
                       task=asdict(task_settings), reward=asdict(reward_settings),
                       obstacles=obstacles, bands=asdict(bands), start_budget=asdict(start_budget),
                       declared_estimator_initial_pose=declared,
                       runtime_configuration=runtime_identity, controller_configuration=controller_config,
                       recovery_reward=self.recovery_reward,
                       macro_ramp=macro_ramp, motion_quality=motion_quality,
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

    def _score(self, physical, trace):
        if trace.get('baseline_state_independent_of_policy') is not True:
            raise UnknownTaskData('Missing independent baseline evidence; no reward/replay label')
        left, right = trace['shaped_baseline_wheel_m_s']
        separation = self.adapter.pipeline.reference.limits.separation_m
        return self.scorer.update(physical, MotionTarget((left+right)/2., (right-left)/separation))

    def _initial_score(self, physical, view, info):
        if self.startup_initialization is None or info.get('synthetic_fixture') is True:
            return self.scorer.reset(physical)
        bootstrap, estimate = info.get('startup_bootstrap', {}), info.get('estimator_audit', {})
        age = physical.decision_stamp_s-estimate.get('stamp_s', -math.inf)
        if (bootstrap.get('contract_id') != self.startup_initialization
                or bootstrap.get('truth_input') is not False
                or estimate.get('truth_input') is not False
                or estimate.get('source') != 'wheel_imu_odometry'
                or estimate.get('initialization') != self.startup_initialization
                or not 0 <= age <= self.settings.maximum_source_age_s):
            raise UnknownTaskData('Missing causal startup integration evidence')
        return self.scorer.reset(physical, estimated_start_pose=estimate['pose'])

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
