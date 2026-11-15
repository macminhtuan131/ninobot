#!/usr/bin/env bash
# Laptop only. Does not install into the RL environment or launch ROS nodes.
set -euo pipefail
nino_package="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
nino_repository="${NINO_REPO:-$(cd -- "$nino_package/../.." && pwd)}"
nino_export_env="$nino_repository/.venv-studio-export"
if [[ -L "$nino_export_env" ]]; then
  echo 'Refusing a linked export environment.' >&2
  exit 1
fi
/usr/bin/python3 -m venv --system-site-packages "$nino_export_env"
touch "$nino_export_env/COLCON_IGNORE"
"$nino_export_env/bin/python" -m pip --isolated install --disable-pip-version-check --no-input \
  --requirement "$nino_package/config/studio_export_requirements.txt"
"$nino_export_env/bin/python" -c 'import numpy, pyarrow.parquet; print("Studio export ready; NumPy", numpy.__version__)'
echo "Export interpreter: $nino_export_env/bin/python"
