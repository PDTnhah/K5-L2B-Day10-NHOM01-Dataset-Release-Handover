#!/usr/bin/env python3
"""Pha 2 — đối chiếu detection (YOLO) <-> panoptic (mask) và sinh ứng viên lỗi gán nhãn.

    python validator/crosscheck.py runs/r1007/delivery --out runs/r1007/candidates.json
    python validator/crosscheck.py runs/clean/delivery --out runs/clean/candidates.json   # đo nhiễu tự nhiên

Dùng trong validate.py (Pha 1):

    from crosscheck import find_candidates, write_candidates
    if args.candidates:
        write_candidates(find_candidates(Path(args.delivery)), Path(args.candidates))

Chỉ dùng thư viện chuẩn + scripts/pngutil.py. Chỉ đọc thư mục delivery được truyền vào.

Ý tưởng (GUIDE Pha 2):
  * Đổi box YOLO sang pixel; ghép lớp hai nguồn qua TÊN (classes.txt <-> categories).
  * Mỗi segment thing được nén thành các "run" theo hàng, để đếm nhanh số pixel của segment
    nằm trong một hình chữ nhật bất kỳ.
  * Với một cặp ghép đúng, gần như MỌI pixel của segment nằm trong box (cov ~ 1.0), vì panoptic
    COCO sinh từ cùng polygon với box (vật bị che chỉ làm segment nhỏ lại, không tràn ra ngoài).
      - cov thấp            -> box lệch khỏi vật        (bbox_drift)
      - một segment phủ hai box cùng lớp, mỗi box một phần riêng -> bị gộp (instance_merge)
      - cặp trùng vị trí nhưng khác lớp                         -> class_swap / category_swap
      - segment thing lớn không có box nào phủ                  -> missing_box
  * Ảnh đã dính lỗi luật ảnh hưởng tới đối chiếu (thing_overlap, invalid_category_id,
    invalid_class, duplicate_box, bbox_out_of_bounds) được bỏ qua vì mỗi ảnh mang nhiều nhất
    một lỗi (docs/DELIVERY.md); lỗi luật đã do validator luật bắt.

Mọi ngưỡng nằm trong DEFAULTS và chỉnh được bằng --set key=value. Chọn ngưỡng bằng lô sạch
(runs/clean), không bằng _private.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402

SEMANTIC = ["class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"]

DEFAULTS = {
    "margin_px": 2,          # nới box thêm vài pixel khi đếm (làm tròn toạ độ YOLO 6 chữ số)
    "match_iou": 0.5,        # ghép cặp box<->segment theo IoU(box, bbox của mask), không xét lớp
    "same_class_bonus": 0.15,  # cộng vào IoU khi xếp hạng cặp cùng lớp
    "swap_iou": 0.6,         # cặp khác lớp thành ứng viên swap khi trùng vị trí đủ chặt ...
    "swap_fill": 0.4,        # ... hoặc segment nằm gọn trong box và lấp >= tỉ lệ này của box
    "drift_cov": 0.92,       # cặp cùng lớp: tỉ lệ pixel segment nằm trong box dưới mức này -> drift
    "drift_min_out_px": 40,  # ... và số pixel rơi ra ngoài box phải đủ nhiều (bỏ nhiễu viền)
    "drift_min_box": 0.003,  # bỏ box quá nhỏ (tỉ lệ diện tích ảnh): khó nhìn, nhiễu cao
    "missing_min_seg": 0.004,  # segment thing không có box: chỉ báo khi >= tỉ lệ này của ảnh
    "missing_cov": 0.6,      # segment được một box cùng lớp phủ >= mức này thì coi như đã có box
    "merge_excl": 0.2,       # instance_merge: phần pixel segment CHỈ nằm trong box thứ hai / diện tích box đó
    "merge_max_cov": 0.97,   # segment nằm gọn trong một box (cov cao hơn) thì không phải gộp
    "max_per_type": 0,       # 0 = không giới hạn; >0 = chỉ giữ N ứng viên điểm cao nhất mỗi loại
}


# --------------------------------------------------------------------------- đọc delivery
def read_classes(path: Path) -> dict[int, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            idx, name = line.split(maxsplit=1)
            out[int(idx)] = name.strip()
    return out


def read_boxes(path: Path, classes: dict[int, str], width: int, height: int) -> tuple[list[dict], list[str]]:
    """Trả về (box hợp lệ ở pixel, danh sách cờ luật thấy được trong file nhãn)."""
    boxes, flags = [], []
    if not path.is_file():
        return boxes, ["no_label_file"]
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        parts = line.split()
        if not parts:
            continue
        try:
            cid = int(parts[0])
            x, y, w, h = map(float, parts[1:5])
        except (ValueError, IndexError):
            flags.append("bad_row")
            continue
        if cid not in classes:
            flags.append("invalid_class")
            continue
        x0, y0, x1, y1 = (x - w / 2) * width, (y - h / 2) * height, (x + w / 2) * width, (y + h / 2) * height
        if x0 < -1 or y0 < -1 or x1 > width + 1 or y1 > height + 1:
            flags.append("bbox_out_of_bounds")
        boxes.append({
            "idx": line_no, "cls": classes[cid],
            "x0": max(0.0, x0), "y0": max(0.0, y0), "x1": min(float(width), x1), "y1": min(float(height), y1),
        })
    # box lặp (lỗi luật duplicate_box): cùng lớp, cùng cỡ, tâm lệch <= 3 px
    for a, b in itertools.combinations(boxes, 2):
        if a["cls"] == b["cls"] and abs((a["x1"] - a["x0"]) - (b["x1"] - b["x0"])) < 1.5 \
                and abs((a["y1"] - a["y0"]) - (b["y1"] - b["y0"])) < 1.5 \
                and abs(a["x0"] - b["x0"]) <= 3 and abs(a["y0"] - b["y0"]) <= 3:
            flags.append("duplicate_box")
            break
    return boxes, flags


def mask_runs(path: Path) -> tuple[int, int, dict[int, list[tuple[int, int, int]]]]:
    """Đọc mask, trả về {segment_id: [(y, x_start, x_end_exclusive), ...]}."""
    width, height, pixels = pngutil.read_rgb(path)
    stride = width * 3
    runs: dict[int, list[tuple[int, int, int]]] = {}
    for y in range(height):
        row = pixels[y * stride:(y + 1) * stride]
        ids = [r + g * 256 + b * 65536 for r, g, b in zip(row[0::3], row[1::3], row[2::3])]
        x = 0
        for sid, grp in itertools.groupby(ids):
            n = sum(1 for _ in grp)
            if sid:
                runs.setdefault(sid, []).append((y, x, x + n))
            x += n
    return width, height, runs


# --------------------------------------------------------------------------- hình học
def rect_px(box: dict, margin: float, width: int, height: int) -> tuple[int, int, int, int]:
    """Hình chữ nhật pixel [x0, x1) x [y0, y1) của box, nới thêm margin."""
    return (max(0, int(box["x0"] - margin + 0.5)), max(0, int(box["y0"] - margin + 0.5)),
            min(width, int(box["x1"] + margin + 0.5)), min(height, int(box["y1"] + margin + 0.5)))


def count_in(seg: dict, rect: tuple[int, int, int, int]) -> int:
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0 or seg["bx1"] < x0 or seg["bx0"] >= x1 or seg["by1"] < y0 or seg["by0"] >= y1:
        return 0
    total = 0
    for y, a, b in seg["runs"]:
        if y0 <= y < y1:
            lo, hi = max(a, x0), min(b, x1)
            if hi > lo:
                total += hi - lo
    return total


def intersect(r1, r2):
    return (max(r1[0], r2[0]), max(r1[1], r2[1]), min(r1[2], r2[2]), min(r1[3], r2[3]))


def iou_box_seg(box: dict, seg: dict) -> float:
    sx0, sy0, sx1, sy1 = seg["bx0"], seg["by0"], seg["bx1"] + 1, seg["by1"] + 1
    ix = max(0.0, min(box["x1"], sx1) - max(box["x0"], sx0))
    iy = max(0.0, min(box["y1"], sy1) - max(box["y0"], sy0))
    inter = ix * iy
    area_b = (box["x1"] - box["x0"]) * (box["y1"] - box["y0"])
    area_s = (sx1 - sx0) * (sy1 - sy0)
    return inter / (area_b + area_s - inter + 1e-9)


def box_area(box: dict) -> float:
    return max(0.0, box["x1"] - box["x0"]) * max(0.0, box["y1"] - box["y0"])


def box_json(box: dict) -> dict:
    return {"line": box["idx"], "class": box["cls"],
            "xyxy": [round(box["x0"], 1), round(box["y0"], 1), round(box["x1"], 1), round(box["y1"], 1)]}


def seg_json(seg: dict) -> dict:
    return {"id": seg["id"], "class": seg["cls"], "pixels": seg["px"],
            "xyxy": [seg["bx0"], seg["by0"], seg["bx1"] + 1, seg["by1"] + 1]}


# --------------------------------------------------------------------------- một ảnh
def analyse_image(stem: str, width: int, height: int, boxes: list[dict], segs: list[dict],
                  crowd: list[dict], p: dict, log: list | None = None) -> list[dict]:
    img_area = float(width * height)
    m = p["margin_px"]
    rects = [rect_px(b, m, width, height) for b in boxes]
    # inside[i][j] = số pixel của segment j nằm trong box i (đã nới margin)
    inside = [[count_in(s, r) for s in segs] for r in rects]
    findings: list[dict] = []

    # ---- 1) instance_merge: một segment, hai box cùng lớp, mỗi box giữ một phần riêng
    merged_segs, merge_boxes = set(), set()
    for j, s in enumerate(segs):
        same = [i for i, b in enumerate(boxes) if b["cls"] == s["cls"] and inside[i][j] > 0]
        if len(same) < 2:
            continue
        best_cov = max(inside[i][j] for i in same) / s["px"]
        if best_cov >= p["merge_max_cov"]:
            continue
        best = None
        for i1, i2 in itertools.permutations(same, 2):
            both = count_in(s, intersect(rects[i1], rects[i2]))
            excl2 = inside[i2][j] - both                     # pixel chỉ nằm trong box thứ hai
            union_cov = (inside[i1][j] + inside[i2][j] - both) / s["px"]
            # box thứ hai không có segment cùng lớp riêng của nó
            own = any(k != j and segs[k]["cls"] == boxes[i2]["cls"] and iou_box_seg(boxes[i2], segs[k]) >= p["match_iou"]
                      for k in range(len(segs)))
            ratio = excl2 / max(1.0, box_area(boxes[i2]))
            if not own and ratio >= p["merge_excl"] and union_cov >= 0.85:
                if best is None or ratio > best[0]:
                    best = (ratio, i1, i2, union_cov)
        if best:
            ratio, i1, i2, union_cov = best
            merged_segs.add(j)
            merge_boxes.update((i1, i2))
            findings.append({"type": "instance_merge", "score": round(ratio, 3),
                             "why": f"segment {s['cls']} phủ 2 box cùng lớp; {ratio:.0%} box thứ hai chỉ có pixel của segment này",
                             "boxes": [box_json(boxes[i1]), box_json(boxes[i2])], "segments": [seg_json(s)],
                             "cov_best": round(best_cov, 3), "cov_union": round(union_cov, 3)})

    # ---- 2) ghép cặp theo IoU (>= match_iou), một-một, tham lam. Cặp cùng lớp được cộng
    #         same_class_bonus để vật bị che (bbox mask nhỏ hơn box) không bị box lớp khác cướp.
    pairs = []
    for i, b in enumerate(boxes):
        for j, s in enumerate(segs):
            if i in merge_boxes or j in merged_segs:
                continue
            iou = iou_box_seg(b, s)
            if iou >= p["match_iou"]:
                pairs.append((iou + (p["same_class_bonus"] if b["cls"] == s["cls"] else 0.0), i, j))
    pairs.sort(reverse=True)
    match_b, match_s = {}, {}
    for _, i, j in pairs:
        if i in match_b or j in match_s:
            continue
        match_b[i], match_s[j] = j, i
    # vòng 2: box còn lại <-> segment còn lại theo số pixel chung.
    #   cùng lớp: chỉ cần chung >= 20% (bắt drift lớn);
    #   khác lớp: segment phải nằm gọn trong box và lấp phần lớn box (vật bị che nặng + đổi lớp).
    pairs2 = []
    for i, b in enumerate(boxes):
        for j, s in enumerate(segs):
            if i in match_b or j in match_s or i in merge_boxes or j in merged_segs or inside[i][j] == 0:
                continue
            cov, fill = inside[i][j] / s["px"], inside[i][j] / max(1.0, box_area(b))
            if b["cls"] == s["cls"] and (cov >= 0.2 or fill >= 0.2):
                pairs2.append((1, inside[i][j], i, j))
            elif b["cls"] != s["cls"] and cov >= 0.9 and fill >= p["swap_fill"]:
                pairs2.append((0, inside[i][j], i, j))
    for _, _, i, j in sorted(pairs2, reverse=True):
        if i in match_b or j in match_s:
            continue
        match_b[i], match_s[j] = j, i

    # ---- 3) xét từng cặp
    for i, j in match_b.items():
        b, s = boxes[i], segs[j]
        iou = iou_box_seg(b, s)
        cov = inside[i][j] / s["px"]
        if b["cls"] != s["cls"]:
            fill = inside[i][j] / max(1.0, box_area(b))
            if iou >= p["swap_iou"] or (cov >= 0.9 and fill >= p["swap_fill"]):
                findings.append({"type": "class_swap|category_swap", "score": round(iou, 3),
                                 "why": f"cùng vị trí (IoU {iou:.2f}) nhưng detection ghi '{b['cls']}', panoptic ghi '{s['cls']}'",
                                 "boxes": [box_json(b)], "segments": [seg_json(s)], "cov": round(cov, 3)})
            continue
        out_px = s["px"] - inside[i][j]
        if log is not None:
            log.append({"image": stem, "kind": "pair", "box_class": b["cls"], "seg_class": s["cls"],
                        "iou": round(iou, 4), "cov": round(cov, 4), "out_px": out_px,
                        "box_frac": round(box_area(b) / img_area, 5), "seg_frac": round(s["px"] / img_area, 5)})
        if box_area(b) / img_area >= p["drift_min_box"] and cov < p["drift_cov"] and out_px >= p["drift_min_out_px"]:
            findings.append({"type": "bbox_drift", "score": round(1 - cov, 3),
                             "why": f"{1 - cov:.0%} pixel segment {s['cls']} ({out_px} px) nằm ngoài box; IoU {iou:.2f}",
                             "boxes": [box_json(b)], "segments": [seg_json(s)], "cov": round(cov, 3), "iou": round(iou, 3)})

    # ---- 4) segment thing lớn không có box
    for j, s in enumerate(segs):
        if j in match_s or j in merged_segs:
            continue
        frac = s["px"] / img_area
        if frac < p["missing_min_seg"]:
            continue
        cover = max([inside[i][j] / s["px"] for i, b in enumerate(boxes) if b["cls"] == s["cls"]], default=0.0)
        if log is not None:
            log.append({"image": stem, "kind": "unmatched_seg", "box_class": "", "seg_class": s["cls"], "iou": "",
                        "cov": round(cover, 4), "out_px": "", "box_frac": "", "seg_frac": round(frac, 5)})
        if cover >= p["missing_cov"]:
            continue  # đã có box cùng lớp phủ (ví dụ box gộp nhiều vật sẵn trong COCO)
        findings.append({"type": "missing_box", "score": round(frac, 4),
                         "why": f"segment {s['cls']} {s['px']} px ({frac:.1%} ảnh) không có box nào; box cùng lớp phủ tốt nhất {cover:.0%}",
                         "boxes": [], "segments": [seg_json(s)]})

    # ---- 5) box không ghép được (ghi lại làm thông tin, không tự thành ứng viên)
    for i, b in enumerate(boxes):
        if i in match_b or i in merge_boxes:
            continue
        in_crowd = any(count_in(c, rects[i]) > 0.3 * box_area(b) for c in crowd)
        if not in_crowd and box_area(b) / img_area >= p["drift_min_box"]:
            findings.append({"type": "unmatched_box", "score": round(box_area(b) / img_area, 4),
                             "why": f"box {b['cls']} không ghép được segment nào (có thể drift rất xa, hoặc lệch tự nhiên)",
                             "boxes": [box_json(b)], "segments": []})
    return findings


# --------------------------------------------------------------------------- cả lô
def find_candidates(delivery: Path, params: dict | None = None, progress: bool = False,
                    log: list | None = None) -> dict:
    p = dict(DEFAULTS)
    p.update(params or {})
    classes = read_classes(delivery / "classes.txt")
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan["categories"]}
    anns = {a["image_id"]: a for a in pan["annotations"]}
    candidates, skipped, stats = [], [], {"images": 0, "pairs_checked": 0}
    images = sorted(pan["images"], key=lambda im: Path(im["file_name"]).stem)
    for n, im in enumerate(images):
        stem = Path(im["file_name"]).stem
        width, height = im["width"], im["height"]
        ann = anns.get(im["id"])
        if ann is None:
            skipped.append({"image": stem, "why": "không có annotation panoptic"})
            continue
        boxes, flags = read_boxes(delivery / "labels" / f"{stem}.txt", classes, width, height)
        mpath = delivery / "masks" / Path(ann["file_name"]).name
        if not mpath.is_file():
            skipped.append({"image": stem, "why": "thiếu mask"})
            continue
        mw, mh, runs = mask_runs(mpath)
        if (mw, mh) != (width, height):
            flags.append("mask_size")
        segs, crowd = [], []
        for info in ann["segments_info"]:
            cat = cats.get(info["category_id"])
            r = runs.get(info["id"], [])
            if cat is None:
                flags.append("invalid_category_id")
                continue
            px = sum(b - a for _, a, b in r)
            if info.get("area", px) > px + 1:
                flags.append("thing_overlap")
            if not cat.get("isthing") or px == 0:
                continue
            seg = {"id": info["id"], "cls": cat["name"], "px": px, "runs": r,
                   "bx0": min(a for _, a, _ in r), "bx1": max(b for _, _, b in r) - 1,
                   "by0": r[0][0], "by1": r[-1][0]}
            (crowd if info.get("iscrowd") else segs).append(seg)
        stats["images"] += 1
        if flags:
            skipped.append({"image": stem, "why": "lỗi luật: " + ",".join(sorted(set(flags)))})
            continue
        stats["pairs_checked"] += len(boxes) * len(segs)
        found = analyse_image(stem, width, height, boxes, segs, crowd, p, log)
        real = [f for f in found if f["type"] != "unmatched_box"]
        if real:
            real.sort(key=lambda f: -f["score"])
            candidates.append({"image": stem, "type": real[0]["type"], "score": real[0]["score"],
                               "width": width, "height": height,
                               "signals": real + [f for f in found if f["type"] == "unmatched_box"]})
        if progress and (n + 1) % 25 == 0:
            print(f"  {n + 1}/{len(images)} ảnh", file=sys.stderr)
    if p["max_per_type"]:
        kept = []
        for t in sorted({c["type"] for c in candidates}):
            kept += sorted([c for c in candidates if c["type"] == t], key=lambda c: -c["score"])[: p["max_per_type"]]
        candidates = kept
    candidates.sort(key=lambda c: (c["type"], -c["score"]))
    by_type = {}
    for c in candidates:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    stats.update({"candidates": len(candidates), "by_type": by_type, "skipped_rule_images": len(skipped)})
    return {"delivery": str(delivery), "params": p, "stats": stats, "candidates": candidates, "skipped": skipped}


def write_candidates(result: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def parse_set(items: list[str]) -> dict:
    out = {}
    for item in items:
        key, _, val = item.partition("=")
        if key not in DEFAULTS:
            raise SystemExit(f"không có tham số {key}; có: {', '.join(DEFAULTS)}")
        out[key] = type(DEFAULTS[key])(float(val)) if isinstance(DEFAULTS[key], int) else float(val)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Pha 2: ghép detection <-> panoptic, sinh candidates.json")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True, help="candidates.json")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VAL", help="đổi ngưỡng, ví dụ --set drift_cov=0.9")
    ap.add_argument("--dump-pairs", metavar="CSV", help="ghi số đo mọi cặp đã ghép + segment không có box (để chọn ngưỡng trên lô sạch)")
    args = ap.parse_args()
    log: list | None = [] if args.dump_pairs else None
    result = find_candidates(Path(args.delivery), parse_set(args.set), progress=True, log=log)
    write_candidates(result, Path(args.out))
    if log is not None:
        import csv
        with open(args.dump_pairs, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["image", "kind", "box_class", "seg_class", "iou", "cov", "out_px", "box_frac", "seg_frac"])
            w.writeheader()
            w.writerows(log)
        pairs = sorted(r["cov"] for r in log if r["kind"] == "pair" and r["box_class"] == r["seg_class"])
        if pairs:
            q = lambda f: pairs[min(len(pairs) - 1, int(f * len(pairs)))]
            print(f"cov cặp cùng lớp (n={len(pairs)}): min {pairs[0]:.3f}  p1 {q(0.01):.3f}  p5 {q(0.05):.3f}  median {q(0.5):.3f}")
        print(f"số đo -> {args.dump_pairs}")
    s = result["stats"]
    print(f"{s['images']} ảnh, {s['skipped_rule_images']} ảnh bỏ qua vì lỗi luật, {s['candidates']} ứng viên -> {args.out}")
    for t, k in sorted(s["by_type"].items()):
        print(f"  {t:28s} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
