# Phase 4 — Kiểm toán chi phí đọc/ghi Appwrite v2

Phạm vi: `integration/pre-prod-v1` @ `a0420e6` + nhánh
`chore/preprod-overnight-hardening-v1`. Mục tiêu: tìm N+1, `listDocuments`
không giới hạn, fetch lặp lại từ frontend, polling không cần thiết — tái
kiểm sau sự cố hết quota Appwrite Cloud trước đây.

## Tóm tắt

| Khu vực | Trạng thái | Số phát hiện |
|---|---|---|
| Admin Dashboard (`/api/admin/overview`) | SẠCH (đã tối ưu ở Phase 7) | 0 |
| Gamification store (`server/appwrite_gamification_store.py`) | SẠCH | 0 (1 ghi chú thông tin) |
| Social service (`server/social_service.py`) | SẠCH | 0 |
| Creator service (`server/creator_service.py`) | SẠCH (1 hạn chế đã biết, chấp nhận được) | 0 |
| Route công khai `server/main.py` (`/api/novels`, `/api/animation/series`, ...) | SẠCH | 0 |
| `/api/health`, `/api/ready` | SẠCH | 0 |
| Worker loops (`scripts/*`) | SẠCH — không có worker vòng lặp polling thật | 0 |
| Frontend `useEffect`/`setInterval` (trang không phải admin) | SẠCH | 0 |

Không tìm thấy N+1 mới, không tìm thấy `listDocuments` không giới hạn nào
chạy trên đường nóng (hot path). Không có thay đổi code nào được thực hiện
trong phase này (chỉ audit, đúng theo chỉ thị).

## Chi tiết theo khu vực

### 1. Admin Dashboard

Đã song song hoá bằng `ThreadPoolExecutor(max_workers=4)` ở Phase 7 (đo thật
trên VM dev: 5-9s, ổn định qua nhiều lần chạy — `max_workers=8` từng gây
`httpx.ReadTimeout` thật trên VM nhỏ). Mọi đếm dùng thành ngữ
`_page(...)[1]` đọc field `total` của Appwrite mà không tải tài liệu —
không có ngoại lệ nào bị bỏ sót trong lần rà soát này.

### 2. Gamification store

`server/appwrite_gamification_store.py`:
- `list_all_progress_ranked` (dòng 550) — bảng xếp hạng, phân trang
  `orderDesc`+`limit`/`offset` do MÁY CHỦ Appwrite làm — SẠCH.
- `count_users_above_xp` — dùng `total`, không tải hàng — SẠCH.
- `xp_earned_since` (dòng 563) — `_list_all` có chặn bởi mốc thời gian
  (`q_greater_equal("created_at", since_iso)`), không phải quét vô hạn.
  Đã đọc đủ code, xác nhận đúng như docstring mô tả — SẠCH.
- `list_xp_events`, `list_unlocked_achievements`, `list_cosmetics` — `_list_all`
  nhưng luôn lọc theo `q_equal("user_id", user_id)` của MỘT người dùng, nên bị
  chặn bởi kích cỡ lịch sử/catalogue của một người, không phải toàn bảng.
- **Ghi chú thông tin (không phải lỗi)**: `list_xp_events` chỉ có nơi gọi
  trong test (`test_gamification_store.py`, `test_gamification_contract.py`,
  `test_gamification_service.py`) — không tìm thấy nơi gọi nào trong
  `gamification_service.py` hay `main.py`. Có thể là API dự phòng cho tính
  năng tương lai (vd. trang "lịch sử XP" chưa xây) chứ không phải code chết
  do lỗi — không có rủi ro đọc/ghi vì hiện không được gọi trên đường thật.
  Không cần sửa; ghi lại để Phase 16 (tài liệu) cân nhắc nếu muốn làm rõ ý
  định.
- `list_cosmetics_by_ids`, `get_progress_by_ids` — dùng
  `q_equal("user_id", [...])` HÀNG LOẠT, đúng thành ngữ tránh N+1 đã dùng
  nơi khác trong kho.

### 3. Social service

