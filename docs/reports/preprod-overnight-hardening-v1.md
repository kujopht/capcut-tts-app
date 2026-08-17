# Báo cáo Release-Candidate — Overnight Pre-Production Hardening Marathon V1

Nhánh: `chore/preprod-overnight-hardening-v1`. Nguồn: `integration/pre-prod-v1`
(đã qua xét duyệt tích hợp Admin Control Center V2 + Trusted Video Sources).
Đây là báo cáo tổng hợp Phase 17 — tổng hợp 13 báo cáo con dưới
`docs/reports/preprod-*.md` và toàn bộ tiến độ ghi trong
`docs/handoffs/preprod-overnight-hardening-v1.md`.

## 1. SHA bắt đầu

`integration/pre-prod-v1` @ `a0420e6` (local == remote lúc bắt đầu).

## 2. SHA cuối nhánh overnight

`chore/preprod-overnight-hardening-v1` @ `78aa81a` (trước khi push/freeze ở
Phase 19).

## 3. Các checkpoint commit

| SHA | Nội dung |
|---|---|
| `efdaaa2` | Phase 0 — bootstrap + baseline |
| `4edf102` | Phase 1-4, 6 — route matrix, browser QA, auth audit, Appwrite cost audit, smoke matrix tự lưu trữ |
| `34cf29f` | Đánh dấu Phase 5,7,10,11,14-16 đang chạy nền |
| `89540fb` | Phase 5,7,10,11,14-16 — hiệu năng, YouTube, resilience, a11y, worker/ops, cross-platform, docs |
| `b4a20f3` | Phase 7 — sửa `episode_parser.py` thiếu `re.IGNORECASE` |
| `54d2609` | Phase 10 — cập nhật báo cáo (chi tiết `AppwriteUnavailableError`) |
| `ef9dd77` | Phase 8-9 — Image Studio + Translation/TTS (sạch, không sửa) |
| `868d54f` | Phase 12 — security/secret audit |
| `43b20f0` | Phase 13 — schema consistency (3 nhóm lỗi sửa) |
| `78aa81a` | Dọn báo cáo trùng lặp + vá banner lỗi thời `docs/HANDOFF.md` |

## 4. Bugs tìm thấy (tổng hợp toàn bộ 19 phase)

1. `server/episode_parser.py::_BARE_E_RE` thiếu `re.IGNORECASE` — `"e12"`
   không nhận dạng được trong khi `"E12"` thì có (Phase 7).
2. `GET /api/admin/image-studio/spending` mất 7.8s do 9 truy vấn đếm chạy
   tuần tự; `admin_analytics_detail` tương tự (Phase 5).
3. N+1 thật trong Trusted Video Sources admin: `admin_list_imports`/
   `admin_source_detail` gọi `get_series(id)`/`get_source(id)` từng cái một,
   tối đa ~201 round-trip cho một trang 100 dòng (Phase 5).
4. `server/appwrite_adapter.py::_request()` không phân biệt "Appwrite mất kết
   nối" với "phiên hết hạn" — mọi route được bảo vệ trả 401 thay vì 503 khi
   Appwrite chỉ tạm thời không tới được (Phase 10).
5. 9 chỉ mục Appwrite còn thiếu cho các truy vấn lọc/sắp đã tồn tại từ trước
   (`profiles`, `moderation_events`, `posts`, `comments`, `content_reports`,
   `user_progress`, `xp_ledger`) (Phase 13).
6. 4 điểm đọc enum không an toàn (`PublishState`/`JobStatus` parse trần, có
   thể `ValueError` nếu Appwrite có giá trị lạ/cũ) (Phase 13).
7. **`server/trusted_source_domain.py`** — `TrustedSource.to_dict()`/
   `VideoImport.to_dict()` (9 trường datetime tuỳ chọn) chưa có `or None` —
   lỗi CÙNG LỚP đã sửa ở checkpoint `8b1c544` trên nhánh feature gốc, nhưng
   đợt đó chưa từng chạm file domain-serializer này (Phase 13). Ảnh hưởng
   thật: nguồn tin cậy/video mới tạo hiện SAI là "đã quét/đã đồng bộ".
