"""Offline evidence dashboard. No ROS/SSH, no command or readiness mutations."""
import json
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtWidgets as Q
from .data_quality import LEVELS, assess_capture, load_catalog, quality_text
from .collection_recipes import TASK_RECIPES
from .command_panel import CommandsDialog


class ProjectPanel(Q.QWidget):
    def __init__(self, demo=False, parent=None, connection=None):
        super().__init__(parent)
        self.demo = demo
        self.catalog = {}
        self.last_capture = None
        self.selected_sources = []
        self.connection = connection
        self.selected_recipe = 'diagnostic'
        self.setMinimumHeight(600)
        root = Q.QVBoxLayout(self)
        self.banner = Q.QLabel()
        self.banner.setWordWrap(True)
        root.addWidget(self.banner)
        bar = Q.QHBoxLayout()
        self.search = Q.QLineEdit()
        self.search.setPlaceholderText("Lọc: IMU, chưa có, gyro, P0, Q2, caster…")
        self.search.textChanged.connect(self.filter_rows)
        bar.addWidget(self.search, 1)
        reload_button = Q.QPushButton("Đọc lại hồ sơ local")
        reload_button.clicked.connect(self.reload)
        bar.addWidget(reload_button)
        export = Q.QPushButton("Xuất hồ sơ JSON")
        export.clicked.connect(self.export)
        bar.addWidget(export)
        self.commands_button = Q.QPushButton("Lệnh thu / Copy")
        self.commands_button.clicked.connect(self.show_commands)
        bar.addWidget(self.commands_button)
        root.addLayout(bar)
        self.pages = Q.QTabWidget()
        self.pages.setMinimumHeight(250)
        root.addWidget(self.pages, 1)
        self.tables = []
        self.add_table("Dữ liệu cần / đã / chưa", "data", ["ID", "Dữ liệu", "Trạng thái", "Kết quả / giới hạn"],
                       ["id", "name", "status", "result"])
        self.add_table("Thông số / kết quả", "parameters", ["Thông số", "Giá trị", "Loại bằng chứng", "Giới hạn"],
                       ["name", "value", "kind", "limits"])
        self.add_table("Phiên đã review", "sessions", ["Session", "Mức", "Claim được dùng", "Outcome"],
                       ["id", "level", "claim", "outcome"])
        self.add_table("To-do", "tasks", ["ID", "Ưu tiên", "Trạng thái", "Công việc / đầu ra"],
                       ["id", "priority", "status", "action"])
        self.tables[3][2].itemDoubleClicked.connect(lambda item: self.show_commands())
        rubric = Q.QWidget()
        layout = Q.QVBoxLayout(rubric)
        self.rubric = Q.QPlainTextEdit()
        self.rubric.setReadOnly(True)
        layout.addWidget(self.rubric)
        self.current = Q.QPlainTextEdit()
        self.current.setReadOnly(True)
        self.current.setPlainText("Phiên GUI hiện tại: chưa thu. Kết nối Pi không cập nhật hồ sơ lịch sử tự động.")
        layout.addWidget(self.current)
        self.pages.addTab(rubric, "Chất lượng / phiên mới")
        self.detail = Q.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(80)
        self.detail.setMaximumHeight(110)
        root.addWidget(self.detail)
        self.open_source = Q.QPushButton("Mở nguồn của dòng đã chọn")
        self.open_source.setEnabled(False)
        self.open_source.clicked.connect(self.open_selected_source)
        root.addWidget(self.open_source)
        self.reload()

    def add_table(self, title, key, columns, fields):
        table = Q.QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(Q.QAbstractItemView.SelectRows)
        table.setSelectionMode(Q.QAbstractItemView.SingleSelection)
        table.setWordWrap(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Interactive)
        table.horizontalHeader().setSectionResizeMode(len(columns)-1, Q.QHeaderView.Stretch)
        table.viewport().installEventFilter(self)
        table.itemSelectionChanged.connect(lambda: self.show_detail(table))
        self.tables.append((key, fields, table))
        self.pages.addTab(table, title)

    def reload(self):
        try:
            self.catalog = load_catalog()
        except (OSError, ValueError, TypeError) as error:
            self.banner.setText("Hồ sơ local không đọc được: " + str(error))
            return
        c = self.catalog
        self.banner.setText(f"HỒ SƠ LOCAL · cập nhật {c['review_date']} · dữ liệu đến {c['data_cutoff']}\n"
                            + c["scope"] + "\n" + c["next_action"])
        for key, fields, table in self.tables:
            table.setRowCount(len(c[key]))
            for row, record in enumerate(c[key]):
                for col, field in enumerate(fields):
                    item = Q.QTableWidgetItem(str(record.get(field, "chưa biết")))
                    item.setData(QtCore.Qt.UserRole, record)
                    item.setToolTip(str(record.get("limits", record.get("result", record.get("outcome", "")))))
                    table.setItem(row, col, item)
            for row in range(table.rowCount()):
                table.setRowHeight(row, 64)
        text = "MỨC BẰNG CHỨNG THEO CLAIM · rubric v1, không là chứng nhận an toàn\n\n"
        text += "\n".join(f"{k}: {v}" for k, v in LEVELS.items())
        text += "\n\n" + "\n".join(c["quality_rules"])
        text += "\n\nPHẢN BIỆN BÁO CÁO MỚI\n" + "\n\n".join(c["corrections"])
        self.rubric.setPlainText(text)
        self.filter_rows()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize:
            weights = {"data": (.07, .24, .18), "parameters": (.25, .25, .21),
                       "sessions": (.32, .06, .25), "tasks": (.07, .10, .17)}
            for key, _, table in self.tables:
                if obj is table.viewport():
                    for col, fraction in enumerate(weights[key]):
                        table.setColumnWidth(col, max(46, int(table.viewport().width()*fraction)))
                    break
        return super().eventFilter(obj, event)

    def filter_rows(self):
        term = self.search.text().casefold().strip()
        for _, _, table in self.tables:
            for row in range(table.rowCount()):
                record = table.item(row, 0).data(QtCore.Qt.UserRole)
                table.setRowHidden(row, term not in json.dumps(record, ensure_ascii=False).casefold())

    def show_detail(self, table):
        row = table.currentRow()
        if row < 0 or not table.item(row, 0):
            return
        record = table.item(row, 0).data(QtCore.Qt.UserRole)
        if table is self.tables[3][2]:
            self.selected_recipe = TASK_RECIPES.get(record.get('id'), 'inventory')
        self.selected_sources = record.get("sources", [])
        paths = [self.catalog["sources"][key] for key in self.selected_sources]
        self.detail.setPlainText("\n".join(f"{k}: {v}" for k, v in record.items()) +
                                 "\n\nNguồn snapshot:\n" + "\n".join(f"{p['path']}\nSHA256: {p['sha256']}" for p in paths))
        self.open_source.setEnabled(bool(paths))

    def show_commands(self):
        dialog = CommandsDialog(self.selected_recipe, connection=self.connection, parent=self)
        dialog.exec_()

    def open_selected_source(self):
        menu = Q.QMenu(self)
        for key in self.selected_sources:
            source = self.catalog["sources"][key]
            path = Path(source["path"])
            action = menu.addAction(key + " · " + path.name)
            action.setEnabled(path.is_file())
            action.triggered.connect(lambda checked=False, p=path: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(p))))
        menu.exec_(self.open_source.mapToGlobal(self.open_source.rect().bottomLeft()))

    def handle(self, message):
        if message.get("type") != "capture":
            return
        self.last_capture = message
        if message.get("active"):
            self.current.setPlainText("Phiên đang chạy / đóng: chưa chấm mức cuối.\n" + str(message.get("directory", "")))
        elif message.get("result"):
            result = message["result"]
            report = assess_capture(result, demo=True) if self.demo else result.get("quality_report") or assess_capture(result)
            self.current.setPlainText(str(message.get("directory", "")) + "\n" + quality_text(report))

    def export(self):
        target, _ = Q.QFileDialog.getSaveFileName(self, "Xuất bản sao hồ sơ; không sửa raw", "nino_project_status.json", "JSON (*.json)")
        if target:
            try:
                Path(target).write_text(json.dumps(dict(catalog=self.catalog, current_gui_capture=self.last_capture),
                                                  ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            except (OSError, ValueError) as error:
                Q.QMessageBox.warning(self, "Không xuất được", str(error))
