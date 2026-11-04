#!/usr/bin/env bash
# Install a per-user desktop entry. Does not touch Pi, ROS, or firmware.
set -euo pipefail
nino_script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
/usr/bin/python3 -c 'from PyQt5 import QtWidgets' || {
  echo 'Install GUI dependency: sudo apt install python3-pyqt5' >&2; exit 1;
}
/usr/bin/python3 - "$nino_script_root/mode_gui.sh" <<'PY'
from pathlib import Path
import sys
launcher = str(Path(sys.argv[1]).resolve())
# Desktop Entry Exec uses double quotes, not shell quoting.
escaped = launcher.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
entry = ('[Desktop Entry]\nType=Application\nName=Nino Real Data Studio\n'
         'Comment=Observer GUI v7: sensor, recorder, QC, Parquet, TD3 parameters\n'
         f'Exec=bash "{escaped}"\nIcon=input-gaming\nTerminal=false\nCategories=Utility;\n')
target = Path.home()/'.local/share/applications/nino-control-modes.desktop'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(entry)
print(target)
PY
