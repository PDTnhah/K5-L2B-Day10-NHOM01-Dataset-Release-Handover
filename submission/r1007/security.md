# Bảo mật khi làm việc

> Trả lời gắn với lô bạn vừa bàn giao, không chép slide. Mỗi mục vài câu.

Lô: `runs/r1007` — `release_id lab250_fd90ed6d0b9f`, 250 ảnh COCO val2017 (250 ảnh, mỗi ảnh
mang nhiều nhất một lỗi, 10 lỗi luật đã bắt được ở Pha 1).

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

Trạng thái lô: lô chưa được xử lý làm mờ khuôn mặt. Vì vậy lô đang ở trạng
thái Hold, và nhóm không đóng gói bàn giao (`pack_release.py`) cho tới khi xử lý
xong.

Báo ai: báo giảng viên/coach phụ trách (người quyết định mức xử lý) và ghi
trong `runs/r1007/security.md` cùng phần Ghi chú của `README.txt` ở lô v2. Lý do phải
báo: quyền quyết định làm mỹ/xoá ảnh thuộc về chủ sở hữu dữ liệu và người chịu
trách nhiệm phê duyệt bàn giao; đội dữ liệu không tự ý xoá ảnh.

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

Phương án nhóm đề xuất: giữ nguyên `delivery/` (không đụng), tạo lô v2 trong
`runs/r1007/handover/<release_id>_v2/`; nếu giảng viên yêu cầu xoá ảnh có mặt thì xoá
ở v2 và ghi rõ danh sách ảnh bị loại vào `README.txt` + `Ghi chú`, để số liệu QC v1
vẫn truy vết được.

(Phần dưới để nhóm điền thêm nếu có phát hiện cụ thể khác.)