8. `.tim-dau` (ô tìm kiếm `SearchOverlay`) mất focus-visible; `ReportDialog`
   không trả tiêu điểm về nút mở dù docstring tự nhận có; `.bell` không đạt
   44×44px trên mobile; `ProviderConnectDialog` (BYOK) hoàn toàn thiếu xử lý
   bàn phím (Phase 11, hai vòng độc lập).
9. `docs/HANDOFF.md` cực kỳ lỗi thời (sửa cuối 2026-08-08, bỏ sót toàn bộ
   Appwrite tự lưu trữ/Admin V2/Trusted Video/Image Studio) dù `CLAUDE.md`
   vẫn trỏ vào đó; `docs/WEB_README.md` khẳng định sai Appwrite/R2 "chưa kiểm
   chứng thật"; `docs/ADMIN.md` API list lỗi thời (Phase 16).
10. Tiến trình backend tạm ở cổng 8010 từ một lần chạy trước bị treo lại,
    khiến vài lần chạy smoke test đầu tiên âm thầm nhắm nhầm backend mock cũ
    thay vì backend cấu hình đúng (Phase 6, phát hiện vận hành, không phải
    bug code).

## 5. Bugs đã sửa

Tất cả các mục 1, 2, 3, 4, 5, 6, 7, 8 (phần `.tim-dau`/`ReportDialog`/`.bell`/
`ProviderConnectDialog`), 9 (banner `docs/HANDOFF.md`, sửa nhỏ
`docs/WEB_README.md`/`docs/ADMIN.md`) ở mục 4 phía trên đã được sửa, có test
xác nhận không hồi quy (xem mục 20). Mục 10 không phải bug code, đã xử lý
bằng `Stop-Process` và chạy lại.

## 6. Bugs CỐ Ý không sửa (ghi rõ lý do)

- `youtube_client.py::_goi()` không có retry/backoff cho lỗi mạng/5xx tạm
  thời (chỉ `quotaExceeded` được phân biệt) — cần thiết kế lại chiến lược
  retry, vượt phạm vi "sửa nhỏ an toàn" (Phase 7).
- `import_video()` (nút "Nhập" thủ công) là check-then-act không khoá xuyên
  suốt — hai admin bấm "Nhập" cùng lúc trên cùng video có thể tạo 2 episode
  trùng `order_index`. Khác với `scan_source`/`create_import_once` (đã xác
  nhận idempotent qua `documentId` tất định) — đây là đường thủ công hiếm khi
  đụng độ, sửa đòi hỏi khoá phân tán, vượt phạm vi phase (Phase 7).
- `preview` bắt buộc trước khi tạo Trusted Source chỉ ép ở frontend — backend
  `create_source()` không gọi lại YouTube Data API để xác minh. Admin có thể
  POST thẳng ID bịa đặt. Đây là mô hình tin cậy nội bộ (chỉ admin/owner mới
  gọi được), không phải lỗ hổng cho người dùng thường — ghi nhận, không sửa
  (Phase 7).
- `<img>` không khai báo `width`/`height` cho ảnh do người dùng tạo
  (Image Studio) — không có kích thước cố định trước khi tải xong, chấp nhận
  được cho nội dung động (Phase 5).
- Thiếu `dynamic()` code-splitting ở vài trang nặng — tối ưu hoá, không phải
  bug, để lại cho quyết định sản phẩm sau (Phase 5).
- Thiếu health-timer watchdog cho worker **production** (staging đã có);
  không có cảnh báo tự động khi quên chạy worker riêng ở production — vượt
  phạm vi "sửa nhỏ an toàn", cần quyết định vận hành riêng (Phase 14).
- `docs/APPWRITE_V2.md`/`APPWRITE_SCHEMA.md` thiếu 18/39 collection — đã
  thêm ghi chú trỏ nguồn thật (`setup_appwrite.py`) thay vì viết lại toàn bộ
  tài liệu (Phase 13/16).
- R2 (`boto3`) không đặt `connect_timeout`/`read_timeout` tường minh — dựa
  vào mặc định thư viện, không phải treo vô hạn, nhưng nên xem lại sau
  (Phase 10).

## 7. Phát hiện bảo mật

