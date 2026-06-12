"""開發測試用：清空預約／事件／通知／歷史紀錄，所有座位歸零為 AVAILABLE。

用法（DATABASE_URL 決定作用在哪個資料庫，不設則為 SQLite dev.db）：
    python scripts/reset_seats.py

注意：會刪除所有動態資料（座位主檔與 ROI 標定保留），僅供開發環境使用。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal
from src.models import Booking, IdleEvent, Notification, SeatStatusLog
from src.models.seat import Seat, SeatStatus


def main() -> None:
    db = SessionLocal()
    try:
        for model in (IdleEvent, Notification, Booking, SeatStatusLog):
            db.query(model).delete()
        updated = db.query(Seat).update({Seat.status: SeatStatus.AVAILABLE})
        db.commit()
        print(f"重置完成：{updated} 席已全部恢復為 AVAILABLE，動態資料已清空")
    finally:
        db.close()


if __name__ == "__main__":
    main()
