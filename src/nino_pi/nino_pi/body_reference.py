"""Register local video/operator evidence without changing raw or motion authority."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid

VOCABULARY=(None,'observed','not_observed','ambiguous','not_visible')


def digest(path,cancelled=lambda:False):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            if cancelled():raise InterruptedError('Đã hủy; chưa lưu hồ sơ.')
            h.update(block)
    return h.hexdigest()


def session_identity(directory):
    root=Path(directory).expanduser().resolve()
    if root.name=='raw' and (root.parent/'session.json').is_file():root=root.parent
    raw=root/'raw' if (root/'raw/manifest.json').is_file() else root
    if not (raw/'manifest.json').is_file() or not (raw/'bag').is_dir():
        raise ValueError('Chọn session đã có manifest.json và bag/ (hoặc raw/manifest.json + raw/bag/).')
    manifest=json.loads((raw/'manifest.json').read_text())
    if not isinstance(manifest,dict):raise ValueError('Manifest không phải JSON object.')
    return dict(session_id=root.name,session_directory=str(root),raw_directory=str(raw),
        manifest_path=str(raw/'manifest.json'),manifest_sha256=digest(raw/'manifest.json'),
        recorded_manifest_status=manifest.get('status'),
        scope='Identity pin only; raw integrity/closure/body motion are not revalidated here.')


def inspect_media(path,cancelled=lambda:False):
    p=Path(path).expanduser().resolve()
    if not p.is_file() or p.stat().st_size==0:raise ValueError('Video không tồn tại hoặc rỗng: '+str(p))
    if p.suffix.lower() not in {'.mp4','.mov','.mkv','.avi','.webm','.m4v'}:
        raise ValueError('Chọn file video gốc (.mp4/.mov/.mkv/.avi/.webm/.m4v).')
    before=p.stat();checksum=digest(p,cancelled)
    result=dict(path=str(p),sha256=checksum,size_bytes=before.st_size,
        inspection='checksum_only_media_not_validated',width_px=None,height_px=None,nominal_fps=None,
        frame_pts_available=None,clock_domain=None,continuous=None,
        wheel_left_visible=None,wheel_right_visible=None,body_marker_visible=None,fixed_landmark_visible=None)
    ffprobe=shutil.which('ffprobe')
    if ffprobe:
        if cancelled():raise InterruptedError('Đã hủy; chưa lưu hồ sơ.')
        try:
            probe=subprocess.run([ffprobe,'-v','error','-select_streams','v:0','-show_entries',
                'stream=width,height,avg_frame_rate,time_base','-of','json',str(p)],
                capture_output=True,text=True,timeout=10,check=True)
            streams=json.loads(probe.stdout).get('streams',[])
            if not streams:raise ValueError('File không có video stream được ffprobe nhận dạng.')
            stream=streams[0];rate=stream.get('avg_frame_rate','0/0').split('/')
            fps=float(rate[0])/float(rate[1]) if len(rate)==2 and float(rate[1]) else None
            if fps is not None and (not math.isfinite(fps) or fps<=0):fps=None
            result.update(inspection='stream_metadata_only_not_frame_timing',width_px=stream.get('width'),
                height_px=stream.get('height'),nominal_fps=fps,stream_time_base=stream.get('time_base'))
        except (subprocess.SubprocessError,ValueError,KeyError,IndexError) as exc:
            raise ValueError('Không đọc được metadata video: '+str(exc)) from exc
    after=p.stat()
    if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
        raise ValueError('Video thay đổi khi tính hash; chờ file đóng/copy xong.')
    if cancelled():raise InterruptedError('Đã hủy; chưa lưu hồ sơ.')
    return result


def make_observation(identity,videos,labels,note,same_session_attested):
    """Operator labels are preserved, never promoted to calibrated QC."""
    from .studio_contract import config_root
    value=json.loads((config_root()/'body_reference_observation.template.json').read_text())
    if not videos:raise ValueError('Chọn ít nhất một video trước khi lưu liên kết session.')
    if same_session_attested is not True:raise ValueError('Xác nhận video đúng session; đây vẫn là nhãn operator, chưa là kiểm độc lập.')
    if digest(identity['manifest_path'])!=identity['manifest_sha256']:
        raise ValueError('Manifest session đã đổi; chọn lại và review trước khi lưu.')
    required={'wheel_left_rotation','wheel_right_rotation','body_translation'}
    if set(labels)!=required or any(v not in VOCABULARY for v in labels.values()):
        raise ValueError('Nhãn quan sát không hợp lệ.')
    if not isinstance(note,str) or len(note)>4000:raise ValueError('Ghi chú quá dài hoặc sai định dạng.')
    value.update(session_id=identity['session_id'],bag_manifest_sha256=identity['manifest_sha256'],
        session_identity=deepcopy(identity),videos=deepcopy(videos),
        created_utc=datetime.now(timezone.utc).isoformat(),same_session_operator_attestation=True,
        evidence_origin='Operator-entered labels and local file identity; no independent motion review')
    value['observations'].update(labels,observer_note=note.strip() or None)
    value['reference']['level']='candidate_not_reviewed'
    value['qc']['reasons']=['File association and operator labels only; no automatic Q3/Q4 or motion success.',
        'Checksum is not video authenticity, frame timing, scale or synchronization validation.',
        'not_observed is limited by visibility/resolution; it is not physical zero.',
        'No independent body-speed/slip/latency reference; no TD3 replay or motion release.']
    return value


def save_observation(value,destination):
    """Derived-only output, exclusive file creation; never stores inside session/raw."""
    folder=Path(destination).expanduser().resolve()
    session=Path(value['session_identity']['session_directory']).resolve()
    if folder==session or session in folder.parents:
        raise ValueError('Chọn thư mục derived ngoài session/raw; không ghi thêm vào raw đã đóng.')
    encoded=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
    folder.mkdir(parents=True,exist_ok=True)
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:8]
    path=folder/('body_reference_'+name+'.json')
    created=False
    try:
        with path.open('x') as stream:
            created=True;stream.write(encoded)
    except BaseException:
        if created:path.unlink(missing_ok=True)
        raise
    return path
