"""Causal estimated-pose guidance -> existing residual reference contract.

Pure offline adapter; no ROS, publishers, robot commands or training. Reuses
the existing flat_motion_command geometry. Pose never becomes an actor feature;
only the follower's v/yaw reference enters the unchanged 20-feature ABI.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from .core import PathTracker, TrackingState, wrap_angle
from .flat_feedback import flat_motion_command


@dataclass(frozen=True)
class PoseSample:
    x_m: float
    y_m: float
    yaw_rad: float
    stamp_s: float
    receipt_s: float
    frame_id: str
    source_id: str
    clock_id: str
    epoch: str


def contract(config):
    c = deepcopy(config)
    if c['schema_version'] != 1 or not c['baseline_id']:
        raise ValueError('Versioned baseline identity required')
    sources = {'wheel_imu_odometry', 'fused_localization'}
    if c.get('allow_sim_truth_oracle') is True: sources.add('sim_truth_oracle')
    if c['pose_source'] not in sources:
        raise ValueError('Pose source unknown or truth oracle not explicitly allowed')
    for key in ['pose_frame_id','command_frame_id','clock_id']:
        if not isinstance(c[key], str) or not c[key]: raise ValueError('Explicit pose/command frame and common clock required')
    for key in ['maximum_pose_age_s','maximum_corridor_error_m','maximum_goal_overshoot_m','goal_tolerance_m','goal_heading_tolerance_deg']:
        if not math.isfinite(c[key]) or c[key] <= 0: raise ValueError('Positive finite guidance setting: '+key)
    if len(c['path_points_m']) != 2:
        raise ValueError('V1 guidance supports one straight segment only; turns need a separate ordered-route contract')
    PathTracker(c['path_points_m'])
    nav = c['navigation']; feedback = nav['path_feedback']
    if feedback['enabled'] is not True: raise ValueError('Guidance adapter requires enabled path feedback')
    for value in [nav['straight_speed_m_s'], nav['minimum_approach_speed_m_s'], nav['goal_slowdown_distance_m'],
                  feedback['lookahead_m'], feedback['max_yaw_rate_rad_s'], feedback['residual_fade_distance_m']]:
        if not math.isfinite(value) or value <= 0: raise ValueError('Positive finite follower parameters required')
    if not 0 <= nav['goal_stop_tolerance_m'] <= c['goal_tolerance_m']:
        raise ValueError('Goal stop tolerance exceeds declared goal radius')
    if nav['minimum_approach_speed_m_s'] > nav['straight_speed_m_s']:
        raise ValueError('Minimum approach speed exceeds cruise')
    paths = [Path(__file__), Path(__file__).with_name('core.py'), Path(__file__).with_name('flat_feedback.py'), Path(__file__).with_name('task_geometry.py')]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    body = dict(configuration=c, source_sha256=hashes, actor_features_added=0,
                scope='offline_guidance_adapter_not_deployed', oracle=c['pose_source']=='sim_truth_oracle')
    return dict(body, sha256=hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest())


class GuidanceReference:
    def __init__(self, config, *, epoch):
        self.config = deepcopy(config)
        self.contract = contract(config)
        self.path = PathTracker(config['path_points_m'])
        self.reset(epoch=epoch)

    def reset(self, *, epoch):
        if not isinstance(epoch, str) or not epoch: raise ValueError('Explicit control epoch required')
        self.epoch, self.pose, self.fault_reason = epoch, None, None
        self.previous_tick = None

    def reject(self, reason):
        self.pose = None
        self.fault_reason = reason
        raise ValueError(reason)

    def update_pose(self, sample):
        if self.fault_reason: raise ValueError('Guidance latched; explicit reset required')
        if not isinstance(sample, PoseSample): return self.reject('Typed PoseSample required')
        values = [sample.x_m,sample.y_m,sample.yaw_rad,sample.stamp_s,sample.receipt_s]
        if not all(math.isfinite(v) for v in values): return self.reject('Nonfinite pose/clock')
        c = self.config
        if (sample.frame_id, sample.source_id, sample.clock_id, sample.epoch) != (c['pose_frame_id'], c['pose_source'], c['clock_id'], self.epoch):
            return self.reject('Pose frame/source/clock/epoch mismatch')
        if sample.stamp_s > sample.receipt_s: return self.reject('Future source pose; no implicit clock conversion')
        if self.pose:
            if sample.stamp_s == self.pose.stamp_s:
                # Repeated source cannot renew its receipt-based lease, even
                # when a republisher gives it a fresh receipt time.
                if (sample.x_m,sample.y_m,sample.yaw_rad) != (self.pose.x_m,self.pose.y_m,self.pose.yaw_rad):
                    return self.reject('Changed payload at duplicate pose stamp')
                return False
            if sample.stamp_s < self.pose.stamp_s or sample.receipt_s <= self.pose.receipt_s:
                return self.reject('Pose timestamp reversal')
        self.pose = sample
        return True

    def command(self, now_s, *, permission, stop_requested=False):
        if type(permission) is not bool or type(stop_requested) is not bool:
            raise ValueError('Explicit boolean owner permission and stop required')
        c = self.config
        result = dict(reference=[0.,0.], valid=False, permission=False, fault=True,
            reason='missing_pose', command_stamp_s=now_s, frame_id=c['command_frame_id'],
            pose_frame_id=c['pose_frame_id'], pose_source=c['pose_source'], clock_id=c['clock_id'],
            epoch=self.epoch, baseline_contract_sha256=self.contract['sha256'], oracle=self.contract['oracle'])
        if not math.isfinite(now_s) or (self.previous_tick is not None and now_s <= self.previous_tick):
            self.fault_reason = 'Control clock duplicate/reversal'
        self.previous_tick = now_s
        if stop_requested or not permission:
            result.update(reason='requested_stop' if stop_requested else 'owner_denied', fault=False)
            return result
        if self.fault_reason:
            result['reason'] = self.fault_reason
            return result
        p = self.pose
        if p is None: return result
        source_age, receipt_age = now_s-p.stamp_s, now_s-p.receipt_s
        result.update(pose_stamp_s=p.stamp_s, pose_receipt_s=p.receipt_s,
                      source_age_s=source_age, receipt_age_s=receipt_age)
        if not 0 <= min(source_age,receipt_age) <= max(source_age,receipt_age) <= c['maximum_pose_age_s']:
            self.fault_reason = 'Stale/future pose; explicit reset required'
            result['reason'] = self.fault_reason
            return result
        path_s, lateral, heading, _ = self.path.project(p.x_m,p.y_m)
        tracking = TrackingState(path_s,lateral,wrap_angle(heading-p.yaw_rad),
            max(0.,self.path.total_length-path_s),math.hypot(p.x_m-self.path.points[-1,0],p.y_m-self.path.points[-1,1]))
        tangent = self.path.delta[-1]/self.path.lengths[-1]
        overshoot = float((p.x_m-self.path.points[-1,0])*tangent[0]+(p.y_m-self.path.points[-1,1])*tangent[1])
        if abs(lateral)>c['maximum_corridor_error_m'] or overshoot>c['maximum_goal_overshoot_m']:
            self.fault_reason = 'Outside declared guidance corridor/overshoot'
            result['reason'] = self.fault_reason
            return result
        state = SimpleNamespace(x=p.x_m,y=p.y_m,yaw=p.yaw_rad)
        v, yaw = flat_motion_command(state,self.path,tracking,c,policy_yaw=0.)
        result.update(reference=[v,yaw],valid=True,permission=True,fault=False,
                      reason='goal_reference_zero' if (v,yaw)==(0.,0.) else 'guidance_reference')
        return result


def apply_guidance(view, reference):
    """Pure bridge: preserve telemetry and flag invalid guidance to the gate.

    No pose/GT enters feature_frame. A new generated command stamp does not
    conceal stale pose: invalid guidance removes permission and sets fault.
    No hardware or motor publication is performed by this function.
    """
    if reference['command_stamp_s'] != view['stamp_s']:
        raise ValueError('Guidance and policy tick must share the declared clock')
    if view.get('clock_id') != reference['clock_id']:
        raise ValueError('Explicit matching guidance/policy clock identity required')
    baseline_frame = (view.get('source_samples') or {}).get('baseline', {}).get('frame')
    if baseline_frame != reference['frame_id']:
        raise ValueError('Guidance and policy command frames differ')
    result = deepcopy(view)
    result['baseline'] = tuple(reference['reference'])
    result['features']['baseline_v_m_s'], result['features']['baseline_yaw_rad_s'] = result['baseline']
    result['permission'] = bool(view['permission'] and reference['permission'] and reference['valid'])
    result['fault'] = bool(view['fault'] or reference['fault'])
    result['command_age_s'] = 0.
    result['guidance_audit'] = deepcopy(reference)
    if result.get('source_samples') is not None:
        result['source_samples']['baseline'] = dict(values=list(result['baseline']),receipt_s=view['stamp_s'],
            source_s=None,frame=reference['frame_id'])
    return result
