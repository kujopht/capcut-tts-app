# Fanfic AI Support — đề xuất lưu trữ bền (CHƯA migrate)

Trạng thái: **ĐỀ XUẤT**. PR Support V1 **không** tạo collection, **không** chạy migration, **không** ghi Appwrite production.
V1 dùng `server/support/store.py::InMemorySupportStore`: dữ liệu nằm trong bộ nhớ tiến trình, có giới hạn và hạn lưu, và **mất khi khởi động lại**.

## Vì sao V1 chấp nhận được lưu trong bộ nhớ

| Hạng mục | Trong bộ nhớ (V1) | Appwrite (đề xuất) |
|---|---|---|
| Dữ liệu | Sự kiện lỗi đã làm sạch, báo cáo SUP-xxxx, sự cố gom nhóm | như bên trái |
| Mất khi restart | Có | Không |
| Nhiều tiến trình web | Mỗi tiến trình một kho riêng (lệch nhau) | Một kho chung |
| Rủi ro dữ liệu người dùng | Thấp: không nội dung truyện, không email, không token | như bên trái |
| Chi phí | 0 | ~3 collection và index |

Đây là dữ liệu **vận hành**, không phải dữ liệu người dùng. Mất khi restart làm giảm giá trị lịch sử nhưng không mất gì của người dùng. Khi chủ dự án bật Support trên production thật và cần lịch sử bền, làm theo đề xuất dưới đây trong một PR riêng.

## Collection đề xuất

### `support_incidents`

| Thuộc tính | Kiểu | Ghi chú |
|---|---|---|
| `incident_id` | string(16) | `INC-XXXXXX`, unique |
| `fingerprint` | string(16) | unique; `sha256(route|lỗi chuẩn|phân hệ)[:16]` |
| `title` | string(160) | lỗi đã chuẩn hoá, đã làm sạch |
| `subsystem` | enum | audio, reader, studio, api, storage, auth, chat, support, web, unknown |
| `route` | string(120) | mẫu route (`/chapters/[id]`), không id thật |
| `severity` | enum | low, medium, high, critical |
| `status` | enum | new, open, ai_diagnosed, needs_owner, resolved |
| `first_seen`, `last_seen` | datetime | |
| `event_count` | integer | |
| `affected_count` | integer | đếm theo băm ẩn danh (không lưu id thô của khách) |
| `builds_json`, `routes_json`, `browsers_json`, `devices_json` | string(2000) | bộ đếm, cắt top-N |
| `timeline_json` | string(8000) | tối đa 100 mục |
| `evidence_json` | string(8000) | chuỗi đã làm sạch |

Index: `status + last_seen`, `subsystem + status`, `fingerprint` (unique).

### `support_reports`

| Thuộc tính | Kiểu | Ghi chú |
|---|---|---|
| `report_id` | string(12) | `SUP-XXXXXX`, unique |
| `incident_id` | string(16) | |
| `summary` | string(1000) | lời người dùng, **đã làm sạch** (email/token/URL ký bị che) |
| `route`, `build`, `browser`, `device` | string | |
| `checks_json`, `findings_json` | string(8000) | kết quả công cụ chỉ đọc |
| `owner_key` | string(24) | `u:<băm>` hoặc `g:<băm>`, không phải user_id thô |
| `reporter_user_id` | string(36), nullable | chỉ khi người dùng đăng nhập; chỉ admin đọc |
| `status` | enum | new, resolved |
| `created_at` | datetime | |

Quyền: **chỉ backend** (API key server). Không quyền nào cho client, kể cả người gửi: người gửi xem lại qua route có kiểm `owner_key`.

### `support_client_events` (tuỳ chọn)

Chỉ cần nếu muốn giữ từng sự kiện thô. Mặc định nên **không** tạo: bộ đếm trong `support_incidents` là đủ cho màn hình admin.

## Hạn lưu và dọn dẹp

- Sự cố `resolved` hơn 30 ngày, báo cáo hơn 90 ngày: xoá bằng một tác vụ định kỳ riêng, có dry-run.
- Không bao giờ lưu nội dung chương, tin nhắn chat, token, cookie, email, hay URL ký. Máy chủ làm sạch **trước khi** ghi (`server/support/sanitize.py`).

## Các bước khi chủ dự án muốn bật lưu bền

1. Duyệt đề xuất này.
2. Tạo PR riêng: `AppwriteSupportStore` hiện thực cùng giao diện với `InMemorySupportStore`, cộng script tạo schema **có dry-run**.
3. Chạy trên môi trường thử trước.
4. Thêm cờ `FAS_SUPPORT_PERSISTENCE=appwrite`. Mặc định vẫn là `memory`.
