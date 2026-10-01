# Sổ tay vận hành Trợ lý AI (production)

Dành cho Owner/người trực. Trạng thái hiện hành: **mở cho mọi người đã đăng nhập** (`FAS_AI_AUDIENCE=all`), preset **`beta`** (5 lượt/người/ngày, 150 lượt/ngày toàn cục), pool **9 slot Gemini, 8 bật + `gemini-05` TẮT có chủ ý**, Ink Scout **TẮT**, khách chưa đăng nhập **không dùng được**.

Nguyên tắc khi có sự cố: **tắt khẩn cấp trước, điều tra sau.** Không bao giờ dán/ghi khoá, không liệt kê biến môi trường Render, không đưa ID người dùng vào issue/PR/chat công khai.

Tài liệu liên quan: hợp đồng `AI_ASSISTANT_V1.md`, bảng điều khiển `AI_ADMIN_CONTROL_PLANE.md`, kế hoạch mở rộng `AI_PUBLIC_BETA_CHECKLIST.md` (phần trạng thái trong đó là ảnh chụp 2026-10-01; trạng thái hiện hành là tài liệu này).

---

## 1. Kiến trúc trong một trang

```
Trình duyệt (Next.js trên Cloudflare Workers)
   cờ build NEXT_PUBLIC_AI_ASSISTANT_ENABLED (biến repo PRODUCTION_AI_ASSISTANT_ENABLED) -> có vẽ lối vào hay không
   GET /api/ai/access        -> {"eligible": bool}  (chỉ HIỂN THỊ; không phải rào chặn)
        │  Authorization: Bearer <phiên>   (khoá nhà cung cấp KHÔNG BAO GIỜ xuống trình duyệt)
        ▼
Render `fas-prod-api` (FastAPI, một tiến trình, gói free: có thể ngủ/chậm)
   MaxBodyMiddleware (/api/ai/* và /api/admin/ai/*: thân tối đa 256 KB -> 413, trước cả bước xác thực)
   RateLimitMiddleware (toàn app, theo băm token; POST/PUT Tier B 120/phút)
   build_ai_router  /api/ai/*     xác thực -> khán giả -> RPM 8/người/phút -> admission -> StreamGuard
        admission (control plane): công tắc tổng -> trần toàn cục -> trần theo người (hoặc trần QA)
        StreamGuard: 1 luồng/người, tối đa FAS_AI_MAX_STREAMS=4 luồng/instance
        ControlledGateway: plan() -> thử từng slot (<=45 s kể từ lần thử đầu) -> Gemini (endpoint tương thích OpenAI)
   build_ai_admin_router /api/admin/ai/*   (đọc: Admin/Owner; ghi: chỉ Owner; mọi thay đổi có audit)
        ▼
Appwrite (bền):  ai_usage_daily (sổ người dùng + sổ QA)  ai_provider_usage_daily (sổ slot)  ai_messages/conversations/…
                 ai_control_settings / ai_provider_slots / ai_routing_profiles / ai_admin_audit
Trong tiến trình (MẤT khi deploy/khởi động lại): breaker, cooldown, cửa sổ RPM/TPM mềm, 429 gần đây, last_error_*, lịch sử Kiểm tra
```

| Việc | Ở đâu | Bền? |
|---|---|---|
| Lượt đã dùng của người dùng hôm nay | `ai_usage_daily` (`{user_id}_{yyyymmdd}`) | có |
| Lượt đã dùng của từng slot (= trần toàn cục) | `ai_provider_usage_daily` | có (ghi tuần tự theo slot-ngày trong một tiến trình) |
| Cấu hình, trần, công tắc tổng, slot, hồ sơ | `ai_control_*` | có, cache 15 s |
| Cooldown / breaker / `last_error_*` | bộ nhớ tiến trình | **không** |
| Khán giả, cờ bật backend, khoá | biến môi trường Render (`FAS_AI_AUDIENCE`, `FAS_AI_ASSISTANT_V1`, `FAS_AI_SECRET_<REF>`…) | có, đổi cần deploy |

