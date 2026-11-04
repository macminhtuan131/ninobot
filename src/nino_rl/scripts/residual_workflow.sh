#!/usr/bin/env bash
set -euo pipefail
nino_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
fi
export PYTHONPATH="$nino_repo/src/nino_control:$nino_repo/src/nino_rl${PYTHONPATH:+:$PYTHONPATH}"
nino_python="$nino_repo/.venv/bin/python"
if [[ ! -x "$nino_python" ]]; then
  echo "Missing $nino_python; prepare the documented research environment before running a job." >&2
  exit 2
fi
exec "$nino_python" -u -m nino_rl.residual_workflow "$@"
