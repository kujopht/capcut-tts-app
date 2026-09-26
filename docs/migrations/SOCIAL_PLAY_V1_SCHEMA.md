# Social Play V1 — schema Appwrite (bổ sung, không phá vỡ)

Migration cho gói "community + hồ sơ" (PR A): spoiler/fandom trên bài đăng,
nhãn "đã chỉnh sửa", báo cáo người dùng, chặn/tắt tiếng, banner/màu nhận
diện/fandom trên hồ sơ. Toàn bộ thay đổi là **CỘNG THÊM** (thêm thuộc tính,
thêm một collection mới) — không đổi tên, không xoá, không đổi kiểu của bất
kỳ thuộc tính nào đã có.

## 1. Vì sao phải tắt trước khi chạy

Ghi một thuộc tính **chưa tồn tại** vào một document Appwrite làm **hỏng cả
lần ghi đó** (không phải chỉ bỏ qua thuộc tính lạ). Vì vậy toàn bộ tính năng
ở PR này nằm sau một cờ duy nhất:

```
FAS_SOCIAL_V1_SCHEMA=false   # mặc định — mọi nơi TẮT cho tới khi migration chạy xong
```

Khi cờ tắt, `server/social_service.py` từ chối rõ ràng (409,
`social.CapabilityDisabled`, thông điệp "Tính năng này chưa được bật trên
máy chủ.") ngay khi có ai cố dùng field mới — **không bao giờ** âm thầm bỏ
field đó rồi coi như thành công. Đây là lớp phòng thủ THỨ NHẤT.

Lớp phòng thủ THỨ HAI (độc lập, luôn bật, không phụ thuộc cờ trên):
`server/appwrite_store.py::AppwriteMetadataStore._writable()` hỏi Appwrite
xem collection thực sự có thuộc tính nào (`_supported_fields`, cache theo
tiến trình) rồi **lọc bỏ** field chưa tồn tại trước khi gửi đi. Cơ chế này
đã dùng cho mọi nhóm field V2/V4/V6 trước đây; các field mới của PR này chỉ
là một nhóm nữa dùng lại đúng cơ chế đó (xem `Settings.social_v1_schema`,
`appwrite_social.SOCIAL_PERSISTED_FIELDS`, `appwrite_adapter._PROFILE_V2_FIELDS`).

Kho **mock** (`DATA_BACKEND=mock`) không có Appwrite thật để làm hỏng, nên
năng lực luôn **BẬT** trên mock bất kể cờ — xem `social.capabilities_for`.
Đây là môi trường phát triển/kiểm thử cục bộ, không phải production.

## 2. Danh sách thay đổi

### 2.1 `profiles` — thêm 3 thuộc tính

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `banner_key` | string(512) | không | Khoá object R2 của banner, cùng quy ước với `avatar_key` |
| `accent` | string(24) | không | Một trong preset `server/social.py::ACCENT_PRESETS` |
| `fandom_ids` | string(32), **mảng** | không | Slug trong `social.COMMUNITY_FANDOMS`, tối đa 5 |

### 2.2 `posts` — thêm 3 thuộc tính, thêm 1 index

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `spoiler` | boolean | không | Người viết tự đánh dấu |
| `fandom_id` | string(32) | không | Slug trong `social.COMMUNITY_FANDOMS`, rỗng = không gán |
| `edited_at` | datetime | không | Rỗng/NULL = chưa từng sửa; chỉ đường sửa của chính chủ mới ghi |

Index mới: `fandom_created_idx` trên `(fandom_id, created_at)` — lọc bảng
tin theo fandom.

### 2.3 `comments` — thêm 1 thuộc tính

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `edited_at` | datetime | không | Cùng ngữ nghĩa với `posts.edited_at` |

(`spoiler` đã có sẵn từ trước — không đổi.)

### 2.4 `content_reports` — mở rộng enum

`target_kind` thêm giá trị `"user"` (giữ nguyên `"post"`, `"comment"`) — báo
cáo thẳng một người dùng, không gắn với một nội dung cụ thể. Đây là thay đổi
**enum**, không phải thuộc tính mới; Appwrite cho phép mở rộng danh sách giá
trị của một thuộc tính enum có sẵn mà không cần xoá/tạo lại.

### 2.5 Collection mới: `user_blocks`

| Thuộc tính | Kiểu | Bắt buộc |
|---|---|---|
| `block_id` | string(64) | có |
| `blocker_id` | string(64) | có |
| `blocked_id` | string(64) | có |
| `kind` | enum (`"block"`, `"mute"`) | có |
| `created_at` | datetime | có |

`block_id` là khoá **tất định** từ `(blocker_id, blocked_id, kind)` — xem
`social.block_key`. `"block"` là hai chiều (từ chối tương tác + ẩn nội dung
cả hai phía); `"mute"` là một chiều (chỉ ẩn nội dung khỏi người tắt tiếng).

Index: `blocker_created_idx (blocker_id, created_at)` — danh sách của chính
người chặn (`GET /api/me/blocks`); `blocked_kind_idx (blocked_id, kind)` và
`blocker_kind_idx (blocker_id, kind)` — tra "ai đã chặn mình"/kiểm tra hai
chiều mà không quét toàn bảng.

**Quyền document**: giống các bảng quan hệ khác (`user_follows`,
`post_likes`) — không cấp quyền đọc công khai cho client; mọi đường đọc hợp
lệ đi qua backend bằng API key.

## 3. Lệnh dry-run (KHÔNG chạy thật)

```bash
.venv\Scripts\python.exe -m scripts.setup_appwrite --dry-run
```

In ra đúng kế hoạch (collection/thuộc tính/index sẽ tạo hoặc đã có), không
ghi gì lên Appwrite. Chạy lệnh này TRƯỚC khi chạm vào bất kỳ môi trường thật
nào, và đối chiếu output với danh sách ở mục 2.

Chạy thật (cần `APPWRITE_SCHEMA_API_KEY`, KHÔNG phải khoá runtime của
backend — xem `AppwriteSettings.schema_api_key`):

```bash
.venv\Scripts\python.exe -m scripts.setup_appwrite
```

Script là **additive và idempotent** (đã dùng cho mọi migration V2/V4/V6
trước đây trong repo này): chạy lại nhiều lần không tạo trùng, không xoá gì.

## 4. Thứ tự triển khai

1. Merge code này với `FAS_SOCIAL_V1_SCHEMA` **chưa đặt** (mặc định `false`)
   — không ai thấy gì đổi, mọi request dùng field mới nhận 409 rõ ràng thay
   vì mất dữ liệu âm thầm.
2. Chạy `--dry-run` trên production, đối chiếu kế hoạch.
3. Chạy migration thật (mục 3, lệnh thứ hai).
4. Đối soát: mở Appwrite Console, xác nhận `profiles`/`posts`/`comments`/
   `content_reports` có đủ thuộc tính mới và collection `user_blocks` tồn
   tại với đúng index.
5. Đặt `FAS_SOCIAL_V1_SCHEMA=1` và khởi động lại tiến trình backend
   (`_attrs_cache` của `AppwriteMetadataStore` cache theo vòng đời tiến
   trình — đổi schema xong mà không restart thì tiến trình đang chạy vẫn
   không thấy thuộc tính mới, y hệt mọi migration trước đây trong repo này).

## 5. Rollback

Đặt lại `FAS_SOCIAL_V1_SCHEMA=0` (hoặc bỏ biến — mặc định là tắt) và khởi
động lại. Các thuộc tính/collection mới **được phép ở lại** trên Appwrite —
chúng chỉ là cột/collection thêm, không có gì đọc chúng khi cờ tắt, và
không thuộc tính nào bị xoá nên không mất dữ liệu đã ghi trước khi rollback
(người dùng chỉ tạm thời không thấy tính năng nữa, không mất bio/fandom/
banner họ đã lưu — khi bật lại cờ, dữ liệu đó hiện lại nguyên vẹn).

## 6. Khôi phục tiến (forward recovery)

Nếu migration chạy dở dang (vd mất kết nối giữa chừng): chạy lại
`python -m scripts.setup_appwrite` — additive/idempotent nên an toàn chạy
lại nhiều lần, script sẽ chỉ tạo nốt phần còn thiếu.

## 7. Chiều ĐỌC khi cờ tắt (bổ sung sau review)

Lọc field khi GHI (mục 1) chưa đủ: một truy vấn ĐỌC nhắc tới collection hay
thuộc tính chưa tồn tại cũng bị Appwrite từ chối. Khi `FAS_SOCIAL_V1_SCHEMA`
tắt, `SocialService` **không đọc** `user_blocks` (tập ẩn của bảng tin, kiểm
chặn khi theo dõi/thích/bình luận, `viewer_relation`) và **không truy vấn**
`posts.fandom_id` (bộ lọc fandom khi đó chỉ khớp theo truyện của fandom).
Khoá `capabilities` nào thiếu cũng bị coi là TẮT. Khoá bằng
`server/tests/test_social_play_v1_capability_off.py` (kho giả lập "chưa
migrate" ném lỗi nếu bị chạm) và `test_social_play_v1_security.py`.

## 8. Rủi ro còn mở — cần kiểm trên Appwrite THẬT trước khi bật cờ

- Truy vấn cursor dùng `or(lessThan(created_at), and(equal(created_at),
  lessThan(post_id)))` và `or(equal(fandom_id), equal(novel_id))` — mới chỉ
  kiểm qua `FakeAppwrite` trong bộ nhớ. Appwrite 1.9.6 (MongoDB) có thể đòi
  index hoặc xử lý `and` lồng trong `or` khác. Sau migration, chạy smoke:
  `GET /api/feed?scope=latest&limit=3` rồi lần theo `next_cursor` 2–3 trang,
  và `GET /api/feed?scope=latest&fandom=naruto`, TRƯỚC khi đặt cờ cho người
  dùng.
- Chặn/ẩn áp dụng cho bảng tin, bài đăng và bình luận bài đăng; CHƯA áp
  dụng cho bình luận chương/tập animation.

## 9. Thứ tự triển khai web và API

Render tắt `autoDeploy`, nên web có thể lên trước API. Web mới nhận ra phản
hồi dạng cũ của `/api/feed` (không có `scope`) và lùi về phân trang offset;
tab "Đang theo dõi" và chip fandom tự ẩn, URL lọc báo "Máy chủ chưa hỗ trợ bộ
lọc này" — đã kiểm bằng web mới + backend `origin/main` chạy cục bộ. Khuyến
nghị vẫn là: API trước, rồi migration, rồi cờ, rồi web.

## 10. Phạm vi KHÔNG đổi

- Không đổi tên, không đổi kiểu, không xoá thuộc tính nào đã có.
- Không đổi quyền document của các bảng đã có.
- `GET /api/feed` (không kèm `scope`) giữ nguyên hành vi/response cũ —
  client web hiện tại không cần biết gì về migration này.
