"""Bounded, read-only hardware inventory; runnable without building nino_pi.

No command publishers, parameter writes, driver launches or motion tests.
ROS imports are delayed so report/measurement logic can be tested without ROS.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time


TYPES = {
    "sensor_msgs/msg/Imu": "imu",
    "sensor_msgs/msg/JointState": "encoder",
    "sensor_msgs/msg/LaserScan": "lidar",
    "nav_msgs/msg/Odometry": "odom",
    "geometry_msgs/msg/Twist": "command",
    "geometry_msgs/msg/TwistStamped": "command",
    "tf2_msgs/msg/TFMessage": "tf",
    "diagnostic_msgs/msg/DiagnosticArray": "diagnostics",
    "rosgraph_msgs/msg/Clock": "clock",
}
PARAMETERS = [
    "use_sim_time", "input_topic", "output_topic", "cmd_vel_topic",
    "odom_topic", "imu_topic", "feedback_topic", "base_frame_id",
    "odom_frame_id", "left_wheel_joint", "right_wheel_joint",
    "wheel_radius", "wheel_separation", "velocity_kp", "velocity_ki",
    "pi_integrator_profile", "control_rate", "command_timeout",
    "accept_cmd_vel", "accept_torque", "publish_odom_tf",
]
PACKAGE_HINT = re.compile(r"nino|cybergear|motor|encoder|lidar|imu|bno|mpu|xsens|micro_ros|controller|diff_drive", re.I)
POWER_HINT = re.compile(r"under.?voltage|voltage.*(low|alarm)|brown.?out|throttl", re.I)


def clean(value):
    """Strict JSON: preserve non-finite values explicitly, never silently zero."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def save(path, data):
    path.write_text(json.dumps(clean(data), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * p
    lo = int(pos)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (pos - lo)


def stamp_ns(stamp):
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def vector(v):
    return [float(v.x), float(v.y), float(v.z)]


def quaternion(q):
    return [float(q.x), float(q.y), float(q.z), float(q.w)]


def extract(msg, kind):
    """Store compact measurements, not complete laser arrays or arbitrary secrets."""
    result = {}
    if hasattr(msg, "header"):
        result.update(stamp_ns=stamp_ns(msg.header.stamp), frame_id=msg.header.frame_id)
    if kind == "imu":
        result.update(acceleration=vector(msg.linear_acceleration), gyro=vector(msg.angular_velocity),
                      orientation=quaternion(msg.orientation),
                      orientation_available=bool(msg.orientation_covariance[0] != -1),
                      acceleration_available=bool(msg.linear_acceleration_covariance[0] != -1),
                      gyro_available=bool(msg.angular_velocity_covariance[0] != -1))
    elif kind == "encoder":
        result.update(names=list(msg.name), position=list(msg.position), velocity=list(msg.velocity),
                      effort=list(msg.effort))
    elif kind == "lidar":
        ranges = list(msg.ranges)
        good = [v for v in ranges if math.isfinite(v) and msg.range_min <= v <= msg.range_max]
        result.update(beams=len(ranges), finite_in_range=len(good),
                      nan_count=sum(math.isnan(v) for v in ranges),
                      positive_infinity_count=sum(v == math.inf for v in ranges),
                      invalid_range_count=sum(v == -math.inf or (math.isfinite(v) and not msg.range_min <= v <= msg.range_max) for v in ranges),
                      min_return_m=min(good) if good else None, max_return_m=max(good) if good else None,
                      range_min_m=float(msg.range_min), range_max_m=float(msg.range_max),
                      angle_min_rad=float(msg.angle_min), angle_max_rad=float(msg.angle_max),
                      angle_increment_rad=float(msg.angle_increment), scan_time_s=float(msg.scan_time),
                      time_increment_s=float(msg.time_increment))
    elif kind == "odom":
        result.update(child_frame_id=msg.child_frame_id, position=vector(msg.pose.pose.position),
                      orientation=quaternion(msg.pose.pose.orientation),
                      linear=vector(msg.twist.twist.linear), angular=vector(msg.twist.twist.angular))
    elif kind == "command":
        twist = msg.twist if hasattr(msg, "twist") else msg
        result.update(linear=vector(twist.linear), angular=vector(twist.angular))
    elif kind == "tf":
        result["transforms"] = [dict(parent=t.header.frame_id, child=t.child_frame_id,
                                    stamp_ns=stamp_ns(t.header.stamp), translation=vector(t.transform.translation),
                                    rotation=quaternion(t.transform.rotation)) for t in msg.transforms]
    elif kind == "diagnostics":
        # Do not dump arbitrary diagnostic key/value strings (may contain credentials).
        result["statuses"] = [dict(name=s.name, level=int(s.level), message=s.message[:300]) for s in msg.status]
    elif kind == "clock":
        result["clock_ns"] = stamp_ns(msg.clock)
    elif hasattr(msg, "data") and not isinstance(msg.data, str):
        result["data"] = list(msg.data)
    return result


def measurement_issues(data, kind):
    issues = []
    numeric_fields = ("acceleration", "gyro", "orientation", "position", "velocity", "effort", "linear", "angular", "data")
    if any(not math.isfinite(x) for key in numeric_fields for x in data.get(key, []) if isinstance(x, (int, float))):
        issues.append("nonfinite_measurement")
    if kind == "encoder":
        n = len(data["names"])
        if not n or len(set(data["names"])) != n:
            issues.append("missing_or_duplicate_joint_names")
        for key in ("position", "velocity", "effort"):
            if len(data[key]) not in (0, n):
                issues.append("joint_" + key + "_length_mismatch")
        if not data["velocity"]:
            issues.append("joint_velocity_unavailable")
    if kind in ("imu", "odom") and data.get("orientation_available", True):
        norm = math.sqrt(sum(x * x for x in data["orientation"]))
        if not math.isfinite(norm) or abs(norm - 1) > .05:
            issues.append("quaternion_not_normalized")
    if kind == "imu":
        for key in ("orientation", "acceleration", "gyro"):
            if not data[key + "_available"]:
                issues.append(key + "_unavailable")
    if kind == "lidar":
        if data["nan_count"] or data["invalid_range_count"]:
            issues.append("invalid_scan_ranges")
        # +inf is a valid no-return representation, not proof of a broken driver.
        if not data["beams"] or not math.isfinite(data["range_max_m"]) or not 0 <= data["range_min_m"] < data["range_max_m"]:
            issues.append("invalid_scan_geometry")
    return issues


class TopicStats:
    def __init__(self):
        self.receipts, self.stamps, self.ages = [], [], []
        self.frames, self.sources, self.issues = Counter(), Counter(), Counter()
        self.last_stamp = None
        self.duplicates = self.backwards = self.zero_stamps = self.nonzero_commands = 0
        self.axes = defaultdict(list)

    def add(self, data, kind, receipt_ns, ros_now_ns, source):
        self.receipts.append(receipt_ns)
        self.sources[source] += 1
        self.issues.update(measurement_issues(data, kind))
        if "frame_id" in data:
            self.frames[data["frame_id"]] += 1
            if not data["frame_id"]:
                self.issues["empty_frame_id"] += 1
        stamp = data.get("stamp_ns")
        if stamp is not None:
            self.zero_stamps += int(stamp == 0)
            if self.last_stamp is not None:
                self.duplicates += int(stamp == self.last_stamp)
                self.backwards += int(stamp < self.last_stamp)
            self.last_stamp = stamp
            self.stamps.append(stamp)
            self.ages.append((ros_now_ns - stamp) / 1e9)
        for key in ("acceleration", "gyro"):
            for axis, value in zip("xyz", data.get(key, [])):
                if math.isfinite(value):
                    self.axes[key + "_" + axis].append(value)
        if kind == "encoder":
            for name,value in zip(data["names"],data["velocity"]):
                if math.isfinite(value):
                    self.axes["joint_velocity_rad_s:" + name].append(value)
        if kind == "command" and any(abs(v) > 1e-6 for v in data["linear"] + data["angular"]):
            self.nonzero_commands += 1

    def report(self, end_ns, stale_s):
        dt = (self.receipts[-1] - self.receipts[0]) / 1e9 if len(self.receipts) > 1 else 0
        positive = [(b - a) / 1e9 for a, b in zip(self.stamps, self.stamps[1:]) if b > a]
        return dict(received=len(self.receipts),
                    receipt_hz=(len(self.receipts) - 1) / dt if dt else None,
                    header_hz=1 / statistics.mean(positive) if positive else None,
                    max_receipt_gap_s=max(((b-a)/1e9 for a,b in zip(self.receipts,self.receipts[1:])), default=None),
                    last_receipt_age_s=(end_ns-self.receipts[-1])/1e9 if self.receipts else None,
                    duplicate_stamps=self.duplicates, backward_stamps=self.backwards, zero_stamps=self.zero_stamps,
                    stamp_age_s={"p05":quantile(self.ages,.05), "median":quantile(self.ages,.5),
                                 "p95":quantile(self.ages,.95), "max":max(self.ages,default=None)},
                    future_stamps=sum(v < -.05 for v in self.ages),
                    older_than_threshold=sum(v > stale_s for v in self.ages),
                    frame_ids=dict(self.frames), publisher_samples=dict(self.sources), issues=dict(self.issues),
                    nonzero_commands=self.nonzero_commands,
                    axis_statistics={k:dict(mean=statistics.mean(v),std=statistics.pstdev(v),min=min(v),max=max(v)) for k,v in self.axes.items()})


def command_output(argv):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
        return dict(argv=argv, returncode=done.returncode, stdout=done.stdout[-150000:], stderr=done.stderr[-2000:])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(argv=argv, error=str(exc))


def throttled(raw):
    match = re.search(r"throttled=(0x[0-9a-fA-F]+)", raw)
    if not match:
        return {"status":"unavailable"}
    value = int(match[1],16)
    return dict(status="observed", raw=value, under_voltage_now=bool(value&1),
                frequency_capped_now=bool(value&2), throttled_now=bool(value&4), soft_temperature_limit_now=bool(value&8),
                under_voltage_since_boot=bool(value&(1<<16)), frequency_capped_since_boot=bool(value&(1<<17)),
                throttled_since_boot=bool(value&(1<<18)), soft_temperature_limit_since_boot=bool(value&(1<<19)))


def power_snapshot():
    result = {"wall_time_ns":time.time_ns(), "hwmon":[], "kernel":{}, "throttled":{"status":"unavailable"}}
    for directory in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        row = {"path":str(directory)}
        for item in [directory/"name", *directory.glob("in*_lcrit_alarm"), *directory.glob("in*_input"), *directory.glob("temp*_input")]:
            try:
                row[item.name] = item.read_text().strip()
            except OSError as exc:
                row[item.name] = {"error":str(exc)}
        result["hwmon"].append(row)
    if shutil.which("vcgencmd"):
        result["vcgencmd"] = command_output(["vcgencmd","get_throttled"])
        result["throttled"] = throttled(result["vcgencmd"].get("stdout", ""))
    if shutil.which("journalctl"):
        log = command_output(["journalctl","-k","-b","--no-pager","-o","short-monotonic","-n","1000"])
        result["kernel"] = {k:v for k,v in log.items() if k != "stdout"}
        result["kernel"]["matching_lines"] = [line for line in log.get("stdout","").splitlines() if POWER_HINT.search(line)]
        result["kernel"]["scope"] = "last_1000_kernel_lines_this_boot; absence is not proof of healthy power"
    return result


def host_inventory():
    result = {"architecture":os.uname().machine, "kernel":os.uname().release,
              "environment":{k:os.environ.get(k) for k in ("ROS_DISTRO","ROS_DOMAIN_ID","RMW_IMPLEMENTATION","ROS_LOCALHOST_ONLY","ROS_AUTOMATIC_DISCOVERY_RANGE")},
              "packages":{}, "local_process_hints":[]}
    for name in ("/etc/os-release", "/proc/device-tree/model", "/proc/sys/kernel/random/boot_id"):
        try:
            result[name] = Path(name).read_text().replace("\x00", "").strip()
        except OSError as exc:
            result[name] = {"error":str(exc)}
    try:
        from ament_index_python.packages import get_packages_with_prefixes
        for name, prefix in sorted(get_packages_with_prefixes().items()):
            if PACKAGE_HINT.search(name):
                binaries = Path(prefix)/"lib"/name
                result["packages"][name] = dict(prefix=prefix, executables=[p.name for p in sorted(binaries.glob("*")) if p.is_file() and os.access(p,os.X_OK)])
    except ImportError as exc:
        result["package_inventory_error"] = str(exc)
    # Process names/executable paths only: no environment or command-line secrets.
    for process in Path("/proc").glob("[0-9]*"):
        try:
            name = (process/"comm").read_text().strip()
            executable = str((process/"exe").resolve(strict=True))
            if PACKAGE_HINT.search(name + " " + executable):
                result["local_process_hints"].append(dict(pid=int(process.name),name=name,executable=executable))
        except OSError:
            pass
    return result


def endpoint_data(endpoint):
    qos = endpoint.qos_profile
    return dict(node=(endpoint.node_namespace.rstrip("/")+"/"+endpoint.node_name),
                gid=bytes(endpoint.endpoint_gid).hex(), type=endpoint.topic_type,
                qos=dict(reliability=getattr(qos.reliability,"name",str(qos.reliability)),
                         durability=getattr(qos.durability,"name",str(qos.durability)),depth=qos.depth))


def publisher_gid(info):
    # Some Jazzy builds provide only timestamps, without a per-message GID.
    # Never attribute such a message to the first/only visible endpoint.
    value = info.get("publisher_gid") if isinstance(info,dict) else getattr(info,"publisher_gid",None)
    return bytes(value).hex() if value is not None else None


def markdown(report):
    lines = ["# Kiểm kê hardware Nino — chỉ đọc", "", "Không phát lệnh motor, không đổi parameter hoặc khởi động driver.",
             "Quan sát trong ROS domain hiện tại; ROS graph không chứng minh node ở trên Pi này hoặc nối tới motor thật.",
             "", "## Kết luận và phần còn thiếu", ""]
    for kind,label in (("imu","IMU"),("encoder","Encoder/joint feedback"),("lidar","LiDAR"),("odom","Odometry")):
        names = [name for name,t in report["topics"].items() if t["kind"] == kind]
        live = [name for name in names if report["measurements"].get(name,{}).get("received",0)]
        lines.append(f"- **{label}:** " + ("nhận dữ liệu: " + ", ".join(live) if live else "chưa nhận dữ liệu; kiểm tra source workspace, domain và driver") + ".")
    for warning in report["warnings"]:
        lines.append("- " + warning)
    lines += ["- **Chiều trục IMU, chiều encoder và đơn vị thực:** chưa xác minh từ quan sát đứng yên. TF chỉ ghi cấu hình khai báo; cần đối chiếu lắp đặt.",
              "- **Vị trí PI:** xem `parameters.json` cho gain/topic đọc được và `graph.mmd` cho luồng khai báo. Có gain không chứng minh PI đang chạy hoặc nằm trên Pi; cần code/firmware và đối chiếu executable/host.",
              "- **Vận tốc odom không chứng minh encoder vật lý hoạt động; joint feedback có thể là dữ liệu giả/lệnh echo.**", "", "## Driver/node quan sát được", "",
              "Package có trong overlay đang source: " + (", ".join(report["installed_package_hints"]) or "không có package khớp bộ lọc tên") + ". Đây chỉ là inventory, không chứng minh driver chạy.", "",
              "| Topic | Publisher node quan sát được | Subscriber node quan sát được |", "|---|---|---|"]
    def names(endpoints):
        return ", ".join(sorted({p["node"] for p in endpoints})).replace("|","/") or "N/A"
    for topic,row in sorted(report["topics"].items()):
        if row["kind"] in ("imu","encoder","lidar","odom","command","feedback_extra"):
            lines.append(f"| {topic.replace('|','/')} | {names(row['publishers'])} | {names(row['subscribers'])} |")
    lines += ["", "Node khai báo tham số PI (chưa chứng minh vòng điều khiển đang thực thi):", ""]
    if not report["pi_parameter_evidence"]:
        lines.append("- Chưa đọc được velocity_kp/velocity_ki; PI có thể ở firmware, dùng tên tham số khác, hoặc service chưa mở.")
    for name,values in report["pi_parameter_evidence"].items():
        lines.append(f"- `{name}`: `{values}`.")
    lines += ["", "## Dữ liệu nhận được", "",
              "| Topic | Loại | Số mẫu | Hz nhận | Hz header | Header lùi/zero |", "|---|---|---:|---:|---:|---|"]
    for name,t in sorted(report["topics"].items()):
        if t["kind"] == "graph_only":
            continue
        s = report["measurements"].get(name,{})
        fmt = lambda v: "N/A" if v is None else f"{v:.2f}"
        lines.append(f"| {name.replace('|','/')} | {t['kind']} | {s.get('received',0)} | {fmt(s.get('receipt_hz'))} | {fmt(s.get('header_hz'))} | {s.get('backward_stamps',0)}/{s.get('zero_stamps',0)} |")
    lines += ["", "Hz nhận tính bằng monotonic clock. Age header so với ROS clock của collector; khác clock/domain có thể gây sai age, không tự coi là network latency.",
              f"Ngưỡng chẩn đoán age: {report['stale_threshold_s']} s, không phải tiêu chuẩn an toàn. Không có yêu cầu rate phần cứng nên không tự chấm đạt rate.",
              "Twist không có header: chỉ biết thời gian nhận, không đo được tuổi lệnh tại nguồn.",
              "Scan +inf có thể là no return hợp lệ; file samples ghi số lượng finite/invalid.", "", "## Nguồn điện", ""]
    for index, power in enumerate(report["power"]):
        lines.append(f"- Snapshot {index+1}: get_throttled = `{power['throttled']}`.")
        for sensor in power["hwmon"]:
            fields = {k:v for k,v in sensor.items() if k != "path"}
            lines.append(f"  - hwmon `{sensor['path']}`: `{fields}` (in*_input thường mV, temp*_input thường milli°C; cần đối chiếu driver).")
        access = {k:v for k,v in power["kernel"].items() if k in ("returncode","error","stderr")}
        lines.append(f"  - Kernel log access: `{access}`.")
        lines.extend("  - " + line for line in power["kernel"].get("matching_lines",[]))
    lines += ["", "Không có alarm/log không chứng minh nguồn đã sửa. Bit lịch sử chỉ cho biết từ lần boot này; thiếu quyền đọc được ghi unavailable.",
              "", "## Luồng lệnh/cảm biến", "", "Xem `graph.mmd` (Mermaid) hoặc `graph.json`. Mũi tên là publisher/topic/subscriber đã quan sát, không chứng minh node thực sự forward lệnh.",
              "`tf.json` ghi parent/child, publisher GID và transform khai báo; duplicate TF authority là cảnh báo cần kiểm tra.",
              "`samples.jsonl` ghi dữ liệu rút gọn kèm timestamp/GID. Laser ranges đầy đủ và diagnostic key/value tùy ý không được lưu.",
              "", "**Không có thử chuyển động trong công cụ này. Không có kết luận sẵn sàng triển khai từ audit tĩnh.**", ""]
    return "\n".join(lines)


def graph_mermaid(graph):
    # Escape every external name; never interpret node/topic text as Mermaid syntax.
    def label(value):
        return "".join(ch if ch.isalnum() or ch in "/_.- " else f"#{ord(ch)};" for ch in value)
    lines, ids = ["flowchart LR"], {}
    def add(key, text):
        if key not in ids:
            ids[key] = "n" + str(len(ids))
            lines.append(f'  {ids[key]}["{label(text)}"]')
        return ids[key]
    for topic, data in sorted(graph.items()):
        t = add(("topic",topic),"topic " + topic)
        for direction,edges in (("publishers",data["publishers"]),("subscribers",data["subscribers"])):
            for endpoint in edges:
                n = add(("node",endpoint["node"]),endpoint["node"])
                lines.append(f"  {n} --> {t}" if direction == "publishers" else f"  {t} --> {n}")
    return "\n".join(lines) + "\n"


def subscription_callback(topic, kind, receiver):
    # rclpy requires exactly two callback arguments for MessageInfo delivery.
    def callback(message, info):
        receiver(topic, kind, message, info)
    return callback


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration",type=float,default=30,help="wall-clock seconds, 5..300")
    parser.add_argument("--output",type=Path,required=True,help="new output directory; never overwritten")
    parser.add_argument("--stale-seconds",type=float,default=.5)
    parser.add_argument("--topic",action="append",default=["/nino_drive/diagnostics", "/wheel_effort_controller/commands"],help="extra Float64MultiArray topic to observe")
    parser.add_argument("--max-samples",type=int,default=200000,help="raw log ceiling; hitting it is reported")
    opt = parser.parse_args(args)
    if not math.isfinite(opt.duration) or not 5 <= opt.duration <= 300 or not math.isfinite(opt.stale_seconds) or opt.stale_seconds <= 0 or opt.max_samples < 1:
        parser.error("duration 5..300, finite positive stale-seconds, max-samples >=1 required")
    opt.output = opt.output.expanduser().resolve()
    opt.output.mkdir(parents=True,exist_ok=False)
    started_utc = datetime.now(timezone.utc).isoformat()
    save(opt.output/"status.json",dict(status="started",command_publishers_created=0))
    host = host_inventory()
    save(opt.output/"host.json",host)
    powers = [power_snapshot()]
    save(opt.output/"power.json",powers)
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.parameter import parameter_value_to_python
        from rcl_interfaces.srv import GetParameters, ListParameters
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        save(opt.output/"status.json",dict(status="ROS_unavailable",error=str(exc),command_publishers_created=0))
        raise SystemExit("Source /opt/ros/jazzy/setup.bash rồi chạy bằng /usr/bin/python3. Inventory đã được lưu.")
    node = None
    graph, selected, stats, subscriptions, tf, errors = {}, {}, {}, {}, {}, []
    graph_history, parameters, param_pending, param_waiting, clients, nodes_seen = [], {}, {}, {}, [], set()
    sample_count = omitted = 0
    interrupted = False
    rclpy.init(args=[])
    raw = (opt.output/"samples.jsonl").open("x",encoding="utf-8")
    try:
        node = Node("nino_readonly_audit_"+str(os.getpid()),enable_rosout=False,start_parameter_services=False)
        start = time.monotonic()
        next_graph = 0

        def receive(topic,kind,msg,info):
            nonlocal sample_count, omitted
            try:
                data = extract(msg,kind)
                received = time.monotonic_ns()
                ros_now = node.get_clock().now().nanoseconds
                gid = publisher_gid(info)
                stats[topic].add(data,kind,received,ros_now,gid or "unavailable")
                if kind == "tf":
                    for transform in data["transforms"]:
                        key = (transform["parent"],transform["child"],gid)
                        tf[key] = dict(topic=topic,publisher_gid=gid,**transform)
                if sample_count < opt.max_samples:
                    raw.write(json.dumps(clean(dict(topic=topic,kind=kind,receipt_monotonic_ns=received,
                                                    receipt_ros_ns=ros_now,publisher_gid=gid,data=data)),ensure_ascii=False,allow_nan=False)+"\n")
                    sample_count += 1
                else:
                    omitted += 1
            except Exception as exc:
                error = dict(topic=topic,error=str(exc))
                if error not in errors:
                    errors.append(error)

        while time.monotonic() - start < opt.duration:
            if time.monotonic() >= next_graph:
                next_graph = time.monotonic() + 2
                snapshot = {}
                for topic,types in sorted(node.get_topic_names_and_types()):
                    if len(types) != 1:
                        errors.append(dict(topic=topic,error="multiple_types",types=types))
                        continue
                    msg_type = types[0]
                    kind = TYPES.get(msg_type,"graph_only")
                    if topic in opt.topic and msg_type == "std_msgs/msg/Float64MultiArray":
                        kind = "feedback_extra"
                    pubs = [endpoint_data(e) for e in node.get_publishers_info_by_topic(topic)]
                    subs = [endpoint_data(e) for e in node.get_subscriptions_info_by_topic(topic) if e.node_name != node.get_name()]
                    row = dict(type=msg_type,kind=kind,publishers=pubs,subscribers=subs)
                    snapshot[topic] = row
                    graph[topic] = row
                    if kind != "graph_only" and topic not in subscriptions and len(subscriptions) < 128:
                        try:
                            qos = QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT,
                                             durability=DurabilityPolicy.TRANSIENT_LOCAL if topic.endswith("/tf_static") else DurabilityPolicy.VOLATILE)
                            stats[topic] = TopicStats()
                            subscriptions[topic] = node.create_subscription(get_message(msg_type),topic,
                                subscription_callback(topic,kind,receive),qos)
                            selected[topic] = row
                        except Exception as exc:
                            errors.append(dict(topic=topic,error=str(exc)))
                graph_history.append(dict(wall_time_ns=time.time_ns(),topics=snapshot))
                # Read an allowlist only; never enumerate/set arbitrary credentials or gains.
                for name,namespace in node.get_node_names_and_namespaces():
                    full = namespace.rstrip("/")+"/"+name
                    if name == node.get_name() or full in nodes_seen or len(nodes_seen) >= 64:
                        continue
                    nodes_seen.add(full)
                    try:
                        client = node.create_client(GetParameters,full+"/get_parameters")
                        listing = node.create_client(ListParameters,full+"/list_parameters")
                        clients.extend([client,listing])
                        param_waiting[full] = (listing,client,None)
                    except Exception as exc:
                        parameters[full] = {"status":"unavailable","error":str(exc)}
            rclpy.spin_once(node,timeout_sec=.05)
            for name,(listing,client,names) in list(param_waiting.items()):
                service = listing if names is None else client
                if service.service_is_ready():
                    if names is None:
                        request = ListParameters.Request()
                        request.prefixes = PARAMETERS
                        request.depth = 0
                    else:
                        request = GetParameters.Request()
                        request.names = names
                    param_pending[name] = ("list" if names is None else "get",service.call_async(request),client,names)
                    del param_waiting[name]
            for name,(stage,future,client,names) in list(param_pending.items()):
                if future.done():
                    try:
                        if stage == "list":
                            names = sorted(set(future.result().result.names).intersection(PARAMETERS))
                            if names:
                                param_waiting[name] = (None,client,names)
                            else:
                                parameters[name] = dict(status="read_no_allowlisted_parameters",values={})
                        else:
                            values = future.result().values
                            parameters[name] = dict(status="read" if len(values)==len(names) else "parameter_response_incomplete",
                                requested=names,values={key:parameter_value_to_python(value) for key,value in zip(names,values) if value.type != 0})
                    except Exception as exc:
                        parameters[name] = dict(status="unavailable",error=str(exc))
                    del param_pending[name]
    except KeyboardInterrupt:
        interrupted = True
    except Exception as exc:
        errors.append(dict(error=str(exc)))
    finally:
        end_ns = time.monotonic_ns()
        raw.close()
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    for name in param_pending:
        parameters[name] = {"status":"read_response_not_received_in_window"}
    for name in param_waiting:
        parameters[name] = {"status":"read_service_not_ready_or_not_exposed"}
    powers.append(power_snapshot())
    measurements = {name:s.report(end_ns,opt.stale_seconds) for name,s in stats.items()}
    warnings = []
    for snapshot in graph_history:
        for topic,row in snapshot["topics"].items():
            if row["kind"] == "command" and len(row["publishers"]) > 1:
                warning = f"Nhiều publisher từng cùng xuất hiện trên {topic}: cần kiểm tra tranh quyền; graph không chứng minh họ đồng thời phát lệnh."
                if warning not in warnings:
                    warnings.append(warning)
    for topic,row in graph.items():
        if row["kind"] == "graph_only":
            continue
        if topic not in selected:
            warnings.append(f"{topic}: chưa subscribe (giới hạn 128 topic hoặc lỗi); không được coi là không có dữ liệu.")
        if not measurements.get(topic,{}).get("received",0):
            warnings.append(f"{topic}: không nhận mẫu trong cửa sổ; xem endpoint/QoS/domain, không kết luận driver chưa cài.")
    for topic,s in measurements.items():
        if "unavailable" in s["publisher_samples"]:
            warnings.append(f"{topic}: rclpy không cung cấp publisher GID từng mẫu; không gán mẫu cho node hoặc xác nhận duplicate TF authority từ mẫu. Endpoint GID vẫn có trong graph.")
        if s["issues"] or s["backward_stamps"] or s["zero_stamps"] or s["future_stamps"] or s["older_than_threshold"]:
            warnings.append(f"{topic}: có cảnh báo dữ liệu/timestamp; xem report.json.")
        if s["last_receipt_age_s"] is not None and s["last_receipt_age_s"] > opt.stale_seconds and graph[topic]["kind"] != "tf":
            warnings.append(f"{topic}: mẫu cuối cũ hơn ngưỡng chẩn đoán tại cuối phiên.")
        if s["nonzero_commands"]:
            warnings.append(f"{topic}: quan sát {s['nonzero_commands']} lệnh khác zero từ nguồn đang có; collector không phát hoặc chặn các lệnh đó.")
    by_child = defaultdict(set)
    parents_by_child = defaultdict(set)
    for (parent,child,gid) in tf:
        by_child[child].add(gid)
        parents_by_child[child].add(parent)
    for child,sources in by_child.items():
        if len(sources)>1:
            warnings.append(f"TF child {child}: nhiều publisher GID; kiểm tra duplicate authority.")
        if len(parents_by_child[child]) > 1:
            warnings.append(f"TF child {child}: có nhiều parent trong cửa sổ; kiểm tra topology và frame ownership.")
    frames = set(by_child).union(parent for parent,_,_ in tf)
    if not tf:
        warnings.append("Chưa nhận TF trong cửa sổ: chưa đối chiếu được frame sensor/base/odom.")
    for topic,row in graph.items():
        if row["kind"] in ("imu","lidar"):
            for frame in measurements.get(topic,{}).get("frame_ids",{}):
                if frame and frame not in frames:
                    warnings.append(f"{topic}: frame {frame} chưa thấy trong TF thu được; không tự kết luận mounting đúng.")
    if any(row["kind"] == "clock" for row in graph.values()) or any(p.get("values",{}).get("use_sim_time") is True for p in parameters.values()):
        warnings.append("Có /clock hoặc node use_sim_time=true: cần tách dữ liệu mô phỏng khỏi phần cứng thật; age hiện so với clock collector.")
    if omitted:
        warnings.append(f"Raw log đạt giới hạn; {omitted} mẫu không lưu raw. Statistics vẫn đếm nhưng không replay toàn bộ được.")
    if interrupted:
        warnings.append("Thu thập bị ngắt; dữ liệu là cửa sổ một phần.")
    for power in powers:
        if power["throttled"].get("under_voltage_now"):
            warnings.append("Nguồn: get_throttled báo undervoltage tại snapshot; chưa xử lý xong.")
        elif power["throttled"].get("under_voltage_since_boot"):
            warnings.append("Nguồn: có bit undervoltage lịch sử từ boot; không đồng nghĩa đang undervoltage hoặc đã sửa xong.")
        if any(str(value) == "1" for sensor in power["hwmon"] for key,value in sensor.items() if key.endswith("_lcrit_alarm")):
            warnings.append("Nguồn: hwmon có low-voltage alarm; xem power.json và driver tương ứng.")
    warnings = list(dict.fromkeys(warnings))
    report = dict(schema_version=1,status="partial" if interrupted or errors else "collected_not_hardware_certified",
                  started_utc=started_utc,finished_utc=datetime.now(timezone.utc).isoformat(),requested_duration_s=opt.duration,
                  stale_threshold_s=opt.stale_seconds,command_publishers_created=0,
                  topics=graph,measurements=measurements,power=powers,warnings=warnings,
                  errors=errors,raw_samples=sample_count,raw_samples_omitted=omitted,
                  installed_package_hints=list(host["packages"]),
                  pi_parameter_evidence={name:{key:value for key,value in row.get("values",{}).items() if key in ("velocity_kp","velocity_ki","pi_integrator_profile","control_rate")}
                                         for name,row in parameters.items() if any(key in row.get("values",{}) for key in ("velocity_kp","velocity_ki"))},
                  axis_sign_verified=False,pi_execution_location="unverified")
    for name,data in (("report.json",report),("parameters.json",parameters),("graph.json",graph_history),
                      ("tf.json",list(tf.values())),("power.json",powers)):
        save(opt.output/name,data)
    (opt.output/"graph.mmd").write_text(graph_mermaid(graph))
    (opt.output/"REPORT.md").write_text(markdown(report))
    save(opt.output/"status.json",dict(status=report["status"],command_publishers_created=0,interrupted=interrupted,errors=errors))
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(opt.output.iterdir()) if p.is_file()}
    hashes["collector_source"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save(opt.output/"sha256.json",hashes)
    print("Đã lưu audit chỉ đọc:",opt.output/"REPORT.md")
    return 1 if errors or interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
