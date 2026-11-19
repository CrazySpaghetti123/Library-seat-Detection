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


def normalize_database_url(url: str) -> str:
    """雲端 PostgreSQL（Neon 等）提供的 postgres:// 或 postgresql:// 字串改用 psycopg 驅動，
    使用者可直接貼上服務給的連線字串（spec: cloud-deployment / Managed Database Connection）。"""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _list_env(name: str) -> list[str]:
    return [v.strip().rstrip("/") for v in os.getenv(name, "").split(",") if v.strip()]


# 開發期預設 SQLite；本機 PostgreSQL 或 DBaaS 以環境變數覆寫，例如：
# postgresql+psycopg://user:pass@localhost:5432/seatdb
DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///dev.db"))

# 學生登入 token 的簽章金鑰（正式環境務必覆寫；Render 部署時自動產生）
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
TOKEN_MAX_AGE_HOURS = _float_env("TOKEN_MAX_AGE_HOURS", 12)

# 存取控制（spec: access-control）。未設定＝開發模式，對應端點不驗證，啟動時記錄警告
DETECTION_API_KEY = os.getenv("DETECTION_API_KEY", "")  # 偵測端上報事件（X-API-Key）
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")              # ROI 標定與報表（X-Admin-Token）

# 允許跨來源呼叫 API 的前端網址（逗號分隔，例：https://crazyspaghetti123.github.io）；未設定＝只允許同源
ALLOWED_ORIGINS = _list_env("ALLOWED_ORIGINS")

AWAY_THRESHOLD_MINUTES = _float_env("AWAY_THRESHOLD_MINUTES", 15)
CONFIRM_WINDOW_MINUTES = _float_env("CONFIRM_WINDOW_MINUTES", 10)
CHECKIN_DEADLINE_MINUTES = _float_env("CHECKIN_DEADLINE_MINUTES", 30)
VACANT_THRESHOLD_MINUTES = _float_env("VACANT_THRESHOLD_MINUTES", 5)
# 結束使用後，每隔多久檢查一次是否已離開（秒）
LEAVE_CHECK_SECONDS = _float_env("LEAVE_CHECK_SECONDS", 30)

# 逾時排程掃描間隔（秒）：計時錨點存於 DB，掃描週期只影響觸發精度
SCHEDULER_INTERVAL_SECONDS = _int_env("SCHEDULER_INTERVAL_SECONDS", 15)

# 當地時區（IANA 名稱）：DB 一律存 naive UTC，報表的日期、開館時段與逐時分組以此時區計算
TIMEZONE = os.getenv("TIMEZONE", "Asia/Taipei")

# 自習室開放時段（當地時間，影響使用率報表分母），預設 08:00–22:00
OPEN_HOUR = _int_env("OPEN_HOUR", 8)
CLOSE_HOUR = _int_env("CLOSE_HOUR", 22)
