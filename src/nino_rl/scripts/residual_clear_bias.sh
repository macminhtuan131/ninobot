#!/usr/bin/env bash
set -euo pipefail
nino_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
set +u
source /opt/ros/jazzy/setup.bash
source "${NINO_SIM_INSTALL:-$nino_repo/install}/local_setup.bash"
set -u
export PYTHONPATH="$nino_repo/src/nino_control:$nino_repo/src/nino_rl${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID=129 NINO_ROS_DOMAIN_ID=129 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE
exec "$nino_repo/.venv/bin/python" -u -m nino_rl.residual_clear_bias "$@"
