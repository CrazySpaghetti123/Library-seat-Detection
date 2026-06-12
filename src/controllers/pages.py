"""頁面 Controller（View 由 Jinja2 模板渲染）。"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src import config
from src.database import get_db
from src.models.seat import Seat

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "views" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

# 學號格式：英數 4–15 碼（輕量驗證，正式介接 SSO 後可移除）
STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{4,15}$")


@router.get("/")
def index(request: Request):
    if request.session.get("student_id"):
        return RedirectResponse("/map", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, student_id: str = Form(...)):
    student_id = student_id.strip().upper()
    if not STUDENT_ID_PATTERN.match(student_id):
        return templates.TemplateResponse(
            request, "login.html", {"error": "學號格式不正確（英數 4–15 碼）"}
        )
    request.session["student_id"] = student_id
    return RedirectResponse("/map", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/map")
def floor_map(request: Request, db: Session = Depends(get_db)):
    student_id = request.session.get("student_id")
    if not student_id:
        return RedirectResponse("/login", status_code=302)
    floors = sorted({f for (f,) in db.query(Seat.floor).distinct()})
    return templates.TemplateResponse(request, "map.html", {
        "student_id": student_id,
        "floors": floors,
        "checkin_deadline_minutes": config.CHECKIN_DEADLINE_MINUTES,
    })


@router.get("/admin/reports")
def reports_dashboard(request: Request):
    # 專題階段儀表板不另設管理者權限，正式部署時應加上管理者驗證
    return templates.TemplateResponse(request, "dashboard.html", {
        "open_hour": config.OPEN_HOUR,
        "close_hour": config.CLOSE_HOUR,
    })
