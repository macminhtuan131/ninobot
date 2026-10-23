"""Corrected PI/contact baseline; fixed matching model and evaluation config."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument,IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration,PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package=FindPackageShare("nino_rl")
    return LaunchDescription([
        DeclareLaunchArgument("headless",default_value="false"),
        DeclareLaunchArgument("variant",default_value="clear"),
        DeclareLaunchArgument("output_directory",default_value="rl_runs/factory_floor_stability/contact"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            package,"launch","factory_floor_governor.launch.py"])),
            launch_arguments={
                "variant":LaunchConfiguration("variant"),"headless":LaunchConfiguration("headless"),
                "caster_wheel_damping":"0.001",
                "config":PathJoinSubstitution([package,"config","factory_floor_stability_pi_check.yaml"]),
                "output_directory":LaunchConfiguration("output_directory")}.items()),
    ])
