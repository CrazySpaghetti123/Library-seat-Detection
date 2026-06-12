"""座位狀態機——全系統唯一的狀態轉換入口（design.md D4）。

偵測端、預約 API、逾時排程都必須經由 transition() 變更座位狀態，
以保證：合法性驗證、歷史紀錄（seat_status_logs）、WebSocket 廣播三者一致。
"""
from typing import Callable

from sqlalchemy.orm import Session

from src.models.seat import Seat, SeatStatus, SeatStatusLog
from src.utils import utcnow

# (from, to) 合法轉換表
VALID_TRANSITIONS: set[tuple[SeatStatus, SeatStatus]] = {
    (SeatStatus.AVAILABLE, SeatStatus.RESERVED),     # 預約
    (SeatStatus.AVAILABLE, SeatStatus.OCCUPIED),     # 未預約直接入座（walk-in）
    (SeatStatus.AVAILABLE, SeatStatus.MAINTENANCE),  # 管理者
    (SeatStatus.RESERVED, SeatStatus.OCCUPIED),      # 報到
    (SeatStatus.RESERVED, SeatStatus.AVAILABLE),     # 取消／逾期未報到
    (SeatStatus.OCCUPIED, SeatStatus.AWAY),          # 離席達提示門檻
    (SeatStatus.OCCUPIED, SeatStatus.AVAILABLE),     # 淨空釋放／結束使用
    (SeatStatus.AWAY, SeatStatus.OCCUPIED),          # 確認仍在使用／本人返回
    (SeatStatus.AWAY, SeatStatus.AVAILABLE),         # 逾時釋放
    (SeatStatus.MAINTENANCE, SeatStatus.AVAILABLE),  # 維修完成
}


class InvalidTransitionError(ValueError):
    pass


class SeatStateService:
    # 轉換後的通知掛勾：fn(seat_id, label, to_status_value)
    # main.py 啟動時掛上 WebSocket 廣播；測試可掛假函式驗證
    on_transition_hooks: list[Callable[[int, str, str], None]] = []

    @classmethod
    def transition(cls, db: Session, seat: Seat, to_status: SeatStatus, source: str) -> Seat:
        """驗證並執行狀態轉換，寫入歷史紀錄並觸發廣播掛勾。

        source: booking / detection / timeout / admin
        """
        from_status = seat.status
        if (from_status, to_status) not in VALID_TRANSITIONS:
            raise InvalidTransitionError(
                f"座位 {seat.label} 不允許由 {from_status.value} 轉換為 {to_status.value}"
            )

        seat.status = to_status
        seat.updated_at = utcnow()
        db.add(SeatStatusLog(
            seat_id=seat.id,
            from_status=from_status,
            to_status=to_status,
            source=source,
        ))
        db.flush()

        for hook in cls.on_transition_hooks:
            try:
                hook(seat.id, seat.label, to_status.value)
            except Exception:  # 廣播失敗不得影響資料寫入
                pass
        return seat
