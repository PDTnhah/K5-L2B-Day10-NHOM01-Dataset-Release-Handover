# Bảo mật khi làm việc

> Trả lời gắn với lô bạn vừa bàn giao, không chép slide. Mỗi mục vài câu.

Lô: `runs/r1007` — v1 `lab250_fd90ed6d0b9f` (250 ảnh COCO val2017, QC v1 20/250 lỗi, Hold),
v2 `lab250_fd90ed6d0b9f_v2` (236 ảnh, đã đóng gói).

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
Không chép lô (cả file ảnh, nhãn, mask) qua USB hay bất kỳ thiết bị lưu trữ
di động nào, cũng không gửi qua email cá nhân hay nhờ người khác chép hộ.
Lý do: lô gồm ảnh chụp người thật (COCO) — đây là dữ liệu ảnh có khuôn mặt, dù được
công khai trong bài học thì trong bài này nó được xử lý như dữ liệu lô bàn giao của nhóm.
Thay bằng cách: làm tiếp trên máy công ty trong ca làm việc, hoặc nếu thật sự cần
thì xin giảng viên phê duyệt một phương án cụ thể (ví dụ: chỉ chép phần văn bản
không chứa ảnh — `errors.json`, `candidates.json`, `review_log.csv` — vì phần này không
chứa dữ liệu cá nhân). Nhờ người khác chép hộ cũng không được: việc gửi file qua
thiết bị của người thứ ba vẫn là phát tán dữ liệu, và không ai nắm được máy đó.

## 2. Năm việc: được hay không
| Việc | Được/không | Vì sao |
|---|---|---|
| Mở job được giao trên máy công ty | Được | Đây là đúng mục đích của máy công ty và job đã được phân công cho nhóm. Miễn là trong ca, trên máy công ty, không chụp lại màn hình. |
| Chụp màn hình gửi người quen | Không | Ảnh chụp màn hình lô bàn giao có thể chứa ảnh người và dữ liệu chưa được bàn giao; gửi qua mạng xã hội/chat làm mất kiểm soát. Nếu cần hỏi nhau thì chép số đo hay đường dẫn file, không chụp màn hình. |
| Chép lô ra USB | Không | Xem mục 1 — ảnh có khuôn mặt người thật, không mang ra khỏi môi trường công ty. |
| Dán nhãn thật lên chatbot | Không | Nhãn thật gắn với ảnh thật; dán lên chatbot (dịch vụ ngoài) là đưa dữ liệu ra ngoài, và chatbot có thể lưu giữ dùng để huấn luyện. Trong bài này chỉ dán văn bản (mã, log, số đo) — không dán ảnh. |
| Đưa tài khoản CVAT cho đồng nghiệp | Không | Tài khoản dùng chung làm mất khả năng truy vết ai đã làm gì, và khiến người khác đánh dấu vào lô bằng tài khoản của nhóm. Nếu thật sự cần người khác giúp thì tạo tài khoản riêng cho họ và ghi rõ trong `review_log.csv` ai đã xem ảnh nào. |

Nguyên tắc chung: công cụ dùng trong nhóm phải nằm trong phạm vi kiểm soát của
nhóm (máy công ty, tài khoản có tên người dùng thật). Dữ liệu ảnh không đi ra ngoài;
văn bản đi được vì không chứa dữ liệu cá nhân.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
Việc nhóm làm: đã rà lô và xác nhận lô có ảnh mặt người nhìn rõ, cụ thể:
- `000000004395` — mặt người rõ, ảnh cận cảnh (nhiều người, mặt chiếm phần lớn khung hình)
- `000000016598` — mặt người rõ ở khoảng giữa ảnh
- `000000009448` — mặt người rõ, người đứng gần camera
- `000000020992` — mặt người rõ

Trạng thái lô: cả 4 ảnh trên đều nằm trong v2 (`lab250_fd90ed6d0b9f_v2`) và chưa được
làm mờ. Guideline của lô bài lab (`guideline/changelog.md`, v1.2 và v1.3) không có quy định
làm mờ, nên README v2 ghi "Kết luận v2: Release" là kết luận về chất lượng nhãn detection
(QC). Trong ca này guideline **yêu cầu** làm mờ, nên kết luận phải là **Hold**: dừng gửi
v2 cho team AI cho tới khi người phụ trách quyết định. Nhóm không tự sửa ảnh trong v2
đã đóng gói (sửa thì mã `.sha256` không còn khớp).

Báo ai: báo người phụ trách lô / chủ sở hữu dữ liệu (trong bài lab là giảng viên/coach)
bằng văn bản, kèm danh sách 4 ảnh trên và trạng thái Hold. Lý do phải báo: quyền quyết định
làm mờ/xoá ảnh thuộc về chủ sở hữu dữ liệu và người chịu trách nhiệm phê duyệt bàn giao;
đội dữ liệu không tự ý làm mờ hay xoá ảnh.

Vì sao không tự làm mờ hay xoá ảnh:
1. Xoá ảnh trong `delivery/` là sửa lô v1, vi phạm quy tắc "không sửa `delivery/`;
   bản sửa là v2" — và làm sai mã `release_id` (id được tính từ hash của
   `manifest.json` + `metadata.json`).
2. Lô v2 là sản phẩm detection giao cho team AI: xoá hoặc làm mờ ảnh sẽ làm hỏng
   mốc 1–1 giữa ảnh và nhãn, và các ảnh bị xoá sẽ biến mất khỏi tỉ lệ QC v1
   (mẫu số 250) — làm sai số liệu bàn giao.
3. Làm mờ bằng công cụ không được kiểm chứng có thể che nhãn hoặc làm hỏng ảnh;
   đây là thao tác cần người chịu trách nhiệm chấp nhận rủi ro và có thể yêu cầu chạy
   lại kiểm thử.
4. Nội dung cụ thể: guideline/changelog của lô quy định khi nào vẫn phải gán box
   cho vật bị che; làm mờ mặt có thể làm ảnh rơi vào trường hợp đó và làm sai nhãn.

Phương án nhóm đề xuất: giữ nguyên v1 (`delivery/`) và v2 đã đóng gói. Nếu người phụ
trách yêu cầu làm mờ hoặc loại ảnh có mặt, thì làm ở một bản mới (v3, `--parent` là v2
trong lineage) bằng công cụ được duyệt, ghi danh sách ảnh đã xử lý vào phần Ghi chú của
`README.txt`, lập lại `manifest.csv` và chạy lại `pack_release.py`. Như vậy số liệu QC
v1 và v2 vẫn truy vết được.
