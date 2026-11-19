"""WebSocket 連線管理與端點（spec: floor-map-web / Real-Time Map Updates）。

- /ws/seats：座位狀態廣播頻道（所有開啟平面圖的瀏覽器）
- 登入學號者於同一連線另收個人通知（away_warning / seat_released / no_show / checked_in / checked_out）
- 瀏覽器無法替 WebSocket 自訂標頭，學生身分以查詢參數 ?token= 帶入；
  沒有或無效的 token 仍可連線收座位廣播，只是收不到個人通知（spec: access-control）
- 前端每 4 分鐘送一則 ping：Render 免費方案把收到的 WebSocket 訊息計為活動，
  有人開著平面圖時後端就不會休眠（spec: cloud-deployment / Keep-Alive During Use）

Service 層在同步情境（HTTP handler 執行緒、APScheduler 執行緒）觸發掛勾，
透過 run_coroutine_threadsafe 丟回 event loop 送出。
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.services.auth_service import verify_token

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

    def publish_seat_update(self, seat_id: int, label: str, status: str,
                            from_status: str = "", source: str = "") -> None:
        self._submit({"type": "seat_update", "seat_id": seat_id,
                      "label": label, "status": status,
                      "from_status": from_status, "source": source})

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
    student_id = verify_token(ws.query_params.get("token"))
    await manager.connect(ws, student_id)
    try:
        while True:
            await ws.receive_text()  # 上行只有心跳 ping，內容不需處理
    except WebSocketDisconnect:
        manager.disconnect(ws, student_id)
