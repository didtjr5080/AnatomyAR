# 설치 및 실행

## 검증 환경과 대상 장비

행사 대상은 **갤럭시북2 / Intel Core i5-12500H / Intel Iris Xe / RAM 16GB**입니다(2026-10-19 사용자 확인). 현재 개발 PC 성능은 이 장비를 대체하지 않습니다.
개발 PC: Windows, Ryzen 3 3100, 약 32GB RAM, GTX 1650. GPU 추론은 사용하지 않습니다.
카메라/외부 모니터와 GPU 드라이버 버전, 전원 모드 및 실제 FPS·지연은 현장에서 기록해야 합니다.

Python 3.11.14를 우선 설치하려 했으나 uv의 다운로드 후 디렉터리 이동이 Windows 파일 잠금으로 실패했습니다.
Python 3.12.8 64비트로 별도 환경을 구성해 실행 검증했습니다. **3.11 호환성 검증 완료를 주장하지 않습니다.**
PySide6 6.12.0은 이 개발 PC에서 QtCore DLL 로딩에 실패해 6.8.3으로 고정했습니다.
설치 성공한 전체 패키지는 `requirements.txt`에 고정했습니다. cv2 제공 패키지는 opencv-contrib-python 하나입니다.

## 온라인 설치 PC

1. Windows 10/11 x64에서 저장소를 복제하거나 GitHub ZIP을 내려받아 압축을 풉니다.
2. `run_windows.bat`을 실행합니다. 첫 실행에는 인터넷이 필요하며 설치가 완료될 때까지 기다립니다.
3. Python이 없으면 체크섬을 확인한 portable uv 0.10.7로 프로젝트 안에 Python 3.12.8과 `.venv`를 만듭니다. 시스템 Python, PATH, 레지스트리는 변경하지 않습니다.
   `setup_windows.bat`은 설치·검증만 수행합니다. 패키지 설치, 두 모델 체크섬, 전체 테스트가 통과한 뒤에만 설치 완료 표시를 남깁니다.
4. 모델 누락/손상 시 인터넷이 연결된 설치 환경에서 아래 명령을 명시적으로 실행합니다.

```powershell
.venv\Scripts\python.exe scripts\fetch_model.py
```

5. `run_windows.bat` 실행 → 카메라 자동 연결. 영상 위 근육/뼈 버튼을 손으로 0.8초 가리키거나 클릭합니다.
   다른 카메라가 선택되면 **컨트롤**의 장치 / 전시 탭에서 재검색 → 번호 선택 → 시작합니다.
   실행 중 장치 설정 변경은 고급 / 저장 탭의 적용/재시작 버튼으로 반영합니다.

