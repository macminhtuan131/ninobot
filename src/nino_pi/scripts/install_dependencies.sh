#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -m)" != 'aarch64' ]]; then
  echo 'This installer targets 64-bit Ubuntu on Pi 5 (aarch64).' >&2
  exit 1
fi
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
  echo 'This bundle targets Ubuntu 24.04 and ROS 2 Jazzy.' >&2
  exit 1
fi
if [[ ! -f /opt/ros/jazzy/setup.bash ]]; then
  echo 'Install ROS 2 Jazzy first using the official Ubuntu installation guide.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y \
  python3-colcon-common-extensions python3-yaml \
  ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-slam-toolbox \
  ros-jazzy-teleop-twist-joy ros-jazzy-joy \
  ros-jazzy-tf2-ros \
  ros-jazzy-rosbag2 ros-jazzy-rosbag2-storage-default-plugins
