"""ROI 標定工具（spec: seat-detection / ROI Seat Calibration）。

執行（需安裝 requirements-detection.txt 的 opencv-python 與 httpx）：
    python -m src.detection.calibrate --source 0 --seat A1
    python -m src.detection.calibrate --source 照片.jpg --seat A1
    python -m src.detection.calibrate --source 照片.jpg --seat A1 A2 B1 --out rois.json

操作：
- 在畫面上依序點擊座位的四個角點
- 按 s 儲存並換下一席、r 重新點選、q 離開
- 預設寫入後端 seats.roi；指定 --out 時改存成本機 JSON（不需後端，供照片評估用）
- 加 --box 為立體框選：依序點桌面遠左、遠右、近右、近左四角，再點近左、近右桌腳落地點，
  ROI 取整個桌子長方體在畫面上的外輪廓（斜視角下比四邊形貼合）
- 其他座位已標定的 ROI 以灰色顯示、本座位的舊 ROI 以淡藍色顯示，避免框選範圍互相重疊

手機照片的解析度通常遠大於螢幕，畫面會縮小顯示；
點擊座標會換算回原始解析度後才儲存，ROI 一律以原圖像素為準。
"""
import argparse
import logging
import math

logger = logging.getLogger(__name__)

# 顯示視窗的上限；超過時等比縮小，確保整張畫面都點得到
MAX_DISPLAY_W, MAX_DISPLAY_H = 1600, 900


def display_scale(width: int, height: int,
                  max_w: int = MAX_DISPLAY_W, max_h: int = MAX_DISPLAY_H) -> float:
    """縮小到螢幕放得下的比例；不放大小畫面（如 webcam 640x480 維持 1.0）。"""
    return min(1.0, max_w / width, max_h / height)


def to_original(point, scale: float) -> list[int]:
    """顯示座標 → 原圖座標。"""
    return [round(point[0] / scale), round(point[1] / scale)]


def to_display(point, scale: float) -> tuple[int, int]:
    """原圖座標 → 顯示座標。"""
    return (round(point[0] * scale), round(point[1] * scale))


def save_roi(api_base: str, seat_label: str, points: list[list[int]]) -> bool:
    import httpx

    res = httpx.put(
        f"{api_base.rstrip('/')}/api/seats/{seat_label}/roi",
        json={"points": points}, timeout=10.0,
    )
    if res.status_code == 200:
        logger.info("座位 %s 的 ROI 已儲存: %s", seat_label, points)
        return True
    logger.error("儲存失敗（%s）: %s", res.status_code, res.text)
    return False


def fetch_existing_rois(api_base: str) -> dict[str, list]:
    """取得已標定的 ROI 作為框選參考；後端連不上時回傳空字典，不影響標定。"""
    import httpx

    try:
        res = httpx.get(f"{api_base.rstrip('/')}/api/seats", timeout=5.0)
        res.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("無法取得既有 ROI（%s），僅顯示畫面", exc)
        return {}
    return {s["label"]: s["roi"]["points"] for s in res.json()["seats"]
            if s.get("roi") and s["roi"].get("points")}


def load_json_rois(path: str) -> dict[str, list]:
    from pathlib import Path
    import json

    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_json_roi(path: str, seat_label: str, points) -> bool:
    """合併寫入 JSON（同一座位重框會覆蓋），格式與 evaluate_photos.py --rois 相同。"""
    from pathlib import Path
    import json

    data = load_json_rois(path)
    data[seat_label] = points
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("座位 %s 的 ROI 已存入 %s: %s", seat_label, path, points)
    return True


