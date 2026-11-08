"""Prepared simulation-only motor backend; no hardware entry or runtime release.

    /cmd_vel -> existing ownership/watchdog -> gain common map -> unchanged
    speed/ramp/velocity PI/torque limits. No second velocity PI is added.
"""
import os
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from std_msgs.msg import Float64MultiArray,MultiArrayDimension
from nino_control.effort_drive import EffortDrive
from .gain_reference_map import CONTEXT_ID,require_gain,target_map,map_audit
from .gain_drive_kernel import gain_control_update


def require_simulation_environment(environment):
    if (environment.get('ROS_DOMAIN_ID')!='129' or environment.get('NINO_SIM_GAIN_CONTEXT')!=CONTEXT_ID
            or not environment.get('GZ_PARTITION','').startswith('nino_factory_td3_')):
        raise ValueError('Gain drive requires its isolated simulation context/domain/partition')


class GainEffortDrive(EffortDrive):
    def __init__(self):
        require_simulation_environment(os.environ)
        self.last_gain_map=None;self.gain_map_calls=0
        super().__init__()
        self.declare_parameter('sim_common_gain',1.,ParameterDescriptor(read_only=True))
        self.sim_common_gain=require_gain(float(self.get_parameter('sim_common_gain').value))
        if not self.get_parameter('use_sim_time').value or self.accept_torque or not self.accept_cmd_vel:
            raise ValueError('Gain context requires sim clock and velocity-reference-only motor backend')
        self.gain_publisher=self.create_publisher(Float64MultiArray,'/nino_drive/gain_map',10)

    def gain_target_map(self,linear,angular,radius,separation):
        targets,self.last_gain_map=target_map(linear,angular,radius,separation,self.sim_common_gain)
        self.gain_map_calls+=1
        return targets

    def _control_update(self):
        self.last_gain_map=None;self.gain_map_calls=0
        before=self.last_torque_status_publish_ns
        gain_control_update(self)
        if self.last_torque_status_publish_ns!=before:
            audit=map_audit(self.last_gain_map,stamp_s=self.last_control_ns*1e-9,
                targets=self.target_velocity,max_speed=self.max_wheel_speed,calls=self.gain_map_calls)
            # Gain is evaluation telemetry only. Existing drive diagnostics and
            # last_final remain the honest pre-map execution-reference channel.
            audit['common_gain']=self.sim_common_gain
            msg=Float64MultiArray();fields=tuple(audit)
            msg.layout.dim=[MultiArrayDimension(label=','.join(fields),size=len(fields),stride=len(fields))]
            msg.data=[float(audit[k]) for k in fields];self.gain_publisher.publish(msg)

    def _reset_odometry(self,request,response):
        result=super()._reset_odometry(request,response)
        self.last_gain_map=None;self.gain_map_calls=0
        return result


def main(args=None):
    require_simulation_environment(os.environ)
    rclpy.init(args=args);node=None
    try:
        node=GainEffortDrive();rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        if node is not None:node.stop();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
