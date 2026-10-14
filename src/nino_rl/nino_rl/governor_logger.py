"""Research-only contact/body logger; never publishes motor commands."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import hashlib

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.clock import Clock,ClockType
from rosidl_runtime_py.convert import message_to_ordereddict
from sensor_msgs.msg import Imu,JointState
from std_msgs.msg import Float64MultiArray,String
from nav_msgs.msg import Odometry
from ros_gz_interfaces.msg import Contacts

CONTACT_COMPONENTS=("left_wheel","right_wheel","caster_left_wheel","caster_right_wheel",
                    "caster_bracket_left","caster_bracket_right","chassis")


def finite_json(value):
    """Missing/nonfinite measurements are null, never artificial zeros."""
    if isinstance(value,float) and not math.isfinite(value):
        return None
    if isinstance(value,dict):
        return {key:finite_json(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [finite_json(item) for item in value]
    return value


class GovernorLogger(Node):
    def __init__(self):
        super().__init__("governor_logger")
        self.declare_parameter("output_directory","rl_runs/governor_contact_lab")
        self.declare_parameter("config_file","")
        self.declare_parameter("variant","cable")
        self.declare_parameter("contact_sample_rate",100.)
        self.output=Path(self.get_parameter("output_directory").value).expanduser().resolve()/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
        self.output.mkdir(parents=True,exist_ok=False)
        self.stream=(self.output/"samples.jsonl").open("w",buffering=1024*1024)
        self.event_stream=(self.output/"contact_events.jsonl").open("w")
        self.counts={}
        self.active={}
        self.last_contact={}
        self.last_time=None
        self.episode=None
        self.interval=1/float(self.get_parameter("contact_sample_rate").value)
        if not 0<self.interval<=1:
            raise ValueError("Invalid contact sampling rate")
        config_path=self.get_parameter("config_file").value
        metadata=dict(schema_version=2,complete=False,logger_only=True,sim_contact_is_privileged=True,
            ground_truth_is_evaluation_only=True,governor_has_no_oracle_input=True,
            contact_forces_may_be_unavailable=True,impulse_not_inferred_without_valid_force_timing=True,
            qualification="Instrumentation/authority experiment, not a learning or sim-to-real result")
        metadata["contact_components"]=CONTACT_COMPONENTS
        if config_path:
            contents=Path(config_path).read_bytes()
            (self.output/"source_config.yaml").write_bytes(contents)
            metadata["source_config_sha256"]=hashlib.sha256(contents).hexdigest()
            from nino_rl.core import load_config
            (self.output/"resolved_config.json").write_text(json.dumps(load_config(config_path),indent=2)+"\n")
        from ament_index_python.packages import get_package_share_directory
        from nino_control import governor_core
        metadata["governor_core_sha256"]=hashlib.sha256(Path(governor_core.__file__).read_bytes()).hexdigest()
        variant=self.get_parameter("variant").value
        world=Path(get_package_share_directory("nino_description"))/"worlds"/f"factory_floor_{variant}_contact_lab.sdf"
        if world.is_file():
            metadata["world_sha256"]=hashlib.sha256(world.read_bytes()).hexdigest()
            (self.output/"world_metadata.json").write_bytes(world.with_suffix(".json").read_bytes())
        metadata["logger_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.metadata=metadata
        self.write_metadata()
        self._log_subscriptions=[]
        for topic,typ in (("/imu/data",Imu),("/joint_states",JointState),
                          ("/nino_drive/diagnostics",Float64MultiArray),
                          ("/ground_truth/odom",Odometry),("/odom",Odometry)):
            self._log_subscriptions.append(self.create_subscription(typ,topic,
                lambda msg,topic=topic:self.record(topic,msg),qos_profile_sensor_data))
        for topic in ("/nino/governor/state","/nino/governor/episode"):
            self._log_subscriptions.append(self.create_subscription(String,topic,
                lambda msg,topic=topic:self.on_state(topic,msg),10))
        for component in CONTACT_COMPONENTS:
            self._log_subscriptions.append(self.create_subscription(Contacts,"/nino/contact_lab/"+component,
                lambda msg,component=component:self.on_contacts(component,msg),qos_profile_sensor_data))
        self.create_timer(1.,self.flush,clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info("Research logger: "+str(self.output))

    def write_metadata(self):
        (self.output/"metadata.json").write_text(json.dumps(self.metadata,indent=2)+"\n")

    def write(self,stream,row):
        stream.write(json.dumps(finite_json(row),allow_nan=False)+"\n")

    def episode_id(self):
        if not isinstance(self.episode,dict):
            return None
        return (str(self.episode["run_id"])+":"+str(self.episode["attempt"])
                if self.episode.get("run_id") else self.episode.get("attempt"))

    def record(self,topic,msg):
        self.counts[topic]=self.counts.get(topic,0)+1
        self.write(self.stream,dict(receipt_time_s=self.get_clock().now().nanoseconds*1e-9,
                                   topic=topic,episode=self.episode_id(),data=message_to_ordereddict(msg)))

    def on_state(self,topic,msg):
        try:
            data=json.loads(msg.data)
        except ValueError:
            data={"invalid_payload":msg.data}
        if topic.endswith("/episode"):
            self.episode=data
            self.active.clear()
            self.last_contact.clear()
        self.counts[topic]=self.counts.get(topic,0)+1
        self.write(self.stream,dict(topic=topic,episode=self.episode_id(),data=data))

    def on_contacts(self,component,msg):
        stamp=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
        if self.last_time is not None and stamp<self.last_time-1:
            self.active.clear()
            self.last_contact.clear()
        self.last_time=stamp
        contacts={tuple(sorted((c.collision1.name,c.collision2.name))) for c in msg.contacts}
        previous=self.active.get(component,set())
        for kind,pairs in (("begin",contacts-previous),("end",previous-contacts)):
            for pair in sorted(pairs):
                # Floor support is retained in raw logs. This annotation only
                # labels named positive obstacles; carved-pit phases require
                # offline geometry/contact-position analysis.
                positive=any(name in collision for collision in pair for name in (
                    "cable_bumps","training_cable","isolated_threshold","feature_"))
                self.write(self.event_stream,dict(time_s=stamp,component=component,event=kind,
                    collisions=pair,named_positive_obstacle=positive,episode=self.episode_id(),
                    end_time_is_upper_bound=kind=="end"))
        self.active[component]=contacts
        if contacts!=previous or stamp-self.last_contact.get(component,-float("inf"))>=self.interval:
            self.record("/nino/contact_lab/"+component,msg)
            self.last_contact[component]=stamp

    def flush(self):
        self.stream.flush()
        self.event_stream.flush()
        self.metadata["message_counts"]=self.counts
        self.write_metadata()

    def close(self):
        self.flush()
        self.stream.close()
        self.event_stream.close()
        self.metadata["complete"]=True  # Logger closed, not experiment success.
        self.write_metadata()


def main(args=None):
    rclpy.init(args=args)
    node=GovernorLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
