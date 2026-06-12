"""座位主檔 seed：建立示範自習室（3F，A/B 兩排各 6 席）。

執行：python scripts/seed_seats.py
重複執行安全：已存在的座位（依 label）會跳過。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal
from src.models.seat import Seat

# (label, floor, 平面圖座標 x, y)；座標對應前端 SVG viewBox 0 0 640 360
SEATS = [
    *[(f"A{i}", "3F", 60 + (i - 1) * 95, 80) for i in range(1, 7)],
    *[(f"B{i}", "3F", 60 + (i - 1) * 95, 220) for i in range(1, 7)],
]


def main() -> None:
    db = SessionLocal()
    try:
        created = 0
        for label, floor, x, y in SEATS:
            if db.query(Seat).filter(Seat.label == label).first():
                continue
            db.add(Seat(label=label, floor=floor, map_x=x, map_y=y))
            created += 1
        db.commit()
        print(f"seed 完成：新增 {created} 席，總計 {db.query(Seat).count()} 席")
    finally:
        db.close()


if __name__ == "__main__":
    main()
