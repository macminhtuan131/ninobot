"""Offline parameter inspection/editor. Never starts training or changes a runtime."""
import json
from datetime import datetime, timezone
from pathlib import Path
from PyQt5 import QtWidgets as Q
import yaml


class TD3ParameterPanel(Q.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=Q.QVBoxLayout(self)
        try:
            from nino_rl.td3_config import load_profiles
            self.profiles=load_profiles()
        except (ImportError,OSError,ValueError) as exc:
            self.profiles={};message=Q.QLabel('Chưa có catalog nino_rl: '+str(exc)+'\nStudio thu dữ liệu vẫn dùng được.');message.setWordWrap(True)
            layout.addWidget(message);return
        note=Q.QLabel('TD3 PARAMETER SYSTEM · profile có phiên bản / hash\n'
            'h5 đang dùng; h1/h8 là ablation đề xuất, cần ABI và backend validation mới. '
            'Editor chỉ lưu draft, không đổi config của job, không mở budget hoặc hardware authority. '
            'Adapter SB3 hiện dùng chung LR actor/critic; giá trị khác nhau sẽ bị từ chối.')
        note.setWordWrap(True);layout.addWidget(note)
        self.choose=Q.QComboBox();self.choose.addItems(self.profiles);layout.addWidget(self.choose)
        self.editor=Q.QPlainTextEdit();layout.addWidget(self.editor,1)
        row=Q.QHBoxLayout();self.validate=Q.QPushButton('Kiểm schema + hiện hash');self.validate.clicked.connect(self.check)
        self.save=Q.QPushButton('Lưu profile draft mới');self.save.clicked.connect(self.save_draft)
        self.prepare=Q.QPushButton('Tạo effective config + ABI');self.prepare.clicked.connect(self.prepare_profile)
        row.addWidget(self.validate);row.addWidget(self.save);row.addWidget(self.prepare);layout.addLayout(row)
        self.result=Q.QPlainTextEdit();self.result.setReadOnly(True);self.result.setMaximumHeight(155);layout.addWidget(self.result)
        self.choose.currentTextChanged.connect(self.load);self.load(self.choose.currentText())

    def load(self,name):
        self.editor.setPlainText(yaml.safe_dump(self.profiles[name],sort_keys=False,allow_unicode=True));self.check()

    def check(self):
        from nino_rl.td3_config import validate_profile
        try:
            value=yaml.safe_load(self.editor.toPlainText());report=validate_profile(value)
            self.result.setPlainText(json.dumps(report,ensure_ascii=False,indent=2));return value
        except (ValueError,TypeError,KeyError,yaml.YAMLError) as exc:
            self.result.setPlainText('KHÔNG ĐẠT: '+str(exc));return None

    def save_draft(self):
        value=self.check()
        if value is None:return
        path,_=Q.QFileDialog.getSaveFileName(self,'Lưu draft mới',str(Path.home()/(value['profile_id']+'.yaml')),'YAML (*.yaml)')
        if path:
            try:
                with Path(path).open('x') as stream:yaml.safe_dump(value,stream,sort_keys=False)
                self.result.appendPlainText('Đã lưu draft: '+path+'; không áp vào job đang chạy.')
            except OSError as exc:self.result.appendPlainText(str(exc))

    def prepare_profile(self):
        value=self.check()
        if value is None:return
        if value!=self.profiles[self.choose.currentText()]:
            self.result.appendPlainText('Editor đã thay đổi: lưu draft để review; không gán tên/hash profile catalog cho tham số khác.');return
        parent=Q.QFileDialog.getExistingDirectory(self,'Chọn thư mục cha cho config/ABI draft',str(Path.home()))
        if not parent:return
        from nino_rl.td3_config import prepare_profile
        try:
            out=Path(parent)/('td3_profile_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            self.result.setPlainText(json.dumps(prepare_profile(self.choose.currentText(),out),ensure_ascii=False,indent=2))
        except (OSError,ValueError,KeyError) as exc:self.result.setPlainText(str(exc))
