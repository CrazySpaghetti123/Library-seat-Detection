"""離席逾時流程（spec: seat-timeout）。

事件來源為偵測端（經 /api/detection/events）：
- person_left_belongings：人離開、物品仍在 → 建立 away 事件，15 分鐘後轉 AWAY 並提示
- seat_vacant：人與物品皆離開 → 建立 vacant 事件，5 分鐘後直接釋放
- person_present：人（重新）出現 → 解除事件；RESERVED 自動報到、AVAILABLE 視為 walk-in

計時錨點（away_started_at / notified_at）持久化於 idle_events，
由 APScheduler 週期呼叫 sweep()，程序重啟不會遺失計時。
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from src import config
from src.models.idle_event import IdleEvent
from src.models.seat import Seat, SeatStatus
from src.services.booking_service import BookingService
from src.services.notification_service import NotificationService
from src.services.seat_state_service import SeatStateService
from src.utils import utcnow


def _fmt_minutes(minutes: float) -> str:
    """通知顯示用：不足 1 分鐘改以秒呈現（展示模式常把參數調短）。"""
    if minutes < 1:
        return f"{round(minutes * 60)} 秒"
    return f"{minutes:g} 分鐘"


class IdleTimeoutService:

    # ---- 偵測事件入口 ----

    @classmethod
    def handle_detection_event(cls, db: Session, seat: Seat, event: str) -> None:
        if event == "person_present":
            cls._on_person_present(db, seat)
        elif event == "person_left_belongings":
            cls._on_person_left(db, seat, kind="away")
        elif event == "seat_vacant":
            cls._on_person_left(db, seat, kind="vacant")
        else:
            raise ValueError(f"未知的偵測事件: {event}")

    @classmethod
    def _on_person_present(cls, db: Session, seat: Seat) -> None:
        cls._resolve_open_events(db, seat.id, resolution="returned")
        if seat.status == SeatStatus.AWAY:
            # 本人返回視同完成確認（spec: Confirmation / Person physically returns）
            SeatStateService.transition(db, seat, SeatStatus.OCCUPIED, source="detection")
        elif seat.status == SeatStatus.RESERVED:
            # 自動報到（spec: seat-booking / Auto check-in by detection）
            BookingService.auto_check_in(db, seat)
        elif seat.status == SeatStatus.AVAILABLE:
            # 未經預約直接入座（walk-in）
            SeatStateService.transition(db, seat, SeatStatus.OCCUPIED, source="detection")
        # OCCUPIED：人本來就在，不需處理
        db.flush()

    @classmethod
    def _on_person_left(cls, db: Session, seat: Seat, kind: str) -> None:
        if seat.status not in (SeatStatus.OCCUPIED, SeatStatus.AWAY):
            return  # 沒有使用中的座位不需要計時
        open_events = cls._open_events(db, seat.id)
        same = [e for e in open_events if e.kind == kind]
        if same:
            return  # 已在計時，不重複建立
        # 事件型態改變（如 away → vacant）：結束舊事件、以原離席起點延續計時
        started_at = utcnow()
        for e in open_events:
            started_at = min(started_at, e.away_started_at)
            e.resolved_at = utcnow()
            e.resolution = "superseded"
        booking = BookingService.active_booking_for_seat(db, seat.id)
        db.add(IdleEvent(
            seat_id=seat.id,
            booking_id=booking.id if booking else None,
            kind=kind,
            away_started_at=started_at,
        ))
        db.flush()

    # ---- 使用者確認 ----

    @classmethod
    def confirm_presence(cls, db: Session, seat: Seat, student_id: str) -> None:
        """「我仍在使用」確認：回復 OCCUPIED 並重新計時（spec: Confirmation）。"""
        if seat.status != SeatStatus.AWAY:
            raise ValueError("此座位目前不需要確認")
        booking = BookingService.active_booking_for_seat(db, seat.id)
        if booking and booking.student_id != student_id:
            raise PermissionError("僅能確認自己的座位")

        cls._resolve_open_events(db, seat.id, resolution="confirmed")
        SeatStateService.transition(db, seat, SeatStatus.OCCUPIED, source="booking")
        # 人實際上仍未返回，偵測端不會再發離席事件——由此處重新起算計時
        db.add(IdleEvent(
            seat_id=seat.id,
            booking_id=booking.id if booking else None,
            kind="away",
            away_started_at=utcnow(),
        ))
        db.flush()

    # ---- 排程掃描（APScheduler 週期呼叫）----

    @classmethod
    def sweep(cls, db: Session) -> dict:
        """處理所有到期的計時，回傳各類處理筆數（ログ用）。"""
        now = utcnow()
        stats = {"away_notified": 0, "timeout_released": 0, "vacant_released": 0}

        # 1) away 事件達提示門檻 → 轉 AWAY 並通知
        due_away = (
            db.query(IdleEvent)
            .filter(
                IdleEvent.resolved_at.is_(None),
                IdleEvent.kind == "away",
                IdleEvent.notified_at.is_(None),
                IdleEvent.away_started_at
                <= now - timedelta(minutes=config.AWAY_THRESHOLD_MINUTES),
            )
            .all()
        )
        for event in due_away:
            seat = db.get(Seat, event.seat_id)
            if seat.status != SeatStatus.OCCUPIED:
                continue
            SeatStateService.transition(db, seat, SeatStatus.AWAY, source="timeout")
            event.notified_at = now
            booking = BookingService.active_booking_for_seat(db, seat.id)
            if booking:
                NotificationService.notify(
                    db, booking.student_id, type="away_warning", seat_id=seat.id,
                    payload={
                        "seat_label": seat.label,
                        "confirm_window_minutes": config.CONFIRM_WINDOW_MINUTES,
                        "message": (
                            f"您已離席超過 {_fmt_minutes(config.AWAY_THRESHOLD_MINUTES)}，"
                            f"請於 {_fmt_minutes(config.CONFIRM_WINDOW_MINUTES)} 內確認仍在使用，"
                            "否則座位將被釋放"
                        ),
                    },
                )
            stats["away_notified"] += 1

        # 2) 已提示且超過確認倒數 → 釋放
        due_release = (
            db.query(IdleEvent)
            .filter(
                IdleEvent.resolved_at.is_(None),
                IdleEvent.notified_at.isnot(None),
                IdleEvent.notified_at
                <= now - timedelta(minutes=config.CONFIRM_WINDOW_MINUTES),
            )
            .all()
        )
        for event in due_release:
            seat = db.get(Seat, event.seat_id)
            if seat.status != SeatStatus.AWAY:
                event.resolved_at = now
                event.resolution = "stale"
                continue
            cls._release(db, seat, event, reason="timeout_release", now=now)
            stats["timeout_released"] += 1

        # 3) vacant 事件達淨空門檻 → 直接釋放，不需提示
        due_vacant = (
            db.query(IdleEvent)
            .filter(
                IdleEvent.resolved_at.is_(None),
                IdleEvent.kind == "vacant",
                IdleEvent.away_started_at
                <= now - timedelta(minutes=config.VACANT_THRESHOLD_MINUTES),
            )
            .all()
        )
        for event in due_vacant:
            seat = db.get(Seat, event.seat_id)
            if seat.status not in (SeatStatus.OCCUPIED, SeatStatus.AWAY):
                event.resolved_at = now
                event.resolution = "stale"
                continue
            cls._release(db, seat, event, reason="vacant_release", now=now)
            stats["vacant_released"] += 1

        db.flush()
        return stats

    # ---- 內部工具 ----

    @classmethod
    def _release(cls, db: Session, seat: Seat, event: IdleEvent, reason: str, now) -> None:
        event.resolved_at = now
        event.resolution = "released"
        booking = BookingService.active_booking_for_seat(db, seat.id)
        SeatStateService.transition(db, seat, SeatStatus.AVAILABLE, source="timeout")
        if booking:
            BookingService.end_booking(db, booking, reason=reason)
            NotificationService.notify(
                db, booking.student_id, type="seat_released", seat_id=seat.id,
                payload={"seat_label": seat.label,
                         "message": f"座位 {seat.label} 因離席逾時已被釋放"},
            )

    @staticmethod
    def _open_events(db: Session, seat_id: int) -> list[IdleEvent]:
        return (
            db.query(IdleEvent)
            .filter(IdleEvent.seat_id == seat_id, IdleEvent.resolved_at.is_(None))
            .all()
        )

    @classmethod
    def _resolve_open_events(cls, db: Session, seat_id: int, resolution: str) -> None:
        now = utcnow()
        for event in cls._open_events(db, seat_id):
            event.resolved_at = now
            event.resolution = resolution
        db.flush()
