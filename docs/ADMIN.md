# Khu quản trị

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

Ghi: `action`, `target_user_id`, `actor_id`, `note`, `created_at`.

`created_at` dùng **micro giây**, không dùng `now_iso()` (cắt ở giây). Một quản
trị bấm Duyệt rồi Treo trong cùng một giây sẽ tạo hai bản ghi cùng mốc, và nhật
ký có thể kể ngược câu chuyện — "phục hồi" hiện trước "treo". Lỗi này đã đổ ra
trong test trước khi ai kịp đọc nhầm.

Không bao giờ ra API công khai: `note` có thể chứa nhận xét nội bộ, và
`actor_id` cho biết ai đang làm quản trị.

## 6. Schema cần thêm — **CHƯA áp lên production**

`scripts/setup_appwrite.py` đã có định nghĩa `moderation_events`:

| Thuộc tính | Kiểu |
|---|---|
| `event_id` | string(64), bắt buộc |
| `action` | enum(author_approved/rejected/suspended/restored) |
| `target_user_id` | string(64), bắt buộc |
| `actor_id` | string(64) |
| `note` | string(1000) |
| `created_at` | datetime, bắt buộc |

Index: `target_created_idx`, `created_idx`.

## 7. Tạo quản trị đầu tiên cho production — **chưa thực hiện**

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

**Gỡ truyện xuống (takedown).** Chưa có, và khu duyệt truyện **chỉ để xem**. Đặt
một nút xoá lên một luồng chưa thiết kế là cách nhanh nhất để mất nội dung của
người khác. Những thứ cần có **trước** cái nút đó:

- một trạng thái `removed` **tách khỏi** `draft` — để tác giả biết truyện bị gỡ
  chứ không phải họ tự hạ xuống;
- một bản ghi lý do, hiện cho tác giả;
- một đường khiếu nại;
- một cách hoàn tác.

**Xoá tài khoản.** Chưa có, và cố ý: chưa có luồng an toàn nào cho việc quyết
định số phận truyện, audio và lượt nghe của người bị xoá.

**Tầng lưu trữ Appwrite.** Các phương thức V2 (`get_application`, `get_stats`,
`record_event`, `search_profiles`…) mới chỉ hiện thực cho kho **mock**. Ở chế độ
Appwrite, các endpoint V2 và `/api/admin/*` sẽ trả 500 cho tới khi có đợt hiện
thực đó. Các luồng cũ không bị ảnh hưởng.
