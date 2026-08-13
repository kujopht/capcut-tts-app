# Tác giả, hạng tác giả và lượt nghe hợp lệ

Tài liệu này mô tả ba khái niệm **khác nhau** mà giao diện và backend phải luôn
phân biệt, kế hoạch migration, và những việc còn để lại.

## 1. Ba khái niệm, đừng gộp

| Khái niệm | Là gì | Ai quyết định | Hiện ở đâu |
|---|---|---|---|
| **Người dùng** | ai cũng có: đọc, nghe, tạo bản nháp | tự đăng ký | mọi nơi |
| **Trạng thái tác giả** | được phép **xuất bản công khai** hay không | người duyệt | huy hiệu `Tác giả` |
| **Hạng tác giả** | uy tín, tính từ số lượt nghe hợp lệ | máy chủ tính | huy hiệu hạng |

Một tác giả hạng cao vẫn có thể bị treo. Một tác giả mới được duyệt vẫn ở hạng
thấp nhất. **Dùng hạng để ngụ ý "đã được kiểm duyệt" là sai** — giao diện vẽ hai
thứ bằng hai ngôn ngữ thị giác khác nhau, và `docs` này là chỗ ghi lại lý do.

## 2. Trạng thái tác giả

```
none ──gửi đơn──> pending ──duyệt──> approved ──treo──> suspended
                     │                   ▲                  │
                     └──từ chối──> rejected                  │
                                      │                      │
                                      └──gửi lại──> pending   └──phục hồi──> approved
```

Bảng chuyển trạng thái là **nguồn sự thật duy nhất**:
`server/creator.py::TRANSITIONS`.

**Không có bước `none → approved`.** Mọi tác giả đều đi qua một bản ghi đơn, kể
cả khi được grandfather — migration tạo đơn với trạng thái `approved` kèm ghi chú,
chứ không nhảy bước. Nhờ vậy lịch sử luôn giải thích được câu hỏi "vì sao người
này được xuất bản".

Chờ nộp lại sau khi bị từ chối: **3 ngày** (`RESUBMIT_COOLDOWN`).

### Bị treo thì truyện cũ vẫn công khai

Treo chỉ chặn xuất bản **mới**. Một tác giả bị treo vẫn còn độc giả, và rút truyện
của họ khỏi tay người đọc là một hình phạt đánh vào người khác.

## 3. Hạng tác giả

Toàn bộ định nghĩa nằm ở **một chỗ**: `server/creator.py::RANK_TIERS`.

| Khoá | Tên | Lượt nghe hợp lệ tối thiểu | Bậc |
|---|---|---|---|
| `tan_but` | Tân Bút | 0 | 1 |
| `nguoi_ke_chuyen` | Người Kể Chuyện | 50 | 2 |
| `ke_det_mong` | Kẻ Dệt Mộng | 250 | 3 |
| `bien_nien_su_gia` | Biên Niên Sử Gia | 1 000 | 4 |
| `huyen_thoai_di_gioi` | Huyền Thoại Dị Giới | 5 000 | 5 |
| `than_but` | Thần Bút | 20 000 | 6 |

Ngưỡng ở trên là **ngưỡng cho phát triển**: đủ thấp để dữ liệu mock hiện được cả
sáu bậc. Trước khi mở cho người thật, xem lại bằng số liệu thật.

`GET /api/creator/ranks` trả cả bảng, để giao diện vẽ thang bậc mà **không nhúng
ngưỡng vào code frontend** — một bản frontend cũ đang chạy trong tab của ai đó
không được vẽ một hạng khác với hạng máy chủ công nhận.

Khoá (`key`) **không bao giờ đổi**, kể cả khi đổi tên hiển thị: đổi khoá là làm
hỏng mọi ảnh chụp, mọi test, và huy hiệu của mọi tác giả cùng lúc.

## 4. Lượt nghe hợp lệ (V1)

`server/creator.py::evaluate_listen` — hàm thuần, bốn phép kiểm theo thứ tự:

1. **Phải đăng nhập.** V1 không đếm khách ẩn danh. Đếm được thì cần một cách nhận
   diện phiên mà không lấn vào quyền riêng tư; bỏ qua hẳn an hơn là đếm bừa rồi
   phải đi dọn.
