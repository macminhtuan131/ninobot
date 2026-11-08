"""Reference registration never converts labels/file hashes into motion proof."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from nino_pi import body_reference as b


def fixture(tmp_path,nested=False):
    session=tmp_path/'captured_session';raw=session/'raw' if nested else session
    (raw/'bag').mkdir(parents=True);(raw/'manifest.json').write_text('{"status":"captured_not_calibrated"}')
    (session/'session.json').write_text('{}')
    video=tmp_path/'camera.mp4';video.write_bytes(b'fixture bytes, not a validated video')
    return session,raw,video


def test_legacy_and_studio_identity_pin_not_raw_qc(tmp_path):
    session,raw,video=fixture(tmp_path,True)
    identity=b.session_identity(session)
    assert b.session_identity(raw)==identity
    assert identity['raw_directory']==str(raw)
    assert identity['manifest_sha256']==hashlib.sha256((raw/'manifest.json').read_bytes()).hexdigest()
    with pytest.raises(ValueError):b.session_identity(tmp_path)


def test_preserve_raw_and_unknown_quantities_when_registering_operator_labels(tmp_path,monkeypatch):
    session,raw,video=fixture(tmp_path);monkeypatch.setattr(b.shutil,'which',lambda *a:None)
    identity=b.session_identity(session);manifest=(raw/'manifest.json').read_bytes()
    media=b.inspect_media(video)
    assert media['inspection']=='checksum_only_media_not_validated'
    assert media['nominal_fps'] is None and media['frame_pts_available'] is None
    labels=dict(wheel_left_rotation='observed',wheel_right_rotation='not_visible',body_translation='not_observed')
    value=b.make_observation(identity,[media],labels,'operator note',True)
    output=b.save_observation(value,tmp_path/'derived');other=b.save_observation(value,tmp_path/'derived')
    assert output!=other and json.loads(output.read_text())==value
    assert (raw/'manifest.json').read_bytes()==manifest
    assert value['qc']['physical_motion_verdict']=='unknown'
    assert value['qc']['same_session_link_verified'] is None and value['same_session_operator_attestation'] is True
    assert value['qc']['raw_integrity_verified'] is None and value['motion_released'] is False
    assert not value['qc']['eligible_for_td3_replay'] and not value['qc']['eligible_for_slip']
    assert value['reference']['body_speed_m_s'] is None
    with pytest.raises(ValueError,match='ngoài session'):b.save_observation(value,session/'derived')
    link=tmp_path/'alias';link.symlink_to(session,target_is_directory=True)
    with pytest.raises(ValueError,match='ngoài session'):b.save_observation(value,link/'derived')


def test_changed_manifest_unlinked_video_and_invalid_labels_fail_closed(tmp_path,monkeypatch):
    session,raw,video=fixture(tmp_path);identity=b.session_identity(session)
    monkeypatch.setattr(b.shutil,'which',lambda *a:None);media=b.inspect_media(video)
    labels=dict(wheel_left_rotation=None,wheel_right_rotation=None,body_translation=None)
    with pytest.raises(ValueError,match='ít nhất'):b.make_observation(identity,[],labels,'',True)
    with pytest.raises(ValueError,match='Xác nhận'):b.make_observation(identity,[media],labels,'',False)
    with pytest.raises(ValueError,match='Nhãn'):b.make_observation(identity,[media],dict(labels,body_translation='safe'),'',True)
    (raw/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='đã đổi'):b.make_observation(identity,[media],labels,'',True)


def test_media_cancel_and_stream_metadata_never_establish_frame_timing(tmp_path,monkeypatch):
    session,raw,video=fixture(tmp_path)
    with pytest.raises(InterruptedError):b.inspect_media(video,lambda:True)
    monkeypatch.setattr(b.shutil,'which',lambda *a:'/fixture/ffprobe')
    monkeypatch.setattr(b.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=json.dumps(dict(streams=[dict(width=640,height=480,avg_frame_rate='30/1',time_base='1/1000')]))))
    media=b.inspect_media(video)
    assert media['nominal_fps']==30 and media['width_px']==640
    assert media['frame_pts_available'] is None and media['clock_domain'] is None
    assert media['inspection']=='stream_metadata_only_not_frame_timing'
    video.write_bytes(b'')
    with pytest.raises(ValueError,match='rỗng'):b.inspect_media(video)
