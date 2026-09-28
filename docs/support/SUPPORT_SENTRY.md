# AI Support ↔ Sentry: đối chiếu lỗi chỉ đọc

Công cụ `get_recent_sentry_issues` giúp trợ lý Support trả lời "lỗi bạn gặp **đã được hệ thống giám sát ghi nhận chưa**". Công cụ **tắt mặc định**, và chỉ bật khi backend có đủ ba biến `FAS_SUPPORT_SENTRY_TOKEN`, `FAS_SUPPORT_SENTRY_ORG` và `FAS_SUPPORT_SENTRY_PROJECTS` (xem `server/.env.example`). Hiện production **chưa bật**.

Mã nằm ở `server/support/sentry_lookup.py` (`SentryChiDoc`), `tools.py` và `engine.py`; bài kiểm ở `server/tests/test_support_sentry.py`.

## Token

- Token phải là loại **read-only**, với đúng ba scope `event:read`, `org:read`, `project:read`.
- Token chỉ nằm trong **closure** của `SentryChiDoc`. Nó không phải thuộc tính của đối tượng, nên `repr()` và `vars()` đều không lộ ra. Điều này đã được đo: thuộc tính name-mangled `__token` vẫn hiện trong `vars()`, nên không dùng cách đó.
- Token **không bao giờ** xuất hiện trong kết quả công cụ, phản hồi API, log hay lời nhắn gửi mô hình AI. Mỗi điều này có một bài test riêng.

## Ba rào

| # | Rào | Cưỡng chế |
|---|---|---|
| 1 | **Danh sách trắng endpoint** | Chỉ `GET`. Chỉ hai mẫu đường dẫn: danh sách issue của một project đã cấu hình, và sự kiện mới nhất của một issue id dạng số. Chỉ ba gốc `https://sentry.io`, `us.` và `de.`. Chỉ ba tham số `query`, `statsPeriod`, `limit`. Không theo chuyển hướng. Mọi kiểm tra chạy **trước** khi mở kết nối. Không có đường nào nhận URL từ người dùng, nên không có SSRF và không có fetch tùy ý. |
| 2 | **Máy chủ tự chọn từ khoá** | Từ khoá tìm kiếm chỉ lấy từ mã lỗi đã làm sạch (`[a-z0-9_.-]`) hoặc từ mẫu route (`/chapters/[id]`). Tin nhắn người dùng không bao giờ được đưa vào Sentry. Công cụ chỉ được đưa vào kế hoạch khi ngữ cảnh có `last_error_code`. |
| 3 | **Kết quả tối thiểu** | Người dùng và mô hình AI chỉ thấy số vấn đề, số lần xảy ra, thời điểm gần nhất và việc lỗi có trùng bản build hay không. Tiêu đề và culprit (vốn là thông điệp lỗi) chỉ dành cho quản trị (`chi_tiet=True`), và cũng phải qua `sach_chuoi`. |

## Ngân sách thời gian (đo 2026-09-28)

Hộp công cụ cắt mỗi bước ở `THOI_GIAN_TOI_DA_GIAY = 3.0` giây.

**Trước khi sửa:**
- ba GET tuần tự, mỗi GET mở một kết nối mới, mất khoảng 1,3–1,5 giây, cộng lại khoảng **4,2 giây**;
- vì vậy trên QA giao diện, bước này **luôn** báo "Kiểm tra quá thời gian", và phát hiện `error_tracked` không bao giờ xuất hiện.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Kết nối | Mỗi GET một kết nối mới | Một `httpx.Client` dùng chung, giữ kết nối |
| Các project | Tra tuần tự | Tra **song song** |
| Hạn chót | Timeout theo từng pha của httpx, nên không giữ được tổng thời gian (đo được 3,3 giây) | Hạn chót **cứng** `NGAN_SACH_GIAY = 2.6` bằng `wait(timeout=)`; luồng trễ bị bỏ lại |
| "Sự kiện mới nhất" (để so build) | Luôn gọi | Chỉ gọi khi còn đủ thời gian; hết giờ thì `cung_build = None`, tức "chưa biết" |
| Thời gian thật trên Sentry | ~4,2 giây, bị cắt | **1,4–1,7 giây** |

## Không khẳng định khi không tra được

Trước đây, một project trả 401, 5xx, hết hạn hoặc lỗi mạng bị tính thành "0 vấn đề". Người dùng khi đó nhận câu "Hệ thống giám sát chưa ghi nhận lỗi tương tự" — một câu **sai** nhưng nghe rất chắc chắn.

Cách xử lý hiện nay:
- Nếu không thấy vấn đề nào **và** có project không trả lời, kết quả là `khong_tra_duoc`, hiển thị "Chưa tra được hệ thống giám sát lỗi lúc này" với trạng thái `unknown`.
- Nếu thấy vấn đề ở một project nhưng project khác hỏng, công cụ vẫn báo vấn đề đó, kèm cờ `day_du = False`.

## Kiểm chứng

- `server/tests/test_support_sentry.py` và `test_support_v1.py`: **48/48 OK**. Các bài test dùng client HTTP giả, không gọi mạng. Nội dung kiểm gồm:
  - danh sách trắng;
  - token không lộ;
  - song song và hạn chót, kể cả khi một project treo;
  - không khẳng định khi không tra được.
- Trên Sentry thật, với token read-only: tìm lại được hai sự cố smoke `FANFIC-WEB-1` và `PYTHON-FASTAPI-1`, `cung_build = True`, và chỉ gọi các URL trong danh sách trắng.
- QA trên Chrome hiển thị, ở hai khổ 1440 và 390: **6/6 ĐẠT**.
  - Danh sách kiểm tra có dòng "Hệ thống giám sát lỗi — đã ghi nhận 1 lỗi tương tự".
  - Câu trả lời có phát hiện "đã ghi nhận".
  - **Trình duyệt không gửi request nào tới `sentry.io`**, vì việc tra cứu chạy phía máy chủ.
  - Không tràn ngang.
