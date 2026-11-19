#!/usr/bin/env bash
set -eo pipefail
NINO_V4_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
source /opt/ros/jazzy/setup.bash
source "$NINO_V4_ROOT/install/setup.bash"
export PYTHONPATH="$NINO_V4_ROOT/src/nino_rl:$NINO_V4_ROOT/src/nino_control${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
cd "$NINO_V4_ROOT"
exec "$NINO_V4_ROOT/.venv/bin/python" -B -u -m nino_rl.recovery_v4_campaign "$@"
