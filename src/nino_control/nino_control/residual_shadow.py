"""Read-only residual inference observer. Creates diagnostic publishers ONLY.

This executable cannot enable a motor or publish a velocity reference. Firmware
status bits describe source variables, not verified RC/actuator permission.
"""
import argparse
import json
import math
from pathlib import Path
import time
from .residual_actor import PortableActor
from .residual_pipeline import ObservationAssembler, ResidualPipeline
from .residual_velocity import actor_contract


def joint_pair(message,names):
    if len(set(message.name))!=len(message.name):raise ValueError('Duplicate wheel names')
    if len(message.velocity)!=len(message.name):raise ValueError('Wheel velocity/name length mismatch')
    return tuple(float(message.velocity[message.name.index(name)]) for name in names)


def create_shadow_node(config, actor_folder=None, prefix='', context=None, output=None):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu,JointState
    from geometry_msgs.msg import Twist
    from std_msgs.msg import UInt8,String
    class Shadow(Node):
        def __init__(self):
            super().__init__('nino_residual_shadow',context=context)
            self.pipeline=ResidualPipeline(config)
            self.assembler=ObservationAssembler(config['nominal_geometry'],config['reference_limits']['max_age_s'],config.get('imu_yaw_rad',0.))
            self.actor=None;self.rows=[];self.counts={};self.blocked=None;self.last_tick=None
            self.output=Path(output).open('w') if output else None
            if actor_folder:
                contract=json.loads((Path(actor_folder)/'contract.json').read_text())
                # Match all actor-defining settings; the observer never grants authority.
                abi=actor_contract(config)
                if contract.get('abi_sha256')!=abi['abi_sha256']:raise ValueError('Shadow actor ABI/configuration mismatch')
                for key in ('nominal_geometry','reference_limits','control_interval_s'):
                    if abi[key]!=config[key]:raise ValueError('Shadow/actor configuration mismatch: '+key)
                if abi['history_frames']!=config['actor']['history_frames'] or abi.get('imu_yaw_rad',0.)!=config.get('imu_yaw_rad',0.):
                    raise ValueError('Shadow history/mounting mismatch')
                self.actor=PortableActor(actor_folder,abi['abi_sha256'])
            defaults=dict(imu='/imu/data',wheel='/motor_fb',status='/motor_status',baseline='/cmd_vel_selected',final='/cmd_vel',trace='/nino/residual/shadow_trace')
            defaults.update(config.get('topics',{}));self.topics={k:prefix+v for k,v in defaults.items()}
            self.publisher=self.create_publisher(String,self.topics['trace'],20)
            self.subs=[]
            def callback(channel,extract,stamped=False,frame=None):
                def receive(msg):
                    try:
                        if channel=='imu' and config.get('imu_frame') and msg.header.frame_id!=config['imu_frame']:
                            raise ValueError('Unexpected raw IMU frame: '+msg.header.frame_id)
                        source=(msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9) if stamped else None
                        if self.assembler.push(channel,extract(msg),time.monotonic(),source,
                                               getattr(getattr(msg,'header',None),'frame_id',frame)):
                            self.counts[channel]=self.counts.get(channel,0)+1
                    except (ValueError,TypeError,IndexError) as exc:self.blocked=str(exc)
                return receive
            def status(msg):
                v=int(msg.data)
                return dict(permission=bool(v&16) and v&3==3 and not bool(v&76),
                            fault=bool(v&76),emergency_stop=False)
            for channel,typ,extract,stamped in (
                ('imu',Imu,lambda m:(m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z,m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z),True),
                ('wheel',JointState,lambda m:joint_pair(m,config.get('wheel_names',['left_wheel','right_wheel'])),True),
                ('baseline',Twist,lambda m:(m.linear.x,m.angular.z),False),
                ('final',Twist,lambda m:(m.linear.x,m.angular.z),False),('status',UInt8,status,False)):
                self.subs.append(self.create_subscription(typ,self.topics[channel],callback(channel,extract,stamped),qos_profile_sensor_data))
            self.timer=self.create_timer(config['control_interval_s'],self.tick)
        def tick(self):
            now=time.monotonic();dt=now-self.last_tick if self.last_tick is not None else config['control_interval_s']
            self.last_tick=now
            try:
                if self.blocked:raise ValueError(self.blocked)
                view=self.assembler.view(now);obs=self.pipeline.observe(view)
                proposal=self.actor(obs) if self.actor else (0.,0.)
                trace=self.pipeline.project(proposal,dt,0.)
                record=dict(status='observed',scope='SHADOW_ONLY',hardware_authority=0.,
                    effective_motor_permission='unknown; decoded source status is not RC/actuator readback',
                    inference_actor=self.actor.metadata if self.actor else None,trace=trace,receipt_monotonic_s=now)
            except (ValueError,TypeError,OverflowError) as exc:
                # Source reversals/gaps do not silently refill a control epoch.
                self.pipeline.reset()
                record=dict(status='blocked',error=str(exc),hardware_authority=0.,receipt_monotonic_s=now)
            self.rows.append(record)
            if len(self.rows)>5000:self.rows.pop(0)
            msg=String();msg.data=json.dumps(record,allow_nan=False);self.publisher.publish(msg)
            if self.output:self.output.write(msg.data+'\n');self.output.flush()
        def close(self):
            self.timer.cancel()
            if self.output:self.output.close();self.output=None
            self.destroy_node()
    return Shadow()


def main(argv=None):
    import yaml
    import rclpy
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--actor',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=float,default=60.)
    a=p.parse_args(argv)
    if not math.isfinite(a.duration) or not 0<a.duration<=300:raise ValueError('Explicit bounded shadow duration required (0..300 s)')
    if a.output.exists():raise ValueError('Retain existing trace; choose a new output')
    a.output.parent.mkdir(parents=True,exist_ok=True);config=yaml.safe_load(a.config.read_text())
    rclpy.init();node=None
    try:
        node=create_shadow_node(config,a.actor,output=a.output);end=time.monotonic()+a.duration
        while rclpy.ok() and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.1)
    except KeyboardInterrupt:pass
    finally:
        if node:node.close()
        rclpy.shutdown()


if __name__=='__main__':main()
