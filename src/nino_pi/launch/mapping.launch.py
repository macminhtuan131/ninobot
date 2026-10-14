"""Make a real occupancy map using SLAM Toolbox and manual driving."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    share = FindPackageShare("nino_pi")
    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time",default_value="false"),
        DeclareLaunchArgument("slam_params_file",default_value=PathJoinSubstitution([share,"config","mapping.yaml"])),
        DeclareLaunchArgument("joystick",default_value="false"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            share,"launch","teleop.launch.py"])),launch_arguments={
                "joystick":LaunchConfiguration("joystick")}.items()),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare("slam_toolbox"),"launch","online_async_launch.py"])),launch_arguments={
                "use_sim_time":"false","autostart":"true",
                "slam_params_file":LaunchConfiguration("slam_params_file")}.items()),
    ])
