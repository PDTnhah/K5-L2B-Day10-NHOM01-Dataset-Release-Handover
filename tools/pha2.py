#!/usr/bin/env python3
"""Chạy Pha 2 theo đúng 5 bước của GUIDE.

  python tools/pha2.py prep   --seed 1007 [--reviewers "Thai,Thanh,Thuy,Son,Duc"] [--set drift_cov=0.9 ...]
      bước 2-3-4 (chuẩn bị): lô sạch -> đo nhiễu; lô luyện tập -> candidates.json; vẽ trang review.
      Ghi runs/r<seed>/pha2_summary.json (số liệu thật để chép vào REPORT.md).

  python tools/pha2.py finish --seed 1007
      bước 5: kiểm review_log.csv (mỗi ứng viên có kết luận, ghi chú >= 20 ký tự, không trùng),
      gộp rules.json + dòng confirmed -> errors.json, rồi chạy score_findings.py.

Không đọc _private. Không tự điền kết luận review.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SEMANTIC = {"class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"}


def run(*args: str) -> None:
    print("$", " ".join(args))
    subprocess.run([PY, *args], cwd=ROOT, check=True)


def check_files() -> None:
    need = ["validator/crosscheck.py", "tools/review_viewer.py", "scripts/pngutil.py", "scripts/inject_release.py"]
    missing = [f for f in need if not (ROOT / f).is_file()]
    if missing:
        raise SystemExit("Thiếu file trong repo: " + ", ".join(missing) +
                         f"\nChép chúng vào đúng chỗ dưới {ROOT} (giải nén pha2.zip ở gốc repo).")
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("Thiếu Pillow cho công cụ xem ảnh: python -m pip install pillow")


def prep(a) -> int:
    check_files()
    run_dir, clean = ROOT / "runs" / f"r{a.seed}", ROOT / "runs" / "clean"
    if not (run_dir / "delivery").is_dir():
        raise SystemExit(f"chưa có {run_dir}/delivery: chạy python scripts/run_lab.py --seeds {a.seed}")
    sets = [x for s in a.set for x in ("--set", s)]
    if not (clean / "delivery").is_dir():
        run("scripts/inject_release.py", "--seed", "5", "--no-faults", "--out", "runs/clean")
    # bước 3: nhiễu tự nhiên, CÙNG ngưỡng với lô luyện tập
    run("validator/crosscheck.py", "runs/clean/delivery", "--out", "runs/clean/candidates.json",
        "--dump-pairs", "runs/clean/pairs.csv", *sets)
    # bước 2: ứng viên lô luyện tập
    run("validator/crosscheck.py", f"runs/r{a.seed}/delivery", "--out", f"runs/r{a.seed}/candidates.json", *sets)
    # bước 4 (chuẩn bị): ảnh + trang review
    run("tools/review_viewer.py", f"runs/r{a.seed}/delivery", f"runs/r{a.seed}/candidates.json",
        "--out", f"runs/r{a.seed}/review", "--reviewers", a.reviewers)
    c = json.loads((clean / "candidates.json").read_text(encoding="utf-8"))
    r = json.loads((run_dir / "candidates.json").read_text(encoding="utf-8"))
    summary = {"seed": a.seed, "params": r["params"],
               "clean": {"images": c["stats"]["images"], "candidates": c["stats"]["candidates"], "by_type": c["stats"]["by_type"]},
               "practice": {"images": r["stats"]["images"], "candidates": r["stats"]["candidates"],
                            "by_type": r["stats"]["by_type"], "skipped_rule_images": r["stats"]["skipped_rule_images"]}}
    (run_dir / "pha2_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nLô sạch: {summary['clean']['candidates']} ứng viên / {summary['clean']['images']} ảnh")
    print(f"Lô r{a.seed}: hàng đợi {summary['practice']['candidates']} ảnh {summary['practice']['by_type']}")
    print(f"Mở runs/r{a.seed}/review/index.html, xem ảnh, xuất review_log.csv vào runs/r{a.seed}/")
    return 0


def finish(a) -> int:
    run_dir = ROOT / "runs" / f"r{a.seed}"
    rules, review = run_dir / "rules.json", run_dir / "review_log.csv"
    for f, hint in ((rules, "validator luật (Pha 1) phải ghi lỗi luật ra rules.json"),
                    (review, "xuất review_log.csv từ trang review")):
        if not f.is_file():
            raise SystemExit(f"thiếu {f}: {hint}")
    cands = {c["image"] for c in json.loads((run_dir / "candidates.json").read_text(encoding="utf-8"))["candidates"]}
    with review.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    problems, notes = [], {}
    for row in rows:
        img, typ, ver, note = (row.get(k, "").strip() for k in ("image", "type", "verdict", "note"))
        if ver not in ("confirmed", "rejected"):
            problems.append(f"{img}: verdict '{ver}'")
        if ver == "confirmed" and typ not in SEMANTIC:
            problems.append(f"{img}: type '{typ}' không phải lỗi gán nhãn")
        if len(note) < 20:
            problems.append(f"{img}: ghi chú < 20 ký tự")
        notes.setdefault(note, []).append(img)
    problems += [f"ghi chú trùng: {v}" for k, v in notes.items() if k and len(v) > 1]
    reviewed = {r["image"].strip() for r in rows}
    todo = sorted(cands - reviewed)
    if todo:
        problems.append(f"{len(todo)} ứng viên chưa có dòng review: {todo[:5]}")
    conf = sorted(r["image"].strip() for r in rows if r.get("verdict", "").strip() == "confirmed")
    if len(conf) != len(set(conf)):
        problems.append("một ảnh có nhiều dòng confirmed (mỗi ảnh nhiều nhất một lỗi)")
    if problems:
        print("Cần sửa review_log.csv:\n  " + "\n  ".join(problems))
        if not a.force:
            return 1
    run("scripts/merge_review.py", "--rules", str(rules.relative_to(ROOT)), "--review", str(review.relative_to(ROOT)),
        "--out", f"runs/r{a.seed}/errors.json")
    run("scripts/score_findings.py", "--run", f"runs/r{a.seed}")
    n_conf, n_rej = len(conf), sum(1 for r in rows if r.get("verdict", "").strip() == "rejected")
    print(f"\nReview: {len(rows)} dòng, {n_conf} confirmed, {n_rej} rejected")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Pha 2: chuẩn bị review / chốt errors.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--reviewers", default="Thai,Thanh,Thuy,Son,Duc")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VAL")
    f = sub.add_parser("finish")
    f.add_argument("--seed", type=int, required=True)
    f.add_argument("--force", action="store_true", help="vẫn gộp dù review_log còn vấn đề")
    a = ap.parse_args()
    return prep(a) if a.cmd == "prep" else finish(a)


if __name__ == "__main__":
    raise SystemExit(main())
