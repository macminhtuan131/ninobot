"""Offline components for unknown-obstacle traversal, path following and goal stop.

No ROS/Gazebo startup, model loading or training is performed here. The physical
scorer receives privileged simulation labels; the controller receives a separate
allowlisted sensor/reference view. Integrating these components with the Gazebo
lifecycle and releasing an experiment remain separate, unverified work.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from nino_control.residual_pipeline import ResidualPipeline
from nino_control.residual_velocity import FEATURES, actor_contract
from .residual_guidance import GuidanceReference

CONTRACT_ID = 'nino_unknown_step_goal_history100_common_v1'


class UnknownTaskData(ValueError):
    """Invalid/missing measurement: quarantine, never invent a failure transition."""


def _finite(values):
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def _angle(value):
    return math.atan2(math.sin(value), math.cos(value))


@dataclass(frozen=True)
class TaskSettings:
    """Required numeric inputs, with no implicit accepted application thresholds.

    envelope_m contains all eight corners of a conservative body-frame box that
    encloses ALL robot collisions, including the swept caster envelope. Its
    identity must be pinned by the eventual protocol. This is a conservative
    clearance certificate only for the declared geometry, not contact fidelity.
    The initial scope is a straight route and one transverse rigid obstacle.
    None for both obstacle bounds means a genuine clear-floor control.
    """
    route_m: tuple
    envelope_m: tuple
    envelope_identity: str
    obstacle_near_m: float | None
    obstacle_far_m: float | None
    clearance_m: float
    interval_s: float
    maximum_source_age_s: float
    maximum_seconds: float
    goal_tolerance_m: float
    goal_heading_tolerance_rad: float
    maximum_cross_track_m: float
    continuous_stop_s: float
    stop_body_speed_m_s: float
    stop_yaw_rad_s: float
    stop_wheel_rad_s: float
    stop_reference_m_s: float
    stall_window_s: float
    stall_progress_m: float
    maximum_tilt_rad: float
    minimum_body_z_m: float

    def __post_init__(self):
        object.__setattr__(self, 'route_m', tuple(tuple(p) for p in self.route_m))
        object.__setattr__(self, 'envelope_m', tuple(tuple(p) for p in self.envelope_m))
        positive = ('interval_s', 'maximum_source_age_s', 'maximum_seconds', 'goal_tolerance_m',
                    'goal_heading_tolerance_rad', 'maximum_cross_track_m',
                    'continuous_stop_s', 'stop_body_speed_m_s', 'stop_yaw_rad_s',
                    'stop_wheel_rad_s', 'stop_reference_m_s', 'stall_window_s',
                    'stall_progress_m', 'maximum_tilt_rad')
        if any(not _finite([getattr(self, k)]) or getattr(self, k) <= 0 for k in positive):
            raise ValueError('Explicit positive finite task thresholds required')
        if (not _finite([self.clearance_m, self.minimum_body_z_m]) or self.clearance_m < 0
                or self.continuous_stop_s >= self.maximum_seconds
                or not self.interval_s <= self.stall_window_s < self.maximum_seconds
                or self.maximum_tilt_rad >= math.pi / 2):
            raise ValueError('Invalid clearance, stop, stall or tilt contract')
        if (len(self.route_m) != 2 or any(len(p) != 2 or not _finite(p) for p in self.route_m)
                or math.dist(*self.route_m) <= 2 * self.goal_tolerance_m):
            raise ValueError('A finite nonzero straight start/goal route is required')
        if not isinstance(self.envelope_identity, str) or not self.envelope_identity:
            raise ValueError('Pinned conservative full-robot envelope identity required')
        if len(self.envelope_m) != 8 or any(len(p) != 3 or not _finite(p) for p in self.envelope_m):
            raise ValueError('Eight finite full-robot bounding-box corners required')
        axes = [sorted(set(p[k] for p in self.envelope_m)) for k in range(3)]
        if any(len(a) != 2 for a in axes) or set(map(tuple, self.envelope_m)) != {
                (x, y, z) for x in axes[0] for y in axes[1] for z in axes[2]}:
            raise ValueError('Envelope must contain every corner of a nondegenerate box')
        if (self.obstacle_near_m is None) != (self.obstacle_far_m is None):
            raise ValueError('Both obstacle boundaries or neither are required')
        if self.obstacle_near_m is not None:
            if (not _finite([self.obstacle_near_m, self.obstacle_far_m])
                    or not 0 < self.obstacle_near_m < self.obstacle_far_m < math.dist(*self.route_m)):
                raise ValueError('Obstacle interval must lie strictly inside the route')


@dataclass(frozen=True)
class PhysicalSample:
    """Evaluation-only simulation truth and actual reference/feedback evidence.

    stamp_s is the source simulation clock. No receipt-clock substitution. The
    integration adapter must establish a valid common measurement boundary first.
    """
    stamp_s: float
    decision_stamp_s: float
    pose_m_rad: tuple  # x, y, z, roll, pitch, yaw
    body_speed_norm_m_s: float
    body_yaw_rad_s: float
    wheel_rad_s: tuple
    accepted_reference_m_s: tuple  # Left/right projected references, not motor ACK.
    motion_requested: bool
    owner_intervention: bool
    drive_fault: bool

    def validate(self):
        if (not isinstance(self.pose_m_rad, (list, tuple)) or len(self.pose_m_rad) != 6
                or not isinstance(self.wheel_rad_s, (list, tuple)) or len(self.wheel_rad_s) != 2
                or not isinstance(self.accepted_reference_m_s, (list, tuple))
                or len(self.accepted_reference_m_s) != 2
                or not _finite([self.stamp_s, self.decision_stamp_s, *self.pose_m_rad, self.body_speed_norm_m_s,
                                self.body_yaw_rad_s, *self.wheel_rad_s, *self.accepted_reference_m_s])
                or self.body_speed_norm_m_s < 0
                or any(type(getattr(self, k)) is not bool
                       for k in ('motion_requested', 'owner_intervention', 'drive_fault'))):
            raise UnknownTaskData('Missing/nonfinite truth, feedback, reference or owner evidence')


class TraversalScore:
    """Physical task outcomes; estimator arrival alone cannot produce success."""
    def __init__(self, settings: TaskSettings):
        self.c = settings
        (self.x0, self.y0), self.goal = settings.route_m
        self.length = math.dist(*settings.route_m)
        self.heading = math.atan2(self.goal[1] - self.y0, self.goal[0] - self.x0)
        self.tangent = (math.cos(self.heading), math.sin(self.heading))
        self.reset_state()

    def reset_state(self):
        self.initial = self.last = None
        self.quiet_since = None
        self.motion = deque()
        self.count = 0
        self.cross_sq = self.heading_sq = self.maximum_cross = self.measured_s = 0.0
        self.done = False

    def geometry(self, sample):
        x, y, z, roll, pitch, yaw = sample.pose_m_rad
        cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch),
                                 math.sin(pitch), math.cos(yaw), math.sin(yaw))
        # Full Rz(yaw) Ry(pitch) Rx(roll) projection, including elevated corners.
        projections = []
        for ex, ey, ez in self.c.envelope_m:
            rx = cy * cp * ex + (cy * sp * sr - sy * cr) * ey + (cy * sp * cr + sy * sr) * ez
            ry = sy * cp * ex + (sy * sp * sr + cy * cr) * ey + (sy * sp * cr - cy * sr) * ez
            projections.append((x + rx - self.x0) * self.tangent[0]
                               + (y + ry - self.y0) * self.tangent[1])
        progress = (x - self.x0) * self.tangent[0] + (y - self.y0) * self.tangent[1]
        cross = -(x - self.x0) * self.tangent[1] + (y - self.y0) * self.tangent[0]
        return dict(progress_m=progress, cross_track_m=cross,
                    heading_error_rad=_angle(yaw - self.heading),
                    goal_distance_m=math.hypot(x - self.goal[0], y - self.goal[1]),
                    rear_support_m=min(projections), front_support_m=max(projections))

    def reset(self, sample: PhysicalSample):
        self.reset_state()
        sample.validate()
        if not 0 <= sample.decision_stamp_s - sample.stamp_s <= self.c.maximum_source_age_s:
            raise UnknownTaskData('Initial truth source is stale/future')
        g = self.geometry(sample)
        if (sample.owner_intervention or sample.drive_fault
                or max(map(abs, sample.pose_m_rad[3:5])) > self.c.maximum_tilt_rad
                or sample.pose_m_rad[2] < self.c.minimum_body_z_m):
            raise UnknownTaskData('Initial owner/drive/physical state is invalid')
        if (abs(g['progress_m']) > self.c.goal_tolerance_m
                or abs(g['cross_track_m']) > self.c.maximum_cross_track_m):
            raise UnknownTaskData('Initial physical pose does not match the declared start')
        if (self.c.obstacle_near_m is not None
                and g['front_support_m'] >= self.c.obstacle_near_m - self.c.clearance_m):
            raise UnknownTaskData('Whole robot must start before the obstacle')
        self.initial = self.last = sample
        return g

    def update(self, sample: PhysicalSample):
        if self.initial is None or self.done:
            raise RuntimeError('Reset before task updates and after terminal outcomes')
        sample.validate()
        dt = sample.stamp_s - self.last.stamp_s
        decision_dt = sample.decision_stamp_s - self.last.decision_stamp_s
        source_age = sample.decision_stamp_s - sample.stamp_s
        if (abs(decision_dt - self.c.interval_s) > 1e-7 or dt <= 0
                or not -1e-8 <= source_age <= self.c.maximum_source_age_s + 1e-8):
            raise UnknownTaskData('Clock gap/duplicate/reversal or stale/future truth; task outcome UNKNOWN')
        c = self.c
        elapsed = sample.decision_stamp_s - self.initial.decision_stamp_s
        g = self.geometry(sample)
        cleared = c.obstacle_far_m is None or g['rear_support_m'] > c.obstacle_far_m + c.clearance_m
        at_goal = (g['goal_distance_m'] <= c.goal_tolerance_m
                   and abs(g['heading_error_rad']) <= c.goal_heading_tolerance_rad)
        quiet = bool(at_goal and cleared
                     and sample.body_speed_norm_m_s < c.stop_body_speed_m_s
                     and abs(sample.body_yaw_rad_s) < c.stop_yaw_rad_s
                     and max(map(abs, sample.wheel_rad_s)) < c.stop_wheel_rad_s
                     and max(map(abs, sample.accepted_reference_m_s)) <= c.stop_reference_m_s)
        if quiet and self.quiet_since is None:
            self.quiet_since = sample.stamp_s
        elif not quiet:
            self.quiet_since = None
        quiet_s = 0.0 if self.quiet_since is None else sample.stamp_s - self.quiet_since

        if sample.motion_requested and not at_goal:
            # Require a full observed motion window; warmup/goal stop do not count.
            self.motion.append((sample.stamp_s, g['progress_m']))
            while len(self.motion) > 1 and sample.stamp_s - self.motion[1][0] >= c.stall_window_s - 1e-8:
                self.motion.popleft()
        else:
            self.motion.clear()
        stalled = bool(self.motion
                       and sample.stamp_s - self.motion[0][0] >= c.stall_window_s - 1e-8
                       and g['progress_m'] - self.motion[0][1] < c.stall_progress_m)

        reason = None
        if sample.owner_intervention or sample.drive_fault:
            reason = 'owner_intervention' if sample.owner_intervention else 'drive_fault'
        elif (max(abs(sample.pose_m_rad[3]), abs(sample.pose_m_rad[4])) > c.maximum_tilt_rad
              or sample.pose_m_rad[2] < c.minimum_body_z_m):
            reason = 'physical_envelope_failure'
        elif abs(g['cross_track_m']) > c.maximum_cross_track_m:
            reason = 'path_violation'
        elif stalled:
            reason = 'stall'
        elif quiet_s >= c.continuous_stop_s - 1e-8 and elapsed <= c.maximum_seconds + 1e-8:
            reason = 'task_success'
        elif elapsed >= c.maximum_seconds - 1e-8:
            reason = 'task_timeout'

        self.count += 1
        self.measured_s += dt
        self.cross_sq += g['cross_track_m'] ** 2 * dt
        self.heading_sq += g['heading_error_rad'] ** 2 * dt
        self.maximum_cross = max(self.maximum_cross, abs(g['cross_track_m']))
        self.last, self.done = sample, reason is not None
        return dict(contract_id=CONTRACT_ID, measurement_valid=True, elapsed_s=elapsed,
                    truth_source_stamp_s=sample.stamp_s, decision_stamp_s=sample.decision_stamp_s,
                    truth_source_age_s=source_age, measured_elapsed_s=self.measured_s,
                    **g, whole_robot_clear=cleared, at_physical_goal=at_goal,
                    quiet_now=quiet, continuous_quiet_s=quiet_s,
                    cross_track_rmse_m=math.sqrt(self.cross_sq / self.measured_s),
                    maximum_cross_track_m=self.maximum_cross,
                    heading_rmse_rad=math.sqrt(self.heading_sq / self.measured_s),
                    task_success=reason == 'task_success', termination_reason=reason,
                    terminated=self.done, truncated=False,
                    timeout_is_part_of_finite_task=True, samples=self.count,
                    obstacle_contact_is_not_automatic_failure=True)


@dataclass(frozen=True)
class RewardSettings:
    progress: float
    cross_track: float
    heading: float
    time: float
    accepted_action: float
    accepted_action_change: float
    success: float
    failure: float
    cross_scale_m: float
    heading_scale_rad: float

    def __post_init__(self):
        values = asdict(self)
        if not _finite(values.values()) or any(v < 0 for v in values.values()):
            raise ValueError('Finite nonnegative explicit reward settings required')
        if min(self.cross_scale_m, self.heading_scale_rad, self.progress,
               self.time, self.success, self.failure) <= 0:
            raise ValueError('Progress/time/outcome weights and error scales must be positive')


class TraversalReward:
    """Separate proposal objective; no reward weights have been accepted for runs."""
    def __init__(self, settings: RewardSettings, initial_goal_distance_m: float):
        if not _finite([initial_goal_distance_m]) or initial_goal_distance_m < 0:
            raise ValueError('Finite initial physical goal distance required')
        self.c, self.distance, self.previous_action = settings, initial_goal_distance_m, 0.0
        self.previous_time, self.done = 0.0, False

    def update(self, outcome, accepted_common_normalized):
        if self.done:
            raise RuntimeError('New reward state required after terminal')
        if outcome.get('measurement_valid') is not True:
            raise UnknownTaskData('No reward/replay label for an invalid measurement')
        names = ('elapsed_s', 'goal_distance_m', 'cross_track_m', 'heading_error_rad')
        if not _finite([outcome.get(k) for k in names] + [accepted_common_normalized]):
            raise UnknownTaskData('Missing/nonfinite reward labels')
        dt = outcome['elapsed_s'] - self.previous_time
        if dt <= 0 or abs(accepted_common_normalized) > 1 + 1e-7:
            raise ValueError('Increasing reward clock and normalized accepted correction required')
        c, action = self.c, accepted_common_normalized
        terms = dict(progress=c.progress * (self.distance - outcome['goal_distance_m']),
                     cross_track=-c.cross_track * (outcome['cross_track_m'] / c.cross_scale_m) ** 2 * dt,
                     heading=-c.heading * (outcome['heading_error_rad'] / c.heading_scale_rad) ** 2 * dt,
                     time=-c.time * dt, accepted_action=-c.accepted_action * action ** 2 * dt,
                     accepted_action_change=-c.accepted_action_change * (action - self.previous_action) ** 2 / dt)
        if outcome['terminated']:
            terms['outcome'] = c.success if outcome['task_success'] else -c.failure
        self.distance, self.previous_time, self.previous_action = outcome['goal_distance_m'], outcome['elapsed_s'], action
        self.done = outcome['terminated']
        return sum(terms.values()), terms


class SensorOnlyCommonAdapter:
    """100D causal history / 1D common correction, without stop-time features.

    Retains the former obstacle authority (±0.02 m/s) and inherited projection.
    This is a NEW task ABI, not a conversion of a common103 checkpoint. The
    simulator integration must call observe/project exactly once per decision.
    """
    def __init__(self, config):
        self.config = deepcopy(config)
        inherited = actor_contract(config)
        if inherited['observation_size'] != 100 or config['control_interval_s'] != .1:
            raise ValueError('Initial unknown-step adapter retains 5 frames at 10 Hz')
        if config['reference_limits']['residual_wheel_m_s'] != .04:
            raise ValueError('Inherited residual normalization must remain 0.04 m/s')
        self.bound_m_s = .02
        self.pipeline = ResidualPipeline(config, governor=False)
        payload = dict(contract_id=CONTRACT_ID, inherited=inherited,
                       observation_size=100, action_size=1, common_bound_m_s=self.bound_m_s,
                       differential=0.0, planned_stop_features=False,
                       replay_action='requested_normalized_scalar_before_projection',
                       hardware_authorized=False,
                       source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        self.identity = dict(payload, abi_sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest())
        self.pending = False

    def reset(self):
        self.pipeline.reset()
        self.pending = False

    def observe(self, view):
        if self.pending:
            raise RuntimeError('Project the pending observation before another decision')
        names = set(view['features'])
        if names not in (set(FEATURES[:18]), set(FEATURES)):
            raise ValueError('Only declared sensor/command features may enter history')
        if any(type(view[k]) is not bool for k in ('permission', 'sensors_fresh', 'fault', 'emergency_stop')):
            raise ValueError('Explicit source/health flags required')
        samples = view.get('source_samples')
        if samples is not None and set(samples) - {'imu', 'wheel', 'baseline', 'final', 'status'}:
            raise ValueError('Privileged channel in controller source samples')
        allowed = ('features', 'baseline', 'stamp_s', 'command_age_s', 'sensors_fresh',
                   'permission', 'fault', 'emergency_stop', 'source_samples',
                   'input_ages_s', 'freshness_scope', 'actual_actuator_target')
        selected = {k: deepcopy(view[k]) for k in allowed if k in view}
        result = np.asarray(self.pipeline.observe(selected), dtype=np.float32)
        self.pending = True
        return result

    def project(self, requested):
        if not self.pending:
            raise RuntimeError('Observe before requesting an action')
        a = np.asarray(requested, dtype=np.float32)
        if a.shape != (1,) or not np.all(np.isfinite(a)) or abs(float(a[0])) > 1:
            raise ValueError('Finite scalar normalized action in [-1,1] required')
        mapped = (float(a[0]) * self.bound_m_s / .04, 0.0)
        trace = self.pipeline.project(mapped, self.config['control_interval_s'], 1.0)
        self.pending = False
        dl, dr = trace.get('accepted_policy_delta_wheel_m_s', (0., 0.))
        return dict(trace, task_contract_id=CONTRACT_ID,
                    abi_sha256=self.identity['abi_sha256'], requested_scalar_action=a.tolist(),
                    requested_common_m_s=float(a[0]) * self.bound_m_s,
                    inherited_proposal=list(mapped), replay_action=a.tolist(),
                    accepted_common_normalized=(dl + dr) / (2 * self.bound_m_s))

    def require_checkpoint(self, checkpoint_identity):
        if checkpoint_identity != self.identity:
            raise ValueError('Task/observation/action ABI mismatch; common103 cannot resume here')


class EstimatedGoalReference:
    """Known route, estimator-only follower, and latched goal stop; no bump map.

    The latch uses the follower's estimate only. The physical scorer can still
    report failure when the estimate stops the robot short of the physical goal.
    """
    def __init__(self, guidance_config, *, epoch):
        self.guidance = GuidanceReference(guidance_config, epoch=epoch)
        if self.guidance.contract['oracle']:
            raise ValueError('Truth-based guidance is forbidden in the unknown-step task')
        self.stopped = False

    def update_pose(self, sample):
        return self.guidance.update_pose(sample)

    def command(self, stamp_s, *, permission, stop_requested=False):
        result = self.guidance.command(stamp_s, permission=permission,
                                       stop_requested=stop_requested)
        if result['valid'] and result['reason'] == 'goal_reference_zero':
            self.stopped = True
        if self.stopped and result['valid']:
            result.update(reference=[0., 0.], reason='estimated_goal_stop_latched')
        return result
