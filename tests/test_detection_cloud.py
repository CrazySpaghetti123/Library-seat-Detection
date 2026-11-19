"""偵測端連雲端：金鑰、離線補送、開館時段心跳（spec: access-control / cloud-deployment）。"""
from datetime import datetime

import httpx
import pytest

from src.detection.detector import parse_args
from src.detection.reporter import EventReporter, Heartbeat, in_open_hours


class FakeBackend:
    """記錄收到的請求；online=False 時模擬連線失敗。"""

    def __init__(self, status=200):
        self.status = status
        self.online = True
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.online:
            raise httpx.ConnectError("offline", request=request)
        self.requests.append(request)
        return httpx.Response(self.status, json={"results": []})


def reporter(tmp_path, backend, api_key="det-key"):
    return EventReporter(api_base="https://seat.example", queue_path=str(tmp_path / "q.jsonl"),
                         api_key=api_key, transport=httpx.MockTransport(backend.handler))


def test_send_carries_api_key(tmp_path):
    backend = FakeBackend()
    reporter(tmp_path, backend).send("A1", "person_present")
    assert backend.requests[0].headers["X-API-Key"] == "det-key"


def test_offline_queue_flush_carries_api_key(tmp_path):
    backend = FakeBackend()
    r = reporter(tmp_path, backend)
    backend.online = False
    r.send("A1", "person_present")
    r.send("A1", "person_left_belongings")
    assert (tmp_path / "q.jsonl").exists()

    backend.online = True
    assert r.flush() is True
    sent = backend.requests[-1]
    assert sent.headers["X-API-Key"] == "det-key"
    assert b"person_left_belongings" in sent.content
    assert not (tmp_path / "q.jsonl").exists()


def test_rejected_key_keeps_events_queued(tmp_path, caplog):
    backend = FakeBackend(status=401)
    r = reporter(tmp_path, backend, api_key="wrong")
    r.send("A1", "person_present")
    assert (tmp_path / "q.jsonl").exists()
    assert "金鑰錯誤" in caplog.text


def test_no_key_sends_no_header(tmp_path):
    backend = FakeBackend()
    reporter(tmp_path, backend, api_key="").send("A1", "person_present")
    assert "X-API-Key" not in backend.requests[0].headers


@pytest.mark.parametrize("hour, expected", [(9, False), (10, True), (19, True), (20, False)])
def test_in_open_hours(hour, expected):
    assert in_open_hours(hour, 10, 20) is expected


def test_in_open_hours_across_midnight():
    assert in_open_hours(23, 22, 6) and in_open_hours(3, 22, 6) and not in_open_hours(12, 22, 6)


def test_heartbeat_only_during_open_hours_and_interval(tmp_path):
    backend = FakeBackend()
    client = httpx.Client(transport=httpx.MockTransport(backend.handler))
    clock = {"t": 0.0}
    now = {"dt": datetime(2026, 11, 19, 9, 30)}
    hb = Heartbeat(client, "https://seat.example", 10, 10, 20,
                   clock=lambda: clock["t"], now=lambda: now["dt"])

    assert hb.tick() is False                      # 09:30 開館前不送
    now["dt"] = datetime(2026, 11, 19, 10, 0)
    assert hb.tick() is True                       # 開館後第一次立即送
    clock["t"] = 5 * 60
    assert hb.tick() is False                      # 未滿 10 分鐘
    clock["t"] = 10 * 60
    assert hb.tick() is True
    now["dt"] = datetime(2026, 11, 19, 20, 5)
    clock["t"] = 30 * 60
    assert hb.tick() is False                      # 閉館後不送
    assert [r.url.path for r in backend.requests] == ["/api/health", "/api/health"]


def test_heartbeat_disabled_with_zero_interval():
    hb = Heartbeat(httpx.Client(), "https://seat.example", 0, 0, 24,
                   now=lambda: datetime(2026, 11, 19, 12, 0))
    assert hb.tick() is False


def test_heartbeat_survives_connection_error():
    def down(request):
        raise httpx.ConnectError("waking up", request=request)
    hb = Heartbeat(httpx.Client(transport=httpx.MockTransport(down)), "https://seat.example",
                   10, 0, 24, now=lambda: datetime(2026, 11, 19, 12, 0))
    assert hb.tick() is True  # 失敗不中斷偵測迴圈


def test_detector_cli_options(monkeypatch):
    monkeypatch.setenv("DETECTION_API_KEY", "from-env")
    monkeypatch.setenv("OPEN_HOUR", "10")
    monkeypatch.setenv("CLOSE_HOUR", "20")
    args = parse_args([])
    assert (args.api_key, args.heartbeat, args.open_hours) == ("from-env", 10, (10, 20))
    args = parse_args(["--api-key", "k", "--heartbeat", "0", "--open-hours", "8-22"])
    assert (args.api_key, args.heartbeat, args.open_hours) == ("k", 0, (8, 22))
    with pytest.raises(SystemExit):
        parse_args(["--open-hours", "ten-twenty"])
