# AI Control Plane — `/admin/ai`

Bảng điều khiển cho **Owner/Admin** để định tuyến provider, đặt hạn mức và theo dõi sức khoẻ của Trợ lý AI V1. Mã nguồn: `server/ai_assistant/control/`, giao diện: `web/src/app/admin/ai/`.

## 0. Nguyên tắc

1. **Cờ `FAS_AI_ADMIN_V1`, mặc định TẮT.** Khi tắt: mọi route `/api/admin/ai/*` trả 503 `ai_admin_not_enabled`; chat dùng chuỗi provider từ env như cũ (`FAS_AI_PROVIDERS`). Khi bật: API/UI quản trị mở; **chat định tuyến theo cấu hình trong kho**, bỏ qua `FAS_AI_PROVIDERS`/`AI_*`.
2. **CẤU HÌNH tách khỏi BÍ MẬT.** Kho (Appwrite) chỉ chứa cấu hình, bộ đếm và nhật ký. Khoá API chỉ nằm trong biến môi trường máy chủ.
3. **Fail-closed.** Thiếu cấu hình → AI tắt. Cấu hình hỏng → AI tắt. Kho không với tới được → dùng bản hợp lệ gần nhất tối đa 10 phút, sau đó AI tắt. Không bao giờ âm thầm rơi về một provider trả phí không giới hạn.
4. **Quyền.** Đọc (`GET`): ADMIN hoặc OWNER. Ghi: **chỉ OWNER**. MODERATOR và người thường: 403. Chưa đăng nhập: 401.

## 1. Tham chiếu bí mật

| Nơi | Thấy gì |
|---|---|
| Slot trong kho (`ai_provider_slots.secret_ref`) | Tên tham chiếu, ví dụ `GEMINI_PROJECT_01` |
| Biến môi trường máy chủ | `FAS_AI_SECRET_GEMINI_PROJECT_01=<khoá thật>` — Owner đặt trên host |
| API quản trị / giao diện | `secret_ref`, tên biến môi trường, có/thiếu, vân tay `sha256:xxxxxxxx` (8 hex) |
| Client bundle, log, nhật ký audit, Appwrite | **Không bao giờ** có giá trị khoá |

`secrets.py::SecretResolver` đọc biến môi trường **lúc gọi** (không cache vào cấu hình). Đổi khoá = đổi biến môi trường + khởi động lại; vân tay đổi theo, client provider được dựng lại.

**Khoá gắn với loại provider.** `secret_ref` phải bắt đầu bằng tên loại viết hoa: `GEMINI_…`, `GROQ_…`, `WORKERS_AI_…`, `QWEN_…`, `AZURE_OPENAI_…`, `OPENROUTER_…`, `ALIBABA_…`. Nhờ vậy không thể trỏ lại một slot để gửi khoá Gemini tới endpoint Azure (hay loại khác).

## 2. Mô hình cấu hình

### Slot provider (`ProviderSlot`)

> **Thêm 2026-10:** loại `alibaba` (Alibaba Model Studio, **ngủ đông**, cổng máy chủ `FAS_AI_ALIBABA_ENABLED`), trường `tiers` (tầng năng lực), `free_quota_remaining` / `free_quota_expires_at` / `free_quota_only` (hạn mức miễn phí), độ trễ/TTFT trong `health.latency`, trạng thái `GATE_CLOSED` / `QUOTA_EXHAUSTED` / `META_CORRUPT`. Chi tiết, bảng lỗi và migration: `ALIBABA_PROVIDER.md`. Cờ loại thiếu trong cấu hình cũ = tắt (khoá lạ vẫn là lỗi).

`slot_id` (2–27 ký tự: id tài liệu usage là `{slot_id}_{yyyymmdd}` và Appwrite giới hạn 36 ký tự), `provider_type` (`gemini`, `groq`, `workers_ai`, `qwen`, `azure_openai`, `openrouter`, `alibaba`), `label`, `secret_ref`, `model` (không có `..`; với Azure không có `/`), `enabled`, `endpoint` (bắt buộc với `workers_ai`/`azure_openai`; ≤300 ký tự; host nằm trong danh sách cho phép theo loại — chống SSRF), `api_version` (Azure), `priority` (0–99, nhỏ thử trước), `weight` (1–100), `daily_request_cap`, `daily_token_cap`, `rpm_soft_cap`, `tpm_soft_cap` (0 = không trần), `workloads` (`general`, `story`, `support`, `writer`, `web_search`), giá micro-USD / 1M token (vào/ra) để ước tính chi phí.

