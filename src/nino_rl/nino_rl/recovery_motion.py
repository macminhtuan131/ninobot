from dataclasses import asdict, dataclass
import math

from .unknown_step_runtime import UnknownTaskData


@dataclass(frozen=True)
class MotionTarget:
    forward_m_s: float
    yaw_rad_s: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in asdict(self).values()):
            raise UnknownTaskData('Finite independent motion target required')


@dataclass(frozen=True)
class MotionQuality:
    maximum_speed_rmse_m_s: float
    maximum_cross_track_rmse_m: float
    maximum_heading_rmse_rad: float

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError('Explicit positive proposed motion-quality bounds required')


class MotionEvaluator:
    """Pose differences are interval labels, never deployable actor features."""
    def __init__(self, tangent, corners, ramp=None):
        if ramp is not None and (abs(tangent[1]) > 1e-9 or tangent[0] < 1.-1e-9):
            raise ValueError('Macro-ramp evaluation currently requires the eastbound route')
        self.tangent, self.ramp = tangent, ramp
        self.support_min = min(p[0] for p in corners)
        self.support_max = max(p[0] for p in corners)
        self.reset()

    def reset(self):
        self.duration = self.speed_sq = 0.
        self.moving_duration = self.moving_speed_sq = 0.

    def update(self, previous, sample, target):
        if not isinstance(target, MotionTarget):
            raise UnknownTaskData('Typed independent motion target required')
        dt = sample.stamp_s-previous.stamp_s
        if dt <= 0:
            raise UnknownTaskData('Increasing physical source clock required')
        delta = [(a-b)/dt for a,b in zip(sample.pose_m_rad[:3], previous.pose_m_rad[:3])]
        tx, ty = self.tangent
        planar = delta[0]*tx+delta[1]*ty
        lateral = -delta[0]*ty+delta[1]*tx
        midpoint = (sample.pose_m_rad[0]+previous.pose_m_rad[0])/2
        gradient = float(self.ramp.slope(midpoint)) if self.ramp is not None else 0.
        surface = (planar+gradient*delta[2])/math.sqrt(1+gradient**2)
        error = surface-target.forward_m_s
        self.duration += dt
        self.speed_sq += error**2*dt
        if abs(target.forward_m_s) > 1e-6:
            self.moving_duration += dt
            self.moving_speed_sq += error**2*dt

        roll, pitch, yaw = sample.pose_m_rad[3:]
        chord = 0.
        if self.ramp is not None:
            x = sample.pose_m_rad[0]
            span = self.support_max-self.support_min
            chord = float((self.ramp.height(x+self.support_max)-self.ramp.height(x+self.support_min))/span)
        up = (math.cos(yaw)*math.sin(pitch)*math.cos(roll)+math.sin(yaw)*math.sin(roll),
              math.sin(yaw)*math.sin(pitch)*math.cos(roll)-math.cos(yaw)*math.sin(roll),
              math.cos(pitch)*math.cos(roll))
        alignment = (-chord*up[0]+up[2])/math.sqrt(1+chord**2)
        tilt = math.acos(max(-1., min(1., alignment)))
        return dict(motion_target=asdict(target),
                    motion_target_source='independent_zero_residual_shaper_on_current_causal_follower',
                    motion_phase='motion' if abs(target.forward_m_s)>1e-6 else 'quiet_or_stop',
                    target_speed_error_m_s=error,
                    target_speed_rmse_m_s=math.sqrt(self.speed_sq/self.duration),
                    moving_target_speed_rmse_m_s=(math.sqrt(self.moving_speed_sq/self.moving_duration)
                                                  if self.moving_duration else None),
                    moving_measured_duration_s=self.moving_duration,
                    truth_surface_velocity_fd_m_s=surface,
                    truth_forward_velocity_fd_m_s=planar,
                    truth_lateral_velocity_fd_m_s=lateral,
                    road_relative_tilt_rad=tilt,
                    macro_support_chord_gradient=chord,
                    velocity_diagnostic_method='source_pose_difference_projected_on_macro_surface_tangent',
                    support_diagnostic_method='macro_chord_over_conservative_envelope_not_loaded_contact')
