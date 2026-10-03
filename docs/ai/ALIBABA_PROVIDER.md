# Alibaba Model Studio trong control plane AI

> Trạng thái: **đã tích hợp, NGỦ ĐÔNG**. Không có request nào tới Alibaba cho tới khi Owner bật tường minh (mục 2). Gemini,
> hạn mức công khai: **không đổi**; hồ sơ định tuyến mặc định chỉ đổi ở chỗ loại `qwen` cũ nghỉ hưu (mục 2b, không đổi gì với Gemini). Cổng Alibaba
> và cổng `qwen` cũ độc lập nhau. Dữ liệu Alibaba ở collection riêng nên rút mã về bản cũ không làm hỏng Gemini (mục 11). Mốc hiện tại: `ALIBABA_PROVIDER_INTEGRATION_READY_FOR_CANARY`
> (mục 12 liệt kê thông tin Owner cần cung cấp để canary). Adapter mới chỉ được chạy qua `httpx.MockTransport` — chưa từng gọi
> Alibaba thật; những gì cần xác nhận ở canary nằm ở mục 11.

## 1. Cắm vào đâu (không có hệ thống AI song song)

| Việc | Ở đâu |
|---|---|
| Adapter HTTP (streaming, timeout, phân loại lỗi) | `server/llm_gateway/alibaba.py` — lớp con của `OpenAICompatChatProvider`; lớp gốc mà Gemini dùng **không bị sửa** |
| Loại provider `alibaba`, slot, kiểm hợp lệ, tầng năng lực, trường hạn mức | `server/ai_assistant/control/model.py` |
| Hàm thuần: tầng, trạng thái hạn mức miễn phí, thứ tự "ưu tiên sắp hết hạn" | `server/ai_assistant/control/capability.py` |
| Lưu trữ: slot + bước định tuyến Alibaba ở **collection riêng** `ai_alibaba_config` (vùng tách biệt, mục 11); `meta_json` tuỳ chọn cho slot loại cũ | `server/ai_assistant/control/store.py` |
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
* **`FAS_AI_ALIBABA_ENABLED=1` KHÔNG đánh thức loại `qwen` cũ.** Hai đường tới Alibaba là hai cổng độc lập (mục 2b): bật cái này không
  mở cái kia, và ngược lại. Một lần canary Model Studio không được vô tình đưa đường DashScope cũ vào lưu lượng thật.
* Không có đường fallback Gemini → Alibaba: `alibaba` không nằm trong bất kỳ hồ sơ mặc định nào; test khẳng định cả bốn chế độ
  chat không bao giờ gọi slot Alibaba khi hồ sơ là mặc định, và khi cổng đóng thì Alibaba không được gọi dù Gemini lỗi.
* Kill switch vẫn áp dụng: công tắc tổng tắt → `plan()` rỗng → không provider nào được gọi.

### 2b. Loại `qwen` cũ — đã nghỉ hưu, có cổng riêng và đường quay về

`qwen` (DashScope, có từ trước Model Studio) từng nằm trong các hồ sơ mặc định (`SUPPORT_SAFE = azure > qwen > gemini`, `FREE_FIRST` có
`qwen` sau `gemini`, `WRITER`/`QUALITY_FIRST` có `qwen` đứng đầu). Đợt này tách nó ra:

