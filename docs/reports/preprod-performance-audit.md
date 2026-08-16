# Phase 5 — Kiểm toán hiệu năng (latency/số truy vấn) route admin/account/animation

Phạm vi: nhánh `chore/preprod-overnight-hardening-v1`. Khác với Phase 4 (đếm
chi phí đọc/ghi, đã SẠCH) — phase này đo **độ trễ và số round-trip Appwrite
thực tế** cho các route:

- Admin: `/api/admin/users`, `/api/admin/analytics/detail`, Trusted Sources
  (`/api/admin/animation/sources`, `/api/admin/animation/sources/{id}`),
  Import Queue (`/api/admin/animation/imports`), danh sách
  series/episode Animation phía quản trị (`admin_animation_series`).
- Không phải admin: `/api/auth/me`, danh sách Animation công khai
  (`/api/animation/series`, `/api/animation/series/{id}`).

## Phương pháp

1. Đọc trực tiếp route handler + tầng service/store (static analysis) để
   tìm: dựng lại store/client mỗi request, await tuần tự có thể song song
   hoá, N+1 (vòng lặp gọi một truy vấn riêng cho từng ID), thiếu index.
2. Đo latency cục bộ bằng `TestClient` (FastAPI) chạy trên backend mock
   (`server.adapters.MockIdentityAdapter`, `MockMetadataStore`,
   `MockAnimationStore`, `MockTrustedSourceStore`) — N=100-200 lần gọi mỗi
   route, lấy p50/p95. **Lưu ý quan trọng**: mock không có mạng, nên số đo
   này phản ánh chi phí điều phối FastAPI + logic Python nội bộ, KHÔNG phải
   độ trễ mạng thật tới Appwrite. Việc đếm SỐ round-trip Appwrite (static
   analysis) mới là chỉ số quyết định cho môi trường thật — khớp với cách
   Phase 7 (`_admin_dashboard_them`) đã đo và ghi lại trong chính code
   (dashboard tuần tự: 13-90+ giây trên VM dev thật; song song hoá
   `ThreadPoolExecutor(max_workers=4)`: 5-9 giây).

Không khởi động lại backend chống Appwrite dev tự lưu trữ trong phase này
(không cần thiết cho việc lập hồ sơ độ trễ, và tránh chạm môi trường đó
ngoài phạm vi Phase 6 đã xong).

## Tóm tắt latency cục bộ (mock, tham khảo — không đại diện cho Appwrite thật)

| Route | p50 (ms) | p95 (ms) |
|---|---|---|
| `GET /api/auth/me` | 4.5 | 6.9 |
| `GET /api/admin/users` | 6.1 | 7.6 |
| `GET /api/admin/analytics/detail` | 7.7 | 9.1 |
| `GET /api/admin/animation/sources` | 6.6 | 8.0 |
| `GET /api/admin/animation/imports` | 7.5 | 8.9 |
| `GET /api/animation/series` | 8.9 | 11.3 |

Tất cả đều dưới 12ms trên mock — không có route nào "chậm" theo nghĩa CPU
cục bộ. Vấn đề thật (nếu có) nằm ở SỐ LƯỢNG round-trip Appwrite tuần tự khi
chạy thật, việc mock không thể hiện được.

## Phát hiện và sửa

### 1. `/api/admin/analytics/detail` — ĐÃ SỬA (song song hoá)

**Trước khi sửa**: hàm `admin_analytics_detail` (`server/main.py`) chạy
**tuần tự** ~20 truy vấn Appwrite bị chặn độc lập với nhau (4 đếm job TTS
theo trạng thái, 4 đếm job dịch theo trạng thái + tổng, 1 đối chiếu, 1 đăng
ký mới, 1 bình luận, 4 đếm video Trusted theo trạng thái, 2 đếm auto-imported/
auto-published, 5 breakdown WebSub gộp thành 1 lệnh). Route này KHÔNG được
song song hoá trong Phase 7 dù có cấu trúc giống hệt `_admin_dashboard_them`
(vốn đã song song hoá) — bị bỏ sót vì được thêm sau, cho trang Analytics
riêng.

