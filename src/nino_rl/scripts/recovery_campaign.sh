#!/usr/bin/env bash
set -eo pipefail
NINO_CAMPAIGN_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
source /opt/ros/jazzy/setup.bash
source "$NINO_CAMPAIGN_ROOT/install/setup.bash"
export PYTHONPATH="$NINO_CAMPAIGN_ROOT/src/nino_rl:$NINO_CAMPAIGN_ROOT/src/nino_control${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
cd "$NINO_CAMPAIGN_ROOT"
exec "$NINO_CAMPAIGN_ROOT/.venv/bin/python" -B -u -m nino_rl.recovery_campaign "$@"