---

## 2. Ngữ nghĩa hạn mức (đọc kỹ trước khi đổi bất cứ thứ gì)

Ngày tính theo **UTC**: đặt lại lúc **00:00 UTC = 07:00 giờ Việt Nam**.

| Loại lượt | Sổ ghi | Trần áp dụng | Cộng vào trần toàn cục 150? | Bị tắt khẩn cấp chặn? |
|---|---|---|---|---|
| Người dùng thường | `ai_usage_daily` khoá `user_id` | **5 lượt/ngày** và 15.000 token/ngày (cái nào chạm trước) | có | có |
| Owner dùng như người thường | như trên | như trên | có | có |
| **Owner QA** (`qa:true`, chỉ Owner + control plane bật) | khoá tổng hợp `qa-<băm 16 hex>` | `FAS_AI_OWNER_QA_DAILY_REQUESTS` (mặc định 20/Owner/ngày, `0` = đóng) — **không** ăn vào 5 lượt thường | **có** | **có** |
| **Probe** (nút "Kiểm tra" slot, chỉ Owner) | **không ghi sổ nào** | đếm riêng (`probes_today`, tối đa 30/slot/ngày, ≥20 s giữa hai lần cùng slot) | **không** | không (chạy được cả khi tắt) |
| Khách / người ngoài khán giả | — | 401 / 403 trước mọi bước | — | — |

Những điều dễ hiểu nhầm:

* **Trần thật của một người = min(5 lượt, 15.000 token).** Hội thoại dài (4.000 token ngữ cảnh + 400 đầu ra mỗi lượt) có thể chạm 15.000 token trước lượt thứ 5; giao diện báo "hết lượt" như nhau.
* **Trần toàn cục 150 lượt đi kèm 450.000 token**: với lượt dài trung bình > 3.000 token, trần token chạm trước 150 lượt. Cả hai trả `429 ai_budget_exhausted` `scope:"global"`.
* **Giao diện người dùng chỉ hiện hạn mức RIÊNG** ("Hôm nay còn 3/5 lượt hỏi · làm mới lúc 07:00"). Mức dùng toàn cục, công suất nhà cung cấp, phần trăm: **chỉ ở `/admin/ai`**.
* Một lượt được **tính** khi có văn bản/token, hoặc khi client bỏ đi *sau khi* nhà cung cấp đã bị gọi (chống vòng lặp gửi-rồi-ngắt). **Lỗi phía nhà cung cấp trước token đầu là miễn phí**. "Tạo lại" là một lượt mới (tốn thêm 1 lượt, và nhân đôi câu hỏi trong lịch sử — hành vi V1 có chủ ý).
* Tin bị từ chối trước khi lưu (429/503) **không** nằm trong hội thoại; giao diện hiện "Chưa gửi".
* Một lượt bị client bỏ đi *trước khi nhà cung cấp trả byte nào* vẫn tính cho người dùng **và** cho slot đang được gọi (gateway báo `on_attempt` ngay trước mỗi lời gọi), nên cũng vào trần toàn cục. Trước đây chỉ trừ người dùng, và N tài khoản × 5 lượt "gửi rồi ngắt" gọi nhà cung cấp mà không bao giờ chạm trần 150. Gateway kiểm lại cờ huỷ NGAY SAU `on_attempt`: client ngắt đúng khoảng đó thì lời gọi không được phát đi (không có gì để đếm).
* Nhà cung cấp trả lời **thành công nhưng rỗng** (vd. bị lọc nội dung: chỉ có `usage` + `finish_reason`, không token chữ nào) là một lượt thật: trừ lượt người dùng (nếu nhà cung cấp báo usage) **và** tính vào slot/trần toàn cục. Trước đây slot bị bỏ sót vì `ProviderServed` chỉ phát ở token chữ đầu tiên.
* Nhiều tài khoản có thể cùng đốt trần toàn cục (30 tài khoản × 5 lượt = 150). Đây là đánh đổi của trần toàn cục, không phải lỗi.

