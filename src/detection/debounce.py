"""去抖動（spec: seat-detection / Person Occupancy Detection）。

座位的原始判定要連續維持 hold_seconds 秒才確認成立，
短暫遮擋（如有人走過鏡頭前）不會造成狀態翻轉。
"""
import time


class StateDebouncer:
    def __init__(self, hold_seconds: float = 5.0):
        self.hold_seconds = hold_seconds
        self._confirmed: dict[str, str] = {}   # seat_label -> 已確認狀態
        self._candidate: dict[str, tuple[str, float]] = {}  # seat_label -> (狀態, 起始時間)

    def update(self, seat_label: str, raw_state: str, now: float | None = None) -> str | None:
        """餵入單幀的原始判定；當狀態「確認改變」時回傳新狀態，否則回傳 None。"""
        now = time.monotonic() if now is None else now

        if raw_state == self._confirmed.get(seat_label):
            # 與已確認狀態一致：取消進行中的候選（短暫抖動結束）
            self._candidate.pop(seat_label, None)
            return None

        candidate = self._candidate.get(seat_label)
        if candidate is None or candidate[0] != raw_state:
            self._candidate[seat_label] = (raw_state, now)
            return None

        if now - candidate[1] >= self.hold_seconds:
            self._confirmed[seat_label] = raw_state
            self._candidate.pop(seat_label, None)
            return raw_state
        return None

    def confirmed_state(self, seat_label: str) -> str | None:
        return self._confirmed.get(seat_label)
