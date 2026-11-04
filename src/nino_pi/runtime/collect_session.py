"""One pilot recorder. No command publishers. Operator starts run_trial separately."""
from datetime import datetime,timezone
import fcntl,hashlib,json,os,sys,tempfile,time
from pathlib import Path
import collector_resilient as collect_real_data
from closure_sync import sync_session
import pilot_state
from preallocation import begin_after_ready

def main():
    root=Path(__file__).resolve().parent
    check=sys.argv[1:]==['--check']
    if sys.argv[1:] not in ([],['--check']):raise SystemExit('Usage: collect_session.py [--check]')
    pilot_state.release(root,require_ready=not check)
    profile=json.loads((root/'motion_profile.accepted.json').read_text())
    session=json.loads((root/'session.base.json').read_text())
    session_id='wheel_body_diagnostic_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=Path.home()/'nino_real_data'/session_id
    session.update(session_id=session_id,date_utc=datetime.now(timezone.utc).isoformat(),host_boot_id=pilot_state.boot_id())
    session['motion_contract']['accepted_profile']=profile
    session['pilot_contract_sha256']=pilot_state.digest(root/'pilot_contract.json')
    session['configuration_sha256']={name:pilot_state.digest(root/name) for name in ('run_trial.py','control.clear_floor.yaml','collection.json','qos.yaml')}
    with (root/'recording.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        slot=0;began=False;result=None;error=None
        if not check:
            slot=pilot_state.can_begin(root)
            print('Pilot slot',slot,'/ 1. RC AUTO, stationary, clear floor/load. No motion from recorder.',flush=True)
            metadata=json.loads(os.environ['NINO_GUI_METADATA']) if os.environ.get('NINO_GUI_METADATA') else None
            if metadata is not None:
                if not all(metadata.get(k) is True for k in ('rc_auto','clear_floor','same_load','video_ready')):
                    raise SystemExit('GUI conditions not confirmed; no slot consumed')
                pose=metadata['pose_caster_note']
            else:
                if not sys.stdin.isatty():raise SystemExit('Run recorder in an interactive terminal')
                if input('Type AUTO to confirm these conditions: ').strip()!='AUTO':raise SystemExit('Conditions not confirmed; no slot consumed')
                pose=input('Initial pose/caster/video note (unknown is allowed): ').strip() or 'unknown'
            conditions={'operator_reports_rc_auto':True,'stationary_at_start':True,'same_surface_load':True,
                        'pose_caster_note':pose,'operator_metadata':metadata}
            a=begin_after_ready(root,session_id,output,conditions);began=True
            session['pilot_slot']=a['slot'];session['pilot_conditions']=conditions
        try:
            if not check:
                marker={'session_id':session_id,'output':str(output),'pilot_slot':slot,'collector_pid':os.getpid(),'collector_start_ticks':Path('/proc/self/stat').read_text().split()[21],'boot_id':pilot_state.boot_id(),'created_monotonic_ns':time.monotonic_ns()}
                (root/'active_session.json').write_text(json.dumps(marker,indent=2)+'\n')
            print('Output:',output,flush=True)
            print('File-only check; no recording or pilot slot.' if check else 'Recorder only. Use the separate motion button (or run_trial CLI). Keep Pi powered until FINISHED.',flush=True)
            with tempfile.TemporaryDirectory(prefix='nino_pilot_') as tmp:
                form=Path(tmp)/'session.json';form.write_text(json.dumps(session,ensure_ascii=False,indent=2)+'\n')
                args=['--config',str(root/'collection.json'),'--session',str(form),'--qos',str(root/'qos.yaml'),'--output',str(output)]
                if check:args.append('--check')
                result=collect_real_data.main(args)
                if not check:sync_session(output)
        except BaseException as exc:
            error=str(exc);raise
        finally:
            if began:
                a=pilot_state.finish(root,session_id,result,error)
                print('Pilot slot status:',a['status'],'; stop here for data/operator review.',flush=True)
            active=root/'active_session.json'
            if not check and active.exists() and json.loads(active.read_text()).get('session_id')==session_id:active.unlink()
        if began and result==0:print('FINISHED: recorder closed; session files synced. Review required before next slot.',flush=True)
        return result
if __name__=='__main__':raise SystemExit(main())
