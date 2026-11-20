# Báo cáo nhóm 01

## 1. Số liệu luyện tập
- **F1 theo seed** (rule / cross_check / overall, số làm tròn do `score_findings.py` in):

  | Seed | Lỗi luật | Lỗi gán nhãn đã xác nhận | rule | cross_check | overall |
  |---|---:|---:|---:|---:|---:|
  | 1007 (luyện tập, có review) | 10 | 10 | ≈ 1.0 | ≈ 0.7 | ≈ 0.9 |
  | 2007 (chỉ chạy validator luật, không review) | 11 | 0 | ≈ 1.0 | — | ≈ 0.7 |
  | 5 `--no-faults` (lô sạch, 50 ảnh) | 0 | 0 | ≈ 1.0 | — | ≈ 1.0 |

  Các seed khác đã thử khi viết validator luật (11, 23, 42, 77, 101, 1007 `--opaque`) đều có F1 lỗi luật 1.0, xem `prompts.md` mục 3.2.
- **Số ứng viên trên lô sạch** (`--no-faults`, seed 5, 50 ảnh): **0** với `validator/crosscheck.py` và cũng **0** với `validate.py --candidates`.
- **Hàng đợi trên seed luyện tập 1007:** **10 ứng viên trên 10 ảnh** (`crosscheck.py`: 2 `bbox_drift`, 4 lệch lớp, 1 `instance_merge`, 3 `missing_box`). Ngoài ra có 4 ảnh bị bỏ qua vì đã dính lỗi luật (mỗi ảnh mang nhiều nhất một lỗi). Cả 10 ảnh đều đã được xem, kết quả 10 `confirmed`, 0 `rejected`.
- **Ngưỡng đã chọn và cách chọn** (không dùng `_private`): ngưỡng nằm trong `DEFAULTS` của `validator/crosscheck.py`. Nhóm chọn bằng số đo các cặp box–segment trên lô sạch (`--dump-pairs`), dựa vào pixel mask chứ không chỉ IoU bbox:
  - `match_iou` 0.5: ghép box với segment.
  - `drift_cov` 0.92 + `drift_min_out_px` 40: `bbox_drift` chỉ báo khi box bỏ sót pixel thật sự, không phải nhiễu viền.
  - `missing_min_seg` 0.004 + `missing_cov` 0.6: `missing_box` chỉ xét segment thing đủ lớn mà không có box cùng lớp nào phủ.
  - `merge_excl` 0.2 + `merge_max_cov` 0.97: `instance_merge`.
  - `swap_iou` 0.6 / `swap_fill` 0.4: lệch lớp.

  Với bộ ngưỡng này lô sạch ra 0 ứng viên, còn hàng đợi seed 1007 chỉ 10 ảnh, đủ nhỏ để cả nhóm xem hết. Đổi lại vẫn có lỗi gán nhãn bị sót (cross_check ≈ 0.7). Quá trình chỉnh ngưỡng của `validate.py --candidates` (lọc `isthing`, điều kiện kép cho `bbox_drift`, hai box không chồng nhau cho `instance_merge`) ghi ở `prompts.md` mục 2.3.

## 2. Vì sao báo hết ứng viên làm F1 giảm?

- Báo cáo tất cả ứng viên không đồng nghĩa với phát hiện đúng tất cả lỗi. Một ứng viên chỉ là trường hợp nghi ngờ, cần được kiểm chứng. Nếu báo nhầm các trường hợp không có lỗi, số False Positive (FP) tăng, làm Precision giảm. Nếu bỏ sót lỗi, False Negative (FN) tăng, làm Recall giảm. Cả hai đều khiến F1 giảm.

**Kết quả thực nghiệm seed 1007:**

| Chỉ số | Kết quả |
|---|---:|
| Lỗi luật được phát hiện | 10 |
| Lỗi gán nhãn được xác nhận | 10 |
| Tổng lỗi sau merge | 20 |
| F1 tổng | ≈ 0.9 |
| F1 lỗi luật | ≈ 1.0 |
| F1 lỗi gán nhãn | ≈ 0.7 |

Lô sạch (seed 5) cho thấy vì sao không thể báo hết ứng viên: khi tiêu chí còn lỏng, lô sạch (không có lỗi nào) vẫn sinh nhiều ứng viên. Ví dụ khi chưa lọc `isthing` có 168 ứng viên `missing_box` giả, khi chưa thêm điều kiện cho `instance_merge` còn 15 ứng viên, và chỉ dùng pixfrac cho `bbox_drift` thì có 29 cặp nghi lệch trên 50 ảnh sạch (xem `prompts.md` mục 2.3). Đó là lệch tự nhiên của COCO (vật bị che, crowd, polygon lệch), không phải lỗi. Báo hết thì mỗi ứng viên như vậy là một FP.

**Kiểm tra lô sạch seed 5:**

| Chỉ số | Kết quả |
|---|---:|
| Số ảnh kiểm tra | 50 |
| Số lỗi luật phát hiện | 0 |

**Kết luận:** Không nên tối đa hóa số lượng ứng viên được báo cáo. Cần ưu tiên độ chính xác, hạn chế báo nhầm và bỏ sót lỗi. Mỗi ứng viên cần được kiểm chứng trước khi đưa vào kết quả cuối cùng.

