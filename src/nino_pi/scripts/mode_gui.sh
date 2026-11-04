#!/usr/bin/env bash
set -euo pipefail
nino_pkg_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Local bag decoding needs ROS type support/shared libraries. Sourcing launches no nodes.
if [[ -r /opt/ros/jazzy/setup.bash ]]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
fi
export PYTHONPATH="$nino_pkg_root:$nino_pkg_root/../nino_control:$nino_pkg_root/../nino_rl${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m nino_pi.mode_gui "$@"
