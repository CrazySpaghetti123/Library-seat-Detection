"""偵測端實機路徑：讀取立體框選 ROI、判定模式切換（spec: seat-detection）。

assign_layered() 本身的重疊情境測試在 test_evaluation.py。
"""
import pytest

from src.detection.detector import (
    MATCH_DESK_FIRST,
    MATCH_PER_SEAT,
    RAW_PRESENT,
    RAW_VACANT,
    calibrated_rois,
    judge_frame,
    parse_args,
)


def _pip(poly, point):
    """射線法點在多邊形內（不依賴 OpenCV）。"""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _rect(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


# 前排 A1 桌面 y 240~280、外輪廓到 400；後排 B1 桌面 y 120~160、外輪廓往下延伸到 300，蓋到 A1 桌面
ROWS = {
    "A1": {"points": _rect(0, 240, 100, 400), "top": _rect(0, 240, 100, 280)},
    "B1": {"points": _rect(0, 120, 100, 300), "top": _rect(0, 120, 100, 160)},
}
# 坐在 A1 的人：框底停在 A1 桌面（y=260），也落在 B1 外輪廓內
FRONT_ROW_PERSON = (0, 20, 100, 80, 260)


def test_calibrated_rois_keeps_box_structure_and_skips_uncalibrated(caplog):
    seats = [
        {"label": "A1", "roi": {"points": _rect(0, 0, 10, 10)}},
        {"label": "B1", "roi": ROWS["B1"]},
        {"label": "B2", "roi": None},
        {"label": "B3", "roi": {"points": []}},
    ]
    rois = calibrated_rois(seats)
    assert rois == {"A1": {"points": _rect(0, 0, 10, 10)}, "B1": ROWS["B1"]}
    assert "B2" in caplog.text and "B3" in caplog.text


def test_desk_first_counts_front_row_person_once():
    raws = judge_frame(ROWS, [FRONT_ROW_PERSON], _pip, MATCH_DESK_FIRST)
    assert raws == {"A1": RAW_PRESENT, "B1": RAW_VACANT}


def test_per_seat_counts_overlap_for_both_rows():
    raws = judge_frame(ROWS, [FRONT_ROW_PERSON], _pip, MATCH_PER_SEAT)
    assert raws == {"A1": RAW_PRESENT, "B1": RAW_PRESENT}


def test_desk_first_works_with_four_point_rois():
    rois = {"A1": {"points": _rect(0, 0, 100, 100)}, "A2": {"points": _rect(100, 0, 200, 100)}}
    person = (0, 120, 10, 160, 90)  # 接地點 (140, 90) 在 A2
    assert judge_frame(rois, [person], _pip) == {"A1": RAW_VACANT, "A2": RAW_PRESENT}


def test_default_mode_is_desk_first():
    args = parse_args([])
    assert args.match == MATCH_DESK_FIRST


def test_per_seat_allows_box_center_anchor():
    args = parse_args(["--match", "per-seat", "--person-anchor", "center"])
    assert (args.match, args.person_anchor) == (MATCH_PER_SEAT, "center")


def test_desk_first_rejects_box_center_anchor():
    with pytest.raises(SystemExit):
        parse_args(["--person-anchor", "center"])
