#!/usr/bin/env bash
# Deploy backend files only. Never starts a bridge or changes firmware.
set -euo pipefail
nino_pkg_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
nino_target="${1:-d@192.168.0.109}"
nino_key="${NINO_SSH_KEY:-$HOME/.ssh/nino_pi_flash_ed25519}"
if [[ "$nino_target" == -* || "$nino_target" =~ [[:space:]] ]]; then
  echo 'Use user@host as one argument' >&2; exit 2
fi
# Fixed relative destination resolves in the SSH user's home.
ssh -o BatchMode=yes -o ConnectTimeout=5 -i "$nino_key" "$nino_target" \
  'mkdir -p ~/nino_runtime/mode_gui_v1/nino_pi; touch ~/nino_runtime/mode_gui_v1/nino_pi/__init__.py'
scp -o BatchMode=yes -o ConnectTimeout=5 -i "$nino_key" \
  "$nino_pkg_root/nino_pi/mode_protocol.py" "$nino_pkg_root/nino_pi/mode_bridge.py" \
  "$nino_pkg_root/nino_pi/data_workflow.py" "$nino_pkg_root/nino_pi/gui_capture.py" \
  "$nino_pkg_root/nino_pi/data_quality.py" \
  "$nino_pkg_root/nino_pi/data_bridge.py" "$nino_pkg_root/nino_pi/mode_data_io.py" \
  "$nino_pkg_root/nino_pi/collect_real_data.py" "$nino_pkg_root/nino_pi/hardware_audit.py" \
  "$nino_target:nino_runtime/mode_gui_v1/nino_pi/"
scp -o BatchMode=yes -o ConnectTimeout=5 -i "$nino_key" \
  "$nino_pkg_root/config/gui_data_control.yaml" "$nino_pkg_root/scripts/start_gui_data_stack.sh" \
  "$nino_target:nino_runtime/mode_gui_v1/"
echo 'Bridge copied only. Firmware GUI v1 must be installed separately before mode switching works.'
