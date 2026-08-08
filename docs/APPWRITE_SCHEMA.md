# Schema Appwrite

Tài liệu tạo database cho Fanfic Audio Studio. Tất cả nằm trong **một database**
(id đặt ở `APPWRITE_DATABASE_ID`).

## Nguyên tắc phân quyền

**Client chỉ được ĐỌC. Mọi thao tác ghi đi qua backend bằng API key.**

- Mọi collection bật `documentSecurity: true` và dùng **document-level permissions**.
- Quyền ở **mức collection là rỗng** — không cấp gì cho client. Quyền mức
  collection áp dụng **thêm vào** quyền document, nên một quyền rộng ở đây sẽ
  vô hiệu hoá toàn bộ mô hình phân quyền theo document.
- Khi tạo document, backend chỉ gán `read("user:<id>")` cho chủ sở hữu.
- Truyện đã xuất bản thêm `read("any")` để thư viện công khai đọc được.
- **Không bao giờ cấp `create` / `update` / `delete` cho client** — kể cả cho
  chính chủ sở hữu.
- **API key chỉ ở backend.** Frontend không bao giờ nhận key. API key bỏ qua
  document permission nên backend vẫn ghi được bình thường.

### Vì sao client không được quyền ghi

Người dùng nắm session/JWT hợp lệ **có thể gọi thẳng Appwrite API ngoài giao
diện**. Không được dựa vào việc "trình duyệt hiện không gọi Appwrite". Các
collection đều chứa trường do **server** quyết định:

| Collection | Trường server-authoritative | Nếu client ghi được thì sao |
|---|---|---|
| `profiles` | `tier`, `listened_minutes`, `tts_characters_used` | Tự nâng gói, tự xoá quota đã dùng |
| `novels` | `state` | Tự xuất bản, hoặc đổi `owner_id` |
| `tts_jobs` | `status`, `output_key` | Tự đánh dấu hoàn tất, trỏ sang file người khác |
| `audio_tracks` | `object_key` | **Đổi sang key của người khác → `/api/audio/{chapter}` phục vụ audio của họ, vượt qua `_may_listen()`** |

Nếu sau này cần cho sửa tên hiển thị hoặc avatar, phải làm qua **route của
backend với danh sách trường được phép** — không bao giờ mở quyền ghi thẳng.

## Collections

### `profiles`
Khoá document = `user_id` của Appwrite.

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `user_id` | string(64) | ✔ | trùng `$id` |
| `email` | email | ✔ | |
| `display_name` | string(120) | | |
| `tier` | enum | ✔ | `free`, `listener_pro`, `creator_pro`, `ultra` |
| `listened_minutes` | integer | | mặc định 0 |
| `tts_characters_used` | integer | | mặc định 0 |
| `created_at` | datetime | ✔ | |

Index: `email` (unique).

### `novels`

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `novel_id` | string(64) | ✔ | trùng `$id` |
| `owner_id` | string(64) | ✔ | |
| `title` | string(200) | ✔ | |
| `description` | string(2000) | | |
| `cover_key` | string(512) | | **object key** trong R2, không phải binary |
| `state` | enum | ✔ | `draft`, `published`, `archived` |
| `tags` | string[] | | |
| `created_at` / `updated_at` | datetime | ✔ | |

Index: `owner_id`; `state`; tổ hợp `state,created_at` (sắp xếp thư viện).

### `chapters`

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `chapter_id` | string(64) | ✔ | trùng `$id` |
| `novel_id` | string(64) | ✔ | |
| `owner_id` | string(64) | ✔ | |
| `title` | string(200) | ✔ | |
| `content` | string(1000000) | | nội dung chương |
| `order_index` | integer | ✔ | |
| `state` | enum | ✔ | như `novels` |
| `created_at` / `updated_at` | datetime | ✔ | |

Index: `novel_id`; tổ hợp `novel_id,order_index`; `owner_id`.

### `tts_jobs`

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `job_id` | string(64) | ✔ | trùng `$id` |
| `owner_id` | string(64) | ✔ | |
| `chapter_id` | string(64) | ✔ | |
| `voice_id` | string(128) | ✔ | dạng `provider:khoá` |
| `content_hash` | string(64) | ✔ | dấu vân tay idempotency |
| `status` | enum | ✔ | `pending`, `running`, `completed`, `failed` |
| `output_key` | string(512) | | object key của audio |
| `error_kind` | string(64) | | |
| `error_message` | string(1000) | | |
| `total_parts` / `done_parts` | integer | | |
| `rate` | string(16) | | |
| `chunk_chars` | integer | | |
| `created_at` | datetime | ✔ | |
| `started_at` / `finished_at` | datetime | | |
| `lease_expires_at` | datetime | | lease của worker đang giữ job |
| `lease_owner` | string(64) | | id worker đang giữ |
| `attempts` | integer | | **fencing token**, tăng mỗi lần claim |

Index **quan trọng**: tổ hợp `owner_id,chapter_id,content_hash` — đây là index
phục vụ idempotency. Thêm `status` để lọc job đang chạy, và `status_lease_idx`
(`status`, `lease_expires_at`) cho bộ quét job kẹt.

Ba trường lease đều **không bắt buộc**, nên dòng job cũ thiếu chúng vẫn đọc được.

### `job_claims`

Sổ ghi chép của bộ điều phối, **không chứa dữ liệu người dùng**. Nó tồn tại chỉ
để biến claim thành thao tác nguyên tử: `$id` là `"{job_id}-{attempt}"` nên hai
worker cùng nhắm một `attempt` sẽ đụng uniqueness ngay trong transaction.

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `job_id` | string(64) | ✔ | |
| `attempt` | integer | ✔ | trùng `tts_jobs.attempts` |
| `worker_id` | string(64) | ✔ | |
| `created_at` | datetime | ✔ | |

Index: `job_idx` trên `job_id`.

**Rollback:** xoá collection này và ba trường lease ở trên. Không cần sửa mã.

### `audio_tracks`

| Thuộc tính | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `track_id` | string(64) | ✔ | trùng `$id` |
| `chapter_id` | string(64) | ✔ | |
| `owner_id` | string(64) | ✔ | |
| `voice_id` | string(128) | ✔ | |
| `object_key` | string(512) | ✔ | **chỉ key**, không lưu binary |
| `content_hash` | string(64) | ✔ | |
| `duration_seconds` | double | | |
| `size_bytes` | integer | | |
| `created_at` | datetime | ✔ | |

Index: `chapter_id`; tổ hợp `chapter_id,created_at`.

## Bật Appwrite

Điền **cả bốn** biến trong `server/.env` rồi khởi động lại backend:

```
APPWRITE_ENDPOINT=https://<host>/v1
APPWRITE_PROJECT_ID=...
APPWRITE_API_KEY=...
APPWRITE_DATABASE_ID=...
```

Thiếu bất kỳ biến nào thì hệ thống dùng mock. Điền đủ nhưng sai thì backend
**báo lỗi rõ** (`AppwriteConfigError`) thay vì âm thầm quay về mock.

## Giới hạn hiện tại

- Adapter Appwrite mới phủ Auth và `profiles`. Novels/chapters/jobs/tracks vẫn
  chạy qua `MockMetadataStore` — cần bổ sung `AppwriteMetadataStore` dùng đúng
  schema trên.
- Chưa có migration script; hiện tạo collection bằng tay theo bảng trên hoặc
  qua Appwrite CLI.
