# Alibaba Model Studio trong control plane AI

> Trạng thái: **đã tích hợp, NGỦ ĐÔNG**. Không có request nào tới Alibaba cho tới khi Owner bật tường minh (mục 2). Gemini,
> hạn mức công khai, hồ sơ định tuyến mặc định: **không đổi**. Mốc hiện tại: `ALIBABA_PROVIDER_INTEGRATION_READY_FOR_CANARY`
> (mục 12 liệt kê thông tin Owner cần cung cấp để canary). Adapter mới chỉ được chạy qua `httpx.MockTransport` — chưa từng gọi
> Alibaba thật; những gì cần xác nhận ở canary nằm ở mục 11.

## 1. Cắm vào đâu (không có hệ thống AI song song)

| Việc | Ở đâu |
|---|---|
| Adapter HTTP (streaming, timeout, phân loại lỗi) | `server/llm_gateway/alibaba.py` — lớp con của `OpenAICompatChatProvider`; lớp gốc mà Gemini dùng **không bị sửa** |
| Loại provider `alibaba`, slot, kiểm hợp lệ, tầng năng lực, trường hạn mức | `server/ai_assistant/control/model.py` |
| Hàm thuần: tầng, trạng thái hạn mức miễn phí, thứ tự "ưu tiên sắp hết hạn" | `server/ai_assistant/control/capability.py` |
| Lưu trữ (`meta_json` tuỳ chọn, lỗi schema rõ ràng) | `server/ai_assistant/control/store.py` |
| Cổng, bỏ qua slot, probe qua stream, độ trễ, hạn mức nhà cung cấp, audit | `server/ai_assistant/control/service.py` |
| Định tuyến, TTFT, đường "hết hạn mức" | `server/ai_assistant/control/router.py` |
| Dựng provider theo slot | `server/ai_assistant/control/providers.py` |
| Giao diện | `/admin/ai` (`web/src/components/admin/ai/*`, `web/src/lib/admin/aiSlotView.ts`) |

Slot Alibaba đi qua đúng đường của slot Gemini: `plan()` → từng slot tối đa một lần → breaker/cooldown → sổ sử dụng theo slot →
trần toàn cục → audit. Tên provider của adapter là **id của slot**, nên cooldown/đếm/nhật ký là theo slot.

## 2. "Không request nào nếu chưa bật tường minh" — các lớp, tất cả phải mở

| # | Lớp | Mặc định | Đổi bằng | Ai đổi được |
|---|---|---|---|---|
| 1 | **Cổng máy chủ** `FAS_AI_ALIBABA_ENABLED` | ĐÓNG (chỉ `1/true/yes/on` mới mở; gõ sai = đóng, không bao giờ làm sập khởi động) | biến môi trường Render + khởi động lại | chủ máy chủ (không phiên `/admin/ai` nào làm được) |
| 2 | Công tắc tổng AI (kill switch) | theo cấu hình hiện hành | `/admin/ai` | Owner |
| 3 | Cờ loại provider `alibaba` | TẮT (khoá thiếu = tắt, kể cả cấu hình do bản cũ ghi) | `/admin/ai` | Owner |
| 4 | Cờ của slot (`enabled`) | slot Alibaba **luôn được tạo ở trạng thái tắt**; bật là thao tác riêng | `/admin/ai` | Owner |
| 5 | Hồ sơ định tuyến có bước `alibaba` hoặc id slot | **không hồ sơ mặc định nào** có | `/admin/ai` | Owner |
| 6 | Khoá `FAS_AI_SECRET_ALIBABA_*` có trong môi trường | không có | biến môi trường | chủ máy chủ |

* Cổng 1 được kiểm ở **ba chỗ**: `skip_reason` (slot không được chọn), `provider_for` (không dựng được provider) và `probe` (nút
  Kiểm tra trả 409, không gửi gì, không tính lượt kiểm). Có test cho từng chỗ.
* Loại `qwen` **cũ** (cũng là DashScope của Alibaba) dùng **chung cổng**. Lý do: `qwen` nằm trong các hồ sơ mặc định
  (`SUPPORT_SAFE = azure > qwen > gemini`, `FREE_FIRST` có `qwen` sau `gemini`, `WRITER`/`QUALITY_FIRST` có `qwen` đứng đầu) — bật
  một slot `qwen` sẽ lập tức đưa Alibaba vào lưu lượng thật, kể cả làm Alibaba đứng TRƯỚC Gemini ở chế độ Hỗ trợ. Cổng chung chặn
  đường đó. Production không có slot `qwen` nào nên việc này không đổi hành vi hiện tại. **Khuyến nghị tách riêng:** bỏ `qwen` khỏi
  `DEFAULT_PROFILE_STEPS` là một quyết định định tuyến — không làm trong đợt này.
