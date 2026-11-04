"""Start zero-output stack, wait for active lifecycle AND measured zero trace.
No source/motor-enable publishers. No configure/activate retries. Old pilot unchanged.
"""
import argparse,json,os,signal,subprocess,time,hashlib
from datetime import datetime,timezone
from pathlib import Path
import stack_readiness

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-once',action='store_true',help='Stop own stack after bounded zero check');a=p.parse_args()
    import rclpy
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    root=Path(__file__).resolve().parent;config=root/'control.clear_floor.yaml'
    assert hashlib.sha256(config.read_bytes()).hexdigest()=='5bd90e4d10ec0f1c21745e444b94f11f06021e94c019720ca9bce4c0f3898489'
    ident=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO);n=Node('nino_checked_start',enable_rosout=False,start_parameter_services=False);obs=stack_readiness.Observer(n)
    child=None;log=None;report={'check_id':ident,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'source_commands_sent':0,'enable_requests_sent':0,'automatic_restart_or_transition_retry':False,'old_pilot_reopened':False};exit_code=1
    old={}
    def interrupted(sig,frame):raise KeyboardInterrupt
    for sig in (signal.SIGINT,signal.SIGTERM):old[sig]=signal.signal(sig,interrupted)
    try:
        end=time.monotonic()+3
        while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.02)
        for t in (*stack_readiness.TOPICS,'/cmd_vel_teleop','/cmd_vel_nav','/cmd_mit','/cmd_torque','/motor_enable'):
            if n.get_publishers_info_by_topic(t):raise RuntimeError('Existing owner on '+t)
        if obs.status is None or time.monotonic()-obs.status_time>.6 or obs.status&3!=3 or obs.status&76:raise RuntimeError('Fresh nonfault wheel status required')
        log=(root/(ident+'.launch.log')).open('x')
        child=subprocess.Popen(['ros2','launch','nino_pi','teleop.launch.py','control_params:='+str(config)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        report['launch_pid']=child.pid;report['launch_start_ticks']=Path('/proc') .joinpath(str(child.pid),'stat').read_text().split()[21]
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            rclpy.spin_once(n,timeout_sec=.02);obs.poll()
            if child.poll() is not None:raise RuntimeError('Command stack exited during startup')
            s=obs.snapshot()
            if s['nonzero_or_nonfinite']:raise RuntimeError('Unexpected nonzero command in startup')
            for t in ('/cmd_vel_teleop','/cmd_vel_nav','/cmd_mit','/cmd_torque','/motor_enable'):
                if n.get_publishers_info_by_topic(t):raise RuntimeError('New competing owner '+t)
            if not stack_readiness.problems(s):break
        else:raise RuntimeError('Startup not ready within 20 s: '+str(stack_readiness.problems(obs.snapshot())))
        report.update(ready_seen=True,ready_snapshot=s,ready_monotonic_ns=time.monotonic_ns())
        print('READY: lifecycle active and fresh ZERO references observed. No motor enable sent.',flush=True)
        if not a.check_once:
            while child.poll() is None:rclpy.spin_once(n,timeout_sec=.1)
        exit_code=0
    except KeyboardInterrupt:
        report['interrupted']=True;exit_code=0 if report.get('ready_seen') else 1
    except Exception as exc:report['error']=str(exc);print('BLOCKED:',exc,flush=True)
    finally:
        report['last_snapshot']=obs.snapshot()
        if child is not None and child.poll() is None:
            os.killpg(child.pid,signal.SIGINT)
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                report['forced_shutdown']=True;os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        report['launch_returncode']=child.returncode if child else None
        report['check_pass']=exit_code==0 and not report.get('forced_shutdown') and report.get('ready_seen',False)
        if not report['check_pass']:exit_code=1
        if log:log.close()
        (root/(ident+'.result.json')).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        n.destroy_node();rclpy.try_shutdown()
        for sig,handler in old.items():signal.signal(sig,handler)
    return exit_code
if __name__=='__main__':raise SystemExit(main())
