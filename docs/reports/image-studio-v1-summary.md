# Image Studio V1 — báo cáo tổng kết (overnight build)

Nhánh: `feature/image-studio-v1`, branch từ `feature/animation-v6` (`79ba675`).
Chưa merge, chưa deploy, chưa chạm production Appwrite, chưa mua Pollen thật,
chưa bật Auto Top-Up, chưa thực hiện giao dịch thanh toán thật nào.

## 1. Kiến trúc

Toàn bộ tính năng nằm trong các module `server/image_*.py` mới, tái sử dụng
kiến trúc đã có thay vì phát minh hệ thống song song:

| Module | Vai trò | Tái sử dụng từ |
|---|---|---|
| `image_domain.py` | Dataclass thuần (không phụ thuộc Appwrite/FastAPI) — `GenerationMode`, `WalletTransaction`, `GenerationReservation`, `ImageModelInfo`, `PollinationsConnection`, `SavedImage`. Tiền = số nguyên micro-credit (`MICRO_PER_CREDIT=100`), không dùng float. | Khuôn `server/domain.py`/`gamification_domain.py` |
| `image_wallet_store.py` | `MockWalletStore` — sổ cái append-only, KHÔNG update-in-place | Khuôn `gamification_store.py` |
| `image_provider_registry.py` | `QuickFreeImageProvider` (anonymous, không nhận tham số model), `SharedPremiumImageProvider` (Unified API, khoá server-side) | `translation_provider_registry.py` (cooldown/backoff pattern) |
| `image_community_catalogue.py` | `CommunityCatalogueCache` — khám phá động model cộng đồng giá 0 | — (mới, xem mục 4) |
| `image_pricing.py` | Tách chi phí provider (USD, nội bộ) khỏi giá Fanfic Credit hiển thị; markup/minimum charge cấu hình được | Nguyên tắc PHASE 8 |
| `image_byop_crypto.py` + `image_byop_service.py` | OAuth 2.1 Authorization Code + PKCE, mã hoá token tại chỗ | Tái dùng NGUYÊN VẸN `translation_byok_crypto.py::ByokCrypto` (AES-256-GCM), khoá master RIÊNG (`IMAGE_BYOP_MASTER_KEY`) |
| `image_payment.py` | `PaymentProvider` interface + `MockPaymentProvider` (test-mode) | — (mới; xác nhận KHÔNG có Stripe/PayOS nào tồn tại trước khi viết) |
| `image_spending_guard.py` | `SharedPremiumSpendingGuard` — ngân sách tháng, cảnh báo, kill switch, giới hạn đồng thời | — (mới) |
| `image_library_store.py` | `MockImageLibraryStore` — chỉ ảnh người dùng chủ động "Lưu" | Khuôn `gamification_store.py` |
| `image_service.py` | `ImageStudioService` — điều phối `estimate → reserve → gọi provider → settle/refund` | Nguyên tắc PHASE 5 |
| `config.py::ImageStudioSettings` | Đọc biến môi trường, `describe()` KHÔNG BAO GIỜ chứa secret | Khuôn `AppwriteSettings`/`R2Settings` |
| `main.py` | 20 route `/api/image/*` + `/api/admin/image-studio/*`, tái dùng `current_profile`/`admin_profile` (guard admin dùng CHUNG dependency với 27 route admin khác — không tạo guard yếu hơn) | — |

Frontend: `web/src/app/image-studio/page.tsx` (trang chính), `.../connect/callback/page.tsx`
(BYOP OAuth callback), `web/src/lib/api.ts::imageStudio` (export riêng, cùng
khuôn `translate`/`social`).

## 2. Bốn chế độ sinh ảnh

### A. Quick Free
Endpoint legacy ẩn danh (`image.pollinations.ai`), **không** key, **không**
header `Authorization`, **không** `?key=`. Cuộc dò thám `chore/pollinations-
anonymous-probe` đã chứng minh tham số `model=` bị bỏ qua/chuẩn hoá ẩn danh —
class `QuickFreeImageProvider` do đó **cấu trúc không cho phép** truyền tham
số model (không phải chỉ là quy ước hiển thị): nhãn cố định "Quick Free"/
"Auto model". Có rate limit theo IP (6 lần/phút) + cooldown khi lỗi liên
tiếp, timeout, lỗi được làm sạch trước khi hiển thị.