### Chính sách đếm (có chủ ý — đổi nó là một quyết định, không phải sửa lỗi; có test ghim lại)

| Tình huống | Lượt của người dùng (`ai_usage_daily`) | `requests` của slot (= trần 150) | Bộ đếm khác của slot |
|---|---|---|---|
| Có token chữ, kết thúc bình thường | +1 | +1 (slot đã phục vụ) | — |
| Thành công nhưng rỗng (lọc nội dung) | +1 nếu nhà cung cấp báo usage | +1 (slot đang được gọi) | — |
| Client bỏ đi trước token đầu | +1 | +1 (slot đang được gọi) | — |
| Lỗi nhà cung cấp **trước** token đầu (5xx, timeout…) rồi chuyển slot | 0 | 0 | `errors` +1 cho MỖI slot đã lỗi |
| 429 từ nhà cung cấp trước token đầu | 0 | 0 | `rate_limited` +1, slot nghỉ theo `Retry-After` (kẹp 1–600 s) |
| Lỗi **giữa chừng** (đã có token) | +1 | +1 | `errors` +1 |
| Probe của Owner | không ghi sổ | 0 | `probes_today` (tối đa 30/slot/ngày) |

Lý do để lỗi-trước-token không vào `requests`: trần 150 đo lượt được PHỤC VỤ; người dùng không bị phạt vì lỗi của nhà cung cấp. Rủi ro đã biết: lỗi lặp lại có thể gọi nhà cung cấp nhiều lần mà không chạm trần. Giới hạn: RPM 8/người/phút, breaker 3 lỗi → cooldown 60 s, ngân sách chuyển slot 45 s/lượt.

---

## 3. Slot Gemini & chuyển dự phòng

* Pool: 9 slot `gemini-01..09`, model `gemini-3.5-flash-lite`. **`gemini-05` (FFW3) TẮT có chủ ý — đừng chờ nó và đừng bật lại khi chưa Kiểm tra ổn định.** Năng lực danh nghĩa 8 slot × 30 = 240 lượt/ngày > trần 150.
* **Thứ tự thử**: theo hồ sơ định tuyến của chế độ (`mode_profiles`); trong cùng bậc ưu tiên chọn **ngẫu nhiên có trọng số** = `weight × hệ số headroom` (còn nhiều hạn mức → tải nhiều; vừa bị 429/lỗi → giảm). Mỗi slot **thử tối đa một lần mỗi lượt**.
* **Chỉ chuyển slot TRƯỚC token đầu tiên.** Đã có token mà đứt → lỗi `ai_provider_interrupted`, giữ phần đã nhận, **không ghép hai nhà cung cấp**.
* **429**: slot vào cooldown theo `Retry-After` (kẹp 1–600 s; thiếu thì 30 s). **Lỗi khác**: 3 lần liên tiếp mở breaker 60 s. Một lần thành công đóng cooldown/breaker (nút "Reset cooldown" và một Kiểm tra thành công cũng vậy).
* **Ngân sách chuyển slot 45 s** kể từ lần thử đầu: quá mức đó không bắt đầu lần thử mới (trước đây 8 slot cùng treo giữ một luồng SSE hàng chục phút). **Client bỏ đi** → không bắt đầu thêm lần thử nào.
* **Mã lỗi cuối khi không có slot nào phục vụ** (SSE `error`, lượt miễn phí):

  | Tình trạng | Mã | Giao diện nói |
  |---|---|---|
  | đã thử các slot, tất cả lỗi | `ai_provider_unavailable` | đang tạm gián đoạn, thử lại sau ít phút |
  | mọi slot vừa chạm RPM/TPM mềm (tự hết ≤ 60 s) | `ai_busy` | đang bận, thử lại sau ít giây |
  | mọi slot đang cooldown | `ai_provider_unavailable` | tạm gián đoạn |
  | mọi slot chạm trần NGÀY của slot | `ai_budget_exhausted` `scope:"global"` + giờ reset | công suất chung đã hết, không phải do bạn |
  | không có gì bật/cấu hình | `ai_no_provider` | tạm gián đoạn |

