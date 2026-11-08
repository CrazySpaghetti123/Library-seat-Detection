"""照片集離線評估的純邏輯，以及標定工具的座標換算（不需 OpenCV / ultralytics）。"""
from datetime import datetime
from pathlib import Path

import pytest

from src.detection.calibrate import display_scale, to_display, to_original
from src.detection.evaluation import (
    KIND_BELONGINGS,
    KIND_PERSON,
    KIND_VACANT,
    LabelError,
    Record,
    SeatTruth,
    compare_modes,
    compute_stats,
    format_report,
    occluded_seats,
    order_by_capture,
    parse_exif_datetime,
    parse_labels,
    parse_value,
    resolve_truth,
    sort_seats,
)

SEATS = ["A1", "A2", "A3", "B1", "B2", "B3"]
PLAN = Path(__file__).resolve().parents[1] / "scripts" / "eval_shot_plan.txt"


# ---- 標註解析 ----

def test_shot_plan_parses_into_24_complete_shots():
    shots = parse_labels(PLAN.read_text(encoding="utf-8"))
    assert len(shots) == 24
    assert shots[0].all_vacant
    # 每張都要能解析出 6 席的完整標註
    for shot in shots:
        assert len(resolve_truth(shot, SEATS)) == 6
    assert shots[10].walkway and "A1" in shots[10].note
    assert not shots[1].walkway


def test_value_kinds():
    assert parse_value("人").kind == KIND_PERSON
    assert parse_value("人(側坐)").kind == KIND_PERSON
    assert parse_value("人+書").kind == KIND_PERSON
    assert parse_value("空").kind == KIND_VACANT
    bottle = parse_value("水壺")
    assert (bottle.kind, bottle.item) == (KIND_BELONGINGS, "水壺")
    # 括號內為備註，統計時歸入同一種物品
    assert parse_value("書(闔上)").item == "書"
    assert parse_value("書（闔上）").item == "書"


def test_numbers_optional_and_skip_line():
    shots = parse_labels("全空\n廢片\nA1人 A2空\n")
    assert [s.index for s in shots] == [1, 2, 3]
    assert shots[1].skip
    assert shots[2].seats["A1"].kind == KIND_PERSON


def test_comments_and_blank_lines_ignored():
    shots = parse_labels("# 註解\n\n1 全空\n")
    assert len(shots) == 1


def test_number_out_of_order_rejected():
    with pytest.raises(LabelError, match="編號 3"):
        parse_labels("1 全空\n3 A1人\n")


def test_unrecognized_token_rejected():
    with pytest.raises(LabelError, match="無法辨識"):
        parse_labels("1 A1人 (側坐)\n")


def test_duplicate_seat_rejected():
    with pytest.raises(LabelError, match="重複"):
        parse_labels("1 A1人 A1空\n")


def test_missing_seat_rejected_rather_than_treated_as_vacant():
    shot = parse_labels("1 A1人 A2空\n")[0]
    with pytest.raises(LabelError, match="A3"):
        resolve_truth(shot, ["A1", "A2", "A3"])


def test_all_vacant_resolves_every_seat():
    shot = parse_labels("1 全空\n")[0]
    truth = resolve_truth(shot, SEATS)
    assert {t.kind for t in truth.values()} == {KIND_VACANT}


def test_seats_sorted_by_row_then_number():
    assert sort_seats(["B10", "A2", "B2", "A10", "A1"]) == ["A1", "A2", "A10", "B2", "B10"]


# ---- 遮擋推定 ----

def test_seat_behind_a_seated_person_is_occluded():
    truth = {
        "A1": SeatTruth(KIND_PERSON), "A2": SeatTruth(KIND_BELONGINGS, "水壺"),
        "A3": SeatTruth(KIND_VACANT),
        "B1": SeatTruth(KIND_VACANT), "B2": SeatTruth(KIND_PERSON), "B3": SeatTruth(KIND_PERSON),
    }
    # 只有前方坐著人才算遮擋；前方擺物品或空著都不算，前排本身永不算
    assert occluded_seats(truth) == {"B1"}


# ---- 拍攝時間排序 ----

def test_order_by_exif_time():
    t = datetime(2026, 11, 6, 15, 0, 0)
    items = [("b.jpg", t.replace(second=2)), ("a.jpg", t.replace(second=5)), ("c.jpg", t)]
    assert order_by_capture(items) == (["c.jpg", "b.jpg", "a.jpg"], "exif")


def test_order_falls_back_to_filename_when_any_time_missing():
    items = [("b.jpg", datetime(2026, 1, 1)), ("a.jpg", None)]
    assert order_by_capture(items) == (["a.jpg", "b.jpg"], "filename")


