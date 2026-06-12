"""狀態機合法／非法轉換（design.md D4）。"""
import pytest

from src.models.seat import Seat, SeatStatus, SeatStatusLog
from src.services.seat_state_service import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    SeatStateService,
)


def make_seat(db, status, label=None):
    seat = Seat(label=label or f"T-{status.value}", floor="3F", status=status)
    db.add(seat)
    db.flush()
    return seat


def test_all_valid_transitions_succeed_and_log(db):
    for from_status, to_status in VALID_TRANSITIONS:
        seat = make_seat(db, from_status,
                         label=f"T-{from_status.value}-{to_status.value}")
        SeatStateService.transition(db, seat, to_status, source="admin")
        assert seat.status == to_status
        log = (
            db.query(SeatStatusLog)
            .filter_by(seat_id=seat.id, from_status=from_status, to_status=to_status)
            .one()
        )
        assert log.source == "admin"


@pytest.mark.parametrize("from_status,to_status", [
    (SeatStatus.AVAILABLE, SeatStatus.AWAY),
    (SeatStatus.RESERVED, SeatStatus.AWAY),
    (SeatStatus.RESERVED, SeatStatus.MAINTENANCE),
    (SeatStatus.AWAY, SeatStatus.RESERVED),
    (SeatStatus.MAINTENANCE, SeatStatus.OCCUPIED),
    (SeatStatus.OCCUPIED, SeatStatus.RESERVED),
])
def test_invalid_transitions_rejected(db, from_status, to_status):
    seat = make_seat(db, from_status)
    with pytest.raises(InvalidTransitionError):
        SeatStateService.transition(db, seat, to_status, source="admin")
    assert seat.status == from_status  # 狀態不得被更改
    assert db.query(SeatStatusLog).filter_by(seat_id=seat.id).count() == 0


def test_transition_hook_invoked(db):
    calls = []
    SeatStateService.on_transition_hooks.append(
        lambda seat_id, label, status: calls.append((label, status))
    )
    try:
        seat = make_seat(db, SeatStatus.AVAILABLE)
        SeatStateService.transition(db, seat, SeatStatus.RESERVED, source="booking")
        assert calls == [(seat.label, "RESERVED")]
    finally:
        SeatStateService.on_transition_hooks.clear()
