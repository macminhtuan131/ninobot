"""Qt collection panel; all actions go to the Pi bridge, never a local ROS publisher."""
from PyQt5 import QtCore, QtWidgets as Q
from .data_workflow import MODES
from .data_quality import assess_capture


class DataPanel(Q.QWidget):
    def __init__(self, send, demo=False, parent=None):
        super().__init__(parent)
        self.send, self.demo = send, demo
        self.supported = False
        self.capture = {"active": False, "ready": False}
        self.status = {"prepared": False, "phase": "idle", "used": False, "problems": []}
        self.authority_state = None
        self.ours = self.fresh = False
        self.direction = None
        self.observation_saved = False
        self.setStyleSheet("QPushButton { padding:6px 10px; font-size:12px; } QGroupBox { padding-top:10px; } QLineEdit { padding:5px; }")
        root = Q.QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 8)
        root.setSpacing(6)
        self.mapping = Q.QLabel("TBS → Nino: A = ROS/RC · E = ARM/DISARM · F = STOP có khóa · cần lái = v/ω.\n"
                                 "Mode 1–4 và FM0–FM8 là cấu hình transmitter; chưa có ánh xạ riêng sang Nino.")
        self.mapping.setWordWrap(True)
        root.addWidget(self.mapping)
        top = Q.QHBoxLayout()
        self.mode = Q.QComboBox()
        for name, text in MODES.items():
            self.mode.addItem(text, name)
        self.prepare = Q.QPushButton("Chuẩn bị đường lệnh · zero")
        self.prepare.clicked.connect(lambda: self.send({"action": "prepare_data"}))
        self.reset_gate = Q.QPushButton("Reset STOP tầng Pi")
        self.reset_gate.clicked.connect(lambda: self.send({"action": "reset_gate"}))
        top.addWidget(self.mode, 1)
        top.addWidget(self.prepare)
        top.addWidget(self.reset_gate)
        root.addLayout(top)
        form = Q.QFormLayout()
        self.pose = Q.QLineEdit()
        self.pose.setPlaceholderText("Hướng xe / vị trí đầu / hướng caster; chưa biết ghi unknown")
        self.floor = Q.QLineEdit()
        self.floor.setPlaceholderText("Vùng sàn, tải, thay đổi từ phiên trước; chưa biết ghi unknown")
        form.addRow("Pose / caster", self.pose)
        form.addRow("Sàn / tải", self.floor)
        root.addLayout(form)
        confirmations = Q.QHBoxLayout()
        self.clear = Q.QCheckBox("Vùng thử trống; không người / dây sát xe")
        self.parameters = Q.QCheckBox("Đã chọn profile và sẵn sàng dừng vật lý")
        confirmations.addWidget(self.clear)
        confirmations.addWidget(self.parameters)
        root.addLayout(confirmations)
        bar = Q.QHBoxLayout()
        self.record = Q.QPushButton("Bắt đầu thu · 60 s")
        self.record.setObjectName("primary")
        self.record.clicked.connect(self.start_record)
        self.run = Q.QPushButton("Chạy 1 thao tác đã chọn")
        self.run.clicked.connect(self.start_workflow)
        self.stop = Q.QPushButton("Hủy thao tác / kết thúc thu sớm")
        self.stop.clicked.connect(self.stop_capture)
        bar.addWidget(self.record)
        bar.addWidget(self.run)
        bar.addWidget(self.stop)
        root.addLayout(bar)
        self.progress = Q.QProgressBar()
        self.progress.setRange(0, 600)
        self.progress.setValue(0)
        self.progress.setFormat("Chưa thu")
        root.addWidget(self.progress)
        self.record_state = Q.QLabel("Chưa có phiên. Ghi dữ liệu không tự ARM hoặc phát vận tốc.")
        self.record_state.setWordWrap(True)
        self.record_state.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        root.addWidget(self.record_state)
        self.quality = Q.QLabel("Chất lượng: chưa có kết quả đóng phiên. Xem tiêu chí ở tab Tiến độ.")
        self.quality.setWordWrap(True)
        root.addWidget(self.quality)
        self.readiness = Q.QLabel("Chờ kết nối bridge và trạng thái firmware.")
        self.readiness.setWordWrap(True)
        root.addWidget(self.readiness)
        lower = Q.QHBoxLayout()
        manual = Q.QGroupBox("Teleop giữ nút · segment tối đa 2 s sau ARM")
        grid = Q.QGridLayout(manual)
        self.pad = {}
        for name, text, row, col, v, w in (("forward", "↑ 0,05 m/s", 0, 1, .05, 0.),
                ("left", "↶ 0,10 rad/s", 1, 0, 0., .1), ("right", "↷ 0,10 rad/s", 1, 2, 0., -.1),
                ("reverse", "↓ 0,01 m/s", 2, 1, -.01, 0.)):
            b = Q.QPushButton(text)
            b.setAutoRepeat(False)
            b.pressed.connect(lambda v=v, w=w: self.hold(v, w))
            b.released.connect(self.release)
            grid.addWidget(b, row, col)
            self.pad[name] = b
        zero = Q.QPushButton("ZERO")
        zero.clicked.connect(self.release)
        grid.addWidget(zero, 1, 1)
        lower.addWidget(manual, 3)
        review = Q.QGroupBox("Quan sát và review phiên vừa thu")
        r = Q.QVBoxLayout(review)
        self.observation = Q.QLineEdit()
        self.observation.setPlaceholderText("Ví dụ: xe không tiến / tiến rồi tự dừng / có can thiệp")
        self.observation.textChanged.connect(self.update_save)
        r.addWidget(self.observation)
        self.save = Q.QPushButton("Lưu quan sát")
        self.save.clicked.connect(self.save_observation)
        r.addWidget(self.save)
        self.reviewed = Q.QCheckBox("Đã xem kết quả / failures trước phiên mới")
        r.addWidget(self.reviewed)
        note = Q.QLabel("Encoder quay chưa chứng minh thân xe tiến.\nHash đạt chưa chứng minh chất lượng / slip.")
        note.setWordWrap(True)
        r.addWidget(note)
        lower.addWidget(review, 3)
        root.addLayout(lower)
        root.addStretch(1)
        footer = Q.QLabel("Tiến–dừng: source 0,05 m/s × 2 s; yêu cầu smoother ramp 0,10 m/s², kiểm ở readiness.\n"
                          "Chỉ ghi nhận ROS ngoài/Nav2: không khởi động navigation hoặc gửi goal. Một chuỗi thao tác mỗi phiên; không tự thử lại.")
        footer.setWordWrap(True)
        root.addWidget(footer)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.clear.toggled.connect(self.refresh)
        self.parameters.toggled.connect(self.refresh)
        self.pose.textChanged.connect(self.refresh)
        self.floor.textChanged.connect(self.refresh)
        self.reviewed.toggled.connect(self.refresh)
        self.hold_timer = QtCore.QTimer(self)
        self.hold_timer.timeout.connect(self.hold_tick)
        self.hold_timer.start(50)
        self.refresh()

    def start_record(self):
        self.observation_saved = False
        self.reviewed.setChecked(False)
        self.send({"action": "capture_start", "mode": self.mode.currentData(),
                   "metadata": {"pose_caster_note": self.pose.text().strip(), "floor_load_note": self.floor.text().strip()}})

    def start_workflow(self):
        if not self.demo:
            text = MODES[self.capture.get("mode", "stationary")] + "\nThao tác sẽ yêu cầu ARM, rồi zero/DISARM. Đây là một chuỗi mới, không dùng slot pilot cũ."
            if Q.QMessageBox.question(self, "Chạy thao tác trong phiên thu", text,
                                     Q.QMessageBox.Yes | Q.QMessageBox.No, Q.QMessageBox.No) != Q.QMessageBox.Yes:
                return
        self.send({"action": "workflow_start", "clear_confirmed": self.clear.isChecked(),
                   "parameters_confirmed": self.parameters.isChecked()})

    def hold(self, v, w):
        self.direction = (v, w)
        self.hold_tick()

    def hold_tick(self):
        if self.direction is not None:
            if not self.fresh or self.status.get("phase") != "running":
                self.release()
            else:
                self.send({"action": "hold", "v": self.direction[0], "w": self.direction[1]})

    def release(self):
        self.direction = None
        self.send({"action": "hold_release"})

    def stop_capture(self):
        self.release()
        self.send({"action": "capture_stop"})

    def save_observation(self):
        self.send({"action": "observation", "text": self.observation.text().strip()})

    def handle(self, message):
        kind = message.get("type")
        if kind == "connected":
            self.supported = message.get("data_supported", False)
        elif kind == "capture":
            self.capture = message
        elif kind == "data_status":
            self.status = message
        elif kind == "observation_saved":
            self.observation_saved = True
        self.refresh()

    def set_authority(self, state, fresh, ours):
        self.authority_state, self.fresh, self.ours = state, fresh, ours
        self.refresh()

    def refresh(self, *_):
        connected = self.supported and self.fresh
        state = self.authority_state or {}
        active = self.capture.get("active", False)
        ready = self.capture.get("ready", False)
        has_result = self.capture.get("result") is not None
        reviewed = not has_result or (self.observation_saved and self.reviewed.isChecked())
        self.mode.setEnabled(not active)
        self.pose.setEnabled(not active)
        self.floor.setEnabled(not active)
        self.prepare.setEnabled(connected and self.ours and not state.get("armed") and self.status.get("phase") not in ("arming", "running", "stopping"))
        self.reset_gate.setEnabled(self.prepare.isEnabled())
        self.prepare.setEnabled(self.prepare.isEnabled() and self.mode.currentData() in ("zero", "forward", "manual"))
        self.record.setEnabled(connected and not state.get("armed") and not active and reviewed and bool(self.pose.text().strip()) and bool(self.floor.text().strip()))
        if self.mode.currentData() in ("stationary", "external") and (self.status.get("prepared") or self.status.get("preparing")):
            self.record.setEnabled(False)
        self.stop.setEnabled(active and self.supported)
        errors = self.status.get("problems", [])
        self.run.setEnabled(connected and self.ours and active and ready and self.capture.get("remaining_s", 0) >= 12
                            and self.capture.get("mode") in ("zero", "forward", "manual") and not state.get("armed")
                            and state.get("source") == 2 and not state.get("latched") and state.get("feedback") == 3
                            and self.status.get("prepared") and self.status.get("final_zero") and not errors
                            and not self.status.get("used") and self.clear.isChecked() and self.parameters.isChecked())
        for b in self.pad.values():
            b.setEnabled(connected and self.capture.get("mode") == "manual" and self.status.get("phase") == "running" and active and ready)
        self.save.setEnabled(self.supported and not active and has_result and bool(self.observation.text().strip()))
        if active:
            remaining = self.capture.get("remaining_s", 60)
            self.progress.setValue(int((60-remaining)*10))
            self.progress.setFormat(f"Còn {remaining:.1f} s · {'đã ghi đủ kênh ban đầu' if ready else 'chờ dữ liệu / đang đóng'}")
        else:
            self.progress.setFormat("DEMO · không có dữ liệu thật" if self.demo and has_result else "Đã đóng / chưa thu")
        result = self.capture.get("result")
        if result and not active:
            grade = assess_capture(result, demo=True) if self.demo else result.get("quality_report") or assess_capture(result)
            self.quality.setText("Chất lượng: " + grade["level"] + " · " + grade["label"] + "\nCoverage/thân xe/độ lặp cần review riêng; hash không đóng P0/E1.")
        elif active:
            self.quality.setText("Đang thu / đóng: chưa có mức chất lượng cuối.")
        summary = f"\nKết quả: {result.get('status')} · hash mismatch: {result.get('hash_mismatches', 'chưa kiểm')}" if result else ""
        missing = self.capture.get("missing", [])
        self.record_state.setText(f"Recorder: {'đang chạy / đóng' if active else 'không chạy'} · workflow: {self.status.get('phase')}\n"
                                  f"{self.capture.get('directory', 'Chưa có thư mục')}" + summary +
                                  ("\nThiếu kênh: " + ", ".join(missing) if missing else ""))
        self.readiness.setText("DEMO: readiness và recorder được mô phỏng; không có bag thật." if self.demo else
                               ("Chờ bridge / trạng thái firmware; chưa xác minh readiness." if not connected else
                                "Readiness: " + "; ".join(errors[:4]) if errors else "Readiness không báo lỗi; vẫn cần xác nhận người vận hành và recorder mới."))

    def update_save(self):
        self.save.setEnabled(self.supported and not self.capture.get("active") and self.capture.get("result") is not None and bool(self.observation.text().strip()))
