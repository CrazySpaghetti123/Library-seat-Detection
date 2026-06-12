"""預約—報到—取消—逾期情境（spec: seat-booking）。

取代原 src/main.py 主控台模擬，涵蓋原情境一／二並擴充新需求。
"""
from datetime import timedelta

import pytest

from src.models.notification import Notification
from src.models.seat import SeatStatus
from src.services.booking_service import BookingService
from src.services.idle_timeout_service import IdleTimeoutService
from src.utils import utcnow


# ---- 預約（原情境一／二）----

def test_reserve_available_seat(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    assert seats["A1"].status == SeatStatus.RESERVED
    assert booking.student_id == "B11023001"
    assert booking.checkin_deadline > utcnow()


@pytest.mark.parametrize("label", ["A2", "A3"])  # OCCUPIED / RESERVED
def test_reserve_unavailable_seat_rejected(db, seats, label):
    before = seats[label].status
    with pytest.raises(ValueError, match="無法預訂此座位"):
        BookingService.reserve_seat(db, label, "B11023001")
    assert seats[label].status == before  # 狀態不得被更改


def test_reserve_nonexistent_seat(db, seats):
    with pytest.raises(ValueError, match="不存在"):
        BookingService.reserve_seat(db, "Z9", "B11023001")


# ---- 一人一位 ----

def test_one_active_booking_per_student(db, seats):
    BookingService.reserve_seat(db, "A1", "B11023001")
    seats["A2"].status = SeatStatus.AVAILABLE
    with pytest.raises(ValueError, match="已持有座位"):
        BookingService.reserve_seat(db, "A2", "B11023001")


def test_can_book_again_after_cancel(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    BookingService.cancel(db, booking.id, "B11023001")
    seats["A2"].status = SeatStatus.AVAILABLE
    booking2 = BookingService.reserve_seat(db, "A2", "B11023001")
    assert booking2.id != booking.id


# ---- 報到 ----

def test_manual_check_in(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    BookingService.check_in(db, booking.id, "B11023001")
    assert seats["A1"].status == SeatStatus.OCCUPIED
    assert booking.checked_in_at is not None


def test_check_in_other_student_forbidden(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    with pytest.raises(PermissionError):
        BookingService.check_in(db, booking.id, "B99999999")


def test_auto_check_in_by_detection(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    IdleTimeoutService.handle_detection_event(db, seats["A1"], "person_present")
    assert seats["A1"].status == SeatStatus.OCCUPIED
    assert booking.checked_in_at is not None
    note = db.query(Notification).filter_by(type="checked_in").one()
    assert note.student_id == "B11023001"
    assert "自動完成報到" in note.payload["message"]


# ---- 取消 ----

def test_cancel_own_booking(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    BookingService.cancel(db, booking.id, "B11023001")
    assert seats["A1"].status == SeatStatus.AVAILABLE
    assert booking.end_reason == "cancelled"


def test_cancel_others_booking_forbidden(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    with pytest.raises(PermissionError):
        BookingService.cancel(db, booking.id, "B99999999")
    assert seats["A1"].status == SeatStatus.RESERVED


def test_cancel_after_check_in_rejected(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    BookingService.check_in(db, booking.id, "B11023001")
    with pytest.raises(ValueError, match="已報到"):
        BookingService.cancel(db, booking.id, "B11023001")


# ---- 逾期未報到 ----

def test_no_show_released(db, seats):
    booking = BookingService.reserve_seat(db, "A1", "B11023001")
    booking.checkin_deadline = utcnow() - timedelta(minutes=1)  # 模擬逾期
    released = BookingService.release_no_shows(db)
    assert released == 1
    assert seats["A1"].status == SeatStatus.AVAILABLE
    assert booking.end_reason == "no_show"
    note = db.query(Notification).filter_by(student_id="B11023001").one()
    assert note.type == "no_show"


def test_no_show_not_released_before_deadline(db, seats):
    BookingService.reserve_seat(db, "A1", "B11023001")
    assert BookingService.release_no_shows(db) == 0
    assert seats["A1"].status == SeatStatus.RESERVED