**Gemini project pool** = nhiều slot `provider_type=gemini`, mỗi slot một `secret_ref` riêng (`GEMINI_PROJECT_01`…). Cooldown, bộ đếm, sức khoẻ tính **theo slot**, nên project 03 bị 429 không kéo project 01 xuống.

**Cân bằng trong một pool:** `priority` vẫn là **tầng** (tầng nhỏ thử trước). Trong cùng một priority, thứ tự là ngẫu nhiên có trọng số: `weight × hệ số cân bằng` (`ControlPlane.balance_factor`).
- `phần còn = 1 − max(yêu cầu/ngày, token/ngày, yêu cầu/phút RPM mềm, token/phút TPM mềm)`. Trần 0 nghĩa là không giới hạn và được bỏ qua. Hệ số là `phần còn²`.
- Hệ số ×0,25 nếu slot đang lỗi liên tiếp, và ×0,25 nếu slot bị 429 trong 10 phút gần nhất. Sàn của hệ số là 0,01, để slot gần đầy vẫn làm được phương án cuối.
- Hệ quả: các slot **cùng priority** tiêu đều nhau, không project nào cạn trước. Test mô phỏng 200 lượt qua 9 slot: không slot nào chạm trần 30, chênh lệch ≤8 lượt. Pool vẫn dùng hết được 100% tổng hạn mức.
- Muốn thử tuần tự kiểu cũ thì đặt priority khác nhau.
- Cooldown, hết trần, tắt và thiếu khoá vẫn bị **bỏ qua hẳn** như trước; hệ số chỉ sắp thứ tự các slot đủ điều kiện.

**Kiểm slot (Owner):** `POST /api/admin/ai/slots/{id}/probe` gửi **một** request tối thiểu thật qua khoá, endpoint và model của slot. Gọi được cả khi slot đang tắt và công tắc tổng TẮT, nên kiểm được project mới trước khi cho phục vụ người dùng.
- Kết quả chỉ gồm `ok`, `latency_ms`, `code`, `category` đã làm sạch; không bao giờ có văn bản của nhà cung cấp.
- **Ngân sách kiểm tách riêng:** probe **không bao giờ** ghi vào sổ usage, nên không trừ vào hạn mức toàn cục, hạn mức mỗi người hay hạn mức slot mà bước admission áp.
  - Probe có bộ đếm riêng hiển thị công khai trên admin (`health.probes_today`, `overview.probes_today`) và trần riêng: 30 lần / slot / ngày UTC.
  - Bản ghi bền là audit `slot:<id>.probe`.
  - Probe vẫn nuôi **health** như lưu lượng thật: breaker, cooldown 429 và phạt 429 khi cân bằng, `last_error_*`.
- Mỗi slot tối đa 1 lần / 20 giây (409 nếu gọi dồn).
- **Kiểm lại an toàn:** health giữ 5 lần kiểm gần nhất (`probe_history`).
  - `probe_stable = true` khi 3 lần gần nhất đều đạt và mỗi lần ≤ 5 giây.
  - Probe **không bao giờ tự bật slot**: slot chập chờn (ví dụ `gemini-05`) cứ để TẮT và kiểm lại khi tiện, rollout không phải chờ nó.
- Quy trình mở rộng: tạo slot TẮT → cài khoá → deploy → **Kiểm tra** (3 lần, cách ≥ 20 giây) → chỉ bật slot `ổn định`.

### Preset rollout (`model.ROLLOUT_PRESETS`)

Áp bằng `PUT /api/admin/ai/presets/{name}` (OWNER, kèm `expected_version`). Mỗi lần áp ghi audit từng trường cộng một dòng `global.rollout_preset`. Preset **chỉ đặt hạn mức**: không bao giờ đụng `ai_enabled` (công tắc khẩn cấp độc lập và luôn thắng, kể cả khi `expected_version` cũ), cũng không đụng định tuyến hay khán giả. `config.rollout.active_preset` cho biết preset nào đang khớp; đã sửa tay thì hiện `custom`.

