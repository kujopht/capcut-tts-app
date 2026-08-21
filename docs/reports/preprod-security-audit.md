# Kiểm toán bảo mật / bí mật (Security & Secret Audit) — Phase 12

Overnight Pre-Production Hardening Marathon V1. Phạm vi: rà soát THUẦN
ĐỌC (read-only) — không đụng vào Appwrite Cloud production, không in bất kỳ
giá trị bí mật thật nào (mọi ví dụ trong tài liệu này đều là chuỗi giả tự
tạo cho mục đích kiểm thử). Không tìm thấy bí mật thật nào bị lộ ở bất kỳ
đâu trong repo hay lịch sử Git.

## Tóm tắt theo 6 mục

| # | Mục | Kết luận |
|---|---|---|
| 1 | Quét lịch sử Git tìm bí mật đã commit | **SẠCH** — không có `.env` thật nào từng được thêm vào lịch sử (chỉ `*.env.example`); không có key dạng `AIza…`, `sk-…`, private-key PEM, service-account JSON, hay `Bearer <token thật>` nào xuất hiện trong toàn bộ `git log --all -p` |
| 2 | Xác minh `server/secret_redaction.py` | **HOẠT ĐỘNG ĐÚNG** — đã CHẠY THẬT hàm với giá trị giả dạng Appwrite key/Bearer/JWT, cả ba đều bị thay bằng `<redacted>`; phát hiện MỘT khoảng trống nhỏ (xem chi tiết) không phải lỗ hổng khai thác được |
| 3 | Phân loại `print()`/logging trong `server/*.py` | **1 LỖI NHỎ ĐÃ SỬA** — `_an_toan_song_song()` in `repr(exc)` thô không qua lọc; đã vá bằng `loc_bo_theo_gia_tri()`. Phần còn lại (worker.py, translation_worker.py) vốn đã SẠCH theo thiết kế (chỉ log `type(exc).__name__`) |
| 4 | Lộ bí mật ở frontend | **SẠCH** — chỉ có `NEXT_PUBLIC_API_BASE` tồn tại trong `web/src` và `next.config.mjs`; endpoint BYOK/provider-connections chỉ trả `last4`/`status`/metadata, có test riêng canh giữ (`test_translation_byok_security.py`, `test_public_profile_safety_audit.py`) |
| 5 | Rò rỉ token qua URL / log request | **SẠCH** — xác thực luôn qua header `Authorization: Bearer`, không có route nào nhận token qua query string; `server/main.py` không có middleware log request/header nào |
| 6 | Độ ồn của script smoke-test/perf-probe | **SẠCH** — cả 4 script (`smoke_test_selfhost_appwrite.py`, `smoke_test_selfhost_trusted_sources.py`, `smoke_test_selfhost_websub.py`, `perf_probe_admin_selfhost.py`) đúng như docstring tự khai: không in `YOUTUBE_API_KEY`/`APPWRITE_API_KEY`/`websub_secret` |

**Không tìm thấy bí mật thật nào bị lộ.** Một lỗi ghi log không an toàn nhỏ
đã được sửa (mục 3), phù hợp phạm vi cho phép "sửa vấn đề ghi log/redaction
không an toàn nếu nhỏ và rõ ràng". Đã chạy lại toàn bộ `server/tests`
(2408 test) sau khi sửa — **OK**.

---

## 1. Quét lịch sử Git tìm bí mật đã commit

### Phương pháp
- `git ls-files | grep -i env` — chỉ liệt kê `.env.example` (server/web/deploy),
  không có `.env`/`.env.*` thật nào đang được track.
- `git log --all --diff-filter=A --name-only` lọc theo tên file khớp `env` —
  xác nhận suốt lịch sử CHƯA TỪNG có file nào khác ngoài các `.env.example`
  từng được `git add`.
