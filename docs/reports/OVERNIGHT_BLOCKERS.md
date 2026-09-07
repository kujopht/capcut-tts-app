# OVERNIGHT BLOCKERS — 2026-09-08

Việc bị chặn bởi một ranh giới **chỉ người làm được**. Mỗi mục ghi: chặn ở
đâu, lệnh chính xác tiếp theo, và trạng thái đã để lại (luôn fail-closed).

---

## B1. Provision `review_jobs` collection trên Appwrite production

**Chặn ở:** thay đổi schema production (cần `APPWRITE_SCHEMA_API_KEY`, và đây
là một mutation trên kho dữ liệu production).

**Trạng thái để lại:** mã đã sẵn sàng và fail-closed. Farmer gọi
`create_review_job_once()`; nếu collection chưa tồn tại, Appwrite trả lỗi →
`ReviewUnavailable` → **không duyệt, không sản xuất**. Không có đường vòng.

**Lệnh chính xác tiếp theo:**

```bash
python scripts/fanfic_appwrite_schema.py audit --only review_jobs
python scripts/setup_appwrite.py --only review_jobs
python scripts/fanfic_appwrite_schema.py audit --only review_jobs   # kỳ vọng EXIT=0
```

Schema đã khai báo đầy đủ trong `scripts/setup_appwrite.py` (17 thuộc tính,
3 index). Thuần **cộng thêm** — không đụng collection nào đang có.

---

## B2. Bootstrap farmer trên máy AWS (cần quyền quản trị)

**Chặn ở:** `/opt/fanfic-audio` thuộc `root:root`; cài unit systemd và ghi
`/etc/fanfic-audio/farmer.env` đều cần quyền quản trị. Hook bảo mật của phiên
tự động chặn leo thang quyền, và **không được nới ra**.

**Trạng thái để lại:** dịch vụ chưa cài, chưa chạy. Không có tiến trình nền
nào được khởi động.

**Lệnh chính xác tiếp theo:** một lệnh duy nhất trong
`docs/PRODUCTION_FARMER.md` mục "Cài đặt lên máy AWS".

> **Đã đổi so với bản trước:** `farmer.env` **không còn cần**
> `FARMER_GEMINI_API_KEY`. Đánh giá nay đi qua hàng đợi + pool Antigravity.
> Script bootstrap vẫn hỏi khoá Gemini — **cần sửa trước khi chạy** (xem B4).

---

## B3. `fanfic-gdrive` token hết hạn (`invalid_grant`)

**Chặn ở:** OAuth Google — phải mở trình duyệt và đăng nhập.

**Trạng thái để lại:** lớp lưu trữ Drive đã có và fail-closed đúng cách. Drive
hỏng → `ARCHIVE_PENDING` + thử lại. **Không** xoá, **không** làm hỏng object
R2 hợp lệ. Sản xuất (R2 + Appwrite) chạy bình thường mà không cần Drive.

**Lệnh chính xác tiếp theo (trên máy Windows):**

```
rclone config reconnect fanfic-gdrive:
```

Chọn tài khoản có chủ đích: nó trở thành **một** danh tính Drive sản xuất.
Lưu ý `FanficWorld` **không** có trong tài khoản mà `hainam-drive` dùng.

---

## B4. Script bootstrap vẫn hỏi khoá Gemini

**Chặn ở:** không — đây là việc của tôi, ghi ở đây để không quên.

**Trạng thái:** `deploy/bootstrap-farmer.sh` viết `FARMER_GEMINI_API_KEY` vào
`farmer.env` và chạy `--verify-credential`. Sau quyết định đêm nay, đánh giá
đi qua hàng đợi nên khoá Gemini **không còn cần**. Đã sửa trong cùng đợt làm
việc này — xem `FARMER_REVIEW_PROVIDER=queue`.

---

## B5. Khởi động liên tục farmer + reviewer

**Chặn ở:** phụ thuộc B1 (collection) và B2 (bootstrap). Cả hai đều cần người.

**Trạng thái để lại:** **chưa khởi động gì**. Đúng yêu cầu "không chạy liên
tục nếu đánh giá còn phụ thuộc laptop chưa được nối".
