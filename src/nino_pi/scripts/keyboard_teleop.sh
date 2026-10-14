#!/usr/bin/env bash
# Run in a real terminal or ssh -t; command stack runs separately.
set -euo pipefail
if ! command -v ros2 >/dev/null 2>&1; then
  source /opt/ros/jazzy/setup.bash
fi
if [[ ! -t 0 ]]; then
  echo 'Keyboard teleop needs an interactive terminal. Use ssh -t for remote control.' >&2
  exit 1
fi
exec ros2 run nino_pi keyboard_teleop --ros-args -p use_sim_time:=false
