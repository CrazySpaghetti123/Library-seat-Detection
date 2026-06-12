"""網頁內通知：寫入 notifications 表並透過掛勾推播至個人 WebSocket 頻道。"""
from typing import Callable

from sqlalchemy.orm import Session

from src.models.notification import Notification
from src.utils import utcnow


class NotificationService:
    # 推播掛勾：fn(student_id, notification_dict)；main.py 掛上 WebSocket
    on_notify_hooks: list[Callable[[str, dict], None]] = []

    @classmethod
    def notify(cls, db: Session, student_id: str, type: str,
               seat_id: int | None = None, payload: dict | None = None) -> Notification:
        note = Notification(
            student_id=student_id, seat_id=seat_id, type=type, payload=payload or {}
        )
        db.add(note)
        db.flush()
        data = cls.to_dict(note)
        for hook in cls.on_notify_hooks:
            try:
                hook(student_id, data)
            except Exception:
                pass
        return note

    @staticmethod
    def unread(db: Session, student_id: str) -> list[Notification]:
        return (
            db.query(Notification)
            .filter(Notification.student_id == student_id, Notification.read_at.is_(None))
            .order_by(Notification.created_at)
            .all()
        )

    @staticmethod
    def mark_read(db: Session, notification_id: int, student_id: str) -> None:
        note = db.get(Notification, notification_id)
        if note and note.student_id == student_id and note.read_at is None:
            note.read_at = utcnow()
            db.flush()

    @staticmethod
    def to_dict(note: Notification) -> dict:
        return {
            "id": note.id,
            "seat_id": note.seat_id,
            "type": note.type,
            "payload": note.payload,
            "created_at": note.created_at.isoformat(),
        }
