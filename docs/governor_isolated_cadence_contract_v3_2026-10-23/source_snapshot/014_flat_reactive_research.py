"""Sensor-only flat research primitives; no ROS, simulator or checkpoint input."""
from collections import deque
from math import cos, sin, hypot, sqrt

import numpy as np

FIELDS = (
    'roll', 'pitch', 'gyro_x', 'gyro_y', 'gyro_z',
    'accel_x', 'accel_y', 'accel_z', 'left_wheel_velocity', 'right_wheel_velocity',
    'requested_linear', 'requested_yaw', 'executed_linear', 'executed_yaw',
    'executed_scale', 'interval_vertical_rms', 'interval_vertical_peak', 'imu_coverage',
)
FRAME_SIZE = len(FIELDS)


def sensor_frame(state, requested, feedback, imu, dt):
    """Only explicitly enumerated hardware signals enter the actor history.

    feedback must be measured drive diagnostics, not a guessed action scale.
    Pose, scan, obstacle records and simulator contact data are never inspected.
    """
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError('Positive finite observation interval required')
    duration = float(imu.get('duration', 0.))
    energy = float(imu.get('square_integral', 0.))
    peak = float(imu.get('peak', 0.))
    if not np.isfinite([duration, energy, peak]).all() or min(duration, energy, peak) < 0:
        raise ValueError('Invalid IMU interval statistics')
    if duration > dt + 1e-6 or (duration == 0 and (energy > 0 or peak > 0)):
        raise ValueError('Invalid IMU coverage interval')
    rms = sqrt(energy / duration) if duration else 0.
    values = [state.roll, state.pitch, state.gyro_x/3., state.gyro_y/3., state.gyro_z/3.,
              state.accel_x/10., state.accel_y/10., state.accel_z/10.,
              state.left_wheel_velocity/24., state.right_wheel_velocity/24.,
              requested[0]/.5, requested[1]/2.5,
              feedback['executed_linear_m_s']/.5, feedback['executed_yaw_rad_s']/2.5,
              feedback['filtered_speed_scale'], rms/10., float(imu.get('peak', 0.))/10.,
              duration/dt]
    result = np.asarray(values, dtype=np.float32)
    if result.shape != (FRAME_SIZE,) or not np.isfinite(result).all():
        raise ValueError('Nonfinite or malformed sensor-only observation')
    return np.clip(result, -5., 5.)


class SensorHistory:
    def __init__(self, frames):
        if not isinstance(frames, int) or frames < 1:
            raise ValueError('Positive history frame count required')
        self.frames = frames
        self.values = deque(maxlen=frames)

    @property
    def size(self):
        return self.frames * FRAME_SIZE

    def reset(self, observation):
        self.values.clear()
        self.values.extend(np.array(observation, copy=True) for _ in range(self.frames))
        return np.concatenate(self.values).astype(np.float32)

    def append(self, observation):
        if not self.values:
            return self.reset(observation)
        self.values.append(np.array(observation, copy=True))
        return np.concatenate(self.values).astype(np.float32)


class ReactiveReference:
    """Causal threshold/hysteresis baseline, not a learned policy or flat result."""
    def __init__(self, config, includes_gravity=True):
        self.config = dict(config)
        self.includes_gravity = includes_gravity
        for key, value in self.config.items():
            if not np.isfinite(value) or value <= 0:
                raise ValueError('Invalid reactive parameter: ' + key)
        if not .55 <= self.config['target_scale'] <= 1.:
            raise ValueError('Reactive scale outside research bounds')
        if self.config['hold_seconds'] + 1e-9 < (1-self.config['target_scale'])/.4:
            raise ValueError('Holding duration too short for the declared .4/s ramp')
        self.phase = 'ready'
        self.elapsed = self.remaining = self.filtered = 0.
        self.events = 0

    def update(self, state, feedback, dt):
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError('Invalid reactive interval')
        c = self.config
        vertical = (-sin(state.pitch)*state.accel_x + cos(state.pitch)*sin(state.roll)*state.accel_y
                    + cos(state.pitch)*cos(state.roll)*state.accel_z)
        vertical -= 9.80665 if self.includes_gravity else 0.
        v, w = feedback['executed_linear_m_s'], feedback['executed_yaw_rad_s']
        half = c['wheel_separation_m']/2
        error = max(abs(c['wheel_radius_m']*state.left_wheel_velocity - (v-half*w)),
                    abs(c['wheel_radius_m']*state.right_wheel_velocity - (v+half*w)))
        body_rate = hypot(state.gyro_x, state.gyro_y)
        if not np.isfinite([vertical, error, body_rate, v, w]).all():
            raise ValueError('Invalid reactive hardware signals')
        self.filtered += dt/(c['acceleration_tau_seconds']+dt) * (abs(vertical)-self.filtered)
        self.elapsed += dt
        disturbed = (self.filtered >= c['acceleration_threshold_m_s2'] or
                     body_rate >= c['body_rate_threshold_rad_s'] or error >= c['wheel_error_threshold_m_s'])
        if self.phase == 'holding':
            self.remaining -= dt
            if self.remaining <= 1e-9:
                self.phase = 'recovering'
        elif self.phase == 'recovering' and feedback['filtered_speed_scale'] >= .98:
            self.phase, self.remaining = 'cooldown', c['cooldown_seconds']
        elif self.phase == 'cooldown':
            self.remaining -= dt
            if self.remaining <= 1e-9:
                self.phase = 'ready'
        if (self.phase == 'ready' and disturbed and self.elapsed >= c['startup_seconds']
                and abs(v) >= c['minimum_command_m_s']):
            self.phase, self.remaining = 'holding', c['hold_seconds']
            self.events += 1
        return (c['target_scale'] if self.phase == 'holding' else 1.), dict(
            phase=self.phase, disturbed=bool(disturbed), events=self.events,
            vertical_m_s2=vertical, filtered_vertical_m_s2=self.filtered,
            wheel_error_m_s=error, body_rate_rad_s=body_rate)


