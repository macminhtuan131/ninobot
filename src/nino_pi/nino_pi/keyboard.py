"""Terminal teleop with repeat publishing and a real key-expiry watchdog."""
import select
import sys
import termios
import tty
from time import monotonic

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from .selection import CommandSelection


KEYS = {"i":(1,0),"u":(1,1),"o":(1,-1),"j":(0,1),"l":(0,-1),
        ",":(-1,0),"m":(-1,-1),".":(-1,1)}


class KeyboardState:
    def __init__(self):
        self.selection = CommandSelection(timeout=.6)
        self.selection.enable(True)

    def press(self,key,now):
        forward,yaw = KEYS.get(key,(0,0))
        speed = .2 if forward >= 0 else .1
        self.selection.receive("manual",forward*speed,yaw*.6,now)

    def output(self,now):
        return self.selection.output(now)


class KeyboardTeleop(Node):
    def __init__(self):
        super().__init__("nino_keyboard_teleop")
        self.state = KeyboardState()
        self.publisher = self.create_publisher(Twist,"/cmd_vel_teleop",10)
        self.create_timer(.05,self.publish)

    def publish(self):
        msg = Twist()
        msg.linear.x,msg.angular.z = self.state.output(monotonic())
        self.publisher.publish(msg)


def main(args=None):
    if not sys.stdin.isatty():
        raise SystemExit("Use an interactive terminal or ssh -t for keyboard teleop")
    settings = termios.tcgetattr(sys.stdin)
    rclpy.init(args=args)
    node = KeyboardTeleop()
    print("Nino teleop: hold i forward, , reverse, j/l turn, u/o/m/. curve; k/space stop; Ctrl-C exit.\n"
          "0.20 m/s forward, 0.10 m/s reverse, 0.60 rad/s. Key expiry 0.6 s. Enable gate separately.",flush=True)
    try:
        tty.setraw(sys.stdin.fileno())
        while rclpy.ok():
            rclpy.spin_once(node,timeout_sec=0.)
            if select.select([sys.stdin],[],[],.02)[0]:
                key = sys.stdin.read(1)
                if not key or key == '\x03':
                    break
                node.state.press(key,monotonic())
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin,termios.TCSADRAIN,settings)
        if rclpy.ok():
            node.state.press("k",monotonic())
            node.publish()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
