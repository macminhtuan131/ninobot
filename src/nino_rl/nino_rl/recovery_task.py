"""Physical clearance and sustained recovery labels. Never actor features."""
from dataclasses import asdict, dataclass
import math
import numpy as np

from .recovery_contract import CONTRACT_ID
from .unknown_step_runtime import TraversalScore, TraversalReward, UnknownTaskData


@dataclass(frozen=True)
class RecoveryBands:
    cross_track_m: float
    heading_rad: float
    yaw_rate_rad_s: float
    tilt_rad: float
    speed_error_m_s: float
    exit_multiplier: float
    hold_s: float
    maximum_recovery_s: float

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError('Positive finite recovery bands required')
        if self.exit_multiplier <= 1 or self.maximum_recovery_s <= self.hold_s:
            raise ValueError('Recovery needs hysteresis and a bounded hold window')


class RecoveryScore(TraversalScore):
    def __init__(self, settings, obstacles, bands, start_budget, declared_start_pose=(0.,0.,0.)):
        if settings.obstacle_near_m is not None:
            raise ValueError('Recovery engine owns obstacle lifecycle, not historical one-obstacle flag')
        self.obstacles = tuple(obstacles)
        self.bands, self.start_budget = bands, start_budget
        self.declared_start_pose = tuple(declared_start_pose)
        if len(self.declared_start_pose) != 3 or not all(math.isfinite(v) for v in self.declared_start_pose):
            raise ValueError('Finite declared estimator initial pose required')
        names = [r['id'] for r in self.obstacles]
        if len(names) != len(set(names)):
            raise ValueError('Unique obstacle identities required')
        for r in self.obstacles:
            if not 0 < r['near_m'] < r['far_m'] < math.dist(*settings.route_m):
                raise ValueError('Obstacle support must lie inside fixed route')
        super().__init__(settings)

    def reset(self, sample):
        geometry = super().reset(sample)
        x, y, yaw = self.declared_start_pose
        dx, dy = x-self.x0, y-self.y0
        geometry['initial_alignment'] = self.start_budget.check(
            geometry, dx*self.tangent[0]+dy*self.tangent[1],
            -dx*self.tangent[1]+dy*self.tangent[0], yaw-self.heading,
            self.length+math.hypot(dx,dy))
        if any(geometry['front_support_m'] >= r['near_m']-self.c.clearance_m for r in self.obstacles):
            raise UnknownTaskData('Whole robot must start before every obstacle')
        self.phases = [dict(id=r['id'], phase='APPROACH', cleared_at_s=None,
                            cleared_progress_m=None, stable_since_s=None,
                            recovered_at_s=None, recovery_time_s=None, recovery_distance_m=None,
                            recovery_started_at_s=None, bonus_paid=False)
                       for r in self.obstacles]
        self.post_rows = []
        self.last_events = dict(clearance=0, recovery=0)
        return geometry

    def update(self, sample):
        previous = self.last
        result = super().update(sample)
        dt = sample.stamp_s - previous.stamp_s
        dx = sample.pose_m_rad[0] - previous.pose_m_rad[0]
        dy = sample.pose_m_rad[1] - previous.pose_m_rad[1]
        forward_fd = (dx*self.tangent[0]+dy*self.tangent[1])/dt
        lateral_fd = (-dx*self.tangent[1]+dy*self.tangent[0])/dt
        now = sample.stamp_s
        bands = self.bands
        normalized = (abs(result['cross_track_m']) / bands.cross_track_m,
                      abs(result['heading_error_rad']) / bands.heading_rad,
                      abs(sample.body_yaw_rad_s) / bands.yaw_rate_rad_s,
                      max(map(abs, sample.pose_m_rad[3:5])) / bands.tilt_rad,
                      abs(sample.body_speed_norm_m_s - abs(sum(sample.accepted_reference_m_s)/2.))
                      / bands.speed_error_m_s,
                      abs(forward_fd - sum(sample.accepted_reference_m_s)/2.*math.cos(result['heading_error_rad']))
                      / bands.speed_error_m_s,
                      abs(lateral_fd) / bands.speed_error_m_s)
        events = dict(clearance=0, recovery=0)
        recovery_timeout = False
        for obstacle, state in zip(self.obstacles, self.phases):
            if result['terminated'] and not result['task_success']:
                continue
            still_clear = result['rear_support_m'] > obstacle['far_m']+self.c.clearance_m
            if state['phase'] == 'RECOVERED' and (not still_clear or max(normalized) > bands.exit_multiplier):
                state.update(phase='RECOVERY', stable_since_s=None, recovery_started_at_s=now)
            if state['phase'] == 'APPROACH' and result['front_support_m'] >= obstacle['near_m']-self.c.clearance_m:
                state['phase'] = 'CROSSING'
            if state['phase'] == 'CROSSING' and result['rear_support_m'] > obstacle['far_m']+self.c.clearance_m:
                state.update(phase='RECOVERY', cleared_at_s=now,
                             cleared_progress_m=result['progress_m'], recovery_started_at_s=now)
                events['clearance'] += 1
            if state['phase'] == 'RECOVERY':
                if not still_clear or max(normalized) > bands.exit_multiplier:
                    state['stable_since_s'] = None
                elif state['stable_since_s'] is None and max(normalized) <= 1.:
                    state['stable_since_s'] = now
                if (state['stable_since_s'] is not None
                        and now-state['stable_since_s'] >= bands.hold_s-1e-8):
                    state.update(phase='RECOVERED', recovered_at_s=now,
                                 recovery_time_s=now-state['recovery_started_at_s'],
                                 recovery_distance_m=result['progress_m']-state['cleared_progress_m'])
                    if not state['bonus_paid']:
                        events['recovery'] += 1
                        state['bonus_paid'] = True
                elif now-state['recovery_started_at_s'] >= bands.maximum_recovery_s-1e-8:
                    recovery_timeout = True
        all_recovered = all(s['phase'] == 'RECOVERED' for s in self.phases)
        all_clear_now = all(result['rear_support_m'] > r['far_m']+self.c.clearance_m for r in self.obstacles)
        if self.obstacles and any(s['cleared_at_s'] is not None for s in self.phases):
            self.post_rows.append((result['cross_track_m'], result['heading_error_rad'], dt))
        if result['task_success'] and (not all_recovered or not all_clear_now):
            result.update(task_success=False, termination_reason='incomplete_recovery')
        elif recovery_timeout and not result['terminated']:
            result.update(task_success=False, terminated=True, termination_reason='recovery_timeout')
        self.done = result['terminated']
        self.last_events = events
        post = self.post_rows
        post_time = sum(row[2] for row in post)
        result.update(contract_id=CONTRACT_ID, recovery_states=[dict(s) for s in self.phases],
                      stability_cost=(sample.body_yaw_rad_s/bands.yaw_rate_rad_s)**2
                          + sum((v/bands.tilt_rad)**2 for v in sample.pose_m_rad[3:5]),
                      clearance_events=events['clearance'], recovery_events=events['recovery'],
                      all_obstacles_recovered=all_recovered, whole_robot_clear=all_clear_now,
                      crossing_count=sum(s['cleared_at_s'] is not None for s in self.phases),
                      recovery_count=sum(s['phase'] == 'RECOVERED' for s in self.phases),
                      crossing_evidence='conservative_route_geometry_not_loaded_contact',
                      post_clearance_duration_s=post_time,
                      post_cross_track_rmse_m=(math.sqrt(sum(y*y*t for y, _, t in post)/post_time) if post else None),
                      post_heading_rmse_rad=(math.sqrt(sum(h*h*t for _, h, t in post)/post_time) if post else None),
                      post_cross_track_p95_m=float(np.percentile([abs(y) for y, _, _ in post], 95)) if post else None,
                      post_maximum_cross_track_m=max((abs(y) for y, _, _ in post), default=None),
                      truth_forward_velocity_fd_m_s=forward_fd,
                      truth_lateral_velocity_fd_m_s=lateral_fd,
                      velocity_diagnostic_method='finite_difference_source_poses_not_independent_velocity_sensor')
        return result


class RecoveryReward(TraversalReward):
    def __init__(self, settings, initial_goal_distance_m, clearance_bonus, recovery_bonus, stability_weight):
        super().__init__(settings, initial_goal_distance_m)
        values = (clearance_bonus, recovery_bonus, stability_weight)
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('Nonnegative explicit proposed reward weights required')
        self.clearance_bonus, self.recovery_bonus, self.stability_weight = values

    def update(self, outcome, accepted_common_normalized):
        dt = outcome['elapsed_s'] - self.previous_time
        _, terms = super().update(outcome, accepted_common_normalized)
        eligible = not outcome['terminated'] or outcome['task_success']
        terms.update(clearance=self.clearance_bonus*outcome['clearance_events'] if eligible else 0.,
                     recovery=self.recovery_bonus*outcome['recovery_events'] if eligible else 0.,
                     stability=-self.stability_weight*outcome['stability_cost']*dt)
        return sum(terms.values()), terms
