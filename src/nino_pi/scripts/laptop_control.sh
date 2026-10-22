#!/usr/bin/env bash
# Run on laptop. Defaults to a user-owned config, never the example JSON.
set -euo pipefail
nino_tool_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
nino_remote_config="${NINO_LAPTOP_CONFIG:-$HOME/nino_laptop_control.json}"
if [[ -f "$nino_tool_root/nino_pi/laptop_control.py" ]]; then
  exec /usr/bin/python3 "$nino_tool_root/nino_pi/laptop_control.py" --config "$nino_remote_config" "$@"
else
  exec /usr/bin/python3 -m nino_pi.laptop_control --config "$nino_remote_config" "$@"
fi