| Preset | Mỗi người / ngày | Toàn cục / ngày | Token mỗi người | Token toàn cục | Token ra / ngữ cảnh mỗi lượt |
|---|---|---|---|---|---|
| `canary` (đang dùng) | 20 request | 40 request | 40.000 | 80.000 | 400 / 4000 |
| `beta` (đề xuất) | **5 request** | **150 request** | 15.000 | 450.000 | 400 / 4000 |

Với beta, 8 slot × 30 = 240 request/ngày và 8 × 60.000 token. Cả hai đều vượt trần toàn cục, nên **trần toàn cục là giới hạn thật** và còn dư khi một vài slot lỗi.

### Hồ sơ định tuyến

| Hồ sơ | Thứ tự mặc định |
|---|---|
| `FREE_FIRST` | gemini → groq → workers_ai → openrouter |
| `QUALITY_FIRST` | azure_openai → gemini → openrouter |
| `WRITER` | azure_openai → gemini |
| `STORY` | gemini → groq |
| `SUPPORT_SAFE` | azure_openai → **gemini** (chỉ slot có workload `support`). Gemini ở cuối: khi chỉ có pool Gemini, chế độ Hỗ trợ không rơi vào `ai_no_provider` |
| `WEB_SEARCH` | gemini (LLM cho lượt có tìm web). Công cụ tìm web THẬT vẫn do cấu hình `web_search_provider` hiện có quyết định; `web_search_tool` trong control plane hiện chỉ nhận `off` và để dành cho bước sau |

Loại `qwen` (DashScope cũ) **đã nghỉ hưu khỏi các hồ sơ mặc định** (trước đây có ở cả sáu) và có cổng riêng `FAS_AI_QWEN_LEGACY_ENABLED`; thứ tự cũ
giữ ở `model.LEGACY_QWEN_PROFILE_STEPS` làm đường quay về tường minh (`ALIBABA_PROVIDER.md` mục 2b). Hồ sơ đã lưu có bước `qwen` vẫn hợp lệ.
Bước `alibaba`/slot Alibaba của một hồ sơ **không** nằm trong `ai_routing_profiles` mà ở `ai_alibaba_config` (mục 4).

Chế độ → hồ sơ: `general→FREE_FIRST`, `story→STORY`, `writer→WRITER`, `support→SUPPORT_SAFE`; lượt tìm web → `web_search_profile`. Owner đổi được thứ tự, thêm/bớt bước, tắt hồ sơ.

Mỗi **bước** là một loại provider (cả pool: xếp theo `priority`, cùng mức thì xáo có trọng số theo `weight`) hoặc một `slot_id` cụ thể. Mỗi request thử mỗi slot **tối đa một lần**; chỉ được chuyển slot **trước** token đầu tiên.

### Điều khiển toàn cục (`GlobalControls`)

`ai_enabled` (công tắc tổng), bật/tắt theo loại provider, trần request/token toàn cục mỗi ngày, trần request/token mỗi người dùng mỗi ngày, trần chi phí ngày (tuỳ chọn), `max_output_tokens`, `max_context_tokens`, ánh xạ chế độ → hồ sơ, `web_search_profile`, `web_search_tool`, `version` (khoá lạc quan).

### Khán giả (`FAS_AI_AUDIENCE`, env — không nằm trong kho)

Cùng mẫu với `FAS_CHAT_V1_AUDIENCE`. Quyết định **ai** gọi được `/api/ai/*` khi `FAS_AI_ASSISTANT_V1=1`. Cờ giao diện `NEXT_PUBLIC_AI_ASSISTANT_ENABLED` chỉ ẩn/hiện UI, không phải rào chặn.

| `FAS_AI_AUDIENCE` | Ai dùng được |
|---|---|
| rỗng + `DATA_BACKEND=appwrite` (production) | như `canary` — **đóng theo mặc định** |
| rỗng + backend khác (dev/test) | như `all` |
| `canary` | chỉ Owner (`FAS_OWNER_USER_IDS`) + `FAS_AI_CANARY_USERS` (phân tách bằng dấu phẩy; mục không giống user ID bị bỏ) |
| `beta` | nhóm `canary` + **`FAS_AI_BETA_USERS`** (danh sách tester, tối đa **50** ID, mục trùng bị gộp). Vượt trần thì AI TẮT, không âm thầm cắt bớt. `/api/health` hiện thêm `beta_users` (chỉ số lượng) |
| `all` | mọi người đã đăng nhập |
| giá trị khác | AI TẮT (`reason` nêu biến sai) |

