from dataclasses import asdict, dataclass, field, fields
import json
import math
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PARTS = ("torso", "upper_arm", "forearm", "thigh", "shin")


@dataclass(frozen=True)
class Settings:
    schema_version: int = 1
    mode: str = "muscles"
    opacity: float = 0.92
    mirror: bool = True
    labels: bool = False
    upper_only: bool = False
    debug: bool = False
    fit: str = "fit"
    background: str = "#101820"
    guidance: str = "얼굴과 양쪽 어깨가 보이게 서 주세요 · 상체만 보여도 괜찮아요"
    standby: bool = False
    camera_index: int = -1
    capture_width: int = 1280
    capture_height: int = 720
    capture_fps: int = 30
    inference_size: int = 640
    inference_interval_ms: int = 33
    confidence: float = 0.6
    smoothing_ms: float = 65.0
    max_age_ms: int = 200
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0
    widths: dict = field(default_factory=lambda: {p: 1.0 for p in PARTS})
    side_widths: dict = field(default_factory=lambda: {s: 1.0 for s in ("left", "right")})
    screen: dict = field(default_factory=dict)
    asset_set: str = "educational-v1"


def validate(data: dict) -> Settings:
    if not isinstance(data, dict) or type(data.get("schema_version", 1)) is not int or data.get("schema_version", 1) != 1:
        raise ValueError("지원하지 않는 설정 형식입니다")
    defaults = asdict(Settings())
    unknown = set(data) - {f.name for f in fields(Settings)}
    if unknown:
        raise ValueError(f"알 수 없는 설정: {', '.join(sorted(unknown))}")
    defaults.update(data)
    for key, options in {"mode": ("bones", "muscles", "original"), "fit": ("fit", "fill"), "asset_set": ("educational-v1",)}.items():
        if defaults[key] not in options:
            raise ValueError(f"{key}: 잘못된 선택")
    for key in ("mirror", "labels", "upper_only", "debug", "standby"):
        if type(defaults[key]) is not bool:
            raise ValueError(f"{key}: 참/거짓 값이 필요합니다")
    ranges = {
        "opacity": (0, 1), "camera_index": (-1, 20), "capture_width": (320, 3840),
        "capture_height": (240, 2160), "capture_fps": (5, 60), "inference_size": (192, 960),
        "inference_interval_ms": (16, 500), "confidence": (.1, .99), "smoothing_ms": (0, 500),
        "max_age_ms": (50, 500), "offset_x": (-.3, .3), "offset_y": (-.3, .3), "scale": (.5, 1.5),
    }
    integer_keys = {k for k, v in asdict(Settings()).items() if type(v) is int}
    for key, (lo, hi) in ranges.items():
        v = defaults[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{key}: 범위 {lo}–{hi}")
        if key in integer_keys and type(v) is not int:
            raise ValueError(f"{key}: 정수가 필요합니다")
    for key, keys in (("widths", PARTS), ("side_widths", ("left", "right"))):
        values = defaults[key]
        if not isinstance(values, dict) or set(values) != set(keys):
            raise ValueError(f"{key}: 보정 항목 누락")
        if any(type(v) not in (int, float) or not math.isfinite(v) or not .5 <= v <= 1.5 for v in values.values()):
            raise ValueError(f"{key}: 폭 보정 범위 0.5–1.5")
        defaults[key] = dict(values)
    bg = defaults["background"]
    if not isinstance(bg, str) or len(bg) != 7 or bg[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in bg[1:]):
        raise ValueError("배경은 #RRGGBB 형식이어야 합니다")
    if not isinstance(defaults["guidance"], str) or len(defaults["guidance"]) > 120:
        raise ValueError("안내문은 120자 이내여야 합니다")
    if not isinstance(defaults["screen"], dict) or any(k not in ("name", "serial", "manufacturer", "model", "geometry") for k in defaults["screen"]):
        raise ValueError("모니터 설정 형식 오류")
    if any(not isinstance(v, str) for v in defaults["screen"].values()):
        raise ValueError("모니터 식별자는 문자열이어야 합니다")
    return Settings(**defaults)


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "AnatomyAR" / "settings.json"


def load(path: Path | None = None) -> Settings:
    path = path or settings_path()
    if not path.exists():
        return Settings()
    return validate(json.loads(path.read_text(encoding="utf-8-sig")))


def save(settings: Settings, path: Path | None = None):
    path = path or settings_path()
    data = asdict(validate(asdict(settings)))
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as f:
            name = f.name
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
