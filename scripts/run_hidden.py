#!/usr/bin/env python3
"""Chuẩn bị đề ẩn: giải nén + chạy validator + dựng hàng đợi xem ảnh.

  python scripts/run_hidden.py delivery

Chạy từ thư mục gốc repo. Lô đề ẩn nằm ở thư mục `delivery/` (tên ảnh img_0001).
Script KHÔNG tự kết luận lỗi gán nhãn — nó chỉ:
  1. chạy validator ra errors.json (lỗi luật) + candidates.json (ứng viên)
  2. in danh sách ảnh cần xem, kèm đường dẫn file để mở nhanh
  3. tạo review_log.csv rỗng với đúng header để nhóm điền
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Chuẩn bị đề ẩn")
    ap.add_argument("delivery", nargs="?", default="delivery", help="thư mục delivery của đề ẩn")
    ap.add_argument("--outdir", default="submission/de_an", help="nơi ghi bài nộp đề ẩn")
    args = ap.parse_args()

    delivery = ROOT / args.delivery
    if not delivery.is_dir():
        print(f"KHÔNG thấy thư mục delivery: {delivery}")
        print("Giải nén de_an.zip vào thư mục gốc repo trước đã.")
        return 1

    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    print("== 1. Chạy validator ==")
    cmd = [sys.executable, str(ROOT / "validator" / "validate.py"), str(delivery),
           "--out", str(outdir / "errors.json"),
           "--candidates", str(outdir / "candidates.json")]
    subprocess.run(cmd, cwd=ROOT, check=True)

    errors = json.loads((outdir / "errors.json").read_text(encoding="utf-8"))["errors"]
    cands = json.loads((outdir / "candidates.json").read_text(encoding="utf-8"))["candidates"]

    print()
    print("== 2. Kết quả ==")
    print(f"Lỗi luật: {len(errors)}")
    for e in errors:
        print(f"   {e['type']:<22} {e['target']}")
    print(f"Ứng viên cần xem ảnh: {len(cands)}")

    log = outdir / "review_log.csv"
    if not log.is_file():
        with log.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["image", "type", "verdict", "note"])
        print(f"\nĐã tạo {log} (header sẵn) để nhóm điền.")

    print()
    print("== 3. Hàng đợi xem ảnh ==")
    print("Mở ảnh: file nằm ở", delivery / "images")
    for c in cands:
        img = delivery / "images" / (c["target"] + ".jpg")
        print(f"\n  {c['target']}  [{c['type']}]")
        print(f"     file : {img}")
        print(f"     lý do: {c['reason']}")

    print()
    print("Tiếp theo:")
    print(f"  1. Xem từng ảnh trên, điền {log} (verdict=confirmed/rejected, note ghi rõ thấy gì)")
    print(f"  2. python scripts/merge_review.py --rules {outdir}/errors.json "
          f"--review {log} --out {outdir}/errors.json")
    print(f"  3. Làm {outdir}/trace.json (xem templates/trace.json)")
    print("  4. git add submission/de_an && git commit && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
