"""Causal speed governor. No ROS, pose, terrain coordinates or contact oracle.

Parameters are experimental starting values, not calibrated hardware limits.
Wheel tracking error and wheel stall are proxies, never absolute body slip.
"""
from dataclasses import dataclass, asdict
from math import cos, sin, hypot, isfinite, sqrt


@dataclass(frozen=True)
class GovernorSettings:
    profile: str = "reactive"  # full/moderate/deep/pulse: H2 interventions
    target_scale: float = .70
    scale_rate_per_second: float = .4
    vertical_trigger_m_s2: float = 1.5
    # Opt-in ablation for a noisy vertical channel. Vertical remains in quiet/
    # release detection; only its authority to initiate an event is removed.
    vertical_only_trigger_enabled: bool = True
    body_rate_trigger_rad_s: float = .35
    wheel_error_trigger_m_s: float = .06
    wheel_error_acceleration_allowance_s: float = .10
    release_ratio: float = .6
    filter_seconds: float = .05
    confirmation_seconds: float = .04
    quiet_seconds: float = .30
    startup_seconds: float = .80
    minimum_hold_seconds: float = .80
    maximum_hold_seconds: float = 2.5
    pulse_seconds: float = .80
    minimum_trigger_speed_m_s: float = .10
    wheel_radius_m: float = .0625
    wheel_stall_speed_m_s: float = .02
    wheel_stall_seconds: float = 1.2
    stall_recovery_enabled: bool = False
    stall_recovery_scale: float = .85
    stall_recovery_seconds: float = .6
    max_update_seconds: float = .25

    def __post_init__(self):
        if self.profile not in ("reactive", "full", "moderate", "deep", "pulse"):
            raise ValueError("Unknown governor profile")
        for key,value in asdict(self).items():
            if isinstance(value,bool) or isinstance(value,str):
                continue
            if not isfinite(value) or value < 0:
                raise ValueError("Nonfinite/negative governor setting: "+key)
        for key in ("scale_rate_per_second", "vertical_trigger_m_s2", "body_rate_trigger_rad_s",
                    "wheel_error_trigger_m_s", "filter_seconds", "quiet_seconds", "wheel_radius_m",
                    "maximum_hold_seconds", "wheel_stall_seconds", "max_update_seconds"):
            if getattr(self,key) <= 0:
                raise ValueError("Positive governor setting required: "+key)
        if not .55 <= self.target_scale <= 1 or not 0 < self.release_ratio < 1:
            raise ValueError("Invalid governor scale/hysteresis bounds")
        if not .55 <= self.stall_recovery_scale <= 1:
            raise ValueError("Invalid minimum-forward recovery scale")
        if self.maximum_hold_seconds < self.minimum_hold_seconds:
            raise ValueError("Maximum hold must exceed minimum hold")
        if self.maximum_hold_seconds < (1-self.target)/self.scale_rate_per_second:
            raise ValueError("Maximum hold cannot reach target with declared ramp")
        if self.profile == "pulse" and self.pulse_seconds < (1-self.target)/self.scale_rate_per_second:
            raise ValueError("Pulse too short to reach target with declared ramp")

    @property
    def target(self):
        return {"moderate":.85,"deep":.55}.get(self.profile,self.target_scale)


@dataclass(frozen=True)
class GovernorFrame:
    vertical_m_s2: float
    body_rate_rad_s: float
    left_velocity_rad_s: float
    right_velocity_rad_s: float
    left_target_rad_s: float
    right_target_rad_s: float
    executed_linear_m_s: float
    # Interval RMS/peak can preserve transients between slow control updates.
    vertical_rms_m_s2: float = 0.
    vertical_peak_m_s2: float = 0.

    def valid(self):
        return all(isfinite(value) for value in asdict(self).values()) and min(
            self.body_rate_rad_s,self.vertical_rms_m_s2,self.vertical_peak_m_s2) >= 0


def vertical_acceleration(acceleration, roll, pitch, includes_gravity=True):
    """IMU axes must first be aligned with robot axes; rotate to gravity frame."""
    if not all(isfinite(v) for v in (*acceleration,roll,pitch)):
        raise ValueError("Invalid IMU")
    ax,ay,az = acceleration
    return -sin(pitch)*ax+cos(pitch)*sin(roll)*ay+cos(pitch)*cos(roll)*az-(9.80665 if includes_gravity else 0.)


def quaternion_rpy(q):
    x,y,z,w = q
    norm = sqrt(sum(v*v for v in q))
    if not all(isfinite(v) for v in q) or norm < .5 or norm > 1.5:
        raise ValueError("Invalid IMU orientation quaternion")
    from math import atan2, asin
    x,y,z,w = (v/norm for v in q)
    return atan2(2*(w*x+y*z),1-2*(x*x+y*y)),asin(max(-1.,min(1.,2*(w*y-z*x)))),atan2(2*(w*z+x*y),1-2*(y*y+z*z))


