"""YOLOv8 偵測主迴圈（spec: seat-detection）。

執行（需先安裝 requirements-detection.txt）：
    python -m src.detection.detector --source 0
    python -m src.detection.detector --source path\to\video.mp4 --show

判定規則（design.md D5）：
- ROI 內有「人」的偵測框中心點 → person_present
- 無人但有「背包／筆電／書本」 → person_left_belongings（畫面標記橘框）
- 人與物品皆無 → seat_vacant
原始判定經去抖動（連續 5 秒一致）後，僅在狀態改變時上報後端。
"""
import argparse
import logging
import time

logger = logging.getLogger(__name__)

# COCO 類別編號
PERSON_CLASS = 0
BELONGING_CLASSES = {
    24: "backpack", 26: "handbag", 28: "suitcase",
    39: "bottle", 41: "cup",          # 水壺/杯子留桌上是最常見的佔位行為，且辨識穩定
    63: "laptop", 67: "cell phone", 73: "book",
}

RAW_PRESENT = "person_present"
RAW_BELONGINGS = "person_left_belongings"
RAW_VACANT = "seat_vacant"

STATE_COLORS = {  # BGR
    RAW_PRESENT: (0, 0, 220),      # 紅：使用中
    RAW_BELONGINGS: (0, 140, 255),  # 橘：疑似佔位
    RAW_VACANT: (60, 180, 60),      # 綠：空位
}


def classify_seat(roi_points, detections, point_in_polygon) -> str:
    """依 ROI 內的偵測結果判定座位原始狀態。

    detections: [(class_id, center_x, center_y), ...]
    """
    has_person = False
    has_belongings = False
    for class_id, cx, cy in detections:
        if not point_in_polygon(roi_points, (cx, cy)):
            continue
        if class_id == PERSON_CLASS:
            has_person = True
        elif class_id in BELONGING_CLASSES:
            has_belongings = True
    if has_person:
        return RAW_PRESENT
    if has_belongings:
        return RAW_BELONGINGS
    return RAW_VACANT


def fetch_calibrated_seats(api_base: str) -> dict[str, list]:
    """向後端取得已標定 ROI 的座位；未標定者記警告並跳過。"""
    import httpx

    res = httpx.get(f"{api_base.rstrip('/')}/api/seats", timeout=10.0)
    res.raise_for_status()
    rois: dict[str, list] = {}
    for seat in res.json()["seats"]:
        if seat.get("roi") and seat["roi"].get("points"):
            rois[seat["label"]] = seat["roi"]["points"]
        else:
            logger.warning("座位 %s 尚未標定 ROI，跳過偵測", seat["label"])
    return rois


def run(source: str, api_base: str, show: bool, hold_seconds: float,
        model_name: str = "yolov8n.pt", conf: float = 0.35) -> None:
    import cv2
    import numpy as np
    from ultralytics import YOLO

    from src.detection.debounce import StateDebouncer
    from src.detection.reporter import EventReporter

    rois = fetch_calibrated_seats(api_base)
    if not rois:
        logger.error("沒有任何已標定的座位，請先執行 calibrate.py")
        return

    polygons = {label: np.array(pts, dtype=np.int32) for label, pts in rois.items()}

    def point_in_polygon(poly_label_points, point) -> bool:
        return cv2.pointPolygonTest(
            np.array(poly_label_points, dtype=np.int32), point, False) >= 0

    model = YOLO(model_name)
    debouncer = StateDebouncer(hold_seconds=hold_seconds)
    reporter = EventReporter(api_base=api_base)

    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not cap.isOpened():
        logger.error("無法開啟影像來源: %s", source)
        return

    target_classes = [PERSON_CLASS, *BELONGING_CLASSES.keys()]
    last_flush = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                logger.info("影像來源結束")
                break

            results = model.predict(frame, classes=target_classes,
                                    verbose=False, conf=conf)
            detections = []
            for box in results[0].boxes:
                class_id = int(box.cls[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append((class_id, (x1 + x2) / 2, (y1 + y2) / 2))
                if show:
                    # 畫出 YOLO 原始偵測框（白=人、黃=物品），方便調試辨識問題
                    name = results[0].names[class_id]
                    score = float(box.conf[0])
                    box_color = (255, 255, 255) if class_id == PERSON_CLASS else (0, 220, 220)
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)),
                                  box_color, 1)
                    cv2.putText(frame, f"{name} {score:.2f}",
                                (int(x1), int(y1) - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1)

            for label, points in rois.items():
                raw = classify_seat(points, detections, point_in_polygon)
                changed = debouncer.update(label, raw)
                if changed:
                    logger.info("座位 %s 狀態確認為 %s，上報後端", label, changed)
                    reporter.send(label, changed)

                if show:
                    state = debouncer.confirmed_state(label) or raw
                    color = STATE_COLORS[state]
                    cv2.polylines(frame, [polygons[label]], True, color, 2)
                    x, y = polygons[label][0]
                    text = label + (" [IDLE?]" if state == RAW_BELONGINGS else "")
                    cv2.putText(frame, text, (int(x), int(y) - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 每 30 秒嘗試補送離線佇列
            if time.monotonic() - last_flush > 30:
                reporter.flush()
                last_flush = time.monotonic()

            if show:
                cv2.imshow("seat-detection", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description="自習室座位偵測端")
    parser.add_argument("--source", default="0", help="攝影機編號或影片路徑")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="後端 API 位址")
    parser.add_argument("--show", action="store_true", help="顯示偵測畫面")
    parser.add_argument("--hold", type=float, default=5.0, help="去抖動秒數")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLOv8 模型權重")
    parser.add_argument("--conf", type=float, default=0.35,
                        help="偵測信心門檻（辨識不到物品時調低，如 0.25）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    run(args.source, args.api, args.show, args.hold, args.model, args.conf)


if __name__ == "__main__":
    main()
