"""Launch the manual command pipeline; keyboard runs in a separate TTY."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    share = FindPackageShare("nino_pi")
    return LaunchDescription([
        DeclareLaunchArgument("control_params",default_value=PathJoinSubstitution([share,"config","control.yaml"])),
        DeclareLaunchArgument("joystick",default_value="false"),
        DeclareLaunchArgument("joystick_params",default_value=PathJoinSubstitution([share,"config","joystick.yaml"])),
        DeclareLaunchArgument("joystick_device_id",default_value="0"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            share,"launch","command_stack.launch.py"])),
            launch_arguments={"control_params":LaunchConfiguration("control_params")}.items()),
        Node(package="joy",executable="joy_node",name="joy_node",output="screen",
             condition=IfCondition(LaunchConfiguration("joystick")),
             parameters=[{"use_sim_time":False,"deadzone":.08,"autorepeat_rate":20.,
                 "device_id":ParameterValue(
                     LaunchConfiguration("joystick_device_id"),value_type=int)}]),
        Node(package="teleop_twist_joy",executable="teleop_node",name="teleop_twist_joy_node",output="screen",
             condition=IfCondition(LaunchConfiguration("joystick")),
             parameters=[LaunchConfiguration("joystick_params"),{"use_sim_time":False}],
             remappings=[("cmd_vel","/cmd_vel_teleop")]),
    ])
