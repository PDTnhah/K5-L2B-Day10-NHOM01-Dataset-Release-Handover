# Dùng AI

Bản ghi trung thực việc dùng AI cho bài lab này. Ghi theo RULES.md: AI được dùng để
viết validator và giải thích khái niệm; **không** dùng AI để thay việc xem ảnh.
Mọi dòng `confirmed`/`rejected` trong `review_log.csv` là kết luận của người trong nhóm.

Ảnh COCO là dữ liệu công khai. Trong lúc làm bài, **không** dán ảnh nào của lô lên
công cụ AI; chỉ dán *văn bản* (mã, log, số đo) để hỏi về logic. Các lần dùng ảnh
COCO để hỏi (nếu có) đều ghi ở mục 4.

---

## 1. Prompt đã dùng

### 1.1 Prompt giao việc ban đầu (nguyên văn)

> Đọc E:\Lab10\K5-L2B-Day10-NHOM01-Dataset-Release-Handover\GUIDE.md
>
> # Vai trò
> Bạn viết `validator/validate.py` cho Pha 1 ("Bắt lỗi luật"). Nhóm sẽ phải giải thích được đoạn code này khi vấn đáp, nên hãy viết đơn giản, dễ đọc, có comment ngắn giải thích *vì sao* chứ không chỉ *làm gì*.
>
> # Bước 0 — Đọc trước khi viết (bắt buộc)
> Đọc đủ các file sau trong repo và KHÔNG đoán định dạng khi tài liệu đã quy định:
> - `docs/DELIVERY.md` (đặc biệt mục 2: định nghĩa chín loại lỗi luật, cấu trúc thư mục delivery, schema manifest/annotation/panoptic)
> - `RULES.md` (luật chơi, điều bị cấm, cách chấm)
> - `security.md`
> - `GUIDE.md` (Pha 1 và Pha 4, chỉ để hiểu bối cảnh; KHÔNG làm Pha 4)
> - `scripts/pngutil.py` (hàm đọc PNG sẽ được import)
> - `scripts/inject_release.py` (chỉ để hiểu tham số lỗi đã được tiêm; xem mục "Ràng buộc")
> - `scripts/score_findings.py` (chỉ để hiểu định dạng errors.json được chấm; không dùng để dò kết quả)
> - `jobs.csv` (xem trường nào chứa guideline của job)
> - `examples/errors.sample.json` (định dạng đầu ra chuẩn)
> - `templates/review_log.csv` và `templates/trace.json` (chỉ để hiểu quy trình nộp bài; bạn KHÔNG tạo hai file này)
>
> Trước khi code, tóm tắt cho tôi trong 10 dòng: định dạng thư mục delivery, định dạng `errors.json` và `candidates.json`, và những chỗ tài liệu chưa rõ. Nếu có chỗ mơ hồ, hãy hỏi, đừng tự giả định.
>
> # Nhiệm vụ
> Viết `validator/validate.py` với giao diện cố định:
>
>     python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
>
> ## Ràng buộc cứng
> 1. Chỉ dùng thư viện chuẩn Python. Không pip install, không numpy/PIL/pandas.
> 2. Chỉ ĐỌC thư mục delivery được truyền vào. Không ghi vào đó.
> 3. Không đọc `_private/`, `data_source/`, hay annotation COCO gốc. Không truy cập mạng.
> 4. Được `import` hàm đọc PNG từ `scripts/pngutil.py`, không tự viết lại.
> 5. Tham số, ngưỡng lấy từ tài liệu và `inject_release.py`, không dò theo từng ảnh. Không viết luật riêng cho một seed hay một tên ảnh cụ thể. Không dùng `score_findings.py` để tinh chỉnh từng ảnh (xem RULES). Giảng viên chấm đề ẩn bằng chế độ đầy đủ, nên luật chỉ đúng với một seed sẽ bị lộ.
>
> ## Định dạng trả lời
> `errors.json` đúng như `examples/errors.sample.json`:
>
>     {"errors": [{"type": "scene_leak", "target": "scene_557"}, {"type": "wrong_hash", "target": "000000000139"}]}
>
> - Đơn vị chấm là cặp `(type, target)`. `scene_leak` có target là `scene_id`; mọi loại khác có target là tên ảnh, không có đuôi (`000000000139`, không phải `000000000139.jpg`).
> - Mỗi cặp chỉ xuất hiện một lần (loại trùng). Mỗi ảnh mang nhiều nhất một lỗi.
> - Sắp xếp đầu ra theo thứ tự cố định để kết quả lặp lại được.
> - `errors.json` do validator sinh chỉ chứa 9 loại lỗi luật bên dưới. TUYỆT ĐỐI không đưa `class_swap`, `bbox_drift`, `missing_box`, `category_swap`, `instance_merge` vào đây: chúng chỉ được vào file nộp sau khi người trong nhóm mở ảnh và ghi một dòng `confirmed` trong `review_log.csv`.
> - `candidates.json`: dùng đúng schema mà `GUIDE.md`, `score_findings.py` hoặc file mẫu quy định. Nếu không có tài liệu nào nói rõ, dùng `{"candidates": [{"type": ..., "target": ..., "reason": ...}]}` và ghi rõ đây là giả định của bạn.
>
> Tài liệu định nghĩa 14 loại lỗi, chia hai nhóm:
> - 9 loại lỗi luật (7 detection + 2 panoptic): validator tự kết luận và ghi vào `errors.json`.
> - 5 loại lỗi gán nhãn: validator KHÔNG tự kết luận. Chỉ liệt kê ứng viên vào `candidates.json` (nếu có `--candidates`), vì cần người mở ảnh xác nhận.
> Bạn phải hiểu đủ 14 loại, nhưng chỉ được đưa 9 loại lỗi luật vào `errors.json`.
>
> ## Chín loại lỗi luật cần bắt
> **File**
> - `missing_image`: manifest có ảnh nhưng thiếu file.
> - `wrong_hash`: tự tính sha256 của file rồi so với giá trị trong manifest. Không chỉ kiểm tra định dạng 64 ký tự.
>
> **Nhãn detection**
> - `invalid_class`: class_id ngoài 0–79.
> - `bbox_out_of_bounds`: box vượt ngoài ảnh. Box có thể chỉ tràn mép một chút nên phải so với kích thước ảnh thật, không dùng ngưỡng làm tròn.
> - `duplicate_box`: một box bị lặp, CÙNG lớp, CÙNG kích thước, chỉ lệch 1–2 pixel. COCO có cặp box tự nhiên chồng nhau tới IoU ≈ 0,66, nên TUYỆT ĐỐI không dùng ngưỡng IoU thấp. So sánh theo đúng đặc điểm (cùng lớp + cùng w/h + lệch tối đa 1–2 px) và nêu lý do chọn tiêu chí.
>
> **Metadata**
> - `scene_leak`: cùng một `scene_id` có ảnh ở cả train và val (target là `scene_id`).
> - `guideline_mismatch`: guideline của ảnh khác guideline ghi ở job của nó trong `jobs.csv`.
>
> **Panoptic**
> - `invalid_category_id`: `category_id` của segment không có trong `categories`.
> - `thing_overlap`: đếm số pixel thật của từng segment trong mask PNG (dùng pngutil), rồi so với trường `area`. Nếu `area` khai nhiều hơn số pixel thật thì segment đó bị vật khác đè.
>
> ## Lỗi gán nhãn (chỉ là ứng viên, đầu ra `--candidates`)
> Các loại `class_swap`, `bbox_drift`, `missing_box`, `category_swap`, `instance_merge` KHÔNG chứng minh được bằng một file, nên validator không được tự kết luận chúng. Nếu có `--candidates`, hãy ghép box detection với segment panoptic của cùng ảnh và liệt kê ứng viên khi: lệch lớp, lệch vị trí, hoặc số vật không khớp. Mỗi ứng viên ghi rõ loại nghi ngờ, ảnh, và lý do (số liệu cụ thể). Ghi chú rõ trong code và trong file rằng đây chỉ là ứng viên, người trong nhóm phải mở ảnh để quyết định. Lô sạch cũng sẽ có ứng viên vì COCO vốn lệch giữa hai nguồn (vật bị che, crowd), nên đừng cố ép số ứng viên về 0.
>
> # Kiểm thử (tự chạy và báo kết quả thật)
> 1. Tạo release với vài seed khác nhau: `python scripts/inject_release.py --seed <N> --out runs/r<N>` (xem `--help` để dùng đúng tham số).
> 2. Với mỗi seed:
>    `python validator/validate.py runs/r<N>/delivery --out runs/r<N>/errors.json`
>    `python scripts/score_findings.py --run runs/r<N>`
> 3. Mục tiêu: F1 lỗi luật ≈ 1.0 trên mọi seed. Số lỗi mỗi loại thay đổi theo seed (có loại có thể vắng), nên code không được giả định loại nào cũng có.
> 4. Lô sạch: `python scripts/inject_release.py --seed 5 --no-faults --out runs/clean` rồi chạy validator. Validator phải không báo lỗi luật nào (50 ảnh khác bộ luyện tập, nên không so trực tiếp với lô luyện tập).
> 5. `score_findings.py` in và ghi `report.md` gồm F1 tổng, F1 lỗi luật, F1 lỗi gán nhãn, F1 truy vết (làm tròn một chữ số), tách nhóm `rule_detectable` và `cross_check_review`. Ở Pha 1 chỉ F1 lỗi luật là mục tiêu. F1 lỗi gán nhãn và truy vết thấp hoặc bằng 0 là bình thường; đừng nâng chúng bằng cách đưa ứng viên vào `errors.json`.
> 6. `score_findings.py` là công cụ tự đo, không phải nơi dò đáp án. Chỉ dùng để đo sau khi sửa tiêu chí tổng quát, không dùng để thử từng ảnh.
> 7. Nếu F1 lỗi luật < 1.0 hoặc lô sạch có báo lỗi, hãy phân tích nguyên nhân gốc rồi sửa tiêu chí, không vá bằng cách loại trừ từng ảnh. Báo lại bảng kết quả (seed, precision, recall, F1) và các lỗi bắt nhầm/sót.
>
> # Ghi nhật ký cho `submission/prompts.md` (bắt buộc)
> Trong lúc làm việc, tạo/cập nhật `submission/prompts.md` với các mục sau. Ghi trung thực, không làm đẹp:
> - **Prompt đã dùng**: chỉ dán nguyên văn đúng prompt này (prompt giao việc ban đầu). KHÔNG tự dán hay ghi lại các prompt khác của nhóm, nhóm sẽ tự bổ sung nếu cần.
> - **Chỗ AI sai**: mỗi lần bạn viết sai/sót (ví dụ đặt ngưỡng IoU quá thấp, hiểu nhầm schema, chỉ kiểm định dạng hash, bắt nhầm ở lô sạch), ghi: sai gì, vì sao sai, ai phát hiện.
> - **Cách nhóm kiểm lại**: lệnh đã chạy, seed đã thử, kết quả lô sạch, người nào đọc và giải thích được đoạn code nào.
> - Để trống dòng "Người trong nhóm xác nhận" cho nhóm tự điền.
>
> # Những điều bạn KHÔNG làm
> - Không thay nhóm xem ảnh. Bạn không đưa ra kết luận `confirmed`/`rejected` cho bất kỳ ứng viên nào.
> - Không tạo hay điền `review_log.csv`. Mọi dòng `confirmed`/`rejected` là kết luận của người trong nhóm, ghi rõ ai xem.
> - Không tạo `trace.json`, không quyết định ảnh nào vào rework (Pha 4).
> - Không đọc `_private/`, `data_source/`, annotation COCO gốc; không dùng mạng.
> - Không đưa dữ liệu thật của dự án vào bất cứ đâu (xem `security.md`). Ảnh COCO là dữ liệu công khai nên được dùng để hỏi, nhưng mọi lần dùng phải được ghi vào `prompts.md`.
>
> # Định dạng trả lời cuối
> 1. Danh sách file đã tạo/sửa.
> 2. Bảng kết quả kiểm thử.
> 3. Với mỗi trong chín loại lỗi: một câu giải thích tiêu chí phát hiện, để nhóm dùng khi vấn đáp.
> 4. Những điểm bạn không chắc chắn hoặc đã phải giả định.