Thứ tự mở rộng: `canary` (Owner) → `beta` (10–30 tester) → `all`. Thêm hoặc bớt tester là sửa `FAS_AI_BETA_USERS` rồi deploy backend.

Người ngoài khán giả nhận `GET /api/ai/availability` → `enabled:false, reason:"not_in_audience"` (không lộ hạn mức). Mọi route khác trả 403 `ai_not_enabled`. Thứ tự kiểm: AI tắt → 503 như cũ; AI bật thì chưa đăng nhập 401 → ngoài khán giả 403 → mới tới hạn mức/công tắc tổng. `/api/health` công khai hiện `ai_assistant.audience` (chỉ giá trị đã phân giải, không có ID nào).

**Cổng hiển thị `GET /api/ai/access`:**
- **Phản hồi:** đúng một bit `{"eligible": bool}`, kèm `Cache-Control: no-store, private` và `Vary: Authorization`. Chưa đăng nhập thì 401.
- **Ai vẽ lối vào:** frontend chỉ vẽ nút nổi, mục "Trợ lý AI" trong menu tài khoản, lối vào ở trang truyện và linh vật nổi khi bit này là `true`. Đang hỏi hoặc có lỗi đều tính là không vẽ.
- **Một nguồn sự thật:** `AiRuntime.access_state()` cho ra `ok | off | not_in_audience | disabled_by_admin`. Availability và `/api/ai/access` cùng đọc nó; `eligible` chỉ là `true` khi kết quả là `ok`. Vì vậy cờ backend tắt, người ngoài khán giả, hay công tắc khẩn cấp đều ẩn lối vào.
- **Client không thấy gì khác:** không ID, không danh sách, không lý do, không provider.
- **Chỉ là cổng HIỂN THỊ:** mọi route `/api/ai/*` vẫn tự chặn ở mỗi request bằng chính `serving()` + `allows()`, nên sửa bit trong trình duyệt chỉ hiện ra một nút mà máy chủ vẫn từ chối.
- **Bài kiểm:** `server/tests/test_ai_access.py` và `web/tests/ai-access-gate.test.mjs`.

**Cờ build giao diện trên production:**
- **Nguồn:** `production-deploy.yml` đọc `NEXT_PUBLIC_AI_ASSISTANT_ENABLED` và `NEXT_PUBLIC_AI_COMPANION_ENABLED` từ **biến repository** `PRODUCTION_AI_ASSISTANT_ENABLED` và `PRODUCTION_AI_COMPANION_ENABLED`.
- **Kiểm tra:** cả hai phải đúng `"0"` hoặc `"1"`, và companion=1 đòi assistant=1. Việc kiểm diễn ra ở job `validate`, TRƯỚC khi chạm tới Render hay Cloudflare.
- **Bản sao cấp môi trường `production` lệch giá trị:** workflow DỪNG.
- **Kết quả:** lần deploy tự động sau không thể âm thầm lật cờ. Muốn đổi cờ thì đổi biến rồi deploy.
- **Rollback frontend** (`wrangler rollback`) trả về bản build trước, kèm đúng cờ của bản đó.

## 3. Thứ tự kiểm một lượt chat

