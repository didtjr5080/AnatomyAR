from dataclasses import asdict
from PySide6.QtCore import Qt,QSignalBlocker,Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,QLineEdit,QTabWidget,QScrollArea,QDockWidget)
from ..core.settings import Settings,PARTS,load,save
from .exhibition_window import VideoView,screen_identity,match_screen


class ControlWindow(QMainWindow):
    start_requested = Signal()
    stop_requested = Signal()
    apply_requested = Signal()
    screen_requested = Signal(str)
    camera_scan_requested = Signal()
    close_requested = Signal()
    resume_requested = Signal()

    def __init__(self,state):
        super().__init__()
        self.state = state
        self.allow_close = False
        self.setWindowTitle("AnatomyAR")
        self.resize(1280,850)
        self.controls = {}
        self.camera_devices=[]
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        self.status_label = QLabel("중지 · 모델 준비 대기")
        self.status_label.setWordWrap(True)
        self.device_label = QLabel("카메라 시작 대기 · 연결 여부는 영상을 읽어 확인합니다")
        self.device_label.setWordWrap(True)
        commands = QHBoxLayout()
        self.start_button = QPushButton("시작 / 다시 연결")
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button = QPushButton("정지")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        settings_button=QPushButton("컨트롤")
        settings_button.clicked.connect(lambda:self.settings_dock.setVisible(not self.settings_dock.isVisible()))
        commands.addWidget(settings_button)
        fullscreen=QPushButton("전체 화면")
        fullscreen.clicked.connect(self.toggle_fullscreen)
        commands.addWidget(fullscreen)
        self.preview = VideoView(state,True)
        layout.addWidget(self.preview,1)
        layout.addLayout(commands)
        self.settings_dock=QDockWidget("컨트롤",self)
        self.settings_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        settings_body=QWidget()
        settings_layout=QVBoxLayout(settings_body)
        self.settings_dock.setWidget(settings_body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,self.settings_dock)
        self.settings_dock.hide()
        settings_layout.addWidget(self.status_label)
        settings_layout.addWidget(self.device_label)
        settings_layout.addWidget(self.start_button)
        settings_layout.addWidget(self.stop_button)
        self.resume_button=QPushButton("화면 재개")
        self.resume_button.setEnabled(False)
        self.resume_button.clicked.connect(self.resume_requested.emit)
        settings_layout.addWidget(self.resume_button)
        tabs = QTabWidget()
        settings_layout.addWidget(tabs,1)
        display = self.form_tab(tabs,"표시")
        original=QPushButton("원본 보기 (해부학 숨김)")
        original.clicked.connect(lambda:state.update(mode="original"))
        display.addRow(original)
        self.spin(display,"불투명도","opacity",0,1,.05)
        for text,key in (("거울 보기","mirror"),("부위 이름","labels"),("상체만","upper_only"),("기준점 디버그","debug"),("대기 화면","standby")):
            self.check(display,text,key)
        fit = QComboBox()
        fit.addItem("전체 맞춤 / 여백","fit")
        fit.addItem("화면 채움 / 잘림","fill")
        fit.currentIndexChanged.connect(lambda: state.update(fit=fit.currentData()))
        self.controls["fit"] = fit
        display.addRow("영상 비율",fit)
        for text,key in (("배경색 #RRGGBB","background"),):
            edit = QLineEdit()
            edit.editingFinished.connect(lambda k=key,w=edit:self.try_update(**{k:w.text()}))
            display.addRow(text,edit)
            self.controls[key] = edit
        align = self.form_tab(tabs,"정렬")
        for text,key,lo,hi,step in (("좌우 위치 (영상 폭 비율)","offset_x",-.3,.3,.01),("상하 위치 (영상 높이 비율)","offset_y",-.3,.3,.01),("전체 크기","scale",.5,1.5,.02)):
            self.spin(align,text,key,lo,hi,step)
        for part,text in zip(PARTS,("몸통","상완","전완","허벅지","종아리")):
            self.nested_spin(align,text+" 폭 · 좌우 공통","widths",part)
        self.nested_spin(align,"왼쪽 전체 폭 · 추가 보정","side_widths","left")
        self.nested_spin(align,"오른쪽 전체 폭 · 추가 보정","side_widths","right")
        reset = QPushButton("정렬 초기화")
        reset.clicked.connect(lambda:state.update(offset_x=0,offset_y=0,scale=1,widths=Settings().widths,side_widths=Settings().side_widths))
        align.addRow(reset)
        devices = self.form_tab(tabs,"장치 / 전시")
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self.camera_changed)
        devices.addRow("카메라",self.camera_combo)
        self.scan_button = QPushButton("카메라 영상 재검색 (일시 정지)")
        self.scan_button.clicked.connect(self.camera_scan_requested.emit)
        devices.addRow(self.scan_button)
        for text,key,lo,hi,step in (("요청 너비","capture_width",320,3840,160),("요청 높이","capture_height",240,2160,120),("요청 FPS","capture_fps",5,60,1)):
            self.spin(devices,text,key,lo,hi,step,integer=True)
        self.screen_combo = QComboBox()
        self.screen_combo.currentIndexChanged.connect(self.screen_changed)
        devices.addRow("전시 모니터",self.screen_combo)
        for text,action in (("이 화면을 선택 모니터로 이동","move"),("선택 모니터에서 전체 화면","fullscreen"),("창 모드로 돌아가기","window")):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False,a=action:self.screen_requested.emit(a))
            devices.addRow(button)
        advanced = self.form_tab(tabs,"고급 / 저장")
        for text,key,lo,hi,step,integer in (("추론 입력 장변","inference_size",192,960,32,True),("추론 주기 ms","inference_interval_ms",16,500,1,True),("부위 신뢰도","confidence",.1,.99,.05,False),("평활화 시상수 ms","smoothing_ms",0,500,5,False),("결과 유효 시간 ms","max_age_ms",50,500,10,True)):
            self.spin(advanced,text,key,lo,hi,step,integer)
        asset = QComboBox()
        asset.addItem("교육용 질감 자산 v1 · 현장 검수 전","educational-v1")
        advanced.addRow("자산",asset)
        apply = QPushButton("장치 / 추론 입력 적용 (다시 시작)")
        apply.clicked.connect(self.apply_requested.emit)
        advanced.addRow(apply)
        for text,method in (("설정 저장",self.save_settings),("설정 불러오기",self.load_settings),("모든 설정 초기화",self.reset_settings)):
            button = QPushButton(text)
            button.clicked.connect(method)
            advanced.addRow(button)
        self.metrics_label = QLabel("캡처 0 · 추론 0 · 표시 0 FPS")
        self.metrics_label.setWordWrap(True)
        settings_layout.addWidget(self.metrics_label)
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        settings_layout.addWidget(self.notice)
        state.changed.connect(self.sync)
        state.status_changed.connect(lambda status,message:self.status_label.setText(status.value+(" · "+message if message else "")))
        self.refresh_cameras()
        self.refresh_screens()
        self.sync()

    def form_tab(self,tabs,title):
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        tabs.addTab(scroll,title)
        return form

    def spin(self,form,text,key,lo,hi,step,integer=False):
        box = QSpinBox() if integer else QDoubleSpinBox()
        box.setRange(lo,hi)
        box.setSingleStep(step)
        box.valueChanged.connect(lambda value:self.state.update(**{key:value}))
        self.controls[key] = box
        form.addRow(text,box)

    def nested_spin(self,form,text,key,part):
        box = QDoubleSpinBox()
        box.setRange(.5,1.5)
        box.setSingleStep(.02)
        def changed(value):
            settings,_ = self.state.snapshot()
            self.state.update(**{key:{**getattr(settings,key),part:value}})
        box.valueChanged.connect(changed)
        self.controls[f"{key}.{part}"] = box
        form.addRow(text,box)

    def check(self,form,text,key):
        box = QCheckBox(text)
        box.toggled.connect(lambda value:self.state.update(**{key:value}))
        self.controls[key] = box
        form.addRow(box)

    def try_update(self,**values):
        try:
            self.state.update(**values)
        except ValueError as exc:
            self.notice.setText(str(exc))
            self.sync()

    def sync(self):
        s,_ = self.state.snapshot()
        for key,widget in self.controls.items():
            if "." in key:
                parent,child = key.split(".")
                value = getattr(s,parent)[child]
            else:
                value = getattr(s,key)
            blocker = QSignalBlocker(widget)
            if isinstance(widget,QCheckBox): widget.setChecked(value)
            elif isinstance(widget,QLineEdit): widget.setText(value)
            elif isinstance(widget,QComboBox): widget.setCurrentIndex(widget.findData(value))
            else: widget.setValue(value)
            del blocker

    def refresh_cameras(self):
        s,_ = self.state.snapshot()
        blocker = QSignalBlocker(self.camera_combo)
        self.camera_combo.clear()
        self.camera_combo.addItem("자동 선택 · 영상이 나오는 장치 찾기",-1)
        found={info["index"]:info for info in self.camera_devices}
        for index in sorted(set(range(6)) | set(found)):
            info=found.get(index)
            text=(f"{index}: 영상 확인 · {info['width']}×{info['height']} · {info['backend']}" if info
                  else f"{index}: 아직 영상 확인 안 됨")
            self.camera_combo.addItem(text,index)
        if self.camera_combo.findData(s.camera_index)<0:
            self.camera_combo.addItem(f"장치 번호 {s.camera_index} (연결 확인 필요)",s.camera_index)
        self.camera_combo.setCurrentIndex(self.camera_combo.findData(s.camera_index))
        del blocker

    def update_cameras(self,devices):
        self.camera_devices=list(devices)
        self.refresh_cameras()

    def toggle_fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
        elif event.key()==Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
            event.accept()
        else:
            super().keyPressEvent(event)

    def camera_changed(self):
        index = self.camera_combo.currentData()
        if index is not None: self.state.update(camera_index=index)

    def refresh_screens(self):
        s,_ = self.state.snapshot()
        screens = QGuiApplication.screens()
        selected = match_screen(s.screen,screens)
        blocker = QSignalBlocker(self.screen_combo)
        self.screen_combo.clear()
        self.screen_combo.addItem("모니터를 선택하세요",None)
        for screen in screens:
            g = screen.geometry()
            self.screen_combo.addItem(f"{screen.name()} · {g.width()}×{g.height()} · 배율 {screen.devicePixelRatio():g}",screen)
        if selected is not None:
            self.screen_combo.setCurrentIndex(self.screen_combo.findData(selected))
        del blocker

    def screen_changed(self):
        screen = self.screen_combo.currentData()
        self.state.update(screen=screen_identity(screen) if screen else {})

    def save_settings(self):
        try:
            save(self.state.snapshot()[0])
            self.notice.setText("설정을 저장했습니다")
        except (OSError,ValueError) as exc:
            self.notice.setText(f"저장 실패: {exc}")

    def load_settings(self):
        try:
            self.state.replace(load())
            self.refresh_cameras()
            self.refresh_screens()
            self.notice.setText("설정을 불러왔습니다. 장치 변경은 적용 버튼을 눌러 주세요.")
        except (OSError,ValueError) as exc:
            self.notice.setText(f"설정 손상: {exc} · 초기화하거나 파일을 복구하세요")

    def reset_settings(self):
        self.state.replace(Settings())
        self.refresh_cameras()
        self.refresh_screens()
        self.notice.setText("기본 설정 복원 · 장치 설정은 적용 버튼을 눌러 주세요")

    def closeEvent(self,event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.close_requested.emit()
