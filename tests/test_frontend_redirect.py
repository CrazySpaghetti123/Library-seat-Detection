"""雲端後端不提供前端、改為轉址（spec: cloud-deployment / Separately Hosted Static Frontend）。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.controllers import api
from src.main import setup_frontend

FRONT = "https://crazyspaghetti123.github.io/Library-seat-Detection"


def make_client(frontend_url):
    app = FastAPI()
    app.include_router(api.router)
    setup_frontend(app, frontend_url)
    return TestClient(app, follow_redirects=False)


def test_cloud_redirects_pages_to_frontend_url():
    client = make_client(FRONT)
    res = client.get("/")
    assert res.status_code == 307 and res.headers["location"] == FRONT + "/"
    res = client.get("/map.html?x=1")
    assert res.headers["location"] == FRONT + "/map.html?x=1"
    assert client.get("/js/map.js").headers["location"] == FRONT + "/js/map.js"


def test_cloud_keeps_api_and_404s_unknown_api():
    client = make_client(FRONT)
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/api").status_code == 404


def test_local_serves_frontend_files():
    client = make_client("")
    res = client.get("/")
    assert res.status_code == 200 and "學號" in res.text
    assert client.get("/map.html").status_code == 200