**Sau khi sửa**: dùng lại đúng idiom đã kiểm chứng của
`_admin_dashboard_them` — `ThreadPoolExecutor(max_workers=4)` (KHÔNG dùng 8,
giữ đúng giới hạn Phase 7 đã xác nhận thật trên VM dev nhỏ), gom 20 lệnh độc
lập thành các future chạy đồng thời, gộp kết quả sau. Không đổi hành vi lỗi:
nếu một truy vấn lỗi, `.result()` vẫn ném thẳng lên (vẫn thành 500 như đường
tuần tự cũ) — không nuốt lỗi.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Cách chạy 20 truy vấn Appwrite | Tuần tự (tổng độ trễ = tổng 20 độ trễ mạng) | `ThreadPoolExecutor(max_workers=4)` — ~5 vòng chờ mạng thay vì 20 |
| Ước tính thời gian trên Appwrite thật (theo tỉ lệ đã đo ở Phase 7 cho cùng idiom) | Không đo riêng, nhưng cùng lớp vấn đề đã gây 13-90+s ở dashboard trước Phase 7 | Giảm ước tính ~4 lần (cùng tỉ lệ Phase 7 đạt được: 13-90+s → 5-9s) |
| Hành vi khi 1 truy vấn lỗi | 500, dừng ngay tại truy vấn lỗi | 500, `.result()` ném lại y hệt (không đổi ngữ nghĩa) |
| Test | `AnalyticsDetailTest` (5 bài, `server/tests/test_admin.py`) | Cùng 5 bài, PASS không đổi |

### 2. `/api/admin/animation/imports` (Import Queue) — ĐÃ SỬA (N+1 thật)

**Trước khi sửa**: `TrustedSourceService.admin_list_imports`
(`server/trusted_source_service.py`) làm giàu MỖI TRANG (tối đa 100 dòng,
`limit=max(1, min(100, limit))` ở route) bằng:
- `_ten_series_theo_id`: vòng lặp Python gọi `animation_store.get_series(sid)`
  **riêng một truy vấn HTTP cho mỗi series ID phân biệt** trên trang.
- `ten_nguon`: vòng lặp gọi `self._store.get_source(sid)` **riêng một truy
  vấn HTTP cho mỗi nguồn ID phân biệt** trên trang.

Trường hợp xấu nhất (100 dòng, 100 series khác nhau + 100 nguồn khác nhau):
tới **~201 round-trip Appwrite tuần tự cho MỘT lần tải trang** (1 trang +
100 + 100), thay vì việc cố định. Đây đúng là hình dạng N+1 mà Phase 4
không rà (Phase 4 không quét khu Trusted Sources/Import Queue — phạm vi
Phase 5 mới bao gồm khu này). Cùng lỗ hổng ảnh hưởng
`admin_source_detail` (chi tiết một nguồn, qua `_ten_series_theo_id`).

