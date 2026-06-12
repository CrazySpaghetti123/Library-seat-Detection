# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NTUST capstone project: a real-time study-room seat vacancy detection system. Computer vision (YOLOv8 + OpenCV) detects seat occupancy from camera feeds, a FastAPI MVC backend manages booking/timeout rules over PostgreSQL (SQLite in dev), and an RWD web map shows live seat states via WebSocket. See `docs/technical_architecture.md` for the architecture and `docs/roadmap.md` for the two-semester plan.

Documentation, comments, and user-facing strings are written in Traditional Chinese.

## Running

```
pip install -r requirements.txt        # web backend
alembic upgrade head                   # create schema (dev.db by default)
python scripts/seed_seats.py           # seed demo seats (12 seats, 3F)
uvicorn src.main:app --reload          # http://127.0.0.1:8000
```

- `DATABASE_URL` env var switches DB: default `sqlite:///dev.db`, production `postgresql+psycopg://…`.
- Detection process (separate machine OK, needs `requirements-detection.txt`): `python -m src.detection.calibrate --seat A1` then `python -m src.detection.detector --source 0 --show`.
- No camera? `python scripts/simulate_detection.py A1 person_present` replays detection events against the API.
- Timer params for demos: set `AWAY_THRESHOLD_MINUTES` / `CONFIRM_WINDOW_MINUTES` / `CHECKIN_DEADLINE_MINUTES` / `VACANT_THRESHOLD_MINUTES` env vars.

## Testing

```
python -m pytest -q
```

Tests use in-memory SQLite (`tests/conftest.py`); timeout tests manipulate DB timestamp anchors instead of mocking the clock. Console is cp950 — set `PYTHONIOENCODING=utf-8` when running Python scripts that print Chinese.

## Architecture (MVC)

- `src/models/` — SQLAlchemy ORM: `Seat`/`SeatStatus` (AVAILABLE/RESERVED/OCCUPIED/AWAY/MAINTENANCE), `Booking`, `SeatStatusLog`, `IdleEvent`, `Notification`. Schema changes go through Alembic (`alembic/`).
- `src/services/` — business rules. **All seat status changes must go through `SeatStateService.transition()`** (validates against `VALID_TRANSITIONS`, writes `seat_status_logs`, fires WebSocket hooks). `BookingService` (reserve/check-in/cancel/no-show; one active booking per student), `IdleTimeoutService` (away/vacant timers; anchors persisted in DB, swept by APScheduler in `scheduler.py`), `ReportService` (usage rates from `seat_status_logs` only).
- `src/controllers/` — thin FastAPI routers: `pages` (Jinja2 views, session login by student ID), `api` (REST + detection events), `reports`, `ws` (ConnectionManager; sync code publishes via `run_coroutine_threadsafe`).
- `src/views/` — Jinja2 templates + static JS (map.js renders SVG floor map, reconnecting WebSocket re-fetches the full snapshot).
- `src/detection/` — standalone process; talks to the backend only via HTTP (`PUT /api/seats/{label}/roi`, `POST /api/detection/events`), offline events queue to `detection_queue.jsonl`.
- All datetimes are naive UTC (`src/utils.py:utcnow`) for SQLite/PostgreSQL parity; only SQLite+PG common SQL features are allowed.

## Spec-Driven Development (OpenSpec)

This repo uses OpenSpec: behavior is specified in `openspec/specs/<capability>/spec.md` (requirements + WHEN/THEN scenarios) before implementation, and changes flow through `openspec/changes/<name>/` (proposal → design → tasks → archive). Capabilities: `seat-booking`, `seat-detection`, `seat-timeout`, `floor-map-web`, `usage-report`. Keep code consistent with the specs and update them through the OpenSpec change workflow rather than editing ad hoc.

The `openspec` CLI drives this workflow (`openspec new change "<name>"`, `openspec status --change "<name>"`). Detailed workflow instructions live in `.agent/workflows/opsx-*.md` and `.agent/skills/openspec-*/SKILL.md`.
