"""照片集離線評估：量測座位判定準確率，比較接地點與框中心兩種錨點。

用法（需安裝 requirements-detection.txt；後端需啟動以讀取 ROI，或改用 --rois 指定 JSON）：

    python scripts/evaluate_photos.py --photos C:\\Users\\User\\OneDrive\\picture
    python scripts/evaluate_photos.py --photos <資料夾> --save-images all --blur-faces

標註檔預設讀 <照片資料夾>/labels.txt，格式見 src/detection/evaluation.py；
依拍攝清單拍的話，可直接複製 scripts/eval_shot_plan.txt 再修改不同之處。

流程：
  1. 依 EXIF 拍攝時間排序照片，對應標註檔的順序（張數必須一致）
  2. 檢查格式、解析度、旋轉標記，以及每張相對第 1 張的畫面偏移
  3. 每張跑一次 YOLO，對每個座位分別以接地點、框中心判定
  4. 與標註比對，輸出 report.md、results.csv、photo_order.csv 與標示圖

輸出位於 eval_output/<時間戳>/（已列入 .gitignore，照片含人像不應進版控）。
"""
import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.detection.detector import (  # noqa: E402
    ANCHOR_CENTER,
    ANCHOR_GROUND,
    ANCHOR_LAYERED,
    BELONGING_CLASSES,
    PERSON_CLASS,
    anchor_point,
    assign_layered,
    classify_seat,
)
from src.detection.evaluation import (  # noqa: E402
    RAW_TO_KIND,
    LabelError,
    Record,
    compute_stats,
    format_report,
    occluded_seats,
    order_by_capture,
    parse_exif_datetime,
    parse_labels,
    resolve_truth,
    sort_seats,
)

PHOTO_EXTS = {".jpg", ".jpeg", ".png"}
HEIC_EXTS = {".heic", ".heif"}
MODES = (ANCHOR_LAYERED, ANCHOR_GROUND, ANCHOR_CENTER)
MODE_ABBR = {ANCHOR_LAYERED: "L", ANCHOR_GROUND: "G", ANCHOR_CENTER: "C"}
ABBR = {"person": "P", "belongings": "B", "vacant": "V"}  # 標示圖用（OpenCV 無法繪製中文）


class EvalError(RuntimeError):
    """可預期的使用錯誤：印出訊息後結束，不印 traceback。"""


# ---- 照片 ----

def list_photos(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise EvalError(f"找不到照片資料夾：{folder}")
    files = [p for p in folder.iterdir() if p.is_file()]
    heic = [p.name for p in files if p.suffix.lower() in HEIC_EXTS]
    if heic:
        raise EvalError(
            f"發現 HEIC 格式照片（{len(heic)} 張，例如 {heic[0]}），OpenCV 無法讀取。\n"
            "請把 iPhone「設定 → 相機 → 格式」改為「最相容」後重拍，或先轉成 JPEG。")
    photos = [p for p in files if p.suffix.lower() in PHOTO_EXTS]
    if not photos:
        raise EvalError(f"資料夾內沒有 JPEG / PNG 照片：{folder}")
    return photos


def read_exif(path: Path) -> dict:
    """讀取拍攝時間、旋轉標記與原始尺寸（只讀檔頭，很快）。"""
    from PIL import Image

    with Image.open(path) as img:
        exif = img.getexif()
        sub = exif.get_ifd(0x8769)  # Exif IFD
        taken = parse_exif_datetime(sub.get(36867) or exif.get(306), sub.get(37521))
        return {"time": taken, "orientation": exif.get(274, 1), "size": img.size}


def load_frame(path: Path):
    """與 calibrate.py 相同的讀圖方式，確保 ROI 座標系一致。"""
    import cv2

    cap = cv2.VideoCapture(str(path))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise EvalError(f"無法讀取照片：{path}")
    return frame


def estimate_drift(ref_gray, gray, roi_points, max_side=1280):
    """以 ORB 特徵點估算相對參考照的畫面變動，回傳 ROI 角點的最大位移（像素）與旋轉角。

    畫面中的人會移動，但牆面、桌椅等背景佔多數，RANSAC 可排除人身上的特徵點。
    無法估算（特徵點不足）時回傳 None。
    """
    import cv2
    import numpy as np

    scale = min(1.0, max_side / max(ref_gray.shape))
    a = cv2.resize(ref_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    b = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    orb = cv2.ORB_create(4000)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 30 or len(kb) < 30:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 20:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in good])
    dst = np.float32([kb[m.trainIdx].pt for m in good])
    M, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None:
        return None
    pts = np.float32([p for poly in roi_points for p in poly]) * scale
    moved = pts @ M[:, :2].T + M[:, 2]
    shift = float(np.max(np.linalg.norm(moved - pts, axis=1))) / scale
    angle = math.degrees(math.atan2(M[1, 0], M[0, 0]))
    return shift, angle


