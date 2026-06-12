"""匯出所有 ORM models，確保 Base.metadata 完整（Alembic autogenerate 依賴此處）。"""
from src.models.booking import Booking
from src.models.idle_event import IdleEvent
from src.models.notification import Notification
from src.models.seat import Seat, SeatStatus, SeatStatusLog

__all__ = ["Booking", "IdleEvent", "Notification", "Seat", "SeatStatus", "SeatStatusLog"]