## 3. Quyết định và lineage
- QC v1: Có 20 lỗi trên 250 ảnh, tương ứng tỷ lệ lỗi 8%, vượt ngưỡng cho phép 2%.
- Kết luận: HOLD, chưa đủ điều kiện Release dataset v1.
- Lineage: Run `R-021` bị ảnh hưởng (`affected=True`, `action=review_or_retrain`).
- Lý do: R-021 đã được huấn luyện trên dữ liệu thuộc release bị ảnh hưởng. Việc sửa dataset không tự động sửa các trọng số model đã học, vì vậy cần đánh giá lại hoặc huấn luyện lại model bằng dữ liệu đã được kiểm tra và sửa lỗi.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Chứng minh:** bytes của file (hoặc của cả gói zip) **không đổi** kể từ lúc ghi hash. Người nhận tính lại sha256, khớp thì biết mình đang dùng đúng bản đã bàn giao, không bị hỏng khi chép/tải, không bị sửa lén. `pack_release.py` đóng gói tái lập (thứ tự file và thời gian cố định) nên cùng nội dung thì cùng mã trên mọi máy.
- **Không chứng minh:**
  - Nhãn **đúng**: một ảnh `class_swap` hay `missing_box` vẫn có hash hợp lệ; hash chỉ nói "không đổi", không nói "đúng".
  - Ảnh hợp lệ về nội dung, bản quyền hay quyền riêng tư (ảnh có khuôn mặt vẫn có hash hợp lệ).
  - **Ai** tạo ra file: sha256 không phải chữ ký, ai sửa cả file lẫn manifest thì hash mới vẫn khớp.
  - **Bên nào sai** khi lệch: với `wrong_hash` ở 000000006763, hash chỉ báo "lệch", nhóm phải mở ảnh kiểm mới biết ảnh còn nguyên và chỉ manifest ghi sai, nên giữ ảnh và ghi hash mới trong manifest v2.
- **Ví dụ thật trong lab:** `check_handover.py` báo H15 FAIL vì `.sha256` của v2 không khớp: có file trong v2 bị sửa sau khi đóng gói. Hash phát hiện được việc thay đổi nhưng không cho biết file nào đổi hay đổi có đúng không; nhóm kiểm lại nội dung (H1–H14 PASS) rồi chạy lại `pack_release.py`.
- **Vì sao không ghi đè v1:** R-021 đã train trên v1; giữ v1 nguyên (hash cũ vẫn khớp) thì còn tái lập và đối chiếu được model cũ. v2 là bản mới có `parent` trỏ về v1 trong lineage.

## 5. Truy vết
- **Ticket:** team AI báo model bỏ sót `cup` bị che/ở mép ảnh, thấy rõ ở scene_278 và scene_835.
- **Changelog:** v1.3 bắt buộc gán box `cup` bị che trên 50% hoặc cắt ở mép; v1.2 cho phép bỏ qua. Vậy job làm theo **v1.2** có nguy cơ thiếu box `cup`.
- **Tiêu chí:** ảnh thuộc job có guideline v1.2 **theo `jobs.csv`** (J01, J02, J03) và có ít nhất một box lớp `cup` (class 41) trong `labels/` của lô.
  - **tier_a** (thỏa tiêu chí, nằm trong scene team AI nêu): 000000002157, 000000002431 (scene_278); 000000003845, 000000003934 (scene_835).
  - **tier_b** (thỏa cùng tiêu chí ở cảnh khác, chưa ai báo): 000000002592, 000000002685 (scene_418); 000000003661 (scene_859).
  - **notify:** người gán và người kiểm của các job chứa ảnh tầng a/b. Cả 7 ảnh đều thuộc J02, nên báo **A04, Q03**.
- **Vì sao lấy guideline theo job, không theo ảnh:** guideline ghi ở từng ảnh có thể sai, đó chính là lỗi `guideline_mismatch` (lô này có 000000005992, 000000015956). Job mới là đơn vị được giao làm theo một phiên bản guideline, nên nó quyết định người gán thực sự đã theo quy tắc nào.
- **Tầng a khác tầng b:** tầng a là ảnh đã được báo (trong scene ticket nêu); tầng b là ảnh cùng rủi ro nhưng chưa ai phát hiện. Tìm ra tầng b mới là giá trị chính của truy vết, vì team AI chỉ xem tay vài cảnh.
- **Tự đo (`score_findings.py`):** tier_a ≈ 1.0, tier_b ≈ 1.0, notify ≈ 1.0. Đề ẩn dùng cùng tiêu chí (lớp `truck`, scene_100 và scene_777).

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
Không thấy bug trong `scripts/` ở các lệnh nhóm đã chạy. Có hai điểm dễ sai về quy trình khi nhiều người làm trên nhiều máy:
- **`export_submission.py --run` ghi đè `submission/lineage.jsonl`** bằng `runs/lineage.jsonl` của máy đang chạy. `runs/` không được commit, nên nếu chạy lệnh này trên máy chưa ghi HOLD và release v2 vào lineage thì H14 sẽ FAIL. Nhóm chỉ export từ máy đã làm Pha 3–4.
- **`.sha256` phải tạo lại sau mọi lần sửa trong v2.** Nhóm từng sửa một file trong v2 sau khi chạy `pack_release.py`, khiến H15 FAIL; đã chạy lại `pack_release.py` để sửa. GUIDE có nhắc điều này nhưng dễ quên khi sửa README.txt vào phút cuối.
