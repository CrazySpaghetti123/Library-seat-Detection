"""偵測事件模擬器：不需攝影機即可端到端驗證後端流程。

用法（後端需先啟動）：
    python scripts/simulate_detection.py A1 person_present
    python scripts/simulate_detection.py A1 person_left_belongings
    python scripts/simulate_detection.py A1 seat_vacant
    python scripts/simulate_detection.py A1 person_present --api https://<後端>.onrender.com --api-key <金鑰>

--api 預設讀環境變數 SEAT_API（未設定為本機），--api-key 預設讀 DETECTION_API_KEY。

搭配把計時參數調短（環境變數）可快速驗證完整逾時流程：
    $env:AWAY_THRESHOLD_MINUTES='1'; $env:CONFIRM_WINDOW_MINUTES='1'; uvicorn src.main:app
"""
import argparse
import os

import httpx

EVENTS = ["person_present", "person_left_belongings", "seat_vacant"]


def main() -> None:
    parser = argparse.ArgumentParser(description="送出一筆偵測事件")
    parser.add_argument("seat_label", help="座位編號，例如 A1")
    parser.add_argument("event", choices=EVENTS)
    parser.add_argument("--api", default=os.getenv("SEAT_API", "http://127.0.0.1:8000"),
                        help="後端網址")
    parser.add_argument("--api-key", default=os.getenv("DETECTION_API_KEY", ""),
                        help="偵測端金鑰")
    args = parser.parse_args()
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    # 雲端後端休眠時第一次請求要等約一分鐘喚醒
    res = httpx.post(f"{args.api.rstrip('/')}/api/detection/events", headers=headers, timeout=90.0,
                     json={"events": [{"seat_label": args.seat_label, "event": args.event}]})
    print(res.status_code, res.json())


if __name__ == "__main__":
    main()