* Cấu hình cache 15 s; bộ đếm ngày cache 10 s (tự cộng cục bộ sau mỗi lượt); kho cấu hình mất kết nối: dùng bản hợp lệ gần nhất tối đa 10 phút, rồi **AI tự tắt (fail-closed)**.

---

## 4. Ngưỡng sự cố & phản ứng đầu tiên

| Tín hiệu (xem ở `/admin/ai`) | Ngưỡng | Làm gì trước tiên |
|---|---|---|
| Rò khoá / tên provider / tên model ra phía người dùng | **bất kỳ** | **Tắt khẩn cấp**, ghi mã lỗi + thời điểm, xoay khoá liên quan |
| Người ngoài khán giả gửi được tin | bất kỳ | Tắt khẩn cấp (backend phải trả 403) |
| Slot HEALTHY còn lại | < 4 | Tắt khẩn cấp hoặc hạ preset; tìm nguyên nhân chung (Google outage? khoá?) |
| Tỉ lệ lỗi `errors / requests` | > 5% trong 1 giờ | Xem `last_error_code/category` từng slot |
| `rate_limited` (429) tăng đồng loạt nhiều slot | nhiều slot cùng lúc | Giảm RPM mềm của slot, hoặc hạ preset |
| Trần toàn cục | ≥ 80% trước 18h UTC | Cân nhắc thêm slot / nâng trần (xem §7.1) |
| `ai_busy` 503 tăng | liên tục | `FAS_AI_MAX_STREAMS` (4) quá thấp? Có khoá luồng rò? (dấu hiệu: `ai_busy` dù hầu như không ai dùng → khởi động lại instance) |
| `est_cost_micro_usd` | ≠ 0 (free tier phải = 0) | Có slot tính phí: xem lại giá/slot |
| Trang `/admin/ai` báo cấu hình hỏng/không đọc được | state ≠ ok | AI đã tự tắt an toàn; sửa qua đường §5 "cấu hình hỏng" |

---

## 5. Tắt khẩn cấp & rút lui (từ nhanh đến chậm)

1. **Tức thì, không deploy**: `/admin/ai` → *Tắt khẩn cấp* (`ai_enabled=false`). Luôn được nhận (kể cả khi trang giữ phiên bản cũ), hiệu lực ≤ 15 s. Chặn **mọi** lượt gửi (cả Owner QA) với 503 `ai_not_enabled`; `availability.reason = disabled_by_admin`; lối vào biến mất ở lần tải sau. Đọc lịch sử đã lưu vẫn được (có chủ ý). Bật lại = cùng nút.
2. **Một slot hỏng**: TẮT slot đó; bộ cân bằng dồn tải sang slot khác.
3. **Hạ hạn mức**: áp preset `canary` (20/người, 40 toàn cục) hoặc hạ trần ở *Toàn cục*; muốn khôi phục: preset `beta`.
4. **Thu hẹp đối tượng** (cần deploy backend): `FAS_AI_AUDIENCE=beta` (kèm `FAS_AI_BETA_USERS`) hoặc `canary`/xoá để chỉ Owner.
5. **Tắt giao diện**: biến repository `PRODUCTION_AI_ASSISTANT_ENABLED=0` rồi deploy; nhanh hơn là workflow **Production Rollback** (`wrangler rollback`) về bản frontend trước.
6. **Tắt hẳn backend AI**: `FAS_AI_ASSISTANT_V1=0` rồi deploy backend.
7. **Quay lại bản backend trước**: chạy lại `production-deploy.yml` với `ref=<SHA cũ>` và đúng lệnh tường minh ghi trong `CLAUDE.md` (không có lệnh deploy trần; không suy ra đích từ tài liệu cũ; Render build `main` hiện tại còn Cloudflare build SHA đã validate — **không để `main` di chuyển giữa lúc một run đang chờ duyệt**).
8. **Cấu hình hỏng** (AI tắt, đọc được từng dòng nhưng cả cấu hình không hợp lệ): vẫn **xoá slot / sửa hồ sơ / reset cooldown** được từ `/admin/ai` để đưa về hợp lệ; thao tác khác trả 409.

