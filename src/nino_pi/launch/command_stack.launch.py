"""Shared command pipeline; the physical motor/sensor bringup runs separately."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument,OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory
from pathlib import Path
import yaml


def command_owner(context):
    params=LaunchConfiguration("control_params").perform(context)
    enabled=LaunchConfiguration("governor").perform(context).lower() in ("true","1")
    if enabled:
        governor_params=LaunchConfiguration("governor_params").perform(context)
        if not governor_params:
            governor_params=str(Path(get_package_share_directory("nino_control"))/"config/speed_governor.yaml")
        settings=yaml.safe_load(Path(params).read_text())
        gate=settings["nino_command_gate"]["ros__parameters"]
        smoother=settings["velocity_smoother"]["ros__parameters"]
        # Governor owns reference limiting in this mode. It starts disabled;
        # hardware must supply measured /nino_drive/diagnostics before enabling.
        nodes=[Node(package="nino_control",executable="speed_governor",name="nino_speed_governor",
            output="screen",parameters=[governor_params,{"use_sim_time":False,"enabled":False,
                "input_topic":"/cmd_vel_selected","output_topic":"/cmd_vel_smoothed",
                "max_forward_m_s":float(gate["max_forward"]),"max_reverse_m_s":float(gate["max_reverse"]),
                "max_yaw_rad_s":float(gate["max_yaw"]),
                "max_linear_acceleration_m_s2":float(smoother["max_accel"][0]),
                "max_linear_deceleration_m_s2":abs(float(smoother["max_decel"][0])),
                "max_yaw_acceleration_rad_s2":min(abs(float(smoother["max_accel"][2])),abs(float(smoother["max_decel"][2])))}])]
        lifecycle_nodes=["collision_monitor"]
    else:
        nodes=[Node(package="nav2_velocity_smoother",executable="velocity_smoother",name="velocity_smoother",
            output="screen",parameters=[params,{"use_sim_time":False}],
            remappings=[("cmd_vel","/cmd_vel_selected"),("cmd_vel_smoothed","/cmd_vel_smoothed")])]
        lifecycle_nodes=["velocity_smoother","collision_monitor"]
    nodes.append(Node(package="nav2_lifecycle_manager",executable="lifecycle_manager",name="lifecycle_manager_commands",
                      output="screen",parameters=[{"use_sim_time":False,"autostart":True,"node_names":lifecycle_nodes}]))
    return nodes


def generate_launch_description():
    params = LaunchConfiguration("control_params")
    return LaunchDescription([
        DeclareLaunchArgument("control_params",default_value=PathJoinSubstitution([
            FindPackageShare("nino_pi"),"config","control.yaml"])),
        DeclareLaunchArgument("governor",default_value="false"),
        DeclareLaunchArgument("governor_params",default_value=""),
        Node(package="nino_pi",executable="command_gate",name="nino_command_gate",
             output="screen",parameters=[params,{"use_sim_time":False}]),
        Node(package="nav2_collision_monitor",executable="collision_monitor",name="collision_monitor",
             output="screen",parameters=[params,{"use_sim_time":False}]),
        OpaqueFunction(function=command_owner),
    ])
