"""User-invoked, one bounded source-command trial through the existing gate.

Owns /cmd_vel_teleop and /motor_enable for one accepted trial. Never publishes torque or final /cmd_vel. Firmware RC checks remain unchanged.
"""
from datetime import datetime, timezone
import json
import math
import signal
import fcntl
from pathlib import Path
import time


def drive_profile(publish, tick, clock, healthy, event, speed, duration):
    """No nonzero publication after the observed deadline; always request zero."""
    start=clock()
    try:
        while clock()-start<duration:
            healthy()
            if clock()-start>=duration: break
            publish(speed)
            event('forward_publication', elapsed_s=clock()-start, requested_m_s=speed)
            tick()
    finally:
        publish(0.0)
        event('zero_requested',elapsed_s=clock()-start)


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import JointState
    from std_msgs.msg import UInt8, Bool
    from std_srvs.srv import SetBool
    from trial_scene_guard import TrialSceneGuard
    import endpoint_identity
    from rclpy.qos import qos_profile_sensor_data

    root=Path(__file__).resolve().parent
    profile=json.loads((root/'motion_profile.accepted.json').read_text())
    assert profile['status']=='user_authorized_single_verification'
    assert profile['max_forward_m_s']==0.05 and profile['requested_forward_duration_s']==2.0
    import pilot_state
    pilot_state.release(root)
    trial_lock=(root/'trial.lock').open('a')
    fcntl.flock(trial_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    active=json.loads((root/'active_session.json').read_text())
    assert active['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    actual_ticks=Path('/proc')/str(active['collector_pid'])/'stat'
    assert actual_ticks.read_text().split()[21]==active['collector_start_ticks'], 'Collector no longer running'
    output=Path(active['output'])
    if (output/'trial.claim.json').exists(): raise SystemExit('This session already has a trial attempt. No automatic retry.')
    if time.monotonic_ns()-active['created_monotonic_ns']>30*10**9:
        raise SystemExit('Recording window too near its end; do not start a trial in it.')

    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO)
    node=Node('nino_commissioning_trial',enable_rosout=False,start_parameter_services=False)
    scene=TrialSceneGuard(node)
    pub=node.create_publisher(Twist,'/cmd_vel_teleop',10)
    gate=node.create_client(SetBool,'/nino_command_gate/enable')
    seen={}; claimed=False; gate_requested=False; log=None; success=False
    enable_pub=node.create_publisher(Bool,'/motor_enable',10)
    enable_channel_verified=False; require_enable=False; log_error=None
    pins=json.loads((root/'endpoint_pins.json').read_text())
    assert pins['boot_id']==active['boot_id'], 'Pinned hardware identity boot changed'
    def endpoint_snapshot():return endpoint_identity.verify(node,pins,enable_pub.get_subscription_count())
    def status(m): seen['status']=(m.data,time.monotonic())
    def wheel(m): seen['wheel']=(m,time.monotonic())
    subs=[node.create_subscription(Twist,'/cmd_vel',lambda m:seen.update(final=(m,time.monotonic())),10),
          node.create_subscription(UInt8,'/motor_status',status,100),
          node.create_subscription(JointState,'/motor_fb',wheel,qos_profile_sensor_data)]
    def spin(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end: rclpy.spin_once(node,timeout_sec=max(0.0,min(.02,end-time.monotonic())))
    def publish(v):
        msg=Twist();msg.linear.x=v;pub.publish(msg)
    def event(kind,**extra):
        row={'kind':kind,'monotonic_ns':time.monotonic_ns(),'wall_time_ns':time.time_ns(),**extra}
        nonlocal log_error
        if log:
            try:log.write(json.dumps(row)+'\n');log.flush()
            except OSError as exc:log_error=str(exc)
    def gate_enable(enabled):
        if not gate.service_is_ready(): raise RuntimeError('Gate service unavailable')
        req=SetBool.Request();req.data=enabled
        f=gate.call_async(req)
        end=time.monotonic()+2
        while not f.done() and time.monotonic()<end: rclpy.spin_once(node,timeout_sec=.02)
        if not f.done() or f.result() is None or not f.result().success:
            raise RuntimeError('Gate did not acknowledge '+str(enabled))
        event('gate_ack',enabled=enabled,response=f.result().message)
    def healthy():
        if log_error:raise RuntimeError('Trial event log failed: '+log_error)
        scene.require_clear()
        if not actual_ticks.exists() or actual_ticks.read_text().split()[21]!=active['collector_start_ticks']:
            raise RuntimeError('Recorder supervisor stopped')
        now=time.monotonic()
        if 'status' not in seen or now-seen['status'][1]>.6: raise RuntimeError('Stale motor status')
        st=seen['status'][0]
        if (st&3)!=3 or st&12 or st&64: raise RuntimeError('Feedback fault or non-velocity status: '+str(st))
        if enable_channel_verified:
            endpoint_state=endpoint_snapshot()
            if endpoint_state['errors']:raise RuntimeError('Endpoint identity changed: '+str(endpoint_state))
        if require_enable and not st&16: raise RuntimeError('Firmware enable ACK lost: status='+str(st))
        if 'wheel' not in seen or now-seen['wheel'][1]>.2: raise RuntimeError('Stale wheel feedback')
        m=seen['wheel'][0]
        if len(m.name)!=2 or len(m.velocity)!=2 or not all(math.isfinite(v) for v in m.velocity):
            raise RuntimeError('Invalid wheel payload')
        final=seen.get('final')
        if final is None or now-final[1]>.2:raise RuntimeError('Missing/stale final command trace')
        if not all(math.isfinite(getattr(v,k)) for v in (final[0].linear,final[0].angular) for k in ('x','y','z')):
            raise RuntimeError('Non-finite final command')
        if not (root/'active_session.json').exists(): raise RuntimeError('Recorder session ended')
        for t,expected in (('/cmd_vel',['collision_monitor']),('/cmd_vel_teleop',['nino_commissioning_trial']),
                           ('/cmd_vel_selected',['nino_command_gate']),('/cmd_vel_smoothed',['velocity_smoother']),
                           ('/collision_monitor_state',['collision_monitor']),('/cmd_vel_nav',[]),('/cmd_mit',[]),('/cmd_torque',[]),('/motor_enable',['nino_commissioning_trial'] if enable_pub else [])):
            actual=sorted(e.node_name for e in node.get_publishers_info_by_topic(t))
            if actual!=expected: raise RuntimeError('Unexpected command owner on '+t+': '+str(actual))
    def request_enable(value):
        if not enable_channel_verified:raise RuntimeError('Enable endpoint identity not verified')
        msg=Bool();msg.data=value;enable_pub.publish(msg)
        event('firmware_enable_request',enabled=value)
    old_handlers={}
    def interrupted(signum,frame):raise KeyboardInterrupt
    for sig in (signal.SIGINT,signal.SIGTERM):
        old_handlers[sig]=signal.signal(sig,interrupted)
    try:
        print('Waiting for recorder, gate and telemetry; no forward command yet.',flush=True)
        deadline=time.monotonic()+10
        ready=False
        last_readiness_error='Recorder/gate/feedback not ready'
        while time.monotonic()<deadline:
            spin(.1)
            recorder=[e.node_name for e in node.get_subscriptions_info_by_topic('/cmd_vel_teleop')]
            if gate.service_is_ready() and 'nino_real_data_recorder' in recorder and 'wheel' in seen and 'status' in seen:
                try: healthy()
                except RuntimeError as exc:
                    last_readiness_error=str(exc)
                    continue
                identity=endpoint_snapshot()
                if identity['errors']:
                    last_readiness_error='Endpoint readiness: '+str(identity)
                    continue
                ready=True;enable_channel_verified=True;break
        if not ready: raise RuntimeError(last_readiness_error)
        healthy()
        if seen['final'][0].linear.x!=0. or seen['final'][0].angular.z!=0.:
            raise RuntimeError('Final reference must be zero before enabling firmware')
        with (output/'trial.claim.json').open('x') as claim:
            json.dump({'session_id':active['session_id'],'started_utc':datetime.now(timezone.utc).isoformat(),
                       'profile':profile,'scope':'One user-invoked commissioning attempt; no automatic retry'},claim,indent=2)
        pilot_state.claim_motion(root,active)
        claimed=True
        log=(output/'trial_events.jsonl').open('x')
        event('trial_start',status_value=seen['status'][0],endpoint_identity=identity)
        healthy()
        # Establish a known disabled state. A pre-existing enable bit is not
        # an acknowledgement of this trial's enable, nor a motor-mode readback.
        gate_enable(False)
        publish(0.0)
        disabled_requested_at=time.monotonic()
        request_enable(False)
        deadline=time.monotonic()+1.5
        while time.monotonic()<deadline:
            publish(0.0);spin(.05);healthy()
            if seen['status'][1]>disabled_requested_at and not seen['status'][0]&16:break
        else:raise RuntimeError('No fresh firmware disable ACK before baseline; no forward command sent')
        event('firmware_disabled_before_baseline_ack',status=seen['status'][0],
              scope='Fresh firmware variable transition only, not actuator mode/power readback')
        event('zero_baseline_start',pilot_slot=active.get('pilot_slot'))
        baseline_deadline=time.monotonic()+2.0
        while time.monotonic()<baseline_deadline:
            healthy();publish(0.0);spin(.05)
            final=seen['final'][0]
            if final.linear.x!=0. or final.angular.z!=0.:raise RuntimeError('Nonzero final during baseline')
        healthy()
        if seen['status'][0]&16:
            raise RuntimeError('Firmware re-enabled during zero baseline; no forward command sent')
        event('scene_clear_before_enable',scene=scene.snapshot())
        requested_at=time.monotonic();request_enable(True)
        deadline=time.monotonic()+1.5
        while time.monotonic()<deadline:
            spin(.05);healthy()
            if seen['status'][1]>requested_at and seen['status'][0]&16:break
        else:raise RuntimeError('No firmware enable ACK; no forward command sent')
        require_enable=True
        event('firmware_enable_ack',status=seen['status'][0],scope='Fresh disabled-to-enabled firmware variable transition; actuator mode/power and effective RC permission remain unverified')
        gate_requested=True
        gate_enable(True)
        healthy()
        event('scene_clear_before_forward',scene=scene.snapshot())
        print('FORWARD reference 0.05 m/s for target 2 s, then zero.',flush=True)
        drive_profile(publish,lambda:spin(.05),time.monotonic,healthy,event,
                      profile['max_forward_m_s'],profile['requested_forward_duration_s'])
        zero_at=time.monotonic()
        gate_enable(False);gate_requested=False
        deadline=time.monotonic()+1.5
        while time.monotonic()<deadline:
            publish(0.0);spin(.05);healthy()
            item=seen.get('final')
            if item and item[1]>=zero_at and item[0].linear.x==0. and item[0].angular.z==0.:break
        else:raise RuntimeError('Final zero reference not observed after ramp; disabling')
        event('final_zero_observed',scope='ROS final reference, not measured body stop')
        request_enable(False);require_enable=False
        deadline=time.monotonic()+1.5
        while time.monotonic()<deadline:
            spin(.05)
            if seen['status'][1]>=zero_at and not seen['status'][0]&16:break
        else:raise RuntimeError('No firmware disable ACK')
        event('firmware_disable_ack',status=seen['status'][0])
        print('ZERO/disable requested; observing for 3 s. Recorder continues.',flush=True)
        observation_end=time.monotonic()+profile['post_zero_observation_s']
        while time.monotonic()<observation_end:
            spin(.05);healthy()
        event('trial_end',status_value=seen.get('status',(None,None))[0],
              last_reported_wheel_velocity=list(seen['wheel'][0].velocity))
        success=True
    except BaseException as exc:
        event('trial_error',error=str(exc),error_type=type(exc).__name__,scene=scene.snapshot())
        if not claimed and output.is_dir():
            failure=output/('readiness_failed_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
            failure.write_text(json.dumps({'error':str(exc),'error_type':type(exc).__name__,
                'status_value':seen.get('status',(None,None))[0],
                'forward_sequence_started':False,'pi_gate_enable_requested':gate_requested,
                'checked_utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
        raise
    finally:
        if rclpy.ok():
            publish(0.0)
            if gate_requested:
                try: gate_enable(False)
                except Exception as exc: event('gate_disable_error',error=str(exc))
            if enable_pub and enable_channel_verified:
                for _ in range(3):request_enable(False);spin(.05)
            spin(.2)
        if claimed:
            (output/'trial_result.json').write_text(json.dumps({'source_sequence_completed':success and log_error is None,
                'physical_motion_verified':False,
                'physical_motion_status':'requires_operator_and_independent_reference',
                'event_log_error':log_error,
                'scope':'Raw review still required: not physical stop/body/slip proof.',
                'finished_utc':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
        if log: log.close()
        node.destroy_node();rclpy.try_shutdown()
        for sig,handler in old_handlers.items():signal.signal(sig,handler)
    if success: print('Trial source sequence complete. Keep recorder terminal open until it finishes.',flush=True)


if __name__=='__main__': main()
