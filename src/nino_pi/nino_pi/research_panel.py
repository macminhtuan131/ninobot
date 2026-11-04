"""Native Qt build/progress panel with actual artifact-backed job controls."""
import json
from pathlib import Path
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q
from .research_jobs import JOBS,ResearchRunner,repository,workflow_state
from .next_steps_panel import NextStepsPanel
from .td3_parameter_panel import TD3ParameterPanel


class ResearchPanel(Q.QWidget):
    collectionRequested=C.pyqtSignal(str)
    all_closed=C.pyqtSignal()
    def __init__(self,parent=None,root=None,hardware_busy=None):
        super().__init__(parent);self.hardware_busy=hardware_busy or (lambda:False);self.closing=False;self.external_busy=False
        setting=C.QSettings('Nino','ControlModes')
        self.root=Path(root or setting.value('research_root',str(Path.home()/'nino_research/residual_build_v1')))
        self.runner=ResearchRunner(self.root,self);self.runner.update.connect(self.handle)
        self.runner.closed.connect(self.job_closed)
        root_layout=Q.QVBoxLayout(self)
        self.sections=Q.QTabWidget();root_layout.addWidget(self.sections)
        def section(widget,title):
            scroll=Q.QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(Q.QFrame.NoFrame)
            scroll.setWidget(widget);self.sections.addTab(scroll,title)
        self.roadmap=NextStepsPanel();self.roadmap.collectionRequested.connect(self.collectionRequested.emit)
        section(self.roadmap,'Việc cần làm · robot / dữ liệu / nghiên cứu')
        software=Q.QWidget();section(software,'Công cụ kiểm phần mềm · History / TD3 / PPO')
        self.parameters=TD3ParameterPanel();section(self.parameters,'TD3 · tham số có phiên bản')
        layout=Q.QVBoxLayout(software)
        title=Q.QLabel('XÂY DỰNG PROJECT · bằng chứng theo từng gate');title.setStyleSheet('font-size:21px;font-weight:700');layout.addWidget(title)
        note=Q.QLabel('Các nút chạy trên laptop, không nối Pi. TD3/PPO fixture giảm bậc và TD3 FACTORY là các job riêng.\nFACTORY dùng factory_floor_mixed + mô hình Nino + wheel PI: 48 bước kiểm, 128 bước học; chưa chứng minh hiệu quả trên robot.');note.setWordWrap(True);layout.addWidget(note)
        row=Q.QHBoxLayout();self.location=Q.QLineEdit(str(self.root));self.location.setReadOnly(True);row.addWidget(self.location,1)
        choose=Q.QPushButton('Thư mục kết quả');choose.clicked.connect(self.choose_root);row.addWidget(choose)
        self.reload_button=Q.QPushButton('Đọc lại bằng chứng');self.reload_button.clicked.connect(self.reload);row.addWidget(self.reload_button);layout.addLayout(row)
        self.scene=Q.QGraphicsScene(self);self.diagram=Q.QGraphicsView(self.scene);self.diagram.setMinimumHeight(255);self.diagram.setMaximumHeight(310)
        self.diagram.setRenderHint(G.QPainter.Antialiasing);layout.addWidget(self.diagram)
        self.buttons={};grid=Q.QGridLayout()
        for i,(action,(label,deps)) in enumerate(JOBS.items()):
            b=Q.QPushButton(label);b.setToolTip('Phụ thuộc: '+(', '.join(deps) or 'không')+' · lưu toàn bộ lần lỗi/hủy');b.clicked.connect(lambda checked=False,a=action:self.run(a));grid.addWidget(b,i//2,i%2);self.buttons[action]=b
            if action=='factory-td3':
                b.setObjectName('primary');b.setToolTip('Gazebo factory mixed + Nino/caster + wheel PI. 48 bước kiểm rồi 128 bước học mới. Nạp mesh có thể lâu; xem log. Chỉ localhost, không nối Pi.')
        register=Q.QPushButton('Đăng ký dữ liệu SysID · CSV + metadata');register.clicked.connect(self.register);grid.addWidget(register,(len(JOBS)+1)//2,0,1,2);self.register_button=register
        layout.addLayout(grid)
        controls=Q.QHBoxLayout();self.stop=Q.QPushButton('Hủy job local');self.stop.clicked.connect(self.runner.cancel);controls.addWidget(self.stop)
        open_result=Q.QPushButton('Mở thư mục artifact');open_result.clicked.connect(lambda:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(self.root))));controls.addWidget(open_result)
        real=Q.QPushButton('Bước dữ liệu thật → phiên diagnostic');real.clicked.connect(lambda:self.collectionRequested.emit('diagnostic'));controls.addWidget(real);layout.addLayout(controls)
        self.progress=Q.QProgressBar();layout.addWidget(self.progress)
        self.next=Q.QLabel();self.next.setWordWrap(True);self.next.setStyleSheet('color:#72ded0;font-weight:600');layout.addWidget(self.next)
        output=Q.QTabWidget()
        self.job_table=Q.QTableWidget(len(JOBS),3);self.job_table.setHorizontalHeaderLabels(['Bước','Bằng chứng','Artifact'])
        self.job_table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers);self.job_table.setSelectionBehavior(Q.QAbstractItemView.SelectRows)
        self.job_table.horizontalHeader().setSectionResizeMode(0,Q.QHeaderView.ResizeToContents)
        self.job_table.horizontalHeader().setSectionResizeMode(1,Q.QHeaderView.ResizeToContents)
        self.job_table.horizontalHeader().setSectionResizeMode(2,Q.QHeaderView.Stretch)
        self.job_table.cellClicked.connect(self.show_result)
        output.addTab(self.job_table,'Kết quả / to-do')
        self.results=Q.QPlainTextEdit();self.results.setReadOnly(True);output.addTab(self.results,'Thông số / kết quả chi tiết')
        self.log=Q.QPlainTextEdit();self.log.setReadOnly(True);self.log.document().setMaximumBlockCount(300);output.addTab(self.log,'Quá trình chạy')
        output.setMinimumHeight(170);layout.addWidget(output,1);self.output_tabs=output
        self.reload()
    def choose_root(self):
        if self.runner.busy:return
        path=Q.QFileDialog.getExistingDirectory(self,'Chọn thư mục workflow',str(self.root))
        if path:
            self.root=Path(path);self.runner.root=self.root;self.location.setText(path)
            C.QSettings('Nino','ControlModes').setValue('research_root',path);self.reload()
    def reload(self):
        self.roadmap.reload()
        try:self.states=workflow_state(self.root);self.error=None
        except (ImportError,OSError,ValueError) as exc:self.states={};self.error=str(exc)
        self.draw_diagram();self.refresh()
        for i,action in enumerate(JOBS):
            state=self.states.get(action,{})
            for col,value in enumerate((JOBS[action][0],state.get('label','CHƯA KIỂM'),state.get('path') or state.get('error','Chưa có dữ liệu'))):
                item=Q.QTableWidgetItem(value);item.setToolTip(value);self.job_table.setItem(i,col,item)
        if self.error:self.next.setText('Chưa đọc được research toolchain: '+self.error);return
        todo=next((a for a in JOBS if a!='sysid' and self.states[a]['state']!='verified'),None)
        self.next.setText('Bước tiếp: bấm '+JOBS[todo][0] if todo else 'Phần mềm đã có artifact. Bước tiếp: diagnostic có video/reference thân xe; review trước khi mở pilot/SysID mới.')
    def draw_diagram(self):
        self.scene.clear();self.scene.setBackgroundBrush(G.QColor('#101827'))
        cards=[('validate','History / projection\nEnvironment trace',0,0),('train-td3','TD3 giảm bậc\nOptimizer + actor',1,0),('train-ppo','PPO đối chứng\nCùng ABI',1,1),('compare','B0 / B1 / Governor\nTD3 / PPO giảm bậc',2,0),('ros-fixture','ROS shadow fixture\nKhông phát cmd motor',2,1),('gazebo-fixture','Gazebo flat fixture\nKhông calibration Nino',3,0),('factory-td3','TD3 FACTORY mixed\nNino + caster + wheel PI',3,1),('sysid','Dữ liệu thật + SysID\nWhole-session holdout',4,1),('hardware','Model / benchmark\nShadow thật → bounded α',4,0)]
        positions={key:(col*205,row*102) for key,_,col,row in cards}
        # Roadmap order. Exact executable dependencies are on button tooltips.
        for a,b in [('validate','train-td3'),('validate','train-ppo'),('train-td3','compare'),('train-ppo','compare'),('train-td3','ros-fixture'),('compare','gazebo-fixture'),('gazebo-fixture','factory-td3'),('sysid','hardware'),('ros-fixture','hardware'),('factory-td3','hardware')]:
            x,y=positions[a];xx,yy=positions[b];self.scene.addLine(x+188,y+38,xx,yy+38,G.QPen(G.QColor('#50647e'),1.4))
            self.scene.addPolygon(G.QPolygonF([C.QPointF(xx,yy+38),C.QPointF(xx-7,yy+34),C.QPointF(xx-7,yy+42)]),G.QPen(G.QColor('#50647e')),G.QBrush(G.QColor('#50647e')))
        for key,text,col,row in cards:
            state=self.states.get(key,{});verified=state.get('state')=='verified'
            color='#695520' if verified and key=='factory-td3' else '#185c55' if verified else '#27354b';x,y=positions[key]
            self.scene.addRect(x,y,188,78,G.QPen(G.QColor('#42b6a6' if verified else '#53637b')),G.QBrush(G.QColor(color)))
            grade='SMOKE ĐẠT / TASK CHƯA RÕ' if verified and key=='factory-td3' else 'ĐẠT PHẦN MỀM' if verified and key!='sysid' else 'CẦN REVIEW' if verified else 'CHỜ BẰNG CHỨNG'
            item=self.scene.addText(text+'\n'+grade,G.QFont('DejaVu Sans',9))
            item.setDefaultTextColor(G.QColor('#e7edf7'));item.setTextWidth(180);item.setPos(x+3,y+1)
            item.setToolTip(state.get('path') or ('Gate triển khai chưa mở; không tự tăng authority' if key=='hardware' else state.get('error','Chưa có artifact')))
        self.scene.setSceneRect(-5,-5,1020,195)
        C.QTimer.singleShot(0,self.fit_diagram)
    def fit_diagram(self):
        if hasattr(self,'diagram'):self.diagram.fitInView(self.scene.sceneRect(),C.Qt.KeepAspectRatio)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        C.QTimer.singleShot(0,self.fit_diagram)
    def refresh(self):
        locked=self.runner.busy or self.hardware_busy() or self.external_busy or self.closing
        for action,b in self.buttons.items():
            ready=all(self.states.get(dep,{}).get('state')=='verified' for dep in JOBS[action][1])
            if action=='sysid':ready=ready and (self.root/'registration.json').is_file()
            b.setEnabled(not locked and self.error is None and ready)
        self.register_button.setEnabled(not locked and self.error is None);self.stop.setEnabled(self.runner.busy and not self.runner.cancelling)
    def run(self,action):
        if self.hardware_busy() or self.external_busy:return
        try:
            if self.runner.start(action):self.sections.setCurrentIndex(1);self.progress.setValue(0);self.log.clear();self.output_tabs.setCurrentIndex(2);self.next.setText('Đang chạy '+JOBS[action][0]+' · đợi process đóng và manifest được kiểm');self.refresh()
        except (ValueError,OSError) as exc:self.next.setText('Chưa chạy: '+str(exc))
    def handle(self,event):
        if event.get('message'):self.log.appendPlainText(event['message'])
        if event.get('progress') is not None:self.progress.setValue(int(event['progress']*100))
        if event.get('state')=='progress' and event.get('action')=='factory-td3' and event.get('message'):
            self.next.setText('FACTORY · '+event['message']+' · chỉ mô phỏng; chờ process đóng và kiểm manifest.')
        if event.get('result'):self.results.setPlainText(json.dumps(event['result'],ensure_ascii=False,indent=2))
        if event.get('state')=='closed':
            self.reload()
            self.output_tabs.setCurrentIndex(1)
            if event.get('returncode')!=0:self.next.setText('Job lỗi/hủy; artifact được giữ. Đọc log và sửa đúng nguyên nhân; không tự retry hoặc coi là pass.')
        self.refresh()
    def job_closed(self):
        if self.closing:self.all_closed.emit()
    def request_close(self):
        self.closing=True;self.runner.cancel();self.refresh()
    def show_result(self,row,column):
        self.sections.setCurrentIndex(1)
        action=list(JOBS)[row];state=self.states.get(action,{})
        if not state.get('path'):self.results.setPlainText(state.get('error','Chưa có dữ liệu'));return
        path=Path(state['path']);names={'validate':'validation.json','train-td3':'training_result.json','audit-td3':'audit.json','train-ppo':'training_result.json',
            'compare':'comparison.json','ros-fixture':'ros_result.json','gazebo-fixture':'gazebo_result.json','factory-td3':'factory_result.json','sysid':'sysid_result.json'}
        try:
            body=(path/names[action]).read_text();notice=''
            if action=='factory-td3':notice='SMOKE TÍCH HỢP ĐẠT. Task/vượt vật cản và learned benefit chưa được xác nhận.\n\n'
            self.results.setPlainText(notice+str(path)+'\n'+body);self.output_tabs.setCurrentIndex(1)
        except OSError as exc:self.results.setPlainText('Thiếu kết quả: '+str(exc))
    def register(self):
        try:
            csv_path,_=Q.QFileDialog.getOpenFileName(self,'CSV đáp ứng bánh · giữ nguyên raw bag','','CSV (*.csv)')
            if not csv_path:return
            meta,_=Q.QFileDialog.getOpenFileName(self,'Metadata SI / clock / holdout · xem residual_sysid.template.json','','JSON (*.json)')
            if not meta:return
            from nino_rl.residual_sysid import register
            register(self.root,csv_path,meta);self.results.setPlainText((self.root/'registration.json').read_text());self.reload()
        except (OSError,ValueError,KeyError,ImportError) as exc:self.next.setText('Chưa đăng ký: '+str(exc))