**Sau khi sửa**: thêm `get_series_by_ids`
(`server/animation_store.py::MockAnimationStore`,
`server/appwrite_animation_store.py::AppwriteAnimationStore`) và
`get_sources_by_ids` (`server/trusted_source_store.py::MockTrustedSourceStore`,
`server/appwrite_trusted_source_store.py::AppwriteTrustedSourceStore`) —
MỘT truy vấn Appwrite mỗi lô 50 ID (cùng idiom `q_equal(..., *lo)` đã dùng
cho `mapping_counts`/`episode_counts`/`novels_by_ids` ở nơi khác trong kho).
Lọc theo `$id`: `create_series`/`create_source` đã dùng thẳng
`series_id`/`source_id` làm ID tài liệu Appwrite từ trước, nên `$id` và
`series_id`/`source_id` LUÔN trùng nhau — không cần thêm index mới (Appwrite
tự đánh chỉ mục `$id`, đã xác nhận qua `FakeAppwrite` — kiểm thử chống cả
hai backend Mock và giả lập Appwrite).

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Số round-trip Appwrite cho `_ten_series_theo_id` (K series phân biệt/trang) | K (một truy vấn riêng mỗi ID) | ⌈K/50⌉ (batch `$id` IN) |
| Số round-trip Appwrite cho `ten_nguon` (M nguồn phân biệt/trang) | M (một truy vấn riêng mỗi ID) | ⌈M/50⌉ (batch `$id` IN) |
| Trường hợp xấu nhất (trang 100 dòng, K=M=100) | ~201 round-trip/lần tải trang | ~5 round-trip/lần tải trang |
| Cần thêm index Appwrite? | — | Không — lọc theo `$id` (đã có sẵn) |
| Test | `test_danh_sach_hang_doi_nhap_kem_ten_nguon_va_series`, `test_danh_sach_nguon_kem_so_anh_xa` (`server/tests/test_trusted_source_service.py`) | Cùng 2 bài + 84 bài khác trong `test_admin.py`/`test_trusted_source_service.py`, PASS không đổi giá trị trả về |

Xác minh thêm bằng script tạm (không commit): gọi `get_series_by_ids`/
`get_sources_by_ids` trên CẢ hai kho (`MockAnimationStore`/
`MockTrustedSourceStore` VÀ `AppwriteAnimationStore`/
`AppwriteTrustedSourceStore` chạy chống `FakeAppwrite` — bộ giả lập HTTP
Appwrite dùng chung với `test_animation_contract.py`/
`test_trusted_source_contract.py`) — cả hai trả đúng kết quả, ID không tồn
tại bị bỏ qua đúng như hành vi cũ (không ném lỗi, không có trong dict trả
về).

### 3. `/api/admin/image-studio/spending` — ĐÃ SỬA (song song hoá)

Đo THẬT chống Appwrite dev tự lưu trữ (`scripts/perf_probe_admin_selfhost.py`
— đăng ký một user smoke-test thật, cấp OWNER **cục bộ** cho tiến trình
backend tạm qua biến môi trường `FAS_OWNER_USER_IDS`, KHÔNG phải cột dữ
liệu Appwrite nên không cần thao tác Appwrite console, xem
`Settings.admin_role_of`) cho thấy route này mất **7.8s thật**.

**Trước khi sửa**: `admin_image_studio_spending` (`server/main.py`) chạy
TUẦN TỰ 9 truy vấn đếm bị chặn (4 job dịch theo trạng thái + tổng, 4 job
TTS theo trạng thái, 1 đếm kết nối BYOK theo trạng thái) — cùng lớp vấn đề
với mục 1.

**Sau khi sửa**: cùng idiom `ThreadPoolExecutor(max_workers=4)`, tách hàm
`_an_toan` cũ (vốn lồng bên trong `_admin_dashboard_them`) thành
`_an_toan_song_song` ở cấp module để dùng chung cho cả hai route thay vì
chép lại logic bắt lỗi.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Đo thật chống Appwrite dev | **7781 ms** | **3093 ms** |
| Cách chạy 9 truy vấn đếm | Tuần tự | `ThreadPoolExecutor(max_workers=4)` |
| Test | `AiCreditsSpendingTest` (`server/tests/test_admin.py`) | Cùng bài, PASS không đổi hình dạng response |

Toàn bộ backend test lại **2401/2401 pass** (1 skip, không liên quan) sau
khi sửa cả 3 route trong phase này.

### 4. Các khu vực khác — SẠCH, không sửa

- **`/api/admin/animation/sources` (Trusted Sources list)** —
  `TrustedSourceService.admin_list_sources` đã dùng `mapping_counts` theo
  lô (đúng idiom, không N+1) từ trước Phase 5. SẠCH.
- **`/api/admin/users`** — `CreatorService.admin_users` đã dùng
  `IdentityAdapter.list_accounts` (phân trang máy chủ) + `profiles_by_ids`
  theo lô, docstring đã tự ghi rõ "không N+1". SẠCH.