* Không có đường fallback Gemini → Alibaba: `alibaba` không nằm trong bất kỳ hồ sơ mặc định nào; test khẳng định cả bốn chế độ
  chat không bao giờ gọi slot Alibaba khi hồ sơ là mặc định, và khi cổng đóng thì Alibaba không được gọi dù Gemini lỗi.
* Kill switch vẫn áp dụng: công tắc tổng tắt → `plan()` rỗng → không provider nào được gọi.

## 3. Adapter (`AlibabaModelStudioProvider`)

* **Điểm cuối**: không có mặc định (vùng/endpoint là của tài khoản Owner). `endpoint` bắt buộc, `https`, cổng 443, không
  user/query/fragment, **máy chủ chỉ dạng `[nhãn.]dashscope[-x].aliyuncs.com`** (không phải mọi dịch vụ `*.aliyuncs.com` — tên
  nhiều dịch vụ khác do khách hàng tự chọn nên không thể nhận khoá). Kiểm ở API (`validate_slot`) **và** trong constructor của
  adapter (phòng thủ chiều sâu). Không theo chuyển hướng (`follow_redirects=False`).
* **Khoá** chỉ nằm trong header `Authorization` của client httpx; `repr`, lỗi, log không bao giờ chứa nó (có test).
* **Streaming** theo định dạng OpenAI tương thích (`stream_options.include_usage`), không gửi trường `user` (không gửi mã người
  dùng, kể cả đã băm, ra nhà cung cấp mới). `reasoning_content` của model suy luận **không bao giờ** hiển thị hay chuyển tiếp.
* **Model** luôn lấy từ slot; không có tên model nào trong mã.
* **Hết hạn thời gian**: kết nối 10 s; chờ giữa hai gói tin 20 s; **chờ token chữ đầu (TTFT) 30 s**; tổng 120 s. Quá hạn →
  `provider_timeout` (trước token đầu: chuyển slot; sau token đầu: báo "bị gián đoạn", giữ phần đã nhận).
* **Dừng/huỷ**: đóng generator = đóng kết nối. Cận trên của độ trễ huỷ khi nhà cung cấp im lặng là timeout giữa hai gói tin (20 s).
* **Luồng cụt** (kết thúc không có `[DONE]` và không có `finish_reason`) = `provider_truncated`, không phải thành công.
* `generate()` stream bên trong (một số model từ chối gọi không-stream); probe của Owner đi **cùng đường stream** để đo TTFT.

## 4. Phân loại lỗi (đã làm sạch — không bao giờ lộ văn bản của nhà cung cấp)

Mã (`code`) theo quy ước cũ `provider_http_<status>` / `provider_timeout` / `provider_network_error` / `provider_truncated` /
`provider_stream_error` / `provider_empty`. Phân loại (`category`) thuộc **tập đóng** `AUTH_FAILED, PERMISSION_DENIED,
QUOTA_EXHAUSTED, RATE_LIMITED, MODEL_NOT_FOUND, CONTENT_FILTERED, CONTEXT_TOO_LONG, BAD_REQUEST, SERVER_ERROR, UNAVAILABLE, TIMEOUT,
NETWORK_ERROR, BAD_RESPONSE, EMPTY_RESPONSE`. Mã/loại/thông điệp của nhà cung cấp chỉ được đọc trong bộ nhớ để chọn phân loại rồi bỏ.

| Tình huống | Phân loại | Control plane làm gì |
|---|---|---|
| 401 / mã khoá sai | `AUTH_FAILED` | chuyển slot; breaker đếm lỗi; `last_error_*` hiện ở `/admin/ai` |
| 403 | `PERMISSION_DENIED` | như trên |
| 403/400/429 có dấu hiệu hết hạn mức miễn phí / nợ / hết hạn mức phân bổ | `QUOTA_EXHAUSTED` | **slot nghỉ tới 00:00 UTC** (không retry mỗi 30 s, không tính là lỗi sức khoẻ, không cooldown); Owner có thể "Reset cooldown" |
| 429 thường | `RATE_LIMITED` | cooldown theo `Retry-After` (kẹp 1–600 s; thiếu → 30 s), tính `rate_limited` |
| 404 / model không tồn tại | `MODEL_NOT_FOUND` | chuyển slot |
| 400 kiểm duyệt nội dung | `CONTENT_FILTERED` | chuyển slot |
| 400/413 quá dài | `CONTEXT_TOO_LONG` | chuyển slot |
| 408/504, quá hạn thời gian | `TIMEOUT` | chuyển slot |
| 503 / 500 / 502 | `UNAVAILABLE` / `SERVER_ERROR` | chuyển slot, breaker |
| lỗi mạng | `NETWORK_ERROR` | chuyển slot (chỉ tên lớp ngoại lệ, không URL/header) |

