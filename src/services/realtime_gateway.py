"""即時推播：以 HTTP POST 通知 Node.js + Socket.IO 閘道（design D2）。

取代 main 分支的 WebSocket ConnectionManager。因為 POST 是同步呼叫，
排程執行緒與請求執行緒可直接呼叫，不需 asyncio.run_coroutine_threadsafe。
推播失敗（閘道未啟動）只記 log、吞例外，不得影響資料庫交易。
"""
import logging

import httpx

from src import config

logger = logging.getLogger(__name__)

# 短逾時避免阻塞請求／排程執行緒
_client = httpx.Client(timeout=2.0)


def _push(event: str, payload: dict, student_id: str | None = None) -> None:
    body: dict = {"event": event, "payload": payload}
    if student_id is not None:
        body["studentId"] = student_id
    try:
        _client.post(
            f"{config.NODE_GATEWAY_URL}/internal/push",
            json=body,
            headers={"X-Gateway-Secret": config.GATEWAY_SECRET},
        )
    except httpx.HTTPError as exc:
        logger.warning("推播至 Node 閘道失敗（%s）：%s", event, exc)


def publish_seat_update(seat_id: int, label: str, status: str) -> None:
    """座位狀態變更 → 全體廣播。簽名與 main 的 WebSocket 掛勾一致。"""
    _push("seat_update", {"seat_id": seat_id, "label": label, "status": status})


def publish_notification(student_id: str, notification: dict) -> None:
    """個人通知 → 推給該學號的 room。簽名與 main 的 WebSocket 掛勾一致。"""
    _push("notification", {"data": notification}, student_id=student_id)
