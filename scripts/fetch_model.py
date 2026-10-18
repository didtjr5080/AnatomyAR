"""Explicit installation step. The app itself never downloads files."""
import hashlib
import json
from pathlib import Path
import urllib.request
import os

ROOT = Path(__file__).resolve().parents[1]


def fetch(manifest_name,filename):
    info = json.loads((ROOT / "models" / manifest_name).read_text(encoding="utf-8"))
    destination = ROOT / "models" / filename
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == info["sha256"]:
        print("Model already verified.")
        return
    temporary = destination.with_suffix(".download")
    try:
        with urllib.request.urlopen(info["url"], timeout=60) as response, temporary.open("wb") as f:
            total = 0
            while chunk := response.read(1024*1024):
                total += len(chunk)
                if total > 32*1024*1024:
                    raise ValueError("Unexpected model size")
                f.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError("Model checksum mismatch; existing model was not replaced")
        os.replace(temporary,destination)
        print("Model downloaded and SHA256 verified.")
    finally:
        temporary.unlink(missing_ok=True)


def main():
    fetch("manifest.json","pose_landmarker_lite.task")
    fetch("gesture_manifest.json","gesture_recognizer.task")


if __name__=="__main__": main()