| Hạng mục | Trước | Sau |
|---|---|---|
| Cổng máy chủ của `qwen` | không có (ở bản #270 chưa deploy: dùng chung `FAS_AI_ALIBABA_ENABLED`) | **`FAS_AI_QWEN_LEGACY_ENABLED`**, mặc định ĐÓNG, độc lập với cổng Alibaba |
| Hồ sơ mặc định | có `qwen` ở cả 6 hồ sơ | **không còn `qwen`** (bảng cũ giữ ở `LEGACY_QWEN_PROFILE_STEPS`) |
| Chuỗi env cũ `FAS_AI_PROVIDERS=qwen` (khi control plane tắt) | không cổng | cùng cổng riêng `FAS_AI_QWEN_LEGACY_ENABLED` |
| Slot/hồ sơ `qwen` đã lưu từ trước | hợp lệ | **vẫn hợp lệ** (loại còn trong `PROVIDER_TYPES`) — chỉ không nhận request khi cổng đóng |
| Định tuyến Gemini | — | không đổi (test so từng chế độ; production không có slot `qwen`) |

**Đường quay về (an toàn, tường minh, không bao giờ tự động):** (1) đặt `FAS_AI_QWEN_LEGACY_ENABLED=1` + khởi động lại; (2) Owner đặt lại bước
`qwen` cho từng hồ sơ qua `/admin/ai` (hợp lệ vì `qwen` vẫn là loại hợp lệ) — thứ tự cũ chính xác nằm ở `LEGACY_QWEN_PROFILE_STEPS` và được test
đối chiếu từng bước với bản production trước đợt này. Thiếu một trong hai thì `qwen` không nhận request nào.

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
  `provider_timeout` (trước token đầu: chuyển slot; sau token đầu: báo "bị gián đoạn", giữ phần đã nhận). Hạn TTFT chỉ tính token **chữ**:
  model suy luận chỉ phát `reasoning_content` quá 30 s sẽ bị cắt — nếu canary cần model như vậy, cần một hạn TTFT riêng theo slot (chưa có).
  Hạn TTFT/tổng được kiểm mỗi khi có dòng SSE mới; im lặng hoàn toàn thì hạn "giữa hai gói tin" (20 s) cắt trước.
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

Hai nguyên tắc chống bị lạm dụng (có test):

* **Thông điệp của lỗi 400 có thể lặp nguyên văn nội dung người dùng** nên KHÔNG BAO GIỜ dùng nó để quyết định điều đổi trạng thái slot
  (khoá sai, hết hạn mức, model không tồn tại, giới hạn tốc độ): các quyết định đó chỉ dựa vào **mã/loại** do nhà cung cấp gửi. Nhờ vậy một
  người dùng gõ "free tier" hay "unauthorized" vào tin nhắn không làm slot bị nghỉ cả ngày hay bị coi là hỏng khoá.
* **Lỗi do chính yêu cầu** (`CONTENT_FILTERED`, `CONTEXT_TOO_LONG`, `BAD_REQUEST`) không phải lỗi sức khoẻ của slot: vẫn chuyển slot và vẫn
  ghi vào `errors`, nhưng **không** đếm vào breaker. Nếu không, ai cũng làm được cả pool nghỉ 60 s bằng vài yêu cầu bị nhà cung cấp từ chối.

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

Trường tuỳ chọn của slot (slot Alibaba: nằm trong payload của dòng `ai_alibaba_config`; slot loại cũ: `meta_json`): `free_quota_remaining` (token), `free_quota_expires_at` (ISO-8601 có múi giờ,
chuẩn hoá UTC), `free_quota_only`, và `free_quota_updated_at` (do **máy chủ** đóng dấu khi số dư đổi).

* Đây là **ảnh chụp do Owner nhập** từ trang Model Studio, không tự cập nhật (Alibaba không đưa số dư vào API chat). Giao diện luôn
  ghi rõ tuổi của ảnh chụp.
* Trạng thái: `none | active | expiring (≤ 7 ngày) | expired | exhausted`, hiển thị kèm số ngày còn lại.
* `free_quota_only` là **khoá an toàn phía chúng ta để hạn chế phát sinh phí** (không phải rào duy nhất — xem dưới). Số dư thực tế
  được ƯỚC TÍNH = ảnh chụp − token slot đã phục vụ từ **ngày UTC của ảnh chụp** (cả ngày đó, phía thận trọng; đọc từ sổ sử dụng theo
  ngày, mỗi ngày đã đóng chỉ đọc một lần) − **dự phòng 5%** của ảnh chụp. Slot bị bỏ qua khi:
  * quá hạn dùng (`free_quota_expired`);
  * ước tính còn lại (sau dự phòng) nhỏ hơn ước lượng của yêu cầu (`free_quota_exhausted`);
  * ảnh chụp **quá cũ** (> 31 ngày) hoặc thiếu dấu thời gian của máy chủ, hoặc **không đọc được** lượng đã dùng (`free_quota_stale`) —
    không xác minh được thì không dùng.
  Bật khoá bắt buộc nhập số dư. Slot không bật khoá chỉ hiển thị thông tin. `/admin/ai` hiện số ước tính, lượng đã trừ, tuổi ảnh chụp
  và **lý do khoá đang chặn**.
* **Giới hạn thật của khoá này (đừng hiểu nhầm):** token do ta đếm có thể lệch với cách nhà cung cấp tính tiền; lần Kiểm tra (probe) không
  vào sổ; và **tài khoản Alibaba có thể có nơi tiêu hạn mức khác** (ứng dụng khác, console) mà ta không thấy. Vì vậy rào chặn thật sự chống
  phát sinh phí là chế độ **"chỉ dùng hạn mức miễn phí" (free tier only) bật ở console Alibaba** (khi hết, nhà cung cấp tự từ chối — ta
  phân loại thành `QUOTA_EXHAUSTED` và cho slot nghỉ tới 00:00 UTC). **Điều kiện canary: Owner phải xác nhận đã bật chế độ này cho từng model
  trước khi bật `FAS_AI_ALIBABA_ENABLED`.**
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

## 11. Lưu trữ tách biệt + migration Appwrite (CHƯA chạy; Owner/phiên có duyệt chạy ở giai đoạn canary)

### Vì sao slot Alibaba nằm ở collection RIÊNG

Mã **cũ** (production hiện tại và mọi bản trước) đọc `ai_provider_slots` và `ai_routing_profiles`, kiểm từng dòng, và coi **bất kỳ dòng nào nó
không hiểu** là "cấu hình hỏng" → AI tắt cho mọi người (fail-closed, kể cả Gemini). Một dòng `provider_type = alibaba`, hoặc một bước `alibaba` trong
`steps_json`, sẽ biến việc **rút mã về bản cũ** thành sự cố toàn cục — và không bản vá nào ở mã mới cứu được, vì mã cũ là thứ chạy. Cách duy nhất
là **không để mã cũ thấy chúng**:

| Dữ liệu | Nơi lưu | Mã cũ thấy gì |
|---|---|---|
| Slot Alibaba (kể cả tầng, hạn mức miễn phí) | `ai_alibaba_config`, dòng `s-<slot_id>` | không đọc collection này |
| Bước Alibaba của hồ sơ định tuyến | `ai_alibaba_config`, dòng `r-<hồ sơ>` = danh sách bước ĐẦY ĐỦ | `ai_routing_profiles.steps_json` chỉ mang **phần bản cũ đọc được** (bỏ `alibaba` và id slot Alibaba) |
| Cờ loại `alibaba` | khoá thêm trong `provider_types_json` | bỏ qua khoá lạ (mã cũ chỉ đọc 6 khoá của nó) |
| Sử dụng/audit | collection chung (chỉ số đếm / chuỗi) | không kiểm tra |

* **Hồ sơ hiệu lực** = phần bản cũ đọc được + dòng `r-…`, và dòng `r-…` **chỉ được áp khi đồng thời**: (1) mang đúng **dấu** của dòng hồ sơ cũ — dấu
  chính là `updated_at` của dòng `ai_routing_profiles` (cột đã có sẵn ở production, bản cũ cũng ghi nó mỗi lần lưu), được ghi vào CẢ HAI dòng trong
  cùng một lần lưu và luôn tăng nghiêm ngặt; (2) bỏ bước Alibaba phải ra đúng `steps_json`; (3) mọi bước hợp lệ, không lặp, vừa trần. Mọi lần ghi dòng hồ sơ
  cũ về sau — bản cũ sau khi rút mã, hay bản mới sửa hồ sơ lúc vùng này không với tới/không xoá được dòng — đổi dấu và làm dòng Alibaba **mồ côi vĩnh
  viễn, kể cả khi các bước tình cờ trùng lại** (không "sống lại"). Dòng bị bỏ **không bao giờ ghi đè thay đổi về Gemini**, và `/admin/ai` báo "hồ sơ …
  có bước Alibaba bị bỏ". Nghĩa là lệnh "gỡ bước Alibaba" của Owner không thể bị lờ đi chỉ vì lần xoá dòng route thất bại.
* **Giới hạn đã biết (đều thất bại theo hướng an toàn — Gemini không bao giờ bị ảnh hưởng):** (a) bản cũ hay bản mới lưu lại một hồ sơ sẽ làm bước Alibaba của
  hồ sơ đó mất hiệu lực cho tới khi Owner đặt lại ở `/admin/ai` — `/admin/ai` báo rõ; (b) hai instance cùng sửa MỘT hồ sơ trong cùng khoảnh khắc (Appwrite
  không có ghi có điều kiện; `_serialized` chỉ khoá trong một tiến trình) có thể làm bước Alibaba của hồ sơ đó mất hiệu lực — cũng báo rõ, đặt lại là xong.
  Mốc thời gian hỏng/tràn số (vd. `0001-01-01T00:00:00+05:00`) chỉ làm dòng đó "không hợp lệ", không bao giờ ném lỗi vào lúc nạp cấu hình.
* Lúc ghi hồ sơ có bước Alibaba, phần Alibaba ghi **trước**: nếu collection chưa có/không với tới thì lỗi sạch (409), chưa đổi gì; nếu ghi dòng hồ sơ cũ thất
  bại SAU đó thì dòng Alibaba cũ được trả lại (cố gắng hết sức — nếu cũng thất bại thì dòng mới không có dấu khớp nên không được áp). Hồ sơ có bước
  Alibaba **phải còn ít nhất một bước loại khác** — Alibaba không bao giờ là đường duy nhất của một chế độ.
* Một chuỗi bước được giải **giống hệt `router.plan`**: tên LOẠI thắng id slot. Vì vậy id slot **không được trùng tên một loại provider** (`gemini`, `qwen`,
  `groq`, `alibaba`…): tạo mới bị từ chối, dòng trong vùng này mang id như vậy bị coi là không đọc được. Mỗi dòng phải có `$id` đúng bằng `s-<id>` /
  `r-<hồ sơ>` suy từ `kind`/`key` — dòng "bóng" (id khác key) bị bỏ, nên xoá/tắt qua API luôn tác động vào dòng thật.
* Trần slot **riêng theo vùng** (`MAX_SLOTS` cho collection cũ, `MAX_EXT_SLOTS` = 20 cho Alibaba): slot Alibaba không chiếm chỗ của slot Gemini. Tạo slot Alibaba
  khi không đọc được vùng này bị từ chối (không kiểm được trùng id, tránh ghi đè mù). Một trang đọc đầy (≥ 100 dòng) không thể hợp lệ và được coi là
  suy giảm (`unavailable`) thay vì cắt bớt âm thầm.
* `AppwriteControlStore.save_slot` **từ chối** slot loại Alibaba, `save_profile` từ chối bước `alibaba` (lỗi lập trình, không ghi gì): không đường nào
  đưa chúng vào collection cũ. Nếu có (sửa tay) thì mã mới **bỏ qua + đếm** chứ không định tuyến, và không làm cấu hình hỏng.
* **Đọc vùng này không bao giờ làm hỏng cấu hình Gemini:** collection thiếu / kho không với tới / dòng hỏng / lỗi trình phân tích chỉ cho ra một
  *trạng thái* (`schema_missing`, `unavailable`, số dòng `unreadable`) hiện ở `/admin/ai`; Gemini vẫn được đọc và kiểm tra nghiêm ngặt như trước (một dòng
  Gemini hỏng vẫn fail-closed — không nới lỏng). Slot Alibaba đọc được nhưng không hợp lệ (vd. endpoint ngoài danh sách cho phép) bị **đỗ lại**: không
  định tuyến, không Kiểm tra, sửa hợp lệ ở `/admin/ai` là mở lại.

### Migration

Deploy mã này **không cần** migration (ghi slot Gemini gửi đúng bộ thuộc tính cũ — test khoá từng byte — và collection mới chỉ được chạm khi có slot/bước
Alibaba). Tạo slot Alibaba cần **một collection mới, thuần cộng thêm** (không đổi collection nào có sẵn, không đụng enum):

```
.venv\Scripts\python.exe -m scripts.setup_appwrite --plan --only ai_alibaba_config     # CHỈ ĐỌC: cho biết sẽ tạo gì
.venv\Scripts\python.exe -m scripts.setup_appwrite --only ai_alibaba_config            # tạo collection (4 thuộc tính + 1 index); idempotent
```

(dùng khoá schema `APPWRITE_SCHEMA_API_KEY` của Owner; xem chú thích trong script). Trước migration, thử tạo slot Alibaba nhận 409
`ai_admin_schema_outdated` kèm hướng dẫn, `/admin/ai` hiện "chưa chạy migration collection ai_alibaba_config", và **không ảnh hưởng** gì khác.
Thuộc tính tuỳ chọn `meta_json` của `ai_provider_slots` (`--only ai_provider_slots`) **chỉ cần** nếu Owner gán tầng/hạn mức cho một slot **Gemini**; slot
Alibaba không dùng nó. **Enum `provider_type` của collection cũ KHÔNG được mở rộng** (spec đã bỏ giá trị `alibaba`).

### Kiểm chứng rút lui bằng mã cũ thật

`server/tests/fixtures/legacy_release_3f86706/` giữ **nguyên văn** `model.py` + `store.py` của production hiện tại (commit 3f86706, chỉ đổi một dòng
import). `test_ai_alibaba_isolation.py` ghi cấu hình bằng mã mới — Gemini + slot Alibaba đã bật + hồ sơ có bước Alibaba — rồi nạp **chính các dòng đó**
bằng mã cũ và kiểm tra bằng validation cũ: hợp lệ, AI vẫn bật, đúng slot/hồ sơ Gemini. Có bài đối chứng cho thấy mã cũ **thật sự** từ chối một
dòng `alibaba` trong collection cũ (nên bảo đảm không rỗng). Các đột biến "ghi slot vào collection cũ" và "không tách bước hồ sơ" làm bài đó đỏ.

## 12. Điều kiện canary — thông tin Owner phải cung cấp (không đoán)

1. **Endpoint/vùng** của tài khoản Model Studio (máy chủ DashScope và đường dẫn tương thích OpenAI mà tài khoản dùng). Không có mặc định.
2. **Khoá API**: đặt vào môi trường Render dưới tên `FAS_AI_SECRET_ALIBABA_<TÊN>` (slot chỉ lưu `ALIBABA_<TÊN>`); Owner đặt, không gửi cho tôi.
   Phải nêu khoá thuộc tài khoản/vùng nào và có bật chế độ "chỉ dùng hạn mức miễn phí" của Alibaba hay không.
3. **Danh mục model và hạn mức thật**: id model chính xác Owner muốn dùng (mỗi model một slot), tầng nào (FAST/SMART/…), số dư hạn mức miễn phí và ngày
   hết hạn của từng model, giới hạn tốc độ (RPM/TPM) trên trang Alibaba, và có model nào là model "suy luận" (có `reasoning_content`) không.
4. Xác nhận đã bật chế độ **"chỉ dùng hạn mức miễn phí"** ở console Alibaba cho từng model sẽ dùng (rào chặn phí thật, mục 7).
5. Duyệt chạy migration **`--only ai_alibaba_config`** (mục 11) và đặt `FAS_AI_ALIBABA_ENABLED=1`. (Không cần đặt `FAS_AI_QWEN_LEGACY_ENABLED` — cổng đó là của
   đường `qwen` cũ và phải để ĐÓNG.)

**Việc canary phải xác nhận trên tài khoản thật** (adapter chưa từng gọi Alibaba thật): (a) đường dẫn và `stream_options.include_usage` cho ra khung
`usage`; (b) chuỗi mã lỗi thật cho lỗi khoá, hết hạn mức miễn phí, giới hạn tốc độ (đối chiếu phân loại ở mục 4 bằng `last_error_category`);
(c) TTFT/độ trễ thật; (d) hành vi model suy luận; (e) `Retry-After` có được gửi không. Các lần probe không tốn lượt người dùng và không vào trần 150.

## 13. Rút lui

Nhanh nhất: `FAS_AI_ALIBABA_ENABLED` về 0 + khởi động lại (hoặc công tắc tổng ở `/admin/ai`); tắt cờ loại `alibaba`; tắt/xoá slot. Không thay đổi hạn
mức công khai, hồ sơ mặc định hay slot Gemini ở bất kỳ bước nào.

Rút **mã** về bản trước khi có Alibaba (kể cả khi slot/hồ sơ Alibaba đã được lưu): **không cần dọn gì trước**. Dữ liệu Alibaba nằm ở collection mà
mã cũ không đọc, nên cấu hình Gemini vẫn hợp lệ và AI vẫn bật (có test với chính mã cũ, mục 11). Dữ liệu Alibaba còn nguyên để triển khai lại; hồ sơ
mà bản cũ đã sửa trong lúc đó thắng bước Alibaba cũ (bị bỏ, `/admin/ai` báo). Chỉ cần nhớ: bản cũ **không có** nút tắt Alibaba — nhưng cũng không có
đường nào gọi Alibaba (không biết loại này).
