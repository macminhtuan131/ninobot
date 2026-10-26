"""Causal hardware summaries and bounded event state for the new rough contract."""
from math import sqrt
import numpy as np
from nino_rl.reactive_speed import ReactiveSpeed

EXTRA_SIZE = 16


class BoundedCue(ReactiveSpeed):
    """Retain cue thresholds; cap recovery so slow cruise cannot block rearming."""
    def update(self, state, command, executed_scale, dt):
        # The original probe ends recovery at .98. For a free speed policy it
        # must also expire after a bounded time; never prolong that timeout.
        if self.phase == 'recovering':
            self.recovery_elapsed += dt
            if self.recovery_elapsed >= self.config['maximum_recovery_seconds']-1e-9:
                self.phase = 'cooldown'
                self.remaining = self.config['cooldown_seconds']+dt
        old = self.phase
        target, trace = super().update(state, command, executed_scale, dt)
        if self.phase == 'recovering' and old != 'recovering':
            self.recovery_elapsed = 0.
        trace['cue_remaining_s'] = (max(0., self.config['maximum_recovery_seconds']-
                                      getattr(self, 'recovery_elapsed', 0.))
                                    if self.phase == 'recovering' else max(0., self.remaining))
        return target, trace


def summaries(imu):
    covered = float(imu.get('duration', 0.))
    return (sqrt(max(0., float(imu.get('square_integral', 0.)))/covered) if covered>0 else 0.,
            float(imu.get('peak', 0.)), covered)


def extra_observation(imu, cue, scale, published, executed, dt):
    rms, peak, covered = summaries(imu)
    phase = cue.get('cue_phase', 'ready')
    result = np.array([rms/10., peak/10., cue.get('cue_filtered_acceleration_m_s2', 0.)/10.,
        cue.get('cue_body_rate_rad_s', 0.)/3., cue.get('cue_wheel_error_m_s', 0.)/.2,
        cue.get('cue_disturbed', 0), phase=='holding', phase=='recovering', phase=='cooldown',
        cue.get('cue_remaining_s', 0.)/1.2, scale,
        published[0]/.5, published[1]/2.5, executed[0]/.5, executed[1]/2.5,
        min(1., covered/dt)], dtype=np.float32)
    if result.shape != (EXTRA_SIZE,) or not np.isfinite(result).all():
        raise ValueError('Invalid causal hardware summary')
    return np.clip(result, -5., 5.)


class Capture:
    """Store exact actor tensors and associated executed-action/reward records."""
    def __init__(self):
        import os
        from pathlib import Path
        self.directory = Path(os.environ['NINO_REACTIVE_RECORD_DIR']) if os.environ.get('NINO_REACTIVE_RECORD_DIR') else None
        self.observations = []
        self.records = []
        self.chunk = 0

    def add(self, observation, record):
        if self.directory is None:
            return
        self.observations.append(np.array(observation, dtype=np.float32, copy=True))
        self.records.append(record)
        if len(self.records) >= 512:
            self.flush()

    def flush(self):
        if not self.records:
            return
        import json
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory/f'chunk_{self.chunk:05d}.npz'
        if destination.exists():
            raise ValueError('Refusing to overwrite prior observation capture')
        np.savez_compressed(destination, observations=np.stack(self.observations),
            records=np.array([json.dumps(r) for r in self.records]))
        self.chunk += 1
        self.observations.clear()
        self.records.clear()
