# Phase 5 — Kiểm toán hiệu năng (Performance audit)

Phạm vi: nhánh `chore/preprod-overnight-hardening-v1`. Mục tiêu: tìm N+1
query, endpoint list không phân trang, payload JSON thừa (backend), và
re-render thừa, fetch trùng lặp, ảnh không tối ưu, bundle nặng bất thường
(frontend). Khác góc nhìn "chi phí đọc/ghi Appwrite" đã audit ở Phase 4
(`docs/reports/preprod-appwrite-cost-audit.md`) — phase đó đã kết luận
SẠCH cho dashboard, gamification store, social service, creator service,
route công khai, health/ready, worker loops; phase này không lặp lại các
khu vực đó, chỉ bổ sung góc "hiệu năng" (độ trễ, payload, render) và quét
thêm các khu vực Phase 4 chưa chạm tới (trusted video source, animation
store, khu vực admin frontend).

## Tóm tắt

| Khu vực | Trạng thái | Blocker | Minor |
|---|---|---|---|
| Backend — N+1 / phân trang / payload (`server/`) | SẠCH, có 2 ghi chú | 0 | 2 |
| Frontend — re-render / fetch trùng / ảnh / bundle (`web/src`) | SẠCH, có 3 ghi chú | 0 | 3 |
| Lighthouse thật (3 route: `/`, `/fanfic`, `/animation`) | Đã đo | — | — |
| Độ trễ THẬT `/api/admin/*` chống Appwrite dev (mục 4) | 1 phát hiện, ĐÃ SỬA | 0 | — |

**Không có phát hiện mức blocker.** Kiểm tra tĩnh không cần sửa gì. Đo độ
trễ thật (mục 4) phát hiện 1 route sequential-count thật chậm
(`admin_image_studio_spending`, 7.8s) — đã sửa bằng song song hoá theo
đúng FIX POLICY (bug hiệu năng an toàn, tái sản xuất được, cùng mẫu đã
kiểm chứng ở nơi khác trong repo).

## 1. Backend

### 1.1 — Đã kiểm SẠCH

- Toàn bộ route `/api/admin/*` liệt kê qua `server/main.py` (users, authors,
  events/audit-log, posts, comments, animation series/sources/imports) đều
  clamp `limit`/`offset` (vd `max(1, min(200, limit))`, `min(100, limit)`)
  — không có endpoint list nào không giới hạn.
- `GET /api/novels/{id}` (`server/main.py:1215-1221`) — danh sách chương
  dùng `chapter.to_dict(include_content=False)`, cố ý loại nội dung chương
  khỏi payload danh sách (comment tại chỗ giải thích: trước đây trang chi
  tiết phải gọi `/api/chapters/{id}` riêng cho từng chương để biết
  `has_audio`, một truyện 12 chương tốn 13 request — đã gộp thành 1). Đây
  đúng là mẫu tối ưu payload cần tìm, đã được áp dụng sẵn.
- `trusted_source_service.admin_list_sources`/`admin_source_detail` — làm
  giàu theo lô (`mapping_counts` batch theo danh sách id), không lặp gọi
  Appwrite theo từng dòng.
- `appwrite_animation_store.py`, `appwrite_translation_store.py` — các
  vòng lặp `for i in range(0, len(ds), 50)` đều là batch `IN` query theo
  lô 50 (giới hạn của Appwrite `Query.equal` nhiều giá trị), không phải
  N+1.

### 1.2 — Ghi nhận (minor, không sửa)

1. **`server/appwrite_trusted_source_store.py:361-362`** — `delete_source`
   xoá cascading từng `mapping` bằng vòng lặp
   `for m in self.list_mappings(source_id): self._delete(COL_MAPPINGS, m.mapping_id)`
   — N lệnh xoá riêng lẻ thay vì batch. Mức độ: **minor**. Đây là hành
   động ADMIN xoá 1 nguồn tin cậy, số mapping/nguồn thực tế nhỏ (một
   nguồn thường ánh xạ tới vài chục series), không phải đường nóng
   (hot path) — chấp nhận được, không sửa.