def convex_hull(points) -> list[list[int]]:
    """Andrew monotone chain；回傳逆時針外輪廓（不含共線點）。"""
    pts = sorted({(int(x), int(y)) for x, y in points})
    if len(pts) <= 2:
        return [list(p) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [list(p) for p in lower[:-1] + upper[:-1]]


def box_bottom(top, floor_near_left, floor_near_right) -> list[list[int]]:
    """由桌面四角與兩支前腳落地點，推算長方體底面四點。

    top 依序為：遠左、遠右、近右、近左（桌面四角）。
    遠端桌腳常被椅子或人擋住，因此只點前腳；後腳的垂直落差依透視比例推算：
    同樣高度的桌腳，畫面上的長度與該處的桌緣寬度成正比（遠端較短）。
    """
    fl, fr, nr, nl = top
    drop_l = (floor_near_left[0] - nl[0], floor_near_left[1] - nl[1])
    drop_r = (floor_near_right[0] - nr[0], floor_near_right[1] - nr[1])
    near_w = math.dist(nl, nr) or 1.0
    ratio = math.dist(fl, fr) / near_w
    return [
        [round(fl[0] + drop_l[0] * ratio), round(fl[1] + drop_l[1] * ratio)],
        [round(fr[0] + drop_r[0] * ratio), round(fr[1] + drop_r[1] * ratio)],
        [round(floor_near_right[0]), round(floor_near_right[1])],
        [round(floor_near_left[0]), round(floor_near_left[1])],
    ]


def box_roi(clicks) -> list[list[int]]:
    """六次點擊（桌面四角 + 近左、近右桌腳落地點）→ 長方體在畫面上的外輪廓。"""
    top = clicks[:4]
    return convex_hull(top + box_bottom(top, clicks[4], clicks[5]))


def box_record(clicks) -> dict:
    """立體框選存檔格式：外輪廓供逐席判定與退路，桌面供桌面優先判定；地板投影保留供分析。"""
    top = [[int(x), int(y)] for x, y in clicks[:4]]
    return {"points": box_roi(clicks), "top": top,
            "floor": box_bottom(top, clicks[4], clicks[5])}


def roi_polygon(value) -> list:
    """ROI 可能是四點 list 或立體框選的 dict，統一取外輪廓。"""
    return value["points"] if isinstance(value, dict) else value


BOX_STEPS = ["桌面遠左角", "桌面遠右角", "桌面近右角", "桌面近左角",
             "近左桌腳落地點", "近右桌腳落地點"]


def calibrate_one(cv2, np, display, scale, seat, existing, box=False):
    """顯示畫面讓使用者點選；按 s 回傳原圖座標的多邊形，按 q 回傳 None。

    box=False：點四角即為 ROI。
    box=True：點桌面四角 + 兩支前腳落地點，ROI 為長方體的外輪廓。
    """
    need = 6 if box else 4
    points: list[list[int]] = []  # 原圖座標
    window = f"Seat {seat} - click {need} points, s=save r=redo q=quit"

    def hint():
        if box and len(points) < need:
            logger.info("%s 請點：%s", seat, BOX_STEPS[len(points)])

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < need:
            points.append(to_original((x, y), scale))
            logger.info("%s 第 %d 點: (%d, %d)", seat, len(points), *points[-1])
            hint()

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)
    logger.info("開始標定座位 %s", seat)
    hint()
    orange, cyan = (0, 140, 255), (255, 220, 0)
    try:
        while True:
            canvas = display.copy()
            for label, value in existing.items():
                pts = roi_polygon(value)
                color = (230, 180, 90) if label == seat else (150, 150, 150)
                poly = np.array([to_display(p, scale) for p in pts], dtype=np.int32)
                cv2.polylines(canvas, [poly], True, color, 1)
                cv2.putText(canvas, label, (int(poly[:, 0].min()), int(poly[:, 1].min()) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            shown = [to_display(p, scale) for p in points]
            top = shown[:4]
            for i, pt in enumerate(shown):
                cv2.circle(canvas, pt, 5, orange, -1)
            for i in range(1, len(top)):
                cv2.line(canvas, top[i - 1], top[i], orange, 2)
            if len(top) == 4:
                cv2.line(canvas, top[3], top[0], orange, 2)
            if box and len(points) == 6:
                bottom = [to_display(p, scale) for p in box_bottom(points[:4], points[4], points[5])]
                for i in range(4):  # 立體線框：底面 + 四根垂直邊
                    cv2.line(canvas, bottom[i], bottom[(i + 1) % 4], orange, 1)
                    cv2.line(canvas, top[i], bottom[i], orange, 1)
                hull = np.array([to_display(p, scale) for p in box_roi(points)], dtype=np.int32)
                cv2.polylines(canvas, [hull], True, cyan, 2)
            cv2.putText(canvas, seat, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, orange, 3)
            cv2.imshow(window, canvas)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                return None
            if key == ord("r"):
                points.clear()
                hint()
            if key == ord("s"):
                if len(points) != need:
                    logger.warning("需要剛好 %d 個點，目前 %d 個", need, len(points))
                    continue
                return box_record(points) if box else points
    finally:
        cv2.destroyWindow(window)


def main() -> None:
    parser = argparse.ArgumentParser(description="座位 ROI 標定工具")
    parser.add_argument("--source", default="0", help="攝影機編號、影片或圖片路徑")
    parser.add_argument("--seat", required=True, nargs="+",
                        help="座位編號，可一次列多個依序標定（例：A1 A2 A3）")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="後端 API 位址")
    parser.add_argument("--out", help="改存成本機 JSON 檔（不需啟動後端）")
    parser.add_argument("--box", action="store_true",
                        help="立體框選：點桌面四角 + 兩支前腳落地點，ROI 取長方體外輪廓（需搭配 --out）")
    args = parser.parse_args()
    if args.box and not args.out:
        parser.error("--box 產生的多邊形超過四點，後端 API 目前只接受四點，請搭配 --out 存成 JSON")

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    import cv2
    import numpy as np

    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        logger.error("無法讀取影像來源: %s", args.source)
        return

    h, w = frame.shape[:2]
    scale = display_scale(w, h)
    display = (cv2.resize(frame, (round(w * scale), round(h * scale)),
                          interpolation=cv2.INTER_AREA) if scale < 1 else frame)
    logger.info("影像解析度 %dx%d，顯示縮放 %.2f（儲存的座標仍為原圖像素）", w, h, scale)
    existing = load_json_rois(args.out) if args.out else fetch_existing_rois(args.api)

    for seat in args.seat:
        result = calibrate_one(cv2, np, display, scale, seat, existing, box=args.box)
        if result is None:  # 按 q 離開
            break
        ok = (save_json_roi(args.out, seat, result) if args.out
              else save_roi(args.api, seat, result))
        if not ok:
            break
        existing[seat] = result
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
