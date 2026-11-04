"""User-invoked deploy/fetch for copyable collection recipes; never starts motion."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from .collection_recipes import RUNTIME, validate_connection


INSTALL = '''import hashlib,io,json,os,sys,zipfile
from pathlib import Path,PurePosixPath
blob=sys.stdin.buffer.read()
expected=sys.argv[1]
if hashlib.sha256(blob).hexdigest()!=expected:raise SystemExit('Upload hash mismatch')
root=Path.home()/'nino_runtime'/sys.argv[2]
marker=root/'installed_bundle.sha256'
if root.exists():
 if marker.is_file() and marker.read_text().strip()==expected:
  print('Already installed; ledger/active session unchanged:',root);raise SystemExit(0)
 raise SystemExit('Runtime exists with different/unverified content; preserve it, do not overwrite')
z=zipfile.ZipFile(io.BytesIO(blob))
for n in z.namelist():
 p=PurePosixPath(n)
 if p.is_absolute() or '..' in p.parts or not p.parts:raise SystemExit('Invalid archive path')
root.mkdir(parents=True,exist_ok=False)
z.extractall(root)
marker.write_text(expected+'\\n')
print('Installed only; no agent/stack/motor launched:',root)
'''


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('deploy','fetch'))
    p.add_argument('--host', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--output', type=Path)
    a=p.parse_args(argv)
    validate_connection(a.host,a.key)
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','-i',a.key,a.host]
    if a.action=='deploy':
        bundle=Path(__file__).with_name('collection_runtime.zip').read_bytes()
        digest=hashlib.sha256(bundle).hexdigest()
        # Script is fixed Python code, passed as one quoted remote argv string.
        import shlex
        remote='/usr/bin/python3 -c '+shlex.quote(INSTALL)+' '+digest+' '+RUNTIME
        subprocess.run(ssh+[remote],input=bundle,check=True)
    else:
        remote='''from pathlib import Path
import json
r=Path.home()/'nino_runtime'/''' + repr(RUNTIME) + '''
p=r/'last_session.json'
if not p.exists():raise SystemExit('No retained session for this runtime')
a=json.loads(p.read_text())
if not a.get('closed'):raise SystemExit('Recorder not closed; wait FINISHED')
if not a.get('output'):raise SystemExit('No new session allocated; retain readiness error')
path=Path(a['output']).resolve()
if path.parent!=Path.home()/'nino_real_data':raise SystemExit('Invalid session path')
review=a.get('review_output')
if review:
 review=Path(review).resolve()
 if review.parent!=r/'reviews':raise SystemExit('Invalid review path')
print(json.dumps(dict(session=str(path),review=str(review) if review else None)))
'''
        import shlex
        payload=json.loads(subprocess.check_output(ssh+['/usr/bin/python3 -c '+shlex.quote(remote)],text=True))
        raw=payload['session']
        # Session names are generated locally on Pi, not shell snippets.
        path=Path(raw)
        if not path.is_absolute() or path.parent.name!='nino_real_data' or not path.name.replace('_','').isalnum():
            raise ValueError('Unexpected remote session path')
        out=a.output or Path.home()/'nino_real_data_imports'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        out.mkdir(parents=True,exist_ok=False)
        subprocess.run(['scp','-r','-o','BatchMode=yes','-o','ConnectTimeout=5','-i',a.key,a.host+':'+str(path),str(out)],check=True)
        if payload.get('review'):
            review=Path(payload['review'])
            if review.parent.name!='reviews' or review.parent.parent.name!=RUNTIME or not review.name.isalnum():
                raise ValueError('Unexpected remote review path')
            subprocess.run(['scp','-r','-o','BatchMode=yes','-o','ConnectTimeout=5','-i',a.key,a.host+':'+str(review),str(out/'review')],check=True)
        print('Copied whole session to',out,'; raw unchanged on Pi. Video on phone/camera must be copied separately.')
        print('@@NINO_EVENT@@'+json.dumps(dict(job='fetch',kind='progress',state='FETCHED',
              message='Đã tải raw session và review; video cần copy riêng',
              data=dict(local_directory=str(out.resolve()),remote_session=str(path))),ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