0. Khán giả (ở trên): ngoài khán giả → 403 trước mọi bước dưới.
1. `admission()` (trước khi stream): công tắc tổng → 503 `ai_not_enabled`; trần toàn cục/chi phí → 429 `ai_budget_exhausted` `scope:"global"`; trần theo người dùng → 429 `ai_budget_exhausted` `scope:"user"` (lối QA của Owner: hạn mức QA → `scope:"qa"`, xem "Hạn mức người dùng và lối QA"). **Không đọc được bộ đếm** (kho sập, hôm nay chưa có số nào trong bộ nhớ) → 503 `ai_storage_unavailable`: số không biết không bao giờ được coi là 0. Ngân sách token theo tier cũ vẫn áp dụng (cũng `scope:"user"`). Tất cả các từ chối này xảy ra TRƯỚC khi tin nhắn được lưu.
2. `plan()`: dựng danh sách slot theo hồ sơ, mỗi slot kèm lý do bỏ qua hoặc "đủ điều kiện": `slot_disabled`, `type_disabled`, `workload_not_allowed`, `missing_secret`, `cooldown`, `request_cap`, `token_cap`, `rpm_soft_cap`, `tpm_soft_cap`.
3. `ControlledGateway.stream()`: thử lần lượt, mỗi slot tối đa một lần. 429 → cooldown theo `Retry-After` (kẹp 1–600 s, mặc định 30 s); lỗi khác → circuit breaker theo slot (3 lần liên tiếp mở 60 s). Không bắt đầu lần thử mới sau **45 s** kể từ lần thử đầu (`FAILOVER_BUDGET_S`), và không bắt đầu lần thử nào khi client đã bỏ đi (`cancel`). Không còn slot nào → sự kiện lỗi theo NGUYÊN NHÂN THẬT (`router.exhausted_event`): đã thử mà đều lỗi → `ai_provider_unavailable`; chỉ chạm cửa sổ RPM/TPM mềm → `ai_busy`; có slot đang cooldown → `ai_provider_unavailable`; mọi slot chạm trần NGÀY → `ai_budget_exhausted` (`scope:"global"` + giờ reset); không có gì bật/cấu hình → `ai_no_provider`. Trước đây RPM/TPM bị báo như hết hạn ngày (kèm giờ reset nửa đêm) và cooldown bị báo như `ai_no_provider`.
4. Kết thúc lượt: cộng usage/chi phí cho **đúng slot đã phục vụ** (`ai_provider_usage_daily`), cùng lúc với ledger theo người dùng như trước.

**Lỗi gần nhất của slot** (health: `last_error_code`, `last_error_category`, `last_error_at`):
- `last_error_code` là mã máy ổn định: `provider_http_<status>`, `provider_network_error`, `provider_unexpected_error`…
- `last_error_category` là enum của nhà cung cấp: `error.status` của Google (`NOT_FOUND`, `PERMISSION_DENIED`…), kèm `ErrorInfo.reason` nếu có (`PERMISSION_DENIED:SERVICE_DISABLED`); hoặc `error.code`/`error.type` kiểu OpenAI (`model_not_found`…).
- Server đọc tối đa 16 KB thân lỗi, parse trong bộ nhớ rồi bỏ. Chỉ giữ giá trị nằm trong danh sách cho phép đóng hoặc khớp mẫu UPPER_SNAKE (không có chữ số, không có chữ thường). **Không bao giờ lưu `message`, request echo, project hay khoá.**
- Ghi ở mọi pha, kể cả khi đứt giữa stream. Dữ liệu nằm trong tiến trình giống breaker, nên khởi động lại là mất.

### Hạn mức người dùng và lối QA

**Giao diện người dùng chỉ hiện hạn mức RIÊNG của họ.** `GET /api/ai/availability` → `limits` gồm `requests_used`, `requests_limit`, `requests_remaining`, `exhausted`, `reset_at`: đúng ba phép kiểm mà lượt gửi kế tiếp sẽ gặp (trần lượt/ngày và trần token/ngày của control plane, cùng ngân sách token hạng tài khoản cũ). Dòng giao diện là "Hôm nay còn 3/5 lượt hỏi · làm mới lúc 07:00", hết thì ô soạn khoá. Mức dùng toàn site, công suất nhà cung cấp, phần trăm "đã dùng" **không bao giờ** ra người dùng; chúng nằm ở `/admin/ai` ("Hạn mức toàn cục hôm nay"). Trước đây giao diện hiện "Đã dùng 51% hạn mức hôm nay" (token cũ) ngay cạnh "đã hết lượt hỏi" (trần 5 lượt thật): hai thước đo khác nhau.

Hết công suất chung là chuyện khác: 429 `scope:"global"`, giao diện nói "không phải do bạn", không kèm số. Hạn mức riêng của người dùng không đổi trong trường hợp đó.

