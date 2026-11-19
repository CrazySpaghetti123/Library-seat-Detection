"""事件上報與離線佇列（spec: seat-detection / State Change Synchronization）。

上報失敗（後端離線）時事件存入本地 JSONL 佇列，
連線恢復後依序補送，偵測流程不中斷。

後端設定 DETECTION_API_KEY 時，上報與補送都需帶 X-API-Key（spec: access-control）。
雲端後端（Render 免費方案）閒置會休眠，Heartbeat 在開館時段定時呼叫 /api/health
讓它保持清醒，離席逾時才能準時處理（spec: cloud-deployment / Keep-Alive During Use）。
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class EventReporter:
    def __init__(self, api_base: str = "http://127.0.0.1:8000",
                 queue_path: str = "detection_queue.jsonl", api_key: str = "",
                 transport: httpx.BaseTransport | None = None):
        self.api_base = api_base.rstrip("/")
        self.queue_path = Path(queue_path)
        headers = {"X-API-Key": api_key} if api_key else {}
        self.client = httpx.Client(timeout=5.0, headers=headers, transport=transport)

    def send(self, seat_label: str, event: str) -> None:
        """送出單一事件；失敗則入列，成功則順便補送積壓事件。"""
        pending = self._load_queue()
        pending.append({"seat_label": seat_label, "event": event})
        if self._post(pending):
            self._clear_queue()
        else:
            self._save_queue(pending)
            logger.warning("後端連線失敗，事件已入列（佇列 %d 筆）", len(pending))

    def flush(self) -> bool:
        """嘗試補送佇列中的事件。"""
        pending = self._load_queue()
        if not pending:
            return True
        if self._post(pending):
            self._clear_queue()
            logger.info("離線佇列補送完成（%d 筆）", len(pending))
            return True
        return False

    # ---- 內部 ----

    def _post(self, events: list[dict]) -> bool:
        try:
            res = self.client.post(f"{self.api_base}/api/detection/events",
                                   json={"events": events})
        except httpx.HTTPError:
            return False
        if res.status_code == 401:
            # 金鑰錯誤不會自己好：明確記錄，事件仍留在佇列，修正金鑰後重啟即可補送
            logger.error("後端拒絕偵測事件：金鑰錯誤或未提供（--api-key / DETECTION_API_KEY）")
        return res.status_code == 200

    def _load_queue(self) -> list[dict]:
        if not self.queue_path.exists():
            return []
        lines = self.queue_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def _save_queue(self, events: list[dict]) -> None:
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
        self.queue_path.write_text(text + "\n", encoding="utf-8")

    def _clear_queue(self) -> None:
        if self.queue_path.exists():
            self.queue_path.unlink()


def in_open_hours(hour: int, open_hour: int, close_hour: int) -> bool:
    """當地時間 hour 是否在開館時段 [open_hour, close_hour)；跨午夜（如 22–6）也成立。"""
    if open_hour == close_hour:
        return True  # 視為全天
    if open_hour < close_hour:
        return open_hour <= hour < close_hour
    return hour >= open_hour or hour < close_hour


class Heartbeat:
    """開館時段每隔 interval_minutes 呼叫一次 /api/health；interval 為 0 即關閉。

    只在開館時段送出：整天喚醒後端會讓 Neon 免費運算時數超額（design D6）。
    以偵測電腦的本機時間判斷時段。
    """

    def __init__(self, client: httpx.Client, api_base: str, interval_minutes: float,
                 open_hour: int, close_hour: int, clock=time.monotonic, now=datetime.now):
        self.client = client
        self.url = f"{api_base.rstrip('/')}/api/health"
        self.interval = interval_minutes * 60
        self.open_hour, self.close_hour = open_hour, close_hour
        self.clock, self.now = clock, now
        self.last = None

    def due(self) -> bool:
        if self.interval <= 0 or not in_open_hours(self.now().hour, self.open_hour, self.close_hour):
            return False
        return self.last is None or self.clock() - self.last >= self.interval

    def tick(self) -> bool:
        """到期就送出，回傳是否有送出（失敗也算送出，下個週期再試）。"""
        if not self.due():
            return False
        self.last = self.clock()
        try:
            self.client.get(self.url)
        except httpx.HTTPError as exc:
            logger.warning("健康檢查失敗（%s），後端可能正在喚醒", exc)
        return True