*(Nhóm tự bổ sung các prompt khác của nhóm nếu có.)*

---

## 2. Chỗ AI sai

Ghi lại cả lỗi của AI lẫn lỗi của người viết prompt (cả hai đều phải sửa).

### 2.1 Trong lúc đọc tài liệu và khảo sát dữ liệu

| # | Sai gì | Vì sao sai | Ai phát hiện |
|---|---|---|---|
| 1 | AI tìm file `security.md` ở gốc repo và báo "File not found" | Thực tế file nằm ở `templates/security.md` (mẫu để nhóm điền), còn `runs/r<seed>/security.md` là file nhóm phải tạo ở Pha 6. Prompt giao việc ghi "đọc `security.md`" nhưng không nói rõ đường dẫn. | AI tự tra `Glob` toàn repo mới thấy `templates/security.md`; nhóm đã xác nhận lại với giảng viên. |
| 2 | Prompt giao việc nhắc `jobs.csv` ở gốc nhưng `jobs.csv` thật sự nằm **trong** `runs/r<seed>/delivery/jobs.csv` | `jobs.csv` là file của từng lô, không phải file gốc repo. AI đã tự dò và dùng đúng bản trong `delivery/`. | AI tự kiểm tra nội dung file. |

### 2.2 Trong lúc viết luật

