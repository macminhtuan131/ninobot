"""Isolated flat Gazebo velocity-reference integration fixture, not Nino fidelity.

Native DiffDrive sets joint velocities; it does NOT emulate CyberGear PI/current.
Two frictionless spherical supports are not swivel casters. No obstacle claims.
"""
from copy import deepcopy
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from nino_control.residual_pipeline import ObservationAssembler
from nino_control.residual_velocity import CONTRACT_ID


def fixture_world():
    parts=['''<sdf version="1.9"><world name="residual_fixture">
      <physics name="physics" type="ignored"><max_step_size>0.002</max_step_size><real_time_factor>0</real_time_factor></physics>
      <gravity>0 0 -9.80665</gravity>
      <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
      <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
      <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
      <model name="floor"><static>true</static><link name="floor"><collision name="solid_floor"><geometry><box><size>20 20 0.1</size></box></geometry></collision><pose>0 0 -0.05 0 0 0</pose></link></model>
      <model name="robot"><pose>0 0 0.061 0 0 0</pose>
      <link name="body"><inertial><mass>5</mass><inertia><ixx>0.04</ixx><iyy>0.04</iyy><izz>0.06</izz></inertia></inertial>
      <collision name="chassis"><pose>0 0 0.035 0 0 0</pose><geometry><box><size>0.3 0.28 0.05</size></box></geometry></collision>
      <sensor name="imu" type="imu"><always_on>true</always_on><update_rate>50</update_rate><topic>/nino_fixture/imu</topic></sensor></link>''']
    for name,y in [('left',.1725),('right',-.1725)]:
        parts.append(f'''<link name="{name}"><pose>0 {y} 0 -1.57079632679 0 0</pose>
          <inertial><mass>0.2</mass><inertia><ixx>0.0002</ixx><iyy>0.0002</iyy><izz>0.0003</izz></inertia></inertial>
          <collision name="wheel"><geometry><cylinder><radius>0.06</radius><length>0.025</length></cylinder></geometry></collision></link>
          <joint name="{name}_wheel" type="revolute"><parent>body</parent><child>{name}</child><axis><xyz expressed_in="__model__">0 1 0</xyz><limit><lower>-1e16</lower><upper>1e16</upper></limit></axis></joint>''')
    for name,x in [('front',.13),('rear',-.13)]:
        parts.append(f'''<link name="{name}"><pose>{x} 0 -0.04 0 0 0</pose>
          <inertial><mass>0.02</mass><inertia><ixx>0.00001</ixx><iyy>0.00001</iyy><izz>0.00001</izz></inertia></inertial>
          <collision name="support"><geometry><sphere><radius>0.02</radius></sphere></geometry><surface><friction><ode><mu>0</mu><mu2>0</mu2></ode></friction></surface></collision></link>
          <joint name="{name}_fixed" type="fixed"><parent>body</parent><child>{name}</child></joint>''')
    parts.append('''<plugin filename="gz-sim-diff-drive-system" name="gz::sim::systems::DiffDrive">
      <left_joint>left_wheel</left_joint><right_joint>right_wheel</right_joint><wheel_separation>0.345</wheel_separation><wheel_radius>0.06</wheel_radius>
      <topic>/nino_fixture/cmd</topic><odom_topic>/nino_fixture/encoder_odom</odom_topic><odom_publish_frequency>50</odom_publish_frequency>
      <max_linear_acceleration>0.1</max_linear_acceleration><min_linear_acceleration>-0.1</min_linear_acceleration>
      <max_angular_acceleration>0.2</max_angular_acceleration><min_angular_acceleration>-0.2</min_angular_acceleration>
      </plugin><plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher"><topic>/nino_fixture/joints</topic></plugin>
      <plugin filename="gz-sim-odometry-publisher-system" name="gz::sim::systems::OdometryPublisher"><odom_topic>/nino_fixture/truth</odom_topic><odom_publish_frequency>50</odom_publish_frequency><dimensions>3</dimensions></plugin>
      </model></world></sdf>''')
    return ''.join(parts)


