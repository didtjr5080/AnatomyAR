from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QImage
from PySide6.QtWidgets import QWidget
from ..rendering.coordinates import display_transform,mirror_x
from ..core.packets import now_ms
from .hand_selector import DwellSelector,palm_points
from ..rendering.anatomy_mapper import valid

def owned_image(rgb):
    h,w = rgb.shape[:2]
    return QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()


def screen_identity(screen):
    g = screen.geometry()
    return {"name":screen.name(),"serial":screen.serialNumber(),"manufacturer":screen.manufacturer(),
            "model":screen.model(),"geometry":f"{g.x()},{g.y()},{g.width()},{g.height()}"}


def match_screen(saved,screens):
    if not saved:
        return None
    if saved.get("serial"):
        matches = [s for s in screens if s.serialNumber()==saved["serial"] and s.name()==saved.get("name")]
    else:
        matches = [s for s in screens if all(screen_identity(s).get(k)==v for k,v in saved.items() if k!="geometry")]
    if len(matches)==1:
        return matches[0]
    exact = [s for s in matches if screen_identity(s)==saved]
    return exact[0] if len(exact)==1 else None


class VideoView(QWidget):
    def __init__(self,state,operator=False):
        super().__init__()
        self.state,self.operator = state,operator
        self.image = QImage()
        self.labels,self.points = (),None
        self.message = "표시된 영역에 서 주세요"
        self.selector=DwellSelector()
        self.hand_cursors=[]
        self.pose_timestamp=None
        self.pose_received=None
        self.interaction_geometry=None
        self.frozen=False
        self.frozen_settings=None
        self.countdown=None
        self.setMinimumSize(320,180)
        state.changed.connect(self.update)

    def present(self,image,labels=(),points=None,message="",timestamp_ms=None,interactive=True):
        if self.frozen: return
        self.image,self.labels,self.points,self.message = image,labels,points,message
        self.pose_timestamp=timestamp_ms
        if interactive: self.update_hands(now_ms())
        else: self.clear_hands()
        self.update()

    def freeze(self):
        if self.image.isNull(): return
        self.frozen=True
        self.frozen_settings=self.state.snapshot()[0]
        self.countdown=None
        self.clear_hands()

    def resume(self):
        self.frozen=False
        self.frozen_settings=None
        self.image=QImage()
        self.labels,self.points=(),None
        self.clear_hands()

    def image_geometry(self):
        if self.image.isNull(): return None
        s=self.frozen_settings or self.state.snapshot()[0]
        w,h=self.image.width(),self.image.height()
        scale,ox,oy=display_transform(w,h,self.width(),max(1,self.height()),s.fit=="fill")
        return w,h,scale,ox,oy

    def mode_rects(self):
        geometry=self.image_geometry()
        area=QRectF(0,0,self.width(),max(1,self.height()))
        if geometry:
            w,h,scale,ox,oy=geometry
            area=area.intersected(QRectF(ox,oy,w*scale,h*scale))
            s=self.frozen_settings or self.state.snapshot()[0]
            if area.width()>=224 and self.points is not None and valid(self.points,(11,12),w,h,s.confidence):
                shoulders=self.points[[11,12],:2]
                center=shoulders.mean(axis=0)
                span=float(((shoulders[0]-shoulders[1])**2).sum()**.5)*scale
                if span>=20:
                    margin=8
                    bw=min(210,max(96,span*.8))
                    bw=min(bw,(area.width()-3*margin)/2)
                    bh=max(65,min(110,bw*.55))
                    offset=min(max(span*.95,bw*.65+8),(area.width()-bw)/2-margin)
                    cx=(mirror_x(center[0],w) if s.mirror else center[0])*scale+ox
                    cx=min(max(cx,area.left()+margin+bw/2+offset),area.right()-margin-bw/2-offset)
                    cy=min(max(center[1]*scale+oy-span*.3,area.top()+bh/2+8),area.bottom()-bh/2-8)
                    return {"muscles":QRectF(cx-offset-bw/2,cy-bh/2,bw,bh),
                            "bones":QRectF(cx+offset-bw/2,cy-bh/2,bw,bh)}
        bw=max(96,min(210,area.width()*.22))
        bh=max(65,min(110,area.height()*.22))
        margin=max(8,area.width()*.035)
        y=area.top()+max(42,area.height()*.18)
        return {"muscles":QRectF(area.left()+margin,y,bw,bh),
                "bones":QRectF(area.right()-margin-bw,y,bw,bh)}

    def clear_hands(self):
        self.selector.reset()
        self.hand_cursors=[]
        self.pose_timestamp=None
        self.pose_received=None
        self.update()

    def update_hands(self,now):
        if self.frozen: return
        s,_=self.state.snapshot()
        geometry=self.image_geometry()
        signature=(geometry,s.mirror,s.fit,s.standby)
        if signature!=self.interaction_geometry:
            self.selector.reset()
            self.interaction_geometry=signature
        if (not geometry or s.standby or self.pose_timestamp is None
                or not 0<=now-self.pose_timestamp<=s.max_age_ms):
            self.clear_hands()
            return
        w,h,scale,ox,oy=geometry
        if self.pose_timestamp!=self.selector.last:
            self.pose_received=now
        cursors=[]
        hits=[]
        rectangles=self.mode_rects()
        for hand,x,y in palm_points(self.points,w,h,s.confidence):
            pos=QPointF((mirror_x(x,w) if s.mirror else x)*scale+ox,y*scale+oy)
            cursors.append((hand,pos))
            for mode,rect in rectangles.items():
                if rect.contains(pos): hits.append((hand,mode))
        self.hand_cursors=cursors
        chosen=self.selector.update(hits,self.pose_timestamp,now,s.max_age_ms,s.mode,tracking_lost=not cursors)
        if chosen: self.state.update(mode=chosen)
        self.update()

    def mouseReleaseEvent(self,event):
        if self.frozen: return
        if event.button()==Qt.MouseButton.LeftButton:
            for mode,rect in self.mode_rects().items():
                if rect.contains(event.position()):
                    self.selector.reset()
                    self.state.update(mode=mode)
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        s = self.frozen_settings or self.state.snapshot()[0]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(),QColor(s.background))
        area = QRectF(0,0,self.width(),max(1,self.height()))
        if not self.image.isNull() and not s.standby:
            w,h = self.image.width(),self.image.height()
            scale,ox,oy = display_transform(w,h,area.width(),area.height(),s.fit=="fill")
            p.save()
            p.setClipRect(area)
            image = self.image.mirrored(True,False) if s.mirror else self.image
            p.drawImage(QRectF(ox,oy,w*scale,h*scale),image)
            def point(x,y):
                return ((mirror_x(x,w) if s.mirror else x)*scale+ox,y*scale+oy)
            if not self.frozen and self.operator and s.debug and self.points is not None:
                p.setPen(QPen(QColor("#54efc4"),2))
                for row in self.points:
                    if row[3]>=s.confidence and row[4]>=s.confidence:
                        x,y = point(row[0],row[1])
                        p.drawEllipse(QRectF(x-3,y-3,6,6))
            if s.labels:
                used = []
                p.setFont(QFont("Malgun Gothic",10 if self.operator else 14))
                for x,y,label in self.labels:
                    x,y = point(x,y)
                    bounds = p.fontMetrics().boundingRect(label)
                    rect = QRectF(min(max(4,x+8),max(4,self.width()-bounds.width()-16)),y,bounds.width()+12,bounds.height()+8)
                    while any(rect.intersects(r) for r in used):
                        rect.translate(0,rect.height()+3)
                    if rect.bottom()>area.bottom():
                        continue
                    used.append(rect)
                    p.fillRect(rect,QColor(12,20,28,210))
                    p.setPen(QColor("white"))
                    p.drawText(rect,Qt.AlignmentFlag.AlignCenter,label)
            p.restore()
        if not self.frozen: self.paint_mode_controls(p,s)
        if self.countdown is not None:
            p.setPen(QColor("white"))
            p.setFont(QFont("Malgun Gothic",100,QFont.Weight.Bold))
            p.drawText(area,Qt.AlignmentFlag.AlignCenter,str(self.countdown))
        p.end()

    def paint_mode_controls(self,p,s):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rectangles=self.mode_rects()
        for mode,rect in rectangles.items():
            active=s.mode==mode
            color=QColor("#fa9f87" if mode=="muscles" else "#9ee1ee")
            p.setPen(QPen(color,3 if active else 1))
            p.setBrush(QColor(20,34,43,235))
            p.drawRoundedRect(rect,16,16)
            p.setFont(QFont("Malgun Gothic",22 if rect.width()>150 else 16,QFont.Weight.Bold))
            p.setPen(color)
            p.drawText(rect,Qt.AlignmentFlag.AlignCenter,"근육" if mode=="muscles" else "뼈")
            if self.selector.target and self.selector.target[1]==mode:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(QRectF(rect.left()+10,rect.bottom()-7,(rect.width()-20)*self.selector.progress,4),2,2)
        for hand,pos in self.hand_cursors:
            p.setBrush(QColor(255,255,255,90))
            p.setPen(QPen(QColor("#ffffff"),3))
            p.drawEllipse(pos,16,16)
