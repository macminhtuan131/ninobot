"""Concrete operational outline; selecting a step never starts a job."""
from html import escape
import json
from pathlib import Path
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q


class NextStepsPanel(Q.QWidget):
    collectionRequested=C.pyqtSignal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.steps=[]
        layout=Q.QVBoxLayout(self)
        title=Q.QLabel('VIỆC CẦN LÀM · chọn từng bước để xem thao tác và dữ liệu')
        title.setWordWrap(True);title.setStyleSheet('font-size:20px;font-weight:700');layout.addWidget(title)
        current=Q.QLabel('ƯU TIÊN NHÁNH SIM: B0 → TD3 h5 có giới hạn → so baseline. Không cần đợi real dataset.\n'
            'Nhánh dữ liệu thật chạy song song cho SysID/calibration; triển khai residual trên robot là gate riêng.')
        current.setWordWrap(True);current.setStyleSheet('color:#72ded0;padding:8px;background:#173743;');layout.addWidget(current)
        split=Q.QSplitter(C.Qt.Horizontal);layout.addWidget(split,1)
        self.list=Q.QListWidget();self.list.setMinimumWidth(245);self.list.setMaximumWidth(345)
        self.list.setWordWrap(True);self.list.setSpacing(5);split.addWidget(self.list)
        self.detail=Q.QTextBrowser();self.detail.setOpenExternalLinks(False);self.detail.setMinimumHeight(475);split.addWidget(self.detail)
        split.setStretchFactor(0,3);split.setStretchFactor(1,7)
        buttons=Q.QHBoxLayout()
        self.open_collection=Q.QPushButton('Mở Studio · chỉ chuyển trang')
        self.open_collection.clicked.connect(lambda:self.collectionRequested.emit(self.steps[self.list.currentRow()].get('action') or 'studio'));buttons.addWidget(self.open_collection)
        self.open_document=Q.QPushButton('Mở outline đầy đủ');self.open_document.clicked.connect(self.document);buttons.addWidget(self.open_document)
        layout.insertLayout(2,buttons)
        self.note=Q.QLabel('Các bước sau là kế hoạch có điều kiện. Chọn một dòng không cấp slot, chạy training hay phát lệnh robot.')
        self.note.setWordWrap(True);layout.addWidget(self.note)
        self.list.currentRowChanged.connect(self.select)
        self.reload()
    def reload(self):
        row=max(0,self.list.currentRow());self.list.clear()
        try:
            plan=json.loads(Path(__file__).with_name('research_plan.json').read_text())
            self.steps=plan['next_steps']
            for step in self.steps:
                item=Q.QListWidgetItem(step['id']+' · '+step['name']+'\n'+step['status'])
                item.setSizeHint(C.QSize(280,66));self.list.addItem(item)
            self.list.setCurrentRow(min(row,len(self.steps)-1))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.steps=[];self.detail.setPlainText('Chưa đọc được outline: '+str(exc));self.open_collection.setEnabled(False)
    def select(self,row):
        if not 0<=row<len(self.steps):return
        s=self.steps[row]
        sections=[('Ai làm',s['owner']),('1. Làm việc gì?',s['work']),('2. Thu / dùng dữ liệu nào?',s['data']),
                  ('3. Phải nhận được đầu ra gì?',s['output']),('4. Khi nào chuyển bước / dừng?',s['gate'])]
        html='<h2>'+escape(s['id']+' · '+s['name'])+'</h2><p><b>'+escape(s['status'])+'</b></p>'
        for heading,body in sections:
            html+='<h3>'+escape(heading)+'</h3><p>'+escape(body)+'</p>'
        self.detail.setHtml('<html><body style="font-size:13px;line-height:1.35;color:#e7edf7;">'+html+'</body></html>')
        self.open_collection.setEnabled(s.get('action') in ('diagnostic','studio'))
    def document(self):
        from .research_jobs import repository
        try:path=repository()/'docs/NINO_NEXT_STEPS_2026-11-04.md'
        except (OSError,ValueError) as exc:self.note.setText(str(exc));return
        if path.is_file():G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(path)))
        else:self.note.setText('Không có outline tại '+str(path))
