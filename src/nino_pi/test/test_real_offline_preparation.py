"""Regression cases from the real review; no robot, SSH or actuator commands."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import io
import json
import shlex
import sqlite3
import subprocess
import zipfile
import pytest
import yaml

from nino_pi.bag_io import records, metadata_topic_mismatches
from nino_pi.collect_real_data import inspect_bag
from nino_pi.studio_contract import collection_config, validate_metadata
from nino_pi.studio_transport import bundle, remote_command


def bag(tmp_path):
    root=tmp_path/'bag';root.mkdir()
    with sqlite3.connect(root/'data.db3') as db:
        db.execute('CREATE TABLE topics(id INTEGER,name TEXT,type TEXT)')
        db.execute('CREATE TABLE messages(id INTEGER,topic_id INTEGER,timestamp INTEGER,data BLOB)')
        db.executemany('INSERT INTO topics VALUES(?,?,?)',[(1,'/imu/data','sensor_msgs/msg/Imu'),(2,'/motor_fb','sensor_msgs/msg/JointState')])
        db.executemany('INSERT INTO messages VALUES(?,?,?,?)',[(1,1,10,b'a'),(2,1,20,b'b'),(3,2,20,b'c')])
    meta=dict(storage_identifier='sqlite3',relative_file_paths=['data.db3'],message_count=3,
        topics_with_message_count=[dict(topic_metadata=dict(name='/imu/data'),message_count=2),
                                   dict(topic_metadata=dict(name='/motor_fb'),message_count=1)])
    (root/'metadata.yaml').write_text(yaml.safe_dump(dict(rosbag2_bagfile_information=meta)))
    return root,meta


def test_reader_leaves_finalized_raw_unchanged_and_rejects_pending_writes(tmp_path):
    root,_=bag(tmp_path)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    assert len(list(records(root)))==3
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    pending=root/'data.db3-wal';pending.write_bytes(b'pending transaction data')
    with pytest.raises(ValueError,match='Unfinalized'):list(records(root))
    assert pending.read_bytes()==b'pending transaction data'
    report=inspect_bag(root,dict(topics=[]))
    assert any('Unfinalized' in s for s in report['errors'])


def test_same_total_with_wrong_topic_counts_is_not_a_pass(tmp_path):
    root,meta=bag(tmp_path)
    meta['topics_with_message_count'][0]['message_count']=1
    meta['topics_with_message_count'][1]['message_count']=2
    (root/'metadata.yaml').write_text(yaml.safe_dump(dict(rosbag2_bagfile_information=meta)))
    report=inspect_bag(root,dict(topics=[]))
    assert sum(v['count'] for v in report['topics'].values())==3
    assert any(s.startswith('metadata_topic_count_mismatch:') for s in report['errors'])
    assert metadata_topic_mismatches({}, {'/imu':3}) is None


def test_velocity_profile_separates_mode_changing_requests_and_has_no_motion_release():
    config=collection_config('velocity_sysid','sqlite3')
    assert config['backend_contract']=='firmware_velocity_reference'
    assert config['motion_profile_proposal']['motion_released'] is False
    topics={t['name']:t for t in config['topics']}
    assert topics['/cmd_vel']['required']
    assert all(not topics[n]['required'] for n in ('/cmd_torque','/cmd_mit','/motor_enable'))
    assert '/scan' in config['preflight_required_topics']
    meta=dict(scenario='velocity_sysid',storage='sqlite3',conditions_confirmed=True,
       robot_id='Nino',operator='fixture',protocol_id='reviewed_fixture',controller_identity='pi_sac',
       pose_caster_note='unknown',floor_load_note='unknown',body_reference='unknown',firmware_identity='unknown')
    with pytest.raises(ValueError,match='separate dataset'):validate_metadata(meta)
    meta['controller_identity']='firmware_velocity_reference'
    assert validate_metadata(meta)==meta
    payload,_,_=bundle()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        packaged=json.loads(z.read('config/real_collection_velocity_sysid.json'))
        assert packaged['backend_contract']==config['backend_contract']


def test_observer_environment_prefers_current_layout_and_fails_if_none(tmp_path):
    current=tmp_path/'nino-real-test/scripts';current.mkdir(parents=True)
    (current/'env.sh').write_text('nino_env_test_marker=current\n')
    legacy=tmp_path/'pi5-stm32-slam-main/scripts';legacy.mkdir(parents=True)
    (legacy/'env.sh').write_text('nino_env_test_marker=legacy\n')
    command=shlex.split(remote_command('discover','e30='))
    script=command[2].replace('"$HOME/', '"'+str(tmp_path)+'/')
    # Replace only the observer exec for this test. No ROS node or SSH is started.
    script=script[:script.index('exec /usr/bin/python3')]+ 'printf "%s" "$nino_env_test_marker"\n'
    result=subprocess.run(['bash','-c',script],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout=='current'
    (current/'env.sh').unlink();(legacy/'env.sh').unlink()
    result=subprocess.run(['bash','-c',script],capture_output=True,text=True)
    assert result.returncode!=0 and 'environment not found' in result.stderr


def test_even_zero_torque_conflicts_with_declared_velocity_dataset(tmp_path,monkeypatch):
    from nino_pi import studio_quality as quality
    root=tmp_path/'session';raw=root/'raw';raw.mkdir(parents=True)
    (raw/'manifest.json').write_text(json.dumps(dict(status='captured_not_calibrated',issues=[])))
    (raw/'collection_config.json').write_text(json.dumps(dict(backend_contract='firmware_velocity_reference',topics=[])))
    monkeypatch.setattr(quality,'verify_raw',lambda _:dict(checked=2,mismatches=[]))
    monkeypatch.setattr(quality,'metadata',lambda _:dict(message_count=1,storage_identifier='sqlite3',
        topics_with_message_count=[dict(topic_metadata=dict(name='/cmd_torque'),message_count=1)]))
    monkeypatch.setattr(quality,'decoded',lambda _:iter([('/cmd_torque','std_msgs/msg/Float64MultiArray',10,SimpleNamespace(data=[0.,0.]))]))
    report=quality.inspect_session(root)
    check=next(c for c in report['checks'] if c['name']=='velocity_backend_mode_conflicts')
    assert check['verdict']=='FAIL' and check['detail']=={'/cmd_torque':1}
    assert report['verdict']=='FAIL' and not report['td3_replay_eligible']


def test_gui_export_prefers_separate_interpreter_without_running_it(tmp_path,monkeypatch):
    from nino_pi.studio_runner import command
    monkeypatch.setenv('NINO_REPO',str(tmp_path))
    for directory in ('.venv/bin', '.venv-studio-export/bin'):
        target=tmp_path/directory/'python';target.parent.mkdir(parents=True)
        target.write_text('# fixture, not executed\n');target.chmod(0o700)
    argv=command('export',dict(host='d@192.168.0.103',key='/unused/key'))
    assert argv[0]==str(tmp_path/'.venv-studio-export/bin/python')
    assert 'ssh' not in argv
