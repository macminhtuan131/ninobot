"""ROS adapter for GUI data workflows. No direct final-command publisher."""
import json
import math
import time
from .data_workflow import ClearWindow


def parameter_value(p):
    return {1: p.bool_value, 2: p.integer_value, 3: p.double_value,
            4: p.string_value, 8: list(p.double_array_value)}.get(p.type)


class DataIO:
    def __init__(self, node, emit):
        from geometry_msgs.msg import Twist
        from sensor_msgs.msg import LaserScan
        from nav2_msgs.msg import CollisionMonitorState
        from std_srvs.srv import SetBool, Trigger
        from rcl_interfaces.srv import GetParameters
        from lifecycle_msgs.srv import GetState
        from rclpy.qos import qos_profile_sensor_data
        from tf2_ros import Buffer, TransformListener
        self.node, self.emit = node, emit
        self.Twist, self.SetBool, self.Trigger = Twist, SetBool, Trigger
        self.GetParameters, self.GetState = GetParameters, GetState
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, node)
        self.scene = ClearWindow(time.monotonic)
        self.prepared = False
        self.gate_owned = False
        self.publisher = None
        self.target = (0., 0.)
        self.final = None
        self.final_at = float("-inf")
        self.params = {}
        self.param_at = {}
        self.last_query = 0.
        self.last_pub = 0.
        self.last_status = 0.
        self.pending = {}
        self.prepare_queue = []
        self.prepare_future = None
        self.prepare_at = 0.
        self.preparing_activates = False
        self.clients = {"gate_enable": node.create_client(SetBool, "/nino_command_gate/enable"),
                        "gate_mode": node.create_client(SetBool, "/nino_command_gate/navigation_mode"),
                        "gate_reset": node.create_client(Trigger, "/nino_command_gate/reset_stop")}
        for name in ("nino_command_gate", "velocity_smoother", "collision_monitor"):
            self.clients[name] = node.create_client(GetParameters, "/" + name + "/get_parameters")
        for name in ("velocity_smoother", "collision_monitor"):
            self.clients[name + "_state"] = node.create_client(GetState, "/" + name + "/get_state")
        self.subs = [node.create_subscription(Twist, "/cmd_vel", self.receive_final, 10),
                     node.create_subscription(LaserScan, "/scan_raw", self.scan, qos_profile_sensor_data),
                     node.create_subscription(CollisionMonitorState, "/collision_monitor_state",
                                              lambda m: self.scene.monitor(int(m.action_type)), 10)]

    def receive_final(self, msg):
        self.final = (float(msg.linear.x), float(msg.angular.z))
        self.final_at = time.monotonic()

    def scan(self, msg):
        import rclpy.time
        try:
            transform = self.buffer.lookup_transform("base_footprint", msg.header.frame_id, rclpy.time.Time())
            t, q = transform.transform.translation, transform.transform.rotation
            # Floor protocol uses a horizontal, planar scanner. Reject tilt instead of guessing.
            if abs(q.x) > .01 or abs(q.y) > .01:
                raise ValueError("LiDAR tilted")
            yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            polygon = self.params.get("collision_monitor", {}).get("StopZone.points")
            points = json.loads(polygon) if isinstance(polygon, str) else None
            expected = [[.46, .34], [.46, -.34], [-.40, -.34], [-.40, .34]]
            if points != expected:
                raise ValueError("StopZone differs from reviewed clear-floor envelope")
            inside = valid = 0
            for i, r in enumerate(msg.ranges):
                if math.isfinite(r) and msg.range_min <= r <= msg.range_max:
                    valid += 1
                    angle = yaw + msg.angle_min + i*msg.angle_increment
                    x, y = t.x + r*math.cos(angle), t.y + r*math.sin(angle)
                    inside += int(-.40 <= x <= .46 and -.34 <= y <= .34)
            self.scene.scan(inside, valid > 0)
        except Exception:
            self.scene.scan(999, False)

    def ownership_problems(self):
        errors = []
        own = self.node.get_name()
        if any(p.node_name != own for p in self.node.get_publishers_info_by_topic("/cmd_vel_teleop")):
            errors.append("Có publisher teleop khác")
        final = self.node.get_publishers_info_by_topic("/cmd_vel")
        if len(final) != 1 or final[0].node_name != "collision_monitor":
            errors.append("Final cmd_vel chưa do một Collision Monitor duy nhất sở hữu")
        selected = self.node.get_publishers_info_by_topic("/cmd_vel_selected")
        shaped = self.node.get_publishers_info_by_topic("/cmd_vel_smoothed")
        if len(selected) != 1 or selected[0].node_name != "nino_command_gate":
            errors.append("Thiếu / trùng command gate")
        if len(shaped) != 1 or shaped[0].node_name != "velocity_smoother":
            errors.append("Thiếu / trùng velocity smoother")
        return errors

    def problems(self):
        now = time.monotonic()
        errors = self.ownership_problems() + self.scene.problems()
        for name in ("nino_command_gate", "velocity_smoother", "collision_monitor", "velocity_smoother_state", "collision_monitor_state"):
            if now - self.param_at.get(name, float("-inf")) > 3:
                errors.append("Chưa đọc được cấu hình/lifecycle mới: " + name)
        gate = self.params.get("nino_command_gate", {})
        smoother = self.params.get("velocity_smoother", {})
        monitor = self.params.get("collision_monitor", {})
        if gate.get("max_forward") != .05 or gate.get("max_reverse") != .01 or gate.get("max_yaw") != .1 or gate.get("command_timeout") != .3:
            errors.append("Gate chưa khớp giới hạn 0,05 / 0,01 / 0,10 và timeout 0,3 s")
        if smoother.get("max_velocity") != [.05, 0., .1] or smoother.get("min_velocity") != [-.01, 0., -.1] or smoother.get("max_accel") != [.1, 0., .2] or smoother.get("max_decel") != [-.1, 0., -.2]:
            errors.append("Smoother chưa khớp ramp / giới hạn clear-floor")
        if (monitor.get("cmd_vel_in_topic") != "/cmd_vel_smoothed" or monitor.get("cmd_vel_out_topic") != "/cmd_vel"
                or monitor.get("StopZone.enabled") is not True or monitor.get("StopZone.action_type") != "stop"
                or monitor.get("StopZone.min_points") != 3 or monitor.get("base_frame_id") != "base_footprint"
                or monitor.get("scan.enabled") is not True or monitor.get("scan.topic") != "/scan_raw"):
            errors.append("Collision Monitor chưa khớp đường lệnh / StopZone / scan")
        for name in ("velocity_smoother_state", "collision_monitor_state"):
            if self.params.get(name) != 3:
                errors.append(name + " chưa ACTIVE")
        if now - self.final_at > .3 or not self.final or not all(math.isfinite(x) for x in self.final):
            errors.append("Final cmd_vel thiếu / cũ / không hữu hạn")
        return list(dict.fromkeys(errors))

    def command(self, v, w):
        if not all(math.isfinite(x) for x in (v, w)) or not -.01 <= v <= .05 or not -.1 <= w <= .1:
            raise ValueError("Reference vượt giới hạn GUI")
        self.target = (v, w)

    def prepare(self):
        if self.prepare_queue or self.prepare_future:
            raise ValueError("Đang chuẩn bị gate")
        errors = self.ownership_problems()
        if errors:
            raise ValueError("; ".join(errors))
        if not all(c.service_is_ready() for c in (self.clients["gate_enable"], self.clients["gate_mode"])):
            raise ValueError("Thiếu dịch vụ gate enable / navigation_mode")
        self.prepared = False
        self.preparing_activates = True
        self.target = (0., 0.)
        if self.publisher is None:
            self.publisher = self.node.create_publisher(self.Twist, "/cmd_vel_teleop", 10)
        self.gate_owned = True
        self.prepare_queue = [("gate_enable", False), ("gate_mode", False), ("gate_enable", True)]

    def reset_gate(self):
        if self.prepare_queue or self.prepare_future:
            raise ValueError("Đang chờ ACK gate")
        if not self.clients["gate_enable"].service_is_ready() or not self.clients["gate_reset"].service_is_ready():
            raise ValueError("Thiếu dịch vụ disable / reset_stop của gate")
        self.disable(force=True)
        self.preparing_activates = False
        self.prepare_queue = [("gate_enable", False), ("gate_reset", None)]

    def disable(self, force=False):
        owned = getattr(self, "gate_owned", False) or self.prepared or bool(self.prepare_queue) or self.prepare_future is not None
        self.target = (0., 0.)
        self.prepared = False
        self.prepare_queue = []
        self.prepare_future = None
        self.gate_owned = False
        if self.publisher:
            self.publisher.publish(self.Twist())
            self.node.destroy_publisher(self.publisher)
            self.publisher = None
        if (owned or force) and self.clients["gate_enable"].service_is_ready():
            self.clients["gate_enable"].call_async(self.SetBool.Request(data=False))

    def tick(self):
        now = time.monotonic()
        if now - self.last_query >= 1:
            self.last_query = now
            names = {
                "nino_command_gate": ["max_forward", "max_reverse", "max_yaw", "command_timeout"],
                "velocity_smoother": ["max_velocity", "min_velocity", "max_accel", "max_decel"],
                "collision_monitor": ["cmd_vel_in_topic", "cmd_vel_out_topic", "StopZone.points", "StopZone.enabled",
                                      "StopZone.action_type", "StopZone.min_points", "base_frame_id", "scan.enabled", "scan.topic"]}
            for name, client in self.clients.items():
                if name.startswith("gate_") or name in self.pending or not client.service_is_ready():
                    continue
                keys = names.get(name)
                future = client.call_async(self.GetParameters.Request(names=keys) if keys else self.GetState.Request())
                self.pending[name] = (future, now, keys)
        for name, (future, stamp, keys) in list(self.pending.items()):
            if future.done():
                try:
                    response = future.result()
                    self.params[name] = dict(zip(keys, [parameter_value(p) for p in response.values])) if keys else response.current_state.id
                    self.param_at[name] = now
                except Exception:
                    pass
                del self.pending[name]
            elif now - stamp > 2:
                future.cancel()
                del self.pending[name]
        if self.prepare_future:
            if self.prepare_future.done():
                try:
                    if not self.prepare_future.result().success:
                        raise ValueError("Gate từ chối yêu cầu chuẩn bị")
                    self.prepare_future = None
                    if not self.prepare_queue:
                        self.prepared = self.preparing_activates
                        self.emit({"type": "info", "message": "Gate xác nhận MANUAL / enabled; chỉ phát zero, STM32 chưa tự ARM"
                                   if self.prepared else "Đã reset STOP tầng Pi; gate vẫn disabled, STM32 không tự ARM"})
                except Exception as e:
                    self.disable()
                    self.emit({"type": "error", "message": str(e)})
            elif now - self.prepare_at > 2:
                self.disable()
                self.emit({"type": "error", "message": "Gate không trả ACK; đã yêu cầu disable"})
        if self.prepare_queue and self.prepare_future is None:
            name, value = self.prepare_queue.pop(0)
            self.prepare_at = now
            self.prepare_future = self.clients[name].call_async(self.Trigger.Request() if value is None else self.SetBool.Request(data=value))
        if self.publisher and now - self.last_pub >= .05:
            self.last_pub = now
            msg = self.Twist()
            msg.linear.x, msg.angular.z = self.target if self.prepared else (0., 0.)
            self.publisher.publish(msg)

    def final_zero(self):
        return time.monotonic()-self.final_at < .3 and self.final is not None and self.final == (0., 0.)
