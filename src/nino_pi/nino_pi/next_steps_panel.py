"""Concrete operational outline; selecting a step never starts a job."""
from html import escape
import json
from pathlib import Path
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q


class NextStepsPanel(Q.QWidget):
    collectionRequested=C.pyqtSignal(str)
    def __init__(self,parent=None,workstream=None):
        super().__init__(parent);self.steps=[];self.workstream=workstream;self.draft=None
        layout=Q.QVBoxLayout(self)
        title=Q.QLabel('VIỆC CẦN LÀM · chọn từng bước để xem thao tác và dữ liệu')
        title.setWordWrap(True);title.setStyleSheet('font-size:20px;font-weight:700');layout.addWidget(title)
        self.branch=Q.QComboBox();self.branch.addItem('Nhánh Sim offline · chuẩn bị, chưa chạy batch','sim_offline_preparation')
        self.branch.addItem('Nhánh robot thật · reference / readiness','hardware');layout.addWidget(self.branch)
        current=Q.QLabel('SIM: eval 10/10 đã đóng; classical tốt hơn 6/6 lượt TD3 trên cả ba grids.\n'
            'Coverage V1 dừng ở tick đầu vì thiếu metadata; correction offline, chưa budget mới. Không cần đợi real dataset.')
        current.setWordWrap(True);current.setStyleSheet('color:#72ded0;padding:8px;background:#173743;');layout.addWidget(current)
        self.current=current
        split=Q.QSplitter(C.Qt.Horizontal);layout.addWidget(split,1)
        self.list=Q.QListWidget();self.list.setMinimumWidth(245);self.list.setMaximumWidth(345)
        self.list.setWordWrap(True);self.list.setSpacing(5);split.addWidget(self.list)
        self.detail=Q.QTextBrowser();self.detail.setOpenExternalLinks(False);self.detail.setMinimumHeight(475);split.addWidget(self.detail)
        self.detail.setStyleSheet('background-color:#142332;color:#e7edf7;')
        split.setStretchFactor(0,3);split.setStretchFactor(1,7)
        buttons=Q.QHBoxLayout()
        self.open_collection=Q.QPushButton('Mở Studio · chỉ chuyển trang')
        self.open_collection.clicked.connect(lambda:self.collectionRequested.emit(self.steps[self.list.currentRow()].get('action') or 'studio'));buttons.addWidget(self.open_collection)
        self.open_document=Q.QPushButton('Mở outline đầy đủ');self.open_document.clicked.connect(self.document);buttons.addWidget(self.open_document)
        self.open_protocol=Q.QPushButton('Xem quyết định benchmark Sim')
        self.open_protocol.clicked.connect(self.protocol_document);buttons.addWidget(self.open_protocol)
        layout.insertLayout(2,buttons)
        self.note=Q.QLabel('Các bước sau là kế hoạch có điều kiện. Chọn một dòng không cấp slot, chạy training hay phát lệnh robot.')
        self.note.setWordWrap(True);layout.addWidget(self.note)
        self.list.currentRowChanged.connect(self.select)
        self.branch.currentIndexChanged.connect(self.change_branch)
        self.reload()
    def change_branch(self,index):
        self.workstream=self.branch.currentData();self.reload()
    def reload(self):
        row=max(0,self.list.currentRow());self.list.clear();self.draft=None
        try:
            plan=json.loads(Path(__file__).with_name('research_plan.json').read_text())
            v2=plan.get('sim_coverage_v2')
            if v2:
                state=v2.get('study_status','not_started')
                counts=('Chờ artifact study đóng để nghiệm thu.' if state=='running' else
                    f"Study: {v2.get('valid_td3_transitions',0)} train / {v2.get('evaluation_transitions',0)} eval hợp lệ; chưa promote." if state in ('completed','failed','cancelled') else
                    'Chưa có train/eval Gazebo V2 hoặc hardware mới.')
                self.current.setText('Eval trước V2: classical tốt hơn 6/6 điều kiện TD3 trên cả ba grids.\n'
                    f"Coverage V2: {v2.get('display_status',v2['status'])} · {v2.get('software_tests_passed',0)} software tests. "
                    'V1 đã đóng. '+counts)
            ready=plan.get('sim_drive_readiness')
            if ready:
                self.current.setText(f"Reset drive ACK + zero: {ready['gazebo_launches']}/2 launches, {ready['zero_control_ticks']} zero ticks; actor/optimizer0.\n"
                    'Tiếp thiết kế eval-only checkpoint A/B0/cổ điển cùng gate. V2 giữ đóng; chưa learned benefit hoặc hardware.')
            evaluation=plan.get('sim_ready_eval_only')
            if evaluation:
                self.current.setText(f"Eval reset-ready: {evaluation['gazebo_launches']}/6 launches, {evaluation['evaluation_transitions']} eval ticks; 0 train/optimizer.\n"
                    'A seed11 kém cổ điển về velocity RMSE trên cả ba grids, stop6/8. Giữ cổ điển cho clear known-stop; chốt benchmark trước training mới. Chưa hardware.')
            if plan.get('sim_benchmark_decision'):
                self.current.setText('Benchmark đã chốt offline: giữ cổ điển cho clear known-stop. Câu hỏi mới chỉ về gain cố định chưa biết.\n'
                    'Causal encoder baseline kiểm đại số đạt; chưa chứng minh trên Gazebo. Tiếp backend/gain=1 parity rồi baseline qualification riêng; chưa mở training.')
            if plan.get('sim_gain_context_preflight'):
                self.current.setText('Backend/context gain: gain=1 parity đã đạt offline; 4.800 callbacks motor và 840 bước wrapper fixture, 0 Gazebo/training.\n'
                    'Tiếp runner/release riêng cho draft 9 lượt baseline. Giữ cổ điển cho clear known-stop; chưa learned benefit hoặc hardware.')
            gain=plan.get('sim_gain_baseline_qualification')
            if gain:
                self.current.setText(f"Gain baseline: {gain['completed_cells']}/9 cell đã đóng; {gain['valid_ticks']}/1260 tick hợp lệ. gain=1 parity offline giữ nguyên.\n"
                    +gain['next_recommendation']+' Không mở training/hardware hoặc chạy lại budget đã đóng.')
            held=plan.get('sim_held_gain_offline')
            if held:
                self.current.setText('Gain baseline9/9 đã đóng; gain=1 parity giữ nguyên.\n'
                    f"Correction offline: {held['software_tests_passed']} tests, {held['synthetic_decisions']} quyết định synthetic, "
                    f"{held['shadow_decisions']} shadow. Gain-ID/motion benefit UNKNOWN; chưa physics/train/hardware mới. "
                    'Tiếp chẩn đoán lag/bias từ trace cũ; một correction đã đóng, không sửa-thử tiếp tự động.')
            dynamics=plan.get('sim_chain_dynamics_audit')
            if dynamics:
                self.current.setText('Dynamics từ9run đã audit:1260native rows giữ nguyên;8rawquery đầy đủ/1UNKNOWN do timestamp ambiguous.\n'
                    'Gain=1 parity và budget9/9 vẫn đóng. Ưu tiên chuẩn bị draft wheel PI Sim; chưa đổi gains, chạyphysics hoặc trainTD3 mới. '
                    'Gain-ID/motion benefit của correction hold vẫnUNKNOWN.')
            pi=plan.get('sim_pi_screen_preflight')
            if pi:
                self.current.setText('PI screen Sim: software parity đã đạt; gain=1 parity và các budget cũ giữ nguyên.\n'
                    f"{pi['software_tests_passed']} tests, 3.600 callbacks kernel và 560 transitions wrapper synthetic. "
                    'Ki0,10 giữ đúng hành vi cũ; candidate0,15 chưa có outcome Gazebo. '
                    'Tiếp chuẩn bị runner/protocol/release riêng cho tối đa4lượt/560ticks; không mởTD3 hoặc hardware.')
            runner=plan.get('sim_pi_screen_runner_preflight')
            if runner:
                self.current.setText('PI runner/protocol Sim đã kiểm offline; gain=1 parity và budget cũ vẫn giữ nguyên.\n'
                    f"{runner['software_tests_passed']} tests runner, 4cell/560decisions synthetic; không phải outcome Gazebo. "
                    'Tiếp review/release riêng cho screen Ki0,10/0,15 tối đa4lượt/560ticks. '
                    'Chưa cấp slot/chạy physics, mởTD3 hoặc hardware.')
            screen=plan.get('sim_pi_screen')
            if screen:
                self.current.setText('PI screen Gazebo đã đóng4/4,560native ticks; gain=1 parity giữ nguyên.\n'
                    'Ki0,15 giảm native velocity RMSE21,7%/19,5%; hai GT grids cùng chiều. '
                    'Path RMSE cao hơn nhưng <0,46mm trong screen này. Candidate chưa promote; '
                    'tiếp protocol validation riêng ở stop6s, chưa cấp budget hoặc trainTD3/hardware.')
            validation=plan.get('sim_pi_stop_validation_preflight')
            if validation:
                self.current.setText('PI screen8s đã đóng4/4; gain=1 parity giữ nguyên. Candidate chưa promote.\n'
                    f"Validation stop6s đã chuẩn bị: {validation['software_tests_passed']} tests, "
                    '4cell/560decisions synthetic, không là outcome Gazebo. '
                    'Tiếp review/release riêng tối đa4lượt/560ticks; hiện0slot, chưa physics/trainTD3/hardware.')
            training=plan.get('td3_training_evidence')
            if training:
                self.current.setText(
                    f"TD3 A seed{training['seed']}: {training['training_transitions']:,} train transitions; "
                    f"{training['critic_updates']} critic/{training['actor_updates']} actor updates. "
                    'Pilot rất ngắn, chưa đủ kết luận TD3; gain=1 parity đã có.\n'
                    'Tiếp chốt contract/ngân sách pilot TD3 với baseline Ki0,10 frozen. '
                    'Validation Ki0,15 là nhánh riêng, chưa release và không bắt buộc để train với baseline cũ.')
            from .studio_training_evidence import completed_training
            completed=completed_training(plan)
            if completed:
                self.current.setText(
                    f"TD3 Studio seed{completed['seed']}: {completed['training_transitions']:,} transitions; "
                    f"{completed['critic_updates']:,} critic/{completed['actor_updates']:,} actor updates. "
                    'Pilot20k hoàn tất, gain=1 parity giữ nguyên; chưa chứng minh hơn classical.\n'
                    'Tiếp review/chốt continuation10k cùng profile. Chưa chạy thêm, chưa promote hoặc hardware.')
            from .studio_training_evidence import continuation_summary,scientific_assessment
            continuation=continuation_summary(plan)
            if continuation:self.current.setText(self.current.text().split('\n')[0]+'\n'+continuation)
            assessment=scientific_assessment(plan)
            if assessment:self.current.setText(assessment['summary'])
            active=self.workstream or plan.get('active_workstream','hardware')
            self.branch.blockSignals(True);self.branch.setCurrentIndex(max(0,self.branch.findData(active)));self.branch.blockSignals(False)
            self.draft=None
            if active=='sim_offline_preparation':
                import hashlib
                from nino_rl.prestop_authority_draft import load
                record=plan['sim_prestop_authority_draft'];path=Path(record['config'])
                if hashlib.sha256(path.read_bytes()).hexdigest()!=record['config_sha256']:raise ValueError('Sim draft config hash changed')
                self.draft=load(path)
                self.current.setText(self.current.text()+'\nSIM OFFLINE · draft tail −0,005 / 0 / +0,005 m/s trước stop; 12 lượt đề xuất / 0 được cấp. Không cần Pi cho bước này.')
                self.steps=list(plan['sim_next_steps'])
                self.note.setText('Nhánh đang chọn: chuẩn bị Sim offline. Chọn dòng hoặc mở draft không chạy batch, không cấp slot; phần robot thật nằm ở nhánh riêng.')
                self.open_protocol.setText('Xem draft Sim · chưa release')
            else:
                self.steps=list(plan['next_steps'])
                self.note.setText('Các bước robot thật cần reference/readiness và protocol riêng; chọn một dòng không phát lệnh hoặc cấp slot.')
                self.open_protocol.setText('Xem quyết định benchmark Sim đã đóng')
            if continuation and self.steps and not assessment:
                self.steps[0]=dict(self.steps[0],status='BASELINE TRƯỚC LEARNER · '+continuation)
            for step in self.steps:
                item=Q.QListWidgetItem(step['id']+' · '+step['name']+'\n'+step['status'])
                height=self.list.fontMetrics().boundingRect(C.QRect(0,0,250,1000),C.Qt.TextWordWrap,item.text()).height()+20
                item.setSizeHint(C.QSize(280,max(66,height)));item.setToolTip(item.text());self.list.addItem(item)
            self.list.setCurrentRow(min(row,len(self.steps)-1))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.steps=[];self.list.clear();self.current.setText('CHƯA XÁC MINH · hồ sơ hiện tại không hợp lệ; không giữ trạng thái thành công cũ.')
            self.detail.setPlainText('Chưa đọc được outline: '+str(exc));self.open_collection.setEnabled(False)
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
        try:path=repository()/('docs/NINO_SIM_PRESTOP_AUTHORITY_DRAFT_2026-11-08.md' if self.draft else 'docs/NINO_CLASSICAL_BASELINE_HANDOFF_2026-11-07.md')
        except (OSError,ValueError) as exc:self.note.setText(str(exc));return
        if path.is_file():G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(path)))
        else:self.note.setText('Không có outline tại '+str(path))
    def protocol_document(self):
        from .research_jobs import repository
        try:path=repository()/('docs/NINO_SIM_PRESTOP_AUTHORITY_DRAFT_2026-11-08.md' if self.draft else 'docs/NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md')
        except (OSError,ValueError) as exc:self.note.setText(str(exc));return
        if path.is_file():G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(path)))
        else:self.note.setText('Không có protocol tại '+str(path))
