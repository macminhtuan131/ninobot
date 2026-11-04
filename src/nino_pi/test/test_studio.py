"""Storage/clock/fault/GUI tests. No Pi, firmware, drivers, or motor publishers."""
import ast
import hashlib
import json
import os
from pathlib import Path
import zipfile
import io
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from nino_pi.studio_contract import collection_config, validate_metadata
from nino_pi.studio_quality import inspect_session, verify_raw
from nino_pi.studio_transport import bundle, remote_command
from nino_pi.collect_real_data import inspect_bag


def metadata(scenario='stationary'):
    return dict(scenario=scenario,robot_id='Nino',pose_caster_note='unknown',floor_load_note='same tile',
        operator='fixture',protocol_id='unknown',body_reference='unknown',firmware_identity='unknown',
        controller_identity='unknown',conditions_confirmed=True,storage='mcap')


def test_metadata_scenario_does_not_authorize_motion():
    assert validate_metadata(metadata())
    with pytest.raises(ValueError,match='protocol'):validate_metadata(metadata('straight'))
    value=metadata('straight');value['protocol_id']='previously_reviewed_protocol'
    assert validate_metadata(value)
    config=collection_config('straight')
    assert config['storage_id']=='mcap' and 'storage_preset_profile' not in config
    assert not next(t for t in config['topics'] if t['name']=='/motor_enable')['required']


def test_bundle_deterministic_content_addressed_and_no_actuation_api():
    a,sha,namespace=bundle();b,sha2,namespace2=bundle()
    assert a==b and sha==sha2 and namespace==namespace2
    with zipfile.ZipFile(io.BytesIO(a)) as z:
        assert 'nino_pi/studio_remote.py' in z.namelist()
        for name in ('studio_remote.py','studio_telemetry.py'):
            tree=ast.parse(z.read('nino_pi/'+name))
            assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                and n.func.attr in ('create_publisher','publish','set_parameters')]
    assert 'studio_remote record' in remote_command('record','e30=')
    with pytest.raises(ValueError):remote_command('run-trial','e30=')


def make_session(tmp_path,storage='mcap',source_times=(1_000_000_000,1_020_000_000,1_040_000_000)):
    import rosbag2_py
    from rclpy.serialization import serialize_message
    from sensor_msgs.msg import Imu
    root=tmp_path/('session_'+storage);raw=root/'raw';raw.mkdir(parents=True)
    writer=rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(raw/'bag'),storage_id=storage),rosbag2_py.ConverterOptions('',''))
    writer.create_topic(rosbag2_py.TopicMetadata(id=0,name='/imu/data',type='sensor_msgs/msg/Imu',serialization_format='cdr'))
    for i,stamp in enumerate(source_times):
        msg=Imu();msg.header.stamp.sec=stamp//10**9;msg.header.stamp.nanosec=stamp%10**9
        msg.header.frame_id='imu_link';msg.linear_acceleration.z=9.81
        writer.write('/imu/data',serialize_message(msg),2_000_000_000+i*20_000_000)
    del writer
    config=dict(topics=[dict(name='/imu/data',required=True,purpose='synthetic')],storage_id=storage)
    (raw/'collection_config.json').write_text(json.dumps(config))
    (raw/'manifest.json').write_text(json.dumps(dict(status='captured_not_calibrated',issues=[],reason='duration_reached')))
    hashes={str(p.relative_to(raw)):hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.rglob('*') if p.is_file()}
    (raw/'sha256.json').write_text(json.dumps(hashes))
    return root,config


@pytest.mark.parametrize('storage',['mcap','sqlite3'])
def test_actual_cdr_storage_qc_preserves_unknowns(tmp_path,storage):
    root,config=make_session(tmp_path,storage)
    before=(root/'raw/sha256.json').read_bytes()
    report=inspect_session(root)
    assert report['level']=='Q2' and report['verdict']=='WARN'
    assert report['topics']['/imu/data']['count']==3
    assert report['topics']['/imu/data']['observed_receipt_hz']==50.
    assert report['topics']['/imu/data']['coverage'] is None
    assert not report['feature_ready'] and not report['td3_replay_eligible']
    assert before==(root/'raw/sha256.json').read_bytes()
    if storage=='mcap':assert inspect_bag(root/'raw/bag',config)['errors']==[]


def test_clock_reversal_checksum_and_unclosed_storage_fail(tmp_path):
    root,_=make_session(tmp_path,source_times=(1_000_000_000,1_020_000_000,1_010_000_000))
    report=inspect_session(root)
    assert report['verdict']=='FAIL' and report['topics']['/imu/data']['source_backwards']==1
    (root/'raw/manifest.json').write_text('{}')
    assert 'manifest.json' in verify_raw(root/'raw')['mismatches']
    (root/'raw/bag/metadata.yaml').unlink()
    assert inspect_session(root)['verdict']=='FAIL'


def test_parquet_export_preserves_headers_and_raw_hashes(tmp_path):
    pq=pytest.importorskip('pyarrow.parquet')
    from nino_pi.dataset_exporter import export_session
    root,_=make_session(tmp_path)
    before=verify_raw(root/'raw')
    output=tmp_path/'derived'
    report=export_session(root,output)
    table=pq.read_table(output/'messages.parquet').to_pylist()
    assert report['rows']==3 and report['td3_replay_eligible'] is False
    assert [r['source_header_ns'] for r in table]==[1_000_000_000,1_020_000_000,1_040_000_000]
    assert json.loads(table[0]['fields_json'])['linear_acceleration']['z']==9.81
    assert verify_raw(root/'raw')==before
    with pytest.raises(ValueError):export_session(root,root/'processed')
    with pytest.raises(FileExistsError):export_session(root,output)


def test_local_index_keeps_raw_quality_separate(tmp_path):
    from nino_pi.studio_index import register,sessions
    root,_=make_session(tmp_path)
    meta=dict(session_id='fixture',scenario='stationary',dataset_kind='real_sysid')
    (root/'session.json').write_text(json.dumps(meta))
    path=tmp_path/'index.sqlite3'
    assert sessions(path)==[] and not path.exists()
    register(root,inspect_session(root),path)
    assert sessions(path)[0]['quality']=='WARN' and sessions(path)[0]['level']=='Q2'


def test_studio_default_and_separate_recorder_controls():
    pytest.importorskip('PyQt5')
    from PyQt5 import QtWidgets as Q
    from nino_pi.mode_gui import ModeWindow
    app=Q.QApplication.instance() or Q.QApplication([])
    w=ModeWindow(demo=True)
    try:
        assert w.acquisition_tabs.currentWidget() is w.studio
        assert not w.studio.runner.busy and w.process is None
        assert not w.studio.stop.isEnabled()
        assert 'KHÔNG dừng robot' in w.studio.stop.text()
        w.studio.primary.click();app.processEvents()
        assert not w.studio.installed and not w.studio.ready and w.process is None
        assert 'DEMO' in w.studio.detail.toPlainText()
        assert w.research.parameters.check()
    finally:w.close();app.processEvents()
