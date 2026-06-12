"""一次性：把座位主檔改為單一座位（A1, HOME），供家中單座位測試。"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal
from src.models import Booking, IdleEvent, Notification, SeatStatusLog
from src.models.seat import Seat

db = SessionLocal()
for model in (IdleEvent, Notification, Booking, SeatStatusLog):
    db.query(model).delete()
db.query(Seat).delete()
db.add(Seat(label="A1", floor="HOME", map_x=280, map_y=150))
db.commit()
print("完成：現在只有 1 席（A1, HOME），置中顯示")
db.close()
