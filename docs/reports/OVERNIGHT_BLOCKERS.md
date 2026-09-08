# OVERNIGHT BLOCKERS — 2026-09-08

Trạng thái cuối đêm. Mỗi mục: chặn ở đâu, lệnh chính xác tiếp theo, và trạng
thái đã để lại (luôn fail-closed).

---

## ✅ B1. Collection `review_jobs` — ĐÃ GIẢI QUYẾT

Đã cấp phát trên Appwrite production: **22 mục tạo mới**, các collection khác
không bị đụng.

Đây là thao tác **thuần cộng thêm** và dùng đúng `APPWRITE_SCHEMA_API_KEY` —
khoá có đúng 7 scope và **cố ý không có `documents.*`**, nên nó không đọc/sửa
được một tài liệu nào. Không phải một mutation phá huỷ.

Xác minh: `python -m server.farmer --check-review-queue` →
`{"review_queue": "OK", "provider": "queue", "pending_visible": 0}`

---

## ✅ B3. `fanfic-gdrive` — ĐÃ GIẢI QUYẾT (tự phục hồi)

Token **đã hoạt động trở lại** — rclone tự làm mới. Lỗi `invalid_grant` trước
đó là tạm thời, **không** cần `rclone config reconnect`.

Đã tạo cây sản xuất chính tắc:

```
FanficWorld/production/works/{fanfic-tts,existing-audio,chinese-media}
FanficWorld/production/{quarantine,rejected,manifests}
```

Cây **legacy** `FanficWorld/archive/` xác minh còn nguyên: `animation-worker`,
`experiments`, `final`, `infra`, `scraping`.

Dung lượng: 5 TiB tổng, 2,8 GiB đã dùng.

**Danh tính tài khoản (email): KHÔNG lấy được.** rclone không hỗ trợ
`config userinfo` cho backend Drive, và `about` chỉ trả hạn mức. Không có cách
nào khác mà không chạm vào token — nên dừng ở đây.

---

## ⛔ B2. Bootstrap farmer trên máy AWS — CÒN CHẶN

**Chặn ở:** `/opt/fanfic-audio` thuộc `root:root`; cài unit systemd và ghi
`/etc/fanfic-audio/farmer.env` cần quyền quản trị. Hook bảo mật của phiên tự
động chặn leo thang quyền, và **không được nới ra**.

**Trạng thái để lại:** dịch vụ **chưa cài, chưa chạy**. Không có tiến trình nền
nào được khởi động trên AWS.

**Lệnh chính xác tiếp theo:** một lệnh duy nhất trong
`docs/PRODUCTION_FARMER.md` mục "Cài đặt lên máy AWS". Script **không còn hỏi
khoá Gemini** — nó kiểm hàng đợi đánh giá thay thế.

---

## ⛔ B6. Chưa có nguồn truyện chữ thật — CÒN CHẶN (quyết định nội dung)

**Chặn ở:** đây là quyết định **nội dung/sản phẩm**, không phải kỹ thuật. Tôi
không tự chọn nguồn để farm.

`/etc/fanfic-audio/farmer-text-sources.json` chưa tồn tại trên AWS. Bản mẫu
trên máy này chỉ có **một** mục Wikisource dùng để kiểm thử — và nó đã bị
`quarantine` (điểm 35).

**Hệ quả:** kể cả khi B2 xong, lằn truyện chữ sẽ **không sản xuất gì** cho tới
khi có nguồn thật. Lằn audio vẫn nạp `content_queue` bình thường.

**Việc cần:** điền nguồn thật vào tệp đó (định dạng trong
`docs/PRODUCTION_FARMER.md`).

---

## Vì sao farmer CHƯA chạy liên tục

Yêu cầu: *"chỉ khởi động nếu đã xác minh đầy đủ VÀ không còn ranh giới cần
người."*

B2 vẫn là một ranh giới cần người (quyền quản trị), và B6 là một quyết định
nội dung. Nên farmer được để **staged an toàn** — đúng theo yêu cầu, thay vì
khởi động một tiến trình sẽ không sản xuất được gì.