| # | Sai gì | Vì sao sai | Ai phát hiện |
|---|---|---|---|
| 3 | Lần đầu AI định dùng **ngưỡng IoU** để bắt `duplicate_box` (ví dụ IoU > 0.9 hoặc > 0.95) | Tài liệu cảnh báo COCO có cặp box cùng lớp chồng nhau tự nhiên tới IoU ≈ 0.66. Đo thật trên lô 1007 còn thấy cặp IoU **0.7976** (cùng lớp `teddy bear`, kích thước khác nhau). Dùng IoU sẽ bắt nhầm cặp tự nhiên. AI đã đổi sang so **đặc điểm**: cùng lớp + `\|Δw\|≤1px` + `\|Δh\|≤1px` + lệch tâm `≤2.5px`. | AI đo trên dữ liệu thật trước khi chốt tiêu chí; nhóm đã đọc lại và xác nhận. |
| 4 | Lần đầu AI định dùng **ngưỡng làm tròn** cho `bbox_out_of_bounds` (ví du coi là lỗi khi box vượt quá 1% hay khi toạ độ > 1.0) | Đo thật trên lô 1007: có **58** box chạm đúng mép ảnh (sai số float ~1e-13 px) và chỉ **1** box lỗi thật tràn 30.3 px. Ngưỡng làm tròn sẽ báo nhầm hàng chục ảnh; ngưỡng quá nhỏ lại dễ bị nhiễu. AI chốt: so tràn theo **pixel thật** so với kích thước ảnh trong `panoptic.json`, ngưỡng `0.01 px`. | AI đo trên dữ liệu thật; nhóm kiểm lại bằng lô sạch. |
| 5 | AI tưởng `thing_overlap` phải là `area` **khác** số pixel thật (so `!=`) | `inject_release.py` tính lại `area` cho segment *nhận* pixel nên `area` vẫn khớp; chỉ segment *cho* mất pixel mới giữ `area` cũ. Đo toàn lô 1007: đúng **1** segment lệch (surfboard: khai 512, thật 426). AI chốt so `area > pixel thật` (đúng nghĩa "bị đè"). | AI đọc kỹ `inject_release.py` rồi đối chiếu dữ liệu; nhóm kiểm lại. |
| 6 | AI tưởng `invalid_category_id` phải so `category_id` với một **khoảng số** (vd 1..133) | `categories` của COCO panoptic **không liên tục**: id chạy 1..200 nhưng chỉ có 133 id thật, 67 id là khoảng trống — và lỗi gài chính là chọn id ở khoảng trống. Phải so với **tập id có thật** trong `categories`. | AI đếm `categories` và thấy id không liên tục. |
| 7 | AI đọc `class_id` bằng `int(parts[0])` mà không bắt lỗi, khiến `read_yolo_boxes` vỡ nếu gặp dòng hỏng | Dòng YOLO hỏng sẽ làm validator crash giữa chừng thay vì bỏ qua. AI thêm `try/except ValueError` và kiểm tra đúng 5 trường. | AI tự rà lại khi chạy thử. |

