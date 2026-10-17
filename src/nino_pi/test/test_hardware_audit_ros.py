"""Optional Jazzy integration with synthetic IMU only, isolated from robot ROS.

No Gazebo, motor commands or hardware drivers. Run with sourced ROS/system Python.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

pytest.importorskip("rclpy")
from nino_pi import hardware_audit


def test_real_ros_subscription_gid_and_readonly_parameters(tmp_path):
    env = dict(os.environ,ROS_DOMAIN_ID="223",ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",
               ROS_LOCALHOST_ONLY="1")
    ready = tmp_path/"ready"
    fixture = r'''
import sys,time
from pathlib import Path
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from rclpy.qos import qos_profile_sensor_data
rclpy.init(args=[])
node=Node('hardware_audit_synthetic_fixture')
node.declare_parameter('velocity_kp',0.3)
node.declare_parameter('velocity_ki',0.1)
pub=node.create_publisher(Imu,'/audit_fixture/imu',qos_profile_sensor_data)
Path(sys.argv[1]).write_text('ready')
end=time.monotonic()+20
try:
    while time.monotonic()<end:
        msg=Imu()
        msg.header.frame_id='audit_fixture_imu'
        msg.header.stamp=node.get_clock().now().to_msg()
        msg.orientation.w=1.
        msg.linear_acceleration.z=9.81
        pub.publish(msg)
        rclpy.spin_once(node,timeout_sec=.02)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    if rclpy.ok(): rclpy.shutdown()
'''
    source = subprocess.Popen([sys.executable,"-c",fixture,str(ready)],env=env,
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        deadline = time.monotonic()+5
        while not ready.exists() and source.poll() is None and time.monotonic()<deadline:
            time.sleep(.05)
        assert ready.exists(), source.communicate(timeout=1)
        output = tmp_path/"audit"
        result = subprocess.run([sys.executable,str(Path(hardware_audit.__file__).resolve()),
                                 "--duration","5","--output",str(output)],env=env,
                                 capture_output=True,text=True,timeout=20)
        assert result.returncode == 0, result.stdout+result.stderr
        report = json.loads((output/"report.json").read_text())
        row = report["measurements"]["/audit_fixture/imu"]
        assert row["received"] > 20
        assert row["axis_statistics"]["acceleration_z"]["mean"] == pytest.approx(9.81)
        assert row["frame_ids"] == {"audit_fixture_imu":row["received"]}
        assert row["backward_stamps"] == row["zero_stamps"] == 0
        observed = set(row["publisher_samples"])
        if "unavailable" in observed:
            assert observed == {"unavailable"}
            assert any("rclpy không cung cấp publisher GID" in w for w in report["warnings"])
        else:
            assert observed == {p["gid"] for p in report["topics"]["/audit_fixture/imu"]["publishers"]}
        params = json.loads((output/"parameters.json").read_text())
        assert params["/hardware_audit_synthetic_fixture"]["values"]["velocity_kp"] == .3
        assert report["command_publishers_created"] == 0
        assert not any(v["kind"] == "command" for v in report["topics"].values())
        assert (output/"sha256.json").exists()
    finally:
        if source.poll() is None:
            os.killpg(source.pid,signal.SIGINT)
        try:
            source.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(source.pid,signal.SIGTERM)
            source.communicate(timeout=5)
