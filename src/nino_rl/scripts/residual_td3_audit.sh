#!/usr/bin/env bash
set -euo pipefail
nino_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
export PYTHONPATH="$nino_repo/src/nino_control:$nino_repo/src/nino_rl${PYTHONPATH:+:$PYTHONPATH}"
exec "$nino_repo/.venv/bin/python" -u -m nino_rl.residual_td3_audit "$@"
