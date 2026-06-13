"""系統設定：環境變數優先，未設定時採用預設值。

計時參數對應 openspec specs（seat-timeout / seat-booking）：
- AWAY_THRESHOLD_MINUTES   離席（物品仍在）多久後轉 AWAY 並提示，預設 15 分鐘
- CONFIRM_WINDOW_MINUTES   提示後多久未確認即釋放，預設 10 分鐘
- CHECKIN_DEADLINE_MINUTES 預約後報到期限，預設 30 分鐘
- VACANT_THRESHOLD_MINUTES 人與物品皆離開多久後直接釋放，預設 5 分鐘
"""
import os


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    """計時參數允許小數分鐘（例：0.33 ≈ 20 秒），方便展示時縮短流程。"""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


# 開發期預設 SQLite；本機 PostgreSQL 或 DBaaS 以環境變數覆寫，例如：
# postgresql+psycopg://user:pass@localhost:5432/seatdb
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dev.db")

# Session 簽章金鑰（正式環境務必覆寫）
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

AWAY_THRESHOLD_MINUTES = _float_env("AWAY_THRESHOLD_MINUTES", 15)
CONFIRM_WINDOW_MINUTES = _float_env("CONFIRM_WINDOW_MINUTES", 10)
CHECKIN_DEADLINE_MINUTES = _float_env("CHECKIN_DEADLINE_MINUTES", 30)
VACANT_THRESHOLD_MINUTES = _float_env("VACANT_THRESHOLD_MINUTES", 5)

# 逾時排程掃描間隔（秒）：計時錨點存於 DB，掃描週期只影響觸發精度
SCHEDULER_INTERVAL_SECONDS = _int_env("SCHEDULER_INTERVAL_SECONDS", 15)

# 自習室開放時段（影響使用率報表分母），預設 08:00–22:00
OPEN_HOUR = _int_env("OPEN_HOUR", 8)
CLOSE_HOUR = _int_env("CLOSE_HOUR", 22)

# Node.js + Socket.IO 即時推播閘道（feature/nodejs-socketio-gateway 分支）
# FastAPI 狀態變更時以 HTTP POST 通知此閘道，由閘道經 Socket.IO 推給瀏覽器
NODE_GATEWAY_URL = os.getenv("NODE_GATEWAY_URL", "http://127.0.0.1:3001")
GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "dev-gateway-secret")
