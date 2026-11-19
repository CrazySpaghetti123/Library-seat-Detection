"""雲端部署設定：連線字串轉換、連線池選項、CORS（spec: cloud-deployment）。"""
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from src.config import normalize_database_url
from src.database import engine_options


@pytest.mark.parametrize("raw, expected", [
    ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require",
     "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"),
    ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg://u:p@localhost:5432/seatdb", "postgresql+psycopg://u:p@localhost:5432/seatdb"),
    ("sqlite:///dev.db", "sqlite:///dev.db"),
])
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_engine_options():
    assert engine_options("sqlite:///dev.db") == {"connect_args": {"check_same_thread": False}}
    opts = engine_options("postgresql+psycopg://u:p@host/db")
    assert opts["pool_pre_ping"] is True and opts["pool_recycle"] == 300


def _cors_app(origins):
    """與 main.py 相同的 CORS 設定，套在最小的 app 上驗證行為。"""
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET", "POST", "PUT"],
                       allow_headers=["Authorization", "Content-Type", "X-Admin-Token"])

    @app.get("/api/seats")
    def seats():
        return {"seats": []}
    return TestClient(app)


def test_cors_allows_listed_origin_only():
    client = _cors_app(["https://crazyspaghetti123.github.io"])
    ok = client.get("/api/seats", headers={"Origin": "https://crazyspaghetti123.github.io"})
    assert ok.headers.get("access-control-allow-origin") == "https://crazyspaghetti123.github.io"
    assert "access-control-allow-credentials" not in ok.headers

    other = client.get("/api/seats", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers

    pre = client.options("/api/seats", headers={
        "Origin": "https://crazyspaghetti123.github.io",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert pre.status_code == 200
    assert "authorization" in pre.headers["access-control-allow-headers"].lower()
