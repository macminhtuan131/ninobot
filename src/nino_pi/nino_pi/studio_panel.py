"""Single acquisition screen, with explicit next action and recorder-only controls."""
from datetime import datetime, timezone
import json
from pathlib import Path
from PyQt5 import QtCore as C, QtGui as G, QtWidgets as Q
from .studio_contract import SCENARIOS, validate_metadata
from .studio_runner import StudioRunner


class StudioPanel(Q.QWidget):
    def __init__(self,connection,parent=None,demo=False,external_busy=None):
        super().__init__(parent);self.connection=connection;self.external_busy=external_busy or (lambda:False)
        self.runner=StudioRunner(self,demo=demo);self.runner.job_event.connect(self.handle)
        self.installed=False;self.checked=False;self.ready=False;self.session=None;self.local=None;self.closing=False
        self.connection_key=None;self.error=None
        layout=Q.QVBoxLayout(self)
        title=Q.QLabel('NINO REAL DATA STUDIO · GHI DỮ LIỆU, KHÔNG ĐIỀU KHIỂN MOTOR')
        title.setWordWrap(True);title.setStyleSheet('font-size:18px;font-weight:700');layout.addWidget(title)
        note=Q.QLabel('Kết nối → chọn kịch bản → kiểm tra → ghi 60 s → QC → tải / export.\n'
            'Các nút ở đây không đổi RC, ARM, enable, phát trajectory hoặc cmd_vel. Điều khiển xe theo protocol đã review bằng nguồn riêng.')
        note.setWordWrap(True);layout.addWidget(note)
        scroll=Q.QScrollArea();self.scroll=scroll;scroll.setWidgetResizable(True);page=Q.QWidget();scroll.setWidget(page)
        content=Q.QVBoxLayout(page);layout.addWidget(scroll,1)
        form=Q.QFormLayout();self.scenario=Q.QComboBox()
        for key,(name,kind,motion) in SCENARIOS.items():self.scenario.addItem(name,key)
        self.storage=Q.QComboBox();self.storage.addItems(['mcap','sqlite3'])
        form.addRow('Kịch bản quan sát',self.scenario);form.addRow('Raw storage (kiểm plugin trước ghi)',self.storage)
        self.fields={}
        for key,name,default in [('robot_id','Robot','Nino-01'),('operator','Người vận hành',''),
            ('protocol_id','Protocol đã review (motion bắt buộc)','unknown'),
            ('controller_identity','Nguồn/controller đang chạy','unknown'),
            ('firmware_identity','Binary/firmware đã xác minh','unknown'),
            ('pose_caster_note','Pose / caster ban đầu','unknown'),('floor_load_note','Sàn / tải / pin','unknown'),
            ('body_reference','Reference thân xe / video / sync','unknown')]:
            field=Q.QLineEdit(default);self.fields[key]=field;form.addRow(name,field)
        content.addLayout(form)
        self.reference_button=Q.QPushButton('Reference bánh/thân · gắn video với session đã thu')
        self.reference_button.clicked.connect(self.open_body_reference);content.addWidget(self.reference_button)
        self.confirm=Q.QCheckBox('Tôi xác nhận metadata và điều kiện quan sát; Studio chỉ ghi. Không reboot cho tới khi bag đóng.')
        content.addWidget(self.confirm)
        self.telemetry=Q.QTableWidget(0,6);self.telemetry.setHorizontalHeaderLabels(['Topic','Mẫu observer','Hz nhận','Tuổi nhận (s)','Bắt buộc','Pub'])
        self.telemetry.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.telemetry.horizontalHeader().setSectionResizeMode(0,Q.QHeaderView.Stretch)
        for i in range(1,6):self.telemetry.horizontalHeader().setSectionResizeMode(i,Q.QHeaderView.ResizeToContents)
        self.telemetry.setMinimumHeight(155);content.addWidget(self.telemetry)
        self.annotation=Q.QLineEdit();self.annotation.setPlaceholderText('Ví dụ: bắt đầu quay video / operator thấy xe không tiến / STOP xuất hiện')
        row=Q.QHBoxLayout();row.addWidget(self.annotation,1)
        self.mark=Q.QPushButton('Đánh dấu sự kiện');self.mark.clicked.connect(self.annotate);row.addWidget(self.mark);content.addLayout(row)
        self.detail=Q.QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMinimumHeight(120)
        self.detail.document().setMaximumBlockCount(1000);content.addWidget(self.detail)
        self.progress=Q.QProgressBar();layout.addWidget(self.progress)
        self.next=Q.QLabel();self.next.setWordWrap(True);self.next.setStyleSheet('color:#72ded0;font-weight:700');layout.addWidget(self.next)
        row=Q.QHBoxLayout();self.primary=Q.QPushButton();self.primary.setObjectName('primary');self.primary.clicked.connect(self.advance)
        self.stop=Q.QPushButton('Dừng ghi · KHÔNG dừng robot');self.stop.clicked.connect(self.runner.stop_recording)
        row.addWidget(self.primary,1);row.addWidget(self.stop);layout.addLayout(row)
        row=Q.QHBoxLayout()
        self.check=Q.QPushButton('Kiểm sensor');self.check.clicked.connect(lambda:self.start('discover'))
        self.fetch=Q.QPushButton('Tải phiên');self.fetch.clicked.connect(self.fetch_data)
        self.export=Q.QPushButton('Export Parquet');self.export.clicked.connect(self.export_data)
        self.export.setToolTip('Tạo bản derived riêng; không chỉnh sửa raw hoặc tạo replay TD3.')
        self.open=Q.QPushButton('Mở thư mục');self.open.clicked.connect(self.open_data)
        self.history=Q.QPushButton('Lịch sử');self.history.clicked.connect(self.open_history)
        for b in (self.check,self.fetch,self.export,self.open,self.history):row.addWidget(b)
        layout.addLayout(row)
        self.scenario.currentIndexChanged.connect(self.invalidate);self.storage.currentIndexChanged.connect(self.invalidate)
        self.refresh()

    def metadata(self):
        return dict({key:field.text().strip() for key,field in self.fields.items()},
            scenario=self.scenario.currentData(),storage=self.storage.currentText(),conditions_confirmed=self.confirm.isChecked())

    def open_body_reference(self):
        from .body_reference_panel import BodyReferenceDialog
        dialog=BodyReferenceDialog(self,session=self.local)
        dialog.exec_()

    def invalidate(self,*args):
        self.checked=False;self.ready=False;self.refresh()

    def start(self,action):
        if self.external_busy():
            self.detail.appendPlainText('Đóng job commissioning/authority/research đang chạy trước Studio.');return
        try:
            self.error=None
            meta=self.metadata()
            if action=='record':
                if not self.installed or not self.ready:raise ValueError('Check this robot/storage before recording')
                validate_metadata(meta);self.session=None;self.local=None;self.recording_visible=False
            self.runner.start(action,self.connection(),meta)
        except (ValueError,OSError,KeyError) as exc:
            self.error=str(exc);self.detail.appendPlainText(self.error);self.scroll.ensureWidgetVisible(self.detail,0,0)
        self.refresh()

    def advance(self):
        self.start('deploy' if not self.installed else 'discover' if not self.checked or not self.ready else 'record')

    def annotate(self):
        text=self.annotation.text().strip()
        if text and len(text)<=2000:
            self.runner.write(dict(command='annotation',text=text));self.annotation.clear()

    def fetch_data(self):
        if self.runner.busy or not self.session:return
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        out=Path.home()/'nino_real_data_imports'/('studio_'+stamp)
        self.runner.start('fetch',self.connection(),session=self.session,output=out);self.refresh()

    def export_data(self):
        if self.runner.busy or not self.local:return
        out=Q.QFileDialog.getExistingDirectory(self,'Chọn thư mục cha để tạo export mới',str(Path.home()))
        if not out:return
        target=Path(out)/('nino_export_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.runner.start('export',self.connection(),session=self.local,output=target);self.refresh()

    def open_data(self):
        if self.local:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(self.local))

    def open_history(self):
        from .studio_index import sessions
        rows=sessions()
        dialog=Q.QDialog(self);dialog.setWindowTitle('Phiên Studio đã tải · index chỉ là bản dẫn xuất');dialog.resize(900,460)
        layout=Q.QVBoxLayout(dialog)
        table=Q.QTableWidget(len(rows),5);table.setHorizontalHeaderLabels(['Session','Scenario','QC','Mức','Đường dẫn local'])
        table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        for i,row in enumerate(rows):
            for j,key in enumerate(('session_id','scenario','quality','level','path')):table.setItem(i,j,Q.QTableWidgetItem(row[key]))
        table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.ResizeToContents);layout.addWidget(table)
        note=Q.QLabel('Q2 chỉ là raw integrity; index không xác nhận movement/slip và không thay việc kiểm checksum lại. Double-click để mở thư mục.')
        note.setWordWrap(True);layout.addWidget(note)
        table.cellDoubleClicked.connect(lambda i,j:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(rows[i]['path'])))
        dialog.exec_()

    def handle(self,event):
        state=event['state']
        if state=='CHECKED':
            self.checked=True;self.ready=event['report']['ready'];self.show_topics(event['report']['topics'])
            self.detail.appendPlainText(json.dumps(event['report'],ensure_ascii=False,indent=2))
        elif state=='RECORDING':
            self.show_topics(event['topics'])
            if not getattr(self,'recording_visible',False):
                self.recording_visible=True;self.scroll.ensureWidgetVisible(self.telemetry,0,0)
            self.progress.setValue(min(99,int(100*event['elapsed_s']/event['duration_s'])))
            self.next.setText('Đang ghi. Dùng Đánh dấu sự kiện khi cần; chờ đóng bag và QC. Dừng ghi không dừng robot.')
        elif state=='PROCESS_CLOSED':
            final=event.get('final') or {}
            if final.get('state')=='INSTALLED' and event['returncode']==0:self.installed=True
            if final.get('state')=='CLOSED':
                self.session=final['session'];self.ready=False;self.progress.setValue(100)
                self.show_quality(final['report'])
                self.scroll.ensureWidgetVisible(self.detail,0,0)
            if final.get('state')=='FETCHED' and event['returncode']==0:
                self.local=final['local_directory'];self.show_quality(final['report'])
            if final.get('state')=='EXPORTED' and event['returncode']==0:
                self.detail.appendPlainText(json.dumps(final,ensure_ascii=False,indent=2))
            if event['returncode']!=0:
                self.error='Process lỗi / phiên chưa đạt. Giữ dữ liệu và log; review trước phiên tiếp.'
                self.detail.appendPlainText(self.error)
        elif state not in ('CLOSED','FETCHED','INSTALLED','EXPORTED'):
            self.detail.appendPlainText(event.get('message',state))
        self.refresh()

    def show_quality(self,report):
        lines=[report['verdict']+' · '+report['level']+' · chất lượng raw, không phải chất lượng chuyển động',report['scope']]
        for check in report['checks']:
            detail=check['detail']
            if not isinstance(detail,str):detail=json.dumps(detail,ensure_ascii=False)
            lines.append(check['verdict']+' | '+check['name']+' | '+detail)
        lines+=report['limitations']
        lines.append('Chi tiết đầy đủ: qc_report.json; raw giữ nguyên. Feature/history và TD3 replay: chưa sẵn sàng.')
        self.detail.setPlainText('\n'.join(lines))
        rows=[]
        for name,row in report.get('topics',{}).items():
            rows.append(dict(name=name,count=row['count'],observed_hz=row['observed_receipt_hz'],
                             last_receipt_age_s=None,required=False,publishers='—'))
        self.show_topics(rows)
        self.telemetry.setHorizontalHeaderLabels(['Topic raw','Mẫu bag','Hz receipt','—','—','—'])

    def show_topics(self,rows):
        self.telemetry.setHorizontalHeaderLabels(['Topic','Mẫu observer','Hz nhận','Tuổi nhận (s)','Bắt buộc','Pub'])
        self.telemetry.setRowCount(len(rows))
        for i,row in enumerate(rows):
            hz='unknown' if row['observed_hz'] is None else f"{row['observed_hz']:.2f}"
            age=row.get('last_receipt_age_s');age='unknown' if age is None else f'{age:.2f}'
            for j,value in enumerate((row['name'],row['count'],hz,age,'Có' if row['required'] else 'Không',row['publishers'])):
                self.telemetry.setItem(i,j,Q.QTableWidgetItem(str(value)))

    def refresh(self):
        busy=self.runner.busy;locked=busy or self.external_busy() or self.closing
        connection=self.connection()
        identity=tuple(connection.get(k) for k in ('host','key','domain'))
        if not busy and identity!=self.connection_key:
            self.connection_key=identity;self.installed=False;self.checked=False;self.ready=False;self.session=None
        self.primary.setEnabled(not locked)
        self.reference_button.setEnabled(not locked)
        self.primary.setText('1 · Chuẩn bị observer trên Pi' if not self.installed else
            '2 · Kiểm sensor / storage / disk' if not self.checked or not self.ready else '3 · Bắt đầu ghi 60 giây')
        if not busy:
            self.next.setText(self.error or ('Bước tiếp: tải phiên, xem QC WARN/FAIL và review trước phiên mới.' if self.session else
                'Bấm nút chính theo thứ tự. Kịch bản motion chỉ ghi lệnh từ nguồn đã được review; không tự chạy xe.'))
        self.stop.setEnabled(busy and self.runner.action=='record');self.mark.setEnabled(self.stop.isEnabled())
        self.check.setEnabled(not locked and self.installed)
        self.fetch.setEnabled(not locked and self.session is not None)
        self.export.setEnabled(not locked and self.local is not None);self.open.setEnabled(self.local is not None)
        for w in (self.scenario,self.storage,self.confirm,*self.fields.values()):w.setEnabled(not locked)

    def request_close(self):
        self.closing=True;self.runner.stop_recording();self.refresh()