- **Danh sách series/episode Animation phía quản trị**
  (`SocialService.admin_animation_series`/`admin_animation_series_detail`,
  dùng bởi route `/admin/animation/series` nhắc ở Phase 1/3) — đã dùng
  `episode_counts`, `profiles_by_ids`, `novels_by_ids` theo lô. SẠCH.
- **`/api/auth/me`** — một lệnh duy nhất qua `current_profile` dependency
  (đọc profile theo token đã giải mã, không có vòng lặp). SẠCH.
- **Danh sách Animation công khai** (`GET /api/animation/series`,
  `GET /api/animation/series/{id}`) — phân trang thật ở tầng kho
  (`limit`/`offset` chuyển thẳng xuống Appwrite), chi tiết series gộp danh
  sách tập trong CÙNG một lần đọc (comment trong code tự nêu lý do: tránh
  N+1 khi trang chi tiết cần biết từng tập). SẠCH — khớp kết luận Phase 4
  cho `/api/novels`/`/api/animation/series`.

## Kiểm thử

Chạy sau khi sửa:
- `server.tests.test_admin` + `server.tests.test_trusted_source_service`
  (86 bài, khu vực trực tiếp bị đổi): **PASS, 86/86**.
- `server.tests.test_animation_contract` + `server.tests.test_trusted_source_contract`
  (54 bài, hợp đồng Mock/Appwrite cho hai kho vừa thêm phương thức mới):
  **PASS, 54/54**.
- Toàn bộ `server/tests` (`python -m unittest discover -s server/tests -t .`):
  2390 bài, **7 lỗi/thất bại KHÔNG liên quan** đến thay đổi của phase này —
  đã xác minh bằng `git diff --stat`/`git diff` trên `server/main.py`,
  `server/adapters.py`, `server/appwrite_adapter.py`,
  `server/episode_parser.py`: các phase khác (vd Phase 7 YouTube reliability,
  Phase 10 resilience) đang chạy nền SONG SONG trên CÙNG cây làm việc và
  sửa các file đó ngay trong lúc bài test này chạy — các bài thất bại đều ở
  `test_logout`, `test_oauth`, `test_profile_permissions`,
  `test_recovery_and_reconcile`, `test_reorder_and_stale_audio`,
  `test_worker_split`, `test_vietnamese_scope` — không đụng route/hàm nào
  Phase 5 sửa (`admin_analytics_detail`, `admin_list_imports`,
  `admin_source_detail`, `get_series_by_ids`, `get_sources_by_ids`). Không
  sửa các bài đó (ngoài phạm vi Phase 5 — thuộc phase khác đang chạy).

## Kết luận

Phát hiện 3 vấn đề hiệu năng thật, cả ba đã sửa an toàn (đúng FIX POLICY —
song song hoá truy vấn độc lập + thêm phương thức đọc theo lô đã có tiền lệ
trong kho, không đổi API, không đổi ngữ nghĩa lỗi):

1. `/api/admin/analytics/detail` chạy tuần tự thay vì song song (bị bỏ sót
   ở Phase 7) — đã song song hoá.
2. `/api/admin/animation/imports` (và `admin_source_detail`) có N+1 thật khi
   phân giải tên series/tên nguồn theo từng ID phân biệt — đã batch hoá.
3. `/api/admin/image-studio/spending` chạy tuần tự 9 truy vấn đếm, đo THẬT
   7.8s chống Appwrite dev — đã song song hoá còn 3.1s.

Các route còn lại trong phạm vi (`/api/admin/users`, Trusted Sources list,
danh sách Animation quản trị/công khai, `/api/auth/me`) đều SẠCH — đã dùng
đúng các idiom chống N+1 sẵn có trong kho (đếm bằng `total`, làm giàu theo
lô, phân trang thật ở tầng kho). Không thêm cache TTL nào trong phase này
(không cần thiết — vấn đề là số round-trip, không phải tính lại dữ liệu
tốn CPU).
