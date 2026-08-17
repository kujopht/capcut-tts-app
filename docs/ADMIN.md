# Khu quản trị

## 0. Ba mức quan tri (Admin Control Center V2, feature/admin-trusted-video-v2)

Từ V2, có **BA** mức thay vì một mức phẳng — vẫn cùng triết lý ở mục 1 (biến
môi trường, không phải cột dữ liệu), chỉ là **ba danh sách** thay vì một:

| Biến môi trường | Mức | Được làm gì |
|---|---|---|
| `FAS_OWNER_USER_IDS` | OWNER | Toàn quyền — bao gồm cài đặt hệ thống/hạ tầng/tài chính (vd công tắc khẩn cấp Image Studio) |
| `FAS_ADMIN_USER_IDS` | ADMIN | Người dùng/nội dung/phân tích/nguồn tin cậy YouTube — KHÔNG chạm hạ tầng/bí mật/tài chính |
| `FAS_MODERATOR_USER_IDS` | MODERATOR | Chỉ xem/xử lý báo cáo và kiểm duyệt nội dung |

Một `user_id` nằm trong nhiều danh sách cùng lúc (sai sót cấu hình) thì mức
**CAO NHẤT thắng** — không cộng dồn quyền. Xem `Settings.admin_role_of`.

Ba phụ thuộc FastAPI tương ứng, `server/main.py`:
- `admin_profile` — bất kỳ mức nào trong ba (giữ tên cũ, chỉ mở rộng định nghĩa).
- `admin_or_owner_profile` — ADMIN trở lên.
- `owner_profile` — CHỈ OWNER.

`/api/auth/me` trả thêm `admin_role` ("none"/"moderator"/"admin"/"owner") để
giao diện ẩn/hiện đúng mục — **chỉ là gợi ý hiển thị**, mọi route vẫn tự kiểm
lại qua ba phụ thuộc trên.

## 1. Ai là quản trị — và vì sao nó nằm ở biến môi trường

`FAS_ADMIN_USER_IDS` — danh sách `user_id`, ngăn cách bằng dấu phẩy. **Mặc định
rỗng: không ai là quản trị.**

Không phải một cột trong bảng `profiles`, và đó là quyết định trung tâm của cả
thiết kế:

1. **Không thể leo thang qua ứng dụng.** Nếu quyền quản trị là một trường dữ
   liệu thì bất kỳ lỗ hổng ghi nào — một route quên kiểm, một quyền document đặt
   sai — đều trở thành đường tự phong mình làm quản trị. Một biến môi trường thì
   không có API nào chạm tới được.
2. **Không cần migration.** Bật quyền không đổi một dòng dữ liệu nào, và tắt
   cũng vậy.
3. **Đổi danh sách là thao tác vận hành có chủ ý**, có dấu vết trong lịch sử cấu
   hình.

Đánh đổi: đổi quản trị phải khởi động lại tiến trình. Với một hệ thống có một
hoặc hai quản trị thì đó là cái giá đúng.

`/api/health` chỉ báo ra **số lượng** (`admin_count`), không bao giờ là danh
sách — nó là endpoint công khai, và lộ `user_id` của quản trị là chỉ đích.

## 2. Ba mức, ba mã

| Người gọi | Mã | Thân |
|---|---|---|
| Ẩn danh | **401** | `{"detail": "Cần đăng nhập."}` |
| Đã đăng nhập, không phải quản trị | **403** | `{"detail": "Khu vực quản trị."}` |
| Quản trị | **200** | dữ liệu |

403 là **403 rỗng** — không kèm số liệu nào. Một thông điệp lỗi có kèm "có 3 đơn
đang chờ" là rò rỉ dữ liệu qua đường báo lỗi.

Không trả 404 cho cả hai: giấu được sự tồn tại của khu quản trị, nhưng đổi lại
một người quản trị thật gõ nhầm tài khoản sẽ không hiểu vì sao không vào được.
Khu này không bị giấu, nó bị khoá.

Mọi route `/api/admin/*` đi qua **một** phụ thuộc `Depends(admin_profile)`.
`test_admin.py::test_moi_route_admin_deu_duoc_bao_ve` tự liệt kê các route rồi
kiểm từng cái — một route mới quên phụ thuộc sẽ làm bài đó đổ.

## 3. API

```
GET  /api/admin/overview
GET  /api/admin/author-applications?status_filter=&limit=&offset=
GET  /api/admin/author-applications/{user_id}
POST /api/admin/author-applications/{user_id}/approve   {note}
POST /api/admin/author-applications/{user_id}/reject    {note}   ← note BẮT BUỘC
GET  /api/admin/authors
POST /api/admin/authors/{user_id}/suspend               {note}
POST /api/admin/authors/{user_id}/restore               {note}
GET  /api/admin/users?q=            ← đường DUY NHẤT có email
GET  /api/admin/users/{user_id}
GET  /api/admin/novels?q=&state=    ← CHỈ ĐỌC
GET  /api/admin/events              ← CHỈ ĐỌC
```

