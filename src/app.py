import argparse
from dataclasses import replace
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import cv2
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtGui import QGuiApplication,QImage
from PySide6.QtWidgets import QApplication
from .core.settings import Settings,load,settings_path
from .core.state import AppState,Status
from .core.packets import Latest,now_ms
from .core.metrics import Metrics,process_memory
from .capture.camera_worker import CameraWorker
from .capture.devices import CameraScanner
from .tracking.mediapipe_tracker import TrackerWorker
from .ui.control_window import ControlWindow
from .ui.exhibition_window import owned_image
from .ui.fonts import configure_font
from .ui.victory_countdown import VictoryCountdown


class Controller(QObject):
    def __init__(self,app,state,log_path=None):
        super().__init__()
        configure_font(app)
        self.app,self.state = app,state
        self.control = ControlWindow(state)
        self.target_screen=None
        self.generation = 0
        self.camera = self.tracker = None
        self.scanner=None
        self.rescan=False
        self.preview,self.output = Latest(),Latest()
        self.metrics = Metrics()
        self.total_drops=0
        self.last_cpu,self.last_wall=time.process_time(),time.monotonic()
        self.current = None
        self.last_display = None
        self.stopping = self.quitting = self.restart = False
        self.error = None
        self.countdown=VictoryCountdown()
        self.resume_after=-1
        self.last_composite=self.photo_packet=None
        self.last_rendered=None
        self.control.start_requested.connect(self.start)
        self.control.stop_requested.connect(self.stop)
        self.control.apply_requested.connect(self.apply)
        self.control.screen_requested.connect(self.place_screen)
        self.control.camera_scan_requested.connect(self.scan_cameras)
        self.control.close_requested.connect(self.shutdown)
        self.control.resume_requested.connect(self.resume_view)
        app.screenAdded.connect(self.screen_added)
        app.screenRemoved.connect(self.screen_removed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.stats)
        self.stats_timer.start(1000)
        self.logger = None
        if log_path:
            log_path.parent.mkdir(parents=True,exist_ok=True)
            self.logger = logging.getLogger("anatomy_metrics")
            self.logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(log_path,maxBytes=5_000_000,backupCount=2,encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def start(self):
        if self.stopping or self.tracker is not None or self.camera is not None or self.scanner is not None:
            return
        self.error = None
        self.generation += 1
        self.metrics = Metrics()
        self.total_drops=0
        self.preview,self.output = Latest(),Latest()
        self.current,self.last_display = None,None
        self.last_composite=self.photo_packet=None
        self.last_rendered=None
        self.state.set_status(Status.STARTING,"Lite 모델·해부학 자산 확인 중")
        self.control.device_label.setText("카메라 준비 중 · 실제 영상을 읽어 연결을 확인합니다")
        self.control.start_button.setEnabled(False)
        self.tracker = TrackerWorker(self.state,self.generation,self.output,self.metrics)
        self.tracker.ready.connect(self.model_ready)
        self.tracker.failed.connect(lambda generation,message:self.failed(generation,Status.MODEL_ERROR,message))
        self.tracker.start()

    def model_ready(self,generation):
        if generation!=self.generation or self.stopping:
            return
        self.control.device_label.setText("카메라 검색·연결 중 · 실패한 기본 번호 다음의 장치도 확인합니다")
        self.camera = CameraWorker(self.state.snapshot()[0],generation,self.preview,self.metrics)
        self.camera.frame_ready.connect(self.tracker.submit,Qt.ConnectionType.DirectConnection)
        self.camera.opened.connect(self.camera_opened)
        self.camera.failed.connect(lambda g,message:self.failed(g,Status.CAMERA_ERROR,message))
        self.camera.start()

    def camera_opened(self,generation,info):
        if generation==self.generation and not self.stopping:
            self.control.device_label.setText(f"카메라 {info['index']} 연결됨 · {info['backend']} · 실제 {info['width']:.0f}×{info['height']:.0f} / 드라이버 FPS {info['fps']:.1f}")
            devices=[d for d in self.control.camera_devices if d["index"]!=info["index"]]+[info]
            self.control.update_cameras(devices)
            if self.logger: self.logger.info(json.dumps({"event":"camera_opened",**info},ensure_ascii=False))
            self.state.set_status(Status.WAITING_PERSON)

    def failed(self,generation,status,message):
        if generation!=self.generation:
            return
        self.error = (status,message)
        self.control.settings_dock.show()
        if status==Status.CAMERA_ERROR:
            self.control.device_label.setText("장치 검색/영상 열기 실패 · 연결된 카메라가 없다는 판정은 아닙니다")
        if self.logger: self.logger.info(json.dumps({"event":"error","status":status.name,"message":message},ensure_ascii=False))
        self.state.set_status(status,message)
        self.stop()

    def stop(self):
        if self.stopping:
            return
        self.stopping = True
        self.generation += 1
        self.current = None
        self.last_composite=self.photo_packet=None
        self.last_rendered=None
        self.countdown.clear()
        self.control.preview.countdown=None
        if self.camera: self.camera.requestInterruption()
        if self.tracker: self.tracker.stop()
        if self.scanner: self.scanner.requestInterruption()
        self.control.preview.present(QImage(),message="잠시 후 체험을 시작합니다")
        if not self.error: self.state.set_status(Status.STOPPED,"장치 해제 중")

    def apply(self):
        self.restart = True
        self.rescan=False
        self.error = None
        self.stop()

    def shutdown(self):
        self.quitting = True
        self.restart = False
        self.rescan=False
        self.stop()

    def finish_stop(self):
        if any(t is not None and t.isRunning() for t in (self.camera,self.tracker,self.scanner)):
            return
        if self.tracker:
            self.total_drops=self.tracker.input.dropped+self.tracker.results.dropped+self.tracker.matcher.dropped
        for worker in (self.camera,self.tracker,self.scanner):
            if worker: worker.deleteLater()
        self.camera = self.tracker = None
        self.scanner=None
        self.stopping = False
        self.control.start_button.setEnabled(True)
        self.control.scan_button.setEnabled(True)
        if not self.error: self.state.set_status(Status.STOPPED)
        if not self.error: self.control.device_label.setText("카메라 중지 · 시작을 누르면 다시 연결합니다")
        if self.quitting:
            self.control.allow_close = True
            self.control.close()
            self.timer.stop()
            self.stats_timer.stop()
            self.app.quit()
        elif self.rescan:
            self.rescan=False
            self.begin_scan()
        elif self.restart:
            self.restart = False
            self.start()

    def tick(self):
        if self.stopping:
            self.finish_stop()
            return
        if self.control.preview.frozen: return
        settings,version = self.state.snapshot()
        packet = self.output.take()
        if packet and packet.frame.generation_id==self.generation and packet.frame.timestamp_ms>self.resume_after:
            self.current = packet
        now = now_ms()
        view=self.control.preview
        if settings.standby or (self.countdown.started is None and self.countdown.received is not None
                               and now-self.countdown.received>settings.max_age_ms):
            self.countdown.clear()
            self.photo_packet=None
            view.countdown=None
            view.update()
        if view.pose_received is not None and (settings.standby or now-view.pose_received>settings.max_age_ms):
            view.clear_hands()
        current = self.current
        if current and now-current.frame.timestamp_ms<=settings.max_age_ms and current.version==version:
            key = (current.frame.generation_id,current.frame.frame_id,current.version,"render")
            if key!=self.last_display:
                image = owned_image(current.rgb)
                composed=bool(current.labels) or current.status==Status.TRACKING
                if composed: self.last_composite=current
                hands=() if settings.standby else current.pose.victory_hands
                freeze=self.countdown.update(hands,current.pose.timestamp_ms,now,settings.max_age_ms)
                if (self.countdown.started is not None or freeze):
                    if composed or self.photo_packet is None:
                        previous=self.last_composite
                        self.photo_packet=(previous if previous is not None and previous.version==version
                                           and now-previous.frame.timestamp_ms<=500 else current)
                view.countdown=self.countdown.number
                previous=self.last_composite
                keep_composite=(not composed and previous is not None and previous.version==version
                                and (0<=now-previous.frame.timestamp_ms<=500
                                     or self.countdown.started is not None and self.photo_packet is previous))
                if keep_composite:
                    view.present(view.image,view.labels,current.pose.landmarks,current.message,current.pose.timestamp_ms,
                                 interactive=not hands and self.countdown.started is None)
                else:
                    view.present(image,current.labels,current.pose.landmarks,current.message,current.pose.timestamp_ms,
                                 interactive=not hands and self.countdown.started is None)
                    self.last_rendered=(self.generation,version,now)
                if freeze:
                    self.freeze_photo()
                self.last_display = key
                self.metrics.event("display")
                self.metrics.sample("latency_ms",now-current.frame.timestamp_ms)
                self.state.set_status(current.status,current.message)
            self.metrics.sample("age_ms",now-current.frame.timestamp_ms)
            return
        if self.countdown.advance(now):
            self.freeze_photo()
            return
        if view.countdown!=self.countdown.number:
            view.countdown=self.countdown.number
            view.update()
        if self.countdown.started is not None: return
        # Keep one complete camera+anatomy frame between results, never alternate with raw video.
        if (self.last_rendered is not None and self.last_rendered[:2]==(self.generation,version)
                and 0<=now-self.last_rendered[2]<=500 and not settings.standby):
            return
        frame = self.preview.peek()
        if frame and frame.generation_id==self.generation and frame.timestamp_ms>self.resume_after and now-frame.timestamp_ms<500:
            key = (frame.generation_id,frame.frame_id,version,"raw")
            if key!=self.last_display:
                image = owned_image(cv2.cvtColor(frame.bgr,cv2.COLOR_BGR2RGB))
                self.control.preview.present(image,message="카메라를 바라봐 주세요")
                self.last_display = key
                self.metrics.event("raw_display")
            if current and now-current.frame.timestamp_ms>settings.max_age_ms:
                self.state.set_status(Status.DEGRADED,"추적 결과 지연 · 합성 숨김")
        elif self.tracker and self.state.status not in (Status.STARTING,Status.CAMERA_ERROR,Status.MODEL_ERROR):
            self.control.preview.present(QImage(),message="잠시 후 체험을 시작합니다")

    def resume_view(self):
        if not self.control.preview.frozen: return
        self.resume_after=now_ms()
        self.output.take()
        self.current=self.last_display=None
        self.last_composite=self.photo_packet=None
        self.last_rendered=None
        self.countdown.resume()
        self.control.preview.resume()
        self.control.resume_button.setEnabled(False)

    def freeze_photo(self):
        view=self.control.preview
        settings,version=self.state.snapshot()
        photo=self.photo_packet
        if photo is not None and photo.version==version:
            view.present(owned_image(photo.rgb),photo.labels,interactive=False)
        view.freeze()
        self.photo_packet=None
        self.control.resume_button.setEnabled(view.frozen)

    def stats(self):
        m = self.metrics.snapshot()
        drops = (self.tracker.input.dropped+self.tracker.results.dropped+self.tracker.matcher.dropped) if self.tracker else self.total_drops
        m["drops"] = drops
        m["status"] = self.state.status.name
        m["timestamp_ms"] = now_ms()
        m.update(process_memory())
        cpu,wall=time.process_time(),time.monotonic()
        m["process_cpu_percent"]=(cpu-self.last_cpu)/max(wall-self.last_wall,.001)*100/(os.cpu_count() or 1)
        self.last_cpu,self.last_wall=cpu,wall
        self.control.metrics_label.setText(
            f"캡처 {m.get('capture_fps',0):.1f} · 추론 {m.get('inference_fps',0):.1f} · 합성 표시 {m.get('display_fps',0):.1f} FPS\n"
            f"지연 p95 {m.get('latency_ms_p95',0):.0f} ms · 결과 나이 p95 {m.get('age_ms_p95',0):.0f} ms · 드롭 {drops}")
        if self.logger: self.logger.info(json.dumps(m,ensure_ascii=False))

    def scan_cameras(self):
        self.rescan=True
        self.restart=False
        self.error=None
        self.stop()

    def begin_scan(self):
        self.control.start_button.setEnabled(False)
        self.control.scan_button.setEnabled(False)
        self.control.device_label.setText("카메라 영상 재검색 중 · 장치 번호 0~5 확인")
        self.scanner=CameraScanner()
        self.scanner.discovered.connect(self.scan_results)
        self.scanner.finished.connect(self.scan_finished)
        self.scanner.start()

    def scan_results(self,devices):
        if self.stopping or self.quitting: return
        self.control.update_cameras(devices)
        text=(f"영상이 나오는 카메라 {len(devices)}개 확인 · 선택 후 시작하세요" if devices
              else "영상을 읽을 수 없었습니다 · 권한/점유를 확인하거나 장치 번호를 직접 선택하세요")
        self.control.device_label.setText(text)

    def scan_finished(self):
        if self.stopping or self.scanner is None: return
        self.scanner.deleteLater()
        self.scanner=None
        self.control.start_button.setEnabled(True)
        self.control.scan_button.setEnabled(True)

    def place_screen(self,action):
        if action=="window":
            self.control.showNormal()
            return
        screen = self.control.screen_combo.currentData()
        screens = QGuiApplication.screens()
        if screen is None or screen not in screens:
            self.control.notice.setText("화면을 표시할 모니터를 먼저 선택하세요")
            return
        self.target_screen=screen
        self.control.showNormal()
        self.control.windowHandle().setScreen(screen)
        geometry=screen.availableGeometry()
        self.control.resize(min(1280,geometry.width()),min(850,geometry.height()))
        self.control.move(geometry.topLeft())
        if action=="fullscreen": self.control.showFullScreen()

    def screen_added(self,screen):
        self.control.refresh_screens()
        self.control.notice.setText("모니터 연결됨 · 선택한 모니터로 이 화면을 이동할 수 있습니다")

    def screen_removed(self,screen):
        if self.target_screen is screen:
            self.control.showNormal()
            self.target_screen=None
            primary=self.app.primaryScreen()
            if primary:
                self.control.windowHandle().setScreen(primary)
                self.control.move(primary.availableGeometry().topLeft())
            self.control.notice.setText("모니터 연결이 끊겨 기본 화면으로 돌아왔습니다")
        self.control.refresh_screens()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",action="store_true")
    parser.add_argument("--no-start",action="store_true",help="Open UI without accessing a camera")
    parser.add_argument("--quit-after",type=float,default=0,help="Smoke-test duration; no image recording")
    parser.add_argument("--metrics-log",type=Path,help="Optional image-free rotating JSONL performance log")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AnatomyAR")
    app.setStyle("Fusion")
    cv2.setNumThreads(2)
    error = ""
    try:
        settings = load()
    except (OSError,ValueError) as exc:
        settings,error = Settings(),f"설정 파일 손상: 기본값 사용 · {exc}"
    state = AppState(replace(settings,labels=False,debug=False))
    controller = Controller(app,state,args.metrics_log)
    if error: controller.control.notice.setText(error)
    controller.control.showFullScreen()
    if not args.no_start: QTimer.singleShot(100,controller.start)
    if args.quit_after>0: QTimer.singleShot(int(args.quit_after*1000),controller.shutdown)
    return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