class GazeboVelocityBackend:
    residual_contract_id=CONTRACT_ID
    kind='gazebo_flat_velocity_integration_fixture'
    calibrated_to_hardware=False
    def __init__(self,config,directory):
        self.partition='nino_residual_'+uuid.uuid4().hex
        self.previous_partition=os.environ.get('GZ_PARTITION');os.environ['GZ_PARTITION']=self.partition
        from gz.transport13 import Node,NodeOptions
        from gz.msgs10.twist_pb2 import Twist
        from gz.msgs10.imu_pb2 import IMU
        from gz.msgs10.model_pb2 import Model
        from gz.msgs10.odometry_pb2 import Odometry
        self.config=deepcopy(config);self.directory=Path(directory);self.closed=False;self.server=None;self.log=None
        options=NodeOptions();options.partition=self.partition
        self.node=Node(options);self.cmd=self.node.advertise('/nino_fixture/cmd',Twist)
        self.lock=threading.RLock();self.messages={};self.counts={};self.final=(0.,0.);self.time=0.
        self.assembler=ObservationAssembler(config['nominal_geometry'],.2,0.)
        for name,typ,topic in [('imu',IMU,'/nino_fixture/imu'),('joint',Model,'/nino_fixture/joints'),('truth',Odometry,'/nino_fixture/truth')]:
            self.node.subscribe(typ,topic,lambda msg,k=name:self.receive(k,msg))
    def receive(self,key,msg):
        with self.lock:self.messages[key]=msg;self.counts[key]=self.counts.get(key,0)+1
    def _stamp(self,m):return float(m.header.stamp.sec)+m.header.stamp.nsec*1e-9
    def step_world(self,steps):
        # A separate native requester keeps the Python subscriber callbacks free
        # while a blocking request waits. Require the actual Boolean ACK.
        ack=subprocess.run(['gz','service','-s','/world/residual_fixture/control',
            '--reqtype','gz.msgs.WorldControl','--reptype','gz.msgs.Boolean','--timeout','1000',
            '--req',f'pause: true, multi_step: {int(steps)}'],env=dict(os.environ,GZ_PARTITION=self.partition),
            capture_output=True,text=True,timeout=4)
        if ack.returncode or 'data: true' not in ack.stdout:raise RuntimeError('Gazebo world control unavailable: '+ack.stdout+ack.stderr)
        target=self.time+steps*.002;end=time.monotonic()+8.
        while time.monotonic()<end:
            with self.lock:
                ready=len(self.messages)==3 and all(self._stamp(m)>=target-.022 for m in self.messages.values())
                if ready:
                    self.time=self._stamp(self.messages['joint']);return
            time.sleep(.005)
        raise RuntimeError('Gazebo source coverage deadline; retain server log and traces: '+str(self.counts))
    def reset(self,seed=None):
        if self.server is not None:raise ValueError('New fixture instance required for exact reset; no false snapshot claim')
        world=self.directory/'world.sdf';world.write_text(fixture_world());self.log=(self.directory/'gazebo.log').open('w')
        env=dict(os.environ);env['GZ_PARTITION']=self.partition
        self.server=subprocess.Popen(['gz','sim','-s','-v','3','--headless-rendering',str(world)],env=env,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        end=time.monotonic()+12.;connected=False
        while time.monotonic()<end:
            if self.server.poll() is not None:raise RuntimeError('Gazebo exited; inspect gazebo.log')
            try:self.step_world(10);connected=True;break
            except RuntimeError:time.sleep(.1)
        if not connected:raise RuntimeError('Gazebo startup deadline')
        for _ in range(10):self.step_world(50)
        self.start=self.time;self.previous_x=self.messages['truth'].pose.position.x
        return self.view(),dict(backend=self.kind,seed=seed,calibrated_to_hardware=False,partition=self.partition)
    def view(self):
        with self.lock:
            imu=self.messages['imu'];j=self.messages['joint'];truth=self.messages['truth']
            wheels={x.name:x.axis1.velocity for x in j.joint}
            if not {'left_wheel','right_wheel'}.issubset(wheels):raise ValueError('Gazebo joint names missing')
            self.assembler.push('imu',[imu.angular_velocity.x,imu.angular_velocity.y,imu.angular_velocity.z,imu.linear_acceleration.x,imu.linear_acceleration.y,imu.linear_acceleration.z],self._stamp(imu),self._stamp(imu),'body')
            self.assembler.push('wheel',[wheels['left_wheel'],wheels['right_wheel']],self._stamp(j),self._stamp(j),'wheels')
            elapsed=self.time-self.start
            self.assembler.push('baseline',(.05 if elapsed<3. else 0.,0.),self.time)
            self.assembler.push('final',self.final,self.time)
            self.assembler.push('status',dict(permission=True,fault=False,emergency_stop=False),self.time)
            result=self.assembler.view(self.time);result['actual_actuator_target']=None
            result['target_evidence']='no actuator-target readback; native DiffDrive differs from CyberGear'
            return result
    def advance_reference(self,v,w,dt):
        from gz.msgs10.twist_pb2 import Twist
        if self.closed:raise RuntimeError('Backend closed')
        if not math.isclose(dt,.1):raise ValueError('Fixture control interval must be 100 ms')
        msg=Twist();msg.linear.x=float(v);msg.angular.z=float(w)
        # Allow transport delivery while paused; this is NOT measured controller latency.
        self.cmd.publish(msg);time.sleep(.006);self.final=(v,w);self.step_world(50)
        view=self.view();truth=self.messages['truth'];p=truth.pose.position;q=truth.pose.orientation
        yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
        labels=dict(progress_m=p.x-self.previous_x,lateral_m=p.y,heading_rad=yaw,
                    vibration_proxy=abs(view['features']['accel_z_m_s2']-9.80665));self.previous_x=p.x
        elapsed=self.time-self.start;truncated=elapsed>=4.-.01
        return view,labels,False,truncated,dict(backend=self.kind,labels=labels,
            truth_pose_m_rad=[p.x,p.y,yaw],body_speed_m_s=truth.twist.linear.x,
            applied_target_rad_s=None,final_ros_reference=list(self.final),
            final_reference_evidence='Gazebo native input; no final ROS command chain claimed',
            feedback_wheel_rad_s=[view['features']['wheel_l_rad_s'],view['features']['wheel_r_rad_s']],
            sensor_clock_s=self.time,termination_reason='time_limit' if truncated else None)
    def close(self):
        if self.closed:return
        self.closed=True
        if self.server and self.server.poll() is None:
            os.killpg(self.server.pid,signal.SIGTERM)
            try:self.server.wait(timeout=4)
            except subprocess.TimeoutExpired:os.killpg(self.server.pid,signal.SIGKILL);self.server.wait(timeout=2)
        if self.log:self.log.close()
        if self.previous_partition is None:os.environ.pop('GZ_PARTITION',None)
        else:os.environ['GZ_PARTITION']=self.previous_partition


def fixture_job(root,out,config):
    import numpy as np
    from .residual_workflow import save,emit
    from .residual_experiment import make_environment
    # The actor frame is body-aligned in this standalone fixture.
    config=deepcopy(config);config['imu_yaw_rad']=0.
    backend=GazeboVelocityBackend(config,out);env=make_environment(config,backend);rows=[]
    try:
        obs,_=env.reset(seed=11)
        for i in range(50):
            obs,r,t,tr,info=env.step(np.array([.5,.1],dtype=np.float32))
            rows.append(dict(step=i,reward=r,terminated=t,truncated=tr,**info))
            emit('gazebo-fixture','Gazebo flat trace '+str(i+1),min(1.,(i+1)/40))
            if t or tr:break
        distance=rows[-1]['truth_pose_m_rad'][0]-rows[0]['truth_pose_m_rad'][0]
        if distance<=.01 or not any(abs(x)>0.1 for row in rows for x in row['feedback_wheel_rad_s']):
            raise RuntimeError('No physical wheel/body response in Gazebo fixture')
        result=dict(scope='standalone flat Gazebo integration only; not calibrated Nino/caster/contact model',
            rows=len(rows),truth_forward_displacement_m=distance,source_counts=backend.counts,
            partition=backend.partition,actuator_target_readback=None,hardware_validated=False,
            native_backend='DiffDrive joint velocity; no CyberGear PI/current model',obstacles_tested=False)
        save(out/'gazebo_result.json',result);return result
    finally:
        with (out/'gazebo_trace.jsonl').open('w') as f:
            import json
            for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')
        env.close()
