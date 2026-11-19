"""使用率報表計算（spec: usage-report）。

既有測試驗證狀態區間切分，固定在 TIMEZONE=UTC 下執行；
台灣時區的換算另見檔案後段（spec: Hours follow local time / Day boundary follows local time）。
"""
from datetime import date, datetime, timedelta

import pytest

from src import config
from src.models.idle_event import IdleEvent
from src.models.seat import Seat, SeatStatus, SeatStatusLog
from src.services.report_service import ReportService

DAY = date(2026, 6, 10)


@pytest.fixture(autouse=True)
def utc_reports(monkeypatch):
    monkeypatch.setattr(config, "TIMEZONE", "UTC")
    monkeypatch.setattr(config, "OPEN_HOUR", 8)
    monkeypatch.setattr(config, "CLOSE_HOUR", 22)


@pytest.fixture
def taipei(monkeypatch):
    """台灣時間、開館 10:00–20:00（上雲後的設定）。"""
    monkeypatch.setattr(config, "TIMEZONE", "Asia/Taipei")
    monkeypatch.setattr(config, "OPEN_HOUR", 10)
    monkeypatch.setattr(config, "CLOSE_HOUR", 20)


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


# ---- 台灣時區（DB 存 UTC，報表以當地時間計算） ----

def test_taipei_hourly_usage_uses_local_hours(db, taipei):
    seat = make_seat(db)
    # 台灣 10:00 入座、11:30 離開 = UTC 02:00、03:30
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED, datetime(2026, 6, 10, 2, 0))
    add_log(db, seat, SeatStatus.OCCUPIED, SeatStatus.AVAILABLE, datetime(2026, 6, 10, 3, 30))

    report = ReportService.hourly_usage(db, DAY)
    rates = {row["hour"]: row["rate"] for row in report["hourly"]}
    assert list(rates) == list(range(10, 20))
    assert rates[10] == 100.0
    assert rates[11] == 50.0
    assert report["peak_hour"] == 10


def test_taipei_usage_outside_opening_hours_not_counted(db, taipei):
    seat = make_seat(db)
    # 台灣 08:00–10:00（UTC 00:00–02:00）與 20:00–22:00（UTC 12:00–14:00）都在開館時段外
    for start, end in ((0, 2), (12, 14)):
        add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED, datetime(2026, 6, 10, start))
        add_log(db, seat, SeatStatus.OCCUPIED, SeatStatus.AVAILABLE, datetime(2026, 6, 10, end))

    report = ReportService.hourly_usage(db, DAY)
    assert all(row["rate"] == 0.0 for row in report["hourly"])
    assert ReportService.daily_trend(db, DAY, DAY)["days"][0]["rate"] == 0.0


def test_taipei_daily_trend_uses_local_day(db, taipei):
    seat = make_seat(db)
    # 台灣 6/11 10:00–20:00 整段使用 = UTC 6/11 02:00–12:00；查 6/10 應為 0、6/11 為 100
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED, datetime(2026, 6, 11, 2, 0))
    add_log(db, seat, SeatStatus.OCCUPIED, SeatStatus.AVAILABLE, datetime(2026, 6, 11, 12, 0))

    days = ReportService.daily_trend(db, DAY, date(2026, 6, 11))["days"]
    assert [d["rate"] for d in days] == [0.0, 100.0]


def test_taipei_idle_stats_day_boundary(db, taipei):
    from src.services.report_service import local_day_bounds
    seat = make_seat(db)
    # 台灣 6/11 01:00 釋放 = UTC 6/10 17:00：不算 6/10，算 6/11
    db.add(IdleEvent(seat_id=seat.id, kind="away",
                     away_started_at=datetime(2026, 6, 10, 16, 30),
                     resolved_at=datetime(2026, 6, 10, 17, 0), resolution="released"))
    db.flush()

    assert ReportService.idle_stats(db, *local_day_bounds(DAY, DAY))["released_count"] == 0
    next_day = date(2026, 6, 11)
    assert ReportService.idle_stats(db, *local_day_bounds(next_day, next_day))["released_count"] == 1


def test_taipei_csv_hours_are_local(db, taipei):
    seat = make_seat(db)
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED, datetime(2026, 6, 10, 2, 0))
    csv_text = ReportService.usage_csv(db, DAY, DAY)
    assert "2026-06-10,10,100.0" in csv_text
    assert "2026-06-10,8," not in csv_text  # 開館前的小時不列出


def test_half_hour_offset_buckets_align_to_local_hours(db, monkeypatch):
    """非整點偏移的時區（印度 UTC+5:30），小時桶仍對齊當地整點。"""
    monkeypatch.setattr(config, "TIMEZONE", "Asia/Kolkata")
    seat = make_seat(db)
    # 當地 10:00–11:00 = UTC 04:30–05:30
    add_log(db, seat, SeatStatus.AVAILABLE, SeatStatus.OCCUPIED, datetime(2026, 6, 10, 4, 30))
    add_log(db, seat, SeatStatus.OCCUPIED, SeatStatus.AVAILABLE, datetime(2026, 6, 10, 5, 30))

    rates = {r["hour"]: r["rate"] for r in ReportService.hourly_usage(db, DAY)["hourly"]}
    assert rates[10] == 100.0
    assert rates[9] == 0.0 and rates[11] == 0.0
