"""One command owner, bounded speeds, explicit enable and latched software stop."""
from time import monotonic
import signal
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool
from std_srvs.srv import SetBool, Trigger
from .selection import CommandSelection


class CommandGate(Node):
    def __init__(self):
        super().__init__("nino_command_gate")
        defaults = dict(command_timeout=.3, max_forward=.2, max_reverse=.1,
                        max_yaw=.6, publish_rate=20.)
        for key,value in defaults.items():
            self.declare_parameter(key,value)
        p = lambda key: float(self.get_parameter(key).value)
        self.selection = CommandSelection(p("command_timeout"),p("max_forward"),
                                          p("max_reverse"),p("max_yaw"))
        if not 1 <= p("publish_rate") <= 100:
            raise ValueError("publish_rate must be in [1, 100] Hz")
        self.publisher = self.create_publisher(Twist,"/cmd_vel_selected",10)
        self.create_subscription(Twist,"/cmd_vel_teleop",lambda msg: self.receive("manual",msg),10)
        self.create_subscription(Twist,"/cmd_vel_nav",lambda msg: self.receive("navigation",msg),10)
        self.create_subscription(Bool,"/nino/emergency_stop",self.emergency_stop,10)
        self.create_service(SetBool,"~/enable",self.enable)
        self.create_service(SetBool,"~/navigation_mode",self.mode)
        self.create_service(Trigger,"~/reset_stop",self.reset_stop)
        self.create_timer(1/p("publish_rate"),self.publish)
        self.get_logger().info("Manual mode, disabled. Enable explicitly after driver checks.")

    def receive(self,source,msg):
        if not self.selection.receive(source,msg.linear.x,msg.angular.z,monotonic()):
            self.get_logger().error(f"Rejected nonfinite {source} command")

    def publish(self):
        msg = Twist()
        msg.linear.x,msg.angular.z = self.selection.output(monotonic())
        self.publisher.publish(msg)

    def enable(self,request,response):
        response.success = self.selection.enable(request.data)
        response.message = ("Enabled; waiting for a fresh command" if request.data else "Disabled") if response.success else "Software stop is latched; reset it while disabled first"
        self.publish()
        return response

    def mode(self,request,response):
        self.selection.mode(request.data)
        self.publish()
        response.success = True
        response.message = "Navigation mode" if request.data else "Manual mode"
        return response

    def emergency_stop(self,msg):
        if msg.data:
            self.selection.stop()
            self.publish()

    def reset_stop(self,request,response):
        response.success = self.selection.reset_stop()
        response.message = "Stop cleared; remains disabled" if response.success else "Disable first"
        return response


def main(args=None):
    rclpy.init(args=args)
    node = CommandGate()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        node.selection.enable(False)
        if rclpy.ok():
            node.publish()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
