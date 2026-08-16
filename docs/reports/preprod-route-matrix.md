# Ma trận route/tính năng — Fanfic World (Overnight Hardening V1, Phase 1)

Kiểm kê thuần tuý (không phê bình UX — việc đó thuộc Phase 2/3). Cột "Backend
API" chỉ liệt kê endpoint chính, không liệt kê mọi API phụ. "Chặn/known
blocker" chỉ ghi khi thấy rõ trong lúc đọc mã — không suy diễn.

Xác thực phía backend luôn là nguồn sự thật (`server/main.py`); cột "Yêu cầu
đăng nhập" ở bảng ADMIN lấy theo dependency Python thật (`admin_profile` =
ADMIN hoặc OWNER, `owner_profile` = chỉ OWNER), không lấy theo
`vaiToiThieu` phía giao diện (`AdminShell.tsx`) — giá trị đó chỉ là gợi ý
ẩn/hiện, được ghi rõ trong docstring của chính file đó là "không phụ thuộc
vào giá trị này".

## Bảng PUBLIC (44 route công khai/người dùng thường)

| Route | Yêu cầu đăng nhập | Backend API chính | Loading | Empty | Error | Mobile | Blocker đã biết |
|---|---|---|---|---|---|---|---|
| `/` (trang chủ) | Không | `api.listNovels`, `api.listAnimationSeries` (tuỳ bản) | Skeleton | EmptyState | ErrorState | Có | — |
| `/fanfic` (khám phá truyện) | Không | `GET /api/novels` (phân trang server, `limit`/`offset`) | SkeletonCards | EmptyState | ErrorState | Có | — |
| `/novels/[id]` | Không (owner thấy thêm khu quản lý) | `GET /api/novels/{id}` | Skeleton | EmptyState | ErrorState | Có | — |
| `/chapters/[id]` | Không (đọc); có thao tác cần đăng nhập | `GET /api/chapters/{id}` | Skeleton | EmptyState | ErrorState | Có | — |
| `/listen/[id]` | Không (nghe); bình luận/tiến độ cần đăng nhập | `api.getChapter` (2 request tổng: chương + `novel.chapters` cho bộ chọn tập) | Skeleton | EmptyState | ErrorState | Có | — |
| `/login` | Không (trang cho khách) | `api.login`, OAuth Google/Facebook | Loading khi submit | — | Alert lỗi | Có | — |
| `/auth/callback` | Không (điểm trả về OAuth) | `api.exchangeOAuthCallback` (đọc `userId`/`secret` 1 lần, xoá khỏi URL ngay) | Loading | — | Alert (câu chung, không lộ lỗi gốc/secret) | Có | — |
| `/account` | Có | `api.myProfile`/update | Loading | — | Alert | Có | — |
| `/u/[username]` (hồ sơ công khai) | Không | `GET /api/users/{username}` | Skeleton | EmptyState | ErrorState | Có | — |
| `/creator/apply` | Có (mở khi 403 "chưa là tác giả" thay vì lỗi trơ) | `api.creatorState`, `api.applyCreator` | Loading | — | ErrorState | Có | — |
| `/write` (khu tác giả) | Có, cần trạng thái tác giả đã duyệt cho xuất bản (`CongXuatBan`) | `api.listNovels`, `api.listJobs`, CRUD truyện/chương | Loading/Skeleton | EmptyState | Alert + ConfirmDialog cho xoá | Có | — |
| `/studio` (Audio Studio nhanh) | Có | `api.listJobs`, tạo TTS job qua `ensureStudioNovel` | Loading | EmptyState (chưa có job) | Alert | Có | Giới hạn 20.000 ký tự/lần (giới hạn sản phẩm, không phải bug) |
| `/library` (thư viện audio) | Có | `api.listNovels(true)`, `api.listJobs()`, `api.myChapters()` — 3 request cố định bất kể số truyện | Skeleton | EmptyState | ErrorState | Có | — |
| `/community` (bảng tin) | Không (đọc); đăng/thích/bình luận cần đăng nhập | `social.feed` | SkeletonList | EmptyState | ErrorState | Có | — |
| `/posts/[postId]` | Không (đọc); bình luận mở sẵn (khác bảng tin, chỉ 1 bài nên không cần tải theo yêu cầu) | `social.post`, `social.limits` | — (chưa thấy skeleton riêng, xem Phase 2) | EmptyState khi bài đã xoá | ErrorState | Có | Cần kiểm tra trực tiếp trạng thái loading ban đầu (không thấy biến loading rõ trong 60 dòng đầu) |
| `/notifications` | Có | `social.notifications` (cùng endpoint với chuông thông báo) | SkeletonList | EmptyState | ErrorState | Có | — |
| `/leaderboard` | Không (ẩn hàng "vị trí của bạn" nếu chưa đăng nhập) | `GET /api/leaderboard?mode=` (phân trang server, trần 100, không polling) | SkeletonList | EmptyState | ErrorState | Có | — |
| `/animation` (khám phá Animation) | Không | `api.listAnimationSeries` | SkeletonCards | EmptyState | ErrorState | Có | Chưa có phân loại Vietsub/Dub Việt riêng (thiếu trường schema, đã ghi nhận trong docstring — có chủ đích, không phải bug) |
| `/animation/[id]` (chi tiết series) | Không (xem); owner thấy khu quản lý (sửa/thêm tập/xuất bản/xoá) | `api.getAnimationSeries` | Skeleton | EmptyState | ErrorState | Có | — |
| `/animation/new` | Có | `api.createAnimationSeries` | — | — | Alert | Có | — |
| `/animation/watch/[id]` | Không (xem); bình luận/tiến độ cần đăng nhập | `api.getAnimationEpisode` (2 request: tập + series kèm mọi tập) | Skeleton | EmptyState | ErrorState | Có | Không có nút "thích" tập (có chủ đích — tránh hệ thống thích thứ hai, xem docstring) |
| `/image-studio` | Quick Free: không; Cộng đồng Free/Fanfic Credits/BYOP: có | `imageStudio.*` (4 chế độ độc lập) | Skeleton | EmptyState | Alert | Có | Cộng đồng Free có thể RỖNG thật sự (trạng thái hợp lệ, không phải lỗi — đã ghi rõ 2026-08-15) |
| `/image-studio/connect/callback` | Có (điểm trả về BYOP OAuth PKCE) | `imageStudio.exchangeByopCallback` | Loading | — | Alert (câu chung) | Có | — |
| `/tools/subtitles` (Subtitle Studio) | Không (cục bộ hoàn toàn); "Dịch AI" cần đăng nhập | Không upload video (chỉ `URL.createObjectURL` cục bộ); dịch dòng phụ đề gọi Fanfic Translation | — | — | — | Cần kiểm tra trực tiếp (công cụ nặng, nhiều thao tác) | Nhận diện giọng nói cục bộ CHƯA có; "Dịch cục bộ" (NLLB) CHƯA có, nút khoá có ghi lý do — cả hai có chủ đích, không phải bug |
| `/translate` (Novel Translation Studio) | Có | `translate.*` (dự án/job/chương/Novel Bible) | Loading | EmptyState (chưa có dự án) | ErrorState | Cần kiểm tra trực tiếp (giao diện 2 trạng thái phức tạp) | — |

