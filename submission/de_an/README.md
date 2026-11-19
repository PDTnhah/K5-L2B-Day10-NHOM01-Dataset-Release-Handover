# Đề ẩn — hướng dẫn cho nhóm

Lô: `delivery/` (250 ảnh, tên `img_0001`…`img_0250`), `release_id lab250_62d7641abb98`.

## Trạng thái hiện tại (đã chạy sẵn)

| Việc | Trạng thái |
|---|---|
| Chạy validator | ✅ `errors.json` — **12 lỗi luật** (tự động, không cần xem ảnh) |
| Sinh ứng viên | ✅ `candidates.json` — **24 ứng viên trên 22 ảnh** |
| `trace.json` (Pha 5) | ✅ tier_a 3 ảnh, tier_b 3 ảnh, notify 4 người |
| `review_log.csv` | ⬜ **còn phải làm** — nhóm xem ảnh rồi điền |
| `errors.json` cuối | ⬜ sau khi có `review_log.csv` (chạy `merge_review.py`) |

## Cách xem ảnh nhanh nhất

Trong `_vis/` có **22 ảnh đã ghi chú sẵn** cho từng ảnh ứng viên:

- **Khung vàng/đỏ** = box detection (từ `labels/`)
- **Khung xanh** = bbox segment panoptic (từ `panoptic.json`)
- Chữ ở góc khung = tên lớp; chữ **xanh dưới khung xanh** = lớp của segment panoptic

Mở file `submission/de_an/_vis/<tên ảnh>_vis.png`. Nếu cần ảnh gốc: `delivery/images/<tên ảnh>.jpg`.

## Việc còn lại

### 1. Xem 22 ảnh, điền `review_log.csv`

Mỗi ứng viên trong `candidates.json` → một dòng trong `review_log.csv`:

```text
image,type,verdict,note
img_0006,class_swap,confirmed,"mở ảnh: xe bu 2 bánh màu xanh, detection ghi bus đúng, panoptic ghi truck sai"
img_0036,class_swap,confirmed,"mở ảnh: một chiếc giường, detection ghi bed đúng, panoptic ghi couch sai"
```

Quy tắc:
- `verdict` = `confirmed` (lỗi thật) hoặc `rejected` (nhiễu tự nhiên của COCO).
- `type` phải là một trong: `class_swap`, `bbox_drift`, `missing_box`, `category_swap`, `instance_merge`.
  - Nếu **detection** ghi sai lớp → `class_swap`
  - Nếu **panoptic** ghi sai lớp → `category_swap`
- `note` ≥ 20 ký tự, **nói rõ thấy gì trong ảnh**, mỗi dòng khác nhau (không chép mẫu).
- Ghi rõ **ai xem** (tên trong `TEAM.md`).

> Theo `RULES.md`: mọi dòng `confirmed`/`rejected` phải là kết luận của người trong nhóm, ghi rõ ai xem. AI không được thay việc xem ảnh.

### 2. Gộp lại thành `errors.json` cuối

```powershell
python scripts/merge_review.py --rules submission/de_an/errors.json --review submission/de_an/review_log.csv --out submission/de_an/errors.json
```

Lệnh này giữ nguyên 12 lỗi luật và thêm các lỗi gán nhãn đã `confirmed`.

### 3. Commit và push

```powershell
git add submission/de_an
git commit -m "P6b: de an - loi luat + gan nhan da xac nhan"
git push origin main
```

**Không** commit thư mục `delivery/` của đề ẩn (đã có trong `.gitignore`).

## Ghi chú về `trace.json`

Đã dựng theo `incoming/ticket.md` (team AI báo `truck` bị che ở `scene_100`, `scene_777`) và
`guideline/changelog.md` (v1.3 đổi quy tắc lớp `truck`):

| Khoá | Nội dung |
|---|---|
| `tier_a` | 3 ảnh: `img_0146`, `img_0157`, `img_0240` |
| `tier_b` | 3 ảnh: `img_0019`, `img_0084`, `img_0169` |
| `notify` | `A01`, `A02`, `Q01`, `Q03` |

Tiêu chí lấy guideline **theo job** trong `jobs.csv`, không theo `metadata.json` của từng ảnh —
`img_0019` là ví dụ (metadata ghi `v1.3`, job `J01` ghi `v1.2`; và ảnh này đã bị báo
`guideline_mismatch`).
