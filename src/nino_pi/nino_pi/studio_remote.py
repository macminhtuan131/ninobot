"""Read-only Pi observer. Imports never connect; no publishers or driver launches."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import time
from .studio_contract import collection_config, validate_metadata
from .studio_quality import inspect_session, digest

PREFIX = '@@NINO_STUDIO@@'


def emit(state, **value):
    print(PREFIX+json.dumps(dict(state=state, **value), ensure_ascii=False, allow_nan=False), flush=True)


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    tmp.replace(path)


def discovery(config, duration=4.):
    import rosbag2_py
    from .studio_telemetry import TelemetryObserver
    observer=TelemetryObserver(config)
    start = time.monotonic()
    try:
        while time.monotonic()-start < duration:
            observer.poll()
        rows=observer.snapshot()
        # Commands may be absent while idle. They remain required at post-session QC for motion claims.
        required_sensors={'/imu/data','/motor_fb','/motor_status','/scan_raw','/tf_static'}
        missing=[r['name'] for r in rows if r['name'] in required_sensors and r['required'] and not r['count']]
        storage_ok=config['storage_id'] in rosbag2_py.get_registered_writers()
        disk=shutil.disk_usage(Path.home())
        disk_ok=disk.free >= (config['max_session_mb']+config['reserve_disk_mb'])*1024**2
        return dict(ready=not missing and storage_ok and disk_ok and not observer.errors, topics=rows,
            missing_sensors=missing, storage_available=storage_ok, storage=config['storage_id'],
            free_bytes=disk.free, disk_ok=disk_ok, errors=observer.errors, observation_duration_s=time.monotonic()-start,
            note='Short sample/graph check, not calibration, source coverage, command ownership or motion permission.')
    finally:
        observer.close()


def record(meta, duration=60.):
    """No motion: stdin supports pulse/annotation/stop-recorder only."""
    from .collect_real_data import stop_child
    meta=validate_metadata(meta)
    config=collection_config(meta['scenario'],meta['storage'])
    config['duration_s']=duration
    check=discovery(config)
    emit('CHECKED', report=check)
    if not check['ready']:
        raise ValueError('Preflight failed; no recording started')
    session_id='studio_'+meta['scenario']+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root=Path.home()/'nino_datasets/real'/session_id
    root.mkdir(parents=True, exist_ok=False)
    meta.update(schema_version=1, session_id=session_id, started_utc=datetime.now(timezone.utc).isoformat(),
        dataset_kind='real_evaluation' if meta['scenario']=='heldout' else 'real_sysid',
        motor_commands_sent=0, td3_replay_eligible=False, acquisition_source_sha256=digest(__file__),
        observer_bundle_identity=Path(__file__).resolve().parents[1].name,
        provenance_note='Observer source/config identified by bundle content hash; user firmware/controller identity remains unverified metadata.')
    save(root/'session.json',meta); save(root/'collection.json',config); save(root/'preflight.json',check)
    # Reuse existing topic QoS overrides; raw is handled by the proven separate-process collector.
    from .studio_contract import config_root
    qos=config_root()/'stm32_usb_collection_qos.yaml'
    command=[sys.executable,'-u','-m','nino_pi.collect_real_data','--config',str(root/'collection.json'),
        '--session',str(root/'session.json'),'--qos',str(qos),'--output',str(root/'raw')]
    selector=selectors.DefaultSelector();selector.register(sys.stdin,selectors.EVENT_READ);input_buffer=b''
    annotations=[]; reason='duration_reached'; last_pulse=time.monotonic(); next_emit=0.; child=None; observer=None
    def stop(signum, frame):
        raise KeyboardInterrupt
    old={s:signal.signal(s,stop) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
    try:
        with (root/'collector.log').open('x') as log:
            child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            from .studio_telemetry import TelemetryObserver
            observer=TelemetryObserver(config)
            start=time.monotonic()
            while child.poll() is None:
                observer.poll()
                now=time.monotonic()
                if now-last_pulse > 8.:
                    reason='gui_heartbeat_lost';break
                for key,_ in selector.select(.1):
                    block=os.read(key.fileobj.fileno(),65536)
                    if not block:
                        reason='connection_closed';break
                    input_buffer+=block
                    if len(input_buffer)>65536:raise ValueError('Observer input too large')
                    while b'\n' in input_buffer:
                        line,input_buffer=input_buffer.split(b'\n',1)
                        request=json.loads(line)
                        if request.get('command')=='pulse':last_pulse=time.monotonic()
                        elif request.get('command')=='stop-recorder':reason='operator_stopped_recording';break
                        elif request.get('command')=='annotation':
                            text=request.get('text','')
                            if not isinstance(text,str) or not text.strip() or len(text)>2000:
                                raise ValueError('Invalid annotation')
                            annotations.append(dict(wall_time_ns=time.time_ns(),receipt_monotonic_ns=time.monotonic_ns(),
                                text=text, clock_note='Observer receipt time, not contact/actuator event time'))
                            save(root/'annotations.json',annotations)
                            emit('ANNOTATED',count=len(annotations))
                        else:raise ValueError('Unknown observer request')
                if reason!='duration_reached':break
                if now>=next_emit:
                    next_emit=now+1.
                    emit('RECORDING',session=str(root),elapsed_s=now-start,duration_s=duration,
                         topics=observer.snapshot(),
                         note='Recorder only. Stopping recording does not stop the robot.')
            if child.poll() is None:
                emit('CLOSING',reason=reason)
                stop_child(child,grace=25)
    except BaseException:
        reason='observer_error_or_cancel';raise
    finally:
        for s in old:signal.signal(s,signal.SIG_IGN)
        if child is not None and child.poll() is None:
            stop_child(child,grace=25)
        if observer is not None:observer.close()
        selector.close()
        save(root/'annotations.json',annotations)
        save(root/'observer_lifecycle.json',dict(reason=reason,collector_exit=child.returncode if child else None,
             motor_commands_sent=0,closed_utc=datetime.now(timezone.utc).isoformat()))
        report=inspect_session(root)
        if reason!='duration_reached':
            report['verdict']='FAIL';report['level']='Q1'
            report['checks'].append(dict(name='observer_lifecycle',verdict='FAIL',detail=reason))
        save(root/'qc_report.json',report)
        emit('CLOSED',session=str(root),report=report)
        for s,handler in old.items():signal.signal(s,handler)
    return 0 if report['level']=='Q2' else 1


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('discover','record'))
    p.add_argument('--metadata-base64',required=True)
    a=p.parse_args(argv)
    import base64
    meta=json.loads(base64.urlsafe_b64decode(a.metadata_base64))
    if a.action=='discover':
        config=collection_config(meta['scenario'],meta['storage'])
        emit('CHECKED',report=discovery(config));return 0
    return record(meta)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        emit('ERROR',message=type(exc).__name__+': '+str(exc));raise