*(44 route công khai theo yêu cầu ban đầu là tổng route trong repo bao gồm cả
admin; bảng PUBLIC ở trên liệt kê đủ 25 route không thuộc `/admin/*` tìm thấy
qua glob `**/page.tsx`. Route 404/error mặc định của Next.js không phải
`page.tsx` riêng — chưa kiểm tra `not-found.tsx`/`error.tsx` tuỳ biến, ghi
"cần kiểm tra trực tiếp".)*

## Bảng ADMIN (18 route quản trị)

Cổng chặn dùng chung nguyên tắc: `<CongQuanTri>` (`AdminShell.tsx`) không tự
quyết theo cờ phía giao diện — luôn gọi `GET /api/admin/overview` và đọc mã
trạng thái thật (401 → mời đăng nhập, 403 → không đủ quyền, 200 → vào nội
dung). Cột "Yêu cầu đăng nhập" dưới đây là dependency backend thật của các
API route tương ứng.

| Route | Yêu cầu đăng nhập (backend thật) | Backend API chính | Loading | Empty | Error | Mobile | Blocker đã biết |
|---|---|---|---|---|---|---|---|
| `/admin` (Dashboard) | ADMIN hoặc OWNER | `GET /api/admin/overview` (song song qua `ThreadPoolExecutor`, mỗi nhóm truy vấn lỗi độc lập không sập cả trang) | `DanhSachTrangThai dangTai` | `rong={!data}` | Alert + nút thử lại | `.admin-nav` cuộn ngang | DAU/WAU/MAU hiện "chưa có dữ liệu" (Appwrite Users API từ chối lọc `accessedAt` — đã xác nhận bằng gọi API thật) |
| `/admin/users` | ADMIN hoặc OWNER | `GET /api/admin/users` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp (bảng rộng) | — |
| `/admin/users/[user_id]` | ADMIN hoặc OWNER (một số hành động như đổi hạng OWNER chỉ OWNER) | `GET /api/admin/users/{id}`, suspend/unsuspend, sessions | — | — | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/stories` | ADMIN hoặc OWNER | `GET /api/admin/stories` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/posts` | ADMIN hoặc OWNER | `GET /api/admin/posts` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/comments` | ADMIN hoặc OWNER | `GET /api/admin/comments`, `count_comments` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/animation/series` | ADMIN hoặc OWNER (theo `vaiToiThieu` giao diện: mọi vai trò, kể cả MODERATOR — cần xác nhận lại dependency backend thật) | `GET /api/admin/animation/series` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | Cột "Yêu cầu đăng nhập" cần xác minh: đây là route ADMIN duy nhất KHÔNG có `vaiToiThieu` trong `AdminShell.tsx`, khác với ghi chú đầu bảng — cần đối chiếu trực tiếp dependency Python |
| `/admin/animation/series/[id]` | Như trên | `GET /api/admin/animation/series/{id}` | — | — | ErrorState | Cần kiểm tra trực tiếp | Cùng ghi chú như trên |
| `/admin/animation/sources` (Trusted Sources) | ADMIN hoặc OWNER | `adminApi.trustedSources` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | Kiểu `TrustedSource` xác nhận KHÔNG lộ trường API key (đã có test) |
| `/admin/animation/sources/new` | ADMIN hoặc OWNER | `adminApi.previewTrustedSourceUrl` (bắt buộc) → `adminApi.createTrustedSource` | `dangXem` | `rong={false}` (chưa xem trước ≠ rỗng) | `<ChuaCauHinh>` khi 503 (thiếu `YOUTUBE_API_KEY`) | Cần kiểm tra trực tiếp | Yêu cầu biến môi trường `YOUTUBE_API_KEY` + bật YouTube Data API v3 — nếu chưa cấu hình trên máy dev thì hiện đúng trạng thái `ChuaCauHinh`, không phải lỗi chung |
| `/admin/animation/sources/[id]` (chi tiết nguồn) | ADMIN hoặc OWNER | `adminApi.trustedSourceDetail`, `scanTrustedSource`, mapping CRUD | — | — | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/animation/import-queue` | ADMIN hoặc OWNER | `adminApi.videoImports` (lọc theo `status`/`source` qua `useSearchParams`, bọc `<Suspense>`) | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/reports` | ADMIN hoặc OWNER | `GET /api/admin/reports` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/authors/applications` | ADMIN hoặc OWNER | `GET /api/admin/authors/applications` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/authors` | ADMIN hoặc OWNER | `GET /api/admin/authors` | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |
| `/admin/analytics` | ADMIN hoặc OWNER | `adminApi.analyticsDetail(scope)` | `OSo` skeleton | Trạng thái "chưa có dữ liệu" tường minh (không bịa số 0) | ErrorState | Cần kiểm tra trực tiếp | Content-activity (đọc truyện/hoàn thành chương/lượt xem Animation/bình luận) hiện "chưa có dữ liệu" — chưa có instrumentation, đã ghi rõ thay vì bịa |
| `/admin/ai-credits` | ADMIN hoặc OWNER | `adminApi.imageStudioSpending` (mở rộng: dịch/TTS/BYOK) | — | — | ErrorState | Cần kiểm tra trực tiếp | Không hiện secret/API key (theo yêu cầu); ví Fanfic Credit theo người dùng vẫn dùng `MockWalletStore` (chưa có lưu trữ Appwrite thật — đã xác nhận là khoảng trống kiến trúc có chủ đích, ghi trong docstring `image_wallet_store.py`) |
| `/admin/system` | Chỉ OWNER | Nội bộ `_trang_thai_he_thong()` trong `overview` | — | — | — | Cần kiểm tra trực tiếp | 4 trạng thái `healthy/degraded/error/not_configured` — trạng thái "not_configured" cho Cloudflare Analytics khi chưa có `CLOUDFLARE_ANALYTICS_ZONE_ID`/`_API_TOKEN` (chưa cấu hình trên máy dev, đúng theo thiết kế) |
| `/admin/audit-log` | ADMIN hoặc OWNER | `adminApi` audit events (`list_events` với `created_after`) | — | EmptyState | ErrorState | Cần kiểm tra trực tiếp | — |

