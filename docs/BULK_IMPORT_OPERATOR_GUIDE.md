# Nhập chương hàng loạt — hướng dẫn vận hành

Tài liệu thao tác cho người vận hành nhập MỘT truyện nhiều chương (50–500)
cùng lúc, dùng lại đúng đường `POST /api/chapters`/`POST /api/jobs` — xem
`server/bulk_import_domain.py` và `server/bulk_import_service.py` để biết chi
tiết thiết kế đầy đủ. Tài liệu này chỉ trả lời "làm sao để vận hành", không
lặp lại thiết kế.

## Trước khi nhập

1. Tệp đầu vào là `.txt` (mỗi chương bắt đầu bằng dòng `=== Tiêu đề ===`) hoặc
   `.json` (`[{"title": "...", "content": "..."}]` hoặc
   `{"chapters": [...]}`).
2. Giới hạn hiện tại (cấu hình được qua biến môi trường, xem
   `server/main.py`):

   | Biến | Mặc định | Ý nghĩa |
   |---|---|---|
   | `FAS_MAX_IMPORT_ITEMS` | 500 | số chương tối đa MỘT lô |
   | `FAS_MAX_IMPORT_TOTAL_CHARS` | 5.000.000 | tổng ký tự tối đa MỘT lô |
   | `FAS_MAX_CHAPTER_CHARS` | 100.000 | ký tự tối đa MỘT chương |
   | `FAS_MAX_ACTIVE_JOBS` | 3 | số job TTS chạy đồng thời MỖI truyện |

   Vượt `FAS_MAX_IMPORT_ITEMS`/`FAS_MAX_IMPORT_TOTAL_CHARS` bị từ chối
   TRƯỚC khi ghi bất kỳ hàng nào (kiểm toàn bộ danh sách trước, không phải
   kiểm rồi dừng giữa chừng).

3. **Luôn preview trước khi nhập thật**:

   ```bash
   curl -s -X POST "$API/api/novels/$NOVEL_ID/chapter-imports/preview" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d @lo-chuong.json
   ```

   Không ghi gì cả — chỉ phân tích cú pháp, kiểm giới hạn, và trả về
   `batch_id` (tất định từ chủ sở hữu + truyện + toàn bộ nội dung — xem
   `bulk_import_domain.batch_fingerprint`) cùng cờ `already_imported`. Nếu
   `already_imported=true`, lô này (đúng nội dung này) đã tồn tại — kiểm tra
   trạng thái bằng `GET .../chapter-imports/{batch_id}` trước khi gửi lại.

## Nhập thật

```bash
curl -s -X POST "$API/api/novels/$NOVEL_ID/chapter-imports" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @lo-chuong.json
# -> {"batch": {"batch_id": "imb_...", ...}, "created": true|false}
```

`created=false` nghĩa là lô đã tồn tại (cùng fingerprint) và request này chỉ
tiếp tục lô cũ — **an toàn gửi lại nguyên văn bao nhiêu lần cũng được**,
không bao giờ tạo chương trùng (đã kiểm chứng cả ở mức unit test lẫn trực
tiếp trên staging: gửi lại 12 chương giống hệt sau khi hoàn tất, số chương
thật trong Appwrite vẫn đúng 12, không phải 24).

Theo dõi tiến độ:

```bash
watch -n 3 curl -s "$API/api/novels/$NOVEL_ID/chapter-imports/$BATCH_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Trường quan trọng: `status` (`preparing`/`running`/`completed`/`partial`/
`failed`/`cancelled`/`cancelling`), `count_chapter_created`,
`count_job_queued`, `count_completed`, `count_failed`.

## Khi có lỗi

- `status=partial` = có ít nhất một chương lỗi, phần còn lại vẫn xong bình
  thường. Xem `items[].error_message` (route `GET .../chapter-imports/{id}`
  trả về TỐI ĐA 200 mục/trang) để biết chương nào lỗi và vì sao.
- Thử lại MỘT chương lỗi:
  ```bash
  curl -s -X POST "$API/api/novels/$NOVEL_ID/chapter-imports/$BATCH_ID/items/$ITEM_ID/retry" \
    -H "Authorization: Bearer $TOKEN"
  ```
- Thử lại TẤT CẢ chương lỗi trong lô:
  ```bash
  curl -s -X POST "$API/api/novels/$NOVEL_ID/chapter-imports/$BATCH_ID/retry" \
    -H "Authorization: Bearer $TOKEN"
  ```
- Retry trên một mục KHÔNG ở trạng thái `failed` trả `409` (đã kiểm chứng
  trực tiếp trên staging) — không có cách nào vô tình chạy lại một chương
  đã xong.
- Nếu tiến trình vận hành (worker) chết hoặc VM khởi động lại giữa lô đang
  chạy: **không cần làm gì đặc biệt**. Vòng đối soát (`drive_chapter_imports`,
  chạy mỗi vài giây trong `server/worker.py`) tự tiếp tục lô dở dang ngay khi
  worker sống lại — không có lease/hạn nào để hết. Một lô kẹt ở `preparing`
  quá 15 phút (`FAS_IMPORT_PREPARING_STALE_SECONDS`, ví dụ worker chết đúng
  lúc đang ghi danh sách chương) sẽ tự chuyển `failed` với thông báo yêu cầu
  gửi lại ĐÚNG tệp cũ — gửi lại là đủ, `batch_id` tất định sẽ khớp lại lô cũ.

## Huỷ một lô

```bash
curl -s -X POST "$API/api/novels/$NOVEL_ID/chapter-imports/$BATCH_ID/cancel" \
  -H "Authorization: Bearer $TOKEN"
```

Ngừng tạo chương/job MỚI; job đang chạy vẫn được đối soát cho xong (không bỏ
dở giữa chừng). Gửi lại ĐÚNG tệp cũ sau khi huỷ sẽ **resume** (không tạo lô
mới) — tiếp tục đúng những chương chưa làm.

## KHÔNG có chế độ "dry-run" đầy đủ

Route `preview` (ở trên) là validation-only — nó kiểm cú pháp/giới hạn và
tính trước `batch_id`, nhưng **không** mô phỏng việc tạo chương/chạy TTS.
Hiện KHÔNG có cách nào chạy thử toàn bộ luồng (tạo chương thật, chạy job
TTS thật) mà không thực sự ghi dữ liệu. Với một lô lớn (gần 500 chương),
cách an toàn nhất hiện tại là **nhập một lô nhỏ thử nghiệm trước** (xem
checklist lô đầu tiên, `docs/FIRST_REAL_SERIES_CHECKLIST.md`) trên staging,
không phải trông chờ một cờ dry-run chưa tồn tại.

## Giới hạn đã biết (2026-08-23, chưa sửa)

- **Xoá truyện KHÔNG dọn `chapter_import_batches`/`chapter_import_items`.**
  Xác nhận trực tiếp trên staging: xoá một truyện có 2 lô/18 mục nhập —
  chương/track/job đều được dọn sạch (0 còn lại), nhưng CẢ HAI lô và tất cả
  18 mục vẫn còn, trỏ tới một `novel_id` không còn tồn tại. Vô hại (không
  tốn chi phí đáng kể, không có nguy cơ trùng lặp vì `batch_id` gắn với
  `novel_id` cụ thể), nhưng là rác dữ liệu chưa được dọn — cân nhắc thêm vào
  `_xoa_du_lieu_nguoi_dung`/cascade xoá truyện nếu cần dọn triệt để.
