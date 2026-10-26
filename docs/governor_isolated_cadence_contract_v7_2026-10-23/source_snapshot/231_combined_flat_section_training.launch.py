"""Launch the flat specialist's isolated combined-course section."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("headless", default_value="true"),
        DeclareLaunchArgument("pi_integrator_profile", default_value="legacy"),
        DeclareLaunchArgument("verbosity", default_value="1"),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare("nino_rl"), "launch", "training_sim.launch.py"])),
            launch_arguments={
                "world": "combined_flat_section.sdf",
                "world_name": "combined_flat_section",
                "headless": LaunchConfiguration("headless"),
                "pi_integrator_profile": LaunchConfiguration("pi_integrator_profile"),
                "verbosity": LaunchConfiguration("verbosity"),
            }.items(),
        ),
    ])
