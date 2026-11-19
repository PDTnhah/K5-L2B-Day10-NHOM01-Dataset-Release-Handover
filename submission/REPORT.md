# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

## 2. Vì sao báo hết ứng viên làm F1 giảm?

- Báo cáo tất cả ứng viên không đồng nghĩa với phát hiện đúng tất cả lỗi. Một ứng viên chỉ là trường hợp nghi ngờ, cần được kiểm chứng. Nếu báo nhầm các trường hợp không có lỗi, số False Positive (FP) tăng, làm Precision giảm. Nếu bỏ sót lỗi, False Negative (FN) tăng, làm Recall giảm. Cả hai đều khiến F1 giảm.

**Kết quả thực nghiệm seed 1007:**

| Chỉ số | Kết quả |
|---|---:|
| Lỗi luật được phát hiện | 10 |
| Lỗi gán nhãn được xác nhận | 10 |
| Tổng lỗi sau merge | 20 |
| F1 tổng | ≈ 0.5 |
| F1 lỗi luật | ≈ 1.0 |

**Kiểm tra lô sạch seed 5:**

| Chỉ số | Kết quả |
|---|---:|
| Số ảnh kiểm tra | 50 |
| Số lỗi luật phát hiện | 0 |

**Kết luận:** Không nên tối đa hóa số lượng ứng viên được báo cáo. Cần ưu tiên độ chính xác, hạn chế báo nhầm và bỏ sót lỗi. Mỗi ứng viên cần được kiểm chứng trước khi đưa vào kết quả cuối cùng.

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