Hội thoại đã lưu không cần xoá khi rút lui; người dùng tự xoá trong cài đặt trợ lý.

---

## 6. Chẩn đoán theo triệu chứng

| Người dùng/Owner thấy | Mã | Nguyên nhân thường gặp | Xác nhận | Xử lý |
|---|---|---|---|---|
| Không thấy nút/mục Trợ lý AI | `/api/ai/access` → `eligible:false` | ngoài khán giả; backend tắt; tắt khẩn cấp; cờ build UI = 0 | `GET /api/health` → `ai_assistant.audience`; `/admin/ai` công tắc tổng | sửa theo nguyên nhân |
| "Trợ lý AI chưa được bật" | 503 `ai_not_enabled` | **tắt khẩn cấp** hoặc `FAS_AI_ASSISTANT_V1=0` hoặc cấu hình hỏng | công tắc tổng; `state` ở `/admin/ai` | bật lại / sửa cấu hình |
| 403 `ai_not_enabled` | | tài khoản ngoài khán giả | `audience` ở `/api/health` | đúng thiết kế |
| 403 `ai_forbidden` | | mở hội thoại/dự án của người khác (thường do cờ phiên cũ) | — | tải lại; đã được sửa ở bản có `lamSachNeuDoiNguoi` |
| "Bạn đã dùng hết lượt hôm nay" | 429 `ai_budget_exhausted` `scope:"user"` | đủ 5 lượt hoặc 15.000 token | `GET /api/ai/availability` → `limits` | chờ 07:00 VN; không "reset" tay cho người dùng thường |
| "Công suất chung đã hết (không phải do bạn)" | 429 `scope:"global"` | trần toàn cục lượt/token, hoặc mọi slot chạm trần ngày | `/admin/ai` → Hạn mức toàn cục | chờ reset, hoặc nâng trần có kiểm soát (§7.1) |
| 429 ở Owner QA | `scope:"qa"` | hết `FAS_AI_OWNER_QA_DAILY_REQUESTS` | `availability.qa` | chờ reset / tăng biến (cần deploy) |
| "Bạn hỏi hơi nhanh" | 429 `ai_rate_limited` | RPM 8/phút/người; hoặc route ghi 30/phút (escalation 3/phút) | — | chờ vài giây |
| "Trợ lý AI đang bận" | 503 `ai_busy` (HTTP) | người đó đang có 1 luồng chạy, hoặc 4 luồng/instance đã đầy | `/admin/ai` | thử lại; nếu kéo dài khi ít người dùng → nghi khoá luồng rò, khởi động lại instance |
| SSE `ai_busy` | | mọi slot vừa chạm RPM/TPM mềm | slot `rpm_soft_cap`/`tpm_soft_cap` | tự hết ≤ 60 s; nới RPM mềm nếu thường xuyên |
| "Trợ lý AI đang tạm gián đoạn" | SSE `ai_provider_unavailable` / `ai_no_provider` | tất cả slot lỗi/cooldown; hoặc không slot nào bật | `slots_by_status`, `last_error_code/category` từng slot, nút Kiểm tra | xem §3; kiểm khoá (`PERMISSION_DENIED`, `API_KEY_INVALID`), model (`NOT_FOUND`), 503 phía Google |
| "Phản hồi bị ngắt giữa chừng" | SSE `ai_provider_interrupted` hoặc luồng đóng không có `done` | nhà cung cấp đứt giữa chừng; proxy cắt kết nối | `last_error_*` | "Tạo lại" (tốn 1 lượt) |
| 413 `request_too_large` | | thân > 256 KB gửi tới `/api/ai/*` hoặc `/api/admin/ai/*` | — | không phải lỗi người dùng thường; xem log |
| Stream không chạy dần | | Render free vừa ngủ dậy (chậm 30–60 s); proxy đệm | heartbeat `: ping` 15 s trong Network; `GET /api/health` | chờ; nếu lặp lại, kiểm gói Render |
| Slot COOLDOWN mãi | | 429 từ Google (hạn mức/ngày của khoá hết) | `recent_429`, `last_error_code=provider_http_429` | để cooldown tự hết; Reset cooldown chỉ khi chắc khoá đã hồi |
| Slot MISSING_SECRET | | thiếu `FAS_AI_SECRET_<REF>` trên host | `h.secret.present=false` | Owner đặt biến trên Render rồi khởi động lại |

