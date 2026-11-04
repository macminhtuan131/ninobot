"""Bounded localhost sensor-only fixture: normal close, event marks and EOF cleanup."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import pytest


@pytest.mark.parametrize('mode',['normal','stop','eof'])
def test_observer_lifecycle_and_no_motor_commands(tmp_path,mode):
    cancel=mode!='normal'
    env=dict(os.environ,ROS_DOMAIN_ID='228',ROS_LOCALHOST_ONLY='1',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    for key in ('FASTRTPS_DEFAULT_PROFILES_FILE','FASTDDS_DEFAULT_PROFILES_FILE'):env.pop(key,None)
    env['HOME']=str(tmp_path)
    publisher=r'''
import time
import rclpy
from sensor_msgs.msg import Imu
from rclpy.qos import qos_profile_sensor_data
rclpy.init();n=rclpy.create_node('studio_sensor_fixture');p=n.create_publisher(Imu,'/imu/data',qos_profile_sensor_data)
try:
 end=time.monotonic()+45
 while time.monotonic()<end:
  m=Imu();m.header.stamp=n.get_clock().now().to_msg();m.header.frame_id='imu_link';m.linear_acceleration.z=9.81
  p.publish(m);rclpy.spin_once(n,timeout_sec=.02)
except KeyboardInterrupt:pass
finally:n.destroy_node();rclpy.shutdown()
'''
    observer=r'''
from nino_pi import studio_remote as s
config=dict(schema_version=1,duration_s=5,max_session_mb=32,reserve_disk_mb=16,storage_id='mcap',
 topics=[dict(name='/imu/data',required=True,purpose='localhost synthetic sensor only')])
s.collection_config=lambda *args:config
meta=dict(scenario='stationary',robot_id='fixture',pose_caster_note='unknown',floor_load_note='synthetic',
 operator='test',protocol_id='unknown',body_reference='unknown',firmware_identity='unknown',
 controller_identity='none',conditions_confirmed=True,storage='mcap')
raise SystemExit(s.record(meta,duration=5))
'''
    source=subprocess.Popen([sys.executable,'-c',publisher],env=env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    child=None;stop=threading.Event()
    try:
        child=subprocess.Popen([sys.executable,'-u','-c',observer],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def heartbeat():
            sent=False
            while not stop.wait(.25):
                try:
                    child.stdin.write(json.dumps(dict(command='pulse'))+'\n')
                    if not sent:
                        child.stdin.write(json.dumps(dict(command='annotation',text='synthetic marker'))+'\n');sent=True
                    child.stdin.flush()
                except (OSError,ValueError):break
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        lines=[];cancel_sent=False
        for line in child.stdout:
            lines.append(line)
            value=json.loads(line.split('@@NINO_STUDIO@@',1)[1]) if line.startswith('@@NINO_STUDIO@@') else {}
            if cancel and not cancel_sent and value.get('state')=='RECORDING' and value.get('elapsed_s',0)>=1.5:
                if mode=='stop':child.stdin.write('{"command":"stop-recorder"}\n');child.stdin.flush()
                else:stop.set();thread.join(timeout=2);child.stdin.close()
                cancel_sent=True
        code=child.wait(timeout=45);stderr=child.stderr.read()
        stop.set();thread.join(timeout=2)
        assert code==(1 if cancel else 0),''.join(lines)+stderr
        roots=list((tmp_path/'nino_datasets/real').iterdir());assert len(roots)==1
        root=roots[0]
        lifecycle=json.loads((root/'observer_lifecycle.json').read_text())
        qc=json.loads((root/'qc_report.json').read_text())
        assert lifecycle['motor_commands_sent']==0
        assert qc['verdict']==('FAIL' if cancel else 'WARN')
        assert qc['level']==('Q1' if cancel else 'Q2')
        assert json.loads((root/'annotations.json').read_text())[0]['text']=='synthetic marker'
        assert (root/'raw/sha256.json').is_file()
        from nino_pi.studio_quality import verify_raw
        assert verify_raw(root/'raw')['mismatches']==[]
        assert '"state": "CLOSED"' in ''.join(lines)
    finally:
        stop.set()
        for process in (child,source):
            if process is not None and process.poll() is None:
                if process is child:process.terminate()
                else:os.killpg(process.pid,signal.SIGINT)
                try:process.wait(timeout=30)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
