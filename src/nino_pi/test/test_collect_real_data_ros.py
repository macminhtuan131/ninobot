"""Synthetic localhost ROS/rosbag integration only. Never publish motor commands."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

import pytest

pytest.importorskip("rclpy")
from nino_pi import collect_real_data as collect


def test_raw_bag_and_audit_close_without_hardware(tmp_path):
    env = dict(os.environ, ROS_DOMAIN_ID="227", ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST", ROS_LOCALHOST_ONLY="1")
    fixture = r'''
import time,sys
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu,JointState
rclpy.init(args=[])
node=Node('nino_collection_synthetic_sensors')
imu=node.create_publisher(Imu,'/imu/data',qos_profile_sensor_data)
joints=node.create_publisher(JointState,'/joint_states',qos_profile_sensor_data)
Path(sys.argv[1]).touch()
try:
    end=time.monotonic()+30
    while time.monotonic()<end:
        msg=Imu(); msg.header.stamp=node.get_clock().now().to_msg(); msg.header.frame_id='imu_link'
        msg.orientation.w=1.; msg.linear_acceleration.z=9.81; imu.publish(msg)
        msg=JointState(); msg.header.stamp=node.get_clock().now().to_msg()
        msg.name=['left_wheel_joint','right_wheel_joint']; msg.velocity=[0.,0.]; joints.publish(msg)
        rclpy.spin_once(node,timeout_sec=.01)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    if rclpy.ok(): rclpy.shutdown()
'''
    ready = tmp_path / "ready"
    source = subprocess.Popen([sys.executable, "-c", fixture, str(ready)], env=env, start_new_session=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and source.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists()
        config = dict(schema_version=1, duration_s=8, max_session_mb=32, reserve_disk_mb=16,
                      topics=[dict(name=t, required=True, purpose="synthetic sensor") for t in ("/imu/data", "/joint_states")]
                      + [dict(name="/missing_torque", required=False, purpose="intentional missing torque")])
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))
        session = tmp_path / "session.json"
        session.write_text(json.dumps(dict(session_id="synthetic_test_only")))
        output = tmp_path / "record"
        qos = Path(__file__).resolve().parents[1] / "config" / "real_collection_qos.yaml"
        result = subprocess.run([sys.executable, "-m", "nino_pi.collect_real_data", "--config", str(config_path),
                                 "--session", str(session), "--qos", str(qos), "--output", str(output)],
                                env=env, capture_output=True, text=True, timeout=45)
        manifest = json.loads((output / "manifest.json").read_text())
        assert result.returncode == 0, result.stderr + result.stdout + str(manifest)
        assert manifest["status"] == "captured_not_calibrated"
        assert manifest["motion_commands_sent"] == 0
        assert manifest["bag"]["missing_required_topics"] == []
        assert "/missing_torque" in manifest["bag"]["missing_topics"]
        assert manifest["bag"]["topics"]["/imu/data"]["count"] > 30
        assert (output / "audit" / "graph.mmd").exists()
        assert (output / "sha256.json").exists()
        from rclpy.serialization import deserialize_message
        from sensor_msgs.msg import JointState
        db_path = next((output / "bag").glob("*.db3"))
        with sqlite3.connect(db_path) as db:
            raw = db.execute("SELECT m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name='/joint_states' LIMIT 1").fetchone()[0]
        msg = deserialize_message(raw, JointState)
        assert list(msg.effort) == []  # No fabricated measured torque.
        assert msg.header.stamp.sec > 0
        assert list(msg.velocity) == [0., 0.]
    finally:
        if source.poll() is None:
            os.killpg(source.pid, signal.SIGINT)
        try:
            source.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(source.pid, signal.SIGTERM)
            source.communicate(timeout=5)
