"""Isolated simulation PI node. Ki is a readonly launch override, not hot tuning."""
import os
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from std_msgs.msg import Float64MultiArray,MultiArrayDimension
from nino_control.effort_drive import EffortDrive
from .gain_effort_drive import GainEffortDrive
from .pi_screen_contract import (require_simulation_environment,require_ki,
    require_parameters,expected_parameters,runtime_audit,require_audit)


class PiScreenEffortDrive(EffortDrive):
    def __init__(self):
        require_simulation_environment(os.environ)
        self.last_gain_map=None;self.gain_map_calls=0
        super().__init__()
        self.declare_parameter('sim_common_gain',1.,ParameterDescriptor(read_only=True))
        self.sim_common_gain=self.get_parameter('sim_common_gain').value
        ki=require_ki(self.ki)
        actual={name:self.get_parameter(name).value for name in expected_parameters(ki)}
        require_parameters(actual,ki)
        require_audit(runtime_audit(self),ki)
        self.gain_publisher=self.create_publisher(Float64MultiArray,'/nino_drive/gain_map',10)
        self.pi_screen_publisher=self.create_publisher(Float64MultiArray,'/nino_drive/pi_screen',10)

    gain_target_map=GainEffortDrive.gain_target_map

    def _control_update(self):
        before=self.last_torque_status_publish_ns
        # The entire frozen PI/watchdog/ramp/limit/odometry path is shared.
        GainEffortDrive._control_update(self)
        if self.last_torque_status_publish_ns!=before:
            audit=runtime_audit(self)
            msg=Float64MultiArray();fields=tuple(audit)
            msg.layout.dim=[MultiArrayDimension(label=','.join(fields),size=len(fields),stride=len(fields))]
            msg.data=[float(audit[k]) for k in fields];self.pi_screen_publisher.publish(msg)

    def _reset_odometry(self,request,response):
        result=super()._reset_odometry(request,response)
        self.last_gain_map=None;self.gain_map_calls=0
        return result


def main(args=None):
    require_simulation_environment(os.environ)
    rclpy.init(args=args);node=None
    try:
        node=PiScreenEffortDrive();rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        if node is not None:node.stop();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
