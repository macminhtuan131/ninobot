#!/usr/bin/env bash
# Read-only inventory. It does not enable or publish motor commands.
set -uo pipefail
if ! command -v ros2 >/dev/null 2>&1; then
  if [[ -f /opt/ros/jazzy/setup.bash ]]; then
    source /opt/ros/jazzy/setup.bash
  else
    echo 'ROS 2 Jazzy was not found. Install/source ROS before checking robot drivers.'
    exit 1
  fi
fi
echo '--- Platform and ROS environment ---'
uname -m
cat /etc/os-release
printf 'ROS_DISTRO=%s ROS_DOMAIN_ID=%s\n' "${ROS_DISTRO:-unset}" "${ROS_DOMAIN_ID:-0}"
echo '--- Installed packages that may contain robot drivers ---'
ros2 pkg list | grep -Ei 'nino|cybergear|can|lidar|rplidar|sllidar|ydlidar|imu|bno|mpu|xsens|micro_ros|controller' || true
echo '--- Running nodes ---'
timeout 8 ros2 node list || true
echo '--- Running topics and message types ---'
timeout 8 ros2 topic list -t || true
echo '--- Controller states (only applicable to a ros2_control backend) ---'
timeout 8 ros2 control list_controllers || true
for topic in /scan /imu/data /joint_states /odom; do
  printf '\n--- %s publishers ---\n' "$topic"
  timeout 5 ros2 topic info "$topic" || true
  printf '%s\n' 'Sampling rate for four seconds; timeout exit is expected:'
  timeout 4 ros2 topic hz "$topic" || true
done
echo '--- Required transform links ---'
for pair in 'odom base_footprint' 'base_footprint laser'; do
  read -r parent child <<< "$pair"
  timeout 4 ros2 run tf2_ros tf2_echo "$parent" "$child" || true
done
echo 'Installed packages alone do not prove working hardware. Check live publishers, rates and TF.'
echo 'If topics are absent, source the hardware workspace and start its drivers, then repeat.'
