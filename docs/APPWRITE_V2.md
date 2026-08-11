# Schema Appwrite cho V2 + Admin

Bảng thẩm quyền duy nhất cho mọi dữ liệu V2. Nguồn máy đọc được là
`scripts/setup_appwrite.py::SCHEMA` và `server/appwrite_store.py::PERSISTED_FIELDS`
— hai chỗ đó được một bài test đối soát với nhau và với `to_dict()` của domain.

**Chưa áp lên production.**

## 1. `profiles` — ba cột thêm

| Cột | Kiểu | Bắt buộc | Mặc định | Index | Công khai? |
|---|---|---|---|---|---|
| `username` | string(24) | không | `""` | `username_unique` (unique) | **có** (đã chuẩn hoá) |
| `bio` | string(400) | không | `""` | — | **có** |
| `author_status` | enum(none/pending/approved/rejected/suspended) | không | `none` | — | **KHÔNG** — chỉ chiếu xuống một bit `is_author` |

Quyền hàng: `read("user:{user_id}")` — **không đổi**. Không cấp `update`/`delete`
cho client; mọi ghi đi qua backend bằng API key.

## 2. `author_applications`

`rowId` = **`user_id`** → một đơn mỗi người, nộp lại là ghi đè.

| Cột | Kiểu | Bắt buộc | Công khai? |
|---|---|---|---|
| `application_id` | string(64) | có | không |
| `user_id` | string(64) | có | không |
| `pen_name` | string(60) | có | — |
| `bio` | string(400) | không | — |
| `genres` | string(40)[] | không | — |
| `intro` | string(1000) | không | không |
| `accepted_rules` | boolean | không | không |
| `status` | enum(5 giá trị) | có | **không** |
| `reviewer_note` | string(1000) | không | **chỉ chính chủ đơn** |
| `attempts` | integer | không | không |
| `created_at` / `updated_at` | datetime | có | không |
| `decided_at` | datetime | không | không |

Index: `user_unique` (unique), `status_created_idx`.
Quyền: `read("user:{user_id}")`.

## 3. `author_stats`

`rowId` = **`user_id`**.

| Cột | Kiểu | Công khai? |
|---|---|---|
| `user_id` | string(64), bắt buộc | không |
| `qualified_listens` | integer | **có** (qua `rank`) |
| `published_novels` | integer | **có** |
| `updated_at` | datetime, bắt buộc | không |

Index: `user_unique` (unique). Quyền: `read("user:{user_id}")`.

## 4. `listen_credits`

`rowId` = **khoá tất định** `hash(listener_id, chapter_id, ngày UTC)` —
`creator.credit_key()`. **Đây là cơ chế chống farm**, không phải một id ngẫu nhiên.

| Cột | Kiểu | Công khai? |
|---|---|---|
| `credit_id` | string(64), bắt buộc | không |
| `listener_id` | string(64), bắt buộc | **không** |
| `author_id` | string(64), bắt buộc | không |
| `chapter_id` | string(64), bắt buộc | không |
| `day_bucket` | integer | không |
| `listened_seconds` | double | không |
| `created_at` | datetime, bắt buộc | không |

Index: `listener_chapter_idx`, `author_idx`. Quyền: `read("user:{listener_id}")`.

## 5. `moderation_events`

`rowId` = `event_id`. **Chỉ thêm.**

| Cột | Kiểu | Công khai? |
|---|---|---|
| `event_id` | string(64), bắt buộc | không |
| `action` | enum(author_approved/rejected/suspended/restored) | không |
| `target_user_id` | string(64), bắt buộc | không |
| `actor_id` | string(64) | **không bao giờ** |
| `note` | string(1000) | **không bao giờ** |
| `created_at` | datetime, bắt buộc (micro giây) | không |

Index: `target_created_idx`, `created_idx`.

