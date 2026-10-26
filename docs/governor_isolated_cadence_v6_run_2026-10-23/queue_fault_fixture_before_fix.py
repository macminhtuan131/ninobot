#!/usr/bin/env python3
"""Synthetic ROS receipt-buffer fault test; no Gazebo/control publishers.

Pause recorder servicing while a known publisher emits 30 source samples.
Compare the v6 depth5 reader with a test-only depth100 candidate. This is
not a proof that queue overflow alone caused the recorded Gazebo gap.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

if os.environ.get('ROS_DOMAIN_ID')!='199' or os.environ.get('ROS_AUTOMATIC_DISCOVERY_RANGE')!='LOCALHOST':
    raise RuntimeError('Fixture requires isolated ROS domain199, localhost only')
if os.environ.get('NINO_ACQUISITION_SESSION'):
    raise RuntimeError('No experimental session allowed in a synthetic fixture')
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/nino_rl'),str(ROOT/'src/nino_control')]
import rclpy
from rclpy.qos import QoSProfile,qos_profile_sensor_data
from sensor_msgs.msg import JointState
from nav_msgs.msg import Odometry
from nino_rl import isolated_acquisition as recorder
from nino_rl.acquisition_frames import read_frames,atomic_json


def profile(depth):
    s=qos_profile_sensor_data
    return QoSProfile(depth=depth,history=s.history,reliability=s.reliability,durability=s.durability,
        lifespan=s.lifespan,deadline=s.deadline,liveliness=s.liveliness,
        liveliness_lease_duration=s.liveliness_lease_duration,
        avoid_ros_namespace_conventions=s.avoid_ros_namespace_conventions)


def run(depth,output):
    original=recorder.qos_profile_sensor_data
    candidate=profile(depth)
    recorder.qos_profile_sensor_data=candidate  # Test-only injection, no source mutation.
    rclpy.init()
    node=publisher=None
    try:
        node=recorder.IsolatedAcquisition(output)
        publisher=rclpy.create_node('known_receipt_fixture_publisher')
        writer_qos=profile(100)
        joint=publisher.create_publisher(JointState,'/joint_states',writer_qos)
        ground=publisher.create_publisher(Odometry,'/ground_truth/odom',writer_qos)
        deadline=time.monotonic()+10.
        while joint.get_subscription_count()!=1 or ground.get_subscription_count()!=1:
            if joint.get_subscription_count()>1 or ground.get_subscription_count()>1:
                raise RuntimeError('Unexpected consumer in isolated fixture domain')
            if time.monotonic()>deadline:raise TimeoutError('Fixture discovery failed')
            rclpy.spin_once(node,timeout_sec=.01)
        def publish(i):
            ns=1_000_000_000+i*2_000_000
            msg=JointState();msg.header.stamp.sec=ns//1_000_000_000;msg.header.stamp.nanosec=ns%1_000_000_000
            msg.name=['left_wheel_joint','right_wheel_joint'];msg.velocity=[6.4,6.4]
            msg.position=[i*.0128,i*.0128];msg.effort=[0.,0.]
            odom=Odometry();odom.header=msg.header;odom.pose.pose.orientation.w=1.;odom.twist.twist.linear.x=.4
            joint.publish(msg);ground.publish(odom)
        def drain(seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.002)
        for i in range(10):publish(i);drain(.008)
        # Deliberate consumer-service outage only. Publishing and DDS receive
        # continue; source stamps and the number of sends stay identical.
        begin=time.monotonic()
        for i in range(10,40):publish(i);time.sleep(.002)
        time.sleep(.02)
        pause_s=time.monotonic()-begin
        drain(.2)
        for i in range(40,50):publish(i);drain(.008)
        drain(.2)
        node.writer.close()
        frames=list(read_frames(output))
        counts={topic:sorted(f['source_ns'] for f in frames if f['topic']==topic)
                for topic in ('/joint_states','/ground_truth/odom')}
        expected={1_000_000_000+i*2_000_000 for i in range(50)}
        return dict(reader_depth=depth,writer_depth=100,consumer_pause_wall_s=pause_s,
            sent_per_topic=50,received={topic:len(values) for topic,values in counts.items()},
            missing_source_stamps_ns={topic:sorted(expected-set(values)) for topic,values in counts.items()},
            maximum_source_gap_ms={topic:max((b-a)*1e-6 for a,b in zip(values,values[1:])) for topic,values in counts.items()},
            frame_integrity_passed=True)
    finally:
        if node is not None:
            node.writer.close();node.destroy_node()
        if publisher is not None:publisher.destroy_node()
        rclpy.shutdown();recorder.qos_profile_sensor_data=original


def main():
    out=Path(__file__).resolve().parent
    work=Path(tempfile.mkdtemp(prefix='nino_depth_fault_fixture_'))
    rows=[run(depth,work/f'depth_{depth}') for depth in (5,100)]
    result=dict(mode='synthetic_ROS_reader_queue_fault_fixture',simulation_attempts=0,
        motor_publishers=False,domain=199,rows=rows,fixture_directory=str(work),
        candidate_prevents_fixture_loss=all(n==50 for n in rows[1]['received'].values()),
        depth5_loses_in_fixture=any(n<50 for n in rows[0]['received'].values()),
        qualification='Supports queue capacity as a possible mechanism under a forced consumer pause; not unique attribution of the Gazebo loss or a production coverage guarantee.',
        fixture_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    atomic_json(out/'queue_fault_fixture.json',result)
    print(json.dumps(result,indent=2))
    assert result['depth5_loses_in_fixture'] and result['candidate_prevents_fixture_loss']


if __name__=='__main__':main()
