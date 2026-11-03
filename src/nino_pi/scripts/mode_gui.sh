#!/usr/bin/env bash
set -euo pipefail
nino_pkg_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$nino_pkg_root${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m nino_pi.mode_gui "$@"
