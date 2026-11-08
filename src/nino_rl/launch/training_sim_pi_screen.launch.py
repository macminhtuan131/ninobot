"""Prepared PI-screen launch; no standalone physics release."""

import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    simulator = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("nino_description"), "launch", "sim.launch.py"]
            )
        ),
        launch_arguments={
            "world": LaunchConfiguration("world"),
            "world_name": LaunchConfiguration("world_name"),
            "headless": LaunchConfiguration("headless"),
            "rviz": "false",
            "sensor_monitor": "false",
            "start_effort_drive": "false",
            "linorobot2_mode": "false",
            # A direct /cmd_vel straight reference supplies the PI baseline;
            # PI screen requests zero residual; no torque action.
            "accept_cmd_vel": "true",
            "accept_torque": LaunchConfiguration("accept_torque"),
            "contact_lab": LaunchConfiguration("contact_lab"),
            "terrain_preview": LaunchConfiguration("terrain_preview"),
            "caster_wheel_damping": LaunchConfiguration("caster_wheel_damping"),
            "verbosity": LaunchConfiguration("verbosity"),
            "max_wheel_torque": LaunchConfiguration("max_wheel_torque"),
            "pi_integrator_profile": LaunchConfiguration("pi_integrator_profile"),
            "controller_startup_timeout": LaunchConfiguration("controller_startup_timeout"),
        }.items(),
    )
    gain_drive = Node(package="nino_rl", executable="sim_pi_screen_effort_drive", name="effort_drive", output="screen",
        parameters=[PathJoinSubstitution([FindPackageShare("nino_control"),"config","effort_drive.yaml"]), {
            "use_sim_time": True, "accept_cmd_vel": True, "accept_torque": False,
            "pi_integrator_profile": LaunchConfiguration("pi_integrator_profile"),
            "max_wheel_torque": ParameterValue(LaunchConfiguration("max_wheel_torque"),value_type=float),
            "velocity_ki": ParameterValue(LaunchConfiguration("velocity_ki"),value_type=float),
            "sim_common_gain": ParameterValue(LaunchConfiguration("sim_common_gain"),value_type=float)}])
    reset_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="rl_world_control_bridge",
        output="screen",
        arguments=[
            ["/world/", LaunchConfiguration("world_name"), "/control@ros_gz_interfaces/srv/ControlWorld"],
            ["/world/", LaunchConfiguration("world_name"), "/set_pose@ros_gz_interfaces/srv/SetEntityPose"],
            ["/world/", LaunchConfiguration("world_name"), "/create@ros_gz_interfaces/srv/SpawnEntity"],
            ["/world/", LaunchConfiguration("world_name"), "/remove@ros_gz_interfaces/srv/DeleteEntity"],
            ["/world/", LaunchConfiguration("world_name"), "/stats@ros_gz_interfaces/msg/WorldStatistics[gz.msgs.WorldStatistics"],
        ],
    )
    return LaunchDescription(
        [
            SetEnvironmentVariable(
                "ROS_DOMAIN_ID", os.environ.get("NINO_ROS_DOMAIN_ID", "77")
            ),
            SetEnvironmentVariable("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST"),
            DeclareLaunchArgument("world", default_value="long_hall.sdf"),
            DeclareLaunchArgument("pi_integrator_profile", default_value="conditional_v1"),
            DeclareLaunchArgument("controller_startup_timeout", default_value="30"),
            DeclareLaunchArgument("accept_torque",default_value="false"),
            DeclareLaunchArgument("contact_lab",default_value="true"),
            DeclareLaunchArgument("terrain_preview",default_value="false"),
            DeclareLaunchArgument("caster_wheel_damping",default_value="0.001"),
            DeclareLaunchArgument("world_name", default_value="long_hall"),
            DeclareLaunchArgument(
                "headless", default_value="true", description="Disable Gazebo GUI while training"
            ),
            DeclareLaunchArgument(
                "rviz", default_value="false",
                description="Compatibility argument; Nav2/RViz are not launched",
            ),
            DeclareLaunchArgument(
                "verbosity", default_value="1", description="Gazebo log level (0-4)"
            ),
            DeclareLaunchArgument(
                "max_wheel_torque",
                default_value="4.0",
                description="Symmetric RL motor limit in N.m (also enforced by safety adapter)",
            ),
            DeclareLaunchArgument("sim_common_gain",default_value="1.0"),
            DeclareLaunchArgument("velocity_ki",default_value="0.10"),
            simulator,
            gain_drive,
            reset_bridge,
        ]
    )
