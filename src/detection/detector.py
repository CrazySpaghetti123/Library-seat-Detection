"""YOLOv8 偵測主迴圈（spec: seat-detection）。

執行（需先安裝 requirements-detection.txt）：
    python -m src.detection.detector --source 0
    python -m src.detection.detector --source path\to\video.mp4 --show

判定規則（design.md D5）：
- ROI 內有「人」的接地點（偵測框底邊中點） → person_present
- 無人但有「背包／筆電／書本」的框中心 → person_left_belongings（畫面標記橘框）
- 人與物品皆無 → seat_vacant
原始判定經去抖動（連續 5 秒一致）後，僅在狀態改變時上報後端。

人用接地點、物品用框中心的理由見 changes/ground-point-seat-matching/design.md D1：
ROI 畫在座位平面上，而人是立體物件，非正俯視時框中心會沿透視方向偏離座位平面，
偏移量還隨座位遠近而變；接地點錨定於座位平面，全場可共用同一條判定規則。
"""
import argparse
import logging
import math
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

# 人的 ROI 比對錨點：ground=框底邊中點（接地點，預設）、center=框幾何中心（舊行為）
ANCHOR_GROUND = "ground"
ANCHOR_CENTER = "center"

STATE_COLORS = {  # BGR
    RAW_PRESENT: (0, 0, 220),      # 紅：使用中
    RAW_BELONGINGS: (0, 140, 255),  # 橘：疑似佔位
    RAW_VACANT: (60, 180, 60),      # 綠：空位
}


def anchor_point(class_id, x1, y1, x2, y2,
                 person_anchor: str = ANCHOR_GROUND) -> tuple[float, float]:
    """回傳該偵測框用來比對 ROI 的判定點。

    人取框底邊中點（接地點）；物品一律取框幾何中心——物品框小，兩者差距僅數像素，
    且物品常被桌沿部分遮擋而使底邊比中心更不穩定。
    """
    cx = (x1 + x2) / 2
    if class_id == PERSON_CLASS and person_anchor == ANCHOR_GROUND:
        return cx, y2
    return cx, (y1 + y2) / 2


ANCHOR_LAYERED = "layered"  # 桌面優先：人與物品都先比對桌面、外框為退路，每個偵測只歸一席


def _centroid(points) -> tuple[float, float]:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def _region(seat_roi, key: str):
    """立體框選的 ROI 為 {"points": 外輪廓, "top": 桌面, "floor": 地板投影}；
    舊的四點 ROI（list）沒有分層資訊，各層一律退回整個多邊形。"""
    if isinstance(seat_roi, dict):
        return seat_roi.get(key) or seat_roi["points"]
    return seat_roi


def assign_layered(seat_rois: dict, detections, point_in_polygon) -> dict[str, str]:
    """桌面優先判定所有座位，回傳 {座位: 原始狀態}。

    斜視角下相鄰座位的立體框在畫面上會重疊（後排的框往下延伸會蓋到前排桌面），
    逐席獨立判定時，重疊區的偵測會同時算進兩席。這裡改為每個偵測只歸給一席：
    - 物品（框中心）優先比對「桌面」：物品放在桌上
    - 人（接地點）也優先比對「桌面」：坐在桌後的人下半身被自己的桌子擋住，
      偵測框底邊停在自己桌面的遠端邊緣，而不是腳。2026-11 實拍評估中，
      「人比對地板投影」反而會把前排的人歸給後排（後排地板在畫面上就在前排桌面後方）
    - 不在任何一席的桌面時，退回比對整個外輪廓（框到桌下是為了圈定座位範圍）
    - 同時符合多席時，取桌面中心最近的一席
    """
    has_person = {seat: False for seat in seat_rois}
    has_items = {seat: False for seat in seat_rois}
    for class_id, x1, y1, x2, y2 in detections:
        if class_id == PERSON_CLASS:
            flags = has_person
        elif class_id in BELONGING_CLASSES:
            flags = has_items
        else:
            continue
        point = anchor_point(class_id, x1, y1, x2, y2, ANCHOR_GROUND)
        candidates = [s for s, r in seat_rois.items() if point_in_polygon(_region(r, "top"), point)]
        if not candidates:
            candidates = [s for s, r in seat_rois.items() if point_in_polygon(_region(r, "points"), point)]
        if not candidates:
            continue
        # 多席符合時取桌面中心最近者（退回外框比對時也一樣：人與物品都是依附在桌子旁）
        best = min(candidates, key=lambda s: math.dist(point, _centroid(_region(seat_rois[s], "top"))))
        flags[best] = True
    return {seat: (RAW_PRESENT if has_person[seat]
                   else RAW_BELONGINGS if has_items[seat] else RAW_VACANT)
            for seat in seat_rois}


def classify_seat(roi_points, detections, point_in_polygon,
                  person_anchor: str = ANCHOR_GROUND) -> str:
    """依 ROI 內的偵測結果判定座位原始狀態。

    detections: [(class_id, x1, y1, x2, y2), ...]
    """
    has_person = False
    has_belongings = False
    for class_id, x1, y1, x2, y2 in detections:
        point = anchor_point(class_id, x1, y1, x2, y2, person_anchor)
        if not point_in_polygon(roi_points, point):
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
        model_name: str = "yolov8n.pt", conf: float = 0.35,
        person_anchor: str = ANCHOR_GROUND) -> None:
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

    logger.info("人員判定錨點模式: %s（ground=接地點／center=框中心）", person_anchor)

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
                detections.append((class_id, x1, y1, x2, y2))
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
                    # 標出實際比對 ROI 的判定點，現場可直接看出判定依據
                    ax, ay = anchor_point(class_id, x1, y1, x2, y2, person_anchor)
                    cv2.circle(frame, (int(ax), int(ay)), 4, box_color, -1)

            for label, points in rois.items():
                raw = classify_seat(points, detections, point_in_polygon,
                                    person_anchor)
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
    parser.add_argument("--person-anchor", choices=[ANCHOR_GROUND, ANCHOR_CENTER],
                        default=ANCHOR_GROUND,
                        help="人的 ROI 比對點：ground=接地點（預設）、"
                             "center=框幾何中心（舊行為，供對照實驗與現場回退）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    run(args.source, args.api, args.show, args.hold, args.model, args.conf,
        args.person_anchor)


if __name__ == "__main__":
    main()
