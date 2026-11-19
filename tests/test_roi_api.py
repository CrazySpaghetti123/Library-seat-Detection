"""座位 ROI 標定端點（spec: seat-detection / ROI Seat Calibration）。"""
import pytest
from fastapi import HTTPException

from src.controllers.api import RoiRequest, list_seats, set_seat_roi

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]
BOX = {
    "points": [[10, 10], [110, 10], [120, 60], [120, 180], [0, 180], [0, 60]],
    "top": [[10, 10], [110, 10], [120, 60], [0, 60]],
    "floor": [[10, 130], [110, 130], [120, 180], [0, 180]],
}


def roi_of(db, label):
    return next(s["roi"] for s in list_seats(db=db)["seats"] if s["label"] == label)


def test_four_point_roi_still_accepted(db, seats):
    set_seat_roi("A1", RoiRequest(points=SQUARE), db=db)
    assert roi_of(db, "A1") == {"points": SQUARE}  # 不帶空的 top/floor 欄位


def test_box_roi_stored_with_desk_and_floor(db, seats):
    set_seat_roi("A1", RoiRequest(**BOX), db=db)
    assert roi_of(db, "A1") == BOX


def test_box_roi_without_floor_accepted(db, seats):
    body = {"points": BOX["points"], "top": BOX["top"]}
    set_seat_roi("A1", RoiRequest(**body), db=db)
    assert roi_of(db, "A1") == body


@pytest.mark.parametrize("body, message", [
    ({"points": [[0, 0], [1, 1]]}, "外輪廓"),
    ({"points": [[i, i] for i in range(17)]}, "外輪廓"),
    ({"points": BOX["points"], "top": BOX["top"][:3]}, "桌面"),
    ({"points": BOX["points"], "top": BOX["top"], "floor": BOX["floor"] + [[1, 1]]}, "地板投影"),
    ({"points": BOX["points"], "floor": BOX["floor"]}, "一併提供"),
    ({"points": [[0, 0], [10, 0], [10, -5]]}, "非負"),
    ({"points": [[0, 0], [10, 0], [10]]}, "非負"),
])
def test_malformed_roi_rejected_and_original_kept(db, seats, body, message):
    set_seat_roi("A1", RoiRequest(points=SQUARE), db=db)
    with pytest.raises(HTTPException) as exc:
        set_seat_roi("A1", RoiRequest(**body), db=db)
    assert exc.value.status_code == 400
    assert message in exc.value.detail
    assert roi_of(db, "A1") == {"points": SQUARE}


def test_unknown_seat_returns_404(db, seats):
    with pytest.raises(HTTPException) as exc:
        set_seat_roi("Z9", RoiRequest(points=SQUARE), db=db)
    assert exc.value.status_code == 404
