# Checklist nhập bộ truyện THẬT đầu tiên

Dùng lần đầu đưa một bộ truyện thật (không phải dữ liệu QA) vào hệ thống ở
quy mô 50–500 chương. Xem `docs/BULK_IMPORT_OPERATOR_GUIDE.md` để biết các
lệnh cụ thể — tài liệu này chỉ là THỨ TỰ làm, không lặp lại cú pháp.

Đã xác nhận (2026-08-23, trên staging thật, không phải mock):
- Một lô 12 chương thật chạy hết qua worker staging thật (`fanfic-staging-worker`)
  và R2 thật (`fanfic-staging`), hoàn tất trong ~126 giây.
- Gửi lại ĐÚNG lô đó sau khi đã xong: `created=false`, số chương thật trong
  Appwrite vẫn đúng 12 (không nhân đôi) — kiểm bằng cách đếm trực tiếp, không
  chỉ tin phản hồi API.
- `retry` một chương KHÔNG ở trạng thái lỗi trả `409` — không có đường vô
  tình chạy lại một chương đã xong.

## 1. Trước khi chạm vào staging

- [ ] Xác nhận `FAS_OWNER_USER_IDS` trên staging KHÔNG còn tài khoản QA nào
      không cần thiết (kiểm `owner_count` ở `/api/health`).
- [ ] Xác nhận `fanfic-staging-worker` đang `active`+`enabled`
      (`systemctl is-active`/`is-enabled` trên `fanfic-appwrite-temp`).
- [ ] Chuẩn bị tệp `.txt`/`.json` của bộ truyện thật, đã kiểm tra encoding
      UTF-8 và không lẫn ký tự điều khiển lạ.

## 2. Thử nghiệm quy mô nhỏ TRÊN STAGING trước

- [ ] Cắt 5–10 chương ĐẦU của bộ truyện thật thành một tệp thử riêng.
- [ ] `preview` tệp thử — xác nhận số chương/tổng ký tự đúng kỳ vọng, không
      có lỗi phân tích cú pháp (dấu `===` sai chỗ, JSON sai định dạng, v.v.).
- [ ] Nhập thật tệp thử trên staging, theo dõi tới `completed`.
- [ ] Nghe thử ít nhất MỘT chương thật (không chỉ kiểm `HTTP 200`) — xác
      nhận giọng đúng, âm thanh nghe được, không bị cắt/lỗi ghép đoạn.
- [ ] Gửi lại ĐÚNG tệp thử lần hai — xác nhận `created=false` và số chương
      không đổi (đếm trực tiếp qua Appwrite hoặc trang quản trị, không chỉ
      tin phản hồi API).
- [ ] Dọn tệp thử: xoá truyện thử trên staging. Lưu ý giới hạn đã biết —
      `chapter_import_batches`/`chapter_import_items` của lô thử SẼ còn sót
      lại (vô hại, xem mục "Giới hạn đã biết" trong operator guide).

## 3. Nhập TOÀN BỘ bộ truyện thật trên staging

- [ ] Nếu bộ truyện > 500 chương: chia thành nhiều lô theo TRUYỆN (mỗi
      truyện con/mùa một lô), không cố nhét một lô vượt
      `FAS_MAX_IMPORT_ITEMS`.
- [ ] Nhập, theo dõi `count_completed`/`count_failed` tới khi lô ở trạng
      thái cuối (`completed`/`partial`).
- [ ] Nếu `partial`: xem `error_message` của TỪNG mục lỗi trước khi `retry`
      hàng loạt — một lỗi lặp lại ở nhiều chương (vd giọng không hợp lệ,
      định dạng nội dung sai) nên sửa NGUYÊN NHÂN GỐC trước khi retry, không
      retry mù rồi lặp lại đúng lỗi đó.
- [ ] Nghe thử NGẪU NHIÊN vài chương rải rác trong lô (đầu/giữa/cuối), không
      chỉ chương đầu tiên.

## 4. Trước khi coi là "sẵn sàng lên thật"

- [ ] Toàn bộ lô ở trạng thái `completed` (không còn `partial`/`failed` nào
      chưa giải thích được).
- [ ] Đã xác nhận KHÔNG có chương trùng (đếm chương thật của truyện, so với
      số chương kỳ vọng trong tệp gốc).
- [ ] Đã quyết định: xuất bản qua route xuất bản THƯỜNG
      (`POST /api/novels/{id}/publish`) — nhập hàng loạt KHÔNG có route xuất
      bản riêng, và đó là chủ đích (xem `XuatBanSauKhiNhap` trong
      `test_bulk_chapter_import.py`).
- [ ] Đã đọc kỹ mục "KHÔNG có chế độ dry-run" trong operator guide — không
      có cách mô phỏng lô thật mà không ghi dữ liệu; bước 2 (thử quy mô nhỏ
      trên staging) LÀ cách thay thế duy nhất hiện có.

## Không nằm trong phạm vi checklist này

- Triển khai lên **production** — checklist này chỉ dừng ở staging. Chuyển
  sang production là một quyết định phát hành riêng, cần xác nhận rõ ràng
  trước khi thực hiện (không tự động theo sau checklist này).
- Sửa giới hạn "xoá truyện không dọn hết lô nhập" — đã ghi nhận, chưa sửa,
  xem operator guide.