Route **không lặp lại một dòng logic nghiệp vụ nào**: chúng gọi thẳng
`CreatorService`, tầng đã được kiểm thử từ trước.

**LỖI THỜI kể từ Admin Control Center V2** (`feature/admin-trusted-video-v2`,
đã hợp nhất vào `integration/pre-prod-v1`): danh sách trên chỉ là API GỐC
(V1). V2 thêm ~40 route `/api/admin/*` KHÔNG liệt kê ở đây — quản lý tài
khoản (suspend/unsuspend/sessions), kiểm duyệt Animation (series/tập),
Trusted Video Sources (nguồn/ánh xạ/hàng đợi nhập/WebSub), bài đăng/bình
luận/báo cáo, phân tích (`analytics`), Image Studio kill-switch, thống kê
dịch. Danh sách đầy đủ: `grep -n '@app\.\(get\|post\|patch\|delete\)("/api/admin' server/main.py`
hoặc mục 9 của `docs/handoffs/admin-trusted-video-v2-handoff.md`.

## 4. Treo tác giả làm gì và KHÔNG làm gì

| | |
|---|---|
| **Chặn** | xuất bản truyện **mới** |
| **Không chạm** | truyện đã xuất bản — vẫn công khai, vẫn nghe được |
| **Không chạm** | bản nháp, chương, audio, job — không xoá gì cả |

Một tác giả bị treo vẫn còn độc giả. Rút truyện của họ khỏi tay người đọc là một
hình phạt đánh vào người khác. Giao diện nói rõ điều này ở **cả hai** chỗ: dưới
bảng, và trong hộp xác nhận.

## 5. Nhật ký kiểm duyệt

Bảng `moderation_events`. **Chỉ thêm** — không tầng nào có đường sửa hay xoá,
và một bài test kiểm rằng route `events` chỉ có `GET`.

Ghi: `action`, `target_user_id`, `actor_id`, `actor_role`, `target_type`,
`target_id`, `note`, `metadata`, `created_at`.

Bốn trường **MỚI từ V2** (Admin Control Center V2):
- `actor_role` — mức của actor TẠI THỜI ĐIỂM hành động ("owner"/"admin"/
  "moderator") — mức có thể đổi sau (sửa biến môi trường), ghi lại để nhật ký
  không kể sai "ai có quyền gì lúc đó".
- `target_type`/`target_id` — dùng khi đối tượng bị tác động KHÔNG PHẢI là
  user (vd `"animation_series"`, `"trusted_source"`) — rỗng nghĩa là đối
  tượng là user, dùng `target_user_id` như trước.
- `metadata` — JSON AN TOÀN, KHÔNG BAO GIỜ chứa API key/OAuth token/BYOP
  token/cookie/session secret/khoá mã hoá.

`action` là Appwrite **enum** — thêm hành động mới phải MỞ RỘNG danh sách giá
trị trong `scripts/setup_appwrite.py` (script tự phát hiện và PATCH mở rộng,
không bao giờ thu hẹp — xem `_ensure_enum`), không tự ý ghi một chuỗi ngoài
danh sách.

`created_at` dùng **micro giây**, không dùng `now_iso()` (cắt ở giây). Một quản
trị bấm Duyệt rồi Treo trong cùng một giây sẽ tạo hai bản ghi cùng mốc, và nhật
ký có thể kể ngược câu chuyện — "phục hồi" hiện trước "treo". Lỗi này đã đổ ra
trong test trước khi ai kịp đọc nhầm.

Không bao giờ ra API công khai: `note`/`metadata` có thể chứa nhận xét nội bộ,
và `actor_id` cho biết ai đang làm quản trị.

## 6. Schema `moderation_events` — trạng thái áp dụng

**LỖI THỜI**: tiêu đề gốc "CHƯA áp lên production" và bảng dưới đây chỉ còn
đúng ở tầng Appwrite Cloud production (chưa chạm tới, xem mục 8). Trên
Appwrite tự lưu trữ dev (`appwrite-dev.fanfic.world`) schema này **ĐÃ áp
dụng và đã smoke test thật** — xem `docs/DEV_SELFHOST_APPWRITE.md`. Bảng
dưới cũng chỉ còn là bản GỐC (V1): `action` giờ là enum mở rộng nhiều lần
qua Admin Control Center V2 (author_*/post_*/comment_*/report_*/user_*/
content_*/trusted_source_*/youtube_mapping_*/auto_import_*, xem
`scripts/setup_appwrite.py`), và đã thêm bốn thuộc tính `actor_role`,
`target_type`, `target_id`, `metadata` (mục 5 ở trên). `_ensure_enum()` chỉ
MỞ RỘNG, không bao giờ thu hẹp danh sách giá trị.