`docs/reports/preprod-security-audit.md`. Sạch — không có secret thật nào
từng được commit (quét toàn bộ lịch sử git). `secret_redaction.py` xác minh
bằng lời gọi thật với giá trị dạng secret giả. Đã sửa 1 điểm phòng thủ theo
chiều sâu: `_an_toan_song_song()` (`server/main.py`) in `repr(exc)` thô không
qua bộ lọc redaction (không có lỗ hổng đang khai thác — mọi exception hiện tại
đã được làm sạch ở lớp trên, đây là lớp phòng thủ bổ sung).

## 8. Phát hiện phân quyền

Soi trực tiếp `server.main.app.routes`: ~54 route `/api/admin/*`, mỗi route
có ĐÚNG MỘT trong `admin_profile`/`admin_or_owner_profile`/`owner_profile`,
khớp đúng ý đồ vai trò cho từng hành động. SẠCH — không có route thiếu
dependency, không có lỗ hổng leo quyền. "Ẩn ở frontend không tính là bảo
mật" — đã xác nhận qua test tự-kiểm-tra hiện có
(`test_moi_route_admin_deu_duoc_bao_ve` và các test tiêu cực khác).

## 9. Hiệu năng trước/sau

`docs/reports/preprod-performance-audit.md`.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `GET /api/admin/image-studio/spending` | 7.8s (9 truy vấn đếm tuần tự) | ~3.1s (song song hoá `ThreadPoolExecutor`) |
| `admin_analytics_detail` | ~11.4s (tuần tự) | Song song hoá độc lập, cùng idiom |
| Trusted Sources admin — import queue/source detail | N+1: tối đa ~201 round-trip/trang | Batch `get_series_by_ids`/`get_sources_by_ids` (chunk 50) |
| Core Web Vitals (`/`, `/fanfic`, `/animation`) | — | LCP 438-692ms, CLS 0.01 — không vấn đề |

## 10. Kiểm toán đọc/ghi Appwrite

`docs/reports/preprod-appwrite-cost-audit.md`. SẠCH toàn bộ 8 khu vực
(dashboard, gamification store, social service, creator service, route công
khai, health/ready, worker loops, frontend useEffect/setInterval). Không có
N+1/vòng lặp bất thường mới. 1 hạn chế đã biết ở `admin_authors` (kéo tối đa
500 hồ sơ) — chấp nhận được.

## 11. Browser QA (desktop)

`docs/reports/preprod-browser-qa.md`. Quét desktop (1440px+) cho toàn bộ
route công khai + luồng đăng ký/đăng nhập/write/studio/account. Không có lỗi
console/render. Đo Lighthouse Accessibility 100/100 trên 6 route đại diện.

## 12. QA di động

Cùng báo cáo Phase 2 — quét mobile (390×844) song song với desktop. Không có
tràn ngang, double scrollbar, hay phần tử không bấm được. Nav mobile cuộn
ngang cục bộ là có chủ đích (đã xác nhận qua code, không phải bug).

## 13. Phát hiện khả năng tiếp cận (accessibility)

`docs/reports/preprod-accessibility-audit.md`. Lighthouse 100/100 trên 6
route. Đã sửa 4 lỗi thật: focus-visible ô tìm kiếm, `ReportDialog` không trả
tiêu điểm, `.bell` dưới 44×44px trên mobile, `ProviderConnectDialog` (BYOK)
hoàn toàn thiếu xử lý bàn phím. Ghi nhận không sửa (vượt phạm vi nhỏ/an
toàn): `ImageLightbox`/`SearchOverlay` không bẫy phím Tab đầy đủ như
`ConfirmDialog`.

## 14. Phát hiện schema

`docs/reports/preprod-schema-audit.md`. 9 chỉ mục còn thiếu đã thêm vào
`SCHEMA`; 4 điểm đọc enum không an toàn đã có fallback; 1 lỗi datetime-chuỗi-
rỗng còn sót ở `trusted_source_domain.py` (9 trường) đã sửa — lỗi CÙNG LỚP
với đợt hardening `8b1c544` nhưng file domain-serializer này chưa từng được
chạm tới. Xác nhận sạch: phía ghi enum luôn dùng `.value`; mẫu tính duy nhất
qua `documentId` tất định là đúng ý đồ trên >10 collection.

