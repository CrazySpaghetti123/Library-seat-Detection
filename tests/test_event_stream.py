"""座位狀態事件流端點（spec: floor-map-web / Live Status Event Stream）。"""
from datetime import timedelta

from src.controllers.api import list_seat_events
from src.models.seat import SeatStatus, SeatStatusLog
from src.utils import utcnow


def log(db, seat, from_status, to_status, source, minutes_ago):
    db.add(SeatStatusLog(
        seat_id=seat.id,
        from_status=from_status,
        to_status=to_status,
        source=source,
        created_at=utcnow() - timedelta(minutes=minutes_ago),
    ))
    db.flush()


def test_events_returned_newest_first(db, seats):
    log(db, seats["A1"], SeatStatus.AVAILABLE, SeatStatus.RESERVED, "booking", 30)
    log(db, seats["A2"], SeatStatus.OCCUPIED, SeatStatus.AWAY, "detection", 10)
    log(db, seats["A3"], SeatStatus.AWAY, SeatStatus.AVAILABLE, "timeout", 1)

    events = list_seat_events(db=db)["events"]

    assert [e["label"] for e in events] == ["A3", "A2", "A1"]


def test_event_carries_transition_and_source(db, seats):
    log(db, seats["A1"], SeatStatus.AVAILABLE, SeatStatus.RESERVED, "booking", 5)

    event = list_seat_events(db=db)["events"][0]

    assert event["label"] == "A1"
    assert event["from_status"] == "AVAILABLE"
    assert event["to_status"] == "RESERVED"
    assert event["source"] == "booking"
    assert event["seat_id"] == seats["A1"].id
    assert event["created_at"]


def test_limit_restricts_number_of_events(db, seats):
    for i in range(5):
        log(db, seats["A1"], SeatStatus.AVAILABLE, SeatStatus.RESERVED, "booking", i)

    assert len(list_seat_events(limit=3, db=db)["events"]) == 3


def test_limit_is_clamped_to_bounds(db, seats):
    for i in range(3):
        log(db, seats["A1"], SeatStatus.AVAILABLE, SeatStatus.RESERVED, "booking", i)

    # 超出上限與非正數皆須被夾住，避免無界查詢
    assert len(list_seat_events(limit=9999, db=db)["events"]) == 3
    assert len(list_seat_events(limit=0, db=db)["events"]) == 1


def test_empty_stream_when_no_history(db, seats):
    assert list_seat_events(db=db)["events"] == []