**Lối QA của Owner** (`qa: true` trong thân lượt gửi) để smoke test không ăn vào 5 lượt/ngày của chính Owner:
- Chỉ Owner (`FAS_OWNER_USER_IDS`) và chỉ khi control plane bật; người khác gửi cờ thì bị bỏ qua, lượt tính như lượt thường.
- Ghi vào sổ riêng (khoá tổng hợp trong `ai_usage_daily`), có hạn mức riêng `FAS_AI_OWNER_QA_DAILY_REQUESTS` (mặc định 20/Owner/ngày, `0` = đóng). Là biến môi trường chứ không phải trường lưu: thêm cột Appwrite chưa có trên production sẽ làm hỏng mọi lần ghi cấu hình, kể cả nút tắt khẩn cấp.
- **Không phải cửa sau**: công tắc khẩn cấp, mọi trần TOÀN CỤC, slot và RPM áp y hệt; lượt QA nằm trong tổng "Yêu cầu hôm nay". Lượt thường của Owner vẫn bị trần riêng như mọi người.
- `/admin/ai` có ô "Lượt QA của Owner"; "Người dùng AI hoạt động" không đếm sổ QA.
- Cách dùng trong smoke: `POST /api/ai/conversations/{id}/messages` với `{"content": …, "client_id": …, "qa": true}`; `GET /api/ai/availability` của Owner có khối `qa` báo còn bao nhiêu lượt QA.

## 4. Schema (bổ sung thuần — CHƯA áp lên production)

| Collection | Khoá | Nội dung |
|---|---|---|
| `ai_control_settings` | `global` | Điều khiển toàn cục |
| `ai_provider_slots` | `slot_id` | Slot (không có khoá) |
| `ai_routing_profiles` | tên hồ sơ | `steps_json`, `enabled` |
| `ai_provider_usage_daily` | `{slot_id}_{yyyymmdd}` | requests, tokens, errors, 429, chi phí micro-USD, lần thành công cuối |
| `ai_admin_audit` | ngẫu nhiên | admin_id, at, entity, field, old_value, new_value |
| `ai_alibaba_config` | `s-<slot_id>` / `r-<hồ sơ>` | **Vùng tách biệt** của Alibaba Model Studio: `kind` (`slot`\|`route`), `key`, `data_json` (slot hoặc danh sách bước đầy đủ), `updated_at`. Bản cũ không đọc collection này — nên một slot/bước Alibaba đã lưu không thể làm hỏng cấu hình Gemini khi rút mã. Chỉ cần khi dùng Alibaba |

Tất cả `permissions=[]`, `documentSecurity=true` (chỉ backend đọc/ghi). Kế hoạch offline: `python scripts/setup_appwrite.py --dry-run --only=<collection>`. PLAN chỉ đọc trên production: Owner chạy script plan có rào chặn mọi phương thức khác GET, rồi mới apply khi đã duyệt.

## 5. API

| Phương thức | Đường | Quyền |
|---|---|---|
| GET | `/api/admin/ai/overview` (kèm `runtime`: khán giả, RPM/người, luồng đang chạy/tối đa — không ID, không khoá) | ADMIN, OWNER |
| GET | `/api/admin/ai/config` | ADMIN, OWNER |
| GET | `/api/admin/ai/audit?limit=` | ADMIN, OWNER |
| PUT | `/api/admin/ai/global` (+ `expected_version`) | OWNER |
| PUT | `/api/admin/ai/provider-types/{type}` | OWNER |
| POST | `/api/admin/ai/slots` | OWNER |
| PUT / DELETE | `/api/admin/ai/slots/{slot_id}` | OWNER |
| POST | `/api/admin/ai/slots/{slot_id}/reset-cooldown` | OWNER |
| POST | `/api/admin/ai/slots/{slot_id}/probe` (1 request thật; 409 nếu < 20 s) | OWNER |
| PUT | `/api/admin/ai/profiles/{name}` | OWNER |

Lỗi: 422 `ai_admin_invalid` (kèm danh sách `{field, message}`), 409 `ai_admin_conflict` (trùng id, slot đang được hồ sơ dùng, version cũ, kho hỏng), 404, 503.

## 6. Nhật ký audit

