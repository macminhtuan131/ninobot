"""Fixed SSH transport for observer-only Studio; immutable content-addressed install."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import zipfile
from .collection_recipes import validate_connection
from .collection_deploy import INSTALL
from .studio_contract import config_root
from .studio_remote import PREFIX

MODULES=('__init__.py','studio_contract.py','studio_remote.py','studio_telemetry.py','studio_quality.py','bag_io.py',
         'collect_real_data.py','hardware_audit.py','state_monitor.py')


def bundle():
    output=io.BytesIO();root=Path(__file__).parent
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in MODULES:
            info=zipfile.ZipInfo('nino_pi/'+name, date_time=(2026,11,4,0,0,0))
            z.writestr(info,(root/name).read_bytes())
        for name in ('stm32_usb_collection.json','real_collection_residual_diagnostic.json','stm32_usb_collection_qos.yaml'):
            info=zipfile.ZipInfo('config/'+name,date_time=(2026,11,4,0,0,0))
            z.writestr(info,(config_root()/name).read_bytes())
    data=output.getvalue();sha=hashlib.sha256(data).hexdigest()
    return data,sha,'studio_observer_v1_'+sha[:16]


def remote_command(action, payload):
    if action not in ('discover','record') or not re.fullmatch('[A-Za-z0-9_=-]+',payload):
        raise ValueError('Invalid observer action/payload')
    _,_,namespace=bundle()
    # Known driver env contains middleware profile. Sourcing does not launch drivers.
    script='source "$HOME/pi5-stm32-slam-main/scripts/env.sh" || exit 1\n'
    script+='export ROS_DOMAIN_ID=0\n'
    script+='export PYTHONPATH="$HOME/nino_runtime/'+namespace+':${PYTHONPATH:-}"\n'
    script+='exec /usr/bin/python3 -u -m nino_pi.studio_remote '+action+' --metadata-base64 '+payload
    return 'bash -c '+shlex.quote(script)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('deploy','fetch','export'))
    p.add_argument('--host');p.add_argument('--key');p.add_argument('--session');p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    if a.action=='export':
        from .dataset_exporter import export_session
        result=export_session(a.session,a.output)
        print(PREFIX+json.dumps(dict(state='EXPORTED',report=result,local_directory=str(a.output.resolve()))),flush=True)
        return 0
    validate_connection(a.host,a.key)
    ssh=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=5','-i',a.key,a.host]
    if a.action=='deploy':
        data,sha,namespace=bundle()
        subprocess.run(ssh+['/usr/bin/python3 -c '+shlex.quote(INSTALL)+' '+sha+' '+namespace],input=data,check=True)
        print(PREFIX+json.dumps(dict(state='INSTALLED',namespace=namespace,sha256=sha)),flush=True)
        return 0
    path=Path(a.session)
    if not path.is_absolute() or path.parent.parts[-2:]!=('nino_datasets','real') or not re.fullmatch('studio_[A-Za-z0-9_]+',path.name):
        raise ValueError('Invalid observer session path')
    # Refuse live copying. No JSON or stdout is allowed to bypass this remote check.
    code='from pathlib import Path; import json; p=Path('+repr(str(path))+'); json.loads((p/"observer_lifecycle.json").read_text()); print("closed")'
    subprocess.run(ssh+['/usr/bin/python3 -c '+shlex.quote(code)],check=True)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    subprocess.run(['scp','-r','-o','BatchMode=yes','-o','ConnectTimeout=5','-i',a.key,a.host+':'+str(path),str(out)],check=True)
    local=out/path.name
    from .studio_quality import inspect_session
    report=inspect_session(local)
    # Derived verification is outside the original copied session.
    (out/'import_qc.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    from .studio_index import register
    register(local,report)
    print(PREFIX+json.dumps(dict(state='FETCHED',local_directory=str(local),report=report),ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
