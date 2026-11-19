"""使用率報表（spec: usage-report）。

唯一資料來源為 seat_status_logs：由狀態轉換紀錄重建每個座位的
狀態區間，再切分至小時桶累計。
使用率 =（OCCUPIED + RESERVED + AWAY 的座位秒數）÷（座位數 × 開放秒數）。

時間：DB 存 naive UTC；查詢日期、開館時段與小時桶皆以 config.TIMEZONE 的當地時間計算，
只在邊界換算（spec: usage-report / Hours follow local time）。
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src import config
from src.models.idle_event import IdleEvent
from src.models.seat import Seat, SeatStatus, SeatStatusLog

BUSY_STATUSES = {SeatStatus.OCCUPIED, SeatStatus.RESERVED, SeatStatus.AWAY}


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)  # 每次讀取設定，測試可切換時區


def local_to_utc(local: datetime) -> datetime:
    """當地 naive 時間 → naive UTC（DB 比較用）。"""
    return local.replace(tzinfo=_tz()).astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(utc: datetime) -> datetime:
    """naive UTC → 當地 naive 時間（分組用）。"""
    return utc.replace(tzinfo=timezone.utc).astimezone(_tz()).replace(tzinfo=None)


def local_day_bounds(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    """當地日期區間（含首尾兩日整天）→ naive UTC 起訖。"""
    return (local_to_utc(datetime.combine(start_day, time.min)),
            local_to_utc(datetime.combine(end_day, time.max)))


def _open_window(day: date) -> tuple[datetime, datetime]:
    """當地開館時段 → naive UTC 起訖。"""
    return (local_to_utc(datetime.combine(day, time(config.OPEN_HOUR))),
            local_to_utc(datetime.combine(day, time(config.CLOSE_HOUR))))


class ReportService:

    # ---- 核心：重建狀態區間並累計各小時的「忙碌秒數」 ----

    @staticmethod
    def _seat_ids(db: Session, floor: str | None) -> list[int]:
        q = db.query(Seat.id)
        if floor:
            q = q.filter(Seat.floor == floor)
        return [sid for (sid,) in q.all()]

    @classmethod
    def _busy_seconds_by_hour(cls, db: Session, start: datetime, end: datetime,
                              floor: str | None) -> tuple[dict[datetime, float], int, bool]:
        """start／end 為 naive UTC；回傳（{當地小時桶起點: 忙碌秒數}, 座位數, 區間內是否有任何紀錄）。"""
        seat_ids = cls._seat_ids(db, floor)
        if not seat_ids:
            return {}, 0, False

        logs = (
            db.query(SeatStatusLog)
            .filter(SeatStatusLog.seat_id.in_(seat_ids),
                    SeatStatusLog.created_at <= end)
            .order_by(SeatStatusLog.seat_id, SeatStatusLog.created_at)
            .all()
        )
        has_data = any(start <= log.created_at <= end for log in logs)

        # 依座位分組，重建狀態區間（首筆紀錄前視為 AVAILABLE）
        by_seat: dict[int, list[SeatStatusLog]] = defaultdict(list)
        for log in logs:
            by_seat[log.seat_id].append(log)

        buckets: dict[datetime, float] = defaultdict(float)
        for sid in seat_ids:
            cursor, status = start, SeatStatus.AVAILABLE
            for log in by_seat.get(sid, []):
                t = max(log.created_at, start)
                if t > cursor and status in BUSY_STATUSES:
                    cls._accumulate(buckets, cursor, min(t, end))
                cursor, status = max(cursor, t), log.to_status
            if cursor < end and status in BUSY_STATUSES:
                cls._accumulate(buckets, cursor, end)
        return buckets, len(seat_ids), has_data

    @staticmethod
    def _accumulate(buckets: dict[datetime, float], t0: datetime, t1: datetime) -> None:
        """將忙碌區間 [t0, t1)（naive UTC）切分進當地整點的小時桶。

        桶鍵為當地 naive 時間；桶的結束點換回 UTC 比較，非整點偏移的時區也對齊當地整點。
        """
        cursor = t0
        while cursor < t1:
            bucket = utc_to_local(cursor).replace(minute=0, second=0, microsecond=0)
            bucket_end = local_to_utc(bucket + timedelta(hours=1))
            seg_end = min(t1, bucket_end)
            buckets[bucket] += (seg_end - cursor).total_seconds()
            cursor = seg_end

    # ---- 報表查詢 ----

    @classmethod
    def hourly_usage(cls, db: Session, day: date, floor: str | None = None) -> dict:
        """某日（當地）開放時段的逐時使用率與尖峰時段，小時為當地時間。"""
        start, end = _open_window(day)
        buckets, seat_count, has_data = cls._busy_seconds_by_hour(db, start, end, floor)

        hourly = []
        for h in range(config.OPEN_HOUR, config.CLOSE_HOUR):
            bucket = datetime.combine(day, time(h))
            denominator = seat_count * 3600
            rate = (buckets.get(bucket, 0.0) / denominator * 100) if denominator else 0.0
            hourly.append({"hour": h, "rate": round(rate, 1)})

        peak = max(hourly, key=lambda x: x["rate"]) if hourly else None
        return {
            "date": day.isoformat(), "floor": floor, "hourly": hourly,
            "peak_hour": peak["hour"] if peak and peak["rate"] > 0 else None,
            "has_data": has_data,
        }

    @classmethod
    def daily_trend(cls, db: Session, start_day: date, end_day: date,
                    floor: str | None = None) -> dict:
        """日使用率趨勢（含週統計用途，前端可自行彙整為週）。"""
        days = []
        cursor = start_day
        while cursor <= end_day:
            start, end = _open_window(cursor)
            buckets, seat_count, _ = cls._busy_seconds_by_hour(db, start, end, floor)
            denominator = seat_count * (config.CLOSE_HOUR - config.OPEN_HOUR) * 3600
            rate = (sum(buckets.values()) / denominator * 100) if denominator else 0.0
            days.append({"date": cursor.isoformat(), "rate": round(rate, 1)})
            cursor += timedelta(days=1)
        return {"floor": floor, "days": days}

    @classmethod
    def floor_comparison(cls, db: Session, start_day: date, end_day: date) -> dict:
        floors = sorted({f for (f,) in db.query(Seat.floor).distinct()})
        result = []
        for floor in floors:
            trend = cls.daily_trend(db, start_day, end_day, floor)
            rates = [d["rate"] for d in trend["days"]]
            avg = sum(rates) / len(rates) if rates else 0.0
            result.append({"floor": floor, "rate": round(avg, 1)})
        return {"floors": result}

    # ---- 佔位行為統計 ----

    @classmethod
    def idle_stats(cls, db: Session, start: datetime, end: datetime) -> dict:
        """start／end 為 naive UTC；以當地日期查詢時用 local_day_bounds() 換算。"""
        events = (
            db.query(IdleEvent)
            .filter(IdleEvent.resolution == "released",
                    IdleEvent.resolved_at >= start,
                    IdleEvent.resolved_at <= end)
            .all()
        )
        released_count = len(events)
        durations = [
            (e.resolved_at - e.away_started_at).total_seconds() / 60 for e in events
        ]
        avg_away = round(sum(durations) / len(durations), 1) if durations else 0.0

        counts: dict[int, int] = defaultdict(int)
        for e in events:
            counts[e.seat_id] += 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        labels = {s.id: s.label for s in db.query(Seat).filter(Seat.id.in_(counts.keys()))} \
            if counts else {}
        return {
            "released_count": released_count,
            "avg_away_minutes": avg_away,
            "top_seats": [{"label": labels.get(sid, str(sid)), "count": c}
                          for sid, c in top],
        }

    # ---- CSV 匯出 ----

    @classmethod
    def usage_csv(cls, db: Session, start_day: date, end_day: date,
                  floor: str | None = None) -> str:
        lines = ["date,hour,usage_rate_percent"]
        cursor = start_day
        while cursor <= end_day:
            report = cls.hourly_usage(db, cursor, floor)
            for row in report["hourly"]:
                lines.append(f"{cursor.isoformat()},{row['hour']},{row['rate']}")
            cursor += timedelta(days=1)
        idle = cls.idle_stats(db, *local_day_bounds(start_day, end_day))
        lines.append("")
        lines.append("idle_released_count,avg_away_minutes")
        lines.append(f"{idle['released_count']},{idle['avg_away_minutes']}")
        return "\n".join(lines)
