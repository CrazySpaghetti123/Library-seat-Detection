"""離席逾時流程（spec: seat-timeout）。

計時驗證方式：直接把 DB 中的計時錨點（away_started_at / notified_at）
改到過去，再呼叫 sweep()——與正式環境的排程行為一致，不需 mock 時鐘。
"""
from datetime import timedelta

import pytest

from src.models.idle_event import IdleEvent
from src.models.notification import Notification
from src.models.seat import SeatStatus
from src.services.booking_service import BookingService
from src.services.idle_timeout_service import IdleTimeoutService
from src.utils import utcnow


def occupy(db, seats, label="A1", student="B11023001"):
    """走完 預約→報到 流程，讓座位進入 OCCUPIED。"""
    booking = BookingService.reserve_seat(db, label, student)
    BookingService.check_in(db, booking.id, student)
    return booking


def open_event(db, seat_id):
    return (
        db.query(IdleEvent)
        .filter(IdleEvent.seat_id == seat_id, IdleEvent.resolved_at.is_(None))
        .one()
    )


# ---- 疑似佔位開始與提示 ----

def test_person_left_creates_idle_event(db, seats):
    occupy(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_left_belongings")
    event = open_event(db, seats["A1"].id)
    assert event.kind == "away"
    assert seats["A1"].status == SeatStatus.OCCUPIED  # 未達門檻前狀態不變


def test_sweep_before_threshold_does_nothing(db, seats):
    occupy(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_left_belongings")
    stats = IdleTimeoutService.sweep(db)
    assert stats == {"away_notified": 0, "timeout_released": 0, "vacant_released": 0}
    assert seats["A1"].status == SeatStatus.OCCUPIED


def test_away_threshold_notifies_and_marks_away(db, seats):
    occupy(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_left_belongings")
    event = open_event(db, seats["A1"].id)
    event.away_started_at = utcnow() - timedelta(minutes=16)

    stats = IdleTimeoutService.sweep(db)
    assert stats["away_notified"] == 1
    assert seats["A1"].status == SeatStatus.AWAY
    note = db.query(Notification).filter_by(type="away_warning").one()
    assert note.student_id == "B11023001"
    assert note.payload["confirm_window_minutes"] == 10


def test_person_returns_before_threshold_cancels_timer(db, seats):
    occupy(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_left_belongings")
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_present")
    assert seats["A1"].status == SeatStatus.OCCUPIED
    assert db.query(IdleEvent).filter(IdleEvent.resolved_at.is_(None)).count() == 0
    assert db.query(Notification).count() == 0  # 不發送任何通知


# ---- 確認與返回 ----

def _drive_to_away(db, seats):
    occupy(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_left_belongings")
    event = open_event(db, seats["A1"].id)
    event.away_started_at = utcnow() - timedelta(minutes=16)
    IdleTimeoutService.sweep(db)
    assert seats["A1"].status == SeatStatus.AWAY


def test_confirm_keeps_seat_and_restarts_timer(db, seats):
    _drive_to_away(db, seats)
    IdleTimeoutService.confirm_presence(db, seats["A1"], "B11023001")
    assert seats["A1"].status == SeatStatus.OCCUPIED
    # 重新計時：產生新的未通知 away 事件，錨點為現在
    event = open_event(db, seats["A1"].id)
    assert event.notified_at is None
    assert (utcnow() - event.away_started_at).total_seconds() < 5


def test_confirm_by_other_student_forbidden(db, seats):
    _drive_to_away(db, seats)
    with pytest.raises(PermissionError):
        IdleTimeoutService.confirm_presence(db, seats["A1"], "B99999999")
    assert seats["A1"].status == SeatStatus.AWAY


def test_person_returns_while_away_counts_as_confirmation(db, seats):
    _drive_to_away(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_present")
    assert seats["A1"].status == SeatStatus.OCCUPIED
    assert db.query(IdleEvent).filter(IdleEvent.resolved_at.is_(None)).count() == 0


# ---- 逾時釋放 ----

def test_timeout_release_after_confirm_window(db, seats):
    _drive_to_away(db, seats)
    event = open_event(db, seats["A1"].id)
    event.notified_at = utcnow() - timedelta(minutes=11)

    stats = IdleTimeoutService.sweep(db)
    assert stats["timeout_released"] == 1
    assert seats["A1"].status == SeatStatus.AVAILABLE
    assert event.resolution == "released"
    assert BookingService.active_booking_for_seat(db, seats["A1"].id) is None
    note = db.query(Notification).filter_by(type="seat_released").one()
    assert note.student_id == "B11023001"


def test_vacant_release_without_notification(db, seats):
    occupy(db, seats)
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "seat_vacant")
    event = open_event(db, seats["A1"].id)
    event.away_started_at = utcnow() - timedelta(minutes=6)

    stats = IdleTimeoutService.sweep(db)
    assert stats["vacant_released"] == 1
    assert seats["A1"].status == SeatStatus.AVAILABLE
    assert db.query(Notification).filter_by(type="away_warning").count() == 0


# ---- walk-in ----

def test_walk_in_marks_occupied(db, seats):
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_present")
    assert seats["A1"].status == SeatStatus.OCCUPIED
