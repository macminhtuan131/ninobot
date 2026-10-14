"""Small real-time Nav2 stack for a mapped differential-drive robot."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetLaunchConfiguration
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from nino_pi.map_validation import validate_map


def check_map(context):
    path = validate_map(LaunchConfiguration("map").perform(context))
    return [SetLaunchConfiguration("map",path)]


def generate_launch_description():
    share = FindPackageShare("nino_pi")
    params = LaunchConfiguration("params_file")
    actions = [
        DeclareLaunchArgument("map",description="Absolute path to your measured occupancy-map YAML"),
        DeclareLaunchArgument("params_file",default_value=PathJoinSubstitution([share,"config","navigation.yaml"])),
        DeclareLaunchArgument("control_params",default_value=PathJoinSubstitution([share,"config","control.yaml"])),
        DeclareLaunchArgument("rviz",default_value="false"),
        OpaqueFunction(function=check_map),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            share,"launch","command_stack.launch.py"])),
            launch_arguments={"control_params":LaunchConfiguration("control_params")}.items()),
    ]
    servers = [("nav2_map_server","map_server"),("nav2_amcl","amcl"),
               ("nav2_controller","controller_server"),("nav2_planner","planner_server"),
               ("nav2_smoother","smoother_server"),("nav2_behaviors","behavior_server"),
               ("nav2_bt_navigator","bt_navigator"),("nav2_waypoint_follower","waypoint_follower")]
    for package,name in servers:
        extra = {"use_sim_time":False,"enable_stamped_cmd_vel":False}
        if name == "map_server":
            extra["yaml_filename"] = LaunchConfiguration("map")
        if name == "bt_navigator":
            bt = FindPackageShare("nav2_bt_navigator")
            extra.update(default_nav_to_pose_bt_xml=PathJoinSubstitution([
                bt,"behavior_trees","navigate_to_pose_w_replanning_and_recovery.xml"]),
                default_nav_through_poses_bt_xml=PathJoinSubstitution([
                bt,"behavior_trees","navigate_through_poses_w_replanning_and_recovery.xml"]))
        actions.append(Node(package=package,executable=name,name=name,output="screen",
            parameters=[params,extra],remappings=[("cmd_vel","/cmd_vel_nav")] if name in (
                "controller_server","behavior_server") else []))
    for name,nodes in (("localization",["map_server","amcl"]),
                       ("navigation",[name for _,name in servers[2:]])):
        actions.append(Node(package="nav2_lifecycle_manager",executable="lifecycle_manager",
            name=f"lifecycle_manager_{name}",output="screen",parameters=[{
                "use_sim_time":False,"autostart":True,"node_names":nodes}]))
    actions.append(Node(package="rviz2",executable="rviz2",name="rviz2",output="screen",
        condition=IfCondition(LaunchConfiguration("rviz")),parameters=[{"use_sim_time":False}],
        arguments=["-d",PathJoinSubstitution([FindPackageShare("nav2_bringup"),"rviz","nav2_default_view.rviz"])]))
    return LaunchDescription(actions)