### B. Cộng đồng Free (bổ sung theo ADDENDUM)
**Khác Quick Free**: vẫn cần đăng nhập và vẫn gọi Unified API có xác thực
server-side — ADDENDUM: *"Unified/community generation may still require
Pollinations authentication"*. Chỉ riêng bước XEM DANH SÁCH là không cần key.

Nguồn dữ liệu THẬT đã xác minh bằng gọi thật (không đoán URL):

    GET https://gen.pollinations.ai/image/models

Trả 200 ẩn danh, mỗi phần tử có `output_modalities`, `pricing` (đơn vị
pollen), đôi khi `per_user_rpm`. Lọc **động** (không hard-code) theo:
`"image" in output_modalities` **và** mọi trường số trong `pricing` == 0.
Thiếu hoàn toàn trường `pricing` bị coi là **không xác định**, không được
suy diễn là miễn phí (fail-closed).

**Quét thật 2026-08-15**: 55 model có output ảnh, **0 model** đạt giá 0 —
danh sách hiện tại **hợp lệ nhưng rỗng**. Đây là trạng thái thật, không phải
lỗi (UI phân biệt rõ "rỗng hợp lệ" với "không lấy được danh sách" — lỗi
mạng). `vendouple/animagine` tồn tại và tài liệu công khai của nó
(nobindes.work.gd/docs) khớp bộ style được mô tả trong ADDENDUM (Isekai,
Fantasy, Cyberpunk, Horror, Mecha, Chibi…) nhưng giá hiện tại là 0.08
pollen/ảnh — **không miễn phí**. `muse-glimmer` (và các bản cộng đồng của
nó) bị loại đúng như yêu cầu: `output_modalities: ["text"]` — chỉ NHẬN ảnh
đầu vào, không SINH ảnh.

Sinh ảnh: `ImageStudioService.sinh_anh_cong_dong()` kiểm tra LẠI danh sách
NGAY TRƯỚC mỗi lần gọi (không dùng cache cũ quá hạn) — model có thể đã bị rút
khỏi danh sách miễn phí giữa hai lần bấm nút. Nếu không còn miễn phí:
`CommunityModelNoLongerFree` (HTTP 409) — **chặn hẳn, không tự động chuyển
sang Shared Premium/trừ Fanfic Credit** (yêu cầu tuyệt đối của ADDENDUM). Ghi
một bản ghi reservation/settle 0-đồng để có dấu vết kiểm toán nhất quán với
Shared Premium.

### C. Fanfic Credits (Shared Premium)
Unified API qua `POLLINATIONS_API_KEY` server-side — **không bao giờ** gửi
xuống trình duyệt. Allowlist khởi động (6 model, xem `image_pricing.py`):
Flux, Z-Image, GPT Image 2, GPT Image, GPT Image (Large), Nano Banana Pro.
Luồng: `estimate → verify balance → reserve → gọi provider → settle/refund`,
idempotency_key chặn tính tiền hai lần khi thử lại.

### D. My Pollinations (BYOP)
OAuth 2.1 Authorization Code + PKCE **thật**, xác nhận qua RFC 8414 discovery
thật từ `enter.pollinations.ai/.well-known/oauth-authorization-server` (không
đoán URL): `authorization_endpoint`, `token_endpoint`, `scopes_supported =
["profile","usage","keys"]`, `code_challenge_methods_supported=["S256"]`.
Chỉ xin scope `"keys"` tối thiểu. CSRF `state` dùng một lần, PKCE S256, token
mã hoá tại chỗ (AES-256-GCM, khoá `IMAGE_BYOP_MASTER_KEY` riêng biệt với
`TRANSLATION_BYOK_MASTER_KEY`). Pollinations không công bố
`revocation_endpoint` — "Ngắt kết nối" là xoá token phía Fanfic World, ghi rõ
trong code để không ai tưởng nhầm có API revoke thật. Dùng Pollen cá nhân,
**không bao giờ** chạm Fanfic Credit, **không bao giờ** tự động dùng khoá
dùng chung khi lỗi.

## 3. Kinh tế Fanfic Credit (ví/sổ cái)

Không có hệ thống ví/credit nào tồn tại trước đó trong repo (đã audit). Xây
mới theo NGỮ NGHĨA SỔ CÁI, không phải một con số bị trừ trực tiếp:

- Mọi thay đổi là MỘT giao dịch mới (`WalletTransaction`, append-only).
- Số dư = tổng sổ cái, tính lại lúc đọc — không có trường "balance" có thể
  bị ghi đè.
- `idempotency_key` là điểm chặn trùng DUY NHẤT (`_ghi_giao_dich`) — thử lại
  cùng khoá trả về đúng giao dịch cũ, không tạo bản ghi/không trừ tiền lần
  hai (test bắt được một lỗi tính tiền thật trước khi ship).
- Vòng đời: `reserve → settle` (thành công) hoặc `refund`/`release` (thất
  bại/huỷ trước khi gọi provider — hai ngữ nghĩa kế toán khác nhau dù cùng
  hoàn tiền).
- Đơn vị nguyên (`MICRO_PER_CREDIT=100`), không dùng float.
- `pricing_snapshot_version` ghi lại phiên bản giá tại thời điểm ước tính —
  đổi markup sau này KHÔNG làm thay đổi giao dịch đã hoàn tất.

## 4. Thanh toán (mua Fanfic Credit)

**Chưa hề có payment provider nào trong repo trước overnight này** (grep
sạch server/ và web/, hai false positive đã loại). Vì vậy:

- ĐÃ triển khai: `PaymentProvider` interface (`tao_checkout`/`xac_nhan`/
  `hoan_tien`) + `MockPaymentProvider` — mô phỏng 3 trạng thái
  (pending/succeeded/failed), **không bao giờ gọi mạng, không bao giờ tính
  phí tiền thật**.
- ĐÃ triển khai: route checkout/xác nhận (`/api/image/checkout*`), đủ để UI
  happy-path và error-state kiểm thử được.
- CHƯA làm và KHÔNG ĐƯỢC làm tối nay: tạo tài khoản Stripe/PayOS thật, thực
  hiện bất kỳ giao dịch thật nào. **Xác nhận: không có giao dịch tiền thật
  nào được thực hiện trong toàn bộ phiên làm việc này.**
- Còn thiếu để bật mua thật: (1) chọn nhà cung cấp thật (Stripe/PayOS), (2)
  viết `StripePaymentProvider`/tương đương implement đúng interface đã có,
  (3) cấu hình webhook xác nhận thanh toán (không tin trạng thái client tự
  báo — interface đã thiết kế sẵn cho việc này), (4) tài khoản merchant thật.
- Premium generation vẫn dùng được qua BYOP dù cổng mua Fanfic Credit riêng
  của site chưa có — đúng yêu cầu.

## 5. Cấu hình Pollinations (KHÔNG có giá trị secret nào trong tài liệu này)

**Shared Premium**: đặt `POLLINATIONS_API_KEY` (server `.env`) và
`IMAGE_SHARED_PREMIUM_ENABLED=true` để bật — hiện tại `.env` của máy này ĐÃ
có `POLLINATIONS_API_KEY` (từ trước, không phải overnight này thêm) nhưng
`IMAGE_SHARED_PREMIUM_ENABLED` CHƯA đặt → Shared Premium **vẫn tắt mặc
định** (kill switch tự động bật lúc khởi động khi cờ này tắt). Các biến ngân
sách: `IMAGE_MONTHLY_BUDGET_USD`, `IMAGE_WARNING_BUDGET_USD`,
`IMAGE_MAX_COST_PER_REQUEST_USD`, `IMAGE_MAX_CONCURRENT_SHARED_GENERATIONS`,
`IMAGE_MARKUP_MULTIPLIER`, `IMAGE_DISABLED_MODELS` — không hard-code số ví
dụ trong logic nghiệp vụ, chỉ là default của dataclass.

**BYOP**: cần đăng ký một Pollinations App để lấy `POLLINATIONS_CLIENT_ID`
(dạng `pk_...`, publishable — an toàn để lộ), đặt `IMAGE_BYOP_MASTER_KEY`
(khoá AES riêng, tạo bằng cùng phương pháp `TRANSLATION_BYOK_MASTER_KEY`) và
`IMAGE_BYOP_REDIRECT_URI` (phải khớp CHÍNH XÁC redirect URI đã đăng ký với
Pollinations). Hiện CẢ BA biến này đều chưa đặt trên máy này → BYOP đang ở
sau feature flag (`enabled = crypto is not None`), tắt an toàn.