def scenario_bank(spec):
    """Disjoint deterministic layouts, with withheld radii in the test split.

    Geometry is rigid circular cylinders only. Additional shapes and turning
    approaches require future feasibility checks and their own contract.
    """
    s = spec['scenarios']
    lo, hi = map(float, s['position_range_m'])
    spacing = float(s['minimum_center_spacing_m'])
    alo, ahi = map(float, s['angle_range_deg'])
    if not 0 < lo < hi < 6.45 or not 0 < spacing or not -30 <= alo <= ahi <= 30:
        raise ValueError('Invalid scenario bounds')
    rows = []
    signatures = set()
    seeds = list(s['seeds'].values())
    if len(set(seeds)) != len(seeds):
        raise ValueError('Train/validation/test RNG seeds must be distinct')
    for stage, counts in s['stage_counts'].items():
        cmin, cmax = map(int, counts)
        if not 1 <= cmin <= cmax <= 6 or hi-lo < (cmax-1)*spacing:
            raise ValueError('Obstacle count/spacing does not fit the course')
        for split in ('train', 'validation', 'test'):
            rng = np.random.default_rng(int(s['seeds'][split]) + (0 if stage == 'A' else 1000))
            radii = s['heldout_radii_m'] if split == 'test' else s['training_radii_m']
            if not radii or any(not 0 < float(r) <= .016 for r in radii):
                raise ValueError('Invalid circular obstacle radius')
            for index in range(int(s['scenarios_per_split'][split])):
                count = int(rng.integers(cmin, cmax+1))
                # Draw sorted slack positions and add mandatory separation.
                positions = np.sort(rng.uniform(lo, hi-(count-1)*spacing, count)) + np.arange(count)*spacing
                obstacles = [dict(x_m=round(float(x), 6), radius_m=float(rng.choice(radii)),
                                  angle_deg=round(float(rng.uniform(alo, ahi)), 6)) for x in positions]
                signature = tuple(tuple(o.values()) for o in obstacles)
                if signature in signatures:
                    raise ValueError('Duplicate scenario layout across splits')
                signatures.add(signature)
                rows.append(dict(id=f'{stage}_{split}_{index:03d}', stage=stage, split=split,
                                 scenario_seed=int(s['seeds'][split])+index+(0 if stage == 'A' else 1000),
                                 obstacles=obstacles))
    return dict(revision=spec['revision'], geometry=s['geometry'], scenarios=rows,
                test_access='Reserved; do not train, tune or diagnose on test cases',
                geometry_height='height = 2*radius, center z=radius, no cable deformation',
                physically_validated=False)


def lookup_scenario(bank, scenario_id):
    matches = [r for r in bank['scenarios'] if r['id'] == scenario_id]
    if len(matches) != 1:
        raise ValueError('Unknown or duplicate scenario: ' + scenario_id)
    return matches[0]


def scenario_cables(bank, scenario_id):
    row = lookup_scenario(bank, scenario_id)
    return [(o['x_m'], o['radius_m'], float(np.deg2rad(o['angle_deg']))) for o in row['obstacles']]
