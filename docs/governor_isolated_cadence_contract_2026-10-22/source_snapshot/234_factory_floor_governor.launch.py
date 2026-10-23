"""Contact-instrumented factory lab. PI evaluation owns motion commands."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument,IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration,PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    topics=["/nino/contact_lab/"+component+"@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts"
            for component in ("left_wheel","right_wheel","caster_left_wheel","caster_right_wheel",
                              "caster_bracket_left","caster_bracket_right","chassis")]
    return LaunchDescription([
        DeclareLaunchArgument("variant",default_value="cable"),
        DeclareLaunchArgument("world_override",default_value=""),
        DeclareLaunchArgument("headless",default_value="false"),
        DeclareLaunchArgument("controller_startup_timeout",default_value="300"),
        DeclareLaunchArgument("output_directory",default_value="rl_runs/governor_contact_lab"),
        DeclareLaunchArgument("config",default_value=PathJoinSubstitution([
            FindPackageShare("nino_rl"),"config","factory_floor_governor_pi_check.yaml"])),
        DeclareLaunchArgument("caster_wheel_damping",default_value="0.01"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare("nino_rl"),"launch","factory_floor_training.launch.py"])),
            launch_arguments={"variant":LaunchConfiguration("variant"),"headless":LaunchConfiguration("headless"),
                "world_override":LaunchConfiguration("world_override"),
                "controller_startup_timeout":LaunchConfiguration("controller_startup_timeout"),
                "caster_wheel_damping":LaunchConfiguration("caster_wheel_damping"),
                "contact_lab":"true","terrain_preview":"false","accept_torque":"false"}.items()),
        Node(package="ros_gz_bridge",executable="parameter_bridge",name="contact_lab_bridge",
             output="screen",arguments=topics),
        Node(package="nino_rl",executable="governor_logger",name="governor_logger",output="screen",
             parameters=[{"use_sim_time":True,"output_directory":LaunchConfiguration("output_directory"),
                          "variant":LaunchConfiguration("variant"),
                          "world_override":LaunchConfiguration("world_override"),
                          "config_file":LaunchConfiguration("config"),
                          "caster_wheel_damping":ParameterValue(LaunchConfiguration("caster_wheel_damping"),value_type=float)}]),
    ])