**Auto Top-Up (một lần, thủ công, phía Pollinations)**: Fanfic World KHÔNG
tự động hoá/reverse-engineer việc này. Checklist cho chủ site:
1. Đăng nhập `enter.pollinations.ai` bằng tài khoản đã cấp `POLLINATIONS_API_KEY`.
2. Bật Auto Top-Up MỘT LẦN trong phần cài đặt tài khoản Pollinations, lưu
   phương thức thanh toán tại đó (Fanfic World không bao giờ thấy/lưu thông
   tin thẻ).
3. Từ đó Shared Premium tiêu thụ tài khoản Pollinations dùng chung; Pollinations
   tự quản lý việc nạp lại.

**Vệ chắn chi tiêu độc lập** (không phụ thuộc Auto Top-Up): chi tiêu bình
thường → Shared Premium khả dụng; chạm ngưỡng cảnh báo → ghi log có cấu trúc
cho vận hành (chưa có kênh thông báo thật vì Appwrite production đang bị
chặn); chạm hạn mức tháng → **tắt Shared Premium**, Quick Free/Cộng đồng
Free/BYOP vẫn dùng được. Có kill switch thủ công độc lập
(`/api/admin/image-studio/kill-switch`, guard `admin_profile`).

## 6. Lưu trữ / thư viện ảnh

KHÔNG lưu mọi ứng viên tạm — chỉ khi người dùng bấm "Lưu" mới ghi qua
`MockImageLibraryStore` (khuôn `gamification_store`, sẵn sàng thay bằng
Appwrite thật khi production được mở lại). Ảnh tạm (retry/idempotency) chỉ
giữ trong bộ nhớ tiến trình (tối đa 256, LRU) cho Shared Premium/Cộng đồng
Free. Metadata lưu: generation_id, owner, prompt, model, mode, aspect_ratio,
thời điểm, storage key — không lưu secret provider nào.

## 7. Bảo mật đã kiểm tra trực tiếp (không chỉ đọc code)

- `Settings.describe()`/`ImageStudioSettings.describe()`: xác nhận thủ công
  KHÔNG có `pollinations_api_key`/`byop_master_key` — chỉ cờ boolean.
- `POLLINATIONS_API_KEY` hiện có trong `server/.env` (35 ký tự, có TRƯỚC
  overnight này, không phải do agent ghi vào) — quét toàn bộ diff overnight
  bằng pattern secret/entropy: sạch, không có giá trị secret nào bị chép vào
  code/test/report.
- `QuickFreeImageProvider`: không header Authorization, không `?key=`,
  `trust_env=False`.
- `SharedPremiumImageProvider`: header Authorization gắn per-request (không
  bake vào client), lỗi luôn được làm sạch trước khi trả về client (không
  dump body provider thô).
- Route admin (`/api/admin/image-studio/*`) dùng CHUNG `admin_profile` với
  27 route admin khác đã có — không tạo guard riêng yếu hơn.
- Toàn bộ 4 kiểm tra khách quan chạy THẬT (không chỉ tin lời commit): backend
  **2054/2054** test xanh, frontend **563/563** xanh, `typecheck` sạch,
  `lint` 0 lỗi (2 cảnh báo `<img>` không liên quan), `build` production
  thành công (`/image-studio`, `/image-studio/connect/callback` là trang
  tĩnh).

## 8. Blocker / cần thao tác thủ công

- **Production Appwrite đang bị chặn** → mọi store (`MockWalletStore`,
  `MockByopConnectionStore`, `MockImageLibraryStore`) là in-memory, MỘT tiến
  trình. Kiến trúc đã thiết kế để hoán đổi sang Appwrite mà không đổi shape
  dữ liệu, nhưng bản Appwrite thật CHƯA được viết.
- Cộng đồng Free hiện RỖNG thật (0 model đạt giá 0) — không phải bug, sẽ tự
  điền khi Pollinations công bố model cộng đồng giá 0 (dò lại định kỳ, TTL
  cache 300s).
- Shared Premium và BYOP đều tắt mặc định trên máy này — cần chủ site chủ
  động đặt biến môi trường (mục 5) để bật.
- Payment provider thật (Stripe/PayOS) chưa được chọn/nối — xem mục 4.
- `MockPendingAuthorizationStore`/`MockByopConnectionStore` là một-tiến-trình
  — sản xuất nhiều tiến trình (uvicorn nhiều worker) cần kho dùng chung
  (Redis/Appwrite), đã ghi rõ trong docstring.
