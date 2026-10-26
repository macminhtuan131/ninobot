"""Candidate joint/GT recorder in its own process; no contact/control subscriptions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from time import monotonic_ns

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,qos_profile_sensor_data
from rclpy.clock import Clock,ClockType
from rclpy.signals import SignalHandlerOptions
from rclpy.serialization import serialize_message,deserialize_message
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from rosidl_runtime_py.convert import message_to_ordereddict

from nino_rl.acquisition_frames import FrameWriter,read_frames,validate_episode,atomic_json
from nino_rl.observer_health import ObserverShutdown
from nino_rl.governor_logger import finite_json

TYPES={"/joint_states":JointState,"/ground_truth/odom":Odometry,"/nino/governor/episode":String}
SENSOR_QUEUE_DEPTH=100


def capture_sensor_qos():
    """Bounded receipt buffer local to this recorder; never mutate shared QoS.

    A larger queue tolerates finite callback-service pauses. BEST_EFFORT can
    still lose source samples, so original timestamp/coverage gates remain.
    """
    s=qos_profile_sensor_data
    return QoSProfile(depth=SENSOR_QUEUE_DEPTH,history=s.history,reliability=s.reliability,
        durability=s.durability,lifespan=s.lifespan,deadline=s.deadline,
        liveliness=s.liveliness,liveliness_lease_duration=s.liveliness_lease_duration,
        avoid_ros_namespace_conventions=s.avoid_ros_namespace_conventions)


class IsolatedAcquisition(Node):
    def __init__(self,output,use_sim_time=False,maximum_bytes=512*1024*1024):
        super().__init__("isolated_joint_gt_acquisition",parameter_overrides=[
            rclpy.parameter.Parameter("use_sim_time",value=use_sim_time)])
        self.sensor_qos=capture_sensor_qos()
        self.writer=FrameWriter(output,maximum_bytes=maximum_bytes,metadata=dict(
            process_isolated=True,logger_only=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            frames_source_sha256=hashlib.sha256(Path(__file__).with_name("acquisition_frames.py").read_bytes()).hexdigest(),
            sensor_qos=dict(depth=self.sensor_qos.depth,history=self.sensor_qos.history.name,
                            reliability=self.sensor_qos.reliability.name),
            maximum_callback_ns=0,epoch=0,
            qualification="Raw ROS CDR, source timestamps unchanged. Callback sequence counts received messages only; source loss still requires coverage checks."))
        self.epoch=0
        self.last_reset=None
        self.lifecycle=None
        if os.environ.get("NINO_ACQUISITION_SESSION"):
            from nino_rl.acquisition_contract import Lifecycle
            self.lifecycle=Lifecycle(os.environ["NINO_ACQUISITION_SESSION"],"joint_gt",self.writer.directory)
            self.writer.metadata.update(acquisition_session_id=self.lifecycle.session["session_id"],
                acquisition_protocol_sha256=self.lifecycle.session["protocol_sha256"])
            self.create_timer(.1,lambda:self.lifecycle.publish(self.get_clock().now().nanoseconds),
                              clock=Clock(clock_type=ClockType.STEADY_TIME))
        for identifier,topic in ((1,"/joint_states"),(2,"/ground_truth/odom")):
            self.create_subscription(TYPES[topic],topic,lambda msg,i=identifier:self.record(i,msg),self.sensor_qos)
        self.create_subscription(String,"/nino/governor/episode",self.episode,10)
        atomic_json(self.writer.directory/"ready.json",dict(ready=True,pid=__import__("os").getpid(),
            subscriptions=list(TYPES),contact_subscriptions=False,motor_publishers=False))

    def record(self,identifier,message,source_ns=None):
        begin=monotonic_ns()
        if source_ns is None:
            s=message.header.stamp;source_ns=s.sec*1000000000+s.nanosec
        self.writer.append(identifier,serialize_message(message),source_ns,
            self.get_clock().now().nanoseconds,begin,self.epoch)
        if self.lifecycle and identifier in (1,2):
            self.lifecycle.sample("/joint_states" if identifier==1 else "/ground_truth/odom",source_ns)
        self.writer.metadata["maximum_callback_ns"]=max(self.writer.metadata["maximum_callback_ns"],monotonic_ns()-begin)

    def episode(self,message):
        marker=json.loads(message.data)
        if marker.get("event")=="reset":self.epoch+=1;self.last_reset=marker
        self.writer.metadata["epoch"]=self.epoch
        self.record(3,message,round(marker["time_s"]*1e9))
        # Two lifecycle writes per episode; no per-sensor JSON conversion.
        atomic_json(self.writer.directory/"epoch_ready.json",dict(marker=marker,epoch=self.epoch))
        if self.lifecycle:
            self.writer.stream.flush()
            self.lifecycle.marker(marker,self.get_clock().now().nanoseconds)


def decode(directory,output,run_id,attempt,start_ns,end_ns,*,selected_epoch_only=False):
    """A derived JSON view; raw files stay immutable and are never gap-filled."""
    frames=list(read_frames(directory));markers=[];messages=[]
    for f in frames:
        message=deserialize_message(f["payload"],TYPES[f["topic"]])
        if f["topic"]=="/nino/governor/episode":
            marker=json.loads(message.data)
            markers.append(dict(marker,epoch=f["epoch"],sequence=f["sequence"],source_ns=f["source_ns"]))
        else:
            s=message.header.stamp
            if s.sec*1000000000+s.nanosec!=f["source_ns"]:raise ValueError("Envelope/source timestamp mismatch")
        messages.append(message)
    validation_frames=frames
    if selected_epoch_only:
        resets=[m for m in markers if m.get("event")=="reset"
                and m.get("run_id")==run_id and m.get("attempt")==attempt]
        if len(resets)!=1:raise ValueError("Missing/ambiguous selected reset epoch")
        # During paused lockstep the last pre-reset sample can legitimately
        # equal start_ns. Keep it in raw/decode, but never use its old epoch
        # as a selected-episode measurement or as interpolation support.
        validation_frames=[f for f in frames if f["epoch"]==resets[0]["epoch"]]
    result=validate_episode(validation_frames,markers,run_id,attempt,start_ns,end_ns)
    result.update(selected_epoch_only=selected_epoch_only,
                  excluded_other_epoch_frames=len(frames)-len(validation_frames))
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    epoch_ids={m["epoch"]:str(m["run_id"])+":"+str(m["attempt"]) for m in markers}
    with (output/"samples.jsonl").open("x") as stream:
        for f,message in zip(frames,messages):
            data=json.loads(message.data) if f["topic"]=="/nino/governor/episode" else message_to_ordereddict(message)
            row=dict(receipt_time_s=f["receipt_sim_ns"]*1e-9,topic=f["topic"],
                     episode=epoch_ids.get(f["epoch"]),data=finite_json(data))
            stream.write(json.dumps(row,allow_nan=False)+"\n")
    atomic_json(output/"decode_manifest.json",dict(complete=True,validation=result,
        capture_manifest=json.loads((Path(directory)/"capture_manifest.json").read_text()),
        source_timestamps_unchanged=True,all_frames_retained=True,resampling=False,
        valid_for_existing_scoring=False,
        qualification="Candidate sensor-only view. Requires explicit contact/aux view provenance integration and original coverage scoring before any experiment use."))
    return result


def compose_view(primary,capture,output,run_id,attempt,start_ns,end_ns,*,selected_epoch_only=False):
    """Explicit new-contract view, never mix/fill two joint/GT measurement sources."""
    primary,capture,output=Path(primary),Path(capture),Path(output)
    metadata=json.loads((primary/"metadata.json").read_text())
    if not metadata.get("complete") or metadata.get("observer_runtime_error"):
        raise ValueError("Primary observer was not cleanly closed")
    if metadata.get("observer_health") and not metadata["observer_health"].get("valid"):
        raise ValueError("Primary observer health is invalid")
    parent_rows=[json.loads(line) for line in (primary/"samples.jsonl").open()]
    parent_markers=[r["data"] for r in parent_rows if r["topic"]=="/nino/governor/episode"]
    frames=list(read_frames(capture))
    child_markers=[json.loads(deserialize_message(f["payload"],String).data)
                   for f in frames if f["topic"]=="/nino/governor/episode"]
    def identity(markers):
        return [(m.get("event"),m.get("run_id"),m.get("attempt"),round(m["time_s"]*1e9))
                for m in markers if m.get("run_id")==run_id and m.get("attempt")==attempt]
    if identity(parent_markers)!=identity(child_markers) or len(identity(parent_markers))!=2:
        raise ValueError("Parent/capture lifecycle mismatch; cannot combine runs")
    paths=[primary/"samples.jsonl",primary/"metadata.json",capture/"joint_gt.frames",capture/"capture_manifest.json"]
    hashes={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    output.mkdir(parents=True,exist_ok=False)
    atomic_json(output/"view_manifest.json",dict(complete=False,valid_for_existing_scoring=False))
    decoded=output/"decoded_sensor_source"
    validation=decode(capture,decoded,run_id,attempt,start_ns,end_ns,
                      selected_epoch_only=selected_epoch_only)
    sensor_topics={"/joint_states","/ground_truth/odom"}
    authority={topic:0 for topic in sensor_topics};replaced={topic:0 for topic in sensor_topics}
    temp=output/"samples.jsonl.tmp"
    with temp.open("x") as stream:
        for row in parent_rows:
            if row["topic"] in sensor_topics:
                replaced[row["topic"]]+=1
            else:stream.write(json.dumps(row,allow_nan=False)+"\n")
        for line in (decoded/"samples.jsonl").open():
            row=json.loads(line)
            if row["topic"] in sensor_topics:
                if selected_epoch_only:
                    stamp=row["data"]["header"]["stamp"]
                    reset_ns=next(round(m["time_s"]*1e9) for m in child_markers
                        if m.get("event")=="reset" and m.get("run_id")==run_id and m.get("attempt")==attempt)
                    if row.get("episode")!=str(run_id)+":"+str(attempt) or stamp["sec"]*1000000000+stamp["nanosec"]<reset_ns:
                        continue
                authority[row["topic"]]+=1;stream.write(line)
    for p in paths:
        if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p.resolve())]:
            raise ValueError("Source changed during offline composition")
    temp.replace(output/"samples.jsonl")
    atomic_json(output/"primary_metadata.json",metadata)
    result=dict(complete=True,schema="isolated_joint_gt_candidate_view_v1",validation=validation,
        run_id=run_id,attempt=attempt,window_ns=[start_ns,end_ns],input_sha256=hashes,
        isolated_topic_counts=authority,replaced_primary_topic_counts=replaced,
        measurement_authority={topic:"isolated_capture_only" for topic in sorted(sensor_topics)},
        missing_values_filled=False,resampling=False,native_scores_modified=False,
        valid_for_existing_scoring=False,
        selected_epoch_only=selected_epoch_only,
        qualification="Per-topic order retained; aux rows precede sensor rows, no total cross-process callback order claimed. A new integration contract must verify provenance, original sampling/coverage and all native gates. Not a drop-in legacy logger directory.")
    atomic_json(output/"view_manifest.json",result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--use-sim-time",action="store_true")
    p.add_argument("--maximum-bytes",type=int,default=512*1024*1024)
    a=p.parse_args()
    with ObserverShutdown() as stop:
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node=None;error=None
        try:
            node=IsolatedAcquisition(a.output,a.use_sim_time,a.maximum_bytes)
            while rclpy.ok() and not stop.requested:rclpy.spin_once(node,timeout_sec=.05)
        except BaseException as exc:
            error=f"{type(exc).__name__}: {exc}"
            if node is not None:node.writer.error=node.writer.error or error
            raise
        finally:
            try:
                if node is not None:
                    node.writer.metadata["shutdown_signals"]=stop.received
                    closed=node.writer.close(complete=error is None)
                    if node.lifecycle:
                        node.lifecycle.close(node.get_clock().now().nanoseconds,
                            closed.get("error") or error or (None if closed["complete"] else "incomplete_capture"))
                    node.destroy_node()
            finally:
                if rclpy.ok():rclpy.shutdown()


if __name__=="__main__":main()