Chuỗi mã của Alibaba (ví dụ tên `Throttling.*`, `AllocationQuota.*`) được so khớp **khoan dung theo từ khoá** sau HTTP status vì chưa
xác nhận được với tài khoản thật — canary phải xác nhận (mục 11).

**Chính sách đếm** (chung mọi provider, ghi ở `AI_OPERATIONS_RUNBOOK.md` §2): lỗi nhà cung cấp trước token đầu không tính vào
`requests`/lượt người dùng, chỉ vào `errors` (hoặc `rate_limited`) của slot; lượt trả lời rỗng thành công vẫn tính vào slot.

## 5. Sử dụng, token, độ trễ

* Token: từ khung `usage` cuối luồng (`include_usage`); nhà cung cấp không báo thì route dùng ước lượng như mọi provider. Sổ
  `ai_provider_usage_daily` (requests, tokens, errors, rate_limited, cost) **không đổi schema**.
* **Độ trễ/TTFT**: `ControlledGateway` đo mỗi lời gọi (mọi provider như nhau): TTFT = tới token chữ đầu; tổng = hết luồng. Cửa sổ
  trượt 200 lời gọi gần nhất mỗi slot, **trong tiến trình** (mất khi deploy, như breaker) → không cần thuộc tính Appwrite. Hiển
  thị p50/p95/gần nhất ở `/admin/ai`. Lần Kiểm tra cũng ghi vào cửa sổ (đánh dấu `probe`).

## 6. Tầng năng lực (không gắn gói với tên model)

`FAST`, `SMART`, `ADVANCED`, `TRANSLATION`, `VISION`, `EMBEDDING` (`model.CAPABILITY_TIERS`). Một slot khai báo `tiers` (Owner chọn);
`tiers` rỗng = chưa phân loại (slot cũ). Router: `plan(..., tier=None)` — **không route chat nào truyền tier hôm nay**, nên hành
vi hiện tại không đổi. Khi có tier: chỉ slot khai báo tier đó được chọn (`tier_not_served` cho slot khác); `EMBEDDING` không phục
vụ được bằng đường chat (slot chỉ-EMBEDDING không bao giờ nhận lượt chat; yêu cầu tier EMBEDDING cho chat ra kế hoạch rỗng).
Gói đăng ký/tính năng về sau **ánh xạ tới tầng**, rồi tầng → slot do Owner cấu hình; không đặt tên model vào gói.
`/admin/ai` có bản đồ tầng → slot (`capability_map`).

## 7. Hạn mức miễn phí & hạn dùng

Trường tuỳ chọn của slot (lưu trong `meta_json`): `free_quota_remaining` (token), `free_quota_expires_at` (ISO-8601 có múi giờ,
chuẩn hoá UTC), `free_quota_only`, và `free_quota_updated_at` (do **máy chủ** đóng dấu khi số dư đổi).

* Đây là **ảnh chụp do Owner nhập** từ trang Model Studio, không tự cập nhật (Alibaba không đưa số dư vào API chat). Giao diện luôn
  ghi rõ tuổi của ảnh chụp.
* Trạng thái: `none | active | expiring (≤ 7 ngày) | expired | exhausted`, hiển thị kèm số ngày còn lại.
* `free_quota_only` là **khoá an toàn chống phát sinh phí**: slot bị bỏ qua khi quá hạn, hết số dư, hoặc số dư nhỏ hơn ước lượng
  của yêu cầu (`free_quota_expired` / `free_quota_exhausted`). Bật khoá bắt buộc nhập số dư (không biết số dư = không được dùng). Slot
  không bật khoá chỉ hiển thị thông tin.
* **Ưu tiên hạn mức sắp hết hạn** (`capability.order_by_expiring_free_quota`): trong cùng bậc ưu tiên, slot có hạn mức còn dùng được
  và hết hạn SỚM nhất đứng trước. Đã cài + có test, **NGỦ ĐÔNG**: chỉ chạy khi `FAS_AI_PREFER_FREE_QUOTA=1` (mặc định tắt, không đặt ở
  production). Hiện `/admin/ai` báo trạng thái bật/tắt.

## 8. Kiểm tra (probe)

`POST /api/admin/ai/slots/{id}/probe` (Owner): một request tối thiểu qua đường **stream**, trả `ok`, `latency_ms`, `ttft_ms`, mã/phân loại
đã làm sạch — không bao giờ văn bản nhà cung cấp. Chạy được khi slot tắt/công tắc tổng tắt **nhưng cần cổng máy chủ mở**. Không ghi sổ
sử dụng; có ngân sách riêng (30/slot/ngày, ≥20 s giữa hai lần); ghi audit `slot:<id>.probe` kèm id Owner. Quy trình "ổn định" (3 lần đạt ≤ 5 s)
như slot Gemini.

## 9. Audit & quyền

