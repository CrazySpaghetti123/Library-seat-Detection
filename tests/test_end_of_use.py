"""結束使用（spec: seat-booking / End of Use）與保存最新偵測結果（spec: seat-detection）。

計時驗證方式同 test_timeout：把 leave_check_at 改到過去再呼叫 process_leave_checks()。
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src import config
from src.database import get_db
from src.main import app
from src.models.idle_event import IdleEvent
from src.models.notification import Notification
from src.models.seat import SeatStatus
from src.services.booking_service import BookingService
from src.services.idle_timeout_service import IdleTimeoutService
from src.utils import utcnow

STUDENT = "B11023001"


def occupy(db, label="A1", student=STUDENT):
    booking = BookingService.reserve_seat(db, label, student)
    BookingService.check_in(db, booking.id, student)
    return booking


def detect(db, seats, event, label="A1"):
    IdleTimeoutService.handle_detection_event(db, seats[label], event)


def make_due(db, booking):
    booking.leave_check_at = utcnow() - timedelta(seconds=1)
    db.flush()


# ---- 保存最新偵測結果 ----

def test_latest_detection_recorded_without_state_change(db, seats):
    assert seats["A1"].last_detection is None
    detect(db, seats, "seat_vacant")
    assert seats["A1"].status == SeatStatus.AVAILABLE
    assert seats["A1"].last_detection == "seat_vacant"
    assert seats["A1"].last_detection_at is not None


def test_newer_detection_replaces_older(db, seats):
    detect(db, seats, "person_present")
    detect(db, seats, "person_left_belongings")
    assert seats["A1"].last_detection == "person_left_belongings"


def test_unknown_event_not_recorded(db, seats):
    with pytest.raises(ValueError):
        detect(db, seats, "dancing")
    assert seats["A1"].last_detection is None


# ---- 結束使用 ----

def test_request_leave_schedules_first_check(db, seats, monkeypatch):
    monkeypatch.setattr(config, "LEAVE_CHECK_SECONDS", 30)
    booking = occupy(db)
    BookingService.request_leave(db, booking.id, STUDENT)
    assert booking.leave_requested_at is not None
    gap = (booking.leave_check_at - booking.leave_requested_at).total_seconds()
    assert gap == pytest.approx(30)
    # 未到期前不處理
    assert BookingService.process_leave_checks(db)["leave_released"] == 0
    assert seats["A1"].status == SeatStatus.OCCUPIED


def test_release_after_user_left(db, seats):
    booking = occupy(db)
    detect(db, seats, "person_present")
    BookingService.request_leave(db, booking.id, STUDENT)
    detect(db, seats, "seat_vacant")  # 會建立 vacant 事件
    make_due(db, booking)

    stats = BookingService.process_leave_checks(db)
    assert stats["leave_released"] == 1
    assert seats["A1"].status == SeatStatus.AVAILABLE
    assert booking.ended_at is not None
    assert booking.end_reason == "checked_out"
    # 離席／淨空事件一併結束，不會之後再觸發
    assert db.query(IdleEvent).filter(IdleEvent.resolved_at.is_(None)).count() == 0
    note = db.query(Notification).filter(Notification.type == "checked_out").one()
    assert note.student_id == STUDENT and "A1" in note.payload["message"]
    # 結束後可再預約別的座位
    assert BookingService.active_booking_for_student(db, STUDENT) is None


@pytest.mark.parametrize("still_there", ["person_present", "person_left_belongings"])
def test_postponed_while_person_or_belongings_remain(db, seats, still_there, monkeypatch):
    monkeypatch.setattr(config, "LEAVE_CHECK_SECONDS", 30)
    booking = occupy(db)
    detect(db, seats, still_there)
    BookingService.request_leave(db, booking.id, STUDENT)
    make_due(db, booking)

    stats = BookingService.process_leave_checks(db)
    assert stats == {"leave_released": 0, "leave_postponed": 1}
    assert seats["A1"].status == SeatStatus.OCCUPIED
    assert booking.ended_at is None
    assert (booking.leave_check_at - utcnow()).total_seconds() == pytest.approx(30, abs=2)

    # 再次檢查前就離開了 → 下一次檢查釋放
    detect(db, seats, "seat_vacant")
    make_due(db, booking)
    assert BookingService.process_leave_checks(db)["leave_released"] == 1
    assert seats["A1"].status == SeatStatus.AVAILABLE


def test_seat_without_detection_data_released_on_first_check(db, seats):
    booking = occupy(db)
    assert seats["A1"].last_detection is None
    BookingService.request_leave(db, booking.id, STUDENT)
    make_due(db, booking)
    assert BookingService.process_leave_checks(db)["leave_released"] == 1
    assert booking.end_reason == "checked_out"


def test_leave_from_away_state(db, seats):
    booking = occupy(db)
    detect(db, seats, "person_left_belongings")
    event = db.query(IdleEvent).one()
    event.away_started_at = utcnow() - timedelta(minutes=config.AWAY_THRESHOLD_MINUTES + 1)
    IdleTimeoutService.sweep(db)
    assert seats["A1"].status == SeatStatus.AWAY

    BookingService.request_leave(db, booking.id, STUDENT)
    detect(db, seats, "seat_vacant")
    make_due(db, booking)
    assert BookingService.process_leave_checks(db)["leave_released"] == 1
    assert seats["A1"].status == SeatStatus.AVAILABLE


def test_resume_use_stops_checks(db, seats):
    booking = occupy(db)
    BookingService.request_leave(db, booking.id, STUDENT)
    BookingService.resume_use(db, booking.id, STUDENT)
    assert booking.leave_requested_at is None and booking.leave_check_at is None
    assert BookingService.process_leave_checks(db) == {"leave_released": 0, "leave_postponed": 0}
    assert seats["A1"].status == SeatStatus.OCCUPIED
    with pytest.raises(ValueError):
        BookingService.resume_use(db, booking.id, STUDENT)


def test_cannot_end_others_booking_or_twice(db, seats):
    booking = occupy(db)
    with pytest.raises(PermissionError):
        BookingService.request_leave(db, booking.id, "B99999999")
    assert booking.leave_requested_at is None
    BookingService.request_leave(db, booking.id, STUDENT)
    with pytest.raises(ValueError):
        BookingService.request_leave(db, booking.id, STUDENT)  # 不可重複
    assert seats["A1"].status == SeatStatus.OCCUPIED


def test_cannot_end_before_check_in(db, seats):
    seats["A1"].status = SeatStatus.AVAILABLE
    booking = BookingService.reserve_seat(db, "A1", STUDENT)
    with pytest.raises(ValueError, match="取消預約"):
        BookingService.request_leave(db, booking.id, STUDENT)
    assert booking.leave_requested_at is None


# ---- API ----

@pytest.fixture
def client(db, seats, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(config, "DETECTION_API_KEY", "")
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(client, student):
    token = client.post("/api/auth/login", json={"student_id": student}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_leave_and_resume_api(client, db, seats):
    me = auth(client, STUDENT)
    booking_id = client.post("/api/bookings", json={"seat_label": "A1"}, headers=me).json()["id"]
    assert client.post(f"/api/bookings/{booking_id}/leave", headers=me).status_code == 400  # 未報到
    client.post(f"/api/bookings/{booking_id}/checkin", headers=me)
    client.post("/api/detection/events",
                json={"events": [{"seat_label": "A1", "event": "person_present"}]})

    res = client.post(f"/api/bookings/{booking_id}/leave", headers=me)
    assert res.status_code == 200 and res.json()["leave_check_at"]
    data = client.get("/api/me/booking", headers=me).json()
    assert data["booking"]["leave_requested_at"] and data["last_detection"] == "person_present"

    other = auth(client, "B22222222")
    assert client.post(f"/api/bookings/{booking_id}/resume", headers=other).status_code == 403
    assert client.post(f"/api/bookings/{booking_id}/resume", headers=me).status_code == 200
    assert client.get("/api/me/booking", headers=me).json()["booking"]["leave_requested_at"] is None
    assert client.post(f"/api/bookings/{booking_id}/leave").status_code == 401
