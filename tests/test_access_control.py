"""存取控制與雲端部署端點（spec: access-control / cloud-deployment）。

以 TestClient 走完整 HTTP 流程（含相依注入的驗證），資料庫換成測試用 in-memory SQLite。
不使用 `with TestClient(...)`，因此不會啟動 lifespan 中的排程器。
"""
import time

import pytest
from fastapi.testclient import TestClient

from src import config
from src.database import get_db
from src.main import app
from src.services import auth_service

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]


@pytest.fixture
def client(db, seats, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(config, "DETECTION_API_KEY", "")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, student_id="b11023001"):
    res = client.post("/api/auth/login", json={"student_id": student_id})
    assert res.status_code == 200
    return res.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---- 學生登入 ----

def test_login_returns_token_and_uppercased_id(client):
    data = login(client, " b11023001 ")
    assert data["student_id"] == "B11023001"
    assert auth_service.verify_token(data["token"]) == "B11023001"


@pytest.mark.parametrize("bad", ["B1", "B110-23001", "", "A" * 16])
def test_login_rejects_malformed_id(client, bad):
    res = client.post("/api/auth/login", json={"student_id": bad})
    assert res.status_code == 400
    assert res.json()["detail"] == "學號格式不正確（英數 4–15 碼）"


def test_booking_uses_student_from_token(client):
    token = login(client)["token"]
    res = client.post("/api/bookings", json={"seat_label": "A1"}, headers=bearer(token))
    assert res.status_code == 200, res.text
    me = client.get("/api/me/booking", headers=bearer(token)).json()
    assert me["booking"]["student_id"] == "B11023001"


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer not-a-token"},
    {"Authorization": "Basic abc"},
])
def test_student_api_requires_valid_token(client, headers):
    assert client.get("/api/me/booking", headers=headers).status_code == 401
    assert client.post("/api/bookings", json={"seat_label": "A1"}, headers=headers).status_code == 401


def test_token_signed_with_other_key_rejected(client, monkeypatch):
    token = login(client)["token"]
    monkeypatch.setattr(config, "SECRET_KEY", "another-secret")
    assert client.get("/api/me/booking", headers=bearer(token)).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    token = login(client)["token"]
    monkeypatch.setattr(config, "TOKEN_MAX_AGE_HOURS", 1)
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 2 * 3600)
    assert client.get("/api/me/booking", headers=bearer(token)).status_code == 401


def test_public_endpoints_need_no_login(client):
    assert client.get("/api/seats").status_code == 200
    assert client.get("/api/seats/events").status_code == 200


# ---- 即時推播 ----

def test_websocket_with_token_receives_personal_channel(client):
    token = login(client)["token"]
    from src.controllers.ws import manager
    with client.websocket_connect(f"/ws/seats?token={token}") as ws:
        assert "B11023001" in manager._student_channels
        ws.send_text("ping")  # 心跳不影響連線
    assert "B11023001" not in manager._student_channels


def test_websocket_without_token_still_connects(client):
    from src.controllers.ws import manager
    with client.websocket_connect("/ws/seats?token=bad"):
        assert len(manager._seat_subscribers) == 1
        assert manager._student_channels == {}


# ---- 偵測端金鑰 ----

EVENT = {"events": [{"seat_label": "A1", "event": "person_present"}]}


def test_detection_requires_key_when_configured(client, monkeypatch, seats):
    monkeypatch.setattr(config, "DETECTION_API_KEY", "det-key")
    assert client.post("/api/detection/events", json=EVENT).status_code == 401
    assert client.post("/api/detection/events", json=EVENT,
                       headers={"X-API-Key": "wrong"}).status_code == 401
    assert seats["A1"].status.value == "AVAILABLE"
    res = client.post("/api/detection/events", json=EVENT, headers={"X-API-Key": "det-key"})
    assert res.status_code == 200
    assert res.json()["results"][0]["ok"] is True


def test_detection_open_without_key(client):
    assert client.post("/api/detection/events", json=EVENT).status_code == 200


# ---- 管理密碼 ----

def test_reports_and_roi_require_admin_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "admin-pass")
    paths = ["/api/reports/usage?date=2026-06-10", "/api/reports/trend?start=2026-06-10&end=2026-06-10",
             "/api/reports/floors?start=2026-06-10&end=2026-06-10",
             "/api/reports/idle?start=2026-06-10&end=2026-06-10",
             "/api/reports/usage.csv?start=2026-06-10&end=2026-06-10"]
    for path in paths:
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers={"X-Admin-Token": "nope"}).status_code == 401, path
        assert client.get(path, headers={"X-Admin-Token": "admin-pass"}).status_code == 200, path

    assert client.put("/api/seats/A1/roi", json={"points": SQUARE}).status_code == 401
    res = client.put("/api/seats/A1/roi", json={"points": SQUARE},
                     headers={"X-Admin-Token": "admin-pass"})
    assert res.status_code == 200


def test_reports_open_without_admin_token(client):
    assert client.get("/api/reports/usage?date=2026-06-10").status_code == 200


def test_unprotected_endpoints_listed(monkeypatch):
    monkeypatch.setattr(config, "DETECTION_API_KEY", "")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "x")
    monkeypatch.setattr(config, "SECRET_KEY", "dev-secret-change-me")
    items = auth_service.unprotected_endpoints()
    assert any("DETECTION_API_KEY" in i for i in items)
    assert not any("ADMIN_TOKEN" in i for i in items)
    assert any("SECRET_KEY" in i for i in items)


# ---- 設定、健康檢查、靜態前端 ----

def test_config_endpoint(client, monkeypatch):
    monkeypatch.setattr(config, "CHECKIN_DEADLINE_MINUTES", 30)
    monkeypatch.setattr(config, "OPEN_HOUR", 10)
    monkeypatch.setattr(config, "CLOSE_HOUR", 20)
    data = client.get("/api/config").json()
    assert (data["checkin_deadline_minutes"], data["open_hour"], data["close_hour"]) == (30, 10, 20)
    assert data["timezone"] == config.TIMEZONE


def test_health_does_not_touch_database(client):
    def boom():
        raise AssertionError("health 不應建立資料庫連線")
        yield  # pragma: no cover
    app.dependency_overrides[get_db] = boom
    assert client.get("/api/health").json() == {"ok": True}


def test_static_frontend_served_at_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "學號" in res.text
    assert client.get("/map.html").status_code == 200
    assert client.get("/config.js").status_code == 200
