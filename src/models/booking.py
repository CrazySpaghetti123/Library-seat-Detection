from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base
from src.utils import utcnow


class Booking(Base):
    """預約紀錄，完整保存生命週期時間戳（spec: seat-booking）。

    有效預約＝ended_at 為 NULL；一個學號同時間僅能有一筆有效預約。
    end_reason: checked_out / cancelled / no_show / timeout_release / vacant_release
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    checkin_deadline: Mapped[datetime] = mapped_column(DateTime)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
