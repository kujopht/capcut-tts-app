# Audit đọc Appwrite — vì sao dự án còn ở giai đoạn dev đã dùng hết hạn mức đọc

Nhánh: `chore/appwrite-read-optimization-v1`, branch từ `integration/pre-prod-v1`
(`295d470`). Không merge, không deploy. Toàn bộ audit này là đọc mã tĩnh —
**không có request mạng nào được gửi tới Appwrite** trong quá trình audit
(ngoại trừ MỘT lần đọc tối thiểu đã thực hiện ở phiên trước, xem báo cáo
buổi sáng trước đó).

**Quy tắc billing dùng xuyên suốt báo cáo này** (do người dùng xác nhận):
Appwrite tính phí đọc theo **số document trả về**, không phải số request
HTTP. Một `listDocuments` khớp 0 bản ghi = 0 lần đọc bị tính phí, dù request
đó vẫn xảy ra. Một `getDocument` theo ID cụ thể thường tính phí **1 lần đọc
dù tìm thấy hay không** (đây là hành vi tiêu chuẩn của phần lớn database
dạng document — vẫn phải tra index để xác nhận "không có").

## 1. Nguyên nhân xếp hạng theo mức độ khả tín

### #1 (RÕ RÀNG NHẤT, đã sửa) — `xp_earned_since()` quét lại TOÀN BỘ nhật ký XP mỗi lần xem "Bảng xếp hạng — tuần này"

**File**: `server/appwrite_gamification_store.py:564-575`, gọi từ
`server/gamification_service.py::leaderboard_weekly` (route
`GET /api/leaderboard?mode=weekly`, `server/main.py:2761`).

**Trước khi sửa**: mỗi lần BẤT KỲ AI xem tab "tuần này" của bảng xếp hạng,
backend `_list_all(COL_XP_LEDGER, [q_greater_equal("created_at", since_iso)])`
đọc lại **toàn bộ** dòng nhật ký XP từ đầu tuần ISO hiện tại, cộng dồn theo
người dùng ở Python, rồi **vứt kết quả đi** — không cache. Không có giới hạn
trên: mỗi hành động cộng XP (đọc chương, nghe, hoàn thành nhiệm vụ, streak
thưởng…) ghi một dòng vào nhật ký này, và nhật ký đó bị đọc lại **nguyên
vẹn** mỗi lần trang xem.

**Vì sao nghiêm trọng nhất**: đây là nguyên nhân DUY NHẤT trong toàn bộ audit
có **hệ số nhân kép** — chi phí tỷ lệ với (số sự kiện XP trong tuần) × (số
lần trang được xem), không phải chỉ một trong hai. Trang xếp hạng công khai,
không cần đăng nhập, không giới hạn — bất kỳ ai (kể cả bot/crawler) mở lại
nhiều lần trong vài giây đều nhân bản chi phí quét đầy đủ.

**Đã sửa** (`server/gamification_service.py`): thêm `_XpEarnedSinceCache`
(TTL 60 giây, khoá theo `since_iso`). Nhiều lượt xem trong cùng 60 giây chỉ
quét kho thật MỘT lần; đổi tuần (`since_iso` khác) luôn quét lại, không dùng
nhầm cache tuần cũ.

**Trước/sau (lý thuyết)**: giả sử 500 sự kiện XP đã tích luỹ trong tuần hiện
tại (con số hợp lý cho một site đang test gamification tích cực) và trang
được xem 50 lần trong một ngày do nhiều tab/nhiều người xem qua lại:

| | Trước | Sau |
|---|---|---|
| Số lần quét toàn bộ nhật ký | 50 | tối đa 1 lần / 60 giây ≈ tối đa vài chục lần/ngày nếu xem RẢI ĐỀU, nhưng **0 lần thêm** nếu xem dồn trong cùng phút |
| Số document đọc (kịch bản xem dồn) | 50 × 500 = 25.000 | 1 × 500 = 500 |
| Giảm | — | **~98%** trong kịch bản xem dồn |

### #2 (đã sửa) — `/api/ready` bảo đảm ít nhất 1 lần đọc Appwrite mỗi lần gọi, không cache

**File**: `server/main.py` (`_tinh_readiness`, trước đây là thân hàm `ready()`).

