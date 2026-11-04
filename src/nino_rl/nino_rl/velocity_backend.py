"""Executable velocity-reference integration plant; NOT a calibrated Nino model.

This reduced-order backend proves software data flow and supports bounded learner
checks. Gazebo and physical model validation remain separate evidence levels.
"""
from collections import deque
from copy import deepcopy
import math
import numpy as np
from nino_control.residual_velocity import CONTRACT_ID, body_to_wheels
from nino_control.residual_pipeline import ObservationAssembler


class VelocityBackend:
    residual_contract_id=CONTRACT_ID
    kind='reduced_order_velocity_fixture'
    calibrated_to_hardware=False

    def __init__(self,config):
        self.config=deepcopy(config);self.options=config.get('backend',{})
        self.geometry=config['nominal_geometry'];self.b=self.geometry['separation']
        self.dt=float(config['control_interval_s']);self.horizon=float(self.options.get('horizon_s',6.))
        self.speed=float(self.options.get('cruise_m_s',.16))
        self.assembler=ObservationAssembler(self.geometry,config['reference_limits']['max_age_s'],
                                          config.get('imu_yaw_rad',0.))
        self.closed=False;self.last_view=None

    def reference(self):
        return (self.speed if .5<=self.time<self.horizon-2. else 0.,0.)

    def reset(self,seed=None):
        self.rng=np.random.default_rng(seed);self.time=0.;self.position=np.zeros(3);self.wheel=np.zeros(2)
        self.target=np.zeros(2);self.final=np.zeros(2);self.command=np.zeros(2);self.queue=deque()
        self.previous_v=0.;self.previous_yaw=0.;self.assembler.reset();self.closed=False
        self.lag=np.array(self.options.get('motor_lag_s',[.16,.20]),dtype=float)
        self.gain=np.array(self.options.get('wheel_gain',[1.,.97]),dtype=float)
        self.delay=float(self.options.get('command_delay_s',.04))
        self.native_accel=float(self.options.get('motor_acceleration_rad_s2',12.))
        if min(*self.lag,self.native_accel)<=0 or self.delay<0:raise ValueError('Invalid fixture dynamics')
        self._sense(0.,0.,0.)
        self.last_view=self._view()
        return deepcopy(self.last_view),dict(backend=self.kind,calibrated_to_hardware=False,seed=seed)

    def _sense(self,v,w,accel):
        # Generate sensor-frame values, then use the SAME mounting conversion
        # as the real ROS ingestion. Privileged position is not an actor input.
        yaw=float(self.config.get('imu_yaw_rad',0.));c,s=math.cos(yaw),math.sin(yaw)
        noise=float(self.options.get('imu_noise_std',0.))
        sensor=(0.,0.,w,c*accel,-s*accel,9.80665+float(self.rng.normal(0.,noise)))
        self.assembler.push('imu',sensor,self.time,self.time,'imu_link')
        self.assembler.push('wheel',self.wheel.tolist(),self.time,self.time,'drive_wheels')
        self.assembler.push('final',self.final.tolist(),self.time,None,'base_link')
        self.assembler.push('baseline',self.reference(),self.time,None,'base_link')
        self.assembler.push('status',dict(permission=True,fault=False,emergency_stop=False),self.time,self.time)

    def _view(self):
        view=self.assembler.view(self.time)
        view['actual_actuator_target']=self.target.tolist()
        view['target_evidence']='readback_of_fixture_internal_target_only'
        return view

    def advance_reference(self,v,w,dt):
        if self.closed:raise RuntimeError('Backend closed')
        if not math.isclose(dt,self.dt):raise ValueError('Control interval changed')
        request=np.array([v,w],dtype=float)
        if not np.all(np.isfinite(request)):raise ValueError('Nonfinite backend reference')
        self.queue.append((self.time+self.delay,request))
        before=self.position[0];vib=0.;substeps=max(1,int(round(dt/.005)));h=dt/substeps
        for i in range(substeps):
            self.time+=h
            while self.queue and self.queue[0][0]<=self.time+1e-10:self.command=self.queue.popleft()[1]
            # Model the remaining smoother and actuator ramp explicitly.
            rates=np.array([.1,.2]);self.final+=np.clip(self.command-self.final,-rates*h,rates*h)
            linear=body_to_wheels(*self.final,self.b)
            desired=np.asarray(linear)/np.array([self.geometry['radius_l'],self.geometry['radius_r']])
            self.target+=np.clip(desired-self.target,-self.native_accel*h,self.native_accel*h)
            self.wheel+=(self.target*self.gain-self.wheel)*(1-np.exp(-h/self.lag))
            ul,ur=self.wheel*np.array([self.geometry['radius_l'],self.geometry['radius_r']])
            body_v=(ul+ur)/2;body_w=(ur-ul)/self.b
            self.position[0]+=body_v*math.cos(self.position[2])*h
            self.position[1]+=body_v*math.sin(self.position[2])*h
            self.position[2]+=body_w*h
            acceleration=(body_v-self.previous_v)/h;self.previous_v=body_v;self.previous_yaw=body_w
            vib+=acceleration**2*h
            if (i+1)%4==0 or i==substeps-1:self._sense(body_v,body_w,acceleration)
        self.last_view=self._view()
        labels=dict(progress_m=float(self.position[0]-before),heading_rad=float(self.position[2]),
                    lateral_m=float(self.position[1]),vibration_proxy=math.sqrt(vib/dt))
        truncated=self.time>=self.horizon-1e-8
        info=dict(backend=self.kind,calibrated_to_hardware=False,
                  applied_target_rad_s=self.target.tolist(),final_ros_reference=self.final.tolist(),
                  final_reference_evidence='reduced-order modeled smoother output; not real ROS/motor readback',
                  feedback_wheel_rad_s=self.wheel.tolist(),truth_pose_m_rad=self.position.tolist(),
                  body_speed_m_s=float(self.previous_v),body_yaw_rad_s=float(self.previous_yaw),
                  sensor_clock_s=float(self.time),labels=labels,
                  termination_reason='time_limit' if truncated else None)
        return deepcopy(self.last_view),labels,False,truncated,info

    def close(self):
        self.command[:]=0.;self.closed=True
