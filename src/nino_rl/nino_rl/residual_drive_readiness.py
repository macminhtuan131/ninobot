"""One zero-only qualification of drive readiness; no actor/optimizer/hardware."""
import argparse
from datetime import datetime,timezone
import fcntl,hashlib,json,math,signal,time
from pathlib import Path
from . import residual_coverage_study_v2 as parent
from .drive_readiness_candidate import DriveReadinessBackend
from .reliable_episode import EpisodeLifecycle
from .residual_workflow import save,emit,latest,runtime_versions
from .residual_experiment import source_fingerprint

ACTION='sim-drive-readiness'
PROTOCOL_ID='nino_drive_readiness_zero_v1_2026_11_06'
PARENT_MANIFEST='0ba2d7fd3b9d98dff78e8dc27c8f1384a8f6b0d4efff113ad668b3b12c7ca7ca'


def protocol():
    return dict(protocol_id=PROTOCOL_ID,condition_stops_s=[6.,8.],zero_ticks_per_launch=10,
        control_interval_s=.1,maximum_setup_sim_s=5.,continuous_ready_quiet_s=.5,
        maximum_support_age_s=.04,maximum_launches=2,maximum_control_ticks=20,
        optimizer_updates=0,actor_loads=0,hardware_actions=0,retries=0,wall_deadline_s=900,
        qualification_scope='drive_ack_before_task_epoch_and_zero_only_not_learning_or_motion_benefit')


def fingerprint():
    base=parent.frozen.repo()/'src/nino_rl'
    files=['nino_rl/residual_drive_readiness.py','nino_rl/drive_readiness_candidate.py',
        'nino_rl/coverage_reset_readiness.py','scripts/residual_drive_readiness.sh',
        'test/test_drive_readiness_candidate.py','test/test_coverage_reset_readiness.py',
        'test/test_drive_readiness_job.py',
        'test/fixtures/coverage_v2_initial_permission_failure.json']
    return hashlib.sha256(json.dumps(dict(parent=parent.fingerprint(),
        files={f:parent.sha(base/f) for f in files}),sort_keys=True).encode()).hexdigest()


def source(check_runtime=True):
    parent.source(check_runtime)
    out=Path.home()/'nino_research/sim_coverage_study_v2/20261106T111842753138Z_sim-coverage-v2-study'
    if parent.sha(out/'manifest.json')!=PARENT_MANIFEST:raise ValueError('Parent V2 manifest changed')
    m=parent.read(out/'manifest.json')
    if m['coverage_fingerprint']!=parent.fingerprint() or m['status']!='failed':raise ValueError('V2 parent identity changed')
    for name,value in m['files'].items():
        path=(out/name).resolve()
        if not path.is_relative_to(out.resolve()) or parent.sha(path)!=value:raise ValueError('V2 artifact changed')
    return out


def release_record():return parent.read(parent.frozen.repo()/'src/nino_rl/config/drive_readiness_release_v1.json')


