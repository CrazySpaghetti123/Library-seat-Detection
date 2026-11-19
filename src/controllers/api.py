"""REST API（Controller 層，保持薄：驗證輸入 → 呼叫 Service → 回傳）。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src import config
from src.database import get_db
from src.models.booking import Booking
from src.models.seat import Seat, SeatStatus, SeatStatusLog
from src.services.booking_service import BookingService
from src.services.idle_timeout_service import IdleTimeoutService
from src.services.auth_service import (
    STUDENT_ID_ERROR,
    issue_token,
    normalize_student_id,
    require_admin,
    require_detection_key,
    require_student,
)
from src.services.notification_service import NotificationService

router = APIRouter(prefix="/api")


# ---- 登入、設定與健康檢查（spec: access-control / cloud-deployment）----

class LoginRequest(BaseModel):
    student_id: str


@router.post("/auth/login")
def login(body: LoginRequest):
    """以學號換取 token（無密碼）。前端存於 localStorage，之後以 Authorization: Bearer 帶上。"""
    student_id = normalize_student_id(body.student_id)
    if not student_id:
        raise HTTPException(status_code=400, detail=STUDENT_ID_ERROR)
    return {"token": issue_token(student_id), "student_id": student_id}


@router.get("/config")
def public_config():
    """前端需要的系統設定（原本由 Jinja2 模板帶入）。"""
    return {
        "checkin_deadline_minutes": config.CHECKIN_DEADLINE_MINUTES,
        "open_hour": config.OPEN_HOUR,
        "close_hour": config.CLOSE_HOUR,
        "timezone": config.TIMEZONE,
    }


@router.get("/health")
def health():
    """喚醒與保持清醒用；刻意不碰資料庫，避免把閒置暫停的 Neon 也叫醒。"""
    return {"ok": True}


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
        "leave_requested_at": b.leave_requested_at.isoformat() if b.leave_requested_at else None,
        "leave_check_at": b.leave_check_at.isoformat() if b.leave_check_at else None,
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


@router.get("/seats/events")
def list_seat_events(limit: int = 20, db: Session = Depends(get_db)):
    """近期座位狀態變更，供平面圖事件流載入時填充（新到舊）。

    資料來自 seat_status_logs——即時推播與此處回傳同一組欄位，前端共用渲染邏輯。
    """
    limit = max(1, min(limit, 100))  # 夾住上限，避免無界查詢
    rows = (
        db.query(SeatStatusLog, Seat.label)
        .join(Seat, Seat.id == SeatStatusLog.seat_id)
        .order_by(SeatStatusLog.created_at.desc(), SeatStatusLog.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "events": [
            {
                "seat_id": log.seat_id,
                "label": label,
                "from_status": log.from_status.value,
                "to_status": log.to_status.value,
                "source": log.source,
                "created_at": log.created_at.isoformat(),
            }
            for log, label in rows
        ]
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
            "seat_status": seat.status.value,
            # 結束使用時顯示「仍偵測到您／物品仍在」用；None＝該座位沒有偵測資料
            "last_detection": seat.last_detection}


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


def _booking_op(fn, booking_id: int, student_id: str, db: Session) -> dict:
    try:
        booking = fn(db, booking_id, student_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return booking_to_dict(booking)


@router.post("/bookings/{booking_id}/leave")
def leave_seat(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """結束使用：進入收拾中，定期檢查到離開才釋放（spec: seat-booking / End of Use）。"""
    return _booking_op(BookingService.request_leave, booking_id, require_student(request), db)


@router.post("/bookings/{booking_id}/resume")
def resume_seat(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """收拾中按「繼續使用」。"""
    return _booking_op(BookingService.resume_use, booking_id, require_student(request), db)


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
    """座位 ROI。四點標定只有 points；立體框選另帶桌面與地板投影（格式同 calibrate.box_record）。"""
    points: list[list[int]]              # 外輪廓多邊形 [[x,y], ...]
    top: list[list[int]] | None = None    # 桌面四角
    floor: list[list[int]] | None = None  # 桌腳落地的投影四角（由桌面推算，需搭配 top）


ROI_MIN_POINTS, ROI_MAX_POINTS = 3, 16  # 凸包最多 8 點，上限留給手動多邊形


def _roi_error(body: RoiRequest) -> str | None:
    """只驗證結構（design D2）；幾何是否合理由標定工具負責。"""
    if not ROI_MIN_POINTS <= len(body.points) <= ROI_MAX_POINTS:
        return f"外輪廓需為 {ROI_MIN_POINTS}～{ROI_MAX_POINTS} 點"
    for name, pts in (("桌面", body.top), ("地板投影", body.floor)):
        if pts is not None and len(pts) != 4:
            return f"{name}需為四點座標"
    if body.floor is not None and body.top is None:
        return "地板投影需與桌面一併提供"
    for pts in (body.points, body.top or [], body.floor or []):
        if any(len(p) != 2 or p[0] < 0 or p[1] < 0 for p in pts):
            return "座標需為非負整數 [x, y]"
    return None


@router.put("/seats/{seat_label}/roi", dependencies=[Depends(require_admin)])
def set_seat_roi(seat_label: str, body: RoiRequest, db: Session = Depends(get_db)):
    """標定工具寫入座位 ROI。正式部署時應加上管理者驗證。"""
    error = _roi_error(body)
    if error:
        raise HTTPException(status_code=400, detail=error)
    seat = db.query(Seat).filter(Seat.label == seat_label).first()
    if not seat:
        raise HTTPException(status_code=404, detail="座位不存在")
    seat.roi = body.model_dump(exclude_none=True)
    db.commit()
    return {"ok": True, "seat": seat_to_dict(seat)}


# ---- 偵測端事件（spec: seat-detection / State Change Synchronization）----

class DetectionEvent(BaseModel):
    seat_label: str
    # person_present / person_left_belongings / seat_vacant
    event: str


class DetectionBatch(BaseModel):
    events: list[DetectionEvent]


@router.post("/detection/events", dependencies=[Depends(require_detection_key)])
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
