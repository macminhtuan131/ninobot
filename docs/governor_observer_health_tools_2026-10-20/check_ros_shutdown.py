"""Isolated synthetic ROS lifecycle check: no Gazebo, drivers, or motion commands."""
import argparse
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
from nino_rl.observer_health import check_sidecar


def main(output,stall_seconds=0.):
    assert os.environ.get("ROS_DOMAIN_ID")=="198"
    assert os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE")=="LOCALHOST"
    output.mkdir(parents=True,exist_ok=False)
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu,JointState
    assert 0 <= stall_seconds <= .5
    code="from nino_rl.governor_logger import main; main()"
    if stall_seconds:
        code=f"""import time
from nino_rl.governor_logger import GovernorLogger, main
original=GovernorLogger.write
def fixture_write(self,stream,row):
    if self.counts.get('/joint_states',0)>=50 and not getattr(self,'fixture_stalled',False):
        self.fixture_stalled=True
        with self.health.stage('injected_raw_write'):
            time.sleep({stall_seconds!r})
    return original(self,stream,row)
GovernorLogger.write=fixture_write
main()
"""
    command=[sys.executable,"-c",code,
             "--ros-args","-p","use_sim_time:=false","-p",f"output_directory:={output/'logger'}"]
    with (output/"logger.log").open("w") as log:
        child=subprocess.Popen(command,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        node=None
        try:
            rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
            node=rclpy.create_node("synthetic_observer_fixture")
            imu=node.create_publisher(Imu,"/imu/data",qos_profile_sensor_data)
            joints=node.create_publisher(JointState,"/joint_states",qos_profile_sensor_data)
            deadline=time.monotonic()+15
            while (imu.get_subscription_count()<1 or joints.get_subscription_count()<1) and time.monotonic()<deadline:
                assert child.poll() is None,"Logger exited during startup"
                rclpy.spin_once(node,timeout_sec=.02)
            assert imu.get_subscription_count()>=1 and joints.get_subscription_count()>=1
            for _ in range(300):
                stamp=node.get_clock().now().to_msg()
                a=Imu();a.header.stamp=stamp;a.header.frame_id="imu_link"
                a.orientation.w=1.;a.linear_acceleration.z=9.80665
                b=JointState();b.header.stamp=stamp;b.name=["left_wheel_joint","right_wheel_joint"]
                b.position=[0.,0.];b.velocity=[6.4,6.4];b.effort=[0.,0.]
                imu.publish(a);joints.publish(b)
                rclpy.spin_once(node,timeout_sec=0)
                time.sleep(.002)
            time.sleep(.1)
            child.send_signal(signal.SIGINT)
            time.sleep(.001)
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
            assert child.wait(timeout=15)==0,"Logger did not close cleanly"
        finally:
            if child.poll() is None:
                child.kill();child.wait(timeout=5)
            if node is not None:node.destroy_node()
            if rclpy.ok():rclpy.shutdown()
    paths=list((output/"logger").glob("*/metadata.json"))
    assert len(paths)==1
    metadata=json.loads(paths[0].read_text())
    expected=hashlib.sha256((ROOT/"src/nino_rl/nino_rl/observer_health.py").read_bytes()).hexdigest()
    check=check_sidecar(paths[0].parent,expected)
    assert check["valid"],check
    assert metadata["complete"] and len(metadata["observer_shutdown_signals"])>=1
    assert metadata["message_counts"]["/imu/data"]>0 and metadata["message_counts"]["/joint_states"]>0
    result=dict(synthetic_ROS_only=True,simulation_episodes=0,hardware_connected=False,
        motor_commands_published=0,child_returncode=child.returncode,
        metadata_complete=metadata["complete"],health_valid=check["valid"],
        shutdown_signals=metadata["observer_shutdown_signals"],message_counts=metadata["message_counts"],
        observer_health=check,injected_writer_stall_seconds=stall_seconds,
        qualification="Synthetic lifecycle/fault injection only; not contact/sensor fidelity, sampling coverage, governor benefit, or proof of the original gap cause.")
    if stall_seconds:
        duration=check["longest_callback"]["stages_ns"].get("injected_raw_write",0)*1e-9
        assert duration>=stall_seconds
        result["detected_injected_writer_stall_seconds"]=duration
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="observer_health"},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--inject-write-stall",type=float,default=0.)
    args=parser.parse_args()
    main(args.output.resolve(),args.inject_write_stall)
