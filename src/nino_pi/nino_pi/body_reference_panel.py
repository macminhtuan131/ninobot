"""Local-only video/session registration dialog. No ROS, SSH or command owner."""
from pathlib import Path
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q
from .body_reference import session_identity,inspect_media,make_observation,save_observation


class EvidenceWorker(C.QThread):
    saved=C.pyqtSignal(str)
    failed=C.pyqtSignal(str)
    def __init__(self,identity,paths,labels,note,attested,destination,parent=None):
        super().__init__(parent);self.args=(identity,list(paths),dict(labels),note,attested,destination)
    def run(self):
        try:
            identity,paths,labels,note,attested,destination=self.args
            videos=[inspect_media(path,self.isInterruptionRequested) for path in paths]
            value=make_observation(identity,videos,labels,note,attested)
            if self.isInterruptionRequested():raise InterruptedError('Đã hủy; chưa lưu hồ sơ.')
            self.saved.emit(str(save_observation(value,destination)))
        except Exception as exc:self.failed.emit(str(exc))


class BodyReferenceDialog(Q.QDialog):
    def __init__(self,parent=None,session=None):
        super().__init__(parent);self.setWindowTitle('Nino · Liên kết video bánh/thân với session')
        self.resize(1000,780);self.identity=None;self.worker=None;self.closing=False;self.last_saved=None
        layout=Q.QVBoxLayout(self)
        title=Q.QLabel('REFERENCE BÁNH / THÂN · CHUẨN BỊ VÀ GẮN BẰNG CHỨNG')
        title.setStyleSheet('font-size:18px;font-weight:700');layout.addWidget(title)
        self.instructions=Q.QLabel('Nếu còn video đúng lượt V2, dùng video đó trước. Với phiên mới: camera cố định, '
            'thấy từng bánh muốn kết luận và marker thân so với mốc đứng yên; quay liên tục từ baseline đến hết dừng.\n'
            'Màn hình này chỉ đọc file local và lưu JSON derived. Không quay video, chạy xe, đổi RC/enable hoặc cấp lượt thu.')
        self.instructions.setWordWrap(True);layout.addWidget(self.instructions)
        form=Q.QFormLayout();layout.addLayout(form)
        row=Q.QHBoxLayout();self.session_path=Q.QLineEdit();self.session_path.setReadOnly(True)
        self.choose_session=Q.QPushButton('1 · Chọn session / bag local');self.choose_session.clicked.connect(self.pick_session)
        row.addWidget(self.session_path,1);row.addWidget(self.choose_session);form.addRow('Session đã thu',row)
        self.identity_note=Q.QLabel('Chọn session có manifest.json và bag/ hoặc raw/bag/. Chưa kiểm integrity bag tại đây.')
        self.identity_note.setWordWrap(True);layout.addWidget(self.identity_note)
        self.videos=Q.QListWidget();self.videos.setMinimumHeight(90);layout.addWidget(self.videos)
        row=Q.QHBoxLayout()
        self.add=Q.QPushButton('2 · Thêm video gốc');self.add.clicked.connect(self.pick_videos)
        self.remove=Q.QPushButton('Bỏ khỏi danh sách');self.remove.clicked.connect(self.remove_video)
        self.play=Q.QPushButton('Mở video đã chọn');self.play.clicked.connect(self.play_video)
        for b in (self.add,self.remove,self.play):row.addWidget(b)
        layout.addLayout(row)
        form=Q.QFormLayout();layout.addLayout(form);self.labels={}
        for key,label in [('wheel_left_rotation','3 · Bánh trái quay'),('wheel_right_rotation','Bánh phải quay'),('body_translation','Thân dịch chuyển so mốc')]:
            combo=Q.QComboBox()
            for name,value in [('Chưa đánh giá',None),('Quan sát thấy','observed'),('Không quan sát thấy','not_observed'),('Không phân biệt được','ambiguous'),('Không nhìn thấy bộ phận','not_visible')]:combo.addItem(name,value)
            self.labels[key]=combo;form.addRow(label,combo)
        self.note=Q.QPlainTextEdit();self.note.setPlaceholderText('Góc nhìn, mốc cố định, sàn/tải/caster, can thiệp hoặc điểm còn nghi ngờ…')
        self.note.setMaximumHeight(85);layout.addWidget(self.note)
        self.attest=Q.QCheckBox('Tôi đã đối chiếu video đúng session được chọn. Đây là nhãn operator, chưa là review độc lập.')
        self.attest.toggled.connect(self.refresh);layout.addWidget(self.attest)
        row=Q.QHBoxLayout();self.destination=Q.QLineEdit(str(Path.home()/'nino_research/body_reference_reviews'))
        self.choose_output=Q.QPushButton('Chọn thư mục derived');self.choose_output.clicked.connect(self.pick_destination)
        row.addWidget(self.destination,1);row.addWidget(self.choose_output);layout.addLayout(row)
        self.limit=Q.QLabel('QC: hash video + manifest và nhãn quan sát; body speed / latency / slip vẫn unknown. '
            'Nếu thiếu ffprobe: chỉ tính hash, chưa xác nhận media. FPS metadata không thay frame timestamps. Không tự chấm Q3/Q4, không thêm raw hoặc tạo replay TD3. '
            '“Không quan sát thấy” không chứng minh vận tốc bằng zero.')
        self.limit.setWordWrap(True);layout.addWidget(self.limit)
        self.status=Q.QLabel('Bước tiếp: chọn session, thêm video rồi ghi nhận quan sát. Nếu chưa có video: chỉ chuẩn bị góc quay, chưa cần chạy xe.')
        self.status.setWordWrap(True);layout.addWidget(self.status)
        row=Q.QHBoxLayout();self.save=Q.QPushButton('4 · Tính hash và lưu hồ sơ riêng');self.save.clicked.connect(self.start_save)
        self.open=Q.QPushButton('Mở hồ sơ đã lưu');self.open.clicked.connect(self.open_saved)
        self.cancel=Q.QPushButton('Đóng');self.cancel.clicked.connect(self.close)
        for b in (self.save,self.open,self.cancel):row.addWidget(b)
        layout.addLayout(row)
        if session:
            try:self.set_session(session)
            except (ValueError,OSError) as exc:self.status.setText(str(exc))
        self.refresh()

    def set_session(self,path):
        self.identity=session_identity(path);self.session_path.setText(self.identity['session_directory'])
        self.attest.setChecked(False)
        self.identity_note.setText('Session: '+self.identity['session_id']+' · manifest '+self.identity['manifest_sha256'][:12]+'… · chỉ pin danh tính, chưa xác nhận raw/body.')
        self.refresh()
    def pick_session(self):
        path=Q.QFileDialog.getExistingDirectory(self,'Chọn session đã tải về laptop',str(Path.home()))
        if path:
            try:self.set_session(path)
            except (OSError,ValueError) as exc:self.status.setText(str(exc))
    def pick_videos(self):
        paths,_=Q.QFileDialog.getOpenFileNames(self,'Video gốc; không copy hay sửa video',str(Path.home()),'Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)')
        known={self.videos.item(i).text() for i in range(self.videos.count())}
        for path in paths:
            if path not in known:self.videos.addItem(path);known.add(path)
        if paths:self.attest.setChecked(False)
        self.refresh()
    def remove_video(self):
        row=self.videos.currentRow()
        if row>=0:self.videos.takeItem(row);self.attest.setChecked(False)
        self.refresh()
    def play_video(self):
        item=self.videos.currentItem()
        if item:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(item.text()))
    def pick_destination(self):
        path=Q.QFileDialog.getExistingDirectory(self,'Derived ngoài thư mục session/raw',self.destination.text())
        if path:self.destination.setText(path)
    def start_save(self):
        if self.worker or not self.identity or not self.videos.count() or not self.attest.isChecked():return
        worker=EvidenceWorker(dict(self.identity),[self.videos.item(i).text() for i in range(self.videos.count())],
            {key:w.currentData() for key,w in self.labels.items()},self.note.toPlainText(),True,self.destination.text(),self)
        self.worker=worker;worker.saved.connect(self.saved);worker.failed.connect(self.failed);worker.finished.connect(self.worker_finished)
        self.status.setText('Đang đọc video/tính hash ở background; không copy file. Đóng để hủy trước lưu.');self.refresh();worker.start()
    def saved(self,path):
        self.last_saved=path;self.status.setText('Đã lưu hồ sơ riêng: '+path+'\nBước tiếp: review video/raw cùng session; chưa được dùng làm body speed/slip hoặc release motion.')
    def failed(self,error):self.status.setText('Chưa lưu được: '+error)
    def worker_finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater();self.refresh()
        if self.closing:self.close()
    def open_saved(self):
        if self.last_saved:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(self.last_saved))
    def refresh(self):
        busy=self.worker is not None
        for w in (self.choose_session,self.add,self.remove,self.play,self.note,self.attest,self.destination,self.choose_output,*self.labels.values()):w.setEnabled(not busy)
        self.save.setEnabled(not busy and bool(self.identity) and self.videos.count()>0 and self.attest.isChecked())
        self.open.setEnabled(not busy and self.last_saved is not None)
        self.cancel.setText('Hủy tính hash và đóng' if busy else 'Đóng')
    def closeEvent(self,event):
        if self.worker:
            self.closing=True;self.worker.requestInterruption();self.status.setText('Đang hủy đọc file; chờ worker đóng.');event.ignore();return
        super().closeEvent(event)
