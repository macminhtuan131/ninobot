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
        self.root=Path(root or setting.value('research_root_v3',str(Path.home()/'nino_research/sim_guided_baseline_v3')))
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
        sim=Q.QWidget();section(sim,'NHÁNH SIM · không chờ dữ liệu thật')
        sim_layout=Q.QVBoxLayout(sim)
        sim_title=Q.QLabel('SIM · tracking → dừng → đánh giá');sim_title.setStyleSheet('font-size:21px;font-weight:700');sim_layout.addWidget(sim_title)
        self.sim_version=Q.QComboBox();self.sim_version.addItems(['V2 · task/reward/stop · 512 bước','V1 · lịch sử progress · 256 bước','Kiểm bias sàn sạch + reference offline','V3 · estimator + follower trong Gazebo · residual zero'])
        self.sim_version.setCurrentIndex(3 if self.root.name=='sim_guided_baseline_v3' else 2 if self.root.name=='sim_clear_bias_v1' else 1 if self.root.name=='sim_branch_pilot_v1' else 0)
        self.sim_version.currentIndexChanged.connect(self.change_sim_version);sim_layout.addWidget(self.sim_version)
        self.sim_note=Q.QLabel();self.sim_note.setWordWrap(True);sim_layout.addWidget(self.sim_note)
        self.sim_buttons={};self.sim_status={};self.sim_rows={}
        sim_titles={'sim-baselines':'1 · Kiểm B0 trên ba môi trường','sim-train':'2 · Train TD3 h5 · tối đa 256 bước','sim-evaluate':'3 · So B0 / B1 yaw / TD3 h5'}
        sim_titles.update({'sim-v2-baselines':'1 · B0 đi + dừng · 2 lượt/môi trường','sim-v2-train':'2 · Train TD3 h5 · tối đa 512 bước','sim-v2-evaluate':'3 · So tracking / dừng · 2 lượt/arm'})
        sim_titles.update({'sim-bias-clear':'1 · Kiểm B0 / checkpoint V2 đóng băng · sàn sạch','sim-guidance-contract':'2 · Kiểm reference follower → residual · chỉ offline'})
        sim_titles.update({'sim-v3-baselines':'V3 · Chạy 8 lượt baseline clear floor · không actor/optimizer'})
        for action in sim_titles:
            container=Q.QWidget();column=Q.QVBoxLayout(container);column.setContentsMargins(0,0,0,0)
            row=Q.QHBoxLayout();button=Q.QPushButton(sim_titles[action]);button.setObjectName('primary')
            button.clicked.connect(lambda checked=False,a=action:self.run(a));row.addWidget(button,1);self.sim_buttons[action]=button
            view=Q.QPushButton('Xem kết quả');view.clicked.connect(lambda checked=False,a=action:self.show_sim_result(a));row.addWidget(view)
            column.addLayout(row)
            status=Q.QLabel();status.setWordWrap(True);column.addWidget(status);self.sim_status[action]=status
            sim_layout.addWidget(container);self.sim_rows[action]=container
        self.sim_progress=Q.QProgressBar();sim_layout.addWidget(self.sim_progress)
        self.sim_stop=Q.QPushButton('Hủy job sim local · giữ artifact');self.sim_stop.clicked.connect(self.runner.cancel);sim_layout.addWidget(self.sim_stop)
        self.sim_location=Q.QLabel();self.sim_location.setWordWrap(True);sim_layout.addWidget(self.sim_location)
        self.sim_next=Q.QLabel('Điểm dừng: baseline không có body response → sửa backend; gờ 6 mm chưa vượt được → chỉ train sàn sạch.\n'
            'Mixed 22 mm là diagnostic, không mặc định thuộc envelope vượt. Dữ liệu real phục vụ calibration/sim-to-real ở nhánh song song.')
        self.sim_next.setWordWrap(True);sim_layout.addWidget(self.sim_next)
        self.sim_table=Q.QTableWidget(0,5);self.sim_table.setHorizontalHeaderLabels(['Arm','Body x cuối (m)','RMSE ngang (mm)','v cuối (m/s)','Mốc 0,95 m (s)'])
        self.sim_table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.sim_table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch);self.sim_table.setMaximumHeight(145)
        sim_layout.addWidget(self.sim_table)
        self.sim_guidance_status=Q.QLabel();self.sim_guidance_status.setWordWrap(True);sim_layout.addWidget(self.sim_guidance_status)
        self.sim_log=Q.QPlainTextEdit();self.sim_log.setReadOnly(True);self.sim_log.document().setMaximumBlockCount(300)
        sim_layout.addWidget(self.sim_log,1)
        self.sections.setCurrentIndex(3)
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
    def active_sim_actions(self):
        if self.sim_version.currentIndex()==3:return ('sim-v3-baselines',)
        if self.sim_version.currentIndex()==2:return ('sim-bias-clear','sim-guidance-contract')
        return ('sim-v2-baselines','sim-v2-train','sim-v2-evaluate') if self.sim_version.currentIndex()==0 else ('sim-baselines','sim-train','sim-evaluate')
    def change_sim_version(self,index):
        if self.runner.busy:return
        settings=C.QSettings('Nino','ControlModes')
        key={0:'research_root_v2',1:'research_root',2:'research_root_bias',3:'research_root_v3'}[index]
        fallback=Path.home()/'nino_research'/{0:'sim_task_v2',1:'sim_branch_pilot_v1',2:'sim_clear_bias_v1',3:'sim_guided_baseline_v3'}[index]
        self.root=Path(settings.value(key,str(fallback)));self.runner.root=self.root
        self.location.setText(str(self.root));self.reload()
    def choose_root(self):
        if self.runner.busy:return
        path=Q.QFileDialog.getExistingDirectory(self,'Chọn thư mục workflow',str(self.root))
        if path:
            self.root=Path(path);self.runner.root=self.root;self.location.setText(path)
            key={0:'research_root_v2',1:'research_root',2:'research_root_bias',3:'research_root_v3'}[self.sim_version.currentIndex()]
            C.QSettings('Nino','ControlModes').setValue(key,path);self.reload()
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
        actions=self.active_sim_actions()
        todo=next((a for a in actions if self.states[a]['state']!='verified'),None)
        if not self.runner.busy:
            self.sim_progress.setRange(0,100)
            self.sim_progress.setValue(round(100*sum(self.states[a]['state']=='verified' for a in actions)/len(actions)))
        self.next.setText('Nhánh sim: bấm '+JOBS[todo][0] if todo else 'Pilot sim đã có artifact. Review bảng baseline/TD3 trước khi mở train dài; dữ liệu real phục vụ calibration song song.')
        self.sim_next.setText('Bước tiếp: '+JOBS[todo][0]+' → đợi manifest và xem kết quả trước bước kế.' if todo else 'Đã có artifact ba stage; review task/tracking/dừng. Chưa mở train dài hoặc hardware.')
        self.sim_table.setRowCount(0)
        self.sim_guidance_status.clear()
        current=self.states.get('sim-bias-clear' if actions[0]=='sim-bias-clear' else actions[-1],{})
        if actions[0]=='sim-v3-baselines':
            if current.get('state')=='verified':
                try:self.show_guided_baseline_table(json.loads((Path(current['path'])/'evaluation_result.json').read_text()))
                except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được V3: '+str(exc))
            else:self.sim_next.setText('V3: kiểm B0 constant / guided, path bearing ±5°, 2 lượt/điều kiện. Không train; giữ các batch cũ.')
            return
        if current.get('state')=='verified':
            try:
                evaluation=json.loads((Path(current['path'])/'evaluation_result.json').read_text())
                v2=actions[-1].startswith('sim-v2-') or actions[0]=='sim-bias-clear'
                metrics=[(arm+'/'+str(i+1),m) for arm,runs in evaluation['arms'].items() for i,m in enumerate(runs)] if v2 else list(evaluation['arms'].items())
                self.sim_table.setColumnCount(8 if v2 else 5)
                self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','x cuối (m)','RMSE ngang (mm)','v cuối (m/s)','Mốc (s)']+(['RMSE chuẩn (m/s)','Dừng 2 s','Task'] if v2 else []))
                if actions[0]=='sim-bias-clear':self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','RMSE v (m/s)','RMSE ngang (mm)','ω ref TB (rad/s)','ω GT TB (rad/s)','y cuối (m)','Dừng 2 s','Task'])
                self.sim_table.setRowCount(len(metrics));self.sim_table.setMinimumHeight(240 if v2 else 140);self.sim_table.setMaximumHeight(280 if v2 else 180)
                for row,(arm,metric) in enumerate(metrics):
                    marker=metric['local_marker_time_s']
                    values=[arm,f"{metric['final_x_m']:.4f}",f"{metric['lateral_rmse_m']*1000:.3f}",
                            f"{metric['final_body_speed_m_s']:.5f}",'chưa tới' if marker is None else f'{marker:.2f}']
                    if v2:values += [f"{metric['nominal_shaped_tracking_rmse_m_s']:.5f}",'ĐẠT' if metric['stop_completed'] else 'CHƯA ĐẠT','ĐẠT' if metric['task_success'] else 'KHÔNG ĐẠT']
                    if actions[0]=='sim-bias-clear':values=[arm,f"{metric['nominal_shaped_tracking_rmse_m_s']:.5f}",f"{metric['lateral_rmse_m']*1000:.3f}",
                        f"{metric['mean_accepted_yaw_rad_s']:.5f}",f"{metric['mean_gt_yaw_rate_rad_s']:.5f}",f"{metric['final_y_m']:.4f}",
                        'ĐẠT' if metric['stop_completed'] else 'CHƯA ĐẠT','ĐẠT' if metric['task_success'] else 'KHÔNG ĐẠT']
                    for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
                self.sim_next.setText(('V2 · hai fresh launches/arm; một learner seed. Dừng đạt và task đạt là hai điều kiện riêng.\n' if v2 else 'PILOT ĐÃ CHẠY · mỗi arm một fresh launch, một learner seed. Return/progress cao hơn chưa là benefit.\n')+
                    'Xem cả lệch ngang và vận tốc cuối: dừng nguồn không đồng nghĩa thân đã dừng tại horizon. Chưa promote checkpoint.')
                if v2:
                    b0=evaluation['arms']['B0'];td3=evaluation['arms']['TD3_h5']
                    worse=all(min(r[key] for r in td3)>max(r[key] for r in b0) for key in ('nominal_shaped_tracking_rmse_m_s','lateral_rmse_m'))
                    self.sim_next.setText('V2 · '+('Hai lượt TD3 đều có RMSE vận tốc và lệch ngang lớn hơn từng lượt B0. Chưa tăng ngân sách train.' if worse else 'Review từng lượt: pilot nhỏ chưa đủ xác nhận benefit.')+
                        '\nTask/dừng đạt chỉ là feasibility, chưa là chất lượng tốt. Một learner seed; chưa promote. Bước tiếp: baseline/follower và phân tích bias residual trước tiếp xúc.')
                if actions[0]=='sim-bias-clear':
                    bias=evaluation.get('clear_floor_reference_bias_observed')
                    self.sim_next.setText(('SÀN SẠCH · bias yaw vẫn xuất hiện ở cả hai lượt TD3. Gờ không giải thích toàn bộ lệch hướng.' if bias else 'SÀN SẠCH · chưa thấy bias nhất quán; review từng lượt.')+
                        '\nCheckpoint không sửa, không train thêm. Reference follower mới chỉ đạt offline, chưa nối Gazebo/robot.'+
                        ('\nBước tiếp: protocol V3 cho baseline có guidance và velocity-tracking objective.' if self.states.get('sim-guidance-contract',{}).get('state')=='verified' else '\nBước tiếp: bấm 2 để kiểm adapter reference offline.'))
                    guide=self.states.get('sim-guidance-contract',{})
                    if guide.get('state')=='verified':
                        data=json.loads((Path(guide['path'])/'guidance_result.json').read_text())
                        self.sim_guidance_status.setText(f"REFERENCE OFFLINE · {data['fixture_count']}/{data['fixture_count']} fixture đạt · observation {data['observation_size']}D, thêm 0 pose feature. Chưa nối guidance vào Gazebo/robot; localization chưa được xác minh.")
            except (OSError,ValueError,KeyError) as exc:self.sim_next.setText('Chưa đọc được bảng pilot: '+str(exc))
    def show_guided_baseline_table(self,evaluation):
        runs=evaluation['runs'];self.sim_table.setColumnCount(9)
        self.sim_table.setHorizontalHeaderLabels(['Arm/lượt','Tuyến (°)','RMSE path (mm)','Max path (mm)','Max est pos (mm)','Max est yaw (rad)','Dừng 2 s','Task','Gate đề xuất'])
        self.sim_table.setRowCount(len(runs));self.sim_table.setMinimumHeight(310);self.sim_table.setMaximumHeight(360)
        for row,metric in enumerate(runs):
            c=metric['condition'];values=[c['arm']+'/'+str(c['repeat']+1),f"{c['path_bearing_deg']:+.0f}",
                f"{metric['cross_track_rmse_m']*1000:.2f}",f"{metric['maximum_cross_track_m']*1000:.2f}",
                f"{metric['maximum_estimator_position_error_m']*1000:.2f}",f"{metric['maximum_estimator_yaw_error_rad']:.5f}",
                'ĐẠT' if metric['stop_completed'] else 'CHƯA','ĐẠT' if metric['task_success'] else 'CHƯA',
                'CANDIDATE' if metric['functional_proposal_pass'] else 'CHƯA ĐẠT']
            for col,value in enumerate(values):self.sim_table.setItem(row,col,Q.QTableWidgetItem(value))
        passed=evaluation['baseline_functional_candidate']
        self.sim_next.setText(('V3 baseline đạt gate đề xuất trong batch này; chưa là chứng nhận chất lượng nhà máy.' if passed else 'V3 chưa qua gate đề xuất; review drift/reference/stop trước learning.')+
            '\nKhông actor, không optimizer. Bước tiếp: contract reward/baseline/zero-init cho TD3 V3 với ngân sách riêng; không resume V2 chỉ vì cùng ABI.')
        self.sim_guidance_status.setText('ĐÃ NỐI GAZEBO · wheel + gyro-Z → estimate → follower → residual zero → projection → wheel PI. GT chỉ reset/evaluator; chưa calibration hoặc triển khai robot thật.')
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
            complete=(action.startswith('sim-v2-') or action in ('sim-bias-clear','sim-guidance-contract','sim-v3-baselines')) and self.states.get(action,{}).get('state')=='verified'
            b.setEnabled(not locked and self.error is None and ready and not complete)
        self.register_button.setEnabled(not locked and self.error is None);self.stop.setEnabled(self.runner.busy and not self.runner.cancelling)
        for action,button in self.sim_buttons.items():
            ready=all(self.states.get(dep,{}).get('state')=='verified' for dep in JOBS[action][1])
            state=self.states.get(action,{})
            complete=(action.startswith('sim-v2-') or action in ('sim-bias-clear','sim-guidance-contract','sim-v3-baselines')) and state.get('state')=='verified'
            button.setEnabled(not locked and self.error is None and ready and not complete)
            button.setToolTip('Stage đã đóng; bấm Xem kết quả. Không tự chạy lại ngân sách cũ.' if complete else JOBS[action][0])
            self.sim_status[action].setText(state.get('label','CHƯA KIỂM')+(' · chờ bước trước' if not ready else ''))
            self.sim_status[action].setToolTip(str(state.get('path') or state.get('error','Chưa có artifact')))
        self.sim_location.setText('Thư mục kết quả: '+str(self.root)+' · đổi tại tab Công cụ kiểm phần mềm.')
        self.sim_stop.setEnabled(self.runner.busy and self.runner.action.startswith('sim-') and not self.runner.cancelling)
        self.sim_version.setEnabled(not locked)
        active=self.active_sim_actions()
        for action,widget in self.sim_rows.items():widget.setVisible(action in active)
        self.sim_note.setText('Chỉ Gazebo local · không cần Pi/real dataset. '+('V2: reward bám profile chuẩn độc lập; không thưởng progress. 14 s/lượt gồm 6 s pha dừng. B0 2 lượt/môi trường; train 512 bước; evaluate 2 lượt/arm. Một seed, chưa hội tụ hoặc promote.' if active[0].startswith('sim-v2-') else 'V1 lịch sử: progress reward, horizon 10 s, train 256 bước. TD3 từng tăng tốc; dừng nguồn chưa bảo đảm thân dừng. Giữ nguyên kết quả cũ.'))
        if active[0]=='sim-bias-clear':self.sim_note.setText('Checkpoint V2 đóng băng, 4 lượt clear floor, zero optimizer updates. Tách bias policy khỏi gờ. Bước 2 kiểm adapter pose ước lượng → follower → reference → residual; chưa có Gazebo guidance hoặc localization/hardware được xác nhận.')
        if active[0]=='sim-v3-baselines':self.sim_note.setText('V3 · 8 lượt clear floor: constant / guided × tuyến ±5° × 2 lần. Estimator causal chỉ wheel+IMU, initial pose theo metadata scenario; không đọc GT để điều khiển. Task 14 s, residual zero, không actor hoặc optimizer.')
    def run(self,action):
        if self.hardware_busy() or self.external_busy:return
        try:
            if self.runner.start(action):self.sections.setCurrentIndex(3 if action.startswith('sim-') else 1);self.progress.setValue(0);self.log.clear();self.output_tabs.setCurrentIndex(2);self.next.setText('Đang chạy '+JOBS[action][0]+' · đợi process đóng và manifest được kiểm');self.refresh()
        except (ValueError,OSError) as exc:self.next.setText('Chưa chạy: '+str(exc))
    def handle(self,event):
        if event.get('message'):self.log.appendPlainText(event['message'])
        if event.get('message') and (self.runner.action or '').startswith('sim-'):
            self.sim_log.appendPlainText(event['message'])
            if self.runner.busy and event.get('state')!='closed':
                self.sim_next.setText('Đang chạy '+JOBS[self.runner.action][0]+' · '+event['message'])
                if event.get('progress') is None:self.sim_progress.setRange(0,0)
        if event.get('progress') is not None:self.progress.setValue(int(event['progress']*100))
        if event.get('progress') is not None and (self.runner.action or '').startswith('sim-'):
            self.sim_progress.setRange(0,100)
            self.sim_progress.setValue(int(event['progress']*100))
        if event.get('state')=='progress' and event.get('action')=='factory-td3' and event.get('message'):
            self.next.setText('FACTORY · '+event['message']+' · chỉ mô phỏng; chờ process đóng và kiểm manifest.')
        if event.get('result'):
            body=json.dumps(event['result'],ensure_ascii=False,indent=2)
            self.results.setPlainText(body)
            if (event.get('action') or '').startswith('sim-'):self.sim_log.appendPlainText(body)
        if event.get('state')=='closed':
            self.reload()
            self.output_tabs.setCurrentIndex(1)
            if event.get('returncode')!=0:self.next.setText('Job lỗi/hủy; artifact được giữ. Đọc log và sửa đúng nguyên nhân; không tự retry hoặc coi là pass.')
        self.refresh()
    def job_closed(self):
        if self.closing:self.all_closed.emit()
    def show_sim_result(self,action):
        state=self.states.get(action,{})
        if not state.get('path'):
            self.sim_log.setPlainText(state.get('error','Chưa có artifact'));return
        names={'sim-baselines':'baseline_result.json','sim-train':'training_result.json','sim-evaluate':'evaluation_result.json'}
        names.update({'sim-v2-baselines':'baseline_result.json','sim-v2-train':'training_result.json','sim-v2-evaluate':'evaluation_result.json'})
        names.update({'sim-bias-clear':'evaluation_result.json','sim-guidance-contract':'guidance_result.json'})
        names.update({'sim-v3-baselines':'evaluation_result.json'})
        try:self.sim_log.setPlainText(str(state['path'])+'\n'+(Path(state['path'])/names[action]).read_text())
        except OSError as exc:self.sim_log.setPlainText(str(exc))
    def request_close(self):
        self.closing=True;self.runner.cancel();self.refresh()
    def show_result(self,row,column):
        self.sections.setCurrentIndex(1)
        action=list(JOBS)[row];state=self.states.get(action,{})
        if not state.get('path'):self.results.setPlainText(state.get('error','Chưa có dữ liệu'));return
        path=Path(state['path']);names={'validate':'validation.json','train-td3':'training_result.json','audit-td3':'audit.json','train-ppo':'training_result.json',
            'compare':'comparison.json','ros-fixture':'ros_result.json','gazebo-fixture':'gazebo_result.json','factory-td3':'factory_result.json','sysid':'sysid_result.json',
            'sim-baselines':'baseline_result.json','sim-train':'training_result.json','sim-evaluate':'evaluation_result.json'}
        names.update({'sim-v2-baselines':'baseline_result.json','sim-v2-train':'training_result.json','sim-v2-evaluate':'evaluation_result.json'})
        names.update({'sim-bias-clear':'evaluation_result.json','sim-guidance-contract':'guidance_result.json'})
        names.update({'sim-v3-baselines':'evaluation_result.json'})
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