def release_ready(root=None):
    r=release_record()
    if (r.get('released') is not True or r.get('fingerprint')!=fingerprint()
            or r.get('protocol_id')!=PROTOCOL_ID or r.get('hardware_authorized') is not False):
        raise ValueError('Zero qualification not released')
    if root is not None and Path(r['result_root']).resolve()!=Path(root).resolve():
        raise ValueError('Zero qualification release belongs to a different root')
    report=Path(r['software_test_report'])
    if parent.sha(report)!=r['software_test_report_sha256']:raise ValueError('Software test report changed')
    import xml.etree.ElementTree as ET
    suites=list(ET.parse(report).getroot().iter('testsuite'))
    if not suites or any(int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')):
        raise ValueError('Readiness software gate not passed')
    return r


def require_ready(view):
    ages=list(view.get('input_ages_s',{}).values())
    if (view.get('permission') is not True or view.get('sensors_fresh') is not True
            or view.get('fault') is not False or view.get('emergency_stop') is not False
            or not ages or any(not math.isfinite(a) or not 0<=a<=.04+1e-9 for a in ages)):
        raise ValueError('Input not ready before zero tick; no permission override')


def qualify(out):
    worlds=parent.frozen.prepare_worlds(out);runs=[]
    for i,stop in enumerate((6.,8.)):
        target=out/f'zero_{i}';target.mkdir()
        c,g,task,bc=parent.configuration(stop)
        c['purpose']=task['protocol_id']=PROTOCOL_ID
        lp=parent.lifecycle_protocol(True);lp['protocol_id']=PROTOCOL_ID
        backend=EpisodeLifecycle(c,target/'episodes',worlds['clear_box'],g,task,bc,lp,
            backend_factory=DriveReadinessBackend)
        rows=[];error=None
        try:
            view,reset=backend.reset(seed=701)
            save(target/'reset.json',reset);save(target/'initial_view.json',view)
            require_ready(view)
            for step in range(10):
                require_ready(view)
                parent.frozen.append(target/'control_attempts.jsonl',dict(step=step,requested=[0.,0.]))
                view,labels,term,trunc,info=backend.advance_reference(0.,0.,.1)
                row=dict(step=step,requested=[0.,0.],**info)
                parent.frozen.append(target/'trace.jsonl',row)
                require_ready(view)
                if term or trunc or info['final_ros_reference']!=[0.,0.] or info['applied_target_rad_s']!=[0.,0.]:
                    raise ValueError('Zero-only command/target or lifecycle violated')
                rows.append(row)
            backend.current.flush_raw()
        except BaseException as exc:
            error=exc;save(target/'failure.json',dict(error=repr(exc),valid_zero_ticks=len(rows)));raise
        finally:
            try:backend.close()
            except BaseException as exc:
                save(target/'cleanup_failure.json',dict(error=repr(exc),original=repr(error)))
                if error is None:raise
        episode=backend.directory/backend.namespace
        settling=parent.read(episode/'backend/episode_0/settling.json')
        checks=[json.loads(l) for l in (episode/'boundary_checks.jsonl').read_text().splitlines()]
        exit_record=parent.read(episode/'independent/process_exit.json')
        if (not settling['passed'] or exit_record!=dict(returncode=0,shutdown_ack=True)
                or any(not r['primary_after']['supported'] or not r['independent']['supported'] for r in checks)):
            raise ValueError('Readiness/support/closure qualification failure')
        run=dict(source_stop_plan_s=stop,zero_control_ticks=len(rows),drive_ack_before_first_tick=True,
            settling_steps=len(settling['rows']),setup_controlled_sim_s=.1*len(settling['rows']),
            initially_blocked_setup_rows=sum(not r['readiness']['ready'] for r in settling['rows']),
            feedback_checks=len(checks),maximum_joint_age_ms=max(max(r['primary_after']['age_ns'],
                r['independent']['age_ns'])/1e6 for r in checks),observer_closure_ack=True)
        runs.append(run);save(target/'summary.json',run)
        emit(ACTION,f'Zero qualification {i+1}/2 closed',(i+1)/2,result=run)
    result=dict(qualification_pass=True,runs=runs,gazebo_launches=2,zero_control_ticks=20,
        optimizer_updates=0,actor_loads=0,hardware_actions=0,benefit_verified=False,
        no_learning_or_motion_comparison=True,remaining_slots_closed=True)
    save(out/'qualification_result.json',result);return result


def validated_latest(root,check_runtime=True):
    out=latest(root,ACTION,check_runtime=check_runtime)
    if parent.read(out/'manifest.json')['readiness_fingerprint']!=fingerprint():raise ValueError('Readiness sources changed')
    source(check_runtime);return out


def retained_failure(root):
    root=Path(root).resolve()
    try:
        row=parent.read(root/'state.json')['runs'][-1]
        if row['action']!=ACTION or row['status'] not in ('failed','cancelled'):return None
        out=(root/row['path']).resolve();m=parent.read(out/'manifest.json')
        if out.parent!=root or m['readiness_fingerprint']!=fingerprint() or m['status']!=row['status']:return None
        for name,value in m['files'].items():
            path=(out/name).resolve()
            if not path.is_relative_to(out) or parent.sha(path)!=value:return None
        return dict(state='retained_failure',path=str(out),label='READINESS ĐÃ ĐÓNG DO LỖI · KHÔNG RETRY',error=row['error'])
    except (OSError,ValueError,KeyError,TypeError,IndexError):return None


def run(root):
    root=Path(root).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    global_lock=Path.home()/'nino_research/.factory_sim.lock';global_lock.parent.mkdir(parents=True,exist_ok=True)
    with global_lock.open('a') as shared,(root/'.job.lock').open('a') as lock:
        fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'state.json').exists():raise ValueError('Zero qualification already consumed; no retry/foreign root')
        release=release_ready(root);src=source();current=fingerprint()
        out=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+ACTION);out.mkdir()
        row=dict(action=ACTION,path=out.name,status='running',error=None)
        state=dict(schema_version=1,latest={},runs=[row]);save(root/'state.json',state)
        save(out/'protocol.json',protocol());save(out/'release.json',release)
        save(out/'dependencies.json',dict(artifact=str(src),manifest_sha256=PARENT_MANIFEST))
        status,error,result='running',None,None;started=time.monotonic()
        def timeout(*args):raise TimeoutError('Zero qualification wall deadline')
        old=signal.signal(signal.SIGALRM,timeout);signal.alarm(900)
        try:
            emit(ACTION,'Two zero-only launches; no actor or optimizer')
            result=qualify(out)
            if fingerprint()!=current:raise ValueError('Readiness source changed during job')
            source();status='completed'
        except BaseException as exc:
            status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed';error=str(exc);raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,old)
            save(out/'job.json',dict(action=ACTION,status=status,error=error,wall_s=time.monotonic()-started,hardware_actions=0))
            save(out/'manifest.json',dict(action=ACTION,status=status,readiness_fingerprint=current,
                source_fingerprint=source_fingerprint(),runtime=runtime_versions(),hardware_actions=0,
                files={str(f.relative_to(out)):parent.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='manifest.json'}))
            row.update(status=status,error=error)
            if status=='completed':state['latest'][ACTION]=out.name
            save(root/'state.json',state);emit(ACTION,status,1. if status=='completed' else None,directory=str(out),result=result,error=error)
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:run(args.output)
    except (Exception,KeyboardInterrupt) as exc:print('Readiness qualification failed/retained:',exc,flush=True);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
