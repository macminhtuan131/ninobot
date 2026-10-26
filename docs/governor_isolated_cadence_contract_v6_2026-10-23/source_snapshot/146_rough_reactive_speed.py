"""Causal sensor-only slowdown probe; no terrain, truth or route-position inputs."""
from math import cos, sin, hypot, isfinite

DEFAULTS = dict(target_scale=.70, hold_seconds=.60, cooldown_seconds=1.20,
    startup_seconds=.80, acceleration_tau_seconds=.15,
    acceleration_threshold_m_s2=1.50, body_rate_threshold_rad_s=.35,
    wheel_error_threshold_m_s=.06, minimum_command_m_s=.15,
    wheel_radius_m=.0625, wheel_separation_m=.34273666)


def hardware_cue(state, command, includes_gravity=True):
    """Only real IMU, encoder and previously published command fields are read."""
    vertical=(-sin(state.pitch)*state.accel_x+cos(state.pitch)*sin(state.roll)*state.accel_y
        +cos(state.pitch)*cos(state.roll)*state.accel_z)-(9.80665 if includes_gravity else 0.)
    v,w=command;half=DEFAULTS['wheel_separation_m']/2
    error=max(abs(DEFAULTS['wheel_radius_m']*state.left_wheel_velocity-(v-half*w)),
        abs(DEFAULTS['wheel_radius_m']*state.right_wheel_velocity-(v+half*w)))
    values=(vertical,hypot(state.gyro_x,state.gyro_y),error,v)
    if not all(isfinite(x) for x in values):raise ValueError('Nonfinite reactive hardware input')
    return values


class ReactiveSpeed:
    """A bounded hold followed by mandatory ramp recovery and a refractory period."""
    def __init__(self, config=None, includes_gravity=True):
        self.config={**DEFAULTS,**(config or {})};self.includes_gravity=includes_gravity
        self.elapsed=0.;self.filtered_acceleration=0.;self.phase='ready'
        self.remaining=0.;self.events=0

    def update(self,state,command,executed_scale,dt):
        if not isfinite(dt) or dt<=0:raise ValueError('Invalid cue interval')
        c=self.config;vertical,rate,error,linear=hardware_cue(state,command,self.includes_gravity)
        alpha=dt/(c['acceleration_tau_seconds']+dt)
        self.filtered_acceleration+=alpha*(abs(vertical)-self.filtered_acceleration)
        disturbed=(self.filtered_acceleration>=c['acceleration_threshold_m_s2']
            or rate>=c['body_rate_threshold_rad_s'] or error>=c['wheel_error_threshold_m_s'])
        self.elapsed+=dt;triggered=False
        if self.phase=='holding':
            self.remaining-=dt
            if self.remaining<=1e-9:self.phase='recovering'
        elif self.phase=='recovering':
            if executed_scale>=.98:
                self.phase='cooldown';self.remaining=c['cooldown_seconds']
        elif self.phase=='cooldown':
            self.remaining-=dt
            if self.remaining<=1e-9:self.phase='ready'
        if (self.phase=='ready' and disturbed and self.elapsed>=c['startup_seconds']
                and abs(linear)>=c['minimum_command_m_s']):
            triggered=True;self.events+=1;self.phase='holding';self.remaining=c['hold_seconds']
        target=c['target_scale'] if self.phase=='holding' else 1.
        return target,dict(cue_vertical_m_s2=vertical,cue_filtered_acceleration_m_s2=self.filtered_acceleration,
            cue_body_rate_rad_s=rate,cue_wheel_error_m_s=error,cue_disturbed=int(disturbed),
            cue_triggered=int(triggered),cue_phase=self.phase,cue_events=self.events,cue_target_scale=target)
