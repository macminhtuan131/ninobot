"""One causal observation/reference path shared by Gym and ROS. No ROS imports."""
from copy import deepcopy
import math
from .residual_velocity import (FEATURES, FeatureHistory, ReferenceLimits, ResidualReference,
                                body_to_wheels, feature_frame, pair)
from .governor_core import ReactiveGovernor, GovernorFrame


class ObservationAssembler:
    """Receipt clock drives age; source stamps are separately retained/audited.

    Every accepted callback has an increasing source stamp (if provided) and
    receipt stamp. Duplicate callbacks cannot renew freshness. No interpolation
    into the future, no encoder-derived body ground truth.
    """
    def __init__(self, geometry, max_age_s=.2, imu_yaw_rad=0.):
        self.geometry=deepcopy(geometry);self.max_age=float(max_age_s);self.yaw=float(imu_yaw_rad)
        self.reset()

    def reset(self):
        self.samples={};self.rejected=0

    def push(self, channel, values, receipt_s, source_s=None, frame=None):
        if channel not in ('imu','wheel','baseline','final','status'):raise ValueError('Unknown input channel')
        stamp=float(receipt_s)
        if not math.isfinite(stamp) or (source_s is not None and not math.isfinite(source_s)):
            raise ValueError('Invalid input clock')
        old=self.samples.get(channel)
        if old and (stamp<=old['receipt_s'] or (source_s is not None and old['source_s'] is not None and source_s<=old['source_s'])):
            self.rejected+=1;return False
        self.samples[channel]=dict(values=deepcopy(values),receipt_s=stamp,source_s=source_s,frame=frame)
        return True

    def view(self, now_s):
        now=float(now_s)
        if not math.isfinite(now):raise ValueError('Invalid tick clock')
        missing=set(('imu','wheel','baseline','final','status'))-self.samples.keys()
        if missing:raise ValueError('Missing inputs: '+','.join(sorted(missing)))
        ages={k:now-v['receipt_s'] for k,v in self.samples.items()}
        if any(not 0<=age<=self.max_age for age in ages.values()):raise ValueError('Stale/future input: '+str(ages))
        imu=self.samples['imu']['values'];wheel=self.samples['wheel']['values']
        if len(imu)!=6 or len(wheel)!=2:raise ValueError('IMU6 and wheel2 required')
        if not all(math.isfinite(float(x)) for x in (*imu,*wheel)):raise ValueError('Invalid IMU/wheel values')
        c,s=math.cos(self.yaw),math.sin(self.yaw)
        gx,gy,gz,ax,ay,az=map(float,imu)
        gyro=(c*gx-s*gy,s*gx+c*gy,gz);acc=(c*ax-s*ay,s*ax+c*ay,az)
        base=pair(self.samples['baseline']['values']);final=pair(self.samples['final']['values'])
        state=self.samples['status']['values']
        if not isinstance(state,dict) or any(type(state.get(k)) is not bool for k in ('permission','fault','emergency_stop')):
            raise ValueError('Explicit status flags required')
        values=dict(zip(FEATURES[:12],(*base,*wheel,*gyro,*acc,*final)))
        values.update(previous_proposal_common=0.,previous_proposal_diff=0.,
                      previous_accepted_common=0.,previous_accepted_diff=0.,
                      imu_age_s=ages['imu'],wheel_age_s=ages['wheel'])
        return dict(features=values,baseline=base,stamp_s=now,command_age_s=ages['baseline'],
                    sensors_fresh=True,**state,source_samples=deepcopy(self.samples),input_ages_s=ages,
                    clock='caller_declared_receipt_clock',actual_actuator_target=None,
                    freshness_scope='receipt age only; source-to-receipt latency requires separate clock validation')


class ResidualPipeline:
    """Policy proposal and projection use exactly the same history in sim/ROS."""
    def __init__(self, config, governor=False):
        self.config=deepcopy(config);self.reference=ResidualReference(ReferenceLimits(**config['reference_limits']))
        self.history=FeatureHistory(config['actor']['history_frames'],config['actor']['max_history_gap_s'])
        self.governor=ReactiveGovernor(config.get('governor_parameters',{})) if governor else None
        self.reset()

    def reset(self):
        self.reference.reset();self.history.clear();self.proposal=(0.,0.);self.accepted=(0.,0.)
        self.observation=None;self.last_view=None;self._governor_time=None
        if self.governor:self.governor.reset()

    def observe(self, view):
        view=deepcopy(view);f=view['features']
        f['previous_proposal_common'],f['previous_proposal_diff']=self.proposal
        f['previous_accepted_common'],f['previous_accepted_diff']=self.accepted
        self.observation=self.history.append(float(view['stamp_s']),feature_frame(f,**self.config['nominal_geometry']))
        self.last_view=view
        return self.observation

    def project(self, action, dt, authority):
        if self.last_view is None:raise ValueError('Observe before project')
        v=self.last_view;baseline=pair(v['baseline']);governor_trace=None
        if self.governor:
            f=v['features'];targets=v.get('actual_actuator_target')
            # Missing target disables wheel-error channel explicitly. Nothing
            # is emitted as a fabricated actuator target/readback.
            left,right=(targets if targets is not None else (f['wheel_l_rad_s'],f['wheel_r_rad_s']))
            frame=GovernorFrame(f['accel_z_m_s2']-9.80665,math.hypot(f['gyro_x_rad_s'],f['gyro_y_rad_s']),
                f['wheel_l_rad_s'],f['wheel_r_rad_s'],left,right,f['last_final_v_m_s'])
            governor_trace=self.governor.update(frame,dt,*baseline,fresh=v['sensors_fresh'])
            governor_trace['wheel_error_channel_available']=targets is not None
            baseline=tuple(x*governor_trace['scale'] for x in baseline)
        trace=self.reference.compose(baseline,action,dt,authority,
            permission=v['permission'],sensors_fresh=v['sensors_fresh'],history_ready=self.history.ready,
            command_age_s=v['command_age_s'],emergency_stop=v['emergency_stop'],
            fault=v['fault'] or bool(governor_trace and governor_trace.get('fault')))
        self.proposal=pair(action)
        dl,dr=trace.get('accepted_policy_delta_wheel_m_s',(0.,0.));bound=self.reference.limits.residual_wheel_m_s
        self.accepted=((dl+dr)/(2*bound),(dr-dl)/(2*bound))
        trace.update(observation=list(self.observation),history_ready=self.history.ready,
                     source_samples=v.get('source_samples'),input_ages_s=v.get('input_ages_s'),
                     input_stamp_s=v['stamp_s'],governor=governor_trace,
                     freshness_scope=v.get('freshness_scope'),
                     actuator_target_readback=v.get('actual_actuator_target'),
                     original_baseline_body=v['baseline'])
        return trace
