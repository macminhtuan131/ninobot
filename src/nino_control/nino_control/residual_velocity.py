"""Offline/reference contract for bounded wheel-velocity residual research.

No ROS publisher, motor PI, training loop or automatic hardware authority.
Receipt ages and nominal encoder kinematics are not actuator telemetry/GT.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math

CONTRACT_ID = 'nino_residual_velocity_v1'
IMPLEMENTATION_REVISION = 2  # Accepted policy contribution excludes baseline shaping.
FEATURES = (
    'baseline_v_m_s', 'baseline_yaw_rad_s', 'wheel_l_rad_s', 'wheel_r_rad_s',
    'gyro_x_rad_s', 'gyro_y_rad_s', 'gyro_z_rad_s',
    'accel_x_m_s2', 'accel_y_m_s2', 'accel_z_m_s2',
    'last_final_v_m_s', 'last_final_yaw_rad_s',
    'previous_proposal_common', 'previous_proposal_diff',
    'previous_accepted_common', 'previous_accepted_diff',
    'imu_age_s', 'wheel_age_s', 'nominal_yaw_consistency_rad_s', 'nominal_wheel_asymmetry',
)
# Numerical normalization proposals, NOT safety limits or measured sensor ranges.
SCALES = (.4, 1., 10., 10., 2., 2., 2., 19.62, 19.62, 19.62,
          .4, 1., 1., 1., 1., 1., .2, .2, 1., 2.)


def actor_contract(config):
    """Shared exact ABI for environment/export/portable ROS inference."""
    k=config['actor']['history_frames'];dt=float(config['control_interval_s'])
    if type(k) is not int or k<1 or not math.isfinite(dt) or not 0<dt<=config['actor']['max_history_gap_s']:
        raise ValueError('Invalid history/control clock')
    if config['actor'].get('privileged_inputs'):raise ValueError('Privileged actor inputs prohibited')
    geometry=config['nominal_geometry']
    if any(not math.isfinite(float(geometry[key])) or geometry[key]<=0 for key in ('radius_l','radius_r','separation')):
        raise ValueError('Explicit positive nominal geometry required')
    names=config.get('wheel_names',['left_wheel','right_wheel'])
    if len(names)!=2 or len(set(names))!=2 or not all(isinstance(n,str) and n for n in names):
        raise ValueError('Explicit distinct left/right wheel names required')
    abi=dict(id=CONTRACT_ID,implementation_revision=IMPLEMENTATION_REVISION,features=list(FEATURES),
        normalization_scales=list(SCALES),history_frames=k,observation_size=len(FEATURES)*k,
        frame_order='oldest_to_newest',action=['normalized_common','normalized_diff'],
        action_physical_units='wheel_linear_m_s',low_level='velocity_reference',
        nominal_geometry=config['nominal_geometry'],reference_limits=config['reference_limits'],
        control_interval_s=dt,max_history_gap_s=float(config['actor']['max_history_gap_s']),
        imu_yaw_rad=float(config.get('imu_yaw_rad',0.)),
        wheel_names=list(config.get('wheel_names',['left_wheel','right_wheel'])),
        accepted_history='accepted_total_minus_projected_baseline_from_same_previous_reference')
    ReferenceLimits(**config['reference_limits'])
    if config['nominal_geometry']['separation']!=config['reference_limits']['separation_m']:
        raise ValueError('Geometry/reference wheel separation mismatch')
    digest=hashlib.sha256(json.dumps(abi,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(abi,abi_sha256=digest)


def pair(values):
    result = tuple(float(v) for v in values)
    if len(result) != 2 or not all(math.isfinite(v) for v in result):
        raise ValueError('Expected two finite values')
    return result


def body_to_wheels(v, yaw, separation):
    if not math.isfinite(separation) or separation <= 0:
        raise ValueError('Full wheel separation must be positive')
    v, yaw = pair((v, yaw))
    return v - separation*yaw/2, v + separation*yaw/2


def wheels_to_body(left, right, separation):
    left, right = pair((left, right))
    if not math.isfinite(separation) or separation <= 0:
        raise ValueError('Full wheel separation must be positive')
    return (left+right)/2, (right-left)/separation


def feature_frame(sample, radius_l, radius_r, separation):
    """All raw fields are required. No GT/pose/terrain or fabricated target.

    IMU must already be expressed in the declared body frame. Acceleration
    retains gravity; downstream evaluation must handle orientation separately.
    """
    required = FEATURES[:18]
    values = [float(sample[name]) for name in required]
    if not all(math.isfinite(v) for v in values) or any(v < 0 for v in values[16:18]):
        raise ValueError('Invalid/stale-clock feature payload')
    if not all(math.isfinite(v) and v > 0 for v in (radius_l, radius_r, separation)):
        raise ValueError('Nominal geometry must be finite and positive')
    left, right = radius_l*values[2], radius_r*values[3]
    yaw = (right-left)/separation
    asym = (right-left)/max((abs(left)+abs(right))/2, .01)
    values += [yaw-values[6], asym]
    return tuple(max(-5., min(5., v/s)) for v, s in zip(values, SCALES))


class FeatureHistory:
    """Oldest→newest, actual timestamps; duplicates/gaps cannot earn authority."""
    def __init__(self, frames=5, max_gap_s=.15):
        if type(frames) is not int or frames < 1 or not math.isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError('Invalid history contract')
        self.frames, self.max_gap_s = frames, max_gap_s
        self.rows = deque(maxlen=frames)
        self.times = deque(maxlen=frames)

    def clear(self):
        self.rows.clear(); self.times.clear()

    @property
    def ready(self):
        return len(self.times) == self.frames

    def append(self, stamp, frame):
        frame = tuple(float(v) for v in frame)
        if len(frame) != len(FEATURES) or not math.isfinite(stamp) or not all(math.isfinite(v) for v in frame):
            self.clear(); raise ValueError('Invalid feature frame')
        if self.times and (stamp <= self.times[-1] or stamp-self.times[-1] > self.max_gap_s):
            self.clear()
            raise ValueError('History timestamp duplicate/reversal/gap; refill after reset')
        self.times.append(float(stamp)); self.rows.append(frame)
        # Repetition is tensor padding only; ready remains false until real K frames.
        rows = [self.rows[0]]*(self.frames-len(self.rows))+list(self.rows)
        return tuple(v for row in rows for v in row)


@dataclass(frozen=True)
class ReferenceLimits:
    separation_m: float
    wheel_speed_m_s: float
    forward_m_s: float
    yaw_rad_s: float
    wheel_acceleration_m_s2: float
    residual_wheel_m_s: float
    max_age_s: float

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in self.__dict__.values()):
            raise ValueError('Reference limits must be explicit positive proposals')


class ResidualReference:
    """Deterministic proposal→accepted-reference mapping, separate from governor.

    Fallback is STOP, never unvalidated automatic forward recovery. A caller
    must establish a new epoch after stop/fault/source changes. No certificate.
    """
    def __init__(self, limits):
        self.limits = limits
        self.reset()

    def reset(self):
        self.previous = (0., 0.)
        self.latched = False

    def compose(self, baseline, action, dt, authority=0., *, permission=False,
                sensors_fresh=False, history_ready=False, command_age_s=math.inf,
                emergency_stop=False, fault=False):
        trace = dict(contract_id=CONTRACT_ID, proposal=None, proposed_residual_wheel_m_s=None,
                     accepted_reference_wheel_m_s=(0., 0.), body_reference=(0., 0.),
                     actuator_target=None, motor_execution_verified=False, reason='stop',
                     authority=authority)
        try:
            base = pair(baseline); proposal = pair(action)
            if not all(-1 <= x <= 1 for x in proposal):
                raise ValueError('Proposal outside normalized Box')
            if not math.isfinite(dt) or not 0 < dt <= self.limits.max_age_s:
                raise ValueError('Invalid elapsed control period')
            if not math.isfinite(authority) or not 0 <= authority <= 1:
                raise ValueError('Invalid residual authority')
            if not math.isfinite(command_age_s) or not 0 <= command_age_s <= self.limits.max_age_s:
                raise ValueError('Stale baseline')
            if any(type(flag) is not bool for flag in (permission,sensors_fresh,history_ready,emergency_stop,fault)):
                raise ValueError('Explicit boolean permission/freshness/stop/fault flags required')
            if not permission or not sensors_fresh or emergency_stop or fault or self.latched:
                raise ValueError('Permission/freshness/stop/fault')
        except (ValueError, TypeError, OverflowError) as error:
            self.previous = (0., 0.); self.latched = True
            trace['reason'] = str(error)
            return trace
        c, d = proposal
        # L1 scaling enforces a PER-WHEEL bound in the common/diff basis.
        normalizer = max(1., abs(c)+abs(d))
        gain = self.limits.residual_wheel_m_s*authority if history_ready else 0.
        delta = (gain*(c-d)/normalizer, gain*(c+d)/normalizer)
        v = max(-self.limits.forward_m_s, min(self.limits.forward_m_s, base[0]))
        yaw = max(-self.limits.yaw_rad_s, min(self.limits.yaw_rad_s, base[1]))
        nominal = body_to_wheels(v, yaw, self.limits.separation_m)
        # Baseline zero cannot create locomotion from residual alone.
        if base == (0., 0.):
            delta = (0., 0.)
        step = self.limits.wheel_acceleration_m_s2*dt
        def project(wheels):
            v, yaw = wheels_to_body(*wheels, self.limits.separation_m)
            wheels = body_to_wheels(max(-self.limits.forward_m_s,min(self.limits.forward_m_s,v)),
                max(-self.limits.yaw_rad_s,min(self.limits.yaw_rad_s,yaw)),self.limits.separation_m)
            scale = max(1.,max(map(abs,wheels))/self.limits.wheel_speed_m_s)
            return tuple(old+max(-step,min(step,new/scale-old)) for old,new in zip(self.previous,wheels))
        shaped_baseline = project(nominal)
        accepted = project(tuple(a+b for a,b in zip(nominal,delta)))
        policy_contribution = tuple(a-b for a,b in zip(accepted,shaped_baseline))
        # Linear interpolation from the last valid reference preserves these convex bounds.
        self.previous = accepted
        trace.update(proposal=proposal, proposed_residual_wheel_m_s=delta,
                     accepted_reference_wheel_m_s=accepted,
                     body_reference=wheels_to_body(*accepted,self.limits.separation_m),
                     reason='accepted' if history_ready else 'baseline_only_history_warmup',
                     baseline_body=base, nominal_wheel_m_s=nominal,
                     shaped_baseline_wheel_m_s=shaped_baseline,
                     accepted_policy_delta_wheel_m_s=policy_contribution,
                     baseline_shaping_delta_wheel_m_s=tuple(a-b for a,b in zip(shaped_baseline,nominal)),
                     implementation_revision=IMPLEMENTATION_REVISION,
                     reference_modified=accepted != tuple(a+b for a,b in zip(nominal,delta)))
        return trace