Kiểm nhanh chỉ-đọc: `GET /api/health` (`commit_sha`, `ai_assistant`), `/admin/ai` (tổng quan, từng slot, audit), `GET /api/ai/availability` bằng phiên của chính bạn (không lộ cấu hình cho người thường: `reason:"off"`; Owner thấy chi tiết).

Khối **"Ai đang dùng được · hàng đợi luồng"** ở đầu `/admin/ai` (từ `overview.runtime`) cho biết ngay: khán giả đang áp (`all` / `beta` / `canary`; rỗng = cấu hình sai, AI tắt cho mọi người), số **luồng SSE đang chạy / tối đa** trên instance (đầy thì người dùng nhận 503 `ai_busy`; kẹt ở mức cao khi hầu như không ai dùng = nghi khoá luồng rò), và RPM/người. Dòng **"Còn lại hôm nay"** dưới thanh trần toàn cục cho biết còn bao nhiêu lượt trước khi người dùng nhận 429 `scope:"global"`.

---

## 7. Quy trình an toàn

### 7.1 Đổi hạn mức công khai (5 lượt/người, 150 lượt toàn cục)

Không đổi trong lúc đang có sự cố, và **không đổi mà không có Owner**.

1. `/admin/ai` → *Hạn mức* (hoặc *Preset*). Kiểm **năng lực pool** trước: (số slot HEALTHY) × (trần ngày của slot, hiện đặt 30) phải **lớn hơn** trần toàn cục mới, kèm dư cho 1–2 slot lỗi.
2. Nâng trần *người dùng* cần nâng cả trần *token* tương ứng (token người ≈ lượt × 3.000), nếu không trần token chạm trước.
3. Lưu (form gửi `expected_version`; hai Owner cùng sửa thì người sau nhận 409). Hiệu lực ≤ 15 s.
4. Kiểm *Audit* có dòng mới (người sửa, giá trị cũ → mới) và `availability` của một tài khoản thường cho `requests_limit` mới.
5. Hoàn tác: áp lại preset `beta` (5/150).
6. **Đừng** dùng `0` ("không giới hạn") cho trần người dùng/toàn cục ở production.

### 7.2 Thêm slot hoặc provider

* **Thêm slot cùng loại (vd. thêm khoá Gemini):** tạo `secret_ref` (tên, không phải giá trị) → Owner đặt `FAS_AI_SECRET_<REF>` trên Render (khoá **không** nhập ở UI) → khởi động lại/deploy → tạo slot ở `/admin/ai` ở trạng thái **TẮT**, đặt `daily_request_cap`, `rpm_soft_cap`, giá → *Kiểm tra* ≥ 3 lần liên tiếp tới `probe_stable` → bật 1 slot mới mỗi lần → theo dõi 1 giờ.
* **Thêm LOẠI provider chưa hỗ trợ:** cần mã (PR có test): `control/model.py` (`PROVIDER_TYPES`, danh sách host cho phép chống SSRF), `control/providers.py` (factory), test trong `server/tests/test_ai_control_plane.py`, rồi thêm vào hồ sơ định tuyến. Không bật provider mới khi Owner chưa duyệt; không thêm SDK/dịch vụ trả phí.
* Không bao giờ: dán khoá vào chat/PR/log, liệt kê toàn bộ biến Render, hay mở rộng quyền ghi của nhà cung cấp.