- `git log --all -p` (toàn bộ lịch sử, mọi nhánh) quét theo các mẫu:
  - `AIza[0-9A-Za-z_-]{20,}` (khoá Google/YouTube Data API) → 0 kết quả.
  - `sk-[A-Za-z0-9]{20,}` (định dạng khoá kiểu OpenAI) → 0 kết quả.
  - `BEGIN (RSA|EC|OPENSSH|PGP|DSA) PRIVATE KEY` → 0 kết quả.
  - `"type": "service_account"` (JSON service-account GCP) → 0 kết quả.
  - `Bearer [A-Za-z0-9._-]{15,}` → chỉ có các chuỗi test rõ ràng là giả
    (`bat-ky-token-nao`, `token-khong-hop-le`, `abcdefghijklmnopqrstuvwxyz123456`…
    đều nằm trong `server/tests/test_secret_redaction.py`).
  - `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` (JWT) → duy nhất một
    khớp, chính là token mẫu công khai kinh điển của jwt.io
    (`eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ`), nằm
    trong cùng file test nói trên — không phải bí mật thật.
  - `(APPWRITE_API_KEY|CLOUDFLARE_API_TOKEN|R2_ACCESS_KEY|R2_SECRET|GROQ_API_KEY|
    CEREBRAS_API_KEY|YOUTUBE_API_KEY)\s*=\s*[...]` (lọc bớt `example`/`your-`/
    `changeme`) → chỉ còn lại các dòng gán `youtube_api_key="fake-key"` trong
    code test (`main.trusted_sources._youtube_api_key`), không phải file cấu hình.
  - Tên file lịch sử khớp `secret|credential|.pem|.key$|.p12|.pfx|service.?account`
    → chỉ có `server/secret_redaction.py` và bài test của nó (chính module
    redaction, không phải secret bị lộ).

### Kết luận
SẠCH. Toàn bộ ba file `.env.example` (`server/.env.example`,
`web/.env.example`, `deploy/fanfic-worker.env.example`) đều để trống giá trị,
chỉ có tên biến + chú thích hướng dẫn — đã đọc trực tiếp để xác nhận không
lỡ tay điền giá trị thật.

---

## 2. Xác minh `server/secret_redaction.py`

### Đọc hiểu module
`server/secret_redaction.py` cung cấp ba hàm:
- `loc_bo_theo_gia_tri(van_ban)` — áp 3 mẫu regex theo GIÁ TRỊ (không phụ
  thuộc tên trường): khoá Appwrite dạng `standard_<hex dài>`/`console_<hex dài>`,
  `Bearer <token>`, và JWT ba đoạn base64url.
- `loc_bo_de_qui(du_lieu)` — duyệt đệ quy dict/list/tuple, thay giá trị của
  các khoá khớp `SECRET_KEY_NAMES` (so khớp CHÍNH XÁC, không phải substring —
  cố ý để tránh xoá nhầm các trường hợp lệ có hậu tố `_key` như `storage_key`,
  `avatar_key`), đồng thời áp `loc_bo_theo_gia_tri` lên mọi chuỗi còn lại.
- `thong_diep_loi_an_toan(body, status_code)` — dựng thông điệp lỗi AN TOÀN
  từ response Appwrite, ưu tiên trường `message`, luôn lọc qua
  `loc_bo_theo_gia_tri` trước khi trả, cắt tối đa 300 ký tự.

### Call site
Được import và gọi tại 6 file store: `appwrite_adapter.py`,
`appwrite_store.py`, `appwrite_animation_store.py`,
`appwrite_gamification_store.py`, `appwrite_translation_store.py`,
`appwrite_trusted_source_store.py` — mỗi nơi bọc lỗi HTTP >= 400 từ Appwrite
trước khi ném `NotFoundError`. `server/main.py` không gọi trực tiếp (đúng
thiết kế: main.py chỉ nhận exception đã được các store lọc sẵn).

### Đã CHẠY THẬT (không chỉ đọc code)
Viết script kiểm thử độc lập, gọi cả ba hàm với giá trị GIẢ tự tạo mô phỏng
đúng hình dạng bí mật thật (khoá Appwrite giả dạng `standard_<hex>`, Bearer
token giả, JWT giả, khoá YouTube giả dạng `AIzaSy…`):

- `loc_bo_theo_gia_tri`: Bearer/JWT/khoá-Appwrite-giả đều bị thay bằng
  `<redacted>` — xác nhận đúng.
- `loc_bo_de_qui`: các khoá `apiKey`, `Authorization`, `access_token` bị
  redact theo TÊN; khoá Appwrite giả lồng sâu trong
  `trace[].args[]` (đúng kịch bản sự cố có thật mô tả trong docstring module)
  vẫn bị redact nhờ lớp lọc THEO GIÁ TRỊ ở bước cuối; trường `storage_key`
  (không phải bí mật) được giữ nguyên đúng như thiết kế.
