"""Fixed-job, heartbeat-supervised GUI gateway. No arbitrary shell or auto motion."""
import argparse
import base64
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
PREFIX='@@NINO_EVENT@@'
JOBS={'connect-sensors','inventory','start-stack','record-diagnostic','run-trial','stationary','review','status','observation'}


def emit(job,state,message='',**data):
    value=dict(job=job,kind='progress',state=state,message=message,data=data)
    try:print(PREFIX+json.dumps(value,ensure_ascii=False,allow_nan=False),flush=True)
    except BrokenPipeError:pass  # Cleanup must still reach the owned child after SSH loss.


def validate(job,metadata):
    if job not in JOBS or not isinstance(metadata,dict):raise ValueError('Unsupported fixed job')
    if job=='record-diagnostic' and not all(metadata.get(k) is True for k in ('rc_auto','clear_floor','same_load','video_ready')):
        raise ValueError('Explicit operator conditions missing')
    if job in ('stationary','record-diagnostic'):
        if not all(isinstance(metadata.get(k),str) and metadata[k].strip() for k in ('pose_caster_note','floor_load_note')):
            raise ValueError('Pose/caster and floor/load metadata required')
    if job=='run-trial' and metadata.get('confirm_motion') is not True:raise ValueError('Motion click missing')


def recorder_snapshot(job, started=0):
    marker=ROOT/'active_session.json' if job=='record-diagnostic' else ROOT/'last_session.json'
    try:
        if marker.stat().st_mtime<started-0.01:return None
        m=json.loads(marker.read_text());directory=Path(m['output'])
        counts={}
        for path in (directory/'bag').glob('*.db3'):
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.02) as db:
                for name,count in db.execute('SELECT t.name,count(m.id) FROM topics t LEFT JOIN messages m ON t.id=m.topic_id GROUP BY t.id'):
                    counts[name]=counts.get(name,0)+count
        need=('/imu/data','/motor_fb','/motor_status','/scan_raw')
        if job=='record-diagnostic':need+=('/cmd_vel',)
        # Pre-motion source/enable are EVENT channels. Their first message must
        # not be invented to make a recorder-ready check pass.
        ready=all(counts.get(k,0)>0 for k in need)
        remaining=max(0.,60-(time.monotonic_ns()-m['created_monotonic_ns'])/1e9) if m.get('created_monotonic_ns') else None
        return dict(directory=str(directory),session_id=m.get('session_id',directory.name),
                    ready=ready,counts=counts,remaining_s=remaining)
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):return None


def result_data(job,started):
    if job=='connect-sensors':return 'SENSORS_AVAILABLE',dict(not_readiness=True)
    if job=='inventory':
        reports=sorted((ROOT/'inventory').glob('*/report.json'),key=lambda p:p.stat().st_mtime)
        recent=[p for p in reports if p.stat().st_mtime>=started-1]
        if not recent:raise RuntimeError('Inventory report absent')
        report=json.loads(recent[-1].read_text())
        if report.get('status')!='collected_not_hardware_certified':raise RuntimeError('Inventory incomplete; see raw report')
        ledger=json.loads((ROOT/'ledger.json').read_text()) if (ROOT/'ledger.json').exists() else {}
        return 'INVENTORY_READY',dict(report_path=str(recent[-1]),report=report,
                                      diagnostic_used=bool(ledger.get('attempts')),not_motion_readiness=True)
    if job in ('stationary','record-diagnostic'):
        path=ROOT/'last_session.json'
        if path.stat().st_mtime<started-.01:raise RuntimeError('No current session marker')
        marker=json.loads(path.read_text())
        if not marker.get('closed') or not marker.get('output'):raise RuntimeError('Recorder did not close a new session')
        directory=Path(marker['output']);manifest=json.loads((directory/'manifest.json').read_text())
        return 'FINISHED',dict(directory=str(directory),manifest_status=manifest.get('status'),recorder_closed=True,
                               body_motion_verified=False)
    if job in ('review','observation'):
        marker=json.loads((ROOT/'last_session.json').read_text());out=Path(marker['review_output'])
        data=json.loads((out/'raw_quality.json').read_text())
        data.update(review_directory=str(out),observation_saved=(out/'operator_observation.json').is_file())
        return ('REVIEW_READY' if job=='review' else 'OBSERVATION_SAVED'),data
    if job=='status':
        ledger=json.loads((ROOT/'ledger.json').read_text()) if (ROOT/'ledger.json').exists() else {}
        return 'STATUS_READY',dict(diagnostic_used=bool(ledger.get('attempts')),ledger_status=ledger.get('status','not_started'))
    if job=='run-trial':
        marker=json.loads((ROOT/'active_session.json').read_text());r=json.loads((Path(marker['output'])/'trial_result.json').read_text())
        if r.get('source_sequence_completed') is not True:raise RuntimeError('Trial incomplete')
        return 'ZERO_DISABLED',dict(source_sequence_completed=True,body_motion_verified=False)
    return 'CLOSED',{}