class ReactiveGovernor:
    def __init__(self,settings):
        self.settings = settings if isinstance(settings,GovernorSettings) else GovernorSettings(**settings)
        self.reset()

    def reset(self):
        self.phase = "CRUISE"
        self.scale = 1.
        self.elapsed = self.hold_elapsed = self.quiet = self.confirmed = self.stall_elapsed = 0.
        self.stall_recovery_elapsed = 0.
        self.filtered_vertical = 0.
        self.previous_targets = None
        self.armed = True
        self.events = 0
        self.fault = ""

    def fail(self,reason):
        self.phase,self.scale,self.fault = "FAILSAFE",0.,reason
        return self._decision(reason=reason)

    def _decision(self,**extra):
        return dict(phase=self.phase,scale=self.scale,events=self.events,armed=self.armed,
                    hold_seconds=self.hold_elapsed,quiet_seconds=self.quiet,fault=self.fault,**extra)

    def update(self,frame,dt,requested_linear,requested_yaw=0.,fresh=True):
        c = self.settings
        if self.phase == "FAILSAFE":
            return self._decision(reason=self.fault)
        if not fresh:
            return self.fail("stale_feedback")
        if (not frame.valid() or not all(isfinite(v) for v in (dt,requested_linear,requested_yaw))
                or not 0 < dt <= c.max_update_seconds):
            return self.fail("invalid_or_discontinuous_input")
        self.elapsed += dt
        # A stop is always immediate; reverse/in-place turns do not trigger a
        # forward-crossing governor. No minimum speed may override zero input.
        if requested_linear <= 0:
            self.phase,self.scale = "CRUISE",1.
            self.hold_elapsed=self.stall_elapsed=self.stall_recovery_elapsed=0.
            self.confirmed=0.
            return self._decision(reason="nonforward_reference")
        peak = max(abs(frame.vertical_m_s2),frame.vertical_rms_m_s2,frame.vertical_peak_m_s2)
        self.filtered_vertical += dt/(c.filter_seconds+dt)*(peak-self.filtered_vertical)
        targets = (frame.left_target_rad_s,frame.right_target_rad_s)
        target_accel = (max(abs(a-b) for a,b in zip(targets,self.previous_targets))*c.wheel_radius_m/dt
                        if self.previous_targets is not None else 0.)
        self.previous_targets = targets
        wheel_error = max(abs(frame.left_velocity_rad_s-targets[0]),
                          abs(frame.right_velocity_rad_s-targets[1]))*c.wheel_radius_m
        error_threshold = c.wheel_error_trigger_m_s+c.wheel_error_acceleration_allowance_s*target_accel
        motion_ratio = max(frame.body_rate_rad_s/c.body_rate_trigger_rad_s,wheel_error/error_threshold)
        ratio = max(self.filtered_vertical/c.vertical_trigger_m_s2,motion_ratio)
        disturbed = ratio >= 1. and (c.vertical_only_trigger_enabled or motion_ratio >= 1.)
        quiet = ratio <= c.release_ratio
        self.quiet = self.quiet+dt if quiet else 0.
        self.confirmed = self.confirmed+dt if disturbed else 0.
        if self.quiet >= c.quiet_seconds:
            self.armed = True  # Independent of reaching exactly 0.98 cruise.
        moving = abs(frame.executed_linear_m_s) >= c.minimum_trigger_speed_m_s
        # A wheel stall is detectable. Body stall with spinning wheels is not
        # observable here and must remain an independent evaluation failure.
        stopped_wheels = max(abs(frame.left_velocity_rad_s),abs(frame.right_velocity_rad_s))*c.wheel_radius_m < c.wheel_stall_speed_m_s
        self.stall_elapsed = self.stall_elapsed+dt if moving and stopped_wheels else 0.
        if self.stall_elapsed >= c.wheel_stall_seconds and self.phase != "STALL":
            if not c.stall_recovery_enabled:
                return self.fail("persistent_wheel_stall")
            self.phase = "STALL"
            self.stall_recovery_elapsed = 0.
        if self.phase == "STALL":
            self.stall_recovery_elapsed += dt
            if not stopped_wheels:
                self.phase = "RECOVER"
                self.stall_elapsed=0.
            elif self.stall_recovery_elapsed >= c.stall_recovery_seconds:
                return self.fail("wheel_stall_recovery_exhausted")
        if (c.profile != "full" and self.phase != "STALL" and self.armed and moving
                and self.elapsed >= c.startup_seconds and self.confirmed >= c.confirmation_seconds):
            self.phase = "HOLD"
            self.hold_elapsed = 0.
            self.armed = False
            self.events += 1
        if self.phase == "HOLD":
            self.hold_elapsed += dt
            reached = self.scale <= c.target+1e-9
            release = (self.hold_elapsed >= c.pulse_seconds and reached if c.profile == "pulse" else
                       self.hold_elapsed >= c.minimum_hold_seconds and reached and self.quiet >= c.quiet_seconds)
            if release or self.hold_elapsed >= c.maximum_hold_seconds:
                self.phase = "RECOVER"
        target = c.target if self.phase == "HOLD" else c.stall_recovery_scale if self.phase == "STALL" else 1.
        delta = c.scale_rate_per_second*dt
        self.scale += max(-delta,min(delta,target-self.scale))
        self.scale = max(.55,min(1.,self.scale))
        if self.phase == "RECOVER" and self.scale >= 1.-1e-9:
            self.phase = "CRUISE"
        return self._decision(disturbed=disturbed,trigger_ratio=ratio,
                              filtered_vertical_m_s2=self.filtered_vertical,
                              wheel_error_m_s=wheel_error,wheel_error_threshold_m_s=error_threshold,
                              target_scale=target,wheel_stall_seconds=self.stall_elapsed)
