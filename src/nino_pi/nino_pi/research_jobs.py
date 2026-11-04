"""Local fixed software jobs and verified progress; no SSH or robot commands."""
import json
import hashlib
import os
from pathlib import Path
import signal
from PyQt5 import QtCore as C

JOBS={
    'validate':('1 · Kiểm History / giới hạn / environment',()),
    'train-td3':('2 · TD3 fixture giảm bậc · 128 bước',('validate',)),
    'audit-td3':('2b · Kiểm replay / checkpoint / actor TD3',('train-td3',)),
    'train-ppo':('3 · PPO · đối chứng 128 bước',('validate',)),
    'compare':('4 · So B0 / B1 / Governor / TD3 / PPO',('train-td3','train-ppo')),
    'ros-fixture':('5 · Kiểm ROS → actor → trace',('train-td3',)),
    'gazebo-fixture':('6 · Kiểm backend Gazebo sàn phẳng',('validate',)),
    'factory-td3':('FACTORY · TD3 + Nino + wheel PI · 128 bước',()),
    'sim-baselines':('SIM 1 · B0 sàn sạch / gờ 6 mm / mixed 22 mm',()),
    'sim-train':('SIM 2 · TD3 h5 · pilot 256 bước',('sim-baselines',)),
    'sim-evaluate':('SIM 3 · B0 / B1 yaw / TD3 h5',('sim-train',)),
    'sysid':('7 · Phân tích SysID đã đăng ký',()),
}


def repository():
    root=Path(os.environ.get('NINO_REPO',Path(__file__).resolve().parents[3]))
    if not (root/'src/nino_rl/scripts/residual_workflow.sh').is_file():raise ValueError('Cần source workspace Nino; đặt NINO_REPO nếu dùng bản cài.')
    return root


def workflow_state(root):
    from nino_rl.residual_workflow import latest
    result={}
    for action in JOBS:
        try:
            # GUI uses system Python; workers use the research venv. Display
            # verified historical results; each worker rechecks its own runtime.
            path=latest(root,action,check_runtime=False)
            if action in ('sim-baselines','sim-train','sim-evaluate'):
                from nino_rl.residual_sim_pilot import fingerprint
                manifest=json.loads((path/'manifest.json').read_text())
                if manifest.get('pilot_fingerprint')!=fingerprint():raise ValueError('Sim pilot source/protocol changed; retained artifact is historical')
            if action=='factory-td3':
                from nino_rl.residual_factory_workflow import factory_fingerprint
                manifest=json.loads((path/'manifest.json').read_text())
                if manifest.get('factory_fingerprint')!=factory_fingerprint():
                    raise ValueError('Factory map/robot/backend changed; retained smoke is historical')
            if action=='audit-td3':
                from nino_rl import residual_td3_audit
                manifest=json.loads((path/'manifest.json').read_text())
                if manifest.get('auditor_sha256')!=hashlib.sha256(Path(residual_td3_audit.__file__).read_bytes()).hexdigest():
                    raise ValueError('TD3 audit implementation changed; audit again')
                current=latest(root,'train-td3',check_runtime=False)
                if manifest.get('input_artifact')!=str(current) or manifest.get('input_manifest_sha256')!=hashlib.sha256((current/'manifest.json').read_bytes()).hexdigest():
                    raise ValueError('TD3 checkpoint changed; audit the current one')
            label='PILOT MÔ TẢ · CHƯA PROMOTE' if action in ('sim-baselines','sim-train','sim-evaluate') else 'SMOKE ĐẠT · TASK CHƯA XÁC NHẬN' if action=='factory-td3' else 'ĐẠT PHẦN MỀM' if action!='sysid' else 'CANDIDATE · CẦN REVIEW'
            result[action]=dict(state='verified',path=str(path),label=label)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            result[action]=dict(state='pending',path=None,label='CHƯA ĐẠT / ARTIFACT CŨ',error=str(exc))
    return result


class ResearchRunner(C.QObject):
    update=C.pyqtSignal(dict)
    closed=C.pyqtSignal()
    def __init__(self,root,parent=None):
        super().__init__(parent);self.root=Path(root);self.process=None;self.buffer=b'';self.action=None;self.last={};self.cancelling=False
    @property
    def busy(self):return self.process is not None
    def start(self,action):
        if self.busy or action not in JOBS:return False
        state=workflow_state(self.root)
        for dep in JOBS[action][1]:
            if state[dep]['state']!='verified':raise ValueError('Chạy và đạt '+dep+' trước')
        if action=='sysid' and not (self.root/'registration.json').is_file():raise ValueError('Đăng ký CSV + metadata trước')
        command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_workflow.sh'),action,'--output',str(self.root)]
        if action=='audit-td3':command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_td3_audit.sh'),'--workflow','--output',str(self.root)]
        if action=='factory-td3':command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_factory_smoke.sh'),'--output',str(self.root)]
        if action in ('sim-baselines','sim-train','sim-evaluate'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_sim_pilot.sh'),action,'--output',str(self.root)]
        self.action=action;self.last={};self.cancelling=False;self.buffer=b''
        p=C.QProcess(self);self.process=p;p.setProcessChannelMode(C.QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self.read);p.finished.connect(self.finished);p.errorOccurred.connect(self.error)
        p.start(command[0],command[1:]);self.update.emit(dict(state='running',action=action,message='Đang khởi động job local; không nối Pi'))
        return True
    def read(self):
        if not self.process:return
        self.buffer+=bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1);line=line.decode('utf8','replace')
            try:
                if line.startswith('@@NINO_RESEARCH@@'):
                    row=json.loads(line[len('@@NINO_RESEARCH@@'):]);self.last=row;self.update.emit(dict(row,state='progress'));continue
            except ValueError:pass
            self.update.emit(dict(state='log',message=line))
    def finished(self,code=1,status=None):
        if self.process is None:return
        self.read();p=self.process;self.process=None
        if self.buffer:self.update.emit(dict(state='log',message=self.buffer.decode('utf8','replace')));self.buffer=b''
        self.update.emit(dict(self.last,state='closed',action=self.action,returncode=code,cancelled=self.cancelling))
        p.deleteLater();self.closed.emit()
    def error(self,error):
        self.update.emit(dict(state='log',message=self.process.errorString() if self.process else 'process unavailable'))
        if self.process and self.process.state()==C.QProcess.NotRunning:self.finished()
    def cancel(self):
        if self.process and self.process.processId() and not self.cancelling:
            self.cancelling=True
            try:os.kill(int(self.process.processId()),signal.SIGINT)
            except ProcessLookupError:pass
            self.update.emit(dict(state='log',message='Đã yêu cầu hủy; đợi ghi manifest và đóng process con. Không tự chạy lại.'))
