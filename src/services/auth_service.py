"""存取控制（spec: access-control）。

- 學生：以學號換取簽章 token（無密碼，專題階段的已知限制），API 以 Authorization: Bearer 帶上
- 偵測端：X-API-Key 比對 DETECTION_API_KEY
- 管理者：X-Admin-Token 比對 ADMIN_TOKEN
金鑰未設定時視為開發模式，對應端點不驗證（啟動時由 main.py 記錄警告）。

前端（GitHub Pages）與後端（Render）不同網域，跨站 cookie 會被瀏覽器擋下，
因此不用 session cookie，改用 Bearer token（design D3）。
"""
import hmac
import re

from fastapi import Header, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src import config

# 學號格式：英數 4–15 碼（輕量驗證，正式介接 SSO 後可移除）
STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{4,15}$")
STUDENT_ID_ERROR = "學號格式不正確（英數 4–15 碼）"
_SALT = "student-login"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.SECRET_KEY, salt=_SALT)


def normalize_student_id(raw: str) -> str | None:
    """去空白、轉大寫；格式不符回傳 None。"""
    student_id = (raw or "").strip().upper()
    return student_id if STUDENT_ID_PATTERN.match(student_id) else None


def issue_token(student_id: str) -> str:
    return _serializer().dumps({"sid": student_id})


def verify_token(token: str | None) -> str | None:
    """回傳 token 內的學號；缺少、簽章不符、過期或內容異常時回傳 None。"""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=int(config.TOKEN_MAX_AGE_HOURS * 3600))
    except (BadSignature, SignatureExpired):
        return None
    sid = data.get("sid") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and STUDENT_ID_PATTERN.match(sid) else None


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_student(request: Request) -> str:
    """需要學生身分的 API 呼叫此函式取得學號；未登入或 token 無效回傳 401。"""
    student_id = verify_token(bearer_token(request.headers.get("authorization")))
    if not student_id:
        raise HTTPException(status_code=401, detail="請先以學號登入")
    return student_id


def key_matches(expected: str, provided: str | None) -> bool:
    """固定時間比對；expected 為空＝未設定金鑰（開發模式），一律通過。"""
    if not expected:
        return True
    return bool(provided) and hmac.compare_digest(expected.encode(), provided.encode())


def require_detection_key(x_api_key: str | None = Header(default=None)) -> None:
    if not key_matches(config.DETECTION_API_KEY, x_api_key):
        raise HTTPException(status_code=401, detail="偵測端金鑰錯誤")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not key_matches(config.ADMIN_TOKEN, x_admin_token):
        raise HTTPException(status_code=401, detail="管理密碼錯誤")


def unprotected_endpoints() -> list[str]:
    """未設定金鑰而對外開放的端點，供啟動時記錄警告。"""
    out = []
    if not config.DETECTION_API_KEY:
        out.append("POST /api/detection/events（未設定 DETECTION_API_KEY）")
    if not config.ADMIN_TOKEN:
        out.append("PUT /api/seats/{label}/roi、/api/reports/*（未設定 ADMIN_TOKEN）")
    if config.SECRET_KEY == "dev-secret-change-me":
        out.append("學生登入 token（SECRET_KEY 仍為開發預設值，任何人都能偽造）")
    return out
