"""報表 API（spec: usage-report / Report Dashboard and Export）。"""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.services.report_service import ReportService

router = APIRouter(prefix="/api/reports")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"日期格式錯誤: {value}（需 YYYY-MM-DD）")


@router.get("/usage")
def usage(day: str = Query(..., alias="date"), floor: str | None = None,
          db: Session = Depends(get_db)):
    return ReportService.hourly_usage(db, _parse_date(day), floor)


@router.get("/trend")
def trend(start: str, end: str, floor: str | None = None,
          db: Session = Depends(get_db)):
    return ReportService.daily_trend(db, _parse_date(start), _parse_date(end), floor)


@router.get("/floors")
def floors(start: str, end: str, db: Session = Depends(get_db)):
    return ReportService.floor_comparison(db, _parse_date(start), _parse_date(end))


@router.get("/idle")
def idle(start: str, end: str, db: Session = Depends(get_db)):
    return ReportService.idle_stats(
        db,
        datetime.combine(_parse_date(start), time.min),
        datetime.combine(_parse_date(end), time.max),
    )


@router.get("/usage.csv")
def usage_csv(start: str, end: str, floor: str | None = None,
              db: Session = Depends(get_db)):
    csv_text = ReportService.usage_csv(db, _parse_date(start), _parse_date(end), floor)
    return PlainTextResponse(
        csv_text, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename=usage_{start}_{end}.csv"},
    )
