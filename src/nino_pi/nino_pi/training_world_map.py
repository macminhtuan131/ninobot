"""Qt top-down viewer for the active SDF and recorded simulator poses."""
import math
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as Q


class WorldMap(Q.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.identity=None;self.bounds=C.QRectF(-2,-4,11,8)
        self.scene=Q.QGraphicsScene(self);self.view=Q.QGraphicsView(self.scene)
        self.view.setRenderHint(G.QPainter.Antialiasing);self.view.setDragMode(Q.QGraphicsView.ScrollHandDrag)
        self.view.setBackgroundBrush(G.QColor('#111d2c'));self.dynamic=[]
        layout=Q.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        row=Q.QHBoxLayout();self.follow=Q.QCheckBox('Theo robot');self.follow.setChecked(False)
        fit=Q.QPushButton('Toàn map');fit.clicked.connect(self.fit)
        plus=Q.QPushButton('+');plus.clicked.connect(lambda:self.view.scale(1.4,1.4))
        minus=Q.QPushButton('−');minus.clicked.connect(lambda:self.view.scale(1/1.4,1/1.4))
        for w in (fit,plus,minus,self.follow):row.addWidget(w)
        row.addStretch();layout.addLayout(row);layout.addWidget(self.view,1)
        self.view.setMinimumHeight(240)
        self.note=Q.QLabel('Đang chờ SDF và pose từ trace');self.note.setWordWrap(True);self.note.setMinimumHeight(50);layout.addWidget(self.note)
        legend=Q.QLabel('Xanh ngọc: GT sim/vệt đi · vàng: estimator · trắng đứt: tuyến · xám: tường · cam: objects. Đơn vị m; mũi tên là ký hiệu pose.')
        legend.setWordWrap(True);legend.setMinimumHeight(32);layout.addWidget(legend)
    def fit(self):self.follow.setChecked(False);self.view.fitInView(self.bounds,C.Qt.KeepAspectRatio)
    def draw_path(self,values,color,width=2,dashed=False):
        if not values:return
        path=G.QPainterPath(C.QPointF(values[0][0],-values[0][1]))
        for p in values[1:]:path.lineTo(p[0],-p[1])
        pen=G.QPen(G.QColor(color));pen.setWidthF(width);pen.setCosmetic(True)
        if dashed:pen.setStyle(C.Qt.DashLine)
        item=self.scene.addPath(path,pen);item.setZValue(5);self.dynamic.append(item)
    def update_snapshot(self,s):
        world=s['world'];identity=(s['directory'],world.get('sha256'))
        if self.identity!=identity:
            self.scene.clear();self.dynamic=[];self.identity=identity
            for shape in sorted(world.get('shapes',[]),key=lambda v:v['kind']!='floor'):
                points=G.QPolygonF([C.QPointF(x,-y) for x,y in shape['polygon']])
                color={'floor':'#243347','wall':'#71849b','object':'#e58e40'}[shape['kind']]
                item=self.scene.addPolygon(points,G.QPen(G.QColor('#91a3b8'),0),G.QBrush(G.QColor(color)))
                item.setToolTip(shape['name']);item.setZValue(-3 if shape['kind']=='floor' else 0)
            self.bounds=self.scene.itemsBoundingRect().adjusted(-.5,-.5,.5,.5) if world.get('shapes') else C.QRectF(-2,-4,11,8)
            pen=G.QPen(G.QColor('#40516a'),0);pen.setStyle(C.Qt.DotLine)
            for x in range(math.floor(self.bounds.left()),math.ceil(self.bounds.right())+1):
                self.scene.addLine(x,self.bounds.top(),x,self.bounds.bottom(),pen).setZValue(-1)
            for y in range(math.floor(self.bounds.top()),math.ceil(self.bounds.bottom())+1):
                self.scene.addLine(self.bounds.left(),y,self.bounds.right(),y,pen).setZValue(-1)
            origin=self.scene.addSimpleText('(0,0) · X→ Y↑');origin.setBrush(G.QBrush(G.QColor('#e9f4ff')))
            origin.setFlag(Q.QGraphicsItem.ItemIgnoresTransformations);origin.setPos(0,.12);origin.setZValue(3)
            self.scene.setSceneRect(self.bounds);self.fit()
        for item in self.dynamic:self.scene.removeItem(item)
        self.dynamic=[];self.draw_path(s.get('path',[]),'#ecf1f7',1.5,True)
        self.draw_path(s.get('truth_path',[]),'#42e7cd',2.5)
        self.draw_path(s.get('estimate_path',[]),'#f7d560',1.5,True)
        current=s.get('current',{});p=current.get('truth_pose')
        if p:
            x,y,yaw=p
            # Heading is CCW in world XY. Negating world Y also negates yaw.
            local=[(.25,0),(-.16,.13),(-.10,0),(-.16,-.13)]
            points=[C.QPointF(x+px*math.cos(yaw)-py*math.sin(yaw),-(y+px*math.sin(yaw)+py*math.cos(yaw))) for px,py in local]
            arrow=self.scene.addPolygon(G.QPolygonF(points),G.QPen(G.QColor('#dcfff6'),0),G.QBrush(G.QColor('#22cdb3')))
            arrow.setZValue(10);self.dynamic.append(arrow)
            if self.follow.isChecked():self.view.fitInView(C.QRectF(x-2,-y-2,4,4),C.Qt.KeepAspectRatio)
        age=s.get('trace_age_s');pose_text=(f"x={p[0]:.3f}, y={p[1]:.3f}, yaw={math.degrees(p[2]):.1f}°" if p else 'chưa có pose hợp lệ')
        self.note.setText(f"{s.get('map_scope','TRAIN')} · EP {current.get('episode','—')} · t={current.get('elapsed_s','—')} s · {pose_text}\n"
            +('Trace cập nhật %.1f s trước. '%age if age is not None else '')
            +f"World: {world.get('scenario','—')} · {len(world.get('shapes',[]))} collision shapes. "
            +('Chưa hoàn tất đọc trace cũ. ' if s.get('backlog_bytes') else '')
            +' / '.join(world.get('warnings',[])))

