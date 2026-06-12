"""自習室空位偵測系統——FastAPI 應用進入點（MVC 之組裝處）。

啟動方式：
    uvicorn src.main:app --reload
"""
import asyncio
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 將專案根目錄加入路徑，使 `python src/main.py` 與 `uvicorn src.main:app` 皆可執行
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src import config
from src.controllers import api, pages, reports, ws
from src.services import scheduler
from src.services.notification_service import NotificationService
from src.services.seat_state_service import SeatStateService

STATIC_DIR = Path(__file__).resolve().parent / "views" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 取得 event loop 供同步程式碼（service 掛勾、排程執行緒）推播 WebSocket
    ws.manager.loop = asyncio.get_running_loop()
    SeatStateService.on_transition_hooks.append(ws.manager.publish_seat_update)
    NotificationService.on_notify_hooks.append(ws.manager.publish_notification)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="自習室空位偵測系統", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(reports.router)
app.include_router(ws.router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