- `thong_diep_loi_an_toan`: thông điệp lỗi 401 chứa Bearer/khoá giả được
  lọc sạch trước khi trả.

**Khoảng trống phát hiện được (không phải lỗ hổng khai thác được)**: danh
sách mẫu theo-giá-trị (`_MAU_BI_MAT_THEO_GIA_TRI`) KHÔNG có mẫu cho khoá kiểu
YouTube Data API (`AIzaSy…`), và `youtube_api_key` không nằm trong
`SECRET_KEY_NAMES`. Tuy nhiên đã đọc `server/youtube_client.py` và xác nhận
đây không phải lỗ hổng thực tế: khoá YouTube được thiết kế để KHÔNG BAO GIỜ
đi vào exception message ngay từ tầng thấp nhất — `_goi()` không đưa `exc`
(có thể chứa URL kèm `key=`) thẳng vào thông điệp lỗi, luôn dựng câu tĩnh cố
định (`"Không kết nối được YouTube Data API."`). Đã kiểm chứng thêm bằng
thực nghiệm: một `httpx.ConnectError`/`ConnectTimeout` thật với header
`Authorization` giả gắn sẵn trên client KHÔNG làm lộ giá trị header đó qua
`str(exc)`/`repr(exc)` (`httpx` không nhúng header vào exception message).
Ghi nhận làm việc nên làm nếu có thời gian ở phase sau: thêm mẫu `AIzaSy`
vào `_MAU_BI_MAT_THEO_GIA_TRI` cho phòng thủ theo chiều sâu — không khẩn.

---

## 3. Phân loại `print()`/logging trong `server/*.py` (không tính test)

Toàn bộ `server/*.py` (loại trừ `server/tests/`) chỉ có **8 lời gọi**
`print()`, không có `logger.*`/`logging.*` nào khác:

| File:dòng | Nội dung in | Rủi ro lộ bí mật |
|---|---|---|
| `main.py:319` | Cảnh báo ngân sách Image Studio (số tiền/tháng) | Không — không có dữ liệu bí mật |
| `main.py:1934-1935` | Cảnh báo không đo được thời lượng audio (kèm `job_id`) | Không — `job_id` là định danh hệ thống |
| `main.py:1962-1963` | Cảnh báo lỗi sinh transcript, in `{exc}` | Thấp — nhánh này chỉ bắt lỗi từ `build_transcript()` (thuần xử lý dữ liệu audio cục bộ, không gọi mạng/không chạm secret) |
| `main.py:3725` (đã sửa) | `repr(exc)` từ các truy vấn dashboard chạy song song | **Trước khi sửa: trung bình** — in thẳng `repr(exc)` không qua lọc, dù hiện tại mọi nhánh gọi vào đây đều đã ném exception với thông điệp an toàn từ tầng dưới, đây là lưới an toàn cuối cho các adapter thêm sau này |
| `translation_worker.py:107,218` | Log JSON có cấu trúc theo chu kỳ (trạng thái, tuổi nhịp) | Không |
| `translation_worker.py:209,215` | Cảnh báo đọc nhịp lỗi, chỉ in `type(exc).__name__` | Không — cố ý CHỈ log tên lớp lỗi, không log message |
| `worker.py:93,232` | Log JSON có cấu trúc (giống trên) | Không |
| `worker.py:223,229` | Cảnh báo đọc nhịp lỗi, chỉ in `type(exc).__name__` | Không |

**`worker.py`/`translation_worker.py` có comment tường minh tại hàm `_ghi()`**:
*"KHÔNG BAO GIỜ ghi nội dung chương, token hay khoá object đầy đủ vào đây"*
— đã xác nhận bằng grep toàn bộ lời gọi `_ghi(...exc...)`: cả hai file đều
chỉ truyền `loai=type(exc).__name__`, không bao giờ truyền message của
exception.

### Đã sửa: `main.py` — `_an_toan_song_song()`

