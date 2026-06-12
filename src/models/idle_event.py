from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class IdleEvent(Base):
    """疑似佔位／淨空事件（spec: seat-timeout）。

    kind: away（人離開、物品仍在）/ vacant（人與物品皆離開）
    resolution: confirmed（按「我仍在使用」）/ returned（本人返回）/ released（逾時釋放）
    未解決事件＝resolved_at 為 NULL。
    """

    __tablename__ = "idle_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))
    away_started_at: Mapped[datetime] = mapped_column(DateTime)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