# ---- 判定 ----

def detect(model, frame, conf, imgsz):
    kwargs = {"classes": [PERSON_CLASS, *BELONGING_CLASSES], "verbose": False, "conf": conf}
    if imgsz:
        kwargs["imgsz"] = imgsz
    boxes = model.predict(frame, **kwargs)[0].boxes
    return [(int(b.cls[0]), *b.xyxy[0].tolist()) for b in boxes]


def point_in_polygon(points, point) -> bool:
    import cv2
    import numpy as np

    return cv2.pointPolygonTest(np.array(points, dtype=np.int32),
                                (float(point[0]), float(point[1])), False) >= 0


# ---- 標示圖 ----

def blur_heads(frame, detections, ratio=0.5):
    """模糊每個被偵測到的人的上半部（框高的 ratio 比例）。未被偵測到的人不會被模糊。

    比例刻意偏大：人被畫面切到腰部、或身體前傾時，頭部可能佔框高將近一半，
    只模糊頂端 25% 會漏掉整張臉。論文附圖以呈現座位與判定為主，多模糊一些沒有代價。
    """
    import cv2

    h, w = frame.shape[:2]
    for cls, x1, y1, x2, y2 in detections:
        if cls != PERSON_CLASS:
            continue
        top, bottom = int(max(0, y1)), int(min(h, y1 + (y2 - y1) * ratio))
        left, right = int(max(0, x1)), int(min(w, x2))
        if bottom - top < 4 or right - left < 4:
            continue
        region = frame[top:bottom, left:right]
        k = max(15, (min(region.shape[:2]) // 2) | 1)
        frame[top:bottom, left:right] = cv2.GaussianBlur(region, (k, k), 0)
    return frame


def draw_annotations(frame, rois, detections, truth, preds):
    """ROI 依桌面優先判定的對錯著色（綠＝對、紅＝錯），並標出兩種判定點。

    標籤：T=標註、L=桌面優先、G=接地點、C=框中心；P=人、B=物品、V=空。
    """
    import cv2
    import numpy as np

    h, w = frame.shape[:2]
    t = max(2, w // 700)
    font = max(0.6, w / 2200)
    for cls, x1, y1, x2, y2 in detections:
        is_person = cls == PERSON_CLASS
        color = (255, 255, 255) if is_person else (0, 220, 220)
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, max(1, t // 2))
        gx, gy = anchor_point(cls, x1, y1, x2, y2, ANCHOR_GROUND)
        cx, cy = anchor_point(cls, x1, y1, x2, y2, ANCHOR_CENTER)
        if is_person:
            cv2.circle(frame, (int(gx), int(gy)), t * 3, (0, 200, 0), -1)          # 接地點
            cv2.drawMarker(frame, (int(cx), int(cy)), (0, 140, 255),
                           cv2.MARKER_CROSS, t * 8, t)                               # 框中心
        else:
            cv2.circle(frame, (int(cx), int(cy)), t * 2, color, -1)
    for seat, pts in rois.items():
        truth_kind = truth[seat].kind
        ok = preds[seat][ANCHOR_LAYERED] == truth_kind
        color = (60, 200, 60) if ok else (40, 40, 230)
        poly = np.array(pts, dtype=np.int32)
        cv2.polylines(frame, [poly], True, color, t)
        text = f"{seat} T:{ABBR[truth_kind]} " + " ".join(
            f"{MODE_ABBR[m]}:{ABBR[preds[seat][m]]}" for m in MODES)
        x, y = int(poly[:, 0].min()), int(poly[:, 1].min()) - t * 3
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font, t)
        cv2.rectangle(frame, (x, y - th - t * 2), (x + tw + t * 2, y + t), (0, 0, 0), -1)
        cv2.putText(frame, text, (x + t, y), cv2.FONT_HERSHEY_SIMPLEX, font, color, t)
    return frame


# ---- 主流程 ----

def load_rois(args) -> dict[str, list]:
    if args.rois:
        data = json.loads(Path(args.rois).read_text(encoding="utf-8"))
        return data  # 值為四點 list，或立體框選的 {"points", "top", "floor"}
    from src.detection.detector import fetch_calibrated_seats

    try:
        return fetch_calibrated_seats(args.api)
    except Exception as exc:  # noqa: BLE001  連線失敗時給出可行動的訊息
        raise EvalError(f"無法從後端取得 ROI（{args.api}）：{exc}\n"
                        "請先啟動後端（uvicorn src.main:app），或以 --rois 指定 ROI 檔") from exc


def run(args) -> int:
    import cv2
    from ultralytics import YOLO

    photo_dir = Path(args.photos)
    labels_path = Path(args.labels) if args.labels else photo_dir / "labels.txt"
    if not labels_path.exists():
        raise EvalError(f"找不到標註檔：{labels_path}\n"
                        "可複製 scripts/eval_shot_plan.txt 過去，再修改與實際拍攝不同的地方")
    try:
        shots = parse_labels(labels_path.read_text(encoding="utf-8-sig"))
    except LabelError as exc:
        raise EvalError(f"標註檔格式錯誤（{labels_path.name}）：{exc}") from exc

    # 1. 依拍攝時間排序並對應標註
    photos = list_photos(photo_dir)
    meta_by_name = {p.name: read_exif(p) for p in photos}
    order, method = order_by_capture([(n, m["time"]) for n, m in meta_by_name.items()])
    if method != "exif":
        print("警告：部分照片沒有拍攝時間（EXIF），改依檔名排序，請確認順序是否正確")
    if len(order) != len(shots):
        raise EvalError(f"照片 {len(order)} 張，但標註檔有 {len(shots)} 行，兩者必須一致。\n"
                        "拍壞的照片請在標註檔寫「廢片」，不要刪掉那一行")

    rois_all = load_rois(args)
    used_shots = [s for s in shots if not s.skip]
    labelled = set().union(*(s.seats for s in used_shots)) if used_shots else set()
    if any(s.all_vacant for s in used_shots) and not labelled:
        labelled = set(rois_all)
    seats = sort_seats(s for s in rois_all if s in labelled)
    if not seats:
        raise EvalError("標註檔中的座位都沒有 ROI，請先用 calibrate.py 框選座位")
    no_roi = sort_seats(s for s in labelled if s not in rois_all)
    if no_roi:
        print(f"警告：以下座位有標註但沒有 ROI，略過不評估：{'、'.join(no_roi)}")
    regions = {s: rois_all[s] for s in seats}  # 含分層資訊（若有）
    rois = {s: (v["points"] if isinstance(v, dict) else v) for s, v in regions.items()}  # 外輪廓
    if not any(isinstance(v, dict) for v in regions.values()):
        print("提醒：ROI 不是用 --box 立體框選的，桌面優先判定會退回以整個框比對")
    truths = {s.index: resolve_truth(s, seats) for s in used_shots}

    # 2. 一致性檢查（只讀檔頭，在跑 YOLO 之前就擋下）
    ref_shot = used_shots[0]
    ref_name = order[ref_shot.index - 1]
    ref_meta = meta_by_name[ref_name]
    bad = [n for n in order
           if (meta_by_name[n]["size"], meta_by_name[n]["orientation"])
           != (ref_meta["size"], ref_meta["orientation"])]
    if bad:
        raise EvalError(f"以下照片的解析度或旋轉方向與第 {ref_shot.index} 張（{ref_name}）不同，"
                        f"ROI 會錯位：{'、'.join(bad)}\n同一組請用同一支手機、同一設定、不要變焦或裁切")
    if ref_meta["orientation"] not in (1, None):
        print("警告：照片帶有旋轉標記（可能是直拍）。建議橫拍，避免人像被轉向而影響偵測")
    if not ref_shot.all_vacant:
        print(f"提醒：第 {ref_shot.index} 張不是「全空」。偏移檢查以它為基準，"
              "ROI 也應該用同一張照片框選")

    ref_frame = load_frame(photo_dir / ref_name)
    fh, fw = ref_frame.shape[:2]
    outside = [s for s, pts in rois.items()
               if any(not (0 <= x < fw and 0 <= y < fh) for x, y in pts)]
    if outside:
        raise EvalError(f"座位 {'、'.join(outside)} 的 ROI 超出照片範圍（{fw}x{fh}），"
                        "可能是用不同解析度的畫面框選的，請用這組照片重新框選")
    ref_gray = cv2.cvtColor(ref_frame, cv2.COLOR_BGR2GRAY)
    max_drift = args.max_drift if args.max_drift is not None else fw * 0.015

    out_dir = Path(args.out) if args.out else ROOT / "eval_output" / datetime.now().strftime("%Y%m%d-%H%M%S")
    img_dir = out_dir / "images"
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rois.json").write_text(json.dumps(regions, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3. 逐張判定
    model = YOLO(args.model)
    records: list[Record] = []
    order_rows = []
    drifted, unknown_drift = [], []
    for shot in shots:
        name = order[shot.index - 1]
        row = {"張": shot.index, "檔名": name,
               "拍攝時間": meta_by_name[name]["time"] or "", "ROI最大偏移px": "", "旋轉角": "", "狀態": ""}
        order_rows.append(row)
        if shot.skip:
            row["狀態"] = "廢片"
            continue

        frame = load_frame(photo_dir / name)
        drift = estimate_drift(ref_gray, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), list(rois.values()))
        if drift is None:
            unknown_drift.append(shot.index)
            row["狀態"] = "偏移無法估算"
        else:
            row["ROI最大偏移px"], row["旋轉角"] = f"{drift[0]:.1f}", f"{drift[1]:.2f}"
            if drift[0] > max_drift and not args.keep_drifted:
                drifted.append((shot.index, drift[0]))
                row["狀態"] = "偏移過大，排除"
                continue
        row["狀態"] = row["狀態"] or "使用"

        dets = detect(model, frame, args.conf, args.imgsz)
        truth = truths[shot.index]
        occluded = occluded_seats(truth)
        layered = assign_layered(regions, dets, point_in_polygon)
        preds = {}
        for seat, pts in rois.items():
            preds[seat] = {m: RAW_TO_KIND[classify_seat(pts, dets, point_in_polygon, m)]
                           for m in (ANCHOR_GROUND, ANCHOR_CENTER)}
            preds[seat][ANCHOR_LAYERED] = RAW_TO_KIND[layered[seat]]
            for m in MODES:
                records.append(Record(
                    shot=shot.index, photo=name, seat=seat, mode=m,
                    truth=truth[seat].kind, pred=preds[seat][m], item=truth[seat].item,
                    detail=truth[seat].detail, occluded=seat in occluded, walkway=shot.walkway))

        has_error = any(preds[s][m] != truth[s].kind for s in rois for m in MODES)
        if args.save_images == "all" or (args.save_images == "errors" and has_error):
            img_dir.mkdir(exist_ok=True)
            canvas = (blur_heads(frame.copy(), dets, args.blur_ratio)
                      if args.blur_faces else frame.copy())
            draw_annotations(canvas, rois, dets, truth, preds)
            cv2.imwrite(str(img_dir / f"{shot.index:02d}_{Path(name).stem}.jpg"), canvas)
        if args.blur_faces:
            fig_dir.mkdir(exist_ok=True)
            cv2.imwrite(str(fig_dir / f"{shot.index:02d}_{Path(name).stem}.jpg"),
                        blur_heads(frame.copy(), dets, args.blur_ratio))
        print(f"  第 {shot.index:2d} 張 {name}：完成")

    if not records:
        raise EvalError("沒有可評估的照片（可能全部是廢片或偏移過大）")

    # 4. 統計與輸出
    stats = {m: compute_stats(records, m) for m in MODES}
    used = len({r.shot for r in records})
    meta = {
        "照片": f"{len(shots)} 張；評估 {used} 張，廢片 {sum(s.skip for s in shots)} 張，"
              f"偏移排除 {len(drifted)} 張",
        "座位": f"{len(seats)} 席（{'、'.join(seats)}）",
        "判定樣本": f"每種方法 {stats[ANCHOR_GROUND].total} 個（評估張數 × 座位數）",
        "方法": "框中心＝人與物品都取框中心、逐席判定（舊）；接地點＝人改取框底邊中點、逐席判定；"
              "桌面優先＝人（接地點）與物品（框中心）都先比對桌面、不在任何桌面才比對整個框，每個偵測只歸一席",
        "排序依據": "EXIF 拍攝時間" if method == "exif" else "檔名（缺少拍攝時間）",
        "模型": f"{args.model}，信心門檻 {args.conf}" + (f"，imgsz {args.imgsz}" if args.imgsz else ""),
        "偏移門檻": f"{max_drift:.0f} px（ROI 角點最大位移）",
    }
    if drifted:
        meta["偏移排除"] = "、".join(f"第 {i} 張（{d:.0f}px）" for i, d in drifted)
    if unknown_drift:
        meta["偏移無法估算（仍納入評估）"] = "、".join(f"第 {i} 張" for i in unknown_drift)

    report = format_report(stats, records, meta)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    with open(out_dir / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["張", "檔名", "座位", "方法", "正確", "判定", "是否判對", "物品", "標註原文", "被遮擋", "走道"])
        for r in records:
            w.writerow([r.shot, r.photo, r.seat, r.mode, r.truth, r.pred, int(r.correct),
                        r.item or "", r.detail, int(r.occluded), int(r.walkway)])
    with open(out_dir / "photo_order.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(order_rows[0]))
        w.writeheader()
        w.writerows(order_rows)

    print()
    print(report)
    print(f"輸出位置：{out_dir}")
    if args.blur_faces:
        print("注意：只有被偵測到的人會被打碼，公開圖片前請逐張目視檢查")
    return 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # 主控台為 cp950，避免中文訊息編碼失敗
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="照片集離線評估：比較接地點與框中心的座位判定準確率")
    parser.add_argument("--photos", required=True, help="照片資料夾")
    parser.add_argument("--labels", help="標註檔（預設：<照片資料夾>/labels.txt）")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="後端 API 位址（讀取 ROI）")
    parser.add_argument("--rois", help="改從 JSON 讀 ROI：{\"A1\": [[x,y]x4], ...}")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLOv8 權重（預設與偵測端相同）")
    parser.add_argument("--conf", type=float, default=0.35, help="偵測信心門檻（預設與偵測端相同）")
    parser.add_argument("--imgsz", type=int, help="推論尺寸（預設與偵測端相同；小物品可試 1280）")
    parser.add_argument("--max-drift", type=float, help="ROI 最大容許偏移像素（預設：照片寬度的 1.5%%）")
    parser.add_argument("--keep-drifted", action="store_true", help="偏移過大的照片仍納入評估")
    parser.add_argument("--save-images", choices=["none", "errors", "all"], default="errors",
                        help="輸出標示圖：none / errors（有判錯的照片，預設）/ all")
    parser.add_argument("--blur-faces", action="store_true",
                        help="標示圖打碼人像，並另存打碼版原圖到 figures/（供論文與簡報使用）")
    parser.add_argument("--blur-ratio", type=float, default=0.5,
                        help="打碼範圍：人像框由上往下的比例（預設 0.5，臉沒蓋到時調高）")
    parser.add_argument("--out", help="輸出資料夾（預設：eval_output/<時間戳>）")
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except EvalError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