Mọi thay đổi (tạo/sửa slot gồm tầng và hạn mức, bật loại, bật slot, reset, probe) đi qua `ai_admin_audit` kèm id Owner; giá trị cũ/mới không
chứa bí mật (chỉ tên tham chiếu). Chỉ Owner ghi; Admin chỉ đọc. Lệnh bị kho từ chối vì schema thiếu thuộc tính trả 409
`ai_admin_schema_outdated` (không phải 503 mơ hồ).

## 10. Không lộ thông tin cho client thường

`availability`, SSE, danh sách/chi tiết hội thoại, `access` không chứa tên nhà cung cấp, model, id slot hay văn bản lỗi của nhà cung
cấp (test E2E với một lượt thật do slot Alibaba phục vụ, và 3 kiểu lỗi nhà cung cấp mang chuỗi dò). Lỗi nhà cung cấp trước token đầu là
miễn phí cho người dùng.

## 11. Migration schema Appwrite (CHƯA chạy; Owner/phiên có duyệt chạy ở giai đoạn canary)

Schema production hiện có `provider_type` là **enum 6 giá trị** và không có `meta_json`. Mã mới **tương thích ngược**: ghi một slot Gemini
gửi đúng bộ thuộc tính cũ (test khoá từng byte), nên deploy mã này **không cần** migration. Chỉ khi tạo slot Alibaba (giá trị enum mới) hoặc đặt
tầng/hạn mức cho một slot (thuộc tính `meta_json`) mới cần:

```
.venv\Scripts\python.exe -m scripts.setup_appwrite --plan --only ai_provider_slots     # CHỈ ĐỌC: cho biết thiếu gì
.venv\Scripts\python.exe -m scripts.setup_appwrite --only ai_provider_slots            # mở rộng enum (+alibaba) và thêm meta_json; idempotent
```

(dùng khoá schema `APPWRITE_SCHEMA_API_KEY` của Owner; xem chú thích trong script). Trước migration, thử tạo slot Alibaba sẽ nhận 409
`ai_admin_schema_outdated` với hướng dẫn, và **không ảnh hưởng** việc ghi/tắt các slot khác.

**Ràng buộc rút lui (quan trọng):** `meta_json` thì mã cũ bỏ qua an toàn; nhưng mã cũ **không biết loại `alibaba`** — gặp một dòng slot
`alibaba` trong kho nó coi CẢ cấu hình là hỏng và AI tắt cho mọi người (fail-closed, kể cả Gemini). Vì vậy **trước khi rút mã về bản cũ phải
xoá mọi slot `alibaba`** (và khoá cờ loại). Khoá `provider_types_json` có thêm `alibaba` thì mã cũ bỏ qua an toàn.

## 12. Điều kiện canary — thông tin Owner phải cung cấp (không đoán)

1. **Endpoint/vùng** của tài khoản Model Studio (máy chủ DashScope và đường dẫn tương thích OpenAI mà tài khoản dùng). Không có mặc định.
2. **Khoá API**: đặt vào môi trường Render dưới tên `FAS_AI_SECRET_ALIBABA_<TÊN>` (slot chỉ lưu `ALIBABA_<TÊN>`); Owner đặt, không gửi cho tôi.
   Phải nêu khoá thuộc tài khoản/vùng nào và có bật chế độ "chỉ dùng hạn mức miễn phí" của Alibaba hay không.
3. **Danh mục model và hạn mức thật**: id model chính xác Owner muốn dùng (mỗi model một slot), tầng nào (FAST/SMART/…), số dư hạn mức miễn phí và ngày
   hết hạn của từng model, giới hạn tốc độ (RPM/TPM) trên trang Alibaba, và có model nào là model "suy luận" (có `reasoning_content`) không.
4. Duyệt chạy migration (mục 11) và đặt `FAS_AI_ALIBABA_ENABLED=1`.

**Việc canary phải xác nhận trên tài khoản thật** (adapter chưa từng gọi Alibaba thật): (a) đường dẫn và `stream_options.include_usage` cho ra khung
`usage`; (b) chuỗi mã lỗi thật cho lỗi khoá, hết hạn mức miễn phí, giới hạn tốc độ (đối chiếu phân loại ở mục 4 bằng `last_error_category`);
(c) TTFT/độ trễ thật; (d) hành vi model suy luận; (e) `Retry-After` có được gửi không. Các lần probe không tốn lượt người dùng và không vào trần 150.

## 13. Rút lui

Nhanh nhất: `FAS_AI_ALIBABA_ENABLED` về 0 + khởi động lại (hoặc công tắc tổng ở `/admin/ai`); tắt cờ loại `alibaba`; tắt/xoá slot. Không thay đổi hạn
mức công khai, hồ sơ mặc định hay slot Gemini ở bất kỳ bước nào. Rút **mã** về bản trước khi có Alibaba: xoá slot `alibaba` trước (mục 11).
