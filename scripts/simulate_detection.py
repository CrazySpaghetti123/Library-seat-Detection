"""偵測事件模擬器：不需攝影機即可端到端驗證後端流程。

用法（後端需先啟動）：
    python scripts/simulate_detection.py A1 person_present
    python scripts/simulate_detection.py A1 person_left_belongings
    python scripts/simulate_detection.py A1 seat_vacant

搭配把計時參數調短（環境變數）可快速驗證完整逾時流程：
    $env:AWAY_THRESHOLD_MINUTES='1'; $env:CONFIRM_WINDOW_MINUTES='1'; uvicorn src.main:app
"""
import sys

import httpx

API = "http://127.0.0.1:8000"


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    seat_label, event = sys.argv[1], sys.argv[2]
    res = httpx.post(f"{API}/api/detection/events",
                     json={"events": [{"seat_label": seat_label, "event": event}]})
    print(res.status_code, res.json())


if __name__ == "__main__":
    main()
