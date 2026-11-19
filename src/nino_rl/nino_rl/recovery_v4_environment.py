"""Causal slowdown v4 Gym boundary with separate physical scoring labels."""
from collections import deque
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import gymnasium as gym
import numpy as np

from nino_control.residual_velocity import FEATURES, SCALES, feature_frame
from .recovery_v4_contract import (Health, ProjectionState, RewardState, RewardLabels,
    EndReason, identity as software_identity, project_slowdown, score_reward)
from .recovery_task import RecoveryScore
from .recovery_motion import MotionTarget
from .unknown_step_runtime import PhysicalSample, UnknownTaskData

CONTRACT_ID = 'nino_recovery_slowdown_history107_v4'
MISSION_TARGET_SOURCE = 'frozen_mission_time_and_truth_route_progress_v4'
STATE_FEATURES = ('baseline_left_m_s', 'baseline_right_m_s', 'final_left_m_s',
                  'final_right_m_s', 'baseline_stop_latched', 'final_stop_latched',
                  'remaining_mission_time_fraction')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class V4Adapter:
    observation_space = gym.spaces.Box(-5., 5., shape=(107,), dtype=np.float32)
    action_space = gym.spaces.Box(-1., 1., shape=(1,), dtype=np.float32)

    def __init__(self, config, controller_config):
        self.config, self.controller = config, deepcopy(controller_config)
        if config.projection.history_frames != 5 or controller_config['control_interval_s'] != .1:
            raise ValueError('V4 ABI requires five real frames at 10 Hz')
        payload = dict(contract_id=CONTRACT_ID, software=software_identity(config),
            observation_size=107, features=list(FEATURES), scales=list(SCALES),
            history_frames=5, frame_order='oldest_to_newest', exact_state=list(STATE_FEATURES),
            state_wheel_scale=config.projection.wheel_speed_m_s, action_size=1,
            replay_action='requested_normalized_scalar_before_projection',
            previous_proposal_common='requested_slowdown_fraction',
            previous_accepted_common='accepted_slowdown_fraction', differential_fields=0.,
            geometry=controller_config['nominal_geometry'], mission_target_actor_input=False)
        self.identity = dict(payload, abi_sha256=_digest(payload))
        self.reset()

    def reset(self):
        self.rows, self.times = deque(maxlen=5), deque(maxlen=5)
        self.state = ProjectionState()
        self.previous_proposal = self.previous_accepted = 0.
        self.view = None
        self.pending = False

    @property
    def history_real_frames(self):
        return len(self.rows)

    def observe(self, view, *, elapsed_s):
        if self.pending:
            raise RuntimeError('Project before accepting the next observation')
        features = view['features']
        if set(features) not in (set(FEATURES[:18]), set(FEATURES)):
            raise UnknownTaskData('Only declared sensor and command features may enter actor history')
        if any(type(view[k]) is not bool for k in ('permission', 'sensors_fresh', 'fault', 'emergency_stop')):
            raise UnknownTaskData('Explicit source and ownership flags required')
        if set(view.get('source_samples', {})) - {'imu', 'wheel', 'baseline', 'final', 'status'}:
            raise UnknownTaskData('Privileged source channel prohibited')
        stamp = view['stamp_s']
        if not math.isfinite(stamp) or self.times and not 0 < stamp-self.times[-1] <= .15+1e-9:
            raise UnknownTaskData('History needs distinct increasing source-backed decisions')
        sample = dict(features)
        sample.update(previous_proposal_common=self.previous_proposal, previous_proposal_diff=0.,
                      previous_accepted_common=self.previous_accepted, previous_accepted_diff=0.)
        geometry = self.controller['nominal_geometry']
        try:
            frame = feature_frame(sample, geometry['radius_l'], geometry['radius_r'], geometry['separation'])
        except (ValueError, KeyError, TypeError) as exc:
            raise UnknownTaskData('Invalid actor sensor payload') from exc
        self.rows.append(frame)
        self.times.append(stamp)
        self.view = deepcopy(view)
        self.pending = True
        return self.observation(elapsed_s)

    def observation(self, elapsed_s):
        if not math.isfinite(elapsed_s) or elapsed_s < 0:
            raise UnknownTaskData('Invalid mission clock')
        # Incomplete warmup remains private to reset. No padded tensor is returned.
        if len(self.rows) != 5:
            return None
        p = self.state
        scale = self.config.projection.wheel_speed_m_s
        exact = [*(v/scale for v in (*p.baseline_wheel_m_s, *p.final_wheel_m_s)),
                 float(p.baseline_latched), float(p.final_latched),
                 max(0., (self.config.mission.deadline_s-elapsed_s)/self.config.mission.deadline_s)]
        return np.asarray([x for row in self.rows for x in row]+exact, dtype=np.float32)

    def project(self, action):
        if not self.pending:
            raise RuntimeError('Observe before projecting')
        value = np.asarray(action, dtype=np.float64)
        if value.shape != (1,) or not np.all(np.isfinite(value)) or abs(value[0]) > 1:
            raise ValueError('Finite shape-(1,) action in [-1,1] required')
        view = self.view
        health = Health(view['permission'], view['emergency_stop'], view['fault'],
                        float(view['features']['imu_age_s']), float(view['features']['wheel_age_s']),
                        float(view['command_age_s']), len(self.rows))
        if not view['sensors_fresh']:
            health = Health(health.permission, health.emergency_stop, health.fault,
                            math.inf, health.wheel_age_s, health.command_age_s, len(self.rows))
        result = project_slowdown(self.config.projection, self.state, tuple(view['baseline']),
                                  float(value[0]), .1, health)
        self.state, self.pending = result.next_state, False
        self.previous_proposal = result.requested_slowdown_m_s/self.config.projection.max_slowdown_m_s
        self.previous_accepted = result.accepted_slowdown_m_s/self.config.projection.max_slowdown_m_s
        return result

    def trace(self, result):
        return dict(contract_id=CONTRACT_ID, abi_sha256=self.identity['abi_sha256'],
            requested_scalar_action=[result.proposed_action], replay_action=[result.proposed_action],
            requested_slowdown_m_s=result.requested_slowdown_m_s,
            accepted_slowdown_m_s=result.accepted_slowdown_m_s,
            accepted_slowdown_fraction=self.previous_accepted,
            accepted_common_normalized=self.previous_accepted,
            shaped_baseline_wheel_m_s=list(result.next_state.baseline_wheel_m_s),
            accepted_reference_wheel_m_s=list(result.next_state.final_wheel_m_s),
            nominal_body_reference=list(result.nominal_body_reference),
            body_reference=list(result.final_body_reference),
            baseline_state_independent_of_policy=True, projection_state=result.next_state.to_dict(),
            reason=result.reason, learning_eligible=result.learning_eligible,
            motor_execution_verified=False, reference_evidence='drive_request_ack_not_hardware_execution')

    def require_checkpoint(self, candidate):
        if candidate != self.identity:
            raise ValueError('V4 observation/action identity mismatch; v3 cannot resume')


