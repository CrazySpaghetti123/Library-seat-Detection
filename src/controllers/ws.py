"""WebSocket 連線管理與端點（spec: floor-map-web / Real-Time Map Updates）。

- /ws/seats：座位狀態廣播頻道（所有開啟平面圖的瀏覽器）
- 登入學號者於同一連線另收個人通知（away_warning / seat_released / no_show）

Service 層在同步情境（HTTP handler 執行緒、APScheduler 執行緒）觸發掛勾，
透過 run_coroutine_threadsafe 丟回 event loop 送出。
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None  # main.py 啟動時設定
        self._seat_subscribers: set[WebSocket] = set()
        self._student_channels: dict[str, set[WebSocket]] = {}

    # ---- 連線生命週期 ----

    async def connect(self, ws: WebSocket, student_id: str | None) -> None:
        await ws.accept()
        self._seat_subscribers.add(ws)
        if student_id:
            self._student_channels.setdefault(student_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, student_id: str | None) -> None:
        self._seat_subscribers.discard(ws)
        if student_id and student_id in self._student_channels:
            self._student_channels[student_id].discard(ws)
            if not self._student_channels[student_id]:
                del self._student_channels[student_id]

    # ---- 同步程式碼可呼叫的推播介面（services 掛勾用）----

    def publish_seat_update(self, seat_id: int, label: str, status: str) -> None:
        self._submit({"type": "seat_update", "seat_id": seat_id,
                      "label": label, "status": status})

    def publish_notification(self, student_id: str, notification: dict) -> None:
        self._submit({"type": "notification", "data": notification},
                     student_id=student_id)

    def _submit(self, message: dict, student_id: str | None = None) -> None:
        if self.loop is None or self.loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            self._send(message, student_id), self.loop
        )

    async def _send(self, message: dict, student_id: str | None = None) -> None:
        targets = (
            self._student_channels.get(student_id, set())
            if student_id else self._seat_subscribers
        )
        text = json.dumps(message, ensure_ascii=False)
        for ws in list(targets):
            try:
                await ws.send_text(text)
            except Exception:
                self.disconnect(ws, student_id)


manager = ConnectionManager()


@router.websocket("/ws/seats")
async def seats_ws(ws: WebSocket):
    # 學號由 session cookie 帶入（登入後 SessionMiddleware 對 WebSocket 一樣生效）
    student_id = ws.session.get("student_id") if "session" in ws.scope else None
    await manager.connect(ws, student_id)
    try:
        while True:
            await ws.receive_text()  # 前端不需上行訊息，僅維持連線
    except WebSocketDisconnect:
        manager.disconnect(ws, student_id)