def test_parse_exif_datetime():
    assert parse_exif_datetime("2026:11:06 15:04:05") == datetime(2026, 11, 6, 15, 4, 5)
    assert parse_exif_datetime("2026:11:06 15:04:05", "42").microsecond == 420000
    assert parse_exif_datetime("壞掉的值") is None
    assert parse_exif_datetime(None) is None


# ---- 統計 ----

def rec(shot, seat, mode, truth, pred, item=None, occluded=False, walkway=False):
    return Record(shot=shot, photo=f"{shot}.jpg", seat=seat, mode=mode, truth=truth,
                  pred=pred, item=item, detail="", occluded=occluded, walkway=walkway)


@pytest.fixture
def records():
    return [
        # 第 1 張：坐著的人——框中心溢出 ROI 而漏判，接地點判對
        rec(1, "A1", "ground", KIND_PERSON, KIND_PERSON),
        rec(1, "A1", "center", KIND_PERSON, KIND_VACANT),
        # 第 2 張：走道經過者——框中心誤判，接地點判對
        rec(2, "A2", "ground", KIND_VACANT, KIND_VACANT, walkway=True),
        rec(2, "A2", "center", KIND_VACANT, KIND_PERSON, walkway=True),
        # 第 3 張：被遮擋的後排兩種方法都判錯；水壺兩種方法都判對
        rec(3, "B1", "ground", KIND_PERSON, KIND_VACANT, occluded=True),
        rec(3, "B1", "center", KIND_PERSON, KIND_VACANT, occluded=True),
        rec(3, "A3", "ground", KIND_BELONGINGS, KIND_BELONGINGS, item="水壺"),
        rec(3, "A3", "center", KIND_BELONGINGS, KIND_BELONGINGS, item="水壺"),
    ]


def test_ground_mode_stats(records):
    st = compute_stats(records, "ground")
    assert (st.total, st.correct) == (4, 3)
    assert (st.occluded_total, st.occluded_correct) == (1, 0)
    assert (st.clear_total, st.clear_correct) == (3, 3)
    assert (st.person_tp, st.person_fn, st.person_fp) == (1, 1, 0)
    assert st.item_hits == {"水壺": [1, 1]}
    assert [e.seat for e in st.errors] == ["B1"]


def test_center_mode_counts_misses_and_walkway_false_positives(records):
    st = compute_stats(records, "center")
    assert st.correct == 1
    assert st.person_fn == 2          # A1 漏判 + B1 漏判
    assert st.person_fp == 1          # A2 走道誤判
    assert st.walkway_fp == 1
    assert st.confusion[(KIND_PERSON, KIND_VACANT)] == 2


def test_compare_modes(records):
    fixed, broken = compare_modes(records)
    assert sorted(new.seat for new, _ in fixed) == ["A1", "A2"]
    assert broken == []


def test_report_contains_key_sections(records):
    stats = {m: compute_stats(records, m) for m in ("ground", "center")}
    report = format_report(stats, records, {"照片": "3 張"})
    for section in ("整體準確率", "被遮擋座位", "物品佔位", "混淆矩陣", "方法差異：接地點 vs 框中心（舊）", "判錯清單"):
        assert section in report
    assert "75.0%（3/4）" in report   # 接地點整體準確率


# ---- 標定工具的座標換算 ----

def test_phone_photo_is_scaled_down_to_fit_screen():
    scale = display_scale(4032, 3024)
    assert 4032 * scale <= 1600 and 3024 * scale <= 900


def test_webcam_frame_is_not_enlarged():
    assert display_scale(640, 480) == 1.0


def test_click_maps_back_to_original_pixels():
    scale = display_scale(4032, 3024)
    clicked = to_display((2016, 1512), scale)       # 原圖中心點顯示的位置
    restored = to_original(clicked, scale)
    # 縮放後再換算回來，誤差不超過一個顯示像素對應的原圖距離
    assert abs(restored[0] - 2016) <= 1 / scale and abs(restored[1] - 1512) <= 1 / scale


def test_calibrate_json_output_merges_seats(tmp_path):
    from src.detection.calibrate import load_json_rois, save_json_roi

    out = tmp_path / "rois.json"
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    save_json_roi(str(out), "A1", square)
    save_json_roi(str(out), "A2", square)
    save_json_roi(str(out), "A1", [[1, 1], [2, 1], [2, 2], [1, 2]])  # 重框覆蓋
    data = load_json_rois(str(out))
    assert set(data) == {"A1", "A2"} and data["A1"][0] == [1, 1]