def governor_action(observation):
    """Frozen sensor-only baseline, not a tuned or certified safety controller."""
    values = np.asarray(observation, dtype=float)
    if values.shape != (107,) or not np.all(np.isfinite(values)):
        raise ValueError('Governor requires a valid v4 observation')
    frame = values[80:100]*np.asarray(SCALES)
    disturbed = max(abs(frame[4]), abs(frame[5]), abs(frame[6])) > .15 or abs(frame[9]-9.80665) > 1.
    return np.asarray([1. if disturbed else -1.], dtype=np.float32)


class V4Env(gym.Env):
    observation_space = V4Adapter.observation_space
    action_space = V4Adapter.action_space

    def __init__(self, config, controller_config, backend, task_settings, obstacles, bands,
                 start_budget, *, runtime_identity, macro_ramp=None, motion_quality):
        super().__init__()
        if (controller_config['control_interval_s'] != task_settings.interval_s
                or math.dist(*task_settings.route_m) != config.mission.route_length_m
                or task_settings.maximum_seconds != config.mission.deadline_s):
            raise ValueError('V4 mission/task/control contracts disagree')
        self.config, self.settings, self.backend = config, task_settings, backend
        self.adapter = V4Adapter(config, controller_config)
        self.scorer = RecoveryScore(task_settings, obstacles, bands, start_budget,
            controller_config['backend']['initial_pose_xy_yaw'], macro_ramp=macro_ramp,
            motion_quality=motion_quality)
        self.startup_initialization = controller_config['backend'].get('startup_initialization')
        payload = dict(contract_id=CONTRACT_ID, controller=self.adapter.identity,
            task=asdict(task_settings), bands=asdict(bands), start_budget=asdict(start_budget),
            obstacles=obstacles, macro_ramp=macro_ramp, motion_quality=motion_quality,
            runtime_configuration=runtime_identity, controller_configuration=controller_config,
            mission_target_source=MISSION_TARGET_SOURCE,
            environment_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            hardware_authorized=False)
        self.identity = dict(payload, sha256=_digest(payload))
        self.done, self.closed = True, False
        self.current_observation = None
        self.reward_state = RewardState()

    def _sample(self, view, info):
        ages = (view['features']['imu_age_s'], view['features']['wheel_age_s'])
        if (view['sensors_fresh'] is not True
                or not all(type(age) in (int, float) and math.isfinite(age)
                    and 0 <= age <= self.config.projection.maximum_source_age_s for age in ages)
                or not math.isfinite(view['command_age_s'])
                or not 0 <= view['command_age_s'] <= self.config.projection.maximum_command_age_s):
            raise UnknownTaskData('Incoming sensor/command support invalid; no reward or replay row')
        if (view['permission'] is not True or view['fault'] is not False
                or view['emergency_stop'] is not False):
            raise UnknownTaskData('Command owner/fault intervention; quarantine rather than physical failure')
        if info.get('truth_used_for_guidance') is not False:
            raise UnknownTaskData('Explicit non-oracle guidance evidence required')
        sample = info.get('physical_sample')
        if not isinstance(sample, PhysicalSample):
            raise UnknownTaskData('Typed physical measurement required')
        sample.validate()
        if abs(sample.decision_stamp_s-view['stamp_s']) > 1e-8:
            raise UnknownTaskData('Decision clocks disagree')
        if not info.get('synthetic_fixture'):
            if info.get('source_admission', {}).get('valid') is not True:
                raise UnknownTaskData('Retained raw source admission failed')
            estimate = info.get('estimator_audit', view.get('estimator_audit', {}))
            if (estimate.get('truth_input') is not False or estimate.get('source') != 'wheel_imu_odometry'
                    or estimate.get('initialization') != self.startup_initialization
                    or not 0 <= sample.decision_stamp_s-estimate.get('stamp_s', -math.inf) <= self.settings.maximum_source_age_s+1e-8):
                raise UnknownTaskData('Causal wheel/IMU estimate evidence required')
        return sample

    def _abort(self):
        self.done = True
        self.closed = True
        self.backend.close()

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self.closed:
            raise RuntimeError('Environment closed')
        self.done = True
        self.adapter.reset()
        try:
            view, info = self.backend.reset(seed=seed)
            physical = self._sample(view, info)
            backend_reset = dict(info, physical_sample=asdict(physical))
            warmup = [dict(stamp_s=physical.stamp_s, decision_stamp_s=physical.decision_stamp_s)]
            self.adapter.observe(view, elapsed_s=0.)
            for _ in range(4):
                result = self.adapter.project([-1.])
                if result.next_state.final_latched:
                    raise UnknownTaskData('Warmup source or authority STOP')
                view, _, term, trunc, info = self.backend.advance_reference(0., 0., self.settings.interval_s)
                physical = self._sample(view, info)
                if term or trunc:
                    raise UnknownTaskData('Backend ended during reset warmup')
                self.adapter.observe(view, elapsed_s=0.)
                warmup.append(dict(stamp_s=physical.stamp_s, decision_stamp_s=physical.decision_stamp_s))
            # Warmup sends zero, so projector memory must describe that executed reference.
            self.adapter.state = ProjectionState()
            self.adapter.previous_proposal = self.adapter.previous_accepted = 0.
            initial_estimate = info.get('estimator_audit', view.get('estimator_audit'))
            initial = self.scorer.reset(physical, estimated_start_pose=(
                initial_estimate['pose'] if initial_estimate is not None else None))
            self.epoch_s = physical.decision_stamp_s
            self.reward_state = RewardState(highest_seen_progress_m=max(0., initial['progress_m']))
            self.current_observation = self.adapter.observation(0.)
            self.done = False
            return self.current_observation.copy(), dict(info, physical_sample=asdict(physical),
                backend_reset=backend_reset, warmup=dict(real_frames=5, source_frames=warmup,
                    replay_rows=0, zero_advances=4), task_initial=dict(initial, physical_sample=asdict(physical)),
                task_contract_id=CONTRACT_ID, abi_sha256=self.adapter.identity['abi_sha256'])
        except Exception:
            self._abort()
            raise

    def step(self, action):
        if self.done or self.closed:
            raise RuntimeError('Reset before stepping a terminal or closed environment')
        before = self.current_observation.copy()
        try:
            projected = self.adapter.project(action)
            trace = self.adapter.trace(projected)
            if projected.reason in ('stale_source', 'invalid_input', 'invalid_state', 'authority_or_fault', 'stop_latched'):
                # Execute the explicit STOP before closing, never admit this action to replay.
                self.backend.advance_reference(0., 0., self.settings.interval_s)
                raise UnknownTaskData('Current source invalid; STOP and no replay transition')
            view, _, backend_terminal, backend_truncated, info = self.backend.advance_reference(
                *projected.final_body_reference, self.settings.interval_s)
            physical = self._sample(view, info)
            elapsed = physical.decision_stamp_s-self.epoch_s
            progress = self.scorer.geometry(physical)['progress_m']
            target = MotionTarget(self.config.mission.target(elapsed, progress), 0.)
            outcome = self.scorer.update(physical, target)
            outcome.update(contract_id=CONTRACT_ID, motion_target_source=MISSION_TARGET_SOURCE,
                           inherited_geometry_scorer='RecoveryScore', mission_target=asdict(target))
            if projected.next_state.final_latched:
                outcome.update(task_success=False, terminated=True, termination_reason='reference_intervention')
            if backend_terminal and not outcome['terminated']:
                raise UnknownTaskData('Unclassified backend terminal')
            if elapsed >= self.config.mission.deadline_s-1e-8:
                reason = EndReason.INTRINSIC_DEADLINE
                # Avoid losing a finite deadline because of binary clock representation.
                elapsed = max(elapsed, self.config.mission.deadline_s)
            elif outcome['task_success']:
                reason = EndReason.SUCCESS
            elif outcome['terminated']:
                reason = EndReason.PHYSICAL_FAILURE
            elif backend_truncated:
                reason = EndReason.EXTERNAL_SAMPLING
            else:
                reason = EndReason.ONGOING
            result = score_reward(self.config.reward, self.reward_state, RewardLabels(
                elapsed, outcome['progress_m'], outcome['cross_track_m'], outcome['heading_error_rad'],
                outcome['target_speed_error_m_s'], trace['accepted_slowdown_fraction'],
                outcome['stability_cost'], reason))
            self.reward_state = result.next_state
            outcome.update(terminated=result.end.terminated, truncated=result.end.truncated,
                end_reason=result.end_reason.value, bootstrap=result.end.bootstrap,
                right_censored=result.end.truncated,
                task_success=result.end_reason is EndReason.SUCCESS)
            if result.end_reason is EndReason.INTRINSIC_DEADLINE:
                outcome['termination_reason'] = 'intrinsic_deadline'
            elif backend_truncated and not result.end.terminated:
                outcome['termination_reason'] = 'external_cutoff'
            self.current_observation = self.adapter.observe(view, elapsed_s=elapsed)
            self.done = result.end.terminated or result.end.truncated
        except Exception:
            self._abort()
            raise
        return self.current_observation.copy(), result.total, result.end.terminated, result.end.truncated, dict(
            info, physical_sample=asdict(physical), task=outcome, reward_terms=dict(result.terms),
            reward_state=asdict(self.reward_state), task_contract_id=CONTRACT_ID,
            abi_sha256=self.adapter.identity['abi_sha256'], observation=before.tolist(),
            next_observation=self.current_observation.tolist(), requested_scalar_action=trace['replay_action'],
            replay_action=trace['replay_action'], reference_trace=trace, truth_used_for_guidance=False)

    def require_checkpoint(self, candidate):
        if candidate != self.identity:
            raise ValueError('Full v4 environment identity mismatch')

    def close(self):
        if not self.closed:
            self.done, self.closed = True, True
            self.backend.close()