### 7.3 Mở rộng / thu hẹp khán giả

`canary` (Owner + `FAS_AI_CANARY_USERS`) → `beta` (+ `FAS_AI_BETA_USERS`, tối đa 50) → `all`. Mỗi bước đổi biến env **rồi deploy backend** rồi kiểm `/api/health` → `ai_assistant.audience`. Thu hẹp: ngược lại. Công cụ phía Owner (ngoài repo) làm bước này có kiểm tra và đường rút lui.

---

## 8. Kiểm thử hồi quy (chạy trước mọi deploy liên quan AI)

| Lớp | Lệnh | Phủ |
|---|---|---|
| Backend AI | `python -m unittest discover -s server/tests -t . -p "test_ai_*.py"` | quota, QA lane, control plane, router, bảo mật, E2E sản phẩm (`test_ai_e2e_regression.py`), pool/failover (`test_ai_router_hardening.py`), giới hạn thân (`test_ai_body_limit.py`) |
| Web | `npm test` (trong `web/`) + `npm run typecheck` + `npm run lint` | hành vi thuần, bất biến tĩnh, cách ly phiên (`ai-session-isolation.test.mjs`) |
| Giao diện thật | `node scripts/qa/ai_ui/run.mjs` | Chrome headless: 320→1280, luồng gửi/dừng/tạo lại/hết lượt/đổi tài khoản/focus/giảm chuyển động/hiệu năng (xem README trong thư mục đó; không chạy trong CI) |
| Thiết bị thật | thủ công | bàn phím ảo iOS/Android với bố cục `/assistant`, Safari — **chưa kiểm** |

Không dùng khoá/nhà cung cấp thật trong các test trên: nhà cung cấp là bản giả có kịch bản.

---

## 9. Rủi ro còn lại & quyết định đang mở

* Breaker/cooldown nằm trong tiến trình: deploy xoá chúng → *Kiểm tra* từng slot sau mỗi deploy.
* Một instance Render gói free: ngủ/chậm; trần luồng 4/instance.
* Hai lượt kết thúc cùng lúc trên **hai instance** vẫn có thể ghi đè bộ đếm (khoá hiện chỉ trong một tiến trình); Render đang chạy một instance.
* Cửa sổ vài mili-giây giữa kiểm hạn mức và nhận khoá luồng có thể cho một người đi quá trần **thêm 1 lượt** trong tình huống hiếm (người đó phải gửi đúng lúc lượt trước vừa kết thúc).
* Client chậm đọc rồi ngắt kết nối khi uvicorn đang bị chặn ở backpressure: vé luồng được nhả ngay ở response, còn `_finalize` (ghi hạn mức) chạy khi vòng lặp dọn generator — vài mili-giây, có thể lâu hơn nếu có vòng tham chiếu. Lượt kế của cùng người có thể qua bước kiểm hạn mức trước khi lượt cũ được ghi (tối đa +1–2 lượt, bị RPM 8/phút kìm). Không sửa: `aclose()` trong lúc huỷ có rủi ro cao hơn lợi ích.
* Lớp `GeminiProvider` cũ (khoá trong tham số URL `key=`) KHÔNG được pool control plane dùng: slot Gemini đi qua endpoint tương thích OpenAI với khoá ở header `Authorization`. Đừng gắn lớp cũ vào slot — ngoại lệ httpx có thể in cả URL vào log.
* Các route POST/PUT khác của API (ngoài `/api/ai/*` và `/api/admin/ai/*`) chưa có trần thân riêng: FastAPI đọc hết thân vào RAM trước khi xác thực. Ngoài phạm vi tính năng AI; cân nhắc một trần toàn app trong lần làm cứng sau.
* Khoá FFW1–FFW7 bị lộ tiền tố ngày 2026-10-01: **Owner hoãn xoay** (bước và công cụ đã sẵn); cân nhắc lại khi beta ổn định.
* Hành vi bàn phím ảo trên điện thoại thật chưa được kiểm (xem §8).
