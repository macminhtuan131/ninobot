#!/usr/bin/env python3
"""Two real ROS observer processes, fake sensors, no Gazebo or command publisher."""
import argparse
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control"),str(ROOT/"src/nino_rl/scripts")]
from nino_rl.acquisition_contract import create_session,wait_pair,episode_publisher,finalize_view,verify_view
from nino_rl.acquisition_frames import atomic_json,read_frames


def run(output):
    if os.environ.get("ROS_DOMAIN_ID")!="198" or os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE")!="LOCALHOST":
        raise ValueError("Software fixture requires isolated localhost domain198")
    output.mkdir(parents=True,exist_ok=False)
    parent=ROOT/"docs/governor_corrected_logger_cadence_2026-10-21/inputs"
    contract=output/"fixture_protocol.json"
    atomic_json(contract,dict(fixture_only=True,simulation_episodes=0))
    config=parent/"full.yaml";world=parent/"scenario.sdf"
    session=create_session(output/"session",contract,config,world,dict(seed=77600,profile="full"))
    env=os.environ.copy();env["NINO_ACQUISITION_SESSION"]=str(session)
    env["PYTHONPATH"]=os.pathsep.join([str(ROOT/"src/nino_rl"),str(ROOT/"src/nino_control"),env.get("PYTHONPATH","")])
    fixture=output/"injected_primary.py"
    fixture.write_text('''import time,sys
from pathlib import Path
import nino_rl.governor_logger as logger
from ros_gz_interfaces.msg import Contacts
old=logger.message_to_ordereddict
fired=False
def convert(message):
    global fired
    if isinstance(message,Contacts) and not fired:
        fired=True
        begin=time.monotonic_ns()
        old_interval=sys.getswitchinterval()
        try:
            sys.setswitchinterval(.5)
            until=time.monotonic()+.2
            while time.monotonic()<until:pass
        finally:sys.setswitchinterval(old_interval)
        Path(INJECTION_PATH).write_text(str(time.monotonic_ns()-begin))
    return old(message)
logger.message_to_ordereddict=convert
logger.main()
'''.replace("INJECTION_PATH",repr(str(output/"injected_stall_ns.txt"))))
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
    from rosidl_runtime_py.convert import message_to_ordereddict
    from sensor_msgs.msg import JointState,Imu
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    from ros_gz_interfaces.msg import Contacts
    from nino_rl.governor_logger import finite_json
    logs=[(output/name).open("w") for name in ("primary.log","joint_gt.log")]
    children=[];node=None;answer=None
    try:
        children.append(subprocess.Popen([sys.executable,str(fixture),"--ros-args",
            "-p",f"output_directory:={output/'contact'}","-p",f"config_file:={config}",
            "-p",f"world_override:={world}","-p","caster_wheel_damping:=0.001"],
            env=env,stdout=logs[0],stderr=subprocess.STDOUT))
        children.append(subprocess.Popen([sys.executable,"-m","nino_rl.isolated_acquisition",
            "--output",str(output/"joint_gt")],env=env,stdout=logs[1],stderr=subprocess.STDOUT))
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node=rclpy.create_node("acquisition_integration_software_fixture")
        joints=node.create_publisher(JointState,"/joint_states",qos_profile_sensor_data)
        ground=node.create_publisher(Odometry,"/ground_truth/odom",qos_profile_sensor_data)
        imu=node.create_publisher(Imu,"/imu/data",qos_profile_sensor_data)
        contacts=node.create_publisher(Contacts,"/nino/contact_lab/right_wheel",qos_profile_sensor_data)
        description=node.create_publisher(String,"/robot_description",QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        marker=node.create_publisher(String,"/nino/governor/episode",10)
        description.publish(String(data=(parent/"reference_robot.urdf").read_text()))
        def alive():return all(p.poll() is None for p in children)
        def publish(emit_ground=True,emit_imu=True):
            stamp=node.get_clock().now().to_msg()
            a=JointState();a.header.stamp=stamp;a.name=["left_wheel_joint","right_wheel_joint"]
            a.position=[0.,0.];a.velocity=[6.4,6.4];a.effort=[.1,.2]
            b=Odometry();b.header.stamp=stamp;b.pose.pose.orientation.w=1.;b.twist.twist.linear.x=.4
            c=Imu();c.header.stamp=stamp;c.orientation.w=1.;c.linear_acceleration.z=9.80665
            joints.publish(a)
            if emit_ground:ground.publish(b)
            if emit_imu:imu.publish(c)
            return a,b
        def pump():publish();rclpy.spin_once(node,timeout_sec=.01)
        pair=wait_pair(session,alive=alive,pump=pump)
        atomic_json(session.parent/"readiness_pair.json",pair)
        saved_env=os.environ.get("NINO_ACQUISITION_SESSION")
        os.environ["NINO_ACQUISITION_SESSION"]=str(session)
        wrapper=episode_publisher(marker,node)
        now=node.get_clock().now().nanoseconds*1e-9
        import yaml
        reset=dict(event="reset",run_id="software-integration",attempt=1,seed=77600,
                   time_s=now,settings=yaml.safe_load(config.read_text())["governor"])
        wrapper.publish(String(data=json.dumps(reset)))
        expected=[]
        for i in range(160):
            a,b=publish(emit_ground=i%10==0,emit_imu=i%5==0)
            expected.append(("/joint_states",a))
            if i%10==0:expected.append(("/ground_truth/odom",b))
            if i==20:
                c=Contacts();c.header=a.header;contacts.publish(c)
            time.sleep(.002)
        time.sleep(.15)
        terminal=dict(event="end",run_id=reset["run_id"],attempt=1,
                      time_s=node.get_clock().now().nanoseconds*1e-9,metrics=dict(termination="timeout"))
        # Native row is persisted before awaiting end ACK, as in the runner.
        wrapper.publish(String(data=json.dumps(terminal)))
        evaluation=output/"evaluation";(evaluation/"episode-001").mkdir(parents=True)
        with (evaluation/"episode-001/control_trace.csv").open("w") as stream:
            writer=csv.DictWriter(stream,fieldnames=["governor_run_id","governor_input_time_s","sim_time_s"])
            writer.writeheader();writer.writerow(dict(governor_run_id=reset["run_id"],
                governor_input_time_s=reset["time_s"],sim_time_s=terminal["time_s"]))
        atomic_json(evaluation/"native_outcome_fixture.json",dict(physical_success=False,termination="timeout"))
        wait_pair(session,marker=terminal,alive=alive)
        if saved_env is None:os.environ.pop("NINO_ACQUISITION_SESSION",None)
        else:os.environ["NINO_ACQUISITION_SESSION"]=saved_env
        for p in children:p.send_signal(signal.SIGINT)
        codes=[p.wait(timeout=20) for p in children]
        assert codes==[0,0],codes
        primary=next((output/"contact").glob("*/metadata.json")).parent
        view=finalize_view(output,evaluation,primary,session)
        admission=verify_view(view)
        from rclpy.serialization import deserialize_message
        frames=list(read_frames(output/"joint_gt"))
        available={}
        for f in frames:
            typ=JointState if f["topic"]=="/joint_states" else Odometry if f["topic"]=="/ground_truth/odom" else None
            if typ:
                message=deserialize_message(f["payload"],typ)
                available[f["topic"],f["source_ns"]]=finite_json(message_to_ordereddict(message))
        counts={topic:dict(sent=0,received=0,missing_source_ns=[]) for topic in ("/joint_states","/ground_truth/odom")}
        for topic,msg in expected:
            ns=msg.header.stamp.sec*1000000000+msg.header.stamp.nanosec
            counts[topic]["sent"]+=1
            if (topic,ns) not in available:
                counts[topic]["missing_source_ns"].append(ns)
            else:
                counts[topic]["received"]+=1
                assert available[topic,ns]==finite_json(message_to_ordereddict(msg))
        atomic_json(output/"known_publisher_counts.json",counts)
        # This fixture knows each publisher message. Counts are NOT substituted
        # for original time-window coverage in the experiment collector.
        assert all(c["received"]>=.98*c["sent"] for c in counts.values()),counts
        assert (output/"injected_stall_ns.txt").exists()
        answer=dict(passed=True,software_fixture_only=True,simulation_episodes=0,
            known_publisher_counts=counts,received_fields_and_stamps_equal=True,
            both_readiness_reset_end_close=True,view_admitted=True,process_exit_codes=codes,
            injected_contact_stall_ns=int((output/"injected_stall_ns.txt").read_text()),
            native_failure_retained=json.loads((evaluation/"native_outcome_fixture.json").read_text()),
            isolated_counts=admission["isolated_topic_counts"],
            qualification="Injected software fault only; not Gazebo coverage, cadence authority or hardware proof")
        atomic_json(output/"result.json",answer)
        return answer
    finally:
        for p in children:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:p.wait(timeout=20)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        for stream in logs:stream.close()
        if node is not None:node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.output.resolve()),indent=2))
