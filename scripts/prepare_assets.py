"""Slice the original RGBA atlas without repainting or replacing its alpha."""
from pathlib import Path
import json
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PARTS = ["head", "torso", "upper_arm", "forearm", "thigh", "shin"]
X = [0, 288, 610, 835, 1040, 1295, 1536]
JOINTS = {"head": [0, 2, 5, 7, 8, 11, 12], "torso": [12, 11, 23, 24],
          "upper_arm": [12, 14], "forearm": [14, 16], "thigh": [24, 26], "shin": [26, 28]}


def main():
    source = cv2.imread(str(ROOT / "assets/source/atlas-v2.png"), cv2.IMREAD_UNCHANGED)
    assert source is not None and source.shape == (1024, 1536, 4)
    assert np.count_nonzero(source[:, :, 3] == 0) > 500_000, "Atlas must have genuine transparency"
    entries = []
    for row, mode in enumerate(("bones", "muscles")):
        y0, y1 = ((0, 480), (480, 1024))[row]
        for col, part in enumerate(PARTS):
            cell = source[y0:y1, X[col]:X[col + 1]].copy()
            ys, xs = np.where(cell[:, :, 3] > 12)
            assert len(xs) > 100
            box = [max(0, int(xs.min()) - 2), max(0, int(ys.min()) - 2),
                   min(cell.shape[1], int(xs.max()) + 3), min(cell.shape[0], int(ys.max()) + 3)]
            cell = cell[box[1]:box[3], box[0]:box[2]]
            path = f"{mode}/{part}.png"
            assert cv2.imwrite(str(ROOT / "assets" / path), cell)
            h, w = cell.shape[:2]
            entries.append({"id": f"{mode}/{part}", "path": path, "part": part, "mode": mode,
                            "size": [w, h], "source_rect": [X[col] + box[0], y0 + box[1], w, h],
                            "joints": JOINTS[part], "side": "right" if col > 1 else "center",
                            "view": "anterior", "anchors": [[.5, .06], [.5, .94]],
                            "torso_anchors": [[.12, .20], [.88, .20], [.76, .84], [.24, .84]],
                            "reference_width": w, "reference_length": .88 * h,
                            "z_order": 0 if part == "torso" else 1, "confidence": .6,
                            "quality_status": "generated; field/anatomical review pending"})
    left = cv2.imread(str(ROOT / "assets/source/atlas-left.png"),cv2.IMREAD_UNCHANGED)
    assert left is not None and left.shape==(1024,1536,4)
    for row,mode in enumerate(("bones","muscles")):
        for col,part in enumerate(PARTS[2:]):
            y0,y1=((0,490),(490,1024))[row]
            cell=left[y0:y1,col*384:(col+1)*384].copy()
            ys,xs=np.where(cell[:,:,3]>12)
            assert len(xs)>100
            cell=cell[max(0,ys.min()-2):min(cell.shape[0],ys.max()+3),max(0,xs.min()-2):min(cell.shape[1],xs.max()+3)]
            path=f"{mode}/{part}_left.png"
            assert cv2.imwrite(str(ROOT/"assets"/path),cell)
            base=next(e for e in entries if e["id"]==f"{mode}/{part}")
            entries.append({**base,"id":f"{mode}/{part}_left","path":path,"side":"left",
                            "size":[cell.shape[1],cell.shape[0]],"source_rect":None,
                            "joints":[j-1 for j in JOINTS[part]],"reference_width":cell.shape[1],
                            "reference_length":.88*cell.shape[0]})
    flex=cv2.imread(str(ROOT/"assets/source/atlas-flex.png"),cv2.IMREAD_UNCHANGED)
    assert flex is not None and flex.shape[2]==4
    fh,fw=flex.shape[:2]
    for row,part in enumerate(("upper_arm","thigh")):
        for col,side in enumerate(("right","left")):
            y0,y1=((0,round(fh*.45)),(round(fh*.45),fh))[row]
            cell=flex[y0:y1,col*(fw//2):(col+1)*(fw//2)].copy()
            ys,xs=np.where(cell[:,:,3]>12)
            assert len(xs)>100
            cell=cell[max(0,ys.min()-2):min(cell.shape[0],ys.max()+3),max(0,xs.min()-2):min(cell.shape[1],xs.max()+3)]
            base_id=f"muscles/{part}"+("_left" if side=="left" else "")
            base=next(e for e in entries if e["id"]==base_id)
            key=base_id+"_flex"
            assert cv2.imwrite(str(ROOT/"assets"/(key+".png")),cell)
            entries.append({**base,"id":key,"path":key+".png","variant":"flexed",
                "size":[cell.shape[1],cell.shape[0]],"source_rect":None,
                "reference_width":cell.shape[1],"reference_length":.88*cell.shape[0]})
    (ROOT / "assets/anchors/atlas.json").write_text(json.dumps({"schema_version": 1, "alpha": "straight",
        "asset_set": "educational-v1", "assets": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(entries)} transparent sprites, including independent left-side assets. Motion quality not certified.")


if __name__ == "__main__":
    main()
