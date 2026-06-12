"""偵測端純邏輯：去抖動與 ROI 判定（不需 ultralytics/opencv）。"""
from src.detection.debounce import StateDebouncer
from src.detection.detector import (
    BELONGING_CLASSES,
    PERSON_CLASS,
    RAW_BELONGINGS,
    RAW_PRESENT,
    RAW_VACANT,
    classify_seat,
)

ROI = [[0, 0], [100, 0], [100, 100], [0, 100]]


def simple_point_in_polygon(points, point):
    """測試用簡化版（矩形 ROI 直接用邊界判斷）。"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) <= point[0] <= max(xs) and min(ys) <= point[1] <= max(ys)


# ---- classify_seat ----

def test_person_in_roi_wins_over_belongings():
    detections = [(PERSON_CLASS, 50, 50), (next(iter(BELONGING_CLASSES)), 60, 60)]
    assert classify_seat(ROI, detections, simple_point_in_polygon) == RAW_PRESENT


def test_belongings_only_marks_idle():
    detections = [(next(iter(BELONGING_CLASSES)), 50, 50)]
    assert classify_seat(ROI, detections, simple_point_in_polygon) == RAW_BELONGINGS


def test_detections_outside_roi_ignored():
    detections = [(PERSON_CLASS, 500, 500)]
    assert classify_seat(ROI, detections, simple_point_in_polygon) == RAW_VACANT


# ---- 去抖動 ----

def test_state_confirmed_after_hold_seconds():
    d = StateDebouncer(hold_seconds=5)
    assert d.update("A1", RAW_PRESENT, now=0) is None    # 開始候選
    assert d.update("A1", RAW_PRESENT, now=3) is None    # 未滿 5 秒
    assert d.update("A1", RAW_PRESENT, now=5) == RAW_PRESENT  # 確認


def test_brief_occlusion_does_not_flip(seat_label="A1"):
    d = StateDebouncer(hold_seconds=5)
    d.update(seat_label, RAW_PRESENT, now=0)
    d.update(seat_label, RAW_PRESENT, now=5)
    assert d.confirmed_state(seat_label) == RAW_PRESENT
    # 短暫 2 秒偵測不到人（遮擋），之後回復 → 不應翻轉
    assert d.update(seat_label, RAW_VACANT, now=10) is None
    assert d.update(seat_label, RAW_VACANT, now=12) is None
    assert d.update(seat_label, RAW_PRESENT, now=13) is None
    assert d.confirmed_state(seat_label) == RAW_PRESENT
    # 候選已被清除：之後再離席要重新累計
    assert d.update(seat_label, RAW_VACANT, now=20) is None
    assert d.update(seat_label, RAW_VACANT, now=25) == RAW_VACANT
