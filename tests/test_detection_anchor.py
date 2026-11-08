"""人員判定錨點（接地點 vs 框中心）：spec seat-detection / Person Occupancy Detection。

座標系為影像座標：y 向下遞增，畫面下方＝離相機較近。
ROI 為座位平面上的四邊形，人是立體物件，其偵測框會沿透視方向往畫面上方延伸。
"""
from src.detection.detector import (
    ANCHOR_CENTER,
    ANCHOR_GROUND,
    BELONGING_CLASSES,
    PERSON_CLASS,
    RAW_BELONGINGS,
    RAW_PRESENT,
    RAW_VACANT,
    anchor_point,
    classify_seat,
)

ROI = [[0, 0], [100, 0], [100, 100], [0, 100]]
BELONGING = next(iter(BELONGING_CLASSES))

# 坐在 A1 的人：框底邊（接地點 y=90）在 ROI 內，但框往上延伸到 y=-110，
# 使框幾何中心 y=-10 溢出 ROI 上緣。
SEATED_PERSON = (PERSON_CLASS, 40, -110, 60, 90)

# 站在 A1 前方走道（離相機較近）的人：接地點 y=150 在 ROI 下緣之外，
# 但框往上延伸到 y=-50，使框幾何中心 y=50 恰好落在 ROI 內。
PASSERBY_PERSON = (PERSON_CLASS, 40, -50, 60, 150)


def simple_point_in_polygon(points, point):
    """測試用簡化版（矩形 ROI 直接用邊界判斷）。"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) <= point[0] <= max(xs) and min(ys) <= point[1] <= max(ys)


# ---- anchor_point ----

def test_person_anchors_to_box_bottom_center():
    assert anchor_point(PERSON_CLASS, 40, -110, 60, 90) == (50, 90)


def test_person_anchors_to_box_center_when_configured():
    assert anchor_point(PERSON_CLASS, 40, -110, 60, 90, ANCHOR_CENTER) == (50, -10)


def test_belongings_always_anchor_to_box_center():
    assert anchor_point(BELONGING, 40, 20, 60, 80) == (50, 50)
    # 物品不受 person_anchor 影響
    assert anchor_point(BELONGING, 40, 20, 60, 80, ANCHOR_GROUND) == (50, 50)
    assert anchor_point(BELONGING, 40, 20, 60, 80, ANCHOR_CENTER) == (50, 50)


# ---- 接地點判定（預設行為）----

def test_seated_person_detected_though_box_center_overflows_roi():
    """坐姿者框中心溢出 ROI，但接地點在內 → 仍判定有人（避免漏判）。"""
    assert classify_seat(ROI, [SEATED_PERSON], simple_point_in_polygon) == RAW_PRESENT


def test_passerby_in_front_not_counted_though_box_covers_roi():
    """前方走道經過者框覆蓋 ROI，但接地點在外 → 不判定有人（避免誤判）。"""
    assert classify_seat(ROI, [PASSERBY_PERSON], simple_point_in_polygon) == RAW_VACANT


# ---- center 模式回退：確認兩情境回到舊行為 ----

def test_center_mode_misses_seated_person():
    assert classify_seat(ROI, [SEATED_PERSON], simple_point_in_polygon,
                         ANCHOR_CENTER) == RAW_VACANT


def test_center_mode_false_positives_on_passerby():
    assert classify_seat(ROI, [PASSERBY_PERSON], simple_point_in_polygon,
                         ANCHOR_CENTER) == RAW_PRESENT


# ---- 物品判定不受錨點模式影響 ----

def test_belongings_classification_independent_of_anchor_mode():
    detections = [(BELONGING, 45, 45, 55, 55)]
    for mode in (ANCHOR_GROUND, ANCHOR_CENTER):
        assert classify_seat(ROI, detections, simple_point_in_polygon,
                             mode) == RAW_BELONGINGS


def test_passerby_does_not_mask_belongings_on_the_desk():
    """前方經過者不應蓋掉桌上物品的疑似佔位判定。"""
    detections = [PASSERBY_PERSON, (BELONGING, 45, 45, 55, 55)]
    assert classify_seat(ROI, detections, simple_point_in_polygon) == RAW_BELONGINGS
