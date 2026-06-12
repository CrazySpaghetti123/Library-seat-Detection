from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base
from src.utils import utcnow


class SeatStatus(Enum):
    AVAILABLE = "AVAILABLE"      # 空閒（綠）
    RESERVED = "RESERVED"        # 已預約（紅）
    OCCUPIED = "OCCUPIED"        # 使用中（紅）
    AWAY = "AWAY"                # 疑似佔位：人離開、待確認（橘）
    MAINTENANCE = "MAINTENANCE"  # 維修中（灰）


# native_enum=False：以 VARCHAR+CHECK 儲存，SQLite 與 PostgreSQL 行為一致
SeatStatusColumn = SAEnum(SeatStatus, native_enum=False, length=20)


class Seat(Base):
    __tablename__ = "seats"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(20), unique=True)  # 例：A1
    floor: Mapped[str] = mapped_column(String(20))               # 例：3F
    # 攝影機畫面中的 ROI 四點座標 [[x,y]x4]，未標定為 None
    roi: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 平面圖（SVG）上的繪製座標
    map_x: Mapped[int] = mapped_column(default=0)
    map_y: Mapped[int] = mapped_column(default=0)
    status: Mapped[SeatStatus] = mapped_column(SeatStatusColumn, default=SeatStatus.AVAILABLE)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SeatStatusLog(Base):
    """全部狀態轉換歷史——使用率報表的唯一資料來源。"""

    __tablename__ = "seat_status_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), index=True)
    from_status: Mapped[SeatStatus] = mapped_column(SeatStatusColumn)
    to_status: Mapped[SeatStatus] = mapped_column(SeatStatusColumn)
    # 變更來源：booking / detection / timeout / admin
    source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
