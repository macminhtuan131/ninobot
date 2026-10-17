"""Integration: synthetic telemetry in a localhost domain; no motor commands."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

pytest.importorskip("rclpy")
from nino_pi import state_monitor


def test_live_monitor_and_native_recording(tmp_path):
    env=dict(os.environ,ROS_DOMAIN_ID="224",ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",ROS_LOCALHOST_ONLY="1")
    ready=tmp_path/"ready"
    fixture=r'''
import sys,time
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu,JointState
from std_msgs.msg import Float64MultiArray,MultiArrayDimension,Float32
rclpy.init(args=[])
node=Node('nino_monitor_telemetry_fixture')
imu=node.create_publisher(Imu,'/imu/data',qos_profile_sensor_data)
joints=node.create_publisher(JointState,'/joint_states',qos_profile_sensor_data)
drive=node.create_publisher(Float64MultiArray,'/nino_drive/diagnostics',qos_profile_sensor_data)
current=node.create_publisher(Float32,'/test_motor/current',qos_profile_sensor_data)
Path(sys.argv[1]).write_text('ready')
end=time.monotonic()+20
try:
    while time.monotonic()<end:
        msg=Imu(); msg.header.stamp=node.get_clock().now().to_msg(); msg.header.frame_id='imu_link'
        msg.orientation.w=1.; msg.linear_acceleration.z=9.81; imu.publish(msg)
        msg=JointState(); msg.header.stamp=node.get_clock().now().to_msg(); msg.name=['left','right']; msg.velocity=[1.,2.]; joints.publish(msg)
        msg=Float64MultiArray(); msg.layout.dim=[MultiArrayDimension(label='left_pi_nm,right_pi_nm,left_actual_rad_s,right_actual_rad_s',size=4,stride=4)]
        msg.data=[.1,.2,1.,2.]; drive.publish(msg)
        current.publish(Float32(data=1.25))
        rclpy.spin_once(node,timeout_sec=.02)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    if rclpy.ok(): rclpy.shutdown()
'''
    source=subprocess.Popen([sys.executable,"-c",fixture,str(ready)],env=env,start_new_session=True,
                            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+5
        while not ready.exists() and source.poll() is None and time.monotonic()<deadline: time.sleep(.05)
        assert ready.exists()
        config=tmp_path/"signals.json"
        config.write_text(json.dumps(dict(signals=[dict(name="current",topic="/test_motor/current",type="std_msgs/msg/Float32",field="data",unit="A",kind="reported_unverified")])))
        output=tmp_path/"record"
        run=subprocess.run([sys.executable,str(Path(state_monitor.__file__).resolve()),"--duration","5","--json",
                            "--signals",str(config),"--record",str(output)],env=env,capture_output=True,text=True,timeout=20)
        assert run.returncode==0,run.stderr+run.stdout[-2000:]
        final=json.loads((output/"final_state.json").read_text())
        assert final["command_publishers_created"]==0 and final["errors"]==[]
        imu=final["topics"]["/imu/data"]
        assert imu["count"]>10 and imu["values"]["acceleration_m_s2"][2]==pytest.approx(9.81)
        assert final["topics"]["/joint_states"]["values"]["joints"][0]["effort_Nm"] is None
        drive=final["topics"]["/nino_drive/diagnostics"]["values"]
        assert drive["schema_valid"] and drive["fields"]["left_pi_nm"]==pytest.approx(.1)
        assert final["topics"]["/test_motor/current"]["signals"][0]["value"]==pytest.approx(1.25)
        assert final["topics"]["/wheel_torque_applied"]["status"]=="WAITING"
        records=[json.loads(line) for line in (output/"messages.jsonl").read_text().splitlines()]
        assert any(row["topic"]=="/nino_drive/diagnostics" and row["message"]["layout"]["dim"][0]["label"].startswith("left_pi_nm") for row in records)
        assert sum(row["topic"]=="/imu/data" for row in records)==imu["count"]
        assert len([json.loads(line) for line in run.stdout.splitlines()])>=2
    finally:
        if source.poll() is None: os.killpg(source.pid,signal.SIGINT)
        try: source.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(source.pid,signal.SIGTERM); source.communicate(timeout=5)
