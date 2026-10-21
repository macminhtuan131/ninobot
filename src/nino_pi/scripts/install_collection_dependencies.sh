#!/usr/bin/env bash
# Collection-only dependencies; does not install/start navigation or motor drivers.
set -euo pipefail
test -f /opt/ros/jazzy/setup.bash || { echo 'ROS 2 Jazzy must be installed first.' >&2; exit 1; }
sudo apt-get update
sudo apt-get install -y python3-yaml python3-pytest \
  ros-jazzy-rosbag2 ros-jazzy-rosbag2-storage-default-plugins \
  ros-jazzy-rosidl-runtime-py ros-jazzy-rcl-interfaces \
  ros-jazzy-sensor-msgs ros-jazzy-nav-msgs ros-jazzy-tf2-msgs \
  ros-jazzy-diagnostic-msgs ros-jazzy-rosgraph-msgs