**Trước khi sửa**: `print(f"[{nhan}] mot nhom truy van loi, dung gia tri mac dinh: {exc!r}")`
in thẳng `repr(exc)` của bất kỳ exception nào ném ra từ các truy vấn admin
chạy song song (`_admin_dashboard_them`, `admin_analytics_detail`,
`admin_image_studio_spending`), không đi qua `secret_redaction.py` dù module
này tồn tại chính để phục vụ mục đích đó.

**Sau khi sửa**: bọc bằng `loc_bo_theo_gia_tri(repr(exc))` (import
`from server.secret_redaction import loc_bo_theo_gia_tri`) — nếu một adapter
thêm sau này (vd một tích hợp Cloudflare Analytics/R2 mới) ném ra exception
chưa kịp lọc ở tầng dưới, dòng log này vẫn chặn được Bearer/JWT/khoá kiểu
Appwrite lọt ra log. Đã kiểm tra: không có nhánh nào hiện tại thực sự lộ bí
mật qua đường này (Appwrite `_call()` đã tự lọc; `traffic_analytics.py` chưa
hiện thực gọi mạng thật) — đây là phòng thủ theo chiều sâu, không phải vá
một lỗ hổng đang bị khai thác.

Đã chạy `python -m compileall server/main.py` (OK) và toàn bộ
`server/tests` — **2408 test, OK** — sau khi sửa.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `_an_toan_song_song()` ghi log lỗi admin song song | `print(f"...{exc!r}")` — không lọc bí mật | `print(f"...{loc_bo_theo_gia_tri(repr(exc))}")` — đi qua lớp lọc theo mẫu giá trị |

---

## 4. Lộ bí mật ở frontend

- Grep `NEXT_PUBLIC_[A-Z_]+` trong `web/src` → duy nhất một chỗ,
  `web/src/lib/api.ts:9` (`NEXT_PUBLIC_API_BASE`). `web/next.config.mjs:6`
  cũng chỉ khai báo đúng biến này.
- Grep `api_key|apiKey|access_token|encrypted_secret` trong `web/src` → 2 file:
  - `web/src/app/translate/ProviderConnectDialog.tsx`: đây là form NGƯỜI
    DÙNG tự nhập khoá BYOK của họ để gửi LÊN backend (đúng luồng thiết kế
    V5.1 — người dùng chủ động cung cấp khoá của chính họ, không phải khoá
    bị lộ ra ngoài).
  - `web/src/lib/api.ts`: hàm `connectProvider()` chỉ GỬI `api_key` lên
    (trong body POST), không có chỗ nào ĐỌC lại field `api_key`/`encrypted_secret`
    từ response.
- Đọc `server/translation_domain.py::ProviderConnection.to_dict()` — theo
  thiết kế, entity này VÀ `to_dict()` là "ranh giới an toàn duy nhất": field
  `encrypted_secret` không tồn tại trong dict trả về, chỉ có `last4` (4 ký
  tự cuối, không đủ để đoán lại khoá) + `status`/`provider_id`/metadata.
  Được canh giữ bởi các test chuyên biệt đã có sẵn: `test_translation_byok_security.py`
  (kiểm tra cấm cả `encrypted_secret`, `api_key`, `authorization`, `secret`,
  `token` trong mọi response liên quan BYOK), `test_translation_byok_routes.py`,
  `test_public_profile_safety_audit.py`, `test_translation_contract.py`.

### Kết luận
SẠCH — không có biến `NEXT_PUBLIC_*` nào ngoài `NEXT_PUBLIC_API_BASE`, và
không có endpoint BYOK/provider-connection nào trả về khoá thật hay
`encrypted_secret`.

---

## 5. Rò rỉ session-token/URL

- Toàn bộ xác thực trong `server/main.py` đi qua tham số
  `authorization: Optional[str] = Header(default=None)` (FastAPI `Header`,
  đọc từ HTTP header `Authorization`), được `current_profile()`/
  `optional_profile()` tách `Bearer <token>` — KHÔNG có route nào nhận
  token qua query string.
