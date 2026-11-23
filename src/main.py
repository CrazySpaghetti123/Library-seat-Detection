"""自習室空位偵測系統——FastAPI 應用進入點（MVC 之組裝處）。

啟動方式：
    uvicorn src.main:app --reload     # 開 http://127.0.0.1:8000/

前端是 frontend/ 的純靜態檔：本機由這裡一併提供（同源）；
雲端部署到 GitHub Pages、以 CORS 呼叫這裡的 API，後端設定 FRONTEND_URL 後
不再提供前端，非 API 網址轉址到正式網址（spec: cloud-deployment）。
"""
import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 將專案根目錄加入路徑，使 `python src/main.py` 與 `uvicorn src.main:app` 皆可執行
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
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
    if config.FRONTEND_URL:
        logger.info("前端由 %s 提供，本服務只提供 API；其餘網址轉址過去", config.FRONTEND_URL)
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


def setup_frontend(app: FastAPI, frontend_url: str) -> None:
    """必須最後呼叫：其餘路徑交給前端。

    - frontend_url 為空（本機開發）：掛載 frontend/ 靜態檔（/ → index.html 登入頁）
    - 已設定（雲端）：不提供前端檔案，GET 非 API 路徑以 307 轉址到正式網址的同一路徑
    """
    if not frontend_url:
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
        return

    @app.get("/{path:path}", include_in_schema=False)
    def redirect_to_frontend(path: str, request: Request):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        target = f"{frontend_url}/{path}"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(target, status_code=307)


setup_frontend(app, config.FRONTEND_URL)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