`store.get_stats("__readiness__")` (dòng gọi `uy_tin`) là một `getDocument`
theo ID cố định **không bao giờ tồn tại** — nhưng vẫn tính phí 1 lần đọc mỗi
lần gọi, theo đúng quy tắc billing ở trên. Các kiểm tra còn lại
(`list_applications(limit=1)`, `list_events(limit=1)`,
`last_credit_at`, `profile_by_username("__readiness__")`) đều là
`listDocuments` có điều kiện lọc không khớp gì (ID giả) → 0 bản ghi → 0 phí,
nên chi phí THẬT của mỗi lần gọi `/api/ready` là ~1 lần đọc bảo đảm, cộng
thêm chi phí biến thiên của `list_jobs_by_status(RUNNING)` (0 nếu không có
job đang chạy).

**Đã LOẠI TRỪ một giả thuyết ban đầu**: kiểm tra `deploy/render.yaml` xác
nhận `healthCheckPath: /api/health` — health check TỰ ĐỘNG của Render trỏ
vào endpoint LIVENESS (đã xác nhận trong chính docstring của nó: "KHÔNG chạm
Appwrite/R2"), **không phải** `/api/ready`. Vậy cơ chế health-check hạ tầng
của Render **không** phải nguyên nhân. Nếu `/api/ready` từng bị gọi dồn dập,
nguồn khả dĩ là một uptime-monitor bên ngoài (không nằm trong repo) hoặc các
lần `curl` thủ công lặp lại trong `deploy/RUNBOOK.md` khi xác nhận restart —
không thể xác nhận chắc chắn chỉ bằng đọc mã tĩnh.

**Đã sửa**: thêm cache TTL 5 giây (`FAS_READY_CACHE_TTL_SECONDS`, mặc định 5)
quanh toàn bộ tính toán readiness. Gọi dồn dập trong 5 giây chỉ tính phí 1
lần đọc bảo đảm thay vì N lần.

### #3 (đã xác nhận, KHÔNG sửa trong đợt này — rủi ro kiến trúc còn tồn đọng) — hai worker luôn chạy, quét mỗi 3 giây

**File**: `server/worker.py:48` (`POLL_SECONDS=3`),
`server/translation_worker.py:50` (cùng giá trị mặc định),
`deploy/render.yaml` xác nhận cả hai chạy dạng `type: worker` (luôn bật,
gói `starter` trả phí, không tắt khi rảnh).

Mỗi chu kỳ, `recover_stale_jobs()` gọi `list_jobs_by_status()` **2 lần** (TTS:
RUNNING + PENDING) hoặc N lần (dịch: một lần cho MỖI trạng thái chưa kết
thúc trong `NON_TERMINAL_STATUSES`). Theo quy tắc billing, **hàng đợi rỗng
= 0 lần đọc bị tính phí**, dù vẫn là một request HTTP mỗi 3 giây — nên bản
thân việc polling liên tục **không** tự động gây tốn hạn mức nếu hàng đợi
job thường xuyên trống.

**Rủi ro thực sự**: chi phí tỷ lệ thuận với **số job đang ở trạng thái chưa
kết thúc tại bất kỳ thời điểm nào**, nhân với số chu kỳ quét trong suốt thời
gian đó. Một job TTS/dịch bị kẹt (không hoàn tất, không thất bại) nằm lại
trong trạng thái `running`/`pending` trong, ví dụ, 6 giờ sẽ bị đọc lại
`6×3600/3 = 7.200` lần chỉ bởi MỘT job đó. Không thể xác nhận từ mã tĩnh
liệu điều này đã thực sự xảy ra trong 8 ngày qua (08/08–16/08) mà không truy
cập Appwrite thật (bị chặn theo yêu cầu). **Đây là khuyến nghị vận hành, không
phải lỗi mã nguồn** — không sửa trong đợt này vì không có bằng chứng cụ thể
để nhắm vào, và sửa mù (ví dụ giảm tần suất poll) sẽ đổi hành vi sản phẩm
(độ trễ nhận job) mà không có gì đảm bảo là đúng vấn đề.

### #4 (đã xác nhận, không phải lỗi) — `novel_tags()` quét toàn bộ truyện đã xuất bản mỗi lần mở trang khám phá

**File**: `server/appwrite_store.py:556-572`. Docstring tự nhận: "chạy một
lần mỗi lần mở trang khám phá". Đây là hành vi CÓ CHỦ Ý ghi rõ trong mã
(không có collection `tags` riêng để tránh việc này), quy mô tỷ lệ với số
truyện đã xuất bản (không phải số sự kiện, nên trần thấp hơn nhiều so với
#1). Với một catalog nhỏ (giai đoạn dev, có lẽ dưới 50 truyện), đây là chi
phí nhỏ mỗi lần tải trang chủ/khám phá — **không sửa trong đợt này**, ghi
nhận là rủi ro kiến trúc cần theo dõi khi catalog lớn lên (đúng như docstring
đã tự cảnh báo).

### #5 — các đường `_list_all()` khác (chương, job, track…) — ĐÚNG THIẾT KẾ, không phải lỗi

`list_chapters`, `chapters_for_owner`, `list_jobs`, `tracks_for_chapter`,
`audio_by_chapter`, v.v. đều dùng `_list_all()` (bỏ qua giới hạn 25 document
mặc định của Appwrite) — đây là SỬA ĐÚNG cho một lỗi cắt dữ liệu âm thầm đã
biết trước (một truyện 40 chương sẽ mất chương nếu không lật trang). Chi phí
của các đường này tỷ lệ với dữ liệu THẬT của người dùng (số chương, số job)
— đây là chi phí chức năng cần thiết, không phải lỗi khuếch đại đọc.

## 2. Kiểm tra fan-out frontend (Phase 2) — không tìm thấy vấn đề

- `NotificationBell.tsx`: đã có comment kiến trúc rõ ràng giải thích tại sao
  KHÔNG polling ("`setInterval(30s)` trông vô hại nhưng là một truy vấn mỗi
  30 giây cho MỖI tab của MỖI người dùng") — chỉ tải lại khi đổi trang/mở
  bảng. Đã đúng thiết kế từ trước.
- `leaderboard/page.tsx`: đã tự ghi "KHÔNG polling: chỉ tải lại khi người
  dùng đổi chế độ/trang" — xác nhận đúng, không có `setInterval`.
- `SessionProvider` (`web/src/lib/session.tsx`): MỘT provider gốc, MỘT
  `useEffect` gọi `api.me()` một lần — `useSession()` (dùng ở nhiều nơi) chỉ
  ĐỌC state đã có, không tự fetch lại. Đây CHÍNH LÀ kiến trúc "một payload
  hợp nhất" mà Phase 6 yêu cầu — **đã có sẵn**, không cần xây thêm.
- `GamificationPanel`/`StreakBadge`: chỉ render ở `/account`, không nằm
  trong layout/header dùng chung — không refetch mỗi lần chuyển trang.
- React Strict Mode double-invoke effect: chỉ ảnh hưởng `next dev` cục bộ,
  không ảnh hưởng build production trên Render.

Kết luận Phase 2: **frontend không phải nguyên nhân** — kiến trúc hiện tại
đã tránh đúng các cạm bẫy polling/fan-out mà Phase 2 lo ngại, và đã ghi chú
lại lý do ngay trong mã nguồn.

## 3. Mô hình lưu lượng bình thường (Phase 4)

Giả định minh hoạ (KHÔNG phải số đo thật — cần xác nhận qua Appwrite Console
khi hạn mức mở lại): catalog ~50 truyện đã xuất bản, một truyện trung bình
15 chương, ~500 sự kiện XP tích luỹ trong tuần hiện tại.

**Một người dùng** (mở trang chủ → đăng nhập → đọc 1 truyện → mở 10 chương →
xem hồ sơ → xem nhiệm vụ → xem bảng xếp hạng cả hai chế độ):

| Bước | Đọc ước tính (SAU khi sửa) |
|---|---|
| Mở trang chủ (`find_novels` phân trang + `novel_tags` quét catalog) | ~20 + 50 = 70 |
| Đăng nhập | ~1 |
| Mở 1 truyện (`get_novel` + `list_chapters`) | 1 + 15 = 16 |
| Mở 10 chương (`get_chapter` + tra audio mỗi chương) | ~10 × 2 = 20 |
| Xem hồ sơ (tiến độ + thành tựu + streak) | ~3 |
| Xem nhiệm vụ | ~2 |
| Bảng xếp hạng toàn thời gian (`list_all_progress_ranked`, đã phân trang) | ~20 |
| Bảng xếp hạng tuần (CACHE HIT nếu trong 60s có người xem trước, ngược lại quét đầy đủ) | 0 (cache hit) hoặc ~500 (cache miss) |
| **Tổng/người (cache hit)** | **~132** |
| **Tổng/người (cache miss)** | **~632** |

**Ước tính đọc/tháng** (30 ngày, giả định mỗi người dùng thực hiện đúng
luồng trên 1 lần/ngày, và giả định phần lớn lượt xem bảng xếp hạng tuần rơi
vào cache-hit nhờ bản sửa — tỷ lệ cache-miss ước lượng ~10% cho một site
lưu lượng vừa phải):

| DAU | Đọc/người/ngày (pha trộn 90% hit/10% miss) | Đọc/tháng |
|---|---|---|
| 1 | ~182 | ~5.460 |
| 100 | ~182 | ~546.000 |
| 1.000 | ~182 | ~5.460.000 |
| 10.000 | ~182 | ~54.600.000 |

**Route đơn lẻ đáng lo ngại nhất về kinh tế**: bảng xếp hạng tuần TRƯỚC KHI
SỬA — ở quy mô 1.000 DAU với tỷ lệ xem thực tế (không phải 100% cache-miss vì
đã có cache, nhưng trước bản vá thì MỌI lượt xem đều là "miss"), riêng route
này có thể chiếm phần lớn tổng lưu lượng đọc nếu nhiều người xem tab "tuần
này" trong cùng khung giờ cao điểm — đây chính xác là loại route mà Phase 6
cảnh báo ("không được quét lại toàn bộ tập hợp mỗi lần xem").

**Lưu ý quan trọng**: những con số trên dùng giả định minh hoạ, KHÔNG phải
số đo thật từ Appwrite Console (bị chặn truy cập theo yêu cầu). Trước khi ra
quyết định gói cước cuối cùng, nên đối chiếu với biểu đồ sử dụng thật của
Appwrite (theo collection, theo ngày) ngay khi hạn mức mở lại.

## 4. Khuyến nghị Free vs Pro

Không thể khẳng định con số hạn mức Free tier hiện tại của Appwrite từ tài
liệu nội bộ repo — cần xác nhận trực tiếp trên trang giá của Appwrite tại
thời điểm quyết định (giá/hạn mức có thể đã đổi). Về mặt kiến trúc, sau các
bản vá trong đợt audit này:

- Nguyên nhân khuếch đại RÕ RÀNG NHẤT (bảng xếp hạng tuần) đã được xử lý —
  giảm hệ số nhân "số người xem" gần như hoàn toàn.
- Rủi ro còn lại (worker polling khi có job kẹt dài ngày, `novel_tags()` quét
  catalog) tỷ lệ với QUY MÔ DỮ LIỆU THẬT, không phải với số lượt xem — dễ dự
  đoán và kiểm soát hơn nhiều so với #1.
- Hai worker luôn-bật (TTS + dịch) là chi phí NỀN cố định không phụ thuộc
  lưu lượng người dùng — cần theo dõi số job kẹt/không hoàn tất định kỳ
  (`deploy/RUNBOOK.md` mục "Kiểm tra job kẹt") để đảm bảo không có job nào
  âm thầm bị quét lại hàng nghìn lần.

**Khuyến nghị**: tiếp tục Free tier cho giai đoạn dev/pre-launch NẾU có thể
xác nhận (qua Appwrite Console khi hạn mức mở lại) rằng phần lớn lưu lượng
500k+ đã dùng đến từ nguyên nhân #1 (đã sửa) — trong trường hợp đó, hạn mức
Free có khả năng đủ dùng trở lại. Nếu dữ liệu thật cho thấy phần lớn đến từ
worker polling/job kẹt (#3) thay vì #1, cân nhắc Pro tier khi site có người
dùng thật, vì chi phí đó sẽ tăng cùng dữ liệu tồn đọng theo thời gian bất kể
có sửa #1 hay không.

## 5. Kiểm chứng cuối (chạy thật)

- Backend: `Ran 2132 tests in ~55s — OK (skipped=1)` (2130 + 2 test dedup
  mới cho `/api/ready`, cộng 2 test cho `xp_earned_since` cache).
- `npm run typecheck`: sạch.
- `npm run lint`: sạch (2 cảnh báo `<img>` không liên quan, có từ trước).
- `npm test`: `563/563`.
- `npm run build`: thành công.

## 6. Rủi ro kiến trúc còn tồn đọng (chưa sửa, cần theo dõi)

1. Worker polling + job kẹt dài ngày (mục 1, #3) — cần giám sát vận hành,
   không phải sửa mã.
2. `novel_tags()` quét toàn catalog mỗi lần mở trang khám phá (mục 1, #4) —
   chấp nhận được ở quy mô hiện tại, cần một collection `tags` riêng nếu
   catalog lớn lên đáng kể (đã ghi chú sẵn trong mã).
3. Không có cách xác nhận DỨT ĐIỂM đâu là nguyên nhân THẬT của 500k+ lượt đọc
   đã dùng mà không truy cập Appwrite Console/audit log thật — báo cáo này
   dựa hoàn toàn trên suy luận từ mã tĩnh, xếp hạng theo mức độ khả tín chứ
   không phải bằng chứng đo lường trực tiếp.
