"""自習室空位偵測系統——FastAPI 應用進入點（MVC 之組裝處）。

啟動方式：
    uvicorn src.main:app --reload     # 開 http://127.0.0.1:8000/

前端是 frontend/ 的純靜態檔：本機由這裡一併提供（同源），
雲端則部署到 GitHub Pages、以 CORS 呼叫這裡的 API（spec: cloud-deployment）。
"""
import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 將專案根目錄加入路徑，使 `python src/main.py` 與 `uvicorn src.main:app` 皆可執行
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src import config
from src.controllers import api, reports, ws
from src.services import scheduler
from src.services.auth_service import unprotected_endpoints
from src.services.notification_service import NotificationService
from src.services.seat_state_service import SeatStateService

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 取得 event loop 供同步程式碼（service 掛勾、排程執行緒）推播 WebSocket
    ws.manager.loop = asyncio.get_running_loop()
    SeatStateService.on_transition_hooks.append(ws.manager.publish_seat_update)
    NotificationService.on_notify_hooks.append(ws.manager.publish_notification)
    for item in unprotected_endpoints():
        logger.warning("未受保護：%s", item)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="自習室空位偵測系統", lifespan=lifespan)
if config.ALLOWED_ORIGINS:
    # 只允許列出的前端網址；以 Bearer token 驗證，不需要 credentials（design D5）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
    )

app.include_router(api.router)
app.include_router(reports.router)
app.include_router(ws.router)
# 最後掛載：其餘路徑都交給靜態前端（/ → index.html 登入頁）
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
