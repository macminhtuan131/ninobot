#!/usr/bin/env bash
# Start zero/disabled command pipeline only. No trial, motor ARM, or old pilot ledger.
set -eo pipefail
source "$HOME/pi5-stm32-slam-main/scripts/env.sh"
source "$HOME/nino_pi_ws/install/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
nino_stack_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -r "$nino_stack_root/gui_data_control.yaml" ]]; then
  nino_stack_config="$nino_stack_root/gui_data_control.yaml"
else
  nino_stack_config="$nino_stack_root/../config/gui_data_control.yaml"
fi
/usr/bin/python3 - <<'PY'
import time
import rclpy
rclpy.init()
node=rclpy.create_node('nino_gui_stack_discovery')
deadline=time.monotonic()+2
while time.monotonic()<deadline:
    rclpy.spin_once(node, timeout_sec=.1)
busy=[t for t in ('/cmd_vel','/cmd_vel_selected','/cmd_vel_smoothed') if node.get_publishers_info_by_topic(t)]
node.destroy_node()
rclpy.shutdown()
if busy:
    raise SystemExit('Command stack/publisher already exists; do not duplicate: '+str(busy))
PY
echo 'Starting disabled gate + smoother + Collision Monitor. This does not ARM STM32.'
exec ros2 launch nino_pi command_stack.launch.py control_params:="$nino_stack_config" governor:=false
