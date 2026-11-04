"""Real Gazebo factory world + Nino + existing ROS wheel velocity PI.

Private localhost ROS domain / Gazebo partition, never the Pi. Observations
contain IMU, drive feedback and command history; truth/contact are labels only.
No exact snapshot reset claim: every episode starts a fresh owned launch.
"""
from copy import deepcopy
import json
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


def stamp(message):
    return message.header.stamp.sec+message.header.stamp.nanosec*1e-9


class FactoryVelocityBackend:
    residual_contract_id=CONTRACT_ID
    kind='gazebo_nino_factory_velocity_pi'
    calibrated_to_hardware=False

    def __init__(self,config,directory,repository,world):
        self.config=deepcopy(config);self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.repo=Path(repository);self.world=Path(world);self.closed=False;self.launch=None;self.episode=-1
        self.ctx=None;self.executor=None;self.thread=None;self.node=None;self.gz_node=None
        self.lock=threading.RLock();self.messages={};self.counts={};self.raw=[];self.error=None
        self.request=(0.,0.);self.clock=0.;self.iterations=0;self.start_time=0.;self.time=0.
        self.partition='nino_factory_td3_'+uuid.uuid4().hex
        self.environment=dict(os.environ,GZ_PARTITION=self.partition,GZ_IP='127.0.0.1',
            ROS_DOMAIN_ID='129',NINO_ROS_DOMAIN_ID='129',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
        for key in ('FASTRTPS_DEFAULT_PROFILES_FILE','FASTDDS_DEFAULT_PROFILES_FILE'):self.environment.pop(key,None)
        self.assembler=ObservationAssembler(config['nominal_geometry'],config['reference_limits']['max_age_s'],0.)

    def _store(self,key,source,payload):
        with self.lock:
            self.messages[key]=dict(stamp_s=source,values=payload,receipt_monotonic_s=time.monotonic())
            self.counts[key]=self.counts.get(key,0)+1
            self.raw.append(dict(channel=key,**self.messages[key]))

    def _receive(self,key,msg):
        try:
            if key=='imu':
                values=[msg.angular_velocity.x,msg.angular_velocity.y,msg.angular_velocity.z,
                        msg.linear_acceleration.x,msg.linear_acceleration.y,msg.linear_acceleration.z]
                self._store(key,stamp(msg),values)
            elif key=='wheel':
                values=dict(zip(msg.name,msg.velocity))
                self._store(key,stamp(msg),[values[n] for n in self.config['wheel_names']])
            elif key=='truth':
                p,q=msg.pose.pose.position,msg.pose.pose.orientation
                yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                self._store(key,stamp(msg),dict(pose=[p.x,p.y,p.z,yaw],speed=msg.twist.twist.linear.x,
                    speed_norm=math.sqrt(sum(v*v for v in (msg.twist.twist.linear.x,msg.twist.twist.linear.y,msg.twist.twist.linear.z))),
                    yaw_rate=msg.twist.twist.angular.z,roll=math.atan2(2*(q.w*q.x+q.y*q.z),1-2*(q.x*q.x+q.y*q.y)),
                    pitch=math.asin(max(-1.,min(1.,2*(q.w*q.y-q.z*q.x))))))
            elif key=='drive':
                fields=msg.layout.dim[0].label.split(',')
                if len(fields)!=len(msg.data):raise ValueError('Drive diagnostic schema mismatch')
                values=dict(zip(fields,msg.data));self._store(key,values['sim_time_s'],values)
        except Exception as exc:
            with self.lock:self.error=repr(exc)

    def _stats(self,msg):
        with self.lock:
            self.clock=msg.sim_time.sec+msg.sim_time.nsec*1e-9;self.iterations=int(msg.iterations)

    def _contact(self,component,msg):
        if not msg.contact:return
        # Manifolds are instrumentation only, not loaded-contact risk labels.
        rows=[dict(collision1=c.collision1.name,collision2=c.collision2.name,points=len(c.position)) for c in msg.contact]
        self._store('contact_'+component,msg.header.stamp.sec+msg.header.stamp.nsec*1e-9,rows)

    def _start_io(self):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from sensor_msgs.msg import Imu,JointState
        from nav_msgs.msg import Odometry
        from std_msgs.msg import Float64MultiArray
        from geometry_msgs.msg import Twist
        from rcl_interfaces.srv import GetParameters
        from ros_gz_interfaces.srv import ControlWorld
        self.Twist=Twist;self.ctx=Context();rclpy.init(context=self.ctx,domain_id=129)
        self.node=Node('nino_factory_td3_observer',context=self.ctx)
        qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)
        for key,typ,topic in [('imu',Imu,'/imu/data'),('wheel',JointState,'/joint_states'),
                              ('truth',Odometry,'/ground_truth/odom'),('drive',Float64MultiArray,'/nino_drive/diagnostics')]:
            self.node.create_subscription(typ,topic,lambda m,k=key:self._receive(k,m),qos)
        self.publisher=self.node.create_publisher(Twist,'/cmd_vel',10)
        self.node.create_timer(.02,self._publish)
        self.params=self.node.create_client(GetParameters,'/effort_drive/get_parameters')
        self.description=self.node.create_client(GetParameters,'/robot_state_publisher/get_parameters')
        self.ControlWorld=ControlWorld
        self.world_control=self.node.create_client(ControlWorld,'/world/factory_floor_lab/control')
        self.executor=SingleThreadedExecutor(context=self.ctx);self.executor.add_node(self.node)
        self.thread=threading.Thread(target=self.executor.spin,daemon=True);self.thread.start()
        from gz.transport13 import Node as GNode,NodeOptions
        from gz.msgs10.world_stats_pb2 import WorldStatistics
        from gz.msgs10.contacts_pb2 import Contacts
        options=NodeOptions();options.partition=self.partition;self.gz_node=GNode(options)
        self.gz_node.subscribe(WorldStatistics,'/world/factory_floor_lab/stats',self._stats)
        for component in ('left_wheel','right_wheel','caster_left_wheel','caster_right_wheel','caster_bracket_left','caster_bracket_right','chassis'):
            self.gz_node.subscribe(Contacts,'/nino/contact_lab/'+component,lambda m,k=component:self._contact(k,m))

    def _publish(self):
        if self.node is None:return
        msg=self.Twist()
        with self.lock:msg.linear.x,msg.angular.z=self.request
        self.publisher.publish(msg)

    def _control(self,steps):
        """Persistent ROS bridge, one request only. Missing ACK remains unknown.

        A new `gz service` CLI for every chunk can disappear before the reply
        (observed Host unreachable). The bridge and client stay alive here.
        Physics completion is independently required by step_world.
        """
        if not self.world_control.wait_for_service(timeout_sec=5):raise RuntimeError('Missing factory world-control bridge')
        request=self.ControlWorld.Request();request.world_control.pause=True;request.world_control.multi_step=steps
        future=self.world_control.call_async(request);deadline=time.monotonic()+5.
        while not future.done() and time.monotonic()<deadline:self._check();time.sleep(.002)
        if future.done():
            reply=future.result()
            if reply is None or not reply.success:raise RuntimeError('Factory explicitly rejected world-control request')
            return True
        self.world_control.remove_pending_request(future)
        return False

    def _check(self):
        if self.error:raise RuntimeError('Factory observer callback failed: '+self.error)
        if self.launch is not None and self.launch.poll() is not None:raise RuntimeError('Factory launch exited; inspect launch.log')

    def step_world(self,steps):
        with self.lock:before=self.iterations;start=self.clock
        acknowledged=None;completed=False;deadline=time.monotonic()+15.;wall=time.monotonic()
        try:
            acknowledged=self._control(steps)
            while time.monotonic()<deadline:
                self._check()
                with self.lock:
                    if self.iterations>=before+steps:
                        if self.iterations!=before+steps:raise RuntimeError('Factory world overstepped requested physics budget')
                        self.time=self.clock
                        if not math.isclose(self.time-start,steps*.001,abs_tol=1e-7):raise RuntimeError('Factory clock/iteration mismatch')
                        completed=True;return
                time.sleep(.002)
            raise TimeoutError('Factory physics completion timed out; never retry the multi-step request')
        finally:
            if hasattr(self,'episode_dir'):
                with self.lock:after=self.iterations;end=self.clock
                row=dict(steps=steps,before_iterations=before,after_iterations=after,before_sim_s=start,after_sim_s=end,
                    acknowledged=acknowledged,completed=completed,wall_s=time.monotonic()-wall,request_retries=0)
                with (self.episode_dir/'world_control.jsonl').open('a') as stream:stream.write(json.dumps(row,allow_nan=False)+'\n')

    def _wait_feedback(self,target):
        deadline=time.monotonic()+5.
        while time.monotonic()<deadline:
            self._check()
            with self.lock:
                lags={k:target-self.messages.get(k,{}).get('stamp_s',float('-inf')) for k in ('imu','wheel','truth','drive')}
            if all(-1e-8<=v<=.04000001 for v in lags.values()):return lags
            time.sleep(.002)
        raise RuntimeError('Factory action-boundary sensor lags: '+str(lags))

    def _parameter_readback(self,client,names):
        from rcl_interfaces.srv import GetParameters
        if not client.wait_for_service(timeout_sec=5):raise RuntimeError('Missing parameter readback')
        future=client.call_async(GetParameters.Request(names=names));end=time.monotonic()+5
        while not future.done() and time.monotonic()<end:time.sleep(.01)
        if not future.done():raise TimeoutError('Parameter readback timed out')
        return future.result().values

    def reset(self,seed=None):
        if self.episode+1>=int(self.config['backend']['max_episodes']):
            raise RuntimeError('Factory smoke episode budget exhausted; retain failure, no further reset')
        if self.launch is not None:self._stop_episode()
        self.episode+=1;self.episode_dir=self.directory/('episode_'+str(self.episode));self.episode_dir.mkdir()
        self.messages={};self.counts={};self.raw=[];self.error=None;self.request=(0.,0.);self.clock=0.;self.iterations=0
        self.closed=False;self.assembler.reset();self._start_io()
        self.log=(self.episode_dir/'launch.log').open('w')
        args=['ros2','launch',str(self.repo/'src/nino_rl/launch/training_sim.launch.py'),
              'world:='+str(self.world),'world_name:=factory_floor_lab','headless:=true','verbosity:=2',
              'accept_torque:=false','contact_lab:=true','terrain_preview:=false',
              'caster_wheel_damping:=0.001','pi_integrator_profile:=conditional_v1',
              'max_wheel_torque:=4.0','controller_startup_timeout:=300']
        (self.episode_dir/'launch_argv.json').write_text(json.dumps(args,indent=2)+'\n')
        self.launch=subprocess.Popen(args,env=self.environment,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        end=time.monotonic()+330.;last_report=0
        while time.monotonic()<end:
            self._check()
            with self.lock:ready=all(k in self.messages for k in ('imu','wheel','truth','drive')) and self.clock>0
            if ready and self.publisher.get_subscription_count()==1:break
            if time.monotonic()-last_report>10:
                from .residual_workflow import emit
                emit('factory-td3','Factory startup; received '+str(self.counts));last_report=time.monotonic()
            time.sleep(.05)
        else:raise TimeoutError('Factory startup deadline; retain launch.log')
        names=['accept_torque','pi_integrator_profile','wheel_radius','wheel_separation','control_rate',
               'velocity_kp','velocity_ki','max_wheel_torque','max_effort_rate','max_wheel_acceleration']
        values=self._parameter_readback(self.params,names)
        readback={name:({1:value.bool_value,2:value.integer_value,3:value.double_value,4:value.string_value}.get(value.type))
                  for name,value in zip(names,values)}
        (self.episode_dir/'drive_parameters.json').write_text(json.dumps(readback,indent=2)+'\n')
        if values[0].bool_value or values[1].string_value!='conditional_v1':raise ValueError('Wrong factory motor backend mode')
        if not math.isclose(values[2].double_value,.0625) or not math.isclose(values[3].double_value,.34273666):raise ValueError('Factory geometry readback mismatch')
        for key,expected in dict(control_rate=500.,velocity_kp=.3,velocity_ki=.1,max_wheel_torque=4.,max_effort_rate=10.,max_wheel_acceleration=12.).items():
            if readback[key] is None or not math.isclose(readback[key],expected):raise ValueError('Factory drive parameter mismatch: '+key)
        urdf=self._parameter_readback(self.description,['robot_description'])[0].string_value
        (self.episode_dir/'robot.urdf').write_text(urdf)
        if not all(name in urdf for name in ('caster_left_swivel_joint','caster_right_swivel_joint')):raise ValueError('Actual Nino caster model missing')
        if not self._control(0):raise RuntimeError('Factory initial pause ACK missing; no physics request retried')
        time.sleep(.12)
        self.settle()
        self._wait_feedback(self.time);self.start_time=self.time
        self.origin=deepcopy(self.messages['truth']['values']['pose']);self.previous_x=self.origin[0]
        self.flush_raw();return self.view(),dict(backend=self.kind,world=str(self.world),partition=self.partition,
            ros_domain=129,seed=seed,reset='fresh_owned_launch_not_snapshot',calibrated_to_hardware=False)

    def settle(self):
        """Require 0.5 s continuous quiet under zero; cap setup at 5 sim s.

        These are simulation setup proposals, not accepted hardware limits.
        Truth is a reset/evaluation oracle only, never a policy feature.
        """
        quiet=0.;rows=[]
        try:
            for i in range(50):
                self.step_world(50);self.step_world(50);self._wait_feedback(self.time)
                with self.lock:
                    truth=deepcopy(self.messages['truth']['values']);wheel=list(self.messages['wheel']['values'])
                valid=(truth['speed_norm']<.01 and abs(truth['yaw_rate'])<.05 and max(map(abs,wheel))<.15
                       and max(abs(truth['roll']),abs(truth['pitch']))<.2)
                quiet=quiet+.1 if valid else 0.
                rows.append(dict(sim_time_s=self.time,speed_norm_m_s=truth['speed_norm'],yaw_rate_rad_s=truth['yaw_rate'],
                    wheel_rad_s=wheel,quiet=valid,continuous_quiet_s=quiet))
                if quiet>=.5-1e-8:return
            raise RuntimeError('Factory zero-settling gate failed within 5 simulation seconds')
        finally:
            (self.episode_dir/'settling.json').write_text(json.dumps(dict(rows=rows,passed=quiet>=.5-1e-8),indent=2)+'\n')

    def view(self):
        with self.lock:m=deepcopy(self.messages);now=self.time
        for key,channel in [('imu','imu'),('wheel','wheel')]:
            row=m[key];self.assembler.push(channel,row['values'],row['stamp_s'],row['stamp_s'])
        drive=m['drive']['values'];ds=m['drive']['stamp_s']
        self.assembler.push('final',[drive['executed_linear_m_s'],drive['executed_yaw_rad_s']],ds,ds,'base_footprint')
        elapsed=now-self.start_time
        command_end=self.config['backend'].get('command_until_s',float('inf'))
        base=(0. if elapsed<.5 or elapsed>=command_end-1e-8 else self.config['backend']['cruise_m_s'],0.)
        self.assembler.push('baseline',base,now,None,'base_footprint')
        self.assembler.push('status',dict(permission=bool(drive['have_wheel_state']),fault=False,emergency_stop=False),ds,ds)
        view=self.assembler.view(now);view['clock']='Gazebo simulation clock; callback receipt_monotonic_s retained in raw'
        view['freshness_scope']='source age in simulation clock; not hardware transport latency'
        view['actual_actuator_target']=[drive['left_target_rad_s'],drive['right_target_rad_s']]
        view['target_evidence']='existing effort_drive reported post-ramp wheel targets, not measured motor torque'
        return view

    def advance_reference(self,v,w,dt):
        if self.closed:raise RuntimeError('Factory backend closed')
        if not math.isclose(dt,.1):raise ValueError('Factory control interval fixed at 100 ms')
        with self.lock:self.request=(float(v),float(w))
        self._publish();time.sleep(.025)
        # Preserve 1 ms physics, allow ROS PI callbacks between 50 ms chunks.
        for _ in range(2):self.step_world(50);self._wait_feedback(self.time)
        view=self.view();self.flush_raw()
        with self.lock:truth=deepcopy(self.messages['truth']['values']);drive=deepcopy(self.messages['drive']['values'])
        if max(abs(drive['requested_linear_m_s']-v),abs(drive['requested_yaw_rad_s']-w))>1e-6:
            raise RuntimeError('Factory PI did not acknowledge requested reference at action boundary')
        p=truth['pose'];lateral=p[1]-self.origin[1];yaw=p[3]-self.origin[3]
        labels=dict(progress_m=p[0]-self.previous_x,lateral_m=lateral,heading_rad=yaw,
                    vibration_proxy=abs(view['features']['accel_z_m_s2']-9.80665))
        self.previous_x=p[0];elapsed=self.time-self.start_time
        failed=abs(truth['roll'])>.7 or abs(truth['pitch'])>.7 or p[2]<-.15 or abs(lateral)>1.5
        truncated=elapsed>=self.config['backend']['horizon_s']-1e-8 and not failed
        return view,labels,failed,truncated,dict(backend=self.kind,labels=labels,
            truth_pose_m_rad=[p[0],p[1],p[3]],body_speed_m_s=truth['speed'],body_yaw_rad_s=truth['yaw_rate'],
            applied_target_rad_s=view['actual_actuator_target'],final_ros_reference=[drive['executed_linear_m_s'],drive['executed_yaw_rad_s']],
            final_reference_evidence='effort_drive diagnostics; simulated PI output torque is not hardware torque',
            feedback_wheel_rad_s=[view['features']['wheel_l_rad_s'],view['features']['wheel_r_rad_s']],
            drive_diagnostics=drive,sensor_clock_s=self.time,source_lags_s=self._wait_feedback(self.time),
            termination_reason='physical_envelope_failure' if failed else 'time_limit' if truncated else None,
            world=self.config['backend'].get('scenario_id','factory_floor_mixed'),route='E1 straight reference',calibrated_to_hardware=False)

    def flush_raw(self):
        with self.lock:rows=self.raw;self.raw=[]
        if rows:
            with (self.episode_dir/'raw_samples.jsonl').open('a') as stream:
                for row in rows:stream.write(json.dumps(row,allow_nan=False)+'\n')

    def _stop_episode(self):
        with self.lock:self.request=(0.,0.)
        try:
            self._publish();time.sleep(.05)
            if self.launch and self.launch.poll() is None:
                os.killpg(self.launch.pid,signal.SIGINT)
                try:self.launch.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.launch.pid,signal.SIGTERM)
                    try:self.launch.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(self.launch.pid,signal.SIGKILL);self.launch.wait(timeout=2)
        finally:
            self.flush_raw()
            if self.executor:self.executor.shutdown(timeout_sec=2)
            if self.thread:self.thread.join(timeout=2)
            if self.node:self.node.destroy_node()
            if self.ctx and self.ctx.ok():self.ctx.shutdown()
            self.gz_node=None;self.node=None;self.ctx=None;self.executor=None;self.thread=None;self.launch=None
            if getattr(self,'log',None):self.log.close()

    def close(self):
        if self.closed:return
        self.closed=True;self._stop_episode()
