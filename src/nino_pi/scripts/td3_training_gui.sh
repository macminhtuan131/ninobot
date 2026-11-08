#!/usr/bin/env bash
set -euo pipefail
nino_repo="${NINO_REPO:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)}"
set +u
source /opt/ros/jazzy/setup.bash
if [[ -f "$nino_repo/install/local_setup.bash" ]]; then
  source "$nino_repo/install/local_setup.bash"
fi
set -u
export NINO_REPO="$nino_repo"
export PYTHONPATH="$nino_repo/src/nino_pi:$nino_repo/src/nino_rl:$nino_repo/src/nino_control${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m nino_pi.td3_training_panel "$@"
