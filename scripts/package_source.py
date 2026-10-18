"""Package the transferable source, local model, assets and evidence; no venv."""
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={".git",".venv",".tools",".python",".uv-cache",".pip-cache",".test-tmp",".bootstrap-smoke",".serena","__pycache__",".pytest_cache","wheelhouse","logs"}


def main():
    destination=ROOT.parent/"AnatomyAR-source.zip"
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative=path.relative_to(ROOT)
            if path.is_file() and not any(part in EXCLUDE or part.startswith(".venv.backup-") for part in relative.parts):
                archive.write(path,Path("AnatomyAR")/relative)
    with zipfile.ZipFile(destination) as archive:
        names=archive.namelist()
        assert archive.testzip() is None
        for required in ("run_windows.bat","requirements.txt","models/pose_landmarker_lite.task","models/gesture_recognizer.task","models/gesture_manifest.json","assets/anchors/atlas.json","docs/VALIDATION.md"):
            assert "AnatomyAR/"+required in names
        assert not any("/.venv/" in name or "/__pycache__/" in name for name in names)
    print(f"{destination.name}: {destination.stat().st_size:,} bytes, {len(names)} files, CRC verified")


if __name__=="__main__": main()