Mọi thay đổi ghi từng **trường**: admin_id, thời điểm, entity (`global`, `slot:<id>`, `profile:<tên>`, `provider_type:<loại>`), giá trị cũ → mới (không bí mật; `secret_ref` là tên nên được ghi). Xoá slot ghi giá trị cũ → `null`. Reset cooldown cũng được ghi. Nếu kho từ chối lần ghi audit sau khi thay đổi đã lưu, từng dòng audit được ghi vào log lỗi của máy chủ (`ai_control audit (store write failed)`) thay vì trả 503 cho một thay đổi đã áp dụng.

## 6b. Đồng thời và đường sửa

- Mọi thao tác ghi chạy **tuần tự trong một tiến trình**. Appwrite không có ghi có điều kiện; giữa nhiều instance vẫn có thể có lần ghi đè (xem Giới hạn).
- **Tắt khẩn cấp luôn thắng**: `ai_enabled=false` và tắt một loại provider không bao giờ bị từ chối vì `expected_version` cũ. Bật lại thì phải có bản cấu hình hiện tại (409 nếu cũ).
- Không tạo được slot thứ 41 (quá `MAX_SLOTS` sẽ làm cả cấu hình không hợp lệ).
- Khi mọi dòng đọc được nhưng **cả cấu hình** không hợp lệ (ví dụ hồ sơ còn trỏ tới slot vừa bị xoá ở instance khác): AI tắt, nhưng Owner vẫn **xoá slot, sửa hồ sơ, reset cooldown** được từ `/admin/ai` để đưa cấu hình về hợp lệ. Mọi thao tác khác trả 409 cho tới lúc đó.

## 7. Giới hạn đã biết

- Cooldown, cửa sổ RPM/TPM mềm và đếm 429 gần đây nằm **trong tiến trình** (một instance). Bộ đếm ngày và cấu hình thì bền (Appwrite).
- Bộ đếm slot (`ai_provider_usage_daily`, chính là trần toàn cục) dùng đọc-sửa-ghi nhưng được **khoá theo (slot, ngày)** trong một tiến trình; giữa HAI instance vẫn có thể lệch nhỏ (Render đang chạy một instance). Bộ đếm người dùng (`ai_usage_daily`) không cần khoá vì mỗi người chỉ có một luồng tại một thời điểm.
- Thân yêu cầu tới `/api/ai/*` và `/api/admin/ai/*` bị cắt ở **256 KB** (`server/body_limit.py`, 413 `request_too_large`) trước khi FastAPI đọc vào bộ nhớ — kể cả khi chưa đăng nhập.
- Cấu hình được cache 15 s: đổi cấu hình có hiệu lực trong ≤15 s trên mọi instance.
- Chi phí là **ước tính** theo giá Owner nhập, không phải hoá đơn thật.
- Ghi tuần tự chỉ trong một instance: hai instance cùng ghi dòng `global` có thể đè nhau (Render hiện chạy một instance).
- Danh sách host Azure là hậu tố (`.openai.azure.com`, `.cognitiveservices.azure.com`), nên một phiên Owner bị chiếm có thể trỏ slot Azure tới resource Azure của người khác cùng với khoá `AZURE_OPENAI_*`. Chỉ Owner làm được và mọi thay đổi có audit.

## 8. Rollout (mỗi bước chờ Owner duyệt)

1. Merge PR (cờ tắt, không đổi hành vi).
2. PLAN chỉ đọc cho 5 collection mới (+ 7 collection `ai_*`) → duyệt → apply.
3. Đặt `FAS_AI_SECRET_<ref>` cho các slot sẽ dùng (Render / host mới).
4. Bật `FAS_AI_ADMIN_V1=1` (AI vẫn tắt: công tắc tổng mặc định TẮT, mọi loại provider TẮT).
5. Owner tạo slot, chọn hồ sơ, đặt trần trên `/admin/ai`, kiểm sức khoẻ.
6. Chỉ sau đó mới bật `FAS_AI_ASSISTANT_V1` và công tắc tổng — để `FAS_AI_AUDIENCE` trống (production = `canary`, chỉ Owner) cho canary; kiểm `/api/health` → `ai_assistant.audience == "canary"` trước khi bật công tắc tổng.
7. Mở rộng: thêm ID vào `FAS_AI_CANARY_USERS`, rồi `FAS_AI_AUDIENCE=all` + `NEXT_PUBLIC_AI_ASSISTANT_ENABLED=1` khi ra công chúng.
