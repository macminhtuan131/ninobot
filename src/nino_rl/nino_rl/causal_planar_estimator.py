"""Causal wheel-speed + gyro-Z planar odometry. No truth/pose sensor input.

Initial state is explicit scenario metadata. Output is an estimate, never body
ground truth; wheel slip, gyro bias and initial error remain model limitations.
"""
from collections import deque
import math


class CausalPlanarEstimator:
    def __init__(self, *, radius_l, radius_r, maximum_gap_s=.04, gyro_bias_rad_s=0., maximum_buffer=4096):
        if not all(math.isfinite(v) and v>0 for v in (radius_l,radius_r,maximum_gap_s)):
            raise ValueError('Positive finite wheel geometry and gap bound required')
        if not math.isfinite(gyro_bias_rad_s) or type(maximum_buffer) is not int or maximum_buffer<2:
            raise ValueError('Finite gyro bias and bounded buffers required')
        self.radii=(radius_l,radius_r);self.maximum_gap_s=maximum_gap_s
        self.bias=gyro_bias_rad_s;self.maximum_buffer=maximum_buffer

    def reset(self, *, stamp_s, pose, epoch):
        if len(pose)!=3 or not all(math.isfinite(v) for v in (*pose,stamp_s)) or not epoch:
            raise ValueError('Explicit finite initial pose/time and epoch required')
        self.x,self.y,self.yaw=map(float,pose);self.time=float(stamp_s);self.epoch=str(epoch)
        self.initial_time=self.time;self.imu=deque();self.wheel=deque();self.last_received={}
        self.initialization='declared_scenario_pose_at_task_epoch_not_truth_readback'
        self.updates=0

    def push(self, channel, stamp_s, values, receipt_monotonic_s):
        if channel not in ('imu','wheel'):raise ValueError('Only gyro-Z and drive wheel speeds are estimator inputs')
        values=tuple(map(float,values));expected=1 if channel=='imu' else 2
        if len(values)!=expected or not all(math.isfinite(v) for v in (*values,stamp_s,receipt_monotonic_s)):
            raise ValueError('Invalid estimator sample')
        previous=self.last_received.get(channel)
        if previous is not None:
            if stamp_s<previous:raise ValueError('Estimator source reversal')
            if stamp_s==previous:return False
        self.last_received[channel]=stamp_s
        if channel=='imu' and stamp_s<=self.initial_time:return False
        queue=self.imu if channel=='imu' else self.wheel
        if len(queue)>=self.maximum_buffer:raise ValueError('Estimator buffer exhausted; no silent sample eviction')
        queue.append(dict(stamp_s=float(stamp_s),values=values,receipt_monotonic_s=float(receipt_monotonic_s)))
        return True

    def advance(self, now_s):
        if not math.isfinite(now_s) or now_s<self.time:raise ValueError('Estimator control clock reversed')
        records=[]
        while self.imu and self.imu[0]['stamp_s']<=now_s:
            imu=self.imu.popleft();t=imu['stamp_s'];dt=t-self.time
            if not 0<dt<=self.maximum_gap_s+1e-9:raise ValueError('Estimator gyro source gap')
            # Use only a wheel sample with source stamp <= the integration time.
            # Later callbacks cannot retrospectively rewrite the estimate.
            while len(self.wheel)>1 and self.wheel[1]['stamp_s']<=t:self.wheel.popleft()
            if not self.wheel or self.wheel[0]['stamp_s']>t:raise ValueError('No causal wheel support for gyro sample')
            wheel=self.wheel[0];age=t-wheel['stamp_s']
            if age>self.maximum_gap_s+1e-9:raise ValueError('Estimator wheel support stale')
            v=sum(r*w for r,w in zip(self.radii,wheel['values']))/2
            yaw_rate=imu['values'][0]-self.bias;dyaw=yaw_rate*dt;mid=self.yaw+dyaw/2
            self.x+=v*math.cos(mid)*dt;self.y+=v*math.sin(mid)*dt
            self.yaw=(self.yaw+dyaw+math.pi)%(2*math.pi)-math.pi
            self.time=t;self.updates+=1
            records.append(dict(stamp_s=t,wheel_stamp_s=wheel['stamp_s'],wheel_age_s=age,dt_s=dt,
                gyro_receipt_monotonic_s=imu['receipt_monotonic_s'],wheel_receipt_monotonic_s=wheel['receipt_monotonic_s'],
                pose=[self.x,self.y,self.yaw],wheel_linear_v_m_s=v,gyro_yaw_rad_s=yaw_rate,
                epoch=self.epoch,source='wheel_imu_odometry',truth_input=False))
        return records

    def estimate(self):
        return dict(pose=[self.x,self.y,self.yaw],stamp_s=self.time,epoch=self.epoch,
                    updates=self.updates,initialization=self.initialization,source='wheel_imu_odometry',truth_input=False)