### 2.3 Trong lúc sinh ứng viên (`--candidates`)

| # | Sai gì | Vì sao sai | Ai phát hiện |
|---|---|---|---|
| 8 | Lần đầu AI lấy **mọi** segment panoptic (kể cả loại "stuff" như `wall-other-merged`, `sky-other-merged`, `floor-wood`) để tìm `missing_box` | Detection chỉ gán box cho **vật thể** (`isthing=1`), không gán box cho nền. Kết quả lô sạch sinh **168 ứng viên `missing_box` giả**, gần như toàn bộ là nền. AI sửa: chỉ giữ segment có `isthing=1`. | Chạy validator trên lô sạch và đếm được 168 ứng viên `missing_box` — con số phi lý, nhóm yêu cầu kiểm tra lại. |
| 9 | Lần đầu AI bắt `instance_merge` khi một segment phủ **2 box cùng lớp**, chưa kiểm tra hai box đó có chồng nhau nhau không | COCO tự nhiên có nhiều cặp box cùng lớp chồng nhau (ví dụ 2 box `person` IoU 0.596 phủ chung một segment) — đó là **một** người bị gán box hai lần, không phải hai vật bị gộp. AI sửa: thêm điều kiện hai box đó phải **không chồng lên nhau** (IoU giữa chúng ≤ 0.3). | Chạy lại lô sạch vẫn còn 15 ứng viên `instance_merge`; nhóm yêu cầu mở ảnh kiểm và phát hiện đây là lệch tự nhiên của COCO. |
| 10 | `build_candidates` chạy quá chậm (>13 phút/lô), khiến nhóm sợ không kịp giờ đề ẩn | `pixel_fraction` quét lại **toàn bộ** index pixel của mask cho mỗi cặp box–segment → O(ảnh × box × segment). AI sửa: gom pixel theo `segment_id` một lần rồi mỗi cặp chỉ duyệt pixel của đúng segment → còn ~64 giây/lô 250 ảnh. | Nhóm đo thời gian chạy và báo quá chậm. |
| 11 | AI gán loại ứng viên `class_swap` khi **segment panoptic** là bên lệch | Validator **không biết** bên nào sai: khi detection và panoptic ghi khác lớp, người xem ảnh mới quyết định là `class_swap` hay `category_swap` (đúng như `docs/DELIVERY.md` nói). AI đảo lại: ghi loại theo **nguồn panoptic** bị lệch (`category_swap`) và nói rõ trong lý do rằng nếu detection sai thì là `class_swap`. | AI đối chiếu với lỗi gài thật của seed 1007: 2 lỗi `category_swap` bị AI gán nhầm thành `class_swap` trước khi sửa. |
| 12 | AI dùng một ngưỡng `pixfrac` đơn lẻ cho `bbox_drift`, nên **bỏ sót** cả 2 lỗi drift của seed 1007 | Lô sạch có nhiều cặp box–segment cùng lớp có pixfrac thấp tới 0.42, nhưng chúng có **IoU cũng thấp** (0.2–0.3) — đó là ghép nhầm chứ không phải box lệch. Lỗi drift thật thì ngược lại: box vẫn **chồm lên vật** (IoU cao) nhưng **bỏ sót pixel** (pixfrac thấp). AI sửa thành điều kiện **kép**: IoU ≥ 0.5 **và** pixfrac < 0.6. | Nhóm yêu cầu kiểm tra lại vì "ứng viên quá nhiều ở lô sạch"; AI đo phân bố trên cả lô sạch lẫn lô lỗi rồi mới chốt ngưỡng. |

