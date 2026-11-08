"""Read-only local training discovery/log tail. Never starts or signals a worker."""
import json
import os
from pathlib import Path
import re
import time

PREFIX='@@NINO_RESEARCH@@'
MODULES={'nino_rl.training_studio_api','nino_rl.common_training_studio','nino_rl.td3_training_studio'}


def read_json(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default


def normalized(request):
    value=dict(request);value.pop('engine',None);value['schema_version']=1
    return value


def process_identity(path):
    # /proc/stat comm may contain spaces/parentheses; fields after its last ')'
    # start at field3, so starttime (field22) has offset19.
    return (path/'stat').read_text().rsplit(')',1)[1].split()[19]


def discover(roots=None,proc=Path('/proc')):
    roots=None if roots is None else {Path(p).expanduser().resolve() for p in roots}
    result=[]
    for process in proc.iterdir():
        if not process.name.isdigit():continue
        try:
            if process.stat().st_uid!=os.getuid():continue
            argv=(process/'cmdline').read_bytes().decode().strip('\0').split('\0')
            if '-m' not in argv or argv[argv.index('-m')+1] not in MODULES:continue
            request_path=Path(argv[argv.index('--request')+1]).expanduser().resolve()
            root=Path(argv[argv.index('--output')+1]).expanduser().resolve()
            if roots is not None and root not in roots:continue
            request=read_json(request_path)
            if not isinstance(request,dict) or type(request.get('timesteps')) is not int or request['timesteps']<=0:continue
            log=None
            try:
                target=Path(os.readlink(process/'fd/1'))
                if target.is_absolute() and target.is_file():log=target
            except OSError:pass
            if log is None:
                candidate=root/'ui_logs'/(request_path.stem+'.log')
                if candidate.is_file():log=candidate
            directory=None
            if log:
                with log.open('rb') as stream:head=stream.read(65536).decode('utf8','replace')
                for line in head.splitlines():
                    if line.startswith(PREFIX):
                        try:event=json.loads(line[len(PREFIX):])
                        except ValueError:continue
                        if event.get('directory'):
                            candidate=Path(event['directory']).resolve()
                            if candidate.parent==root:directory=candidate;break
            if directory is None:
                candidates=[]
                for path in sorted(root.glob('*/job.json'),reverse=True):
                    job=read_json(path,{})
                    if job.get('status')=='running' and normalized(job.get('request',{}))==normalized(request):
                        candidates.append(path.parent)
                # Equal requests alone cannot identify two concurrent jobs.
                if len(candidates)==1:directory=candidates[0]
            if directory is None:continue
            job=read_json(directory/'job.json',{})
            if job.get('status')!='running' or normalized(job.get('request',{}))!=normalized(request):continue
            result.append(dict(pid=int(process.name),start_time=process_identity(process),
                proc=str(process),root=str(root),directory=str(directory),
                engine=request.get('engine','common103_v1' if argv[argv.index('-m')+1]=='nino_rl.common_training_studio' else 'legacy100_v1'),
                request_path=str(request_path),request=request,log_path=str(log) if log else None))
        except (OSError,ValueError,IndexError,KeyError,TypeError):continue
    return sorted(result,key=lambda r:r['directory'],reverse=True)


def alive(worker):
    try:
        path=Path(worker['proc'])
        return process_identity(path)==worker['start_time'] and (path/'cmdline').read_bytes()!=b''
    except (OSError,ValueError,IndexError):return False


class LiveJob:
    """A reader remains useful after the worker exits; completion needs job.json."""
    def __init__(self,worker):
        self.worker=worker;self.directory=Path(worker['directory']);self.offset=0
        self.inode=None;self.buffer=b'';self.event={};self.start=0;self.start_updates=None
        self.documents={}
        request=worker['request']
        if request.get('resume'):
            p=Path(request['resume']).expanduser()
            if p.is_file():p=p.parent
            meta=read_json(p/'checkpoint.json',{})
            self.start=meta.get('global_steps',0);self.start_updates=meta.get('optimizer_updates')

    def document(self,name,kind,default):
        value=read_json(self.directory/name)
        if isinstance(value,kind):self.documents[name]=value
        # A concurrent partial write must not erase the last known job state.
        return self.documents.get(name,default)

    def tail(self):
        path=self.worker.get('log_path')
        if not path:return []
        try:
            path=Path(path);stat=path.stat();identity=(stat.st_dev,stat.st_ino)
            with path.open('rb') as stream:
                if identity!=self.inode or stat.st_size<self.offset:
                    self.offset=max(0,stat.st_size-262144);self.buffer=b'';self.inode=identity
                    stream.seek(self.offset)
                    if self.offset:stream.readline()  # discard one partial leading line
                else:stream.seek(self.offset)
                data=stream.read(262144);self.offset=stream.tell()
            self.buffer+=data;lines=self.buffer.split(b'\n');self.buffer=lines.pop()
            return [line.decode('utf8','replace') for line in lines]
        except OSError:return []

    def poll(self):
        lines=self.tail();shown=[]
        for line in lines:
            if line.startswith(PREFIX):
                try:event=json.loads(line[len(PREFIX):])
                except ValueError:shown.append(line);continue
                if event.get('action') in ('td3-common-studio','td3-studio'):
                    for key in ('phase','progress','global_steps','checkpoint','message','error'):
                        if event.get(key) is not None:self.event[key]=event[key]
                    match=re.search(r'critic (\d+)',event.get('message',''))
                    if match:self.event['critic_updates_reported']=int(match.group(1))
                if event.get('message'):shown.append(event['message'])
            else:shown.append(line)
        job=self.document('job.json',dict,{})
        coverage=self.document('coverage.json',dict,{})
        final_result=self.document('result.json',dict,{})
        result=final_result or self.document('training_result.json',dict,{})
        final=bool(final_result)
        total=self.worker['request']['timesteps']
        current=max(self.event.get('global_steps',self.start),self.start+coverage.get('total',0))
        if result:current=result.get('global_steps',current)
        done=max(0,min(total,current-self.start))
        checkpoints=[]
        for p in sorted((self.directory/'checkpoints').glob('*/checkpoint.json')):
            if not p.parent.name.startswith('.') and (p.parent/'manifest.json').is_file():checkpoints.append(str(p.parent))
        worker_alive=alive(self.worker);status=job.get('status','running')
        if status=='running' and not worker_alive:status='worker_missing'
        evaluation=self.document('evaluation_progress.json',list,[])
        stat_path=Path(self.worker['log_path']) if self.worker.get('log_path') else self.directory/'coverage.json'
        try:age=max(0,time.time()-stat_path.stat().st_mtime)
        except OSError:age=None
        return dict(worker=self.worker,status=status,worker_alive=worker_alive,
            directory=str(self.directory),starting_global_steps=self.start,global_steps=current,
            additional_steps=done,total_steps=total,progress=done/total,
            phase='evaluate' if result and status=='running' else self.event.get('phase','prepare'),
            critic_updates=result.get('optimizer_updates_total') if result else self.event.get('critic_updates_reported',self.start_updates),
            critic_count_is_logged=not bool(result),actor_updates=result.get('actor_updates_total') if result else None,
            result=result,final_result=final,error=job.get('error'),coverage=coverage,
            checkpoints=checkpoints,evaluation_runs=len(evaluation) if isinstance(evaluation,list) else 0,
            log_lines=shown[-300:],log_age_s=age)
