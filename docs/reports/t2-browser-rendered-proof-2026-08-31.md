# T2 (BROWSER_RENDERED) — bằng chứng thật, 2026-08-31

Bổ sung cho Task #56 (Universal Acquisition Engine Hardening). Chứng minh
T2 là một tầng THẬT SỰ cần thiết (không phải giả thuyết) bằng một cặp
trước/sau thật: cùng một URL, T0 (HTTP trực tiếp) so với render trình
duyệt thật thông thường.

## Nguồn thử nghiệm

`https://docln.net/truyen/14376-thien-su-nha-ben/c109458-chuong-102-sang-hom-sau`
— một chương light novel dịch tiếng Việt, đã được xếp loại
`PUBLIC_BROWSER_RENDERED` trong `server/scraper/source_policy.py` (xem
mục "docln.net", xác minh thực tế 2026-08-31: trang HTML cho phép, JS
gốc của site tự giải mã nội dung, không có CAPTCHA/thử thách nào xuất
hiện với khách vãng lai thông thường — đây KHÔNG PHẢI reverse-engineer/
tái hiện cơ chế mã hoá của site, chỉ là đọc lại DOM mà trình duyệt của
NGƯỜI DÙNG THƯỜNG đã tự hiển thị).

## Bước 1 — T0 (HTTP trực tiếp, `HttpFetcher`)

Lệnh thật (`server/scraper/http_fetcher.py::HttpFetcher.fetch`, không mock):

```
STATUS OK, LEN: 158030
chapter-c-protected idx: 89511
                     <div id="chapter-c-protected" data-s="xor_shuffle"
                            data-k="1bc7a0c239e7612c"
                            data-c="[&quot;0031EabyVg9XQ/ai2N64FlzT2YYWQ1wJ89dcVBkOX/WQUUNWoc8XLFELW0FMSxd10IjOREIA9MFFQ1xb+sVCFlzT2KgWQ0OinUNE8JlFQdeLhQ0RD4KM/hAV8YFQRVnwgdPYqgFNC05AXQ==&quot;,&quot
```

T0 tải được trang (HTTP 200, 158030 byte) nhưng nội dung chương thật nằm
trong `id="chapter-c-protected"`, `data-s="xor_shuffle"` — một chuỗi
ciphertext mã hoá phía máy chủ, KHÔNG PHẢI văn bản đọc được. T0 không có
cách nào lấy được nội dung thật từ đây mà không tự viết mã giải mã cơ chế
riêng của site (bị cấm theo yêu cầu của owner — xem
`source_policy.py`).

Một lần thử trước đó với cùng URL này còn gặp lỗi kết nối TLS
(`httpx.ConnectError: SSL: UNEXPECTED_EOF_WHILE_READING`) — một chế độ
lỗi T0 THẬT SỰ khác, độc lập với việc mã hoá nội dung, càng cho thấy T0
không phải lúc nào cũng đáng tin cậy cho nguồn này.

## Bước 2 — T2 (render trình duyệt thật, phiên `mcp__claude-in-chrome__*`)

Đường đi khách vãng lai THÔNG THƯỜNG (không đăng nhập, không chèn mã giải
mã/trích khoá, không bỏ qua CAPTCHA — không có CAPTCHA nào xuất hiện).
`get_page_text` sau khi trang tải xong và JS gốc của site chạy xong:

- Tiêu đề trang: "Đọc Thiên sứ nhà bên - Chương 102: Sáng hôm sau. - Cổng
  Light Novel - Đọc Light Novel"
- Toàn bộ nội dung chương 102 (~2.395 từ theo chính site tự báo cáo:
  "Độ dài: 2,395 từ") xuất hiện dưới dạng văn bản tiếng Việt đọc được
  hoàn toàn trong DOM — mở đầu bằng "Sáng hôm sau, Amane thức giấc trong
  khi còn đang mơ màng..." và kết thúc đúng nội dung chương, tiếp theo là
  phần bình luận thật của độc giả site.
- Không có bất kỳ trang CAPTCHA/thử thách/từ chối truy cập nào được trình
  duyệt hiển thị ở bất kỳ bước nào.

## Kết luận

| Hạng mục | T0 (HTTP trực tiếp) | T2 (render trình duyệt thật) |
|---|---|---|
| HTTP status | 200 (khi thành công) hoặc lỗi TLS | 200, không thử thách |
| Nội dung chương | Ciphertext `xor_shuffle`, không đọc được | Văn bản tiếng Việt đầy đủ, đọc được |
| Cách lấy được nội dung thật | Không thể (không tự giải mã) | Đọc DOM sau khi JS gốc của site chạy xong |

Đây chính là khoảng cách mà T2 tồn tại để lấp: T0 lấy được ciphertext, T2
lấy được đúng nội dung mà JS của chính site đã tạo ra cho MỌI khách vãng
lai — không đạt được bằng bất kỳ heuristic T0/T1 nào thông minh hơn, và
không đòi hỏi giải mã/tái hiện cơ chế bảo vệ của site.

## Liên kết mã nguồn

- `server/scraper/universal/browser_plugin.py` — `BrowserRenderedPlugin`
  (T2 seam), `NotConfiguredBrowserRenderer` (stub mặc định, không có
  Playwright/renderer thật nào là dependency của repo này hôm nay).
- `server/tests/test_browser_plugin.py` — 8 test, bao gồm tích hợp thật
  với `AcquisitionRouter` (T0 thất bại → rơi xuống T2 → thành công, lịch
  sử router ghi nhớ T2 là tầng thắng cho host này).
