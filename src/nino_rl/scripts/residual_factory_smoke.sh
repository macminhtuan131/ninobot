#!/usr/bin/env bash
set -euo pipefail
nino_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
set +u
source /opt/ros/jazzy/setup.bash
nino_sim_install="${NINO_SIM_INSTALL:-$nino_repo/install}"
if [[ ! -r "$nino_sim_install/local_setup.bash" ]]; then
  echo "Build nino_control and nino_description first, or set NINO_SIM_INSTALL to the verified install directory." >&2
  exit 2
fi
source "$nino_sim_install/local_setup.bash"
set -u
export PYTHONPATH="$nino_repo/src/nino_control:$nino_repo/src/nino_rl${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID=129 NINO_ROS_DOMAIN_ID=129 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE
exec "$nino_repo/.venv/bin/python" -u -m nino_rl.residual_factory_workflow "$@"
