"""預約服務（spec: seat-booking）。

規則：
- 僅 AVAILABLE 座位可預約；其他狀態一律拒絕且座位狀態不變
- 同一學號同時間僅能持有一筆有效預約（ended_at 為 NULL 即有效）
- 預約後須於報到期限內報到（網頁手動或偵測自動），逾期自動釋放
- 僅本人可取消自己的預約
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from src import config
from src.models.booking import Booking
from src.models.seat import Seat, SeatStatus
from src.services.notification_service import NotificationService
from src.services.seat_state_service import SeatStateService
from src.utils import utcnow


class BookingService:

    # ---- 查詢 ----

    @staticmethod
    def active_booking_for_student(db: Session, student_id: str) -> Booking | None:
        return (
            db.query(Booking)
            .filter(Booking.student_id == student_id, Booking.ended_at.is_(None))
            .first()
        )

    @staticmethod
    def active_booking_for_seat(db: Session, seat_id: int) -> Booking | None:
        return (
            db.query(Booking)
            .filter(Booking.seat_id == seat_id, Booking.ended_at.is_(None))
            .first()
        )

    # ---- 預約 ----

    @classmethod
    def reserve_seat(cls, db: Session, seat_label: str, student_id: str) -> Booking:
        seat = db.query(Seat).filter(Seat.label == seat_label).first()
        if not seat:
            raise ValueError(f"座位 {seat_label} 不存在。")
        if seat.status != SeatStatus.AVAILABLE:
            raise ValueError(f"無法預訂此座位，目前狀態為: {seat.status.value}")
        if cls.active_booking_for_student(db, student_id):
            raise ValueError("您已持有座位，請先取消或結束使用")

        booking = Booking(
            seat_id=seat.id,
            student_id=student_id,
            checkin_deadline=utcnow() + timedelta(minutes=config.CHECKIN_DEADLINE_MINUTES),
        )
        db.add(booking)
        SeatStateService.transition(db, seat, SeatStatus.RESERVED, source="booking")
        db.flush()
        return booking

    # ---- 報到 ----

    @classmethod
    def check_in(cls, db: Session, booking_id: int, student_id: str) -> Booking:
        """網頁手動報到（限本人）。"""
        booking = db.get(Booking, booking_id)
        if not booking or booking.ended_at is not None:
            raise ValueError("查無有效預約")
        if booking.student_id != student_id:
            raise PermissionError("僅能對自己的預約報到")
        if booking.checked_in_at is not None:
            raise ValueError("此預約已完成報到")

        seat = db.get(Seat, booking.seat_id)
        booking.checked_in_at = utcnow()
        SeatStateService.transition(db, seat, SeatStatus.OCCUPIED, source="booking")
        db.flush()
        return booking

    @classmethod
    def auto_check_in(cls, db: Session, seat: Seat) -> Booking | None:
        """偵測端在 RESERVED 座位偵測到人入座 → 自動報到並通知使用者。"""
        booking = cls.active_booking_for_seat(db, seat.id)
        if not booking or booking.checked_in_at is not None:
            return None
        booking.checked_in_at = utcnow()
        SeatStateService.transition(db, seat, SeatStatus.OCCUPIED, source="detection")
        NotificationService.notify(
            db, booking.student_id, type="checked_in", seat_id=seat.id,
            payload={"seat_label": seat.label,
                     "message": f"偵測到您已入座，座位 {seat.label} 已自動完成報到"},
        )
        db.flush()
        return booking

    # ---- 取消 ----

    @classmethod
    def cancel(cls, db: Session, booking_id: int, student_id: str) -> Booking:
        booking = db.get(Booking, booking_id)
        if not booking or booking.ended_at is not None:
            raise ValueError("查無有效預約")
        if booking.student_id != student_id:
            raise PermissionError("僅能取消自己的預約")
        if booking.checked_in_at is not None:
            raise ValueError("已報到的預約無法取消")

        seat = db.get(Seat, booking.seat_id)
        booking.ended_at = utcnow()
        booking.end_reason = "cancelled"
        SeatStateService.transition(db, seat, SeatStatus.AVAILABLE, source="booking")
        db.flush()
        return booking

    # ---- 逾期未報到（由排程週期呼叫）----

    @classmethod
    def release_no_shows(cls, db: Session) -> int:
        """釋放所有逾期未報到的預約，回傳釋放筆數。"""
        now = utcnow()
        expired = (
            db.query(Booking)
            .filter(
                Booking.ended_at.is_(None),
                Booking.checked_in_at.is_(None),
                Booking.checkin_deadline <= now,
            )
            .all()
        )
        for booking in expired:
            seat = db.get(Seat, booking.seat_id)
            booking.ended_at = now
            booking.end_reason = "no_show"
            SeatStateService.transition(db, seat, SeatStatus.AVAILABLE, source="timeout")
            NotificationService.notify(
                db, booking.student_id, type="no_show", seat_id=seat.id,
                payload={"seat_label": seat.label,
                         "message": f"座位 {seat.label} 因逾期未報到已自動釋放"},
            )
        db.flush()
        return len(expired)

    # ---- 結束（逾時釋放等情境由 IdleTimeoutService 呼叫）----

    @staticmethod
    def end_booking(db: Session, booking: Booking, reason: str) -> None:
        booking.ended_at = utcnow()
        booking.end_reason = reason
        db.flush()
