"""事件上報與離線佇列（spec: seat-detection / State Change Synchronization）。

上報失敗（後端離線）時事件存入本地 JSONL 佇列，
連線恢復後依序補送，偵測流程不中斷。
"""
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class EventReporter:
    def __init__(self, api_base: str = "http://127.0.0.1:8000",
                 queue_path: str = "detection_queue.jsonl"):
        self.api_base = api_base.rstrip("/")
        self.queue_path = Path(queue_path)
        self.client = httpx.Client(timeout=5.0)

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
            return res.status_code == 200
        except httpx.HTTPError:
            return False

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
