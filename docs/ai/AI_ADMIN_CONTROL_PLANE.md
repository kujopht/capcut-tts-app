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

**Khoá gắn với loại provider.** `secret_ref` phải bắt đầu bằng tên loại viết hoa: `GEMINI_…`, `GROQ_…`, `WORKERS_AI_…`, `QWEN_…`, `AZURE_OPENAI_…`, `OPENROUTER_…`. Nhờ vậy không thể trỏ lại một slot để gửi khoá Gemini tới endpoint Azure (hay loại khác).

## 2. Mô hình cấu hình

### Slot provider (`ProviderSlot`)

`slot_id` (2–27 ký tự: id tài liệu usage là `{slot_id}_{yyyymmdd}` và Appwrite giới hạn 36 ký tự), `provider_type` (`gemini`, `groq`, `workers_ai`, `qwen`, `azure_openai`, `openrouter`), `label`, `secret_ref`, `model` (không có `..`; với Azure không có `/`), `enabled`, `endpoint` (bắt buộc với `workers_ai`/`azure_openai`; ≤300 ký tự; host nằm trong danh sách cho phép theo loại — chống SSRF), `api_version` (Azure), `priority` (0–99, nhỏ thử trước), `weight` (1–100), `daily_request_cap`, `daily_token_cap`, `rpm_soft_cap`, `tpm_soft_cap` (0 = không trần), `workloads` (`general`, `story`, `support`, `writer`, `web_search`), giá micro-USD / 1M token (vào/ra) để ước tính chi phí.

**Gemini project pool** = nhiều slot `provider_type=gemini`, mỗi slot một `secret_ref` riêng (`GEMINI_PROJECT_01`…). Cooldown, bộ đếm, sức khoẻ tính **theo slot**, nên project 03 bị 429 không kéo project 01 xuống.

### Hồ sơ định tuyến

| Hồ sơ | Thứ tự mặc định |
|---|---|
| `FREE_FIRST` | gemini → groq → workers_ai → qwen → openrouter |
| `QUALITY_FIRST` | qwen → azure_openai → gemini → openrouter |
| `WRITER` | qwen → azure_openai → gemini |
| `STORY` | gemini → groq → qwen |
| `SUPPORT_SAFE` | azure_openai → qwen (chỉ slot có workload `support`) |
| `WEB_SEARCH` | gemini → qwen (LLM cho lượt có tìm web). Công cụ tìm web THẬT vẫn do cấu hình `web_search_provider` hiện có quyết định; `web_search_tool` trong control plane hiện chỉ nhận `off` và để dành cho bước sau |

Chế độ → hồ sơ: `general→FREE_FIRST`, `story→STORY`, `writer→WRITER`, `support→SUPPORT_SAFE`; lượt tìm web → `web_search_profile`. Owner đổi được thứ tự, thêm/bớt bước, tắt hồ sơ.

Mỗi **bước** là một loại provider (cả pool: xếp theo `priority`, cùng mức thì xáo có trọng số theo `weight`) hoặc một `slot_id` cụ thể. Mỗi request thử mỗi slot **tối đa một lần**; chỉ được chuyển slot **trước** token đầu tiên.

### Điều khiển toàn cục (`GlobalControls`)

`ai_enabled` (công tắc tổng), bật/tắt theo loại provider, trần request/token toàn cục mỗi ngày, trần request/token mỗi người dùng mỗi ngày, trần chi phí ngày (tuỳ chọn), `max_output_tokens`, `max_context_tokens`, ánh xạ chế độ → hồ sơ, `web_search_profile`, `web_search_tool`, `version` (khoá lạc quan).

## 3. Thứ tự kiểm một lượt chat

1. `admission()` (trước khi stream): công tắc tổng → 503 `ai_not_enabled`; trần toàn cục/chi phí → 429 `ai_budget_exhausted`; trần theo người dùng → 429 `ai_budget_exhausted`. **Không đọc được bộ đếm** (kho sập, hôm nay chưa có số nào trong bộ nhớ) → 503 `ai_storage_unavailable`: số không biết không bao giờ được coi là 0. Ngân sách token theo tier cũ vẫn áp dụng.
2. `plan()`: dựng danh sách slot theo hồ sơ, mỗi slot kèm lý do bỏ qua hoặc "đủ điều kiện": `slot_disabled`, `type_disabled`, `workload_not_allowed`, `missing_secret`, `cooldown`, `request_cap`, `token_cap`, `rpm_soft_cap`, `tpm_soft_cap`.
3. `ControlledGateway.stream()`: thử lần lượt. 429 → cooldown theo `Retry-After` (1–600 s, mặc định 30 s); lỗi khác → circuit breaker theo slot. Không còn slot nào → sự kiện lỗi thân thiện (`ai_budget_exhausted` nếu do trần, `ai_no_provider` nếu không có gì bật/cấu hình).
4. Kết thúc lượt: cộng usage/chi phí cho **đúng slot đã phục vụ** (`ai_provider_usage_daily`), cùng lúc với ledger theo người dùng như trước.

## 4. Schema (bổ sung thuần — CHƯA áp lên production)

| Collection | Khoá | Nội dung |
|---|---|---|
| `ai_control_settings` | `global` | Điều khiển toàn cục |
| `ai_provider_slots` | `slot_id` | Slot (không có khoá) |
| `ai_routing_profiles` | tên hồ sơ | `steps_json`, `enabled` |
| `ai_provider_usage_daily` | `{slot_id}_{yyyymmdd}` | requests, tokens, errors, 429, chi phí micro-USD, lần thành công cuối |
| `ai_admin_audit` | ngẫu nhiên | admin_id, at, entity, field, old_value, new_value |

Tất cả `permissions=[]`, `documentSecurity=true` (chỉ backend đọc/ghi). Kế hoạch offline: `python scripts/setup_appwrite.py --dry-run --only=<collection>`. PLAN chỉ đọc trên production: Owner chạy script plan có rào chặn mọi phương thức khác GET, rồi mới apply khi đã duyệt.

## 5. API

| Phương thức | Đường | Quyền |
|---|---|---|
| GET | `/api/admin/ai/overview` | ADMIN, OWNER |
| GET | `/api/admin/ai/config` | ADMIN, OWNER |
| GET | `/api/admin/ai/audit?limit=` | ADMIN, OWNER |
| PUT | `/api/admin/ai/global` (+ `expected_version`) | OWNER |
| PUT | `/api/admin/ai/provider-types/{type}` | OWNER |
| POST | `/api/admin/ai/slots` | OWNER |
| PUT / DELETE | `/api/admin/ai/slots/{slot_id}` | OWNER |
| POST | `/api/admin/ai/slots/{slot_id}/reset-cooldown` | OWNER |
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
- Bộ đếm dùng đọc-sửa-ghi như `ai_usage_daily` — có thể lệch nhỏ khi hai lượt ghi cùng lúc.
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
6. Chỉ sau đó mới bật `FAS_AI_ASSISTANT_V1` và công tắc tổng.
