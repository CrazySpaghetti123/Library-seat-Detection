"""照片集離線評估的純邏輯：標註解析、遮擋推定、準確率統計與報告。

本模組不依賴 OpenCV / ultralytics，可直接單元測試；
影像讀取、YOLO 推論與檔案輸出由 scripts/evaluate_photos.py 負責。

標註檔格式（一張照片一行，順序須與拍攝順序一致）：

    1  全空
    2  A1人 A2水壺 A3空 B1空 B2背包 B3人
    11 A1空 A2空 A3水壺 B1空 B2背包 B3人 ｜走道A1前
    5  廢片

- 行首編號可省略；有寫時會檢查是否與順序一致
- 「人」開頭視為有人，可附姿勢（如「人(側坐)」「人+書」）；「空」為空位；其餘視為物品名稱
- 「｜」（或半形 |）之後為備註；備註含「走道」者視為走道情境
- 「#」開頭為註解，空行忽略
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from src.detection.detector import RAW_BELONGINGS, RAW_PRESENT, RAW_VACANT

KIND_PERSON = "person"
KIND_BELONGINGS = "belongings"
KIND_VACANT = "vacant"
KINDS = (KIND_PERSON, KIND_BELONGINGS, KIND_VACANT)

KIND_TO_RAW = {KIND_PERSON: RAW_PRESENT, KIND_BELONGINGS: RAW_BELONGINGS,
               KIND_VACANT: RAW_VACANT}
RAW_TO_KIND = {raw: kind for kind, raw in KIND_TO_RAW.items()}
KIND_LABEL = {KIND_PERSON: "人", KIND_BELONGINGS: "物品", KIND_VACANT: "空"}

MODE_LABEL = {"layered": "桌面優先", "ground": "接地點", "center": "框中心（舊）"}
MODE_ORDER = ("layered", "ground", "center")
# 報告中兩兩比較的組合：（較新方法, 對照方法）
MODE_PAIRS = (("ground", "center"), ("layered", "ground"), ("layered", "center"))

_SEAT_TOKEN = re.compile(r"^([A-Za-z]+)(\d+)(.+)$")
_SEAT_LABEL = re.compile(r"^([A-Z]+)(\d+)$")
_NOTE_SPLIT = re.compile(r"[｜|]")
_PAREN = re.compile(r"[（(].*?[）)]")


class LabelError(ValueError):
    """標註檔格式錯誤；訊息含行號，方便使用者直接修正。"""


@dataclass
class SeatTruth:
    kind: str
    item: str | None = None  # 物品名稱（僅物品佔位），已去除括號內的備註
    detail: str = ""         # 原始文字，如「人(側坐)」


@dataclass
class Shot:
    index: int                # 拍攝順序（1 起算）
    line_no: int              # 在標註檔中的行號
    skip: bool = False        # 廢片
    all_vacant: bool = False  # 全空
    seats: dict[str, SeatTruth] = field(default_factory=dict)
    note: str = ""

    @property
    def walkway(self) -> bool:
        return "走道" in self.note


def parse_value(value: str) -> SeatTruth:
    """將座位狀態文字轉為真實狀態。"""
    v = value.strip()
    if v.startswith("人"):
        return SeatTruth(KIND_PERSON, detail=v)
    if v == "空":
        return SeatTruth(KIND_VACANT, detail=v)
    item = _PAREN.sub("", v).strip() or v
    return SeatTruth(KIND_BELONGINGS, item=item, detail=v)


def parse_labels(text: str) -> list[Shot]:
    shots: list[Shot] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        parts = _NOTE_SPLIT.split(line, maxsplit=1)
        tokens = parts[0].split()
        note = parts[1].strip() if len(parts) > 1 else ""

        shot = Shot(index=len(shots) + 1, line_no=line_no, note=note)
        if tokens and tokens[0].isdigit():
            number = int(tokens.pop(0))
            if number != shot.index:
                raise LabelError(
                    f"第 {line_no} 行：編號 {number} 與順序不符（這是第 {shot.index} 張）")
        if not tokens:
            raise LabelError(f"第 {line_no} 行：沒有內容")

        if tokens == ["廢片"]:
            shot.skip = True
        elif tokens == ["全空"]:
            shot.all_vacant = True
        else:
            for tok in tokens:
                m = _SEAT_TOKEN.match(tok)
                if not m:
                    raise LabelError(
                        f"第 {line_no} 行：無法辨識「{tok}」，"
                        "格式應為「座位＋狀態」，例如 A1人、B2水壺、A3空")
                label = f"{m.group(1).upper()}{m.group(2)}"
                if label in shot.seats:
                    raise LabelError(f"第 {line_no} 行：座位 {label} 重複出現")
                shot.seats[label] = parse_value(m.group(3))
        shots.append(shot)
    return shots


def split_label(label: str) -> tuple[str, int]:
    m = _SEAT_LABEL.match(label)
    if not m:
        raise ValueError(f"座位編號格式不符：{label}")
    return m.group(1), int(m.group(2))


def sort_seats(labels) -> list[str]:
    return sorted(labels, key=split_label)


def resolve_truth(shot: Shot, seats: list[str]) -> dict[str, SeatTruth]:
    """取出受評估座位的真實狀態；缺漏座位直接報錯，避免把漏記誤當空位。"""
    if shot.all_vacant:
        return {s: SeatTruth(KIND_VACANT, detail="空") for s in seats}
    missing = [s for s in seats if s not in shot.seats]
    if missing:
        raise LabelError(
            f"第 {shot.line_no} 行（第 {shot.index} 張）缺少座位：{'、'.join(missing)}。"
            "每張照片的每個座位都要寫，空位請寫「空」")
    return {s: shot.seats[s] for s in seats}


def occluded_seats(truth: dict[str, SeatTruth]) -> set[str]:
    """推定被遮擋的座位：正前方座位（前一排、同一行）的真實狀態為有人。

    排別依字母順序由近而遠，A 排最靠近相機。
    """
    rows = sorted({split_label(s)[0] for s in truth})
    occluded = set()
    for label in truth:
        row, col = split_label(label)
        i = rows.index(row)
        if i == 0:
            continue
        front = f"{rows[i - 1]}{col}"
        if front in truth and truth[front].kind == KIND_PERSON:
            occluded.add(label)
    return occluded


def parse_exif_datetime(value: str | None, subsec: str | None = None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value).strip().rstrip("\x00"), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    sub = str(subsec).strip().rstrip("\x00") if subsec else ""
    if sub.isdigit():
        dt = dt.replace(microsecond=int(sub[:6].ljust(6, "0")))
    return dt


def order_by_capture(items: list[tuple[str, datetime | None]]) -> tuple[list[str], str]:
    """依拍攝時間排序；任一張缺少時間則整組改依檔名排序。回傳（順序, 方法）。"""
    if items and all(t is not None for _, t in items):
        return [n for n, _ in sorted(items, key=lambda x: (x[1], x[0]))], "exif"
    return sorted(n for n, _ in items), "filename"


# ---- 統計 ----

@dataclass
class Record:
    shot: int
    photo: str
    seat: str
    mode: str
    truth: str
    pred: str
    item: str | None
    detail: str
    occluded: bool
    walkway: bool

    @property
    def correct(self) -> bool:
        return self.truth == self.pred


@dataclass
class ModeStats:
    mode: str
    total: int = 0
    correct: int = 0
    clear_total: int = 0
    clear_correct: int = 0
    occluded_total: int = 0
    occluded_correct: int = 0
    person_tp: int = 0
    person_fp: int = 0   # 誤判：不是人卻判成有人
    person_fn: int = 0   # 漏判：有人卻沒判成有人
    walkway_fp: int = 0  # 走道情境中的誤判
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)
    item_hits: dict[str, list[int]] = field(default_factory=dict)  # 物品 -> [判對, 總數]
    errors: list[Record] = field(default_factory=list)


def compute_stats(records: list[Record], mode: str) -> ModeStats:
    st = ModeStats(mode=mode)
    for r in (r for r in records if r.mode == mode):
        st.total += 1
        st.correct += r.correct
        if r.occluded:
            st.occluded_total += 1
            st.occluded_correct += r.correct
        else:
            st.clear_total += 1
            st.clear_correct += r.correct
        key = (r.truth, r.pred)
        st.confusion[key] = st.confusion.get(key, 0) + 1

        truth_p, pred_p = r.truth == KIND_PERSON, r.pred == KIND_PERSON
        st.person_tp += truth_p and pred_p
        st.person_fn += truth_p and not pred_p
        if pred_p and not truth_p:
            st.person_fp += 1
            st.walkway_fp += r.walkway

        if r.truth == KIND_BELONGINGS:
            hit = st.item_hits.setdefault(r.item or "（未命名）", [0, 0])
            hit[0] += r.pred == KIND_BELONGINGS
            hit[1] += 1
        if not r.correct:
            st.errors.append(r)
    return st


def compare_modes(records: list[Record], new: str = "ground", old: str = "center"):
    """回傳（新方法改對的, 新方法反而判錯的），元素為（新紀錄, 舊紀錄）。"""
    old_by_key = {(r.shot, r.seat): r for r in records if r.mode == old}
    fixed, broken = [], []
    for r in (r for r in records if r.mode == new):
        o = old_by_key.get((r.shot, r.seat))
        if o is None or r.correct == o.correct:
            continue
        (fixed if r.correct else broken).append((r, o))
    return fixed, broken


def _pct(num: int, den: int) -> str:
    return f"{num / den:.1%}" if den else "—"


def _ratio(num: int, den: int) -> str:
    return f"{_pct(num, den)}（{num}/{den}）"


def _fmt_record(r: Record) -> str:
    tags = [t for t, on in (("遮擋", r.occluded), ("走道", r.walkway)) if on]
    suffix = f"（{'、'.join(tags)}）" if tags else ""
    truth = r.detail or KIND_LABEL[r.truth]
    return f"第 {r.shot} 張 {r.seat}：正確 {truth}，判成 {KIND_LABEL[r.pred]}{suffix}　`{r.photo}`"


def format_report(stats: dict[str, ModeStats], records: list[Record], meta: dict) -> str:
    modes = [m for m in MODE_ORDER if m in stats]
    head = " | ".join(MODE_LABEL[m] for m in modes)
    sep = " | ".join("---" for _ in modes)

    def row(name, fn):
        return f"| {name} | " + " | ".join(fn(stats[m]) for m in modes) + " |"

    out = ["# 座位判定評估報告", "", "## 資料", ""]
    out += [f"- {k}：{v}" for k, v in meta.items()]
    out += ["", "## 整體", "", f"| 指標 | {head} |", f"|---| {sep} |",
            row("整體準確率", lambda s: _ratio(s.correct, s.total)),
            row("無遮擋座位", lambda s: _ratio(s.clear_correct, s.clear_total)),
            row("被遮擋座位", lambda s: _ratio(s.occluded_correct, s.occluded_total)),
            row("漏判（有人判成非人）", lambda s: str(s.person_fn)),
            row("誤判（非人判成有人）", lambda s: str(s.person_fp)),
            row("　其中走道情境", lambda s: str(s.walkway_fp)),
            row("「有人」精確率", lambda s: _pct(s.person_tp, s.person_tp + s.person_fp)),
            row("「有人」召回率", lambda s: _pct(s.person_tp, s.person_tp + s.person_fn)),
            "",
            "- 被遮擋：正前方座位（前一排同一行）有人坐著，由標註自動推定",
            "- 精確率：判成「有人」的座位中真的有人的比例；召回率：真的有人的座位中被判出來的比例",
            ""]

    items = sorted({i for s in stats.values() for i in s.item_hits})
    if items:
        out += ["## 物品佔位（各物品被判成「物品佔位」的比例）", "",
                f"| 物品 | {head} |", f"|---| {sep} |"]
        for it in items:
            out.append(row(it, lambda s, it=it: (
                _ratio(*s.item_hits[it]) if it in s.item_hits else "—")))
        out.append("")

    for m in modes:
        s = stats[m]
        out += [f"## 混淆矩陣：{MODE_LABEL[m]}", "",
                "| 正確 ＼ 判定 | 人 | 物品 | 空 |", "|---|---|---|---|"]
        for t in KINDS:
            out.append(f"| {KIND_LABEL[t]} | " + " | ".join(
                str(s.confusion.get((t, p), 0)) for p in KINDS) + " |")
        out.append("")

    for new, base in MODE_PAIRS:
        if new not in stats or base not in stats:
            continue
        fixed, broken = compare_modes(records, new, base)
        x, y = MODE_LABEL[new], MODE_LABEL[base]
        out += [f"## 方法差異：{x} vs {y}", "",
                f"{x}改對、{y}判錯：{len(fixed)} 個；{x}判錯、{y}判對：{len(broken)} 個", ""]
        for title, pairs in ((f"{x}改對的", fixed), (f"{x}反而判錯的", broken)):
            if pairs:
                out += [f"### {title}", ""]
                out += [f"- {_fmt_record(n)}（{y}判成 {KIND_LABEL[o.pred]}）" for n, o in pairs]
                out.append("")

    for m in modes:
        errs = stats[m].errors
        out += [f"## 判錯清單：{MODE_LABEL[m]}（{len(errs)} 個）", ""]
        out += [f"- {_fmt_record(r)}" for r in errs] or ["- 無"]
        out.append("")
    return "\n".join(out)