| Thuộc tính | Kiểu |
|---|---|
| `event_id` | string(64), bắt buộc |
| `action` | enum(author_approved/rejected/suspended/restored) — **bản GỐC, xem ghi chú trên** |
| `target_user_id` | string(64), bắt buộc |
| `actor_id` | string(64) |
| `note` | string(1000) |
| `created_at` | datetime, bắt buộc |

Index: `target_created_idx`, `created_idx`.

## 7. Tạo quản trị đầu tiên cho production — **chưa thực hiện**

Từ Admin Control Center V2 có BA biến, không chỉ một (xem mục 0):
`FAS_OWNER_USER_IDS`, `FAS_ADMIN_USER_IDS`, `FAS_MODERATOR_USER_IDS`. Các
bước dưới đây minh hoạ với `FAS_ADMIN_USER_IDS`, áp dụng tương tự cho hai
biến còn lại tuỳ mức muốn cấp.

```
1. Đăng nhập bằng tài khoản thật, gọi GET /api/auth/me, chép `user_id`.
2. Đặt biến môi trường trên Render:
       FAS_ADMIN_USER_IDS=usr_xxxxxxxxxxxx
   (nhiều người thì ngăn bằng dấu phẩy, không có khoảng trắng)
3. Khởi động lại service.
4. Kiểm: GET /api/health  →  admin_count = 1
5. Kiểm: GET /api/admin/overview bằng token của tài khoản đó  →  200
6. Kiểm bằng một tài khoản thường  →  403
```

**Không bao giờ** đặt `user_id` của quản trị vào mã nguồn, vào `.env` được
commit, hay vào bất kỳ phản hồi API công khai nào.

Trước khi mở khu quản trị cho nhiều người, cần thêm: xác thực hai bước cho các
tài khoản đó, và giới hạn nhịp gọi trên `/api/admin/*`.

## 8. Việc còn lại

**Gỡ truyện xuống (takedown) — chỉ đúng cho TRUYỆN (`novels`).** Chưa có, và
khu duyệt truyện **chỉ để xem** (`GET /api/admin/novels`, không có route
sửa). Lưu ý: Admin Control Center V2 ĐÃ thêm gỡ/phục hồi cho **Animation**
(series/tập, trục `moderation_state` riêng, KHÔNG đụng `state` xuất bản của
chủ sở hữu) qua `/api/admin/animation/{series|episodes}/*` — xem
`docs/handoffs/admin-trusted-video-v2-handoff.md` mục 4c. Truyện (novel)
vẫn CHƯA có cơ chế tương đương. Đặt một nút xoá lên một luồng chưa thiết kế
là cách nhanh nhất để mất nội dung của người khác. Những thứ cần có
**trước** cái nút đó:

- một trạng thái `removed` **tách khỏi** `draft` — để tác giả biết truyện bị gỡ
  chứ không phải họ tự hạ xuống;
- một bản ghi lý do, hiện cho tác giả;
- một đường khiếu nại;
- một cách hoàn tác.

**Xoá tài khoản.** Chưa có, và cố ý: chưa có luồng an toàn nào cho việc quyết
định số phận truyện, audio và lượt nghe của người bị xoá.

**Tầng lưu trữ Appwrite — ĐÃ XONG, không còn là "việc còn lại".** Ghi chú cũ ở
đây ("các phương thức V2 chỉ hiện thực cho kho mock, `/api/admin/*` trả 500
trên Appwrite") đã LỖI THỜI — kiểm tra lại 2026-08-16 (feature/
admin-trusted-video-v2, Phase 0 audit) thấy `get_application`/`get_stats`/
`record_event`/`search_profiles` đều đã có bản Appwrite đầy đủ trong
`server/appwrite_store.py`/`server/appwrite_adapter.py`. Đã **smoke test
THẬT** trên Appwrite tự lưu trữ dev (`appwrite-dev.fanfic.world`):
`/api/admin/overview`, `/api/admin/users`, `/api/admin/events` đều trả 200,
và một lượt duyệt tác giả thật ghi đúng `actor_role: "owner"` vào
`moderation_events`. Nếu gặp lại lỗi 500 ở nhánh Appwrite, đó là một hồi quy
MỚI, không phải khoảng trống đã biết này.