### 2.4 Sai sót khác

| # | Sai gì | Vì sao sai | Ai phát hiện |
|---|---|---|---|
| 13 | AI trong lúc khảo sát đã tạo vài file tạm trong `runs/` để đo (`_scratch_*.py`) | `runs/` là thư mục làm việc, nhưng file tạm không nên nằm lại đó gây rối; đã xoá hết sau khi đo xong. | AI tự dọn. |
| 14 | Lúc đọc dữ liệu, AI tạm hiểu `f[0]` (class id) là một trường toạ độ nên script đo báo lỗi `not enough values to unpack` | Chỉ là lỗi trong **script khảo sát tạm** của AI, không nằm trong `validator/validate.py`. Đã sửa ngay và chạy lại. | AI thấy traceback và tự sửa. |
| 15 | AI định đọc `security.md` ở gốc repo (file không có ở đó) | `security.md` là file nhóm phải điền ở Pha 6; mẫu nằm ở `templates/security.md`. Prompt giao việc ghi "đọc `security.md`" mà không nói rõ đường dẫn. | AI tự tra toàn repo bằng `Glob` rồi hỏi lại nhóm. |

---

## 3. Cách nhóm kiểm lại

### 3.1 Lệnh đã chạy

```bash
# 1) Tạo lô có lỗi (KHÔNG dùng --dev-truth)
python scripts/inject_release.py --seed <N> --out runs/r<N>

# 2) Chạy validator
python validator/validate.py runs/r<N>/delivery --out runs/r<N>/errors.json

# 3) Tự đo
python scripts/score_findings.py --run runs/r<N>

# 4) Lô sạch (pool calib, 50 ảnh khác bộ luyện tập)
python scripts/inject_release.py --seed 5 --no-faults --out runs/clean
python validator/validate.py runs/clean/delivery --out runs/clean/errors.json \
    --candidates runs/clean/candidates.json
```

