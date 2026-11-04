"""Rebuild package resource from tracked prepared helpers. Never contacts the Pi."""
from pathlib import Path
import hashlib
import json
import zipfile

PACKAGE=Path(__file__).resolve().parents[1]
SOURCE=PACKAGE/'runtime'

def build(target=None):
    files={str(p.relative_to(SOURCE)):p.read_bytes() for p in SOURCE.rglob('*')
           if p.is_file() and p.suffix in ('.py','.json','.yaml') and '__pycache__' not in p.parts}
    files['session.sh']=b'''#!/usr/bin/env bash
set -eo pipefail
nino_job_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$nino_job_root/tooling:$nino_job_root${PYTHONPATH:+:$PYTHONPATH}"
if [[ "${1:-}" != plan && "${1:-}" != status ]]; then
  source "$HOME/pi5-stm32-slam-main/scripts/env.sh"
  source "$HOME/nino_pi_ws/install/setup.bash"
  export ROS_DOMAIN_ID=0
  export PYTHONPATH="$nino_job_root/tooling:$nino_job_root${PYTHONPATH:+:$PYTHONPATH}"
fi
if [[ "${2:-}" == --gui ]]; then
  exec /usr/bin/python3 -u "$nino_job_root/job_gateway.py" "$@"
fi
exec /usr/bin/python3 -u "$nino_job_root/session_cli.py" "$@"
'''
    for name in ('__init__.py','collect_real_data.py','hardware_audit.py','data_quality.py','research_plan.json'):
        files['tooling/nino_pi/'+name]=(PACKAGE/'nino_pi'/name).read_bytes()
    files['payload_hashes.json']=(json.dumps({n:hashlib.sha256(b).hexdigest() for n,b in files.items()},sort_keys=True,indent=2)+'\n').encode()
    target=target or PACKAGE/'nino_pi/collection_runtime.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in sorted(files.items()):
            item=zipfile.ZipInfo(name,date_time=(2026,11,3,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(item,blob)
    print('Prepared GUI runtime:',target,'files:',len(files),'sha256:',hashlib.sha256(target.read_bytes()).hexdigest())
    return target

if __name__=='__main__':build()
