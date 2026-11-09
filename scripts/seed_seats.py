"""座位主檔 seed：建立示範自習室（3F，A/B 兩排各 3 席，與照片評估的實拍佈局一致）。

執行：python scripts/seed_seats.py [--prune | --reset]
重複執行安全：已存在的座位（依 label）僅更新樓層與平面圖座標，
不動其狀態與 ROI——因此調整下方佈局後重跑即可套用新版面。
佈局以外的既有座位預設只列出不刪除；加 --prune 才會連同其預約、
離席事件、通知與狀態紀錄一併刪除（報表歷史會跟著消失）。
--reset 清空所有座位與全部紀錄後重建（例如結束家中單座位測試、正式開始示範前）。
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal
from src.models.booking import Booking
from src.models.idle_event import IdleEvent
from src.models.notification import Notification
from src.models.seat import Seat, SeatStatusLog

# (label, floor, 平面圖座標 x, y)；map.js 只用座標推導「第幾列第幾行」，像素尺寸由前端重算。
# 平面圖為從攝影機方向俯視：A 排靠近攝影機畫在下方、B 排在後方畫在上方，1→3 由左到右
SEATS = [
    *[(f"B{i}", "3F", 28 + (i - 1) * 98, 92) for i in range(1, 4)],
    *[(f"A{i}", "3F", 28 + (i - 1) * 98, 192) for i in range(1, 4)],
]


# 依外鍵相依順序刪除：離席事件參照預約，其餘參照座位
RECORD_MODELS = (IdleEvent, Notification, Booking, SeatStatusLog)


def prune(db, seats: list[Seat]) -> None:
    ids = [s.id for s in seats]
    for model in RECORD_MODELS:
        db.query(model).filter(model.seat_id.in_(ids)).delete(synchronize_session=False)
    for s in seats:
        db.delete(s)


def reset(db) -> dict[str, int]:
    """清空所有紀錄與座位，回傳各表刪除筆數。"""
    counts = {m.__tablename__: db.query(m).delete(synchronize_session=False) for m in RECORD_MODELS}
    counts["seats"] = db.query(Seat).delete(synchronize_session=False)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="建立／更新示範座位")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prune", action="store_true",
                      help="刪除佈局以外的座位及其所有紀錄")
    mode.add_argument("--reset", action="store_true",
                      help="清空所有座位與紀錄（預約、離席、通知、狀態紀錄）後重建")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            counts = reset(db)
            print("已清空：" + "、".join(f"{t} {n} 筆" for t, n in counts.items()))
        created = updated = 0
        for label, floor, x, y in SEATS:
            seat = db.query(Seat).filter(Seat.label == label).first()
            if seat:
                if (seat.floor, seat.map_x, seat.map_y) != (floor, x, y):
                    seat.floor, seat.map_x, seat.map_y = floor, x, y
                    updated += 1
                continue
            db.add(Seat(label=label, floor=floor, map_x=x, map_y=y))
            created += 1

        layout = {label for label, *_ in SEATS}
        extra = [s for s in db.query(Seat).order_by(Seat.label) if s.label not in layout]
        if extra and args.prune:
            prune(db, extra)
        db.commit()

        print(f"seed 完成：新增 {created} 席、更新樓層／座標 {updated} 席，"
              f"總計 {db.query(Seat).count()} 席")
        if extra:
            labels = "、".join(s.label for s in extra)
            print(f"已刪除佈局以外的座位：{labels}" if args.prune
                  else f"佈局以外仍有座位：{labels}（加 --prune 可刪除）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