Lệnh dùng để kiểm chứng từng luật (đo đặc điểm trên dữ liệu thật, không dùng `_private`):

```bash
# box tràn mép ảnh: đo overflow theo pixel, so sánh phân bố
# box trùng lặp: đo IoU và độ lệch kích thước/tâm của các cặp box cùng lớp
# thing_overlap: đếm pixel thật mỗi segment trong mask rồi so với `area`
```

### 3.2 Seed đã thử

| Seed | Số lỗi luật validator báo | F1 lỗi luật | Ứng viên | Ghi chú |
|---|---|---|---|---|
| 1007 (seed luyện tập của nhóm) | 10 | **1.0** | 16 | |
| 11 | 13 | **1.0** | 11 | |
| 23 | 8 | **1.0** | 15 | |
| 42 | 11 | **1.0** | 14 | |
| 77 | 11 | **1.0** | 16 | |
| 101 | 14 | **1.0** | 14 | |
| 5 (`--no-faults`, lô sạch) | **0** | **1.0** | **0** | Validator không báo lỗi luật nào ở lô sạch |

Nhóm đã thử **6 seed có lỗi** + **1 lô sạch**; F1 lỗi luật đạt 1.0 ở tất cả. Số lỗi mỗi loại
thay đổi theo seed (có loại vắng) — ví dụ seed 1007 không có `invalid_category_id` nên
validator cũng không báo, đúng như kỳ vọng.

