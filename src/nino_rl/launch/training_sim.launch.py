"""Start Nino and the direct straight-line RL training interfaces."""

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
            "start_effort_drive": "true",
            "linorobot2_mode": "false",
            # A direct /cmd_vel straight reference supplies the PI baseline;
            # RL adds bounded residual wheel torque.
            "accept_cmd_vel": "true",
            "accept_torque": "true",
            "verbosity": LaunchConfiguration("verbosity"),
            "max_wheel_torque": LaunchConfiguration("max_wheel_torque"),
        }.items(),
    )
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
            simulator,
            reset_bridge,
        ]
    )
