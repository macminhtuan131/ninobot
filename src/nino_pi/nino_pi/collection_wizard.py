"""Presentation for the existing fixed collection controller. No SSH/ROS here."""
from pathlib import Path
import time
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q

PHASES=('Chọn phiên thu','Chuẩn bị Pi','Điều kiện & video','Thu và thử','Kiểm & quan sát','Nhận dữ liệu')
TITLES=('Bạn muốn thu dữ liệu nào?','Kết nối và kiểm thiết bị','Ghi điều kiện của lượt thử',
        'Ghi dữ liệu trước, yêu cầu tiến sau','Kiểm gói dữ liệu và ghi điều bạn thấy','Tải gói dữ liệu về laptop')


def text(value,style=None):
    label=Q.QLabel(value);label.setWordWrap(True)
    if style:label.setStyleSheet(style)
    return label


class CollectionWizard(C.QObject):
    def __init__(self,w,steps):
        super().__init__(w);self.w=w;self.selected=False;self.last_recommended=0;self.command=None;self.destination=None
        root=Q.QVBoxLayout(w);root.setContentsMargins(12,10,12,10);root.setSpacing(8)
        self.title=text('THU DỮ LIỆU · đi lần lượt từng bước','font-size:21px;font-weight:700;');root.addWidget(self.title)
        w.next=text('Chọn loại phiên, sau đó bấm Tiếp tục.');w.next.setStyleSheet('background:#173d4c;border:1px solid #398895;border-radius:7px;padding:9px;color:#baf3e8;');root.addWidget(w.next)
        body=Q.QHBoxLayout();root.addLayout(body,1)
        self.navigation=Q.QListWidget();self.navigation.setMinimumWidth(210);self.navigation.setMaximumWidth(230)
        self.navigation.setSizePolicy(Q.QSizePolicy.Preferred,Q.QSizePolicy.Ignored)
        self.navigation.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
        self.navigation.setStyleSheet('QListWidget {background:#111c2b;border:1px solid #2e3c52;} QListWidget::item {padding:5px;} QListWidget::item:selected {background:#215b65;color:#e7fff8;}')
        self.navigation.setSpacing(5);body.addWidget(self.navigation,2)
        for i,name in enumerate(PHASES):
            item=Q.QListWidgetItem(f'{i+1:02d}  {name}');item.setSizeHint(C.QSize(185,44));self.navigation.addItem(item)
        self.pages=Q.QStackedWidget();self.pages.setMinimumHeight(0)
        self.pages.setSizePolicy(Q.QSizePolicy.Expanding,Q.QSizePolicy.Ignored)
        body.addWidget(self.pages,7);self.layouts=[]
        for heading in TITLES:
            page=Q.QWidget();layout=Q.QVBoxLayout(page);layout.setContentsMargins(10,4,4,4);layout.setSpacing(10)
            layout.addWidget(text(heading,'font-size:18px;font-weight:700;'));self.layouts.append(layout)
            scroll=Q.QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(Q.QFrame.NoFrame)
            scroll.setWidget(page);scroll.setMinimumHeight(0);self.pages.addWidget(scroll)
        # Keep controller action widgets separate from the single visible action.
        w.buttons={}
        for job,label in steps:
            b=Q.QPushButton(label,w);b.hide();b.clicked.connect(lambda checked=False,j=job:w.start(j));w.buttons[job]=b
        p=self.layouts[0];w.mode=Q.QComboBox()
        for label,key in [('Tiến–dừng có video · 1 lượt','diagnostic'),('Đứng yên · 60 giây · không enable','stationary'),('Độ lặp / SysID / vật cản · chưa mở protocol','future')]:w.mode.addItem(label,key)
        p.addWidget(w.mode);self.profile_summary=text('');p.addWidget(self.profile_summary)
        p.addWidget(text('Gói dữ liệu: IMU, feedback/status hai bánh, command có thật, LiDAR/STOP, TF và metadata.\n'
                        'Phiên tiến–dừng cần video bánh/thân/mốc sàn để đối chiếu chuyển động.'))
        p.addWidget(text('Chuẩn bị IP Pi và SSH key ở thanh kết nối phía trên. Các bước thu dùng firmware RC hiện có.','color:#a6b6cc;'));p.addStretch()
        p=self.layouts[1];self.device_status=text('Chưa kiểm thiết bị.');p.addWidget(self.device_status)
        p.addWidget(text('Nút chính lần lượt chuẩn bị bộ thu, kết nối Agent/cảm biến và kiểm dữ liệu.\n'
                        'Nếu driver đã chạy sẵn, sau khi chuẩn bị bộ thu bạn có thể kiểm trực tiếp.'))
        self.inventory_now=Q.QPushButton('Driver đã chạy → kiểm thiết bị ngay');self.inventory_now.clicked.connect(lambda:w.buttons['inventory'].click());p.addWidget(self.inventory_now)
        p.addWidget(text('Chỉ có topic trong graph chưa đủ; báo cáo inventory cần có mẫu. Bước này chưa phát lệnh tiến.','color:#a6b6cc;'));p.addStretch()
        p=self.layouts[2];form=Q.QFormLayout();form.setFieldGrowthPolicy(Q.QFormLayout.AllNonFixedFieldsGrow)
        w.pose=Q.QLineEdit();w.pose.setPlaceholderText('VD: theo đường gạch; caster unknown')
        w.floor=Q.QLineEdit();w.floor.setPlaceholderText('VD: sàn gạch, cùng tải; pin chưa đo')
        w.video=Q.QLineEdit();w.video.setPlaceholderText('Tên video/máy quay + mốc đồng bộ; ghi rõ nếu chưa định lượng')
        form.addRow('Pose / caster',w.pose);form.addRow('Sàn / tải / pin',w.floor);form.addRow('Video / đồng bộ',w.video);p.addLayout(form)
        w.checks={};checks=Q.QGridLayout()
        for i,(key,label) in enumerate([('rc_auto','RC đang AUTO'),('clear_floor','Vùng thử trống'),('same_load','Giữ cùng sàn / tải'),('video_ready','Đã chuẩn bị quay video')]):
            box=Q.QCheckBox(label);w.checks[key]=box;box.toggled.connect(w.refresh);checks.addWidget(box,i//2,i%2)
        p.addLayout(checks)
        w.profile=text('Profile: 0,05 m/s · ramp 0,10 m/s² · tiến 2 s · zero/disable · thu 60 s.');p.addWidget(w.profile)
        self.conditions_hint=text('');p.addWidget(self.conditions_hint)
        p.addWidget(text('Có thể ghi unknown cho caster/số đo chưa biết. Các ô xác nhận là thông tin bạn quan sát, không được tự đánh dấu từ encoder.','color:#a6b6cc;'));p.addStretch()
        p=self.layouts[3];self.record_state=text('Recorder chưa chạy.');p.addWidget(self.record_state)
        w.bar=Q.QProgressBar();w.bar.setRange(0,600);w.bar.setFormat('Chưa thu');p.addWidget(w.bar)
        self.sample_counts=text('Mẫu ghi vào bag: chưa có.');p.addWidget(self.sample_counts)
        w.motion_confirm=Q.QCheckBox('Tôi đang quan sát xe; vùng thử vẫn trống và RC vẫn AUTO')
        w.motion_confirm.toggled.connect(w.refresh);p.addWidget(w.motion_confirm)
        p.addWidget(text('Bấm bắt đầu thu để ghi các mẫu ban đầu. Sau đó kiểm vùng thử và bấm riêng nút yêu cầu tiến.\n'
                        'Khi lệnh thử kết thúc, chờ đủ thời gian thu và recorder đóng; giữ Pi có nguồn.'))
        p.addWidget(text('Nút hủy dừng các tác vụ của GUI; khi cần dừng khẩn cấp, dùng nút vật lý.','color:#a6b6cc;'));p.addStretch()
        p=self.layouts[4];w.quality=Q.QPlainTextEdit();w.quality.setReadOnly(True);w.quality.setMaximumHeight(145)
        w.quality.setPlainText('Chưa kiểm phiên mới. Integrity/hash không chứng minh thân xe tiến.');p.addWidget(w.quality)
        form=Q.QFormLayout();w.outcome=Q.QComboBox()
        for title,key in [('Chưa quan sát đủ','not_observed'),('Xe tiến rồi tự dừng','moved_stopped'),('Xe không tiến','no_motion'),('Có can thiệp / bất thường','intervention')]:w.outcome.addItem(title,key)
        w.observation=Q.QLineEdit();w.observation.setPlaceholderText('Xe tiến/dừng ra sao, lệch/giật, can thiệp, video nào?')
        form.addRow('Quan sát thực',w.outcome);form.addRow('Ghi chú',w.observation);p.addLayout(form)
        p.addWidget(text('Kiểm dữ liệu trước, sau đó lưu quan sát kể cả “không tiến” hoặc “chưa rõ”. Giữ nguyên các phiên lỗi để đánh giá.','color:#a6b6cc;'));p.addStretch()
        p=self.layouts[5];self.summary=text('Chưa có gói dữ liệu để tải.');p.addWidget(self.summary)
        w.local_directory=Q.QLineEdit();w.local_directory.setReadOnly(True);w.local_directory.setPlaceholderText('Thư mục laptop xuất hiện sau khi tải thành công');p.addWidget(w.local_directory)
        p.addWidget(text('Gói tải gồm raw session và review nếu có. Video trên điện thoại/camera cần copy riêng và ghép đúng session/mốc đồng bộ.'))
        p.addWidget(text('Bước tiếp theo sau khi tải: đối chiếu video với command/feedback. Review kết quả trước khi mở đợt đo mới.','color:#72ded0;'));p.addStretch()
        self.session_path=Q.QLineEdit();self.session_path.setReadOnly(True);self.session_path.setPlaceholderText('Phiên trên Pi: chưa bắt đầu thu');root.addWidget(self.session_path)
        footer=Q.QHBoxLayout();self.previous=Q.QPushButton('← Xem bước trước');self.previous.clicked.connect(lambda:self.navigation.setCurrentRow(max(0,self.pages.currentIndex()-1)));footer.addWidget(self.previous)
        self.primary=Q.QPushButton('Tiếp tục → Chuẩn bị Pi');self.primary.setObjectName('primary');self.primary.setMinimumHeight(45);self.primary.clicked.connect(self.activate);footer.addWidget(self.primary,1)
        w.stop=Q.QPushButton('Hủy tác vụ');w.stop.setObjectName('danger');w.stop.clicked.connect(w.cancel);footer.addWidget(w.stop);root.addLayout(footer)
        self.details_toggle=Q.QToolButton();self.details_toggle.setText('▶ Chi tiết / log khi có lỗi');self.details_toggle.setCheckable(True);root.addWidget(self.details_toggle)
        self.details=Q.QWidget();detail_layout=Q.QVBoxLayout(self.details);detail_layout.setContentsMargins(0,0,0,0)
        w.table=Q.QTableWidget(len(steps),3);w.table.setHorizontalHeaderLabels(['Tác vụ','Trạng thái','Kết quả'])
        w.table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers);w.table.verticalHeader().hide();w.table.setMaximumHeight(180)
        w.table.horizontalHeader().setSectionResizeMode(2,Q.QHeaderView.Stretch)
        for i,(job,label) in enumerate(steps):
            for col,value in enumerate((label,'Chưa làm','')):w.table.setItem(i,col,Q.QTableWidgetItem(value))
        detail_layout.addWidget(w.table);w.output=Q.QPlainTextEdit();w.output.setReadOnly(True);w.output.setMaximumHeight(110);w.output.document().setMaximumBlockCount(1000);detail_layout.addWidget(w.output)
        root.addWidget(self.details);self.details.hide();self.details_toggle.toggled.connect(self.details.setVisible)
        # Select the first page before connecting: the controller has not yet
        # assigned its `wizard` attribute while this constructor is running.
        self.navigation.setCurrentRow(0);self.navigation.currentRowChanged.connect(self.show_page)
        w.mode.currentIndexChanged.connect(w.refresh)
        for edit in (w.pose,w.floor,w.video,w.observation):edit.textChanged.connect(w.refresh)
        w.outcome.currentIndexChanged.connect(w.refresh)

    def show_page(self,index):
        if index>=0:self.pages.setCurrentIndex(index)
        self.w.refresh()

    def activate(self):
        if not self.primary.isEnabled():return
        if self.command:
            self.w.buttons[self.command].click()
        elif self.destination is not None:
            self.selected=True;self.navigation.setCurrentRow(self.destination)
        elif self.w.local_directory.text():
            path=Path(self.w.local_directory.text())
            if path.is_dir():G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(path)))

    def refresh(self):
        w=self.w;jobs=w.runner.active_jobs;kind=w.mode.currentData();motion='run-trial' in jobs
        recording=any(k in jobs for k in ('stationary','record-diagnostic'))
        if w.done.get('fetch') or w.done.get('observation'):recommended=5
        elif w.record_closed:recommended=4
        elif recording or motion or w.diagnostic_used:recommended=3
        elif w.done.get('inventory'):recommended=2
        elif self.selected or w.done.get('deploy') or jobs:recommended=1
        else:recommended=0
        if recommended!=self.last_recommended:
            self.last_recommended=recommended;self.navigation.setCurrentRow(recommended)
        index=self.pages.currentIndex();self.title.setText(f'BƯỚC {index+1}/6 · {PHASES[index].upper()}')
        done=[self.selected,w.done.get('inventory'),w.done.get('start-stack') if kind=='diagnostic' else w.done.get('inventory'),w.record_closed,w.done.get('observation'),w.done.get('fetch')]
        for i,label in enumerate(PHASES):self.navigation.item(i).setText(('✓ ' if done[i] else f'{i+1:02d}  ')+label)
        self.profile_summary.setText('Tiến 0,05 m/s · ramp 0,10 m/s² · source 2 s · zero/disable · bag 60 s.' if kind=='diagnostic' else
                                    'Chỉ ghi dữ liệu đứng yên trong 60 s; không enable hoặc phát vận tốc.' if kind=='stationary' else 'Phiên này chưa có protocol được mở; xem lộ trình trước.')
        w.profile.setText('Profile: chỉ ghi đứng yên 60 s; không enable hoặc phát vận tốc.' if kind=='stationary' else
                          'Profile: 0,05 m/s · ramp 0,10 m/s² · tiến 2 s · zero/disable · thu 60 s.')
        for box in w.checks.values():box.setVisible(kind=='diagnostic')
        w.video.setEnabled(kind=='diagnostic' and not w.capture_started)
        self.device_status.setText('Đã có báo cáo inventory; freshness/owner vẫn được kiểm lại ở đường thử.' if w.done.get('inventory') else 'Đang chuẩn bị/kết nối thiết bị.' if jobs else 'Chưa kiểm thiết bị.')
        self.inventory_now.setEnabled(w.buttons['inventory'].isEnabled())
        w.motion_confirm.setVisible(kind=='diagnostic');w.motion_confirm.setEnabled(recording and w.record_ready and not w.diagnostic_used and not w.stopping)
        notes_missing=[name for name,field in [('pose/caster',w.pose),('sàn/tải',w.floor)] if not field.text().strip()]
        if kind=='diagnostic':
            notes_missing += ([] if w.video.text().strip() else ['video / mốc đồng bộ'])
            notes_missing += [box.text() for box in w.checks.values() if not box.isChecked()]
        self.conditions_hint.setText('Còn thiếu: '+', '.join(notes_missing) if notes_missing else 'Đã điền điều kiện; có thể bấm nút chính.')
        self.record_state.setText('Recorder đã đóng. Có thể chuyển sang kiểm dữ liệu.' if w.record_closed else
            'Đang phát profile thử; quan sát xe. Recorder tiếp tục sau khi lệnh thử xong.' if motion else
            'Đã yêu cầu tiến/zero/disable; chờ recorder đóng.' if recording and w.diagnostic_used else
            'Đã có mẫu đầu; xác nhận lại vùng thử rồi bấm nút tiến riêng.' if recording and w.record_ready and kind=='diagnostic' else
            'Đang thu đứng yên; chờ recorder đóng.' if recording and kind=='stationary' else
            'Đang chờ mẫu ghi vào bag.' if recording else 'Recorder chưa chạy hoặc chưa có xác nhận đóng.')
        self.command=None;self.destination=None;label='Chờ bước trước';hint='';enabled=False
        if index==0:
            label='Tiếp tục → Chuẩn bị Pi';self.destination=1;enabled=kind!='future';hint='Chọn phiên phù hợp. Bấm Tiếp tục chỉ chuyển trang.'
        elif index==1:
            job='deploy' if not w.done.get('deploy') else 'connect-sensors' if not w.done.get('connect-sensors') else 'inventory'
            if w.done.get('inventory'):label='Tiếp tục → Điều kiện thu';self.destination=2;enabled=True
            else:self.command=job;label={'deploy':'Chuẩn bị bộ thu trên Pi','connect-sensors':'Kết nối Agent / cảm biến','inventory':'Kiểm mẫu dữ liệu và thiết bị'}[job];enabled=w.buttons[job].isEnabled()
            hint='Bấm nút chính theo thứ tự; nếu có driver sẵn có thể kiểm trực tiếp bằng nút trong trang.'
        elif index==2:
            notes=bool(w.pose.text().strip() and w.floor.text().strip())
            conditions=notes and bool(w.video.text().strip()) and all(b.isChecked() for b in w.checks.values())
            if kind=='stationary':label='Tiếp tục → Thu đứng yên';self.destination=3;enabled=notes and bool(w.done.get('inventory'))
            elif kind=='diagnostic' and w.done.get('start-stack'):label='Tiếp tục → Thu và thử';self.destination=3;enabled=conditions
            elif kind=='diagnostic':label='Khởi động đường lệnh ZERO';self.command='start-stack';enabled=conditions and w.buttons['start-stack'].isEnabled()
            hint='Còn thiếu: '+', '.join(notes_missing) if notes_missing else 'Điều kiện đã điền. Bấm nút chính để tiếp tục; đường lệnh ZERO chưa yêu cầu tiến.'
        elif index==3:
            if w.record_closed:label='Tiếp tục → Kiểm dữ liệu';self.destination=4;enabled=True
            elif recording and kind=='diagnostic' and not w.diagnostic_used:
                label='YÊU CẦU TIẾN 0,05 m/s · 2 s';self.command='run-trial';enabled=w.buttons['run-trial'].isEnabled()
            elif recording:label='Đang thu / chờ đóng recorder…'
            elif not w.diagnostic_used:label='Bắt đầu thu 60 giây';self.command='record-diagnostic';enabled=w.buttons['record-diagnostic'].isEnabled()
            else:label='Lượt thử đã dùng · đợi review'
            hint='Bắt đầu thu không phát lệnh tiến. Nút tiến cần recorder có mẫu, cập nhật trạng thái và xác nhận của bạn.'
            if recording and not w.diagnostic_used and kind=='diagnostic':
                if w.remaining is not None and w.remaining<33:
                    hint='Đã qua cửa sổ bắt đầu trial. Chờ recorder đóng, giữ phiên để review; không tiến muộn hoặc chạy lại.'
                elif not w.demo and time.monotonic()-w.ready_received>2.:
                    hint='Đang chờ cập nhật mới từ recorder; chưa cho phép yêu cầu tiến.'
                elif not w.motion_confirm.isChecked():hint='Đã có mẫu. Kiểm lại vùng thử/RC, đánh dấu ô xác nhận rồi bấm nút tiến.'
            elif w.diagnostic_used and not recording and not motion and not w.record_closed:
                hint='Lượt diagnostic của protocol này đã dùng/đóng. Cần review ledger và mở protocol riêng trước đợt mới; không reset hoặc chạy lại.'
        elif index==4:
            if w.done.get('observation'):label='Tiếp tục → Nhận dữ liệu';self.destination=5;enabled=True
            else:
                self.command='observation' if w.done.get('review') else 'review'
                label='Lưu quan sát thực tế' if self.command=='observation' else 'Kiểm integrity / metadata / hash'
                enabled=w.buttons[self.command].isEnabled()
            hint='QC trước, sau đó ghi outcome và nhận xét thật. Phiên lỗi vẫn được giữ để kiểm.'
        elif index==5:
            if not w.done.get('fetch'):label='Tải gói dữ liệu về laptop';self.command='fetch';enabled=w.buttons['fetch'].isEnabled()
            else:label='Mở thư mục dữ liệu' if w.local_directory.text() else 'Phiên demo hoàn tất · không có file thật';enabled=bool(w.local_directory.text())
            hint='Tải xong cần ghép video đúng session và đánh giá trước khi mở lượt mới.'
        locked=w.external_busy or w.closing or w.stopping
        self.primary.setText(label);self.primary.setEnabled(bool(enabled and not locked));self.previous.setEnabled(index>0)
        prefix='DEMO · không có dữ liệu thật. ' if w.demo else ''
        if w.stopping:hint='Đang đóng trial → recorder → stack. Chờ các process đóng; giữ Pi có nguồn.'
        elif w.errors:hint='Có lỗi: '+' '.join(str(next(reversed(w.errors.values()))).split())[:200]+' · xem Chi tiết/log. Giữ dữ liệu; không tự chạy lại lượt.'
        elif jobs and self.command in jobs:hint='Đang thực hiện '+self.command+'; chờ kết quả, không bấm lặp.'
        w.next.setText(prefix+hint)
        if w.done.get('fetch'):
            self.summary.setText('Đã tải gói session và review. Video cần gắn riêng; tiếp theo đối chiếu body/wheel với lệnh.' if not w.demo else 'Demo hoàn tất; không tạo bag hoặc dataset robot.')
        elif w.record_closed:self.summary.setText('Recorder đã đóng; gói dữ liệu có thể tải. QC/quan sát là phần đánh giá riêng.')
