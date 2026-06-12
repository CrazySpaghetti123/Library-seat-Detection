"""REST API（Controller 層，保持薄：驗證輸入 → 呼叫 Service → 回傳）。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.booking import Booking
from src.models.seat import Seat, SeatStatus
from src.services.booking_service import BookingService
from src.services.idle_timeout_service import IdleTimeoutService
from src.services.notification_service import NotificationService

router = APIRouter(prefix="/api")


def require_student(request: Request) -> str:
    student_id = request.session.get("student_id")
    if not student_id:
        raise HTTPException(status_code=401, detail="請先以學號登入")
    return student_id


def seat_to_dict(seat: Seat) -> dict:
    return {
        "id": seat.id, "label": seat.label, "floor": seat.floor,
        "status": seat.status.value, "map_x": seat.map_x, "map_y": seat.map_y,
        "roi": seat.roi,
    }


def booking_to_dict(b: Booking, seat_label: str | None = None) -> dict:
    return {
        "id": b.id, "seat_id": b.seat_id, "seat_label": seat_label,
        "student_id": b.student_id,
        "created_at": b.created_at.isoformat(),
        "checkin_deadline": b.checkin_deadline.isoformat(),
        "checked_in_at": b.checked_in_at.isoformat() if b.checked_in_at else None,
        "ended_at": b.ended_at.isoformat() if b.ended_at else None,
        "end_reason": b.end_reason,
    }


# ---- 座位 ----

@router.get("/seats")
def list_seats(db: Session = Depends(get_db)):
    """全量快照：平面圖初始載入與 WebSocket 重連後補償用。"""
    seats = db.query(Seat).order_by(Seat.label).all()
    return {
        "seats": [seat_to_dict(s) for s in seats],
        "available_count": sum(1 for s in seats if s.status == SeatStatus.AVAILABLE),
    }


@router.post("/seats/{seat_id}/confirm-presence")
def confirm_presence(seat_id: int, request: Request, db: Session = Depends(get_db)):
    """「我仍在使用」確認（spec: seat-timeout / Confirmation）。"""
    student_id = require_student(request)
    seat = db.get(Seat, seat_id)
    if not seat:
        raise HTTPException(status_code=404, detail="座位不存在")
    try:
        IdleTimeoutService.confirm_presence(db, seat, student_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {"ok": True, "seat": seat_to_dict(seat)}


# ---- 預約 ----

class ReserveRequest(BaseModel):
    seat_label: str


@router.post("/bookings")
def create_booking(body: ReserveRequest, request: Request, db: Session = Depends(get_db)):
    student_id = require_student(request)
    try:
        booking = BookingService.reserve_seat(db, body.seat_label, student_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return booking_to_dict(booking, seat_label=body.seat_label)


@router.get("/me/booking")
def my_booking(request: Request, db: Session = Depends(get_db)):
    student_id = require_student(request)
    booking = BookingService.active_booking_for_student(db, student_id)
    if not booking:
        return {"booking": None}
    seat = db.get(Seat, booking.seat_id)
    return {"booking": booking_to_dict(booking, seat_label=seat.label),
            "seat_status": seat.status.value}


@router.post("/bookings/{booking_id}/checkin")
def check_in(booking_id: int, request: Request, db: Session = Depends(get_db)):
    student_id = require_student(request)
    try:
        booking = BookingService.check_in(db, booking_id, student_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return booking_to_dict(booking)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, request: Request, db: Session = Depends(get_db)):
    student_id = require_student(request)
    try:
        booking = BookingService.cancel(db, booking_id, student_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return booking_to_dict(booking)


# ---- 通知 ----

@router.get("/notifications")
def unread_notifications(request: Request, db: Session = Depends(get_db)):
    student_id = require_student(request)
    notes = NotificationService.unread(db, student_id)
    return {"notifications": [NotificationService.to_dict(n) for n in notes]}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request,
                           db: Session = Depends(get_db)):
    student_id = require_student(request)
    NotificationService.mark_read(db, notification_id, student_id)
    db.commit()
    return {"ok": True}


# ---- ROI 標定（spec: seat-detection / ROI Seat Calibration）----

class RoiRequest(BaseModel):
    points: list[list[int]]  # 四點座標 [[x,y] x4]


@router.put("/seats/{seat_label}/roi")
def set_seat_roi(seat_label: str, body: RoiRequest, db: Session = Depends(get_db)):
    """標定工具寫入座位 ROI。正式部署時應加上管理者驗證。"""
    if len(body.points) != 4:
        raise HTTPException(status_code=400, detail="ROI 需為四點座標")
    seat = db.query(Seat).filter(Seat.label == seat_label).first()
    if not seat:
        raise HTTPException(status_code=404, detail="座位不存在")
    seat.roi = {"points": body.points}
    db.commit()
    return {"ok": True, "seat": seat_to_dict(seat)}


# ---- 偵測端事件（spec: seat-detection / State Change Synchronization）----

class DetectionEvent(BaseModel):
    seat_label: str
    # person_present / person_left_belongings / seat_vacant
    event: str


class DetectionBatch(BaseModel):
    events: list[DetectionEvent]


@router.post("/detection/events")
def receive_detection_events(body: DetectionBatch, db: Session = Depends(get_db)):
    """接收偵測端事件批次（離線補送時一次多筆，依序處理）。"""
    results = []
    for item in body.events:
        seat = db.query(Seat).filter(Seat.label == item.seat_label).first()
        if not seat:
            results.append({"seat_label": item.seat_label, "ok": False,
                            "error": "座位不存在"})
            continue
        try:
            IdleTimeoutService.handle_detection_event(db, seat, item.event)
            results.append({"seat_label": item.seat_label, "ok": True})
        except ValueError as e:
            results.append({"seat_label": item.seat_label, "ok": False,
                            "error": str(e)})
    db.commit()
    return {"results": results}
