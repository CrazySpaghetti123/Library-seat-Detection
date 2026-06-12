"""使用率報表計算（spec: usage-report）。"""
from datetime import date, datetime, timedelta

from src.models.idle_event import IdleEvent
from src.models.seat import Seat, SeatStatus, SeatStatusLog
from src.services.report_service import ReportService

DAY = date(2026, 6, 10)


def add_log(db, seat, from_s, to_s, at, source="detection"):
    db.add(SeatStatusLog(seat_id=seat.id, from_status=from_s, to_status=to_s,
                         source=source, created_at=at))
    db.flush()


def make_seat(db, label="A1", floor="3F"):
    seat = Seat(label=label, floor=floor)
    db.add(seat)
    db.flush()
    return seat


def test_hourly_usage_splits_intervals_across_hours(db):
    seat = make_seat(db)
    # 10:00 入座、11:30 釋放 → 10 時 100%、11 時 50%
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED,
            datetime(2026, 6, 10, 10, 0))
    add_log(db, seat, SeatStatus.OCCUPIED, SeatStatus.AVAILABLE,
            datetime(2026, 6, 10, 11, 30))

    report = ReportService.hourly_usage(db, DAY)
    rates = {row["hour"]: row["rate"] for row in report["hourly"]}
    assert rates[10] == 100.0
    assert rates[11] == 50.0
    assert rates[12] == 0.0
    assert report["peak_hour"] == 10
    assert report["has_data"] is True


def test_busy_includes_reserved_and_away(db):
    seat = make_seat(db)
    # 14:00 預約、14:30 報到、15:00 轉 AWAY、15:30 釋放 → 14、15 時皆計入使用
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.RESERVED,
            datetime(2026, 6, 10, 14, 0))
    add_log(db, seat, SeatStatus.RESERVED, SeatStatus.OCCUPIED,
            datetime(2026, 6, 10, 14, 30))
    add_log(db, seat, SeatStatus.OCCUPIED, SeatStatus.AWAY,
            datetime(2026, 6, 10, 15, 0))
    add_log(db, seat, SeatStatus.AWAY, SeatStatus.AVAILABLE,
            datetime(2026, 6, 10, 15, 30))

    rates = {r["hour"]: r["rate"]
             for r in ReportService.hourly_usage(db, DAY)["hourly"]}
    assert rates[14] == 100.0
    assert rates[15] == 50.0


def test_empty_range_returns_zero_and_flag(db):
    make_seat(db)
    report = ReportService.hourly_usage(db, DAY)
    assert report["has_data"] is False
    assert all(row["rate"] == 0.0 for row in report["hourly"])
    assert report["peak_hour"] is None


def test_floor_comparison(db):
    s3 = make_seat(db, "A1", "3F")
    make_seat(db, "B1", "4F")
    add_log(db, s3, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED,
            datetime(2026, 6, 10, 8, 0))
    add_log(db, s3, SeatStatus.OCCUPIED, SeatStatus.AVAILABLE,
            datetime(2026, 6, 10, 22, 0))

    result = ReportService.floor_comparison(db, DAY, DAY)
    rates = {row["floor"]: row["rate"] for row in result["floors"]}
    assert rates["3F"] == 100.0
    assert rates["4F"] == 0.0


def test_idle_stats(db):
    seat = make_seat(db)
    start = datetime(2026, 6, 10, 12, 0)
    for offset in (0, 1):
        db.add(IdleEvent(
            seat_id=seat.id, kind="away",
            away_started_at=start + timedelta(hours=offset),
            resolved_at=start + timedelta(hours=offset, minutes=25),
            resolution="released",
        ))
    db.flush()

    stats = ReportService.idle_stats(
        db, datetime(2026, 6, 10), datetime(2026, 6, 11))
    assert stats["released_count"] == 2
    assert stats["avg_away_minutes"] == 25.0
    assert stats["top_seats"][0] == {"label": "A1", "count": 2}


def test_csv_export_contains_rows(db):
    seat = make_seat(db)
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED,
            datetime(2026, 6, 10, 10, 0))
    csv_text = ReportService.usage_csv(db, DAY, DAY)
    assert "date,hour,usage_rate_percent" in csv_text
    assert "2026-06-10,10,100.0" in csv_text
    assert "idle_released_count" in csv_text