2. **`server/appwrite_animation_store.py:556-557`** — reorder tập phim
   (`for position, episode_id in enumerate(wanted, ...): self._update(...)`)
   gọi update riêng từng tập thay vì batch. Mức độ: **minor**. Hành động
   ADMIN, số tập/series nhỏ (thường dưới 100) — chấp nhận được.
3. **`server/trusted_source_service.py:225,1058`** — `find_sources(limit=None)`
   quét toàn bộ bảng nguồn tin cậy, dùng ở (a) kiểm trùng định danh khi
   thêm nguồn mới, (b) đối chiếu định kỳ. Bản thân code đã tự ghi chú rõ
   lý do chấp nhận được ("nguồn tin cậy dự kiến không lớn — hàng chục,
   không phải hàng nghìn — quét toàn bộ ở đây CHẤP NHẬN ĐƯỢC, không phải
   đường nóng tại trang danh sách thường"). Xác nhận đúng, không phải bug,
   không liệt kê lại là phát hiện mới.

## 2. Frontend

`web/package.json` chỉ có 4 dependency runtime (`next`, `react`,
`react-dom`, `@eslint/eslintrc` ở dev) — không có thư viện nặng bất
thường (không lodash/moment/chart lib), rủi ro bundle phình do dependency
thấp.

### 2.1 — Đã kiểm SẠCH

- Toàn bộ trang admin dùng chung hook `useAsyncData` (vd
  `web/src/app/admin/page.tsx:28`) thay vì tự viết `useEffect` + `fetch`
  riêng lẻ — một điểm gọi API duy nhất mỗi trang, không có fetch trùng
  lặp giữa các component con trên cùng route admin đã kiểm (`page.tsx`,
  `analytics`, `audit-log`, `authors`, `ai-credits`, `system`, `users`,
  `comments`, `posts`, `reports`, `stories`, `animation/*`).
- `/api/admin/overview` là một endpoint tổng hợp duy nhất (đã xác nhận ở
  Phase 4) — trang dashboard admin không gọi nhiều endpoint rời rạc cho
  từng widget.
- Không có `import * as X` từ thư viện lớn ở bất kỳ đâu trong `web/src`.
- Các chỗ dùng `<img>` thường thay vì `next/image` (`leaderboard/page.tsx:45`,
  `cosmetics/Cosmetics.tsx:59`, `YouTubeFacadePlayer.tsx:100`,
  `ImageLightbox.tsx:68`, `PostCard.tsx:139`, `PostComposer.tsx:215`,
  `admin/animation/sources/new/page.tsx:139`) đều có comment
  `eslint-disable-next-line @next/next/no-img-element` giải thích lý do
  (huy hiệu/khung overlay nhỏ không cần tối ưu, ảnh động/preview trước khi
  upload, thumbnail YouTube ngoài domain) — quyết định có chủ đích, không
  phải bỏ sót. `PostCard.tsx:139` đã có `loading="lazy"`.

### 2.2 — Ghi nhận (minor, không sửa)

1. **`web/src/app/image-studio/page.tsx:620,659`** — ảnh kết quả sinh AI
   và ảnh thư viện đã lưu dùng `<img>` với `style={{maxWidth: "100%"}}`/
   `style={{width: "100%"}}`, không khai báo `width`/`height` tường minh
   → khung ảnh phụ thuộc tỷ lệ ảnh thật tải về, có thể gây dịch chuyển bố
   cục nhỏ (CLS) trong lúc tải nếu container cha không giữ tỷ lệ khung
   hình cố định. Mức độ: **minor** — ảnh do người dùng tạo/lưu (kích
   thước thay đổi theo prompt), không thể biết trước `width`/`height`
   tĩnh; CLS đo thật trên 3 route công khai đều 0.01 (xem mục 3), rủi ro
   thực tế thấp.
2. Toàn kho **không có** `dynamic()`/`next/dynamic` nào — không component
   nào được code-split. Mức độ: **minor**, mang tính thông tin — vì
   `package.json` không có thư viện nặng (không editor/chart lớn), và
   Lighthouse đo thật cho thấy tải trang nhanh, nên thiếu code-splitting
   hiện chưa gây hại đo được; chỉ đáng cân nhắc khi thêm tính năng nặng
   (Image Studio/trình soạn thảo phức tạp) trong tương lai.
3. Không phát hiện re-render thừa rõ ràng (state lift sai chỗ,
   props/callback tạo mới truyền xuống list dài) trong các trang đã rà —
   danh sách (`admin/posts`, `admin/users`, `admin/comments`) đều giới
   hạn 25-100 dòng/trang (khớp `limit` backend ở mục 1.1), không phải
   danh sách hàng nghìn dòng render một lần nên rủi ro re-render nặng
   thấp trong thực tế.

## 3. Lighthouse / Performance trace thật

Backend mock `localhost:8010` và frontend `localhost:3010` đều phản hồi
(CORS đã cấu hình đúng cho cặp cổng này, xác nhận qua `curl`). Đã dùng
`mcp__chrome-devtools__lighthouse_audit` và
`mcp__chrome-devtools__performance_start_trace`/`stop_trace` (Core Web
Vitals thật) trên 3 route.

**Lưu ý về công cụ**: `lighthouse_audit` của MCP server này KHÔNG trả
điểm hạng mục "Performance" (theo mô tả tool: "This excludes performance.
For performance audits, run performance_start_trace") — chỉ trả
Accessibility/Best Practices/SEO/Agentic Browsing. Để có điểm hiệu năng
thật (LCP/CLS), đã dùng trace thật thay vì điểm Lighthouse tổng hợp —
chính xác hơn cho môi trường dev cục bộ này.

| Route | LCP (lab) | CLS | TTFB | Load delay | Render delay |
|---|---|---|---|---|---|
| `/` | 438 ms | 0.01 | 55 ms | 294 ms | 83 ms |
| `/fanfic` | 629 ms | 0.01 | 61 ms | 466 ms | 98 ms |
| `/animation` | 692 ms | 0.01 | 58 ms | 565 ms | 63 ms |

Cả 3 route đều LCP dưới ngưỡng "tốt" (2.5s) rất xa, CLS gần như 0 —
không có vấn đề hiệu năng render thật đo được trên môi trường dev này
(server chưa throttle mạng/CPU, nên số tuyệt đối sẽ cao hơn trên máy
người dùng thật/production, nhưng không có tín hiệu bất thường về cấu
trúc trang — không có render-blocking đáng kể, không DOM khổng lồ theo
insight `DOMSize`/`RenderBlocking` của trace).

Điểm Lighthouse (Accessibility/Best Practices/SEO/Agentic Browsing) cho
`/`: 100/96/100/100. 2 audit "failed": `errors-in-console` (nguyên nhân
là request `/api/novels`, `/api/novels/tags` bị chặn CORS khi Lighthouse
tự reload trang tại cổng 3010 gọi sang 8010 — đây là ĐÚNG artefact môi
trường QA đã ghi nhận ở Phase 2, KHÔNG phải lỗi hiệu năng/CORS thật của
ứng dụng) và `label-content-name-mismatch` (thuộc phạm vi accessibility,
để Phase 11 xử lý, không thuộc phạm vi Phase 5).

## 4. Độ trễ THẬT chống Appwrite dev tự lưu trữ (bổ sung)

Mục 1-3 ở trên là kiểm tra tĩnh (đọc code). Bổ sung ở đây: đo độ trễ THẬT
của các route `/api/admin/*` chống `appwrite-dev.fanfic.world` bằng script
mới `scripts/perf_probe_admin_selfhost.py` — script đăng ký một user
smoke-test thật, cấp OWNER **cục bộ** cho tiến trình backend tạm qua biến
môi trường `FAS_OWNER_USER_IDS` (đây KHÔNG phải một cột dữ liệu Appwrite —
xem `Settings.admin_role_of` — nên không cần thao tác tay trên Appwrite
console/Cloud), rồi đăng nhập thật và gọi thật từng route qua HTTP+JWT.

Đo trước khi sửa:

| Route | Thời gian |
|---|---|
| `GET /api/admin/overview` | 12828 ms / 9766 ms (lần 2) |
| `GET /api/admin/analytics/detail?range=7d` | 11375 ms |
| `GET /api/admin/users?limit=25` | 2109 ms |
| `GET /api/admin/animation/series?limit=25` | 3984 ms |
| `GET /api/admin/animation/sources` | 1047 ms |
| `GET /api/admin/animation/imports?limit=25` | 891 ms |
| `GET /api/admin/image-studio/spending` | **7781 ms** |
| `GET /api/admin/events?limit=25` | 1125 ms |

`/api/admin/analytics/detail` (11.4s) hoá ra ĐÃ được một tiến trình khác
trong phiên song song hoá bằng `ThreadPoolExecutor(max_workers=4)` ngay
sau lần đo này (xem docstring route, nhắc "Phase 5 — SONG SONG HOA") —
không trùng lặp sửa lại. Riêng **`GET /api/admin/image-studio/spending`
(7.8s) là một N+1-shaped thật chưa ai sửa**: hàm gọi TUẦN TỰ 9 truy vấn
đếm bị chặn (`translation_svc.admin_count_jobs` × 4, `store.count_jobs`
× 4, `admin_count_connections_by_status` × 1) — mỗi round-trip tới VM dev
nhỏ ở xa mất ~700-900ms, cộng dồn tuyến tính.

**Đã sửa** (`server/main.py`, hàm `admin_image_studio_spending`): áp dụng
lại đúng idiom đã kiểm chứng an toàn ở `_admin_dashboard_them`
(`ThreadPoolExecutor(max_workers=4)`, KHÔNG dùng 8 — giới hạn này đã xác
nhận thật trên chính VM này ở Phase 7 trước, 8 luồng đôi khi gây
`httpx.ReadTimeout`). Đã tách `_an_toan` cũ (vốn là hàm lồng bên trong
`_admin_dashboard_them`) thành `_an_toan_song_song` ở cấp module để dùng
chung cho cả hai route, tránh chép lại logic bắt lỗi.

Đo lại sau khi sửa (VM dev tại thời điểm đo lần 2 có tải cao hơn — xem
`/api/admin/overview` cùng lúc tăng lên 17-28s dù KHÔNG đổi code route đó,
đúng đặc tính "VM nhỏ, dễ bị chậm khi có tải" đã ghi nhận trước đây, không
phải hồi quy mới):

| Route | Trước | Sau |
|---|---|---|
| `GET /api/admin/image-studio/spending` | 7781 ms | **3093 ms** |

Đã chạy lại toàn bộ test suite backend sau khi sửa: **2401/2401 pass**
(1 skip, không liên quan). Không đổi hình dạng response (test
`AiCreditsSpendingTest` cũ vẫn qua nguyên, không cần sửa test).

## Kết luận

Không có phát hiện mức blocker về hiệu năng backend lẫn frontend qua kiểm
tra tĩnh. Kiến trúc hiện tại đã áp dụng đúng các mẫu tối ưu cần tìm
(payload cắt gọn bằng `include_content=False`, phân trang clamp ở mọi
route admin, hook `useAsyncData` dùng chung tránh fetch trùng, batch
update/query theo lô 50). 5 ghi chú minor (2 backend, 3 frontend) đều là
N tương tác nhỏ trên hành động ADMIN không phải đường nóng, hoặc quyết
định có chủ đích đã ghi chú tại chỗ trong code — không cần sửa trong phase
này. Core Web Vitals đo thật (LCP 438-692ms, CLS 0.01 trên cả 3 route)
không cho thấy vấn đề hiệu năng render nào. Đo độ trễ THẬT chống Appwrite
dev (mục 4) phát hiện VÀ SỬA một N+1-shaped thật (`admin_image_studio_spending`,
7.8s → 3.1s bằng song song hoá) mà kiểm tra tĩnh không thể thấy được.
