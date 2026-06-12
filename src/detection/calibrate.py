"""ROI 標定工具（spec: seat-detection / ROI Seat Calibration）。

執行（需安裝 requirements-detection.txt 的 opencv-python 與 httpx）：
    python -m src.detection.calibrate --source 0 --seat A1

操作：
- 在畫面上依序點擊座位的四個角點
- 按 s 儲存（寫入後端 seats.roi）、r 重新點選、q 離開
"""
import argparse
import logging

logger = logging.getLogger(__name__)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="座位 ROI 標定工具")
    parser.add_argument("--source", default="0", help="攝影機編號、影片或圖片路徑")
    parser.add_argument("--seat", required=True, help="座位編號（例：A1）")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="後端 API 位址")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    import cv2

    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        logger.error("無法讀取影像來源: %s", args.source)
        return

    points: list[list[int]] = []
    window = f"標定座位 {args.seat}（點四角，s=儲存 r=重來 q=離開）"

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([x, y])
            logger.info("第 %d 點: (%d, %d)", len(points), x, y)

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)

    while True:
        canvas = frame.copy()
        for i, (x, y) in enumerate(points):
            cv2.circle(canvas, (x, y), 5, (0, 140, 255), -1)
            if i > 0:
                cv2.line(canvas, tuple(points[i - 1]), (x, y), (0, 140, 255), 2)
        if len(points) == 4:
            cv2.line(canvas, tuple(points[3]), tuple(points[0]), (0, 140, 255), 2)
        cv2.imshow(window, canvas)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r"):
            points.clear()
        if key == ord("s"):
            if len(points) != 4:
                logger.warning("需要剛好四個點，目前 %d 個", len(points))
                continue
            if save_roi(args.api, args.seat, points):
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
