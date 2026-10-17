"""Read-only live ROS 2 robot monitor. Standalone: python3 state_monitor.py --help.

Subscribes only. No command publishers, robot service calls, driver launches or parameter writes.
Optional per-message recording is bounded; display snapshots are not synchronized.
"""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time


DEFAULTS = {
    "imu": ("/imu/data", ["sensor_msgs/msg/Imu"]),
    "joints": ("/joint_states", ["sensor_msgs/msg/JointState"]),
    "odom": ("/odom", ["nav_msgs/msg/Odometry"]),
    "scan": ("/scan", ["sensor_msgs/msg/LaserScan"]),
    "command": ("/cmd_vel", ["geometry_msgs/msg/Twist", "geometry_msgs/msg/TwistStamped"]),
    "drive": ("/nino_drive/diagnostics", ["std_msgs/msg/Float64MultiArray"]),
    "torque_command": ("/wheel_torque_applied", ["std_msgs/msg/Float64MultiArray"]),
    "battery": ("/battery_state", ["sensor_msgs/msg/BatteryState"]),
}
KINDS = {"reported_unverified", "measured", "estimate", "command"}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def strict_json(value):
    """Non-finite raw measurements stay explicit rather than becoming zero."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, dict):
        return {str(k): strict_json(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [strict_json(v) for v in value]
    return value


def encode(value):
    return json.dumps(strict_json(value), ensure_ascii=False, allow_nan=False)


def stamp_ns(message):
    stamp = message.get("header", {}).get("stamp")
    if stamp is None:
        return None
    return int(stamp["sec"]) * 1_000_000_000 + int(stamp["nanosec"])


def xyz(value):
    return [number(value.get(axis)) for axis in "xyz"]


def rpy_degrees(orientation):
    q = [number(orientation.get(axis)) for axis in "xyzw"]
    if any(v is None for v in q) or abs(sum(v*v for v in q)-1) > .1:
        return None
    x,y,z,w = q
    return [math.degrees(math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))),
            math.degrees(math.asin(max(-1.,min(1.,2*(w*y-z*x))))),
            math.degrees(math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)))]


def field_at(message, path):
    """Named fields and nonnegative indices only; never eval user configuration."""
    if not isinstance(path,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\[\d+\])?(?:\.[A-Za-z][A-Za-z0-9_]*(?:\[\d+\])?)*", path):
        raise ValueError("field must use dotted names and optional [index]")
    value = message
    for name,index in re.findall(r"([A-Za-z][A-Za-z0-9_]*)(?:\[(\d+)\])?",path):
        value = value[name]
        if index:
            value = value[int(index)]
    return value


def load_signals(path):
    if path is None:
        return []
    data = json.loads(path.read_text())
    signals = data["signals"]
    if not isinstance(signals,list) or len(signals)>64:
        raise ValueError("signals must be a list with at most 64 entries")
    names = set()
    for item in signals:
        if not isinstance(item,dict):
            raise ValueError("each signal must be an object")
        for key in ("name","topic","type","field","unit","kind"):
            if not isinstance(item.get(key),str) or not item[key]:
                raise ValueError("signal requires nonempty " + key)
        if item["name"] in names or not item["topic"].startswith("/") or item["kind"] not in KINDS:
            raise ValueError("duplicate signal name, relative topic, or unknown kind")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*/msg/[A-Za-z][A-Za-z0-9_]*",item["type"]):
            raise ValueError("type must be package/msg/Message")
        # Validate syntax without requiring that the driver's field already exists.
        try:
            field_at({},item["field"])
        except (KeyError,IndexError,TypeError):
            pass
        names.add(item["name"])
    return signals


def summarize(role, msg, effort_kind="reported_unverified"):
    result = {}
    if role == "imu":
        available = lambda field: not msg.get(field+"_covariance") or msg[field+"_covariance"][0] != -1
        result = dict(frame=msg.get("header",{}).get("frame_id"),
                      acceleration_m_s2=xyz(msg["linear_acceleration"]) if available("linear_acceleration") else None,
                      gyro_rad_s=xyz(msg["angular_velocity"]) if available("angular_velocity") else None,
                      rpy_in_reported_imu_frame_deg=rpy_degrees(msg["orientation"]) if available("orientation") else None,
                      note="Acceleration as reported; may include gravity. Not automatically base-frame or gravity compensated.")
    elif role == "joints":
        result = dict(joints=[],effort_kind=effort_kind,
                      note="JointState.effort is reported effort, not independently verified shaft torque; revolute-joint unit N m.")
        names = msg.get("name",[])
        result["schema_valid"] = bool(names) and len(set(names))==len(names) and all(len(msg.get(k,[])) in (0,len(names)) for k in ("position","velocity","effort"))
        for i,name in enumerate(names):
            get = lambda key: number(msg[key][i]) if i < len(msg.get(key,[])) else None
            result["joints"].append(dict(name=name,position_rad=get("position"),velocity_rad_s=get("velocity"),effort_Nm=get("effort")))
    elif role == "odom":
        result = dict(frame=msg.get("header",{}).get("frame_id"),child=msg.get("child_frame_id"),
                      position_m=xyz(msg["pose"]["pose"]["position"]),
                      linear_m_s=xyz(msg["twist"]["twist"]["linear"]),angular_rad_s=xyz(msg["twist"]["twist"]["angular"]),
                      note="Estimator output, not independent ground truth.")
    elif role == "command":
        twist = msg.get("twist",msg)
        result = dict(linear_m_s=xyz(twist["linear"]),angular_rad_s=xyz(twist["angular"]),kind="command")
    elif role == "drive":
        dimensions = msg.get("layout",{}).get("dim",[])
        labels = dimensions[0].get("label","").split(",") if dimensions else []
        data = msg.get("data",[])
        valid = bool(labels) and all(labels) and len(labels)==len(set(labels))==len(data)
        result = dict(schema_valid=valid,fields={key:number(value) for key,value in zip(labels,data)} if valid else {},
                      note="Nino PI/applied/requested Nm fields are controller commands, not measured torque. executed_linear_m_s is a limited reference, not measured body speed.")
        if not valid:
            result["error"] = "Missing/duplicate layout labels or length mismatch: values not guessed by index."
    elif role == "torque_command":
        result = dict(kind="command",values_Nm=[number(v) for v in msg.get("data",[])],
                      note="Actuator torque command, not measured shaft torque. Array ordering is defined by producer.")
    elif role == "scan":
        good = [float(v) for v in msg["ranges"] if number(v) is not None and msg["range_min"] <= v <= msg["range_max"]]
        result = dict(frame=msg.get("header",{}).get("frame_id"),beams=len(msg["ranges"]),
                      finite_returns=len(good),nearest_m=min(good) if good else None,
                      note="No finite returns may mean no return; +inf is not automatically a driver fault.")
    elif role == "battery":
        result = {name:number(msg.get(name)) for name in ("voltage","current","temperature","percentage")}
        result.update(units="V, A (message convention), degC, fraction",present=msg.get("present"))
    return result


class StateStore:
    def __init__(self, specs, effort_kind):
        self.specs, self.effort_kind, self.rows = specs, effort_kind, {}

    def put(self, topic, message, receipt_ns, ros_ns):
        spec = self.specs[topic]
        row = self.rows.setdefault(topic,dict(count=0,receipts=deque(maxlen=4096),duplicates=0,backwards=0))
        stamp = stamp_ns(message)
        previous = row.get("stamp_ns")
        if stamp is not None and previous is not None:
            row["duplicates"] += int(stamp == previous)
            row["backwards"] += int(stamp < previous)
        row.update(stamp_ns=stamp,receipt_ns=receipt_ns,receipt_ros_ns=ros_ns)
        row["count"] += 1
        row["receipts"].append(receipt_ns)
        row["values"] = summarize(spec["role"],message,self.effort_kind)
        custom = []
        for signal in spec["signals"]:
            value, error = None, None
            try:
                value = number(field_at(message,signal["field"]))
                if value is None:
                    error = "nonfinite_or_not_numeric"
            except (KeyError,IndexError,TypeError) as exc:
                error = "field_unavailable: " + str(exc)
            custom.append(dict(name=signal["name"],value=value,unit=signal["unit"],kind=signal["kind"],
                               classification_origin="user_config_not_verified_by_monitor",error=error))
        row["signals"] = custom

    def snapshot(self, monotonic_ns, ros_ns, stale_s):
        result = {}
        for topic,spec in self.specs.items():
            row = self.rows.get(topic)
            if row is None:
                result[topic] = dict(role=spec["role"],status="WAITING",count=0,signals=spec["signals"])
                continue
            receipts = list(row["receipts"])
            dt = (receipts[-1]-receipts[0])/1e9
            age = (monotonic_ns-row["receipt_ns"])/1e9
            header_age = (ros_ns-row["stamp_ns"])/1e9 if row["stamp_ns"] is not None else None
            warnings = []
            if header_age is not None:
                if row["stamp_ns"]==0:
                    warnings.append("ZERO_STAMP")
                if header_age < -.05:
                    warnings.append("FUTURE_OR_CLOCK_MISMATCH")
                elif header_age > stale_s:
                    warnings.append("OLD_HEADER_OR_CLOCK_MISMATCH")
            if row["values"].get("schema_valid") is False:
                warnings.append("INVALID_SCHEMA")
            result[topic] = dict(role=spec["role"],status="STALE" if age>stale_s else "RECEIVING",count=row["count"],
                                 receipt_hz=(len(receipts)-1)/dt if dt else None,receipt_age_s=age,header_age_s=header_age,
                                 stamp_ns=row["stamp_ns"],receipt_monotonic_ns=row["receipt_ns"],
                                 duplicates=row["duplicates"],backwards=row["backwards"],warnings=warnings,
                                 values=row["values"],signals=row["signals"])
        return dict(monotonic_ns=monotonic_ns,ros_now_ns=ros_ns,topics=result,
                    note="Asynchronous latest samples; not time-aligned. Receipt rate uses bounded recent history; stale means retained old data, not zero.")


class Recorder:
    def __init__(self, directory, max_bytes, config):
        self.directory, self.limit, self.bytes, self.omitted = directory, max_bytes, 0, 0
        self.file = None
        if directory is not None:
            directory.mkdir(parents=True,exist_ok=False)
            self.file = (directory/"messages.jsonl").open("x")
            (directory/"config.json").write_text(encode(config)+"\n")

    def add(self, event):
        if self.file is None:
            return
        data = encode(event)+"\n"
        length = len(data.encode("utf-8"))
        if self.bytes+length > self.limit:
            self.omitted += 1
            return
        self.file.write(data)
        self.bytes += length

    def close(self, final):
        if self.file is not None:
            self.file.close()
            (self.directory/"final_state.json").write_text(encode(final)+"\n")
            (self.directory/"recording_status.json").write_text(encode(dict(bytes=self.bytes,omitted_messages=self.omitted,
                complete_raw_log=self.omitted==0,note="See final_state errors/interrupted for collection status."))+"\n")


def display(state, errors, omitted):
    fmt = lambda v: "N/A" if v is None else f"{v:+.3f}" if isinstance(v,(int,float)) else str(v)
    vec = lambda v: "N/A" if v is None else "("+", ".join(fmt(x) for x in v)+")"
    lines = ["NINO LIVE STATE — READ ONLY", "Latest asynchronous samples; no motor commands sent."]
    for topic,row in state["topics"].items():
        line = topic+"  "+row["status"]
        if row["status"]=="WAITING":
            lines.append(line)
            continue
        line += f"  rx={fmt(row['receipt_hz'])} Hz age={fmt(row['receipt_age_s'])}s header_age={fmt(row['header_age_s'])}s"
        if row["warnings"]:
            line += " ["+",".join(row["warnings"])+"]"
        lines.append(line)
        v = row["values"]
        role = row["role"]
        if role=="imu":
            lines += ["  accel XYZ m/s²="+vec(v["acceleration_m_s2"])+" gyro XYZ rad/s="+vec(v["gyro_rad_s"]),
                      "  RPY deg (reported IMU frame)="+vec(v["rpy_in_reported_imu_frame_deg"])]
        elif role=="joints":
            for joint in v["joints"]:
                lines.append(f"  {joint['name']}: pos={fmt(joint['position_rad'])} rad vel={fmt(joint['velocity_rad_s'])} rad/s effort={fmt(joint['effort_Nm'])} N·m [{v['effort_kind']}]")
        elif role=="odom":
            lines.append("  estimated position m="+vec(v["position_m"])+" v m/s="+vec(v["linear_m_s"])+" omega rad/s="+vec(v["angular_rad_s"]))
        elif role=="command":
            lines.append("  COMMAND v m/s="+vec(v["linear_m_s"])+" omega rad/s="+vec(v["angular_rad_s"]))
        elif role=="drive":
            fields=v["fields"]
            if not v["schema_valid"]:
                lines.append("  "+v["error"])
            else:
                for label,keys in (("wheel target rad/s",("left_target_rad_s","right_target_rad_s")),
                                   ("wheel reported rad/s",("left_actual_rad_s","right_actual_rad_s")),
                                   ("PI torque COMMAND N·m",("left_pi_nm","right_pi_nm")),
                                   ("applied torque COMMAND N·m",("left_applied_nm","right_applied_nm"))):
                    lines.append("  "+label+" L/R="+vec([fields.get(key) for key in keys]))
        elif role=="torque_command":
            lines.append("  actuator torque COMMAND N·m="+vec(v["values_Nm"])+" (producer-defined order)")
        elif role=="scan":
            lines.append(f"  nearest={fmt(v['nearest_m'])} m finite returns={v['finite_returns']}/{v['beams']}")
        elif role=="battery":
            lines.append(f"  battery V={fmt(v['voltage'])} A={fmt(v['current'])} °C={fmt(v['temperature'])} fraction={fmt(v['percentage'])}")
        for signal in row.get("signals",[]):
            lines.append(f"  {signal['name']}={fmt(signal['value'])} {signal['unit']} [{signal['kind']}; user-configured]"+(" "+signal["error"] if signal["error"] else ""))
    lines += ["Torque/current unavailable unless provided by driver; commands are not shaft measurements.",
              "Joint effort classification is unverified by default. Header age depends on clock synchronization."]
    if omitted:
        lines.append(f"RAW LOG LIMIT REACHED: {omitted} messages not recorded; live display continues.")
    lines.extend("ERROR: "+error for error in errors[-5:])
    return "\n".join(lines)


def main(args=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration",type=float,default=0,help="seconds; 0 runs until Ctrl+C")
    parser.add_argument("--display-hz",type=float,default=2)
    parser.add_argument("--stale-seconds",type=float,default=.5)
    parser.add_argument("--record",type=Path,help="new directory; record full per-message data, not just display snapshots")
    parser.add_argument("--max-log-mb",type=float,default=256)
    parser.add_argument("--signals",type=Path,help="JSON mapping of driver-specific current/torque/temperature fields")
    parser.add_argument("--effort-kind",choices=sorted(KINDS),default="reported_unverified",help="JointState.effort classification supplied by you, not auto-verified")
    parser.add_argument("--json",action="store_true",help="print display snapshots as JSON lines")
    for role,(topic,_) in DEFAULTS.items():
        parser.add_argument("--"+role.replace("_","-")+"-topic",default=topic)
    opt=parser.parse_args(args)
    if not all(math.isfinite(v) for v in (opt.duration,opt.display_hz,opt.stale_seconds,opt.max_log_mb)) or opt.duration<0 or not .2<=opt.display_hz<=20 or opt.stale_seconds<=0 or not 0<opt.max_log_mb<=4096:
        parser.error("finite duration>=0, display-hz 0.2..20, stale-seconds>0, max-log-mb>0..4096 required")
    try:
        signals=load_signals(opt.signals)
        specs={}
        for role,(_,types) in DEFAULTS.items():
            topic=getattr(opt,role+"_topic")
            if not topic.startswith("/") or topic in specs:
                raise ValueError("default topics must be distinct absolute topic names")
            specs[topic]=dict(role=role,types=types,signals=[])
        for signal in signals:
            spec=specs.setdefault(signal["topic"],dict(role="custom",types=[signal["type"]],signals=[]))
            if signal["type"] not in spec["types"]:
                raise ValueError("conflicting message types on "+signal["topic"])
            spec["signals"].append(signal)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.error(str(exc))
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.executors import ExternalShutdownException
        from rclpy.qos import qos_profile_sensor_data
        from rosidl_runtime_py.utilities import get_message
        from rosidl_runtime_py.convert import message_to_ordereddict
    except ImportError as exc:
        raise SystemExit("Source /opt/ros/jazzy/setup.bash and driver workspace, then use /usr/bin/python3. "+str(exc))
    recorder=Recorder(opt.record.expanduser().resolve() if opt.record else None,int(opt.max_log_mb*1024*1024),
                      dict(started_utc=datetime.now(timezone.utc).isoformat(),specs=specs,options={k:str(v) if isinstance(v,Path) else v for k,v in vars(opt).items()},
                           source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),command_publishers_created=0))
    store=StateStore(specs,opt.effort_kind)
    subscriptions, errors = {}, []
    node=None
    interrupted=False
    last={"topics":{}}
    try:
        rclpy.init(args=[])
        node=Node("nino_readonly_state_monitor",enable_rosout=False,start_parameter_services=False)
        start=time.monotonic()
        next_graph=next_display=0

        def callback_for(topic):
            def receive(msg):
                try:
                    receipt=time.monotonic_ns()
                    ros_ns=node.get_clock().now().nanoseconds
                    data=message_to_ordereddict(msg)
                    store.put(topic,data,receipt,ros_ns)
                    recorder.add(dict(topic=topic,type=subscriptions[topic][1],receipt_monotonic_ns=receipt,receipt_ros_ns=ros_ns,
                                      header_stamp_ns=stamp_ns(data),message=data))
                except Exception as exc:
                    error=topic+": "+str(exc)
                    if error not in errors:
                        errors.append(error)
            return receive

        while rclpy.ok() and (opt.duration==0 or time.monotonic()-start<opt.duration):
            now=time.monotonic()
            if now>=next_graph:
                next_graph=now+2
                graph=dict(node.get_topic_names_and_types())
                for topic,spec in specs.items():
                    observed=graph.get(topic,[])
                    if topic not in subscriptions and observed:
                        if len(observed)!=1 or observed[0] not in spec["types"]:
                            error=topic+": incompatible/ambiguous types "+str(observed)
                            if error not in errors: errors.append(error)
                            continue
                        try:
                            sub=node.create_subscription(get_message(observed[0]),topic,callback_for(topic),qos_profile_sensor_data)
                            subscriptions[topic]=(sub,observed[0])
                        except Exception as exc:
                            error=topic+": "+str(exc)
                            if error not in errors: errors.append(error)
            rclpy.spin_once(node,timeout_sec=.02)
            if now>=next_display:
                next_display=now+1/opt.display_hz
                last=store.snapshot(time.monotonic_ns(),node.get_clock().now().nanoseconds,opt.stale_seconds)
                last.update(errors=errors.copy(),raw_messages_omitted=recorder.omitted)
                if opt.json:
                    print(encode(last),flush=True)
                else:
                    print(("\033[2J\033[H" if sys.stdout.isatty() else "")+display(last,errors,recorder.omitted),flush=True)
    except (KeyboardInterrupt,ExternalShutdownException):
        interrupted=True
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if node is not None:
            last=store.snapshot(time.monotonic_ns(),node.get_clock().now().nanoseconds,opt.stale_seconds)
            node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
        last.update(errors=errors,interrupted=interrupted,command_publishers_created=0,raw_messages_omitted=recorder.omitted)
        recorder.close(last)
    return 1 if errors else 0


if __name__=="__main__":
    raise SystemExit(main())