- Trường hợp đặc biệt đã kiểm tra kỹ: `/api/audio/{chapter_id}/url` —
  docstring giải thích rõ vì sao cần endpoint riêng (thẻ `<audio src>` của
  trình duyệt không gửi được header `Authorization`). Endpoint này KIỂM TRA
  quyền bằng `Authorization` header như bình thường TRƯỚC, rồi mới trả về
  một **URL ký sẵn của R2** (`storage.signed_url(...)`, có hạn dùng riêng,
  không liên quan token phiên đăng nhập của người dùng) để gắn vào
  `<audio src>`. Đây là URL ký tài nguyên có phạm vi/thời hạn riêng theo
  chuẩn (giống pre-signed URL của S3/R2), KHÔNG PHẢI token phiên bị lộ qua
  URL.
- `server/main.py` không có bất kỳ middleware log request nào
  (`@app.middleware`, `call_next`) — đã grep xác nhận không tồn tại đoạn
  code nào log `request.headers` (chỉ có 2 chỗ đọc `content-length` và
  `x-forwarded-for` cho mục đích khác, không log lại).

### Kết luận
SẠCH.

---

## 6. Độ ồn của script smoke-test/perf-probe

| Script | Docstring tự khai | Xác nhận qua đọc từng `print()` |
|---|---|---|
| `scripts/smoke_test_selfhost_appwrite.py` | "script này không đọc secret nào cả, chỉ gọi HTTP tới backend đang chạy" | Đúng — chỉ in tên bước/kết quả pass-fail, email test (không phải secret) |
| `scripts/smoke_test_selfhost_trusted_sources.py` | "KHÔNG BAO GIỜ in `YOUTUBE_API_KEY`/`APPWRITE_API_KEY` hay bất kỳ lỗi nào [chứa bí mật]" | Đúng — các dòng `print(f"[CẢNH BÁO] ...{exc}")` chỉ là lỗi dọn dẹp tài nguyên tạm gọi tới backend cục bộ, không phải lỗi Appwrite/YouTube thô |
| `scripts/smoke_test_selfhost_websub.py` | Tương tự | Đúng, cùng mẫu như trên |
| `scripts/perf_probe_admin_selfhost.py` | "KHÔNG ghi gì vào Appwrite ngoài một user smoke-test" | Đúng — chỉ in mã trạng thái HTTP/độ trễ và `user_id[:8]…` (cắt ngắn, không phải bí mật) khi đo hiệu năng route `/api/admin/*` cục bộ |

### Kết luận
SẠCH — cả 4 script đều khớp đúng lời khai trong docstring của chính chúng.

---

## Việc đã sửa trong lượt audit này

| File | Thay đổi |
|---|---|
| `server/main.py` | Thêm `from server.secret_redaction import loc_bo_theo_gia_tri`; bọc `print(...)` trong `_an_toan_song_song()` bằng hàm lọc này thay vì in thẳng `repr(exc)` |

Đã xác minh: `compileall` OK, toàn bộ `server/tests` (2408 test) — OK, không
có regression.

## Khuyến nghị không khẩn (để dành phase sau nếu cần)

- Cân nhắc thêm mẫu regex cho khoá kiểu YouTube (`AIzaSy[0-9A-Za-z_-]{33}`)
  vào `_MAU_BI_MAT_THEO_GIA_TRI` trong `server/secret_redaction.py`, dù hiện
  tại `youtube_client.py` đã tự tránh lộ khoá này bằng thiết kế riêng (không
  đưa `exc`/URL vào thông điệp lỗi).

---

## 7. Sự cố 2026-08-20: khoá Appwrite thật lọt vào fixture kiểm thử

### Diễn biến

Commit `82f5ed9` (2026-08-16), khi thêm `server/tests/test_secret_redaction.py`
để TÁI HIỆN sự cố rò rỉ khoá Appwrite thật ngày 2026-08-16 (xem mục 1-6 phía
trên), đã vô tình dùng CHÍNH khoá thật đó làm giá trị kiểm thử thay vì một
giá trị bịa. Khoá lọt vào đúng MỘT commit, MỘT file
(`server/tests/test_secret_redaction.py`), không có ở bất kỳ nơi nào khác
trong lịch sử git (đã quét toàn bộ `git log --all` bằng pickaxe regex cho
`standard_`/`console_`/AWS `AKIA`/PEM private-key/JWT — không tìm thấy bí
mật thật nào khác).