2. **Không tính khi tác giả tự nghe chương của mình.** Kiểm **trước** phép kiểm độ
   dài: nếu kiểm độ dài trước, một tác giả nghe 2 giây sẽ nhận mã "chưa đủ lâu" —
   một thông điệp gợi ý rằng nghe lâu hơn thì sẽ được tính.
3. **Phải nghe đủ lâu.** `30 giây`, hoặc `75% độ dài` với chương ngắn hơn 40 giây.
   Không biết độ dài → quay về 30 giây (thà khó tính hơn là tính sai).
4. **Không tính lại trong 24 giờ** cho cùng người nghe + cùng chương.

Độ dài audio lấy từ **track ở máy chủ**, không từ client: để client tự khai độ dài
là mở một cách hạ ngưỡng xuống còn vài giây.

`listened_seconds` do trình duyệt gửi nên **không được tin**. Một client nói dối
"tôi nghe 9999 giây" cũng chỉ đổi được **một** lần tính mỗi 24 giờ cho mỗi chương
— đó là trần mà hệ thống chấp nhận ở V1.

### Chống farm: hai lớp

| Lớp | Cơ chế | Chặn được gì |
|---|---|---|
| Đọc | truy vấn lượt tính gần nhất của (người nghe, chương), so với 24h | bấm Phát lặp lại |
| Ghi | `rowId` **tất định** = hash(người nghe, chương, ngày UTC) | hai request đồng thời |

Lớp thứ hai là thứ chặn được một cuộc đua: hai request cùng lúc đều đọc thấy "chưa
có" rồi cùng ghi, và khoá tất định biến bước ghi thứ hai thành một xung đột. Trường
hợp xấu nhất của một cuộc đua là **một** lần tính, không phải hai. Cùng kỹ thuật
với `job_locks` — xem `server/creator.py::credit_key`.

**Không fingerprint người dùng.** Không thu IP, không canvas fingerprint, không
device id.

### Cộng dồn thay vì đếm lại

`author_stats.qualified_listens` được **cộng thêm một** mỗi khi có một lượt nghe
hợp lệ. Đếm lại từ bảng sự kiện cho mỗi lần hiện một huy hiệu là một phép quét
toàn bảng; một trang tìm kiếm hiện mười tác giả sẽ thành mười phép quét.

Đánh đổi: bản tổng hợp có thể **lệch** nếu một bước cộng bị mất (lỗi mạng giữa hai
lệnh). `listen_credits` là nguồn sự thật, và `CreatorService.recount_listens()`
dựng lại. Chạy lại bao nhiêu lần cũng được.

## 5. Danh tính công khai

`username` là bước người dùng **tự chọn**. Chưa chọn thì **chưa có trang công
khai** — không tự gán cho họ một cái tên lấy từ email. Phần trước dấu `@` là dữ
liệu riêng tư bị biến thành danh tính công khai vĩnh viễn; người đăng ký bằng
`ten.thatcuatoi.1998@gmail.com` không hề đồng ý cho cả thế giới thấy chuỗi đó.

- Chuẩn hoá: bỏ dấu, hạ chữ thường, dấu cách → gạch ngang. `Kẻ Dệt Mộng` và
  `ke-det-mong` chạm vào **cùng một ô**.
- Độ dài 3–24, chỉ `[a-z0-9_-]`.
- Tên bị giữ lại: đường dẫn thật của site, và các tên ngụ ý quyền hạn (`admin`,
  `support`, `official`…).
- Tính duy nhất được đảm bảo bằng **index `unique` của Appwrite**, không chỉ bằng
  phép kiểm ở tầng service.

### Trường công khai là danh sách CHO PHÉP

`server/creator.py::public_profile` liệt kê những gì **được** ra ngoài, không liệt
kê những gì bị loại. Một ngày nào đó ai thêm `phone` vào profile, và một hàm "loại
bỏ email" sẽ cho nó ra ngoài mà không ai kịp nhận ra.

**Không bao giờ ra ngoài:** email, tier, quota đã dùng, và `author_status`. Trạng
thái duyệt là thông tin **moderation** — biết ai đang bị treo hay bị từ chối không
phải việc của người xem trang. Chỉ **một bit** lọt ra: `is_author`.

## 6. Kế hoạch migration — CHƯA áp lên production

Không một dòng nào trong đợt này được áp lên production. Dưới đây là kế hoạch
chính xác.

### 6.1. Schema

`scripts/setup_appwrite.py` đã có định nghĩa (an toàn khi chạy lại, bỏ qua cái đã
có). Xem trước bằng `--dry-run`.

