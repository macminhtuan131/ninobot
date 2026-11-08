"""Bounded stateful encoder compensation proposal, with no ROS or plant calls.

An estimate update is distinct from an output request. A valid old estimate
may survive changing references for one finite lease; authority never does.
The estimate is an encoder/reference proxy, not an identified physical gain.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from nino_control.residual_velocity import FEATURES, SCALES

ID = 'nino_held_encoder_compensation_v1_2026_11_06'
CHANNELS = ('imu', 'wheel', 'baseline', 'final', 'status')


def repo():
    return Path(__file__).resolve().parents[3]


def specification():
    p = json.loads((repo()/'src/nino_rl/config/sim_held_gain_candidate_v1.json').read_text())
    expected = (ID, 103, 5, .1, .15, .04, .05, .002, .002, .5, 1.5, .6, .005)
    keys = ('id', 'observation_size', 'history_frames', 'policy_dt_s', 'maximum_history_gap_s',
        'maximum_source_age_s', 'minimum_reference_m_s', 'maximum_reference_spread_m_s',
        'maximum_each_wheel_spread_m_s', 'minimum_gain_estimate', 'maximum_gain_estimate',
        'maximum_hold_s', 'common_bound_m_s')
    if tuple(p[k] for k in keys) != expected or p['release'] != dict(
            physics_authorized=False, training_authorized=False, hardware_authorized=False):
        raise ValueError('Changed candidate requires a new version; no authority from offline config')
    return p


def fingerprint():
    base = repo()/'src/nino_rl'
    paths = ['nino_rl/held_gain_candidate.py', 'config/sim_held_gain_candidate_v1.json',
        'nino_rl/held_gain_preflight.py', 'scripts/held_gain_preflight.sh',
        'test/test_held_gain_candidate.py', 'test/test_held_gain_preflight.py']
    hashes = {n: hashlib.sha256((base/n).read_bytes()).hexdigest() for n in paths}
    hashes['inherited_feature_schema'] = hashlib.sha256(
        (repo()/'src/nino_control/nino_control/residual_velocity.py').read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class DecisionSupport:
    """Nonprivileged source support for the same decision, never GT/condition.

    Stamps are source stamps except a headerless baseline uses receipt time,
    exactly as the inherited assembler. These clocks are not execution ACKs.
    """
    clock_s: float
    epoch: str
    source_stamps_s: tuple
    history_ready: bool
    permission: bool
    sensors_fresh: bool
    fault: bool
    emergency_stop: bool


def support_from_trace(trace, *, epoch):
    """Read only the old causal packet, not labels, GT, gains or outcomes."""
    clock = trace['input_stamp_s']
    samples = trace['source_samples']
    if set(samples) != set(CHANNELS):
        raise ValueError('Exactly five declared causal sources required')
    stamps = []
    for name in CHANNELS:
        sample = samples[name]
        stamp = sample['source_s']
        if stamp is None:
            if name != 'baseline':
                raise ValueError('Required source timestamp missing: '+name)
            stamp = sample['receipt_s']
        stamps.append(stamp)
    status = samples['status']['values']
    return DecisionSupport(clock, epoch, tuple(stamps), trace['history_ready'],
        status.get('permission'), True, status.get('fault'), status.get('emergency_stop'))


class HeldGainCandidate:
    """One correction candidate. Output is still a request before projection."""
    def __init__(self, geometry):
        self.p = specification()
        self.radii = tuple(float(geometry[k]) for k in ('radius_l', 'radius_r'))
        if not all(math.isfinite(r) and r > 0 for r in self.radii):
            raise ValueError('Positive explicit nominal wheel radii required')
        self.reset(None)

    def reset(self, epoch):
        self.epoch = epoch
        self.last_clock = None
        self.last_stamps = None
        self.healthy_ticks = 0
        self._forget()

    def _forget(self):
        self.gain = self.updated_at = self.nominal_at_update = None

    def _zero(self, reason, *, hard=False):
        self._forget()
        if hard:
            self.healthy_ticks = 0
        return 0., dict(candidate_id=ID, state='zero', reason=reason, update_accepted=False,
            estimate=None, estimate_age_s=None, requested_common_m_s=0.,
            execution_verified=False, physical_gain_identified=False)

    def step(self, observation, support):
        if not isinstance(support, DecisionSupport):
            self._zero('invalid_support', hard=True)
            raise ValueError('Typed causal DecisionSupport required')
        if not isinstance(support.epoch, str) or not support.epoch:
            self._zero('missing_epoch', hard=True)
            raise ValueError('Explicit nonempty reset epoch required')
        if support.epoch != self.epoch:
            self.reset(support.epoch)
        try:
            obs = np.asarray(observation, dtype=np.float64)
        except (TypeError, ValueError):
            self._zero('malformed_observation', hard=True)
            raise ValueError('Finite bounded103D causal observation required') from None
        if obs.shape != (103,) or not np.isfinite(obs).all() or np.max(np.abs(obs)) > 5.:
            self._zero('malformed_observation', hard=True)
            raise ValueError('Finite bounded103D causal observation required')
        if obs[101] not in (0., 1.):
            self._zero('malformed_window', hard=True)
            raise ValueError('Binary common window required')
        stamp = support.clock_s
        stamps = support.source_stamps_s
        if (type(stamp) not in (float, int) or not math.isfinite(stamp)
                or not isinstance(stamps, tuple) or len(stamps) != len(CHANNELS)
                or any(type(s) not in (float, int) or not math.isfinite(s) for s in stamps)):
            return self._zero('unknown_clock_or_source', hard=True)
        if self.last_clock is not None and stamp <= self.last_clock:
            return self._zero('duplicate_or_reversed_clock', hard=True)
        gap = self.last_clock is not None and stamp-self.last_clock > self.p['maximum_history_gap_s']+1e-9
        self.last_clock = stamp
        ages = [stamp-s for s in stamps]
        if any(not -1e-9 <= a <= self.p['maximum_source_age_s']+1e-9 for a in ages):
            return self._zero('stale_future_or_missing_source', hard=True)
        if self.last_stamps is not None and any(s <= old for s, old in zip(stamps, self.last_stamps)):
            return self._zero('duplicate_or_reordered_source', hard=True)
        self.last_stamps = stamps
        if (support.permission is not True or support.sensors_fresh is not True
                or support.fault is not False or support.emergency_stop is not False):
            return self._zero('owner_freshness_fault_or_stop', hard=True)
        if gap:
            return self._zero('history_clock_gap', hard=True)
        frames = obs[:100].reshape(5, 20)
        decode = lambda name: frames[:, FEATURES.index(name)]*SCALES[FEATURES.index(name)]
        if any(np.min(decode(n)) < -1e-9 or np.max(decode(n)) > self.p['maximum_source_age_s']+1e-9
               for n in ('imu_age_s', 'wheel_age_s')):
            return self._zero('stale_history_features', hard=True)
        self.healthy_ticks += 1
        if support.history_ready is not True or self.healthy_ticks < 5:
            return self._zero('refill_trusted_history')
        if not obs[101]:
            return self._zero('shared_window_closed')
        nominal = float(decode('baseline_v_m_s')[-1])
        if nominal < self.p['minimum_reference_m_s']:
            return self._zero('zero_reverse_or_low_baseline')
        if (self.nominal_at_update is not None and
                abs(nominal-self.nominal_at_update) > self.p['maximum_reference_spread_m_s']+1e-9):
            return self._zero('nominal_plan_changed')
        references = decode('last_final_v_m_s')
        wheels = np.stack([decode(n)*r for n, r in zip(('wheel_l_rad_s', 'wheel_r_rad_s'), self.radii)])
        reason = 'steady_reference_and_encoder'
        if np.min(references) < self.p['minimum_reference_m_s']:
            reason = 'reference_small'
        elif np.ptp(references) > self.p['maximum_reference_spread_m_s']+1e-9:
            reason = 'reference_changing'
        elif np.max(np.ptp(wheels, axis=1)) > self.p['maximum_each_wheel_spread_m_s']+1e-9:
            reason = 'encoder_changing'
        updated = False
        if reason == 'steady_reference_and_encoder':
            gain = float(np.median(np.mean(wheels, axis=0)/references))
            if self.p['minimum_gain_estimate'] <= gain <= self.p['maximum_gain_estimate']:
                self.gain, self.updated_at, self.nominal_at_update = gain, stamp, nominal
                updated = True
            else:
                reason = 'proxy_gain_outside_declared_range'
        if self.gain is None:
            return self._zero('no_estimate:'+reason)
        age = stamp-self.updated_at
        if age > self.p['maximum_hold_s']+1e-9:
            return self._zero('estimate_lease_expired:'+reason)
        request = float(np.clip((nominal/self.gain-nominal)/self.p['common_bound_m_s'], -1., 1.))
        return request, dict(candidate_id=ID, state='updated' if updated else 'held', reason=reason,
            update_accepted=updated, estimate=self.gain, estimate_age_s=age,
            requested_common_m_s=request*self.p['common_bound_m_s'], execution_verified=False,
            physical_gain_identified=False)