## 15. Phát hiện YouTube/Trusted Source

`docs/reports/preprod-youtube-reliability-audit.md`. Đã sửa lỗi
case-insensitive ở parser tập. Duplicate/conflict detection khớp đúng ý đồ
(idempotent qua `documentId`). Unavailable-video handling xuống cấp graceful
(2 test mới xác nhận). 3 phát hiện minor không sửa (mục 6). `YOUTUBE_API_KEY`
không có ở `server/.env` cục bộ (chỉ có ở `.env.selfhost`, đã qua smoke test
19/19).

## 16. Phát hiện admin

Route matrix (`docs/reports/preprod-route-matrix.md`) liệt kê đủ 18 route
admin. Phân quyền sạch (mục 8). Hiệu năng 2 route admin đã sửa (mục 9). Đã
gọi thật `/api/admin/overview`, `/users`, `/animation/series`, `/sources`,
`/imports`, `/events` qua HTTP+JWT thật chống Appwrite dev (owner cấp qua
biến môi trường cục bộ, không cần thao tác Appwrite console) — toàn bộ trả
200 đúng kỳ vọng.

## 17. Phát hiện Image Studio

`docs/reports/preprod-image-translation-tts-audit.md`. SẠCH, không sửa gì.
Quick Free thật sự miễn phí; Community Free trung thực về trạng thái không
khả dụng; kill-switch Shared Premium chặn đúng cả hai chiều; `MockWalletStore`
giữ/chốt/hoàn tiền qua một điểm ghi duy nhất, không đúp; giới hạn mock-only
đã ghi tài liệu trung thực (DEFERRED, chấp nhận được); BYOP mã hoá khi lưu;
lỗi provider không lộ nội dung thật.

## 18. Phát hiện Translation/TTS

Cùng báo cáo mục 17. SẠCH, không sửa gì. Thiếu env provider không crash;
dây chuyền dự phòng Cerebras→Groq đúng; `TRANSLATION_ALLOW_PAID_PROVIDER`
chặn hai lớp; `translation_integrity.py` có 5 kiểm tra cụ thể; TTS dùng
chung đúng một đường claim/lease/fencing với `main.recover_stale_jobs()`.

## 19. Kết quả smoke test tự lưu trữ thật

Chống `https://appwrite-dev.fanfic.world/v1`, dữ liệu dùng-một-lần:

| Khu vực | Kết quả |
|---|---|
| AUTH + PROFILE + GAMIFICATION | **19/19** (mở rộng `smoke_test_selfhost_appwrite.py`: đăng ký/đăng nhập/`/me`/đăng xuất thật + streak/quest/XP/cosmetics/leaderboard/Image Studio metadata) |
| ANIMATION + TRUSTED VIDEO | **19/19** (`smoke_test_selfhost_trusted_sources.py`) |
| WEBSUB | **14/14** (`smoke_test_selfhost_websub.py`) |
| ADMIN qua HTTP+auth thật | **Hết BLOCKED** trong lúc làm Phase 5 — role admin/owner hoá ra là biến môi trường cục bộ (`FAS_OWNER_USER_IDS`), không phải cột Appwrite; đã gọi thật `/api/admin/overview`, `/users`, `/animation/series`, `/sources`, `/imports`, `/events` — toàn bộ 200 |

## 20. Số lượng test đầy đủ

| Bộ | Kết quả |
|---|---|
| Backend (`server/tests`) | **2408/2408 pass** (1 skip — thiếu `.onnx.json` test model cục bộ, không liên quan) |
| Frontend (`web`, `npm test`) | **635/635 pass** |
| Frontend typecheck (`tsc --noEmit`) | Sạch |
| Frontend lint (`eslint .`) | 0 lỗi, 2 warning đã biết trước (`no-img-element` ở Image Studio, chấp nhận được) |
| Frontend build (`npm run build`) | Thành công |
| Quét secret (lịch sử git + diff nhánh) | Sạch — không `.env` nào được track, không mẫu secret nào trong diff |