def test_box_roi_hull_covers_desk_top_and_legs():
    from src.detection.calibrate import box_bottom, box_roi

    # 斜視角：桌面遠端較窄，往右偏
    top = [[100, 100], [200, 100], [220, 160], [90, 160]]
    clicks = top + [[90, 260], [220, 260]]
    bottom = box_bottom(top, clicks[4], clicks[5])
    # 後腳落差依遠近寬度比例縮短（100/130），且不會超過前腳落點
    assert bottom[0][1] == round(100 + 100 * 100 / 130) and bottom[0][1] < 260
    hull = box_roi(clicks)
    xs, ys = [p[0] for p in hull], [p[1] for p in hull]
    assert (min(xs), max(xs), min(ys), max(ys)) == (90, 220, 100, 260)
    # 外輪廓不會包住桌面遠左角正下方以外的左上空白（四邊形會包住的三角形）
    import cv2, numpy as np
    assert cv2.pointPolygonTest(np.array(hull, dtype=np.int32), (92, 105), False) < 0


# ---- 分層判定（立體框選的重疊處理） ----

def _pip(poly, point):
    """射線法點在多邊形內，測試用（不依賴 OpenCV）。"""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _desk(x, top_y, floor_y, width=100, depth=40, leg=120):
    """正視簡化的立體框：桌面 depth 高、桌腳 leg 長，地板投影在桌面下方 leg 處。"""
    from src.detection.calibrate import box_record
    clicks = [[x, top_y], [x + width, top_y], [x + width, top_y + depth], [x, top_y + depth],
              [x, top_y + depth + leg], [x + width, top_y + depth + leg]]
    rec = box_record(clicks)
    assert rec["floor"][2][1] == floor_y
    return rec


@pytest.fixture
def overlapping_rows():
    # 斜視角下前排桌面在畫面上蓋住後排地板：A1 桌面 y 240~280 與 B1 地板投影 240~280 重疊
    return {
        "A1": _desk(0, 240, 400),          # 桌面 240~280、地板 360~400，外輪廓 240~400
        "B1": _desk(0, 120, 280),          # 桌面 120~160、地板 240~280，外輪廓 120~280
    }


def test_front_row_person_not_counted_for_back_row(overlapping_rows):
    from src.detection.detector import RAW_PRESENT, RAW_VACANT, assign_layered, classify_seat
    # A1 坐著的人：下半身被自己的桌子擋住，框底停在 A1 桌面（y=260），也落在 B1 外框的下段
    person = (0, 20, 100, 80, 260)
    assert classify_seat(overlapping_rows["B1"]["points"], [person], _pip) == RAW_PRESENT  # 逐席：B1 誤判
    res = assign_layered(overlapping_rows, [person], _pip)
    assert res == {"A1": RAW_PRESENT, "B1": RAW_VACANT}


def test_back_row_person_on_own_desk(overlapping_rows):
    from src.detection.detector import RAW_PRESENT, RAW_VACANT, assign_layered
    person = (0, 20, 20, 80, 150)  # 框底停在 B1 桌面
    assert assign_layered(overlapping_rows, [person], _pip) == {"A1": RAW_VACANT, "B1": RAW_PRESENT}


def test_item_on_front_desk_not_counted_for_back_row(overlapping_rows):
    from src.detection.detector import RAW_BELONGINGS, RAW_VACANT, assign_layered, classify_seat
    # A1 桌上的水壺：中心 y=260，在 A1 桌面內，也落在 B1 外輪廓（地板段）內
    bottle = (39, 40, 240, 60, 280)
    assert classify_seat(overlapping_rows["B1"]["points"], [bottle], _pip) == RAW_BELONGINGS  # 逐席：B1 誤判
    res = assign_layered(overlapping_rows, [bottle], _pip)
    assert res == {"A1": RAW_BELONGINGS, "B1": RAW_VACANT}


def test_layered_falls_back_to_outline_when_outside_priority_layer(overlapping_rows):
    from src.detection.detector import RAW_PRESENT, RAW_VACANT, assign_layered
    # A1 側坐、腳露在桌腳中段（y=320），不在任何桌面，但在 A1 外輪廓內
    person = (0, 10, 150, 90, 320)
    assert assign_layered(overlapping_rows, [person], _pip) == {"A1": RAW_PRESENT, "B1": RAW_VACANT}


def test_layered_accepts_plain_four_point_rois():
    from src.detection.detector import RAW_PRESENT, assign_layered
    square = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert assign_layered({"A1": square}, [(0, 10, 10, 90, 90)], _pip) == {"A1": RAW_PRESENT}