Phạm vi ảnh hưởng (do kế thừa từ `82f5ed9`): `integration/pre-prod-v1` và
mọi nhánh nhánh ra từ nó sau 2026-08-16, PR #18 (đã merge — release
candidate) và PR #19 (đang Draft). `main` và `upstream/main` KHÔNG bị ảnh
hưởng — cả hai đứng yên tại `d483e90` (2026-08-14), trước khi `82f5ed9` tồn
tại.

Khoá cũ đã được xác nhận thu hồi/xoay trước khi phase này bắt đầu.

### Biện pháp đã áp dụng (phase containment 2026-08-20)

1. **Sửa fixture** — thay giá trị thật bằng một chuỗi BỊA DÙNG, sinh
   CHƯƠNG TRÌNH (`"standard_" + đoạn_hex_lặp_lại * 12`) thay vì gõ tay một
   chuỗi trông giống thật — để không ai (kể cả người review sau này) vô
   tình copy một chuỗi "trông như khoá thật" vào fixture lần nữa. Đã đổi
   tên biến (`_KHOA_APPWRITE_THAT_DANG` → `_KHOA_APPWRITE_GIA_LAP`) và viết
   rõ trong docstring: đây là HÌNH DẠNG, không phải khoá thật, không bao
   giờ dùng được với Appwrite nào. Toàn bộ 17 test trong file vẫn PASS —
   độ mạnh của bài kiểm thử redaction không đổi.
2. **Cổng quét bí mật ở CI** — thêm job `secrets` (`gitleaks/gitleaks-action@v2`)
   vào `.github/workflows/ci.yml`, chạy trên mọi `push`/`pull_request`.
   Cấu hình tại `.gitleaks.toml` (gốc repo): kế thừa toàn bộ luật mặc định
   của gitleaks (AWS, private key, JWT, generic API key...) CỘNG một luật
   riêng `appwrite-api-key` khớp đúng hình dạng khoá Appwrite
   (`\b(?:standard|console)_[a-f0-9]{40,}\b`) — cùng mẫu regex với
   `_MAU_BI_MAT_THEO_GIA_TRI` trong `server/secret_redaction.py`. KHÔNG có
   allowlist riêng cho `test_secret_redaction.py`: vì giá trị kiểm thử giờ
   được ghép chuỗi lúc chạy, không còn một chuỗi liên tục giống bí mật thật
   nằm trong văn bản nguồn để gitleaks phải bỏ qua. Nếu tương lai một
   allowlist cho file này trở nên "cần thiết", đó là dấu hiệu một bí mật
   thật đã lọt vào lại — phải điều tra trước, không được allowlist ngay.
3. **Khuyến nghị bổ sung (chưa bắt buộc bằng công cụ, ghi lại để áp dụng
   thủ công/tổ chức)**:
   - Bật GitHub secret scanning + push protection cho repo (Settings →
     Code security) — đây là lớp chặn ở PHÍA GITHUB, trước khi commit lọt
     vào remote, độc lập với gitleaks chạy trong CI (chạy SAU khi đã push).
   - Cân nhắc thêm một pre-commit hook cục bộ (`.pre-commit-config.yaml`,
     hook `gitleaks protect --staged`) để chặn ở máy dev TRƯỚC khi commit,
     thay vì chỉ phát hiện sau khi đã push lên CI.
   - **Quy tắc bắt buộc từ sự cố này**: KHÔNG BAO GIỜ copy một response
     payload/trace/log THẬT (kể cả khi đang tái hiện một sự cố có thật) vào
     fixture kiểm thử. Khi cần tái hiện HÌNH DẠNG của response thật (cấu
     trúc, tên trường, độ sâu lồng nhau), luôn thay MỌI giá trị nhạy cảm
     bằng giá trị bịa/sinh chương trình trước khi đưa vào file kiểm thử —
     không có ngoại lệ, kể cả khi khoá/token đó "sắp bị xoay" hay "không
     còn hiệu lực" tại thời điểm viết test.

### Kết luận

Sự cố đã được khoanh vùng đầy đủ (1 commit, 1 file, không lan sang `main`),
khoá cũ đã thu hồi, fixture đã sạch, và một cổng CI mới ngăn tái diễn dạng
bí mật này (cùng các dạng bí mật khác đã có sẵn trong luật mặc định của
gitleaks) trên mọi nhánh/PR từ đây về sau.