So với baseline Phase 0 (2375/2375 backend, 635/635 frontend): backend +33
test (fuzz corpus Phase 7, resilience Phase 10, không có test nào bị xoá).

## 21. Blocker đã biết (còn treo, không phải lỗi của đợt hardening này)

1. **YouTube WebSub end-to-end thật**: cần một callback HTTPS công khai —
   môi trường dev này không có, và theo đúng chỉ thị an toàn, KHÔNG được lách
   qua bằng tunnel/triển khai hạ tầng mới. Đã kiểm bằng mô phỏng (WebSub
   simulate 14/14) thay cho E2E thật.
2. **Ví Fanfic Credit theo từng người dùng bền vững**: hiện chỉ có
   `MockWalletStore` (trong bộ nhớ, mô phỏng kiến trúc ledger) — sổ cái bền
   vững thật theo người dùng vẫn là việc DEFERRED, có tài liệu hoá rõ trong
   `docs/WEB_README.md` sau Phase 16.
3. **Dữ liệu profile production (Appwrite Cloud)**: khả năng lịch sử có bản
   ghi profile bị ảnh hưởng bởi lỗi datetime-chuỗi-rỗng (đã sửa ở `8b1c544`
   cho code, nhưng KHÔNG chạm dữ liệu production) — việc dọn dữ liệu vẫn
   DEFERRED cho tới khi quyền truy cập Appwrite Cloud production được khôi
   phục. Không được tự ý thực hiện trong đợt này.

## 22. Việc cần thao tác tay (không tự động hoá được)

- Gán role admin/owner cho MỘT tài khoản Appwrite THẬT trên
  `appwrite-dev.fanfic.world` qua console (nếu muốn test qua UI thật với tài
  khoản cố định, thay vì tiến trình backend tạm cấp quyền qua biến môi
  trường cục bộ như đã làm ở Phase 5/6).
- Xem xét bổ sung `fanfic-worker-health-prod.{service,timer}` (watchdog) cho
  production — hiện chỉ staging có (Phase 14, khuyến nghị vận hành).
- Quyết định có viết lại toàn bộ `docs/HANDOFF.md` hay giữ banner trỏ sang
  tài liệu mới (đã làm ở Phase 17) — cần người đọc cả hai đánh giá Phase 16
  (`preprod-doc-consistency-audit.md`, xếp BLOCKER) trước khi quyết định.
  Đề xuất **khuyến nghị**: giữ banner (đã làm) trong đợt này, xem xét viết
  lại toàn bộ như một task riêng có phạm vi rõ ràng.
- Dọn 2 user thử nghiệm (`smoke-*@fanficdev.invalid`) trên
  `appwrite-dev.fanfic.world` qua console nếu muốn (không bắt buộc — dữ liệu
  rác vô hại, không có quyền tự xoá từ script).
- Khi Appwrite Cloud production truy cập lại được: chạy audit/migration dữ
  liệu profile datetime (mục 21.3) — có script dry-run sẵn
  (`scripts/audit_profiles_datetime_dry_run.py`, chưa chạy chống production).

## 23. Khuyến nghị

**READY FOR PRE-PRODUCTION TESTING TIẾP THEO** (giữ nguyên đánh giá từ
`integration/pre-prod-v1`, không hạ cấp). Toàn bộ 19 phase đã hoàn tất, không
phát hiện lỗ hổng bảo mật/phân quyền, hiệu năng 2 route chậm đã sửa, 3 lỗi
dữ liệu thật (case-insensitive parser, datetime-chuỗi-rỗng còn sót, N+1) đã
sửa và có test khoá bất biến, 2408/2408 backend + 635/635 frontend đều xanh,
build/typecheck/lint sạch, không secret nào lộ. 3 blocker đã biết (mục 21)
đều là quyết định sản phẩm/hạ tầng nằm ngoài phạm vi một đợt hardening code,
không phải khiếm khuyết mới phát sinh. Khuyến nghị **CÓ THỂ merge nhánh
overnight vào `integration/pre-prod-v1`** sau khi người dùng tự soát xét các
commit (đặc biệt Phase 13's schema/datetime fix và Phase 10's
`AppwriteUnavailableError`, vì cả hai đụng vào đường xác thực/dữ liệu).