def run(job,metadata):
    validate(job,metadata)
    env=dict(os.environ,NINO_GUI_METADATA=json.dumps(metadata,ensure_ascii=False),PYTHONUNBUFFERED='1')
    child=subprocess.Popen([sys.executable,'-u',str(ROOT/'session_cli.py'),job],stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,start_new_session=True)
    selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ,'output')
    selector.register(sys.stdin,selectors.EVENT_READ,'input')
    output=b'';incoming=b'';pulse=time.monotonic();cancelled=False;cancel_at=None;last_probe=0.;started=time.time()
    journal=ROOT/'gui_jobs';journal.mkdir(exist_ok=True)
    path=journal/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+job+'.jsonl')
    ready_sent=False
    def cancel(reason):
        nonlocal cancelled,cancel_at
        if cancelled:return
        cancelled=True;cancel_at=time.monotonic()
        if child.poll() is None:os.killpg(child.pid,signal.SIGINT)
        emit(job,'CANCELLING',reason,remote_child_pid=child.pid)
    previous_handlers={sig:signal.signal(sig,lambda signum,frame:cancel('Gateway signal '+str(signum))) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        emit(job,'RUNNING','Process bắt đầu; chưa xác nhận readiness',remote_child_pid=child.pid)
        while child.poll() is None:
            for key,_ in selector.select(.05):
                chunk=os.read(key.fileobj.fileno(),65536)
                if key.data=='input':
                    if not chunk:selector.unregister(sys.stdin);cancel('GUI stdin closed')
                    incoming+=chunk
                    while b'\n' in incoming:
                        line,incoming=incoming.split(b'\n',1)
                        try:command=json.loads(line)
                        except ValueError:cancel('Invalid GUI input');continue
                        if command.get('command')=='pulse':pulse=time.monotonic()
                        elif command.get('command')=='cancel':cancel('Operator cancellation')
                    if len(incoming)>16384:cancel('Oversized GUI input')
                else:
                    if not chunk:
                        selector.unregister(child.stdout);continue
                    output+=chunk
                    while b'\n' in output:
                        line,output=output.split(b'\n',1);text=line.decode(errors='replace')
                        print(text,flush=True)
                        with path.open('a') as f:f.write(json.dumps(dict(wall_ns=time.time_ns(),text=text),ensure_ascii=False)+'\n')
                        if text.startswith('SENSORS:'):emit(job,'SENSORS_AVAILABLE','Kết nối sensor được giữ; bấm kiểm thiết bị để xác minh dữ liệu thật')
                        elif 'READY: lifecycle active' in text:emit(job,'STACK_READY','Stack đang ở ZERO; chưa enable motor')
                        elif text.startswith('FORWARD reference'):emit(job,'FORWARD','Source tiến 0,05 m/s; chưa xác nhận thân tiến')
                        elif text.startswith('ZERO/disable requested'):emit(job,'ZERO_DISABLED','Đã yêu cầu zero/disable; tiếp tục quan sát')
                    if len(output)>65536:cancel('Unbounded output line')
            if time.monotonic()-pulse>1.5:cancel('GUI heartbeat stale; closing owned child')
            if job in ('stationary','record-diagnostic') and not cancelled and time.monotonic()-last_probe>.5:
                last_probe=time.monotonic();snapshot=recorder_snapshot(job,started)
                if snapshot:
                    if snapshot['ready']:
                        ready_sent=True;emit(job,'RECORDING_READY','Bag đã có raw/command ban đầu; một nút tiến riêng',**snapshot)
                    else:emit(job,'WAITING_DATA','Đang chờ samples ban đầu',**snapshot)
            if cancel_at and time.monotonic()-cancel_at>55:
                os.killpg(child.pid,signal.SIGKILL)
                emit(job,'FORCED_UNKNOWN','Forced shutdown; giữ raw incomplete, không khẳng định motor stop')
                break
        rc=child.wait()
        tail=child.stdout.read().decode(errors='replace') if child.stdout else ''
        if tail:print(tail,flush=True)
        if cancelled:return 1
        if rc:
            retained={}
            if job in ('stationary','record-diagnostic'):
                try:_,retained=result_data(job,started)
                except (OSError,ValueError,RuntimeError,KeyError):pass
            emit(job,'FAILED','Tác vụ lỗi; giữ log/raw, không tự chạy lại',returncode=rc,**retained)
            return rc
        state,data=result_data(job,started);emit(job,state,'Hoàn tất bước; quality/body claim được review riêng',**data)
        return 0
    finally:
        for sig,handler in previous_handlers.items():signal.signal(sig,handler)
        selector.close()
        if child.poll() is None:
            cancel('Gateway exiting')
            try:child.wait(timeout=55)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('job',choices=sorted(JOBS));p.add_argument('--gui',action='store_true')
    p.add_argument('--metadata-base64',required=True);a=p.parse_args(argv)
    if len(a.metadata_base64)>16000:raise ValueError('Metadata too large')
    metadata=json.loads(base64.urlsafe_b64decode(a.metadata_base64.encode()))
    return run(a.job,metadata)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError) as e:
        print('GUI gateway error:',e,flush=True);raise SystemExit(1)
