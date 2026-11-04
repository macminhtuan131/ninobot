"""Pilot release/ledger. No ROS imports, publishers or motion commands."""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl,hashlib,json,os
from pathlib import Path

def boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def release(root,require_ready=True):
    c=json.loads((root/'pilot_contract.json').read_text())
    if c['status']!='user_authorized' or c['maximum_attempts']!=1:raise RuntimeError('Pilot is not released for one verification attempt')
    if c['boot_id']!=boot_id():raise RuntimeError('Boot changed; stop pilot for review, do not reuse slots')
    for name,sha in c['files_sha256'].items():
        if digest(root/name)!=sha:raise RuntimeError('Frozen input changed: '+name)
    if require_ready:
        r=json.loads((root/'readiness.json').read_text())
        if not r.get('software_ready') or r.get('boot_id')!=boot_id():raise RuntimeError('Current-boot software preflight required')
    return c

def _load(root):
    p=root/'ledger.json'
    if p.exists():
        s=json.loads(p.read_text())
        if s['contract_sha256']!=digest(root/'pilot_contract.json'):raise RuntimeError('Contract changed after ledger creation')
        return s
    return {'contract_sha256':digest(root/'pilot_contract.json'),'boot_id':boot_id(),'status':'active','sequence':0,'attempts':[]}

def _save(root,s,action):
    s['sequence']+=1;s['updated_utc']=now();s['last_action']=action
    body=json.dumps(s,ensure_ascii=False,indent=2)+'\n'
    history=root/'ledger_history';history.mkdir(exist_ok=True)
    with (history/(str(s['sequence']).zfill(4)+'.json')).open('x') as f:
        f.write(body);f.flush();os.fsync(f.fileno())
    temp=root/'ledger.json.tmp'
    with temp.open('w') as f:f.write(body);f.flush();os.fsync(f.fileno())
    temp.replace(root/'ledger.json')
    fd=os.open(root,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

@contextmanager
def _locked(root):
    with (root/'ledger.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);yield

def can_begin(root):
    release(root)
    with _locked(root):
        s=_load(root)
        if s['status']!='active':raise RuntimeError('Pilot closed: '+s['status'])
        if len(s['attempts'])>=1:raise RuntimeError('One verification attempt consumed; no replacement')
        if s['attempts'] and s['attempts'][-1]['status']!='reviewed_pass':raise RuntimeError('Previous attempt needs data/operator review before the next slot')
        return len(s['attempts'])+1

def begin(root,session_id,output,conditions):
    release(root)
    with _locked(root):
        s=_load(root)
        if s['status']!='active' or len(s['attempts'])>=1:raise RuntimeError('Verification closed or one attempt consumed')
        if s['attempts'] and s['attempts'][-1]['status']!='reviewed_pass':raise RuntimeError('Previous attempt needs review')
        a={'slot':len(s['attempts'])+1,'session_id':session_id,'output':str(output),'status':'recording','motion_claimed':False,'conditions':conditions,'started_utc':now()}
        s['attempts'].append(a);_save(root,s,'begin_recording');return a

def claim_motion(root,active):
    release(root)
    with _locked(root):
        s=_load(root);a=s['attempts'][-1]
        if s['status']!='active' or a['session_id']!=active['session_id'] or a['status']!='recording' or a['motion_claimed']:raise RuntimeError('Slot is not available for one motion attempt')
        a['motion_claimed']=True;a['motion_claimed_utc']=now();_save(root,s,'claim_motion')

def finish(root,session_id,collector_returncode,error=None):
    # Closure still recorded if a boot/input problem happened after capture began.
    with _locked(root):
        s=_load(root);a=s['attempts'][-1]
        if a['session_id']!=session_id:raise RuntimeError('Closure session mismatch')
        out=Path(a['output']);m={};t={}
        try:
            m=json.loads((out/'manifest.json').read_text());t=json.loads((out/'trial_result.json').read_text())
        except (OSError,ValueError) as exc:error=error or str(exc)
        ok=not error and collector_returncode==0 and a['motion_claimed'] and not m.get('issues') and m.get('status')=='captured_not_calibrated' and t.get('source_sequence_completed') is True
        a.update(status='awaiting_review' if ok else 'failed',collector_returncode=collector_returncode,error=error,finished_utc=now(),manifest_status=m.get('status'))
        if not ok:s['status']='stopped';s['remaining_slots_closed']=1-len(s['attempts'])
        _save(root,s,'finish_recording');return a

def review(root,session_id,decision,observation,evidence):
    release(root)
    if decision not in ('pass','stop','unknown'):raise ValueError('Invalid decision')
    with _locked(root):
        s=_load(root);a=s['attempts'][-1]
        if s['status']!='active' or a['status']!='awaiting_review' or a['session_id']!=session_id:raise RuntimeError('No matching attempt awaiting review')
        if decision=='pass':
            fields=('rc_auto','vehicle_moved_forward','stopped_without_intervention','no_obvious_yaw_jerk','same_surface_load')
            if not all(observation.get(k) is True for k in fields):raise RuntimeError('Operator outcome/conditions incomplete or failed')
            if not evidence.is_file():raise RuntimeError('Review evidence absent')
            e=json.loads(evidence.read_text())
            if e.get('session')!=session_id or not e.get('review_data_pass'):raise RuntimeError('Raw/metric review incomplete')
        a.update(status='reviewed_pass' if decision=='pass' else 'reviewed_'+decision,observation=observation,review_evidence=str(evidence),review_evidence_sha256=digest(evidence) if evidence.is_file() else None,reviewed_utc=now())
        if decision!='pass':s['status']='stopped';s['remaining_slots_closed']=1-len(s['attempts'])
        elif len(s['attempts'])==1:s['status']='complete'
        _save(root,s,'review_'+decision);return s