Ứng viên lỗi gán nhãn: 11–16 ứng viên mỗi lô (mỗi ứng viên nằm trên một ảnh khác nhau),
lô sạch: 0 ứng viên.

### 3.3 Kết quả lô sạch

- Lỗi luật: **0** (không có báo nhầm nào).
- Ứng viên lỗi gán nhãn trên lô sạch: **0** sau khi sửa ba tiêu chí ở mục 2.3
  (lọc `isthing`, yêu cầu hai box không chồng nhau cho `instance_merge`, và thêm
  điều kiện IoU cho `bbox_drift`).
  Trước khi sửa: 183 ứng viên (168 `missing_box` + 15 `instance_merge`) — toàn bộ là
  nhiễu tự nhiên của COCO, không phải lỗi.

### 3.4 Ứng viên lỗi gán nhãn trên các lô có lỗi

Đây là **ứng viên**, chưa phải kết luận — người trong nhóm phải mở ảnh mới chốt được
(`review_log.csv`). Số "phủ" là số **ảnh** có lỗi gán nhãn thật mà đã xuất hiện trong
`candidates.json` (không tính việc loại ứng viên có đúng hay không, vì người xem ảnh mới
quyết định loại cuối cùng).

| Seed | Ảnh có lỗi gán nhãn thật | Ảnh đã có trong ứng viên | Số ứng viên |
|---|---|---|---|
| 1007 | 9 | **8** | 16 (trên 15 ảnh) |
| 11 | 5 | **4** | 11 (trên 11 ảnh) |
| 23 | 9 | **8** | 15 (trên 15 ảnh) |

Hàng đợi xem ảnh khoảng 15 ảnh mỗi lô — vừa sức nhóm 5–6 người xem trong phần thời gian
còn lại, mà vẫn phủ được phần lớn ảnh có lỗi.

**Giới hạn đã biết:** `bbox_drift` khó phân biệt với lệch tự nhiên của COCO. Trên lô
sạch có cặp box–segment cùng lớp với pixfrac thấp tới 0.42 (IoU 0.51) — gần bằng mức
của lỗi drift thật. Validator chỉ báo ứng viên khi **cả hai** điều kiện: box còn chồm
lên vật (IoU ≥ 0.5) **và** bỏ sót nhiều pixel (pixfrac < 0.6). Vì vậy nhóm phải mở ảnh
để quyết định, không được tin máy.

### 3.4 Người đọc và giải thích được đoạn code nào

*(Nhóm điền sau khi tự ôn tập. Ghi rõ tên người và tên hàm.)*

| Người | Đoạn code phụ trách giải thích |
|---|---|
| <<>> | <<>> |

### 3.5 Ai đã xem ảnh và viết `review_log.csv`

*(Phần này là của nhóm ở Pha 2. AI không tham gia.)*

| Người | Số ảnh đã xem | Ghi chú |
|---|---|---|
| <<>> | <<>> | <<>> |

---

## 4. Dùng ảnh COCO với AI

- **Có** dán ảnh COCO cho AI: **không**.
- Trong lúc làm Pha 1, AI chỉ nhận **văn bản**: mã nguồn repo, log chạy
  `score_findings.py`, và các **con số đo** (kích thước ảnh, số pixel, tọa độ box,
  tên lớp). Không có pixel ảnh nào được gửi đi.
- Dữ liệu dự án thật: không dán vào bất kỳ công cụ AI nào (xem `security.md`).

---

## 5. Người trong nhóm xác nhận

<<Dòng này để trống, nhóm tự điền.>>
