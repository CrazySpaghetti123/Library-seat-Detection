"""APScheduler 週期任務：離席逾時掃描、逾期未報到釋放、結束使用後的離開檢查（design.md D6）。

計時錨點皆存於 DB（idle_events、bookings.checkin_deadline），
排程只負責週期掃描，程序重啟後自然接續，不會遺失計時。
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from src import config
from src.database import SessionLocal
from src.services.booking_service import BookingService
from src.services.idle_timeout_service import IdleTimeoutService

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
LEAVE_CHECK_INTERVAL_SECONDS = 5


def sweep_once() -> None:
    """單次掃描：逾期未報到 + 離席逾時。獨立 session，失敗 rollback 不影響下次。"""
    db = SessionLocal()
    try:
        no_shows = BookingService.release_no_shows(db)
        stats = IdleTimeoutService.sweep(db)
        db.commit()
        if no_shows or any(stats.values()):
            logger.info("timeout sweep: no_show=%s %s", no_shows, stats)
    except Exception:
        db.rollback()
        logger.exception("timeout sweep 失敗")
    finally:
        db.close()


def leave_check_once() -> None:
    """收拾中檢查（結束使用，design D4）：5 秒一次，讓 30 秒檢查不被主掃描間隔拖慢。"""
    db = SessionLocal()
    try:
        stats = BookingService.process_leave_checks(db)
        db.commit()
        if stats["leave_released"]:
            logger.info("leave check: %s", stats)
    except Exception:
        db.rollback()
        logger.exception("leave check 失敗")
    finally:
        db.close()


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            sweep_once, "interval",
            seconds=config.SCHEDULER_INTERVAL_SECONDS,
            id="timeout-sweep", max_instances=1, coalesce=True,
        )
        _scheduler.add_job(
            leave_check_once, "interval", seconds=LEAVE_CHECK_INTERVAL_SECONDS,
            id="leave-check", max_instances=1, coalesce=True,
        )
        _scheduler.start()
    return _scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