**Quyền: rỗng.** Không client nào đọc trực tiếp được — hàng này chứa ghi chú nội
bộ và danh tính quản trị. Mọi đường đọc hợp lệ đi qua backend bằng API key.
`test_appwrite_v2_contract.py::QuyenHangTest` giữ điều này.

## 6. Chính sách công khai / riêng tư

Một hàm duy nhất quyết định: `creator.public_profile()` — **danh sách CHO PHÉP**.

**Không bao giờ ra API công khai:** `email`, `tier`, `listened_minutes`,
`tts_characters_used`, `author_status`, `reviewer_note`, `actor_id`, toàn bộ
`listen_credits` và `moderation_events`.

`email` chỉ xuất hiện dưới `/api/admin/*`. Một bài test đối chiếu hai đường cạnh
nhau, và một bài khác kiểm `PublicProfile` (TypeScript) không có trường đó.

## 7. Quyền quản trị

`FAS_ADMIN_USER_IDS` — biến môi trường, **không phải dữ liệu**. Không có
migration nào cho nó. Chi tiết ở `docs/ADMIN.md` §1.

## 8. Lượt nghe: tính nguyên tử và giới hạn còn lại

| Bước | Cơ chế | Nguyên tử? |
|---|---|---|
| Tạo lượt tính | `rowId` tất định, Appwrite từ chối hàng thứ hai | **có** |
| Cộng vào `author_stats` | đọc-rồi-ghi | **không** |

Điều **quan trọng** — không tạo hai lượt tính cho cùng người nghe + chương +
ngày — được chặn tuyệt đối. Thứ có thể mất là một đơn vị trong bản tổng hợp khi
hai lượt tính cho **cùng một tác giả** rơi vào cùng phần giây.

Appwrite không có phép cộng nguyên tử, và transaction cũng không cứu được vì giá
trị mới phải tính từ giá trị cũ. `listen_credits` là nguồn sự thật, và
`CreatorService.recount_listens()` dựng lại bản tổng hợp — chạy lại bao nhiêu lần
cũng được.

Một lỗi mạng khi tạo lượt tính cũng trả `False` (bỏ qua) thay vì thử lại: với một
hệ thống uy tín, **thiếu một lần an hơn thừa một lần**.

## 9. Username: tính duy nhất

Ba lớp, và chỉ lớp cuối là ràng buộc thật:

1. chuẩn hoá (bỏ dấu, hạ chữ thường) — `Kẻ Dệt Mộng` và `ke-det-mong` chạm cùng ô;
2. kiểm ở tầng service — để trả thông báo đọc được (409);
3. **index `username_unique` của Appwrite** — thứ duy nhất chặn được một cuộc đua.

## 10. Sẵn sàng theo tính năng

`GET /api/ready` báo riêng 5 phụ thuộc V2: `tac_gia`, `uy_tin`, `luot_nghe`,
`nhat_ky`, `ho_so_cong_khai`.

Thiếu chúng **không** làm dịch vụ trả 503 — đọc/nghe/tạo audio vẫn chạy — nhưng
mỗi cái báo kèm `ghi_chu: "Cần chạy python -m scripts.setup_appwrite"`. Trước đây
thiếu bảng là một lỗi 500 chung và người vận hành không biết nguyên nhân là "chưa
migrate" hay "code hỏng".

## 11. Hạn chế của bộ test hợp đồng

`test_appwrite_v2_contract.py` chạy cùng một kịch bản trên cả hai kho, với
Appwrite được thay bằng một bản giả lập REST trong bộ nhớ. Bản giả lập **có**
cưỡng chế tính duy nhất của `rowId` và trả `total` độc lập với `limit` — hai hành
vi mà mã nguồn dựa vào.

Nó **không** mô phỏng: độ trễ mạng, phân trang 25 hàng mặc định của Appwrite,
hành vi chính xác của `contains` với tiếng Việt có dấu, và các lỗi 5xx. Những thứ
đó chỉ kiểm được bằng một lần chạy thật trên staging.
