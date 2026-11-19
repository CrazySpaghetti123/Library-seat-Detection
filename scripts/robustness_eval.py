"""判定規則的穩健性檢驗：只有一組照片時，用來確認準確率差距不是挑選規則造成的偏差。

三項檢驗（結果與解讀見 docs/evaluation_results.md）：
1. 分組驗證：照片隨機對半，一半從候選規則中挑最佳、另一半計分，重複多次
2. 照片重抽樣：以照片為單位 bootstrap，計算桌面優先與逐席接地點的準確率差距信賴區間
3. ROI 框選誤差：桌面與地板角點隨機位移後重算外輪廓，模擬重新框選

執行（照片集格式同 evaluate_photos.py，ROI 需為 --box 立體框選）：
    python scripts/robustness_eval.py --photos <照片資料夾> --model yolov8s.pt yolov8n.pt

YOLO 偵測每張只跑一次並快取在 eval_output/cache/（gitignored），之後所有規則與擾動都重用同一份偵測結果；
換照片集時請加 --no-cache 或刪除快取。
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
for s in (sys.stdout, sys.stderr):
    s.reconfigure(encoding="utf-8")

import evaluate_photos as ev  # noqa: E402
from src.detection.calibrate import convex_hull  # noqa: E402
from src.detection.detector import (  # noqa: E402
    BELONGING_CLASSES, PERSON_CLASS, RAW_BELONGINGS, RAW_PRESENT, RAW_VACANT,
    anchor_point, assign_layered, classify_seat,
)
from src.detection.evaluation import RAW_TO_KIND, parse_labels, resolve_truth, order_by_capture  # noqa: E402

CACHE = ROOT / "eval_output" / "cache"
PHOTOS: Path
BASE_ROIS: dict
SEATS: list
pip = ev.point_in_polygon


def cached_detections(model_name, use_cache=True):
    cache = CACHE / f"dets_{model_name}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text())
    from ultralytics import YOLO
    model = YOLO(str(ROOT / model_name))
    photos = ev.list_photos(PHOTOS)
    order, _ = order_by_capture([(p.name, ev.read_exif(p)["time"]) for p in photos])
    out = {name: ev.detect(model, ev.load_frame(PHOTOS / name), 0.35, None) for name in order}
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


# ---------------- 候選規則（與 2026-11-08 挑選時比較過的同一批） ----------------

def centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def seg_dist(p, a, b):
    (ax, ay), (bx, by), (px, py) = a, b, p
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def per_seat(anchor):
    return lambda rois, dets: {s: classify_seat(rois[s]["points"], dets, pip, anchor) for s in SEATS}


def exclusive(person_layer, person_pick="centroid"):
    def region(r, layer):
        return r["points"] if layer == "hull" else r[layer]

    def rule(rois, dets):
        person = {s: False for s in SEATS}
        items = {s: False for s in SEATS}
        for cls, x1, y1, x2, y2 in dets:
            if cls == PERSON_CLASS:
                layer, flags = person_layer, person
            elif cls in BELONGING_CLASSES:
                layer, flags = "top", items
            else:
                continue
            pt = anchor_point(cls, x1, y1, x2, y2, "ground")
            cand = [s for s in SEATS if pip(region(rois[s], layer), pt)]
            if not cand:
                cand = [s for s in SEATS if pip(rois[s]["points"], pt)]
            if not cand:
                continue
            if cls == PERSON_CLASS and person_pick == "far_edge":
                key = lambda s: seg_dist(pt, rois[s]["top"][0], rois[s]["top"][1])
            else:
                key = lambda s: math.dist(pt, centroid(region(rois[s], layer)))
            flags[min(cand, key=key)] = True
        return {s: RAW_PRESENT if person[s] else RAW_BELONGINGS if items[s] else RAW_VACANT
                for s in SEATS}
    return rule


DESK_FIRST = "桌面優先（實機程式 assign_layered）"
GROUND = "接地點 逐席"
RULES = {
    "框中心 逐席": per_seat("center"),
    GROUND: per_seat("ground"),
    "人→地板 物→桌面": exclusive("floor"),
    DESK_FIRST: lambda rois, dets: assign_layered(rois, dets, pip),
    "人→外框取最近桌面遠緣": exclusive("hull", "far_edge"),
    "人→桌面取最近遠緣": exclusive("top", "far_edge"),
}


def per_photo_correct(rois, dets_by_photo, shots, names, rule):
    """每張照片答對幾席（之後的重抽樣都以照片為單位）。"""
    out = []
    for shot in shots:
        truth = resolve_truth(shot, SEATS)
        pred = rule(rois, dets_by_photo[names[shot.index - 1]])
        out.append(sum(RAW_TO_KIND[pred[s]] == truth[s].kind for s in SEATS))
    return out


def jitter_rois(rng, k):
    """每個桌面角點與地板角點各自隨機位移 ±k px，外輪廓由兩者的凸包重算（模擬重新框選）。"""
    out = {}
    for s, r in BASE_ROIS.items():
        top = [[x + rng.uniform(-k, k), y + rng.uniform(-k, k)] for x, y in r["top"]]
        floor = [[x + rng.uniform(-k, k), y + rng.uniform(-k, k)] for x, y in r["floor"]]
        top = [[round(x), round(y)] for x, y in top]
        floor = [[round(x), round(y)] for x, y in floor]
        out[s] = {"points": convex_hull(top + floor), "top": top, "floor": floor}
    return out


def pct(x):
    return f"{x:.1%}"


def main(model, use_cache=True, seed=20261119):
    rng = random.Random(seed)
    shots = parse_labels((PHOTOS / "labels.txt").read_text(encoding="utf-8-sig"))
    dets = cached_detections(model, use_cache)
    names = list(dets)
    n_photo, per = len(shots), len(SEATS)
    table = {name: per_photo_correct(BASE_ROIS, dets, shots, names, r) for name, r in RULES.items()}

    print(f"\n## {model}（{n_photo} 張 × {per} 席）\n")
    print("### 全部照片\n")
    for name, c in sorted(table.items(), key=lambda kv: -sum(kv[1])):
        print(f"- {name}：{pct(sum(c) / (n_photo * per))}")

    # 1. 分組驗證：一半挑規則、另一半計分
    trials, chosen, test_sel, test_df, test_gr = 2000, {}, [], [], []
    idx = list(range(n_photo))
    for _ in range(trials):
        rng.shuffle(idx)
        train, test = idx[: n_photo // 2], idx[n_photo // 2:]
        best = max(RULES, key=lambda r: (sum(table[r][i] for i in train), r == DESK_FIRST))
        chosen[best] = chosen.get(best, 0) + 1
        score = lambda r: sum(table[r][i] for i in test) / (len(test) * per)
        test_sel.append(score(best)); test_df.append(score(DESK_FIRST)); test_gr.append(score(GROUND))
    print(f"\n### 分組驗證（隨機對半 {trials} 次：一半挑規則、另一半計分）\n")
    for name, k in sorted(chosen.items(), key=lambda kv: -kv[1]):
        print(f"- 被挑中：{name} {pct(k / trials)}")
    print(f"- 挑出的規則在另一半的平均準確率：{pct(sum(test_sel) / trials)}")
    print(f"- 對照：接地點逐席在另一半：{pct(sum(test_gr) / trials)}")
    wins = sum(s > g for s, g in zip(test_sel, test_gr)) / trials
    print(f"- 挑出的規則在另一半勝過接地點逐席的比例：{pct(wins)}")

    # 2. 照片重抽樣：桌面優先 − 接地點逐席 的差距
    diffs = []
    for _ in range(10000):
        sample = [rng.randrange(n_photo) for _ in range(n_photo)]
        d = sum(table[DESK_FIRST][i] - table[GROUND][i] for i in sample) / (n_photo * per)
        diffs.append(d)
    diffs.sort()
    lo, hi = diffs[249], diffs[9749]
    print("\n### 照片重抽樣 10000 次（桌面優先 − 接地點逐席）\n")
    print(f"- 差距 {pct(sum(table[DESK_FIRST]) / (n_photo * per) - sum(table[GROUND]) / (n_photo * per))}，"
          f"95% 信賴區間 {pct(lo)} ～ {pct(hi)}，差距 > 0 的比例 {pct(sum(d > 0 for d in diffs) / len(diffs))}")
    changed = [(shots[i].index, table[DESK_FIRST][i] - table[GROUND][i]) for i in range(n_photo)
               if table[DESK_FIRST][i] != table[GROUND][i]]
    print(f"- 兩者結果不同的照片 {len(changed)} 張：" + "、".join(f"第{i}張{d:+d}" for i, d in changed))

    # 3. ROI 框選誤差：桌面與地板角點隨機位移
    width = ev.load_frame(PHOTOS / names[0]).shape[1]
    print(f"\n### ROI 框選誤差（照片寬 {width}px，每種位移量 200 次）\n")
    print("| 角點位移 | 桌面優先 平均（最差） | 接地點逐席 平均（最差） | 桌面優先勝出比例 |")
    print("|---|---|---|---|")
    for frac in (0.005, 0.01, 0.02):
        k = width * frac
        df, gr, win = [], [], 0
        for _ in range(200):
            rois = jitter_rois(rng, k)
            a = sum(per_photo_correct(rois, dets, shots, names, RULES[DESK_FIRST])) / (n_photo * per)
            b = sum(per_photo_correct(rois, dets, shots, names, RULES[GROUND])) / (n_photo * per)
            df.append(a); gr.append(b); win += a > b
        print(f"| ±{k:.0f}px（{frac:.1%} 寬） | {pct(sum(df) / 200)}（{pct(min(df))}） | "
              f"{pct(sum(gr) / 200)}（{pct(min(gr))}） | {pct(win / 200)} |")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="判定規則穩健性檢驗（分組驗證／重抽樣／ROI 擾動）")
    parser.add_argument("--photos", required=True, help="照片資料夾（含 labels.txt）")
    parser.add_argument("--rois", help="立體框選 ROI 檔（預設：<照片資料夾>/rois.json）")
    parser.add_argument("--model", nargs="+", default=["yolov8s.pt"], help="YOLOv8 權重，可列多個")
    parser.add_argument("--no-cache", action="store_true", help="重新偵測，不用快取")
    parser.add_argument("--seed", type=int, default=20261119, help="亂數種子（固定可重現）")
    args = parser.parse_args()
    PHOTOS = Path(args.photos)
    BASE_ROIS = json.loads(Path(args.rois or PHOTOS / "rois.json").read_text(encoding="utf-8"))
    if not all(isinstance(v, dict) and v.get("top") for v in BASE_ROIS.values()):
        sys.exit("ROI 需為 calibrate.py --box 立體框選的格式（含 top／floor）")
    SEATS = sorted(BASE_ROIS)
    for m in args.model:
        main(m, not args.no_cache, args.seed)