**Thêm vào `profiles`:**

| Thuộc tính | Kiểu | Bắt buộc |
|---|---|---|
| `username` | string(24) | không |
| `bio` | string(400) | không |
| `author_status` | enum(none/pending/approved/rejected/suspended) | không |

Index mới: `username_unique` (unique) trên `username`.

**Ba collection mới:** `author_applications`, `author_stats`, `listen_credits`.
Chi tiết ở `SCHEMA` trong script.

### 6.2. Mã nguồn chịu được việc schema chưa có

`AppwriteIdentityAdapter` hỏi Appwrite xem `profiles` **thực sự** có thuộc tính nào
rồi mới ghi (`_writable_profile`). Triển khai code trước schema thì chỉ **mất tính
năng**, không làm vỡ đường đăng ký. Cùng kỹ thuật với `_supported_fields` ở
`appwrite_store.py`, và cùng lý do: một thuộc tính chưa tồn tại làm Appwrite từ
chối **cả** document.

### 6.3. Thứ tự bắt buộc

```
1. triển khai mã nguồn          (FAS_AUTHOR_GATE tắt — không ai thấy gì đổi)
2. python -m scripts.setup_appwrite
3. python -m scripts.grandfather_authors          (chạy thử, không ghi gì)
4. python -m scripts.grandfather_authors --apply
5. đối soát vài hồ sơ bằng tay
6. đặt FAS_AUTHOR_GATE=1
```

**Bước 3–4 không được bỏ.** Bật cổng trước khi grandfather là khoá toàn bộ tác giả
hiện có ra khỏi chính công việc của họ. `scripts/grandfather_authors.py` mặc định
là chế thử và không ghi một byte nào nếu thiếu `--apply`.

Quy tắc grandfather: ai đang sở hữu **ít nhất một** truyện `published` thì thành
`approved`, kèm bản ghi đơn ghi rõ là công nhận tự động. Người đang bị `suspended`
**không bao giờ** bị lật lại.

## 7. Việc còn lại

### 7.1. Trang quản trị — CHƯA làm, và cố ý

Dự án **chưa có cơ chế phân quyền quản trị**: không vai trò, không bảng admin,
không xác thực hai bước. Mở một endpoint duyệt mà không có cái đó là **tạo một cái
cổng** — bất kỳ ai đoán được đường dẫn đều tự phong mình làm tác giả.

Nên các hàm duyệt tồn tại ở `CreatorService`, được kiểm thử đầy đủ, và **không một
route HTTP nào gọi chúng**:

| Hàm | Việc |
|---|---|
| `pending_applications(limit, offset)` | liệt kê đơn đang chờ, cũ nhất trước |
| `approve(user_id, note)` | duyệt |
| `reject(user_id, note)` | từ chối (**bắt buộc** có ghi chú) |
| `suspend(user_id, note)` | treo quyền xuất bản |
| `restore(user_id, note)` | phục hồi |

Một bài test (`test_creator_routes.py::NoAdminEndpointTest`) **đổ** nếu có route
nào chứa `approve`/`reject`/`suspend`/`admin`. Khi thật sự làm trang quản trị, đó
là lúc phải đọc lại mục này trước khi xoá bài test đó, và việc cần làm trước là:
vai trò trên hồ sơ, xác thực riêng cho khu quản trị, và log thao tác duyệt.

### 7.2. Hạn chế đã biết của V1

- **Khách ẩn danh không được tính.** Một chương được nghe một nghìn lần bởi người
  chưa đăng nhập vẫn cho hạng bằng không.
- **`authors_only` lọc sau khi phân trang.** Kho hiện tại không lọc theo
  `author_status` ở tầng truy vấn, nên trang kết quả "Tác giả" có thể ít hơn
  `limit` dù còn tác giả ở trang sau.
- **Đổi username không giữ đường dẫn cũ.** `/u/ten-cu` sẽ 404. Cần bảng bí danh
  trước khi mở cho người thật.
- **Một đơn mỗi người.** Nộp lại thì ghi đè; không có lịch sử nhiều đơn.
- **`published_novels` ở `author_stats` không được cập nhật tự động** khi xuất bản
  / gỡ xuất bản. Trang công khai đếm thật từ danh sách truyện, nên nó luôn đúng;
  con số trong `author_stats` chỉ là bản đệm cho kết quả tìm kiếm.
