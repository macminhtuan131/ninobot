"""Real ROS DDS synthetic fixture for the read-only shadow observer."""
import json
import time
import uuid
from .residual_experiment import experiment_contract
from .velocity_backend import VelocityBackend
from nino_control.residual_shadow import create_shadow_node


def fixture_job(root,out,config):
    import rclpy
    from rclpy.context import Context
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu,JointState
    from geometry_msgs.msg import Twist
    from std_msgs.msg import UInt8
    from .residual_workflow import latest,save,emit
    actor=latest(root,'train-td3');prefix='/nino_fixture_'+uuid.uuid4().hex[:8]
    context=Context();context.init(domain_id=119)
    publisher=Node('synthetic_sensors',context=context);observer=None;executor=SingleThreadedExecutor(context=context)
    backend=VelocityBackend(config);backend.reset(seed=73)
    pubs={k:publisher.create_publisher(t,prefix+topic,qos_profile_sensor_data) for k,t,topic in (
        ('imu',Imu,'/imu/data'),('wheel',JointState,'/motor_fb'),('status',UInt8,'/motor_status'),
        ('baseline',Twist,'/cmd_vel_selected'),('final',Twist,'/cmd_vel'))}
    try:
        observer=create_shadow_node(config,actor,prefix,context,out/'ros_trace.jsonl')
        executor.add_node(publisher);executor.add_node(observer)
        end=time.monotonic()+2.
        while time.monotonic()<end:executor.spin_once(timeout_sec=.02)
        start=time.monotonic();last=start;next_pub=start;steps=0
        while time.monotonic()-start<3.:
            now=time.monotonic()
            if now>=next_pub:
                view,_,_,_,_=backend.advance_reference(.05,0.,config['control_interval_s']);steps+=1
                samples=view['source_samples'];stamp=publisher.get_clock().now().to_msg()
                m=Imu();m.header.stamp=stamp;m.header.frame_id='imu_link'
                gx,gy,gz,ax,ay,az=samples['imu']['values']
                m.angular_velocity.x=gx;m.angular_velocity.y=gy;m.angular_velocity.z=gz
                m.linear_acceleration.x=ax;m.linear_acceleration.y=ay;m.linear_acceleration.z=az;pubs['imu'].publish(m)
                w=JointState();w.header.stamp=stamp;w.name=['left_wheel','right_wheel'];w.velocity=samples['wheel']['values'];pubs['wheel'].publish(w)
                s=UInt8();s.data=19;pubs['status'].publish(s)
                for key in ('baseline','final'):
                    c=Twist();c.linear.x=.05;pubs[key].publish(c)
                next_pub=now+.04
            executor.spin_once(timeout_sec=.005)
        good=[row for row in observer.rows if row['status']=='observed' and row['trace']['history_ready']]
        if len(good)<10 or any(n<30 for n in observer.counts.values()) or len(observer.counts)!=5:
            raise RuntimeError('ROS callback/history coverage insufficient: '+str(observer.counts))
        ready=good[-1]['trace']
        if ready['authority']!=0 or any(ready['accepted_policy_delta_wheel_m_s']):raise RuntimeError('Shadow gained authority')
        names=[v.topic_name for v in observer.publishers]
        if set(names)-{prefix+'/nino/residual/shadow_trace','/rosout','/parameter_events'}:
            raise RuntimeError('Unexpected control publisher from shadow: '+str(names))
        result=dict(scope='synthetic ROS DDS integration; not a real robot/shadow session',domain_id=119,prefix=prefix,
            callback_counts=observer.counts,history_ready_rows=len(good),observer_publishers=names,
            hardware_authority=0.,motor_command_publishers=0,abi_sha256=experiment_contract(config)['abi_sha256'])
        save(out/'ros_result.json',result);emit('ros-fixture','ROS callbacks → history → portable actor → diagnostic trace verified',1.)
        return result
    finally:
        backend.close()
        if observer:executor.remove_node(observer);observer.close()
        executor.remove_node(publisher);publisher.destroy_node();executor.shutdown();context.shutdown()
