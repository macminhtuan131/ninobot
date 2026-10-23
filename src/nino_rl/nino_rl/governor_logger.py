"""Research-only contact/body logger; never publishes motor commands."""
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
from rclpy.clock import Clock,ClockType
from rclpy.signals import SignalHandlerOptions
from rosidl_runtime_py.convert import message_to_ordereddict
from sensor_msgs.msg import Imu,JointState
from std_msgs.msg import Float64MultiArray,String
from nav_msgs.msg import Odometry
from ros_gz_interfaces.msg import Contacts
from nino_rl.observer_health import ObserverHealth,observed_callback,ObserverShutdown

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
        self.declare_parameter("world_override","")
        self.declare_parameter("contact_sample_rate",100.)
        self.declare_parameter("caster_wheel_damping",.01)
        self.output=Path(self.get_parameter("output_directory").value).expanduser().resolve()/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
        self.output.mkdir(parents=True,exist_ok=False)
        self.stream=(self.output/"samples.jsonl").open("w",buffering=1024*1024)
        self.event_stream=(self.output/"contact_events.jsonl").open("w")
        self.counts={}
        self.health=ObserverHealth()
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
        metadata["caster_wheel_damping_declared"]=float(self.get_parameter("caster_wheel_damping").value)
        metadata["robot_description_validated"]=False
        if config_path:
            contents=Path(config_path).read_bytes()
            (self.output/"source_config.yaml").write_bytes(contents)
            metadata["source_config_sha256"]=hashlib.sha256(contents).hexdigest()
            from nino_rl.core import load_config
            resolved = load_config(config_path)
            (self.output/"resolved_config.json").write_text(json.dumps(resolved,indent=2)+"\n")
            if resolved.get("research_experiment", {}).get("oracle_contact_input"):
                metadata["governor_has_no_oracle_input"] = False
                metadata["research_experiment"] = resolved["research_experiment"]
        from ament_index_python.packages import get_package_share_directory
        from nino_control import governor_core
        metadata["governor_core_sha256"]=hashlib.sha256(Path(governor_core.__file__).read_bytes()).hexdigest()
        from importlib.util import find_spec
        for name in ("effort_drive","control_timing"):
            source=Path(find_spec("nino_control."+name).origin).read_bytes()
            metadata[name+"_sha256"]=hashlib.sha256(source).hexdigest()
            (self.output/(name+"_source.py")).write_bytes(source)
        metadata["timing_telemetry"]=dict(missing_value=-1,
            qualification="PI-update aggregates emitted at the existing 50Hz status rate; no control change")
        variant=self.get_parameter("variant").value
        override=self.get_parameter("world_override").value
        world=(Path(override).expanduser().resolve() if override else
               Path(get_package_share_directory("nino_description"))/"worlds"/f"factory_floor_{variant}_contact_lab.sdf")
        metadata["world_file"]=str(world)
        if world.is_file():
            metadata["world_sha256"]=hashlib.sha256(world.read_bytes()).hexdigest()
            (self.output/"world_metadata.json").write_bytes(world.with_suffix(".json").read_bytes())
        metadata["logger_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        metadata["observer_health_source_sha256"]=hashlib.sha256(
            Path(__file__).with_name("observer_health.py").read_bytes()).hexdigest()
        metadata["observer_health"]=dict(schema="observer_health_v1",complete=False,
            maximum_records=self.health.maximum_records,sidecar_written_after_collection=True)
        self.metadata=metadata
        self.lifecycle=None
        if os.environ.get("NINO_ACQUISITION_SESSION"):
            from nino_rl.acquisition_contract import Lifecycle
            self.lifecycle=Lifecycle(os.environ["NINO_ACQUISITION_SESSION"],"primary",self.output)
            self.metadata["acquisition_session_id"]=self.lifecycle.session["session_id"]
            self.metadata["acquisition_protocol_sha256"]=self.lifecycle.session["protocol_sha256"]
        self.write_metadata()
        self._log_subscriptions=[]
        self._log_subscriptions.append(self.create_subscription(String,"/robot_description",self.on_description,
            QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)))
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
        if self.lifecycle:
            self.create_timer(.1,lambda:self.lifecycle.publish(self.get_clock().now().nanoseconds),
                              clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info("Research logger: "+str(self.output))

    @observed_callback("description")
    def on_description(self,msg):
        """Audit the model actually published by robot_state_publisher."""
        try:
            robot=ET.fromstring(msg.data)
            values={side:float(robot.find(f"joint[@name='caster_{side}_wheel_joint']/dynamics").get("damping"))
                    for side in ("left","right")}
            valid=all(abs(value-self.metadata["caster_wheel_damping_declared"])<1e-12 for value in values.values())
            self.metadata.update(robot_description_validated=valid,caster_wheel_damping_observed=values,
                                 robot_description_sha256=hashlib.sha256(msg.data.encode()).hexdigest())
            (self.output/"robot_description.urdf").write_text(msg.data)
            if not valid: self.get_logger().error("Caster damping does not match declared experiment model")
        except (ET.ParseError,AttributeError,TypeError,ValueError) as error:
            self.metadata.update(robot_description_validated=False,robot_description_error=str(error))
        self.write_metadata()

    def write_metadata(self):
        with self.health.stage("metadata_write"):
            (self.output/"metadata.json").write_text(json.dumps(self.metadata,indent=2)+"\n")

    def write(self,stream,row):
        with self.health.stage("sanitize"):
            value=finite_json(row)
        with self.health.stage("json_encode"):
            text=json.dumps(value,allow_nan=False)+"\n"
        with self.health.stage("raw_write" if stream is self.stream else "event_write"):
            stream.write(text)

    def episode_id(self):
        if not isinstance(self.episode,dict):
            return None
        return (str(self.episode["run_id"])+":"+str(self.episode["attempt"])
                if self.episode.get("run_id") else self.episode.get("attempt"))

    @observed_callback("sensor")
    def record(self,topic,msg):
        if getattr(self,"lifecycle",None):
            s=msg.header.stamp if hasattr(msg,"header") else None
            if s is not None:self.lifecycle.sample(topic,s.sec*1000000000+s.nanosec)
        self.counts[topic]=self.counts.get(topic,0)+1
        receipt=self.get_clock().now().nanoseconds*1e-9
        self.health.annotate(receipt_sim_s=receipt)
        with self.health.stage("message_convert"):
            data=message_to_ordereddict(msg)
        self.write(self.stream,dict(receipt_time_s=receipt,
                                   topic=topic,episode=self.episode_id(),data=data))

    @observed_callback("state")
    def on_state(self,topic,msg):
        try:
            data=json.loads(msg.data)
        except ValueError:
            data={"invalid_payload":msg.data}
        self.health.annotate(source_stamp_s=data.get("time_s") if isinstance(data,dict) else None)
        if topic.endswith("/episode"):
            self.episode=data
            self.active.clear()
            self.last_contact.clear()
        self.counts[topic]=self.counts.get(topic,0)+1
        self.write(self.stream,dict(topic=topic,episode=self.episode_id(),data=data))
        if getattr(self,"lifecycle",None) and topic.endswith("/episode"):
            self.stream.flush()
            self.lifecycle.marker(data,self.get_clock().now().nanoseconds)

    @observed_callback("contact")
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

    @observed_callback("flush")
    def flush(self):
        with self.health.stage("raw_flush"):
            self.stream.flush()
        with self.health.stage("event_flush"):
            self.event_stream.flush()
        self.metadata["message_counts"]=self.counts
        self.write_metadata()

    def close(self):
        self.flush()
        self.stream.close()
        self.event_stream.close()
        self.metadata["complete"]=True  # Logger closed, not experiment success.
        self.metadata["observer_health"]=self.health.close(self.output)
        self.write_metadata()
        if self.lifecycle:
            self.lifecycle.close(self.get_clock().now().nanoseconds,
                                 self.metadata.get("observer_runtime_error"))


def main(args=None):
    # ROS context remains alive until collection/sidecar close finishes. The
    # launcher may signal both the process group and the child separately.
    with ObserverShutdown() as shutdown:
        rclpy.init(args=args,signal_handler_options=SignalHandlerOptions.NO)
        node=None
        try:
            node=GovernorLogger()
            while rclpy.ok() and not shutdown.requested:
                rclpy.spin_once(node,timeout_sec=.1)
        except Exception as error:
            if node is not None:
                node.metadata["observer_runtime_error"]=f"{type(error).__name__}: {error}"
            raise
        finally:
            try:
                if node is not None:
                    node.metadata["observer_shutdown_signals"]=shutdown.received
                    try:
                        node.close()
                    finally:
                        node.destroy_node()
            finally:
                if rclpy.ok():
                    rclpy.shutdown()