포즈 모델과 브이 인식 모델은 모두 프로젝트에 포함되어 있습니다. `models/manifest.json`의 URL은 Google 공식 Pose Lite v1 파일입니다.
SHA-256: `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
제스처 모델 정보는 `models/gesture_manifest.json`, 파일은 `models/gesture_recognizer.task`입니다.
SHA-256: `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482`.
앱 실행 중 자동 다운로드는 없습니다. 최초 설치 단계에서만 uv/Python/PyPI 패키지를 내려받습니다. 임의 모델을 넣으면 체크섬 검증이 실패합니다.

## 행사장 오프라인 준비

행사장과 같은 Windows x64 / Python 3.12 PC에서, 출발 전에 설치와 실행을 끝내는 것이 기본 절차입니다.
인터넷 없는 장비에 새로 설치해야 한다면 온라인 PC에서 wheelhouse를 준비합니다.

```powershell
.venv\Scripts\python.exe -m ensurepip --upgrade
.venv\Scripts\python.exe -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse
```

Python 3.12 x64 설치 파일, 프로젝트, `wheelhouse`, `models`, `assets`를 함께 복사한 뒤
`setup_windows.bat --offline`을 실행합니다. wheelhouse는 기본 제출물에 포함하지 않았습니다.
새 오프라인 PC에는 Python 3.12 x64 설치본을 함께 준비하고 먼저 `py -3.12 -m venv .venv`로 환경을 만듭니다.
또는 출발 전에 같은 행사 PC에서 온라인 설치를 완료합니다. `.venv`는 다른 PC에서 복사하지 않습니다.

## 실행 옵션

```powershell
# 통합 화면 + 카메라 자동 시작
.venv\Scripts\python.exe -m src.app
# 카메라를 열지 않고 통합 화면만 확인
.venv\Scripts\python.exe -m src.app --no-start
# 자동 시작 + 영상 없는 성능 로그
.venv\Scripts\python.exe -m src.app --start --metrics-log logs\event.jsonl
# 30분 종료 예약. 운영자가 현장에 있는 상태에서 실행
.venv\Scripts\python.exe -m src.app --start --quit-after 1800 --metrics-log logs\soak.jsonl
# 카메라 없이 합성 검증 자료 생성
.venv\Scripts\python.exe -m scripts.validate_runtime --evidence
# 카메라 없이 통합 화면과 손 선택 검증 자료 생성
.venv\Scripts\python.exe -m scripts.preview_ui
# 명시적인 온라인 검증: Google 예제 이미지로 실제 브이 인식→화면 고정→재개. 이미지는 저장하지 않음
.venv\Scripts\python.exe -m scripts.validate_gestures
```

설정은 `%LOCALAPPDATA%\AnatomyAR\settings.json`에 저장됩니다. 설치 폴더에 사용자 설정을 쓰지 않습니다.
손상된 설정은 시작 시 원본 파일을 보존하고 기본값으로 열며 운영자에게 오류를 표시합니다.
설정 저장은 임시 파일 기록·flush·fsync 후 원자 교체입니다.

## 문제 해결

- 모델 오류: 체크섬과 파일 존재를 확인하고 명시적 모델 확보 스크립트로 복구합니다.
- 자산 오류: `assets/anchors/atlas.json`과 모든 PNG를 복구합니다. 원본에서 `scripts/prepare_assets.py`로 재생성할 수 있습니다.
- 카메라 오류: Windows 카메라 개인정보 설정, USB, 다른 앱 점유 확인 → 설정에서 카메라 재검색 → 번호 선택 → 다시 시작.
- 자동 선택은 OpenCV 번호 0~5를 순서대로 검사하고, DirectShow/Media Foundation에서 실제 프레임을 읽은 장치를 사용합니다. 기존 설정의 번호 0도 실패하면 다음 번호를 시도합니다. 명시적으로 선택한 양수 번호는 다른 장치로 대체하지 않습니다.
- 장치 이름 목록과 OpenCV 번호를 대응시키지 않습니다. 재검색 목록의 번호·백엔드·해상도와 실제 영상을 확인합니다. 가상 카메라가 먼저 잡히면 원하는 번호를 직접 선택합니다. 재검색은 현재 캡처를 정지한 후 진행합니다.
- 연결 확인 실패를 물리적 카메라 부재로 단정하지 않습니다. 개발 PC에서는 번호 0이 실패했지만 번호 1의 영상은 정상 수신했습니다.
- Qt DLL 오류: 기존 패키지를 섞지 말고 새 venv에 고정 requirements를 설치합니다. Microsoft VC++ 런타임/Windows 업데이트 상태도 확인합니다.
- 한글 글꼴: Windows 맑은 고딕을 사용합니다. offscreen 검증에서도 OS의 `Fonts/malgun.ttf`를 명시적으로 로드합니다. 글꼴 파일을 재배포하지 않습니다.
- 카메라 드라이버 read가 영구 정지하면 정상 해제가 지연될 수 있습니다. 앱은 GUI를 막거나 worker를 강제 파괴하지 않고 해제를 기다립니다. 현장 장치 분리 시험이 필요합니다.
- GitHub ZIP에서 실행할 때는 압축을 완전히 푼 뒤 실행합니다. 최초 설치가 차단되면 인터넷/회사 보안 정책과 GitHub·PyPI 접속을 확인합니다.
- 이동 후 기존 `.venv`가 실행되지 않으면 자동 설치가 이를 `.venv.backup-...`로 보존하고 새 환경을 구성합니다.

Windows 실행 파일 패키징은 아직 하지 않았습니다. 소스/venv 실행 방식으로 제공합니다.
