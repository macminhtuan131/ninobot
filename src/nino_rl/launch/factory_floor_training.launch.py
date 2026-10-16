"""View/check a factory-floor contact world with the existing flat wheel PI."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def launch_world(context):
    variant = LaunchConfiguration("variant").perform(context)
    contact = LaunchConfiguration("contact_lab").perform(context).lower() in ("true","1")
    if variant not in ("mixed", "clear", "clear_box", "cable", "cable_box", "cable_box_capsule", "pothole", "groove", "threshold"):
        raise ValueError("Choose mixed, clear/clear_box, cable/cable_box/cable_box_capsule, pothole, groove or threshold")
    if variant in ("clear_box","cable_box","cable_box_capsule") and not contact:
        raise ValueError("Box controls require contact_lab:=true")
    return [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare("nino_rl"), "launch", "training_sim.launch.py"])),
        launch_arguments={
            "world": f"factory_floor_{variant}{'_contact_lab' if contact else ''}.sdf",
            "world_name": "factory_floor_lab",
            "headless": LaunchConfiguration("headless"),
            "pi_integrator_profile": "conditional_v1",
            "max_wheel_torque": "4.0",
            "verbosity": LaunchConfiguration("verbosity"),
            "controller_startup_timeout": LaunchConfiguration("controller_startup_timeout"),
            "accept_torque": LaunchConfiguration("accept_torque"),
            "contact_lab": LaunchConfiguration("contact_lab"),
            "terrain_preview": LaunchConfiguration("terrain_preview"),
            "caster_wheel_damping": LaunchConfiguration("caster_wheel_damping"),
        }.items(),
    )]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("variant", default_value="mixed"),
        DeclareLaunchArgument("headless", default_value="false"),
        DeclareLaunchArgument("verbosity", default_value="1"),
        # Mixed floor is imported by DART before controller updates can run.
        # This changes startup only, never the RL action/clock deadlines.
        DeclareLaunchArgument("controller_startup_timeout", default_value="300"),
        DeclareLaunchArgument("accept_torque",default_value="true"),
        DeclareLaunchArgument("contact_lab",default_value="false"),
        DeclareLaunchArgument("terrain_preview",default_value="true"),
        DeclareLaunchArgument("caster_wheel_damping",default_value="0.01"),
        OpaqueFunction(function=launch_world),
    ])
