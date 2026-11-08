"""座位主檔 seed：建立示範自習室（3F，A/B 兩排各 6 席）。

執行：python scripts/seed_seats.py
重複執行安全：已存在的座位（依 label）僅更新平面圖座標，
不動其狀態與 ROI——因此調整下方佈局後重跑即可套用新版面。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal
from src.models.seat import Seat

# (label, floor, 平面圖座標 x, y)；座標對應前端 SVG viewBox 0 0 640 360
# 座位尺寸 92x76（map.js 的 SEAT_W/SEAT_H），水平間距 6、垂直間距 24，整體置中
SEATS = [
    *[(f"A{i}", "3F", 28 + (i - 1) * 98, 92) for i in range(1, 7)],
    *[(f"B{i}", "3F", 28 + (i - 1) * 98, 192) for i in range(1, 7)],
]


def main() -> None:
    db = SessionLocal()
    try:
        created = updated = 0
        for label, floor, x, y in SEATS:
            seat = db.query(Seat).filter(Seat.label == label).first()
            if seat:
                if (seat.map_x, seat.map_y) != (x, y):
                    seat.map_x, seat.map_y = x, y
                    updated += 1
                continue
            db.add(Seat(label=label, floor=floor, map_x=x, map_y=y))
            created += 1
        db.commit()
        print(f"seed 完成：新增 {created} 席、更新座標 {updated} 席，"
              f"總計 {db.query(Seat).count()} 席")
    finally:
        db.close()


if __name__ == "__main__":
    main()
