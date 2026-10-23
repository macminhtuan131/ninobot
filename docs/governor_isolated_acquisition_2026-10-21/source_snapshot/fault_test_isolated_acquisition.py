"""Synthetic ROS fault comparison: no Gazebo, robot driver or motion publisher."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src/nino_rl"))
from nino_rl.acquisition_frames import read_frames
from nino_rl.isolated_acquisition import decode,compose_view
from nino_rl.governor_logger import finite_json

FIXTURE='''import json,sys,time
from pathlib import Path
import nino_rl.governor_logger as logger
from ros_gz_interfaces.msg import Contacts
original=logger.message_to_ordereddict
fired=False
def convert(msg):
    global fired
    if isinstance(msg,Contacts) and msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9>=100.2 and not fired:
        fired=True
        begin=time.monotonic_ns()
        previous=sys.getswitchinterval()
        try:
            sys.setswitchinterval(.5)
            until=time.monotonic()+.25
            while time.monotonic()<until:pass
        finally:sys.setswitchinterval(previous)
        Path(FAULT_PATH).write_text(json.dumps(dict(kind="synthetic_contact_conversion_busy_stall",
            begin_monotonic_ns=begin,end_monotonic_ns=time.monotonic_ns())))
    return original(msg)
logger.message_to_ordereddict=convert
logger.main()
'''


def wait_for(predicate,children,seconds=20):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if any(p.poll() is not None for p in children):raise RuntimeError("Fixture child exited unexpectedly")
        if predicate():return
        time.sleep(.01)
    raise TimeoutError("Synthetic fixture readiness deadline")


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT);time.sleep(.001)
        if process.poll() is None:process.send_signal(signal.SIGINT)
    return process.wait(timeout=20)


def main(output):
    if os.environ.get("ROS_DOMAIN_ID")!="197" or os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE")!="LOCALHOST":
        raise ValueError("Fixture requires isolated localhost ROS domain197")
    output.mkdir(parents=True,exist_ok=False)
    fixture=output/"contact_fixture.py"
    fixture.write_text(FIXTURE.replace("FAULT_PATH",repr(str(output/"injected_stall.json"))))
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.serialization import serialize_message
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from sensor_msgs.msg import JointState
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    from ros_gz_interfaces.msg import Contacts,Contact
    logs=[(output/name).open("w") for name in ("contact.log","acquisition.log")]
    processes=[];node=None;result=None
    references={"/joint_states":[],"/ground_truth/odom":[]}
    def semantic_hash(message):
        data=finite_json(message_to_ordereddict(message))
        return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    try:
        processes.append(subprocess.Popen([sys.executable,str(fixture),"--ros-args","-p","use_sim_time:=false",
            "-p",f"output_directory:={output/'contact'}"],cwd=ROOT,stdout=logs[0],stderr=subprocess.STDOUT))
        processes.append(subprocess.Popen([sys.executable,"-m","nino_rl.isolated_acquisition",
            "--output",str(output/"capture")],cwd=ROOT,stdout=logs[1],stderr=subprocess.STDOUT))
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node=rclpy.create_node("isolated_acquisition_fault_fixture")
        joint=node.create_publisher(JointState,"/joint_states",qos_profile_sensor_data)
        truth=node.create_publisher(Odometry,"/ground_truth/odom",qos_profile_sensor_data)
        contact=node.create_publisher(Contacts,"/nino/contact_lab/right_wheel",qos_profile_sensor_data)
        epoch=node.create_publisher(String,"/nino/governor/episode",10)
        wait_for(lambda:joint.get_subscription_count()>=2 and truth.get_subscription_count()>=2
            and contact.get_subscription_count()>=1 and epoch.get_subscription_count()>=2,processes)
        marker=dict(event="reset",run_id="isolated-fixture",attempt=1,time_s=100.)
        epoch.publish(String(data=json.dumps(marker)))
        ready=output/"capture/epoch_ready.json"
        wait_for(lambda:ready.exists() and json.loads(ready.read_text())["marker"]["event"]=="reset",processes)
        time.sleep(.1)
        begin=time.monotonic()
        for i in range(600):
            ns=100_000_000_000+i*2_000_000
            a=JointState();a.header.stamp.sec=ns//1_000_000_000;a.header.stamp.nanosec=ns%1_000_000_000
            a.header.frame_id="fixture";a.name=["left_wheel_joint","right_wheel_joint"]
            a.position=[float(i),0.];a.velocity=[6.4,6.4];a.effort=[0.,0.]
            joint.publish(a)
            references["/joint_states"].append(dict(source_ns=ns,all_fields_sha256=semantic_hash(a)))
            if i%10==0:
                b=Odometry();b.header=a.header;b.child_frame_id="base_link"
                b.pose.pose.position.x=float(i//10);b.pose.pose.orientation.w=1.;b.twist.twist.linear.x=.4
                truth.publish(b)
                references["/ground_truth/odom"].append(dict(source_ns=ns,all_fields_sha256=semantic_hash(b)))
            if i%5==0:
                c=Contacts();c.header=a.header;one=Contact()
                one.collision1.name="cable_bumps::fixture";one.collision2.name="wheel";one.depths=[.001]
                c.contacts=[one];contact.publish(c)
            time.sleep(max(0.,begin+(i+1)*.002-time.monotonic()))
        marker=dict(marker,event="end",time_s=101.2)
        epoch.publish(String(data=json.dumps(marker)))
        wait_for(lambda:ready.exists() and json.loads(ready.read_text())["marker"]["event"]=="end"
                 and (output/"injected_stall.json").exists(),processes)
        time.sleep(.2)
        exits=[stop(p) for p in processes]
        if exits!=[0,0]:raise ValueError(f"Unclean fixture process exits: {exits}")
        frames=list(read_frames(output/"capture"))
        types={"/joint_states":JointState,"/ground_truth/odom":Odometry}
        observed={name:[dict(source_ns=f["source_ns"],all_fields_sha256=semantic_hash(deserialize_message(f["payload"],types[name])))
            for f in frames if f["topic"]==name] for name in references}
        exact={name:observed[name]==references[name] for name in references}
        raw=list((output/"contact").glob("*/samples.jsonl"))
        if len(raw)!=1:raise ValueError("Ambiguous baseline logger output")
        base={name:[] for name in references}
        for line in raw[0].open():
            row=json.loads(line)
            if row["topic"] in base:
                s=row["data"]["header"]["stamp"]
                base[row["topic"]].append(s["sec"]*1_000_000_000+s["nanosec"])
        decoded=decode(output/"capture",output/"decoded","isolated-fixture",1,100_000_000_000,101_200_000_000)
        view=compose_view(raw[0].parent,output/"capture",output/"composed_view",
                          "isolated-fixture",1,100_000_000_000,101_200_000_000)
        result=dict(synthetic_ROS_only=True,Gazebo_episodes=0,hardware_connected=False,motor_commands=0,
            process_pids=[p.pid for p in processes],separate_processes=processes[0].pid!=processes[1].pid,
            requested_joint_hz=500,requested_GT_hz=50,
            published_counts={name:len(rows) for name,rows in references.items()},
            captured_counts={name:len(rows) for name,rows in observed.items()},
            baseline_counts={name:len(rows) for name,rows in base.items()},
            exact_order_timestamp_all_fields=exact,decode_validation=decoded,
            composed_view_complete=view["complete"],
            composed_view_counts=view["isolated_topic_counts"],
            payload_comparison="All decoded ROS fields and exact source stamps; CDR padding bytes are not a semantic equality criterion. CRC+SHA still verify stored frames bit-for-bit.",
            injected_stall=json.loads((output/"injected_stall.json").read_text()),
            process_exit_codes=exits,
            qualification="Known synthetic contact/GIL stall, original QoS depth5. Does not prove capture cannot lose samples under other CPU/disk/DDS loads or validate Gazebo coverage.")
        (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
        (output/"reference_payloads.json").write_text(json.dumps(references,indent=2)+"\n")
        if not all(exact.values()):raise AssertionError("Isolated capture lost/reordered/changed fixture payloads")
        if len(base["/joint_states"])>=600:raise AssertionError("Shared-executor baseline did not exhibit injected loss")
        print(json.dumps(result,indent=2))
    finally:
        for process in processes:
            if process.poll() is None:
                try:stop(process)
                except BaseException:process.kill();process.wait(timeout=5)
        if node is not None:node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
        for stream in logs:stream.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    main(parser.parse_args().output.resolve())
