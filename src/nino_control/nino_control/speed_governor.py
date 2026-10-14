"""ROS wrapper for a hardware-signal-only reactive speed governor."""
from dataclasses import asdict
from collections import deque
import json
from math import hypot, isfinite
from time import monotonic

import rclpy
from rclpy.clock import Clock,ClockType
from rclpy.qos import qos_profile_sensor_data
from rclpy.node import Node
from rcl_interfaces.msg import ParameterDescriptor
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64MultiArray,String
from std_srvs.srv import SetBool,Trigger

from nino_control.governor_core import GovernorSettings,GovernorFrame,ReactiveGovernor,quaternion_rpy,vertical_acceleration


class SpeedGovernor(Node):
    def __init__(self):
        super().__init__("nino_speed_governor")
        fixed=ParameterDescriptor(read_only=True,description="Startup contract; restart to change. Use enable/reset services for runtime state.")
        for name,default in asdict(GovernorSettings()).items():
            self.declare_parameter(name,default,fixed)
        for name,default in dict(input_topic="/nino/governor/reference",output_topic="/cmd_vel_governed",
            imu_topic="/imu/data",feedback_topic="/nino_drive/diagnostics",enabled=False,
            imu_includes_gravity=True,publish_rate=20.,feedback_timeout_seconds=.25,
            wall_timeout_seconds=.5,max_forward_m_s=.5,max_reverse_m_s=.1,max_yaw_rad_s=.8,
            max_linear_acceleration_m_s2=.25,max_linear_deceleration_m_s2=.5,
            max_yaw_acceleration_rad_s2=1.5).items():
            self.declare_parameter(name,default,fixed)
        self.settings=GovernorSettings(**{name:self.get_parameter(name).value for name in asdict(GovernorSettings())})
        self.core=ReactiveGovernor(self.settings)
        self.enabled=bool(self.get_parameter("enabled").value)
        self.enable_wall_at=monotonic()
        self.imu=self.feedback=self.reference=None
        self.imu_window=deque(maxlen=300)
        self.last_imu_used=-float("inf")
        self.received={}
        self.last_ros=None
        self.last_output=(0.,0.)
        self.last_graph_check=0.
        self.competing=False
        self.rate=float(self.get_parameter("publish_rate").value)
        self.timeout=float(self.get_parameter("feedback_timeout_seconds").value)
        self.wall_timeout=float(self.get_parameter("wall_timeout_seconds").value)
        self.bounds=tuple(float(self.get_parameter(k).value) for k in (
            "max_forward_m_s","max_reverse_m_s","max_yaw_rad_s","max_linear_acceleration_m_s2",
            "max_linear_deceleration_m_s2","max_yaw_acceleration_rad_s2"))
        if (not all(isfinite(v) and v>0 for v in (self.rate,self.timeout,self.wall_timeout,*self.bounds))
                or self.rate<10):
            raise ValueError("Invalid governor timer/limits")
        self.input_topic=self.get_parameter("input_topic").value
        self.output_topic=self.get_parameter("output_topic").value
        if self.input_topic==self.output_topic:
            raise ValueError("Governor input/output must differ")
        self.publisher=self.create_publisher(Twist,self.output_topic,10)
        self.state_publisher=self.create_publisher(String,"/nino/governor/state",10)
        self.create_subscription(Twist,self.input_topic,self.on_reference,10)
        self.create_subscription(Imu,self.get_parameter("imu_topic").value,self.on_imu,qos_profile_sensor_data)
        self.create_subscription(Float64MultiArray,self.get_parameter("feedback_topic").value,self.on_feedback,qos_profile_sensor_data)
        self.create_service(SetBool,"~/enable",self.on_enable)
        self.create_service(Trigger,"~/reset",self.on_reset)
        # Wall timer continues to publish stop while simulated time is paused.
        self.timer=self.create_timer(1/self.rate,self.tick,clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info("Reactive governor ready; enabled="+str(self.enabled)+"; no contact/pose/preview input")

    def now(self):
        return self.get_clock().now().nanoseconds*1e-9

    def mark(self,key,stamp):
        self.received[key]=(stamp,monotonic())

    def on_reference(self,msg):
        if not all(isfinite(v) for v in (msg.linear.x,msg.angular.z)):
            self.core.fail("nonfinite_reference")
            return
        self.reference=(float(msg.linear.x),float(msg.angular.z))
        self.mark("reference",self.now())

    def on_imu(self,msg):
        try:
            # Mount must be aligned with base axes (the supplied Nino model is).
            # A different real mount needs its measured transform before use.
            roll,pitch,_=quaternion_rpy((msg.orientation.x,msg.orientation.y,msg.orientation.z,msg.orientation.w))
            vertical=vertical_acceleration((msg.linear_acceleration.x,msg.linear_acceleration.y,msg.linear_acceleration.z),
                roll,pitch,self.get_parameter("imu_includes_gravity").value)
            rate=hypot(msg.angular_velocity.x,msg.angular_velocity.y)
            if not isfinite(rate) or msg.orientation_covariance[0]==-1:
                raise ValueError("Orientation unavailable")
            self.imu=(vertical,rate)
            stamp=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
            if self.imu_window and stamp<self.imu_window[-1][0]:
                self.imu_window.clear()
                self.last_imu_used=-float("inf")
            self.imu_window.append((stamp,vertical))
            self.mark("imu",stamp)
        except (ValueError,IndexError):
            self.core.fail("invalid_imu")

    def on_feedback(self,msg):
        required=("sim_time_s","executed_linear_m_s","left_actual_rad_s","right_actual_rad_s",
                  "left_target_rad_s","right_target_rad_s","have_wheel_state","cmd_fresh")
        if not msg.layout.dim:
            self.core.fail("feedback_schema_missing")
            return
        names=msg.layout.dim[0].label.split(",")
        values=dict(zip(names,msg.data))
        if len(names)!=len(msg.data) or not all(k in values and isfinite(values[k]) for k in required):
            self.core.fail("invalid_drive_feedback")
            return
        self.feedback=values
        self.mark("feedback",values["sim_time_s"])

    def on_enable(self,request,response):
        if request.data and self.core.phase=="FAILSAFE":
            response.success=False
            response.message="Disable, reset, then enable after resolving the fault"
            return response
        self.enabled=bool(request.data)
        self.enable_wall_at=monotonic()
        self.reference=None
        self.received.pop("reference",None)
        self.last_output=(0.,0.)
        self.last_ros=None
        self.publish(0.,0.,dict(phase="ARMING" if self.enabled else "DISABLED",scale=0.,fault=self.core.fault))
        response.success=True
        response.message="Enabled; fresh reference required" if self.enabled else "Disabled"
        return response

    def on_reset(self,request,response):
        if self.enabled:
            response.success=False
            response.message="Disable before reset"
            return response
        self.core.reset()
        self.received.clear()
        self.imu=self.feedback=self.reference=None
        self.imu_window.clear()
        self.last_imu_used=-float("inf")
        self.last_ros=None
        response.success=True
        response.message="Reset; fresh sensors and reference required"
        return response

    def fresh(self,now):
        return all(key in self.received and -.02<=now-self.received[key][0]<=self.timeout
                   and monotonic()-self.received[key][1]<=self.wall_timeout
                   for key in ("reference","imu","feedback"))

    def publish(self,linear,yaw,decision):
        msg=Twist()
        msg.linear.x=float(linear)
        msg.angular.z=float(yaw)
        self.publisher.publish(msg)
        self.last_output=(linear,yaw)
        trace=String()
        trace.data=json.dumps(dict(time_s=self.now(),enabled=self.enabled,
            requested_linear_m_s=self.reference[0] if self.reference else 0.,
            requested_yaw_rad_s=self.reference[1] if self.reference else 0.,
            governed_linear_m_s=linear,governed_yaw_rad_s=yaw,**decision),allow_nan=False)
        self.state_publisher.publish(trace)

    def tick(self):
        now=self.now()
        if monotonic()-self.last_graph_check>=1:
            self.last_graph_check=monotonic()
            self.competing=len(self.get_publishers_info_by_topic(self.output_topic))>1
        if not self.enabled:
            self.publish(0.,0.,dict(phase="DISABLED",scale=0.,events=self.core.events))
            self.last_ros=now
            return
        if self.competing:
            self.publish(0.,0.,self.core.fail("competing_output_publisher"))
            return
        if self.reference is None and monotonic()-self.enable_wall_at<self.wall_timeout:
            self.publish(0.,0.,dict(phase="ARMING",scale=0.,events=self.core.events))
            self.last_ros=now
            return
        if not self.fresh(now) or not self.feedback or self.feedback["have_wheel_state"]<.5:
            self.publish(0.,0.,self.core.fail("stale_feedback"))
            self.last_ros=now
            return
        dt=1/self.rate if self.last_ros is None else now-self.last_ros
        self.last_ros=now
        if dt==0:
            # Physics paused: retain output only while wall freshness holds.
            self.publish(*self.last_output,self.core._decision(reason="clock_paused"))
            return
        f=self.feedback
        samples=[v for stamp,v in self.imu_window if stamp>self.last_imu_used]
        if self.imu_window:
            self.last_imu_used=self.imu_window[-1][0]
        rms=(sum(v*v for v in samples)/len(samples))**.5 if samples else abs(self.imu[0])
        peak=max(map(abs,samples),default=abs(self.imu[0]))
        frame=GovernorFrame(*self.imu,f["left_actual_rad_s"],f["right_actual_rad_s"],
                            f["left_target_rad_s"],f["right_target_rad_s"],f["executed_linear_m_s"],rms,peak)
        decision=self.core.update(frame,dt,*self.reference)
        if self.core.phase=="FAILSAFE":
            self.publish(0.,0.,decision)
            return
        forward,reverse,yaw_limit,accel,decel,yaw_accel=self.bounds
        requested_v=max(-reverse,min(forward,self.reference[0]))
        requested_w=max(-yaw_limit,min(yaw_limit,self.reference[1]))
        target=(requested_v*decision["scale"],requested_w*decision["scale"])
        if self.reference==(0.,0.):
            self.publish(0.,0.,decision)
            return
        # One command-limiting owner; inner wheel acceleration/torque limits
        # remain actuator protections. Interpolate v/w by a common fraction.
        dv,dw=target[0]-self.last_output[0],target[1]-self.last_output[1]
        allowed=(accel if abs(target[0])>abs(self.last_output[0]) else decel)*dt
        fraction=min(1.,allowed/abs(dv) if dv else 1.,yaw_accel*dt/abs(dw) if dw else 1.)
        self.publish(self.last_output[0]+fraction*dv,self.last_output[1]+fraction*dw,decision)


def main(args=None):
    rclpy.init(args=args)
    node=SpeedGovernor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.publish(0.,0.,dict(phase="SHUTDOWN",scale=0.))
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