`server/social_service.py::_lam_giau_bai` (dòng 791) — làm giàu MỘT TRANG
bài đăng bằng đúng một số lượng truy vấn CỐ ĐỊNH không phụ thuộc số bài
đăng: `_the_nguoi` (thẻ tác giả hàng loạt), `liked_flags` (đã-thích hàng
loạt), `novels_by_ids` (tiêu đề truyện hàng loạt), `comments_for_posts`
(xem trước bình luận hàng loạt). Docstring của chính hàm này ghi rõ đây là
bản sửa cho một sự cố N+1 THẬT trước đây ("đã làm khu quản trị mất 34 giây
trên staging thật") — xác nhận bản hiện tại không lặp lại lỗi đó.

### 4. Creator service

`server/creator_service.py::admin_authors` (dòng 679) — **hạn chế đã biết,
được ghi rõ trong chính docstring**: kho không lọc được `author_status` ở
tầng truy vấn Appwrite (cột nằm trên bảng `profiles`, `search_profiles`
không nhận bộ lọc đó), nên phải kéo tối đa 500 hồ sơ rồi lọc ở Python. Sau
khi lọc, việc làm giàu (`_lam_giau`) đi THEO LÔ (2 truy vấn cho cả trang:
`stats_by_ids`, `published_counts`), không phải từng hàng. Trần 500 là
giới hạn cứng, không phải "không giới hạn" — chấp nhận được cho quy mô
hiện tại của Fanfic World; không sửa trong phase này (thuộc diện thay đổi
kiến trúc, ngoài phạm vi audit-only).

### 5. Route công khai `server/main.py`

`GET /api/novels`, `GET /api/animation/series` — cả hai đều phân trang
thật ở tầng kho (`limit`/`offset` chuyển thẳng xuống Appwrite), có
`total`/`has_more` tính đúng, không tải toàn bộ bảng rồi lọc ở Python
(khác hẳn thời trước đây `/fanfic` tải hết truyện về rồi lọc bằng
JavaScript — đã ghi trong chính comment của route). SẠCH.

### 6. `/api/health`, `/api/ready`

- `/api/health` — KHÔNG chạm Appwrite/R2 theo đúng thiết kế liveness, chỉ
  trả trạng thái tiến trình + `job_lock_ready`. SẠCH, đúng ý đồ.
- `/api/ready` — mỗi kiểm tra dùng đúng MỘT truy vấn đọc nhỏ nhất có thể
  (`list_jobs_by_status(..., limit=1)` kiểu, `get_stats("__readiness__")`,
  v.v. — xem code, tất cả đều bounded). Không có vòng lặp, không liệt kê
  không giới hạn. SẠCH.

### 7. Worker loops

Không tìm thấy worker dạng `while True`/polling thật trong `scripts/`.
Các script khớp mẫu tìm kiếm (`setup_appwrite.py`,
`run_websub_reconciliation.py`, `audit_profiles_datetime_dry_run.py`,
`smoke_test_selfhost_appwrite.py`, `staging_smoke.py`) đều chạy MỘT LẦN
rồi thoát (dùng cho cron/tay, không phải tiến trình thường trú). Tiến
trình job xử lý audio/dịch chạy theo mô hình "inline worker" trong tiến
trình FastAPI (đã biết từ trước, xem `settings.inline_worker` ở
`/api/ready`) — không phải một worker loop riêng cần audit thêm ở đây.

### 8. Frontend — `useEffect`/`setInterval` (trang không phải admin)

Rà `web/src/app` cho các trang `novels/[id]`, `chapters/[id]`,
`animation`, `animation/[id]` (`watch/[id]`), `listen/[id]`, `library`,
`fanfic`: mỗi trang chỉ có 1-2 `useEffect` tải dữ liệu một lần khi mount
(qua `useAsyncData`/`load`), không có fetch lặp trong dependency array gây
vòng lặp.

Duy nhất một `setInterval` thật trong toàn bộ nhóm trang này:
`web/src/app/animation/watch/[id]/page.tsx` dòng 119 — báo cáo tiến độ xem
mỗi `KHOANG_BAO_CAO_GIAY` giây, CHỈ bắt đầu sau khi người xem thật sự bấm
Play (`onReady` của YouTube IFrame API), và được `clearInterval` đúng cách
trong cleanup của `useEffect` (dòng 91-96) khi đổi tập/rời trang. Gọi
`api.reportWatchProgress` — một request nhỏ, không phải `listDocuments`.
SẠCH.

## Kết luận

Không có phát hiện nào cần sửa trong Phase 4. Kiến trúc chi phí Appwrite
hiện tại nhất quán với các bài học đã áp dụng từ sự cố hết quota trước đây
(thành ngữ đếm bằng `total`, làm giàu theo lô, phân trang thật ở tầng kho).
Một hạn chế đã biết ở `admin_authors` (kéo tối đa 500 hồ sơ) được giữ
nguyên vì đã có tài liệu rõ trong code và không phải rủi ro leo thang theo
số lượng bài đăng/tập phim — chỉ theo số người dùng có vai trò tác giả,
tăng chậm hơn nhiều.
