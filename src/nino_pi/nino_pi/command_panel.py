"""Copy-only commands dialog. No execution or network surface."""
from PyQt5 import QtWidgets as Q
from .collection_recipes import RECIPES, render_recipe


class CommandsDialog(Q.QDialog):
    def __init__(self, recipe='diagnostic', connection=None, parent=None):
        super().__init__(parent)
        self.connection = connection or (lambda: {})
        self.setWindowTitle('Nino · Lệnh thu dữ liệu · chỉ copy')
        self.resize(970,700)
        layout=Q.QVBoxLayout(self)
        self.choose=Q.QComboBox()
        for key,(title,_) in RECIPES.items():self.choose.addItem(title,key)
        self.choose.setCurrentIndex(self.choose.findData(recipe))
        layout.addWidget(self.choose)
        self.note=Q.QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.steps=Q.QListWidget();layout.addWidget(self.steps,1)
        self.where=Q.QLabel();self.where.setWordWrap(True);layout.addWidget(self.where)
        self.command=Q.QPlainTextEdit();self.command.setReadOnly(True);self.command.setMaximumHeight(150);layout.addWidget(self.command)
        self.warning=Q.QLabel();self.warning.setWordWrap(True);layout.addWidget(self.warning)
        row=Q.QHBoxLayout()
        self.copy=Q.QPushButton('Copy lệnh bước đã chọn');self.copy.clicked.connect(self.copy_selected);row.addWidget(self.copy)
        self.copy_all=Q.QPushButton('Copy toàn bộ hướng dẫn');self.copy_all.clicked.connect(self.copy_guide);row.addWidget(self.copy_all)
        close=Q.QPushButton('Đóng');close.clicked.connect(self.accept);row.addWidget(close);layout.addLayout(row)
        self.feedback=Q.QLabel('Copy không chạy lệnh. Các bước terminal 1/2/3 phải chạy ở các cửa sổ riêng.');layout.addWidget(self.feedback)
        self.choose.currentIndexChanged.connect(self.refresh)
        self.steps.currentRowChanged.connect(self.select_step)
        self.refresh()

    def refresh(self):
        self.steps.clear();self.recipe=None
        try:
            c=self.connection()
            self.recipe=render_recipe(self.choose.currentData(),host=c.get('host','d@192.168.0.109'),key=c.get('key'))
        except ValueError as e:
            self.note.setText(str(e));self.copy.setEnabled(False);self.copy_all.setEnabled(False);self.command.clear();return
        self.note.setText(self.recipe['note']+'\nDùng IP/key từ Thiết lập SSH. Mỗi lệnh từ laptop sẽ SSH vào Pi khi cần.')
        self.copy_all.setEnabled(True)
        for step in self.recipe['steps']:self.steps.addItem(step['title']+'  ·  '+step['effect'])
        self.steps.setCurrentRow(0)

    def select_step(self,index):
        valid=self.recipe is not None and 0<=index<len(self.recipe['steps'])
        self.copy.setEnabled(valid)
        if not valid:return
        step=self.recipe['steps'][index]
        self.where.setText('Chạy tại: '+step['terminal']+'\nTác động: '+step['effect'])
        self.command.setPlainText(step['command'])
        self.warning.setText(step['note'])

    def copy_selected(self):
        if self.copy.isEnabled():
            Q.QApplication.clipboard().setText(self.command.toPlainText())
            self.feedback.setText('Đã copy lệnh. Dán vào đúng terminal ghi phía trên; GUI không thực thi lệnh.')

    def copy_guide(self):
        if not self.recipe:return
        lines=['# '+self.recipe['title'],'# '+self.recipe['note']]
        for step in self.recipe['steps']:
            lines+=['','# '+step['title'],'# Terminal: '+step['terminal'],'# '+step['note'],step['command']]
        Q.QApplication.clipboard().setText('\n'.join(lines)+'\n')
        self.feedback.setText('Đã copy hướng dẫn. Chạy từng khối theo terminal; không dán cả hướng dẫn vào một cửa sổ.')