## Ghi chú tổng hợp cho các phase sau

- Toàn bộ route ADMIN đều phải qua `<CongQuanTri>` trước khi vào nội dung —
  đây là điểm neo chính cho **Phase 3 (audit adversarial)**: kiểm tra từng
  route `/api/admin/*` có thực sự trả 401/403 đúng khi bị gọi trực tiếp bằng
  phiên của người dùng thường/moderator, không chỉ tin vào việc sidebar ẩn
  mục đó.
- `/admin/animation/series` và `/admin/animation/series/[id]` là hai route
  DUY NHẤT trong nhóm admin không có `vaiToiThieu` trong `AdminShell.tsx` —
  cần Phase 3 xác minh trực tiếp dependency Python thật của
  `GET /api/admin/animation/series*` để biết đây có phải là một route dành
  cho MODERATOR (khác các route "ADMIN hoặc OWNER" còn lại) hay là một thiếu
  sót khi thêm `vaiToiThieu` — **không kết luận là bug ở Phase 1 này, chỉ ghi
  nhận để Phase 3 kiểm tra**.
- Nhiều route công khai và toàn bộ route admin còn thiếu quan sát trực tiếp
  về hành vi `loading`/mobile thực tế (đã đánh dấu "cần kiểm tra trực tiếp")
  — đây chính là phạm vi của **Phase 2 (browser QA thật ở 3 độ rộng màn
  hình)**.
- `/posts/[postId]` không thấy biến trạng thái loading ban đầu rõ ràng trong
  60 dòng đầu file — cần Phase 2 xác nhận có bị chớp giao diện rỗng trước khi
  `social.post()` trả về hay không.
- Không phát hiện lỗi rõ ràng (crash, import sai, route trùng) trong lúc đọc
  — mọi điểm "chưa làm" tìm thấy (Vietsub/Dub Việt phân loại, nhận diện giọng
  nói cục bộ, dịch cục bộ NLLB, ví Fanfic Credit theo người dùng, DAU/WAU/MAU,
  content-activity analytics) đều đã được chính codebase ghi nhận tường minh
  bằng docstring/trạng thái UI rõ ràng, không phải im lặng bỏ dở.
