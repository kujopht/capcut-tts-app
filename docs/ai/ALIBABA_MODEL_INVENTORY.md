# Kiểm kê model Alibaba Model Studio & định tuyến theo tầng năng lực

Trạng thái: **chuẩn bị dữ liệu, chưa định tuyến, chưa gọi Alibaba thật**. Slot `alibaba-sg-01` đang **ngủ đông** (tắt, cờ loại `alibaba`
tắt, cấu hình còn nguyên); không có lưu lượng công khai nào đi vào Alibaba; `FAS_AI_PREFER_FREE_QUOTA` chưa đặt; `qwen` cũ ĐÓNG.

Bối cảnh: canary Owner (2026-10-03, `docs/ai/ALIBABA_PROVIDER.md` mục 12c–12d) đã kiểm chứng đường chat với **một** model. Muốn dùng nhiều
model theo tầng (FAST/SMART/ADVANCED/TRANSLATION/VISION/EMBEDDING) và ưu tiên hạn mức miễn phí, trước hết cần **dữ liệu thật** về từng model —
**không đoán id model, không đoán hạn mức**. Tài liệu này mô tả nơi dữ liệu đó sống và cách biến nó thành slot.

## 1. Định dạng kiểm kê (`docs/ai/alibaba_model_inventory.json`)

Mã: `server/ai_assistant/control/alibaba_inventory.py` (thuần, ngoại tuyến) + `scripts/alibaba_inventory.py` (dòng lệnh). Không mạng, không
đọc/ghi production, không bí mật; không giữ endpoint/WorkspaceId (chỉ nhận lúc xuất payload slot).

| Trường (mỗi model) | Ý nghĩa | Chưa biết thì |
|---|---|---|
| `model_id` | id CHÍNH XÁC trên console (giữ nguyên hoa/thường, không điền hộ) | — (bắt buộc) |
| `console_category` | danh mục NGUYÊN VĂN trên console (ví dụ `语音模型`, `向量模型`) — là bằng chứng, **không** phải tầng | `""` |
| `status` | `inventoried` → `benchmarked` → `validated_candidate`; `rejected` | `inventoried` |
| `tiers` | một hay nhiều trong `FAST, SMART, ADVANCED, TRANSLATION, VISION, EMBEDDING` (Owner phân loại, không suy từ tên model) | `[]` (chưa phân loại) |
| `quota_unit` | `tokens` / `calls` / `characters` / `images` / `seconds`. **Bảng Free Quota chỉ có con số, không có đơn vị** nên chưa biết = `null` (KHÔNG mặc định là token). Đơn vị khác `tokens` **bị chặn khỏi định tuyến** (sổ hạn mức của ta đếm token) | `null` |
| `free_quota_total`, `free_quota_remaining` | tổng / còn lại (ảnh chụp, không tự cập nhật) | `null` |
| `free_quota_snapshot_at` | thời điểm Owner đọc số dư trên console | `""` |
| `free_quota_expires_at` | hạn dùng (ISO-8601 CÓ múi giờ, chuẩn hoá UTC) | `""` |
| `rpm`, `tpm` | giới hạn tốc độ của model | `null` |
| `thinking_support` / `thinking_default` | `none \| hybrid \| thinking_only` / `on \| off` | `null` |
| `slot_thinking` | chế độ ta cấu hình cho slot: **`provider_default` hoặc `off` — `on` bị CẤM** (mục 3) | `provider_default` |
| `input_modalities` | trong `text, image, audio, video` (đa phương thức = có thứ ngoài `text`) | `null` |
| `free_quota_only` | công tắc **Free Quota Only trên CONSOLE**: `confirmed_on \| not_enabled` | `null` |
| `observations[]` | số đo THẬT nếu đã benchmark: thời điểm, nguồn, `thinking`, số mẫu, TTFT/tổng (median, max), token ra (min, max) | `[]` |
| `source`, `notes`, `free_quota_only_note` | bằng chứng/ghi chú tự do (không bí mật) | `""` |

Quy tắc: **không đoán** (null là giá trị hợp lệ), lược đồ chặt (khoá lạ/kiểu sai/trùng id/tầng lạ/thời điểm không múi giờ bị từ chối và báo **mọi** lỗi
một lượt), `model_id` khớp chính xác.

### Mức sẵn sàng (`readiness`)

* `READY` — đủ `tiers, quota_unit (=tokens), free_quota_remaining, free_quota_snapshot_at, free_quota_expires_at, rpm, tpm, thinking_support (+thinking_default nếu có thinking), input_modalities, free_quota_only` và không bị chặn.
* `INCOMPLETE` — thiếu dữ liệu; `missing()` nói **đúng thiếu gì**.
* `BLOCKED` — đủ hay không cũng không dùng được: `rejected`, đơn vị khác token, hết hạn, hết số dư. BLOCKED thắng INCOMPLETE.

Chỉ model `READY` mới xuất được payload slot (`to_slot_dict`): luôn `enabled=false`, đi qua **chính `validate_slot`** của slot thật, `free_quota_only` ở app
chỉ bật khi console đã `confirmed_on` (không bao giờ bật hộ khi chưa có rào chặn phí thật), không bao giờ kèm `thinking=on`.

### Dòng lệnh

```
python scripts/alibaba_inventory.py validate docs/ai/alibaba_model_inventory.json
python scripts/alibaba_inventory.py report   docs/ai/alibaba_model_inventory.json   # mức sẵn sàng, phủ theo tầng, dữ liệu còn thiếu + lấy ở đâu
python scripts/alibaba_inventory.py report   docs/ai/alibaba_model_inventory.json --brief   # chỉ đếm theo mức sẵn sàng/danh mục + dữ liệu còn thiếu
python scripts/alibaba_inventory.py parse-console <văn bản dán từ bảng Free Quota> --into docs/ai/alibaba_model_inventory.json --out moi.json
python scripts/alibaba_inventory.py from-csv bang.csv --captured-at <ISO> --region ap-southeast-1 > kiem_ke.json
python scripts/alibaba_inventory.py slot docs/ai/alibaba_model_inventory.json <model_id> --slot-id alibaba-sg-02 --secret-ref ALIBABA_SG_02 --endpoint <endpoint workspace>
python scripts/alibaba_inventory.py template                                          # khung MỘT model (model_id để trống có chủ ý)
```

CSV (`docs/ai/alibaba_model_inventory.template.csv`): một dòng mỗi model, ô trống = chưa biết, danh sách ngăn bằng `|`, số theo kiểu console
(`1,000,000`, `992.19K`, `1M`). **Lưu ý**: console làm tròn (`992.19K` ≈ 992.190 token) — số dư là gần đúng tới hàng chục token. `observations` chỉ nhập bằng JSON.
Mã thoát: 0 ổn, 1 không hợp lệ, 2 model chưa READY (không in payload).

### Nhập thẳng từ bảng Free Quota của console (`parse-console`)

Dán nguyên văn bảng (4 dòng mỗi model: `<id>  <danh mục>` · `剩 X / 共 Y` · `<YYYY/MM/DD>剩余 N 天` · `未开启|已开启`) vào một tệp rồi chạy lệnh trên. Nghiêm ngặt: dòng sai khuôn dạng,
bản dán bị cắt, id lặp, ngày không tồn tại → lỗi kèm **số dòng**, không bao giờ im lặng bỏ qua một model. Gộp: model mới được thêm; model đã có chỉ được **làm mới các trường do console quyết định**
(`console_category`, tổng/còn lại, thời điểm chụp, hạn dùng, Free Quota Only) — tầng, RPM, TPM, thinking, đa phương thức, số đo do Owner/benchmark ghi **không bao giờ bị ghi đè**; chạy lại là idempotent.
Giới hạn của nguồn (ghi vào `notes` của tệp): bảng **không có đơn vị** (→ `quota_unit=null`); `10K`/`1M` là số làm tròn của console; hạn dùng chỉ có NGÀY (lưu 00:00 UTC của ngày đó, có thể lệch tới 1 ngày); thời điểm chụp suy ra từ
`剩余 N 天` (các dòng phải cùng cho một ngày, không thì phải cấp `--captured-at`); bản dán không kèm tiêu đề cột nên `未开启/已开启` được đọc là Free Quota Only **chưa bật/đã bật — chờ Owner xác nhận**.

## 2. Bản ghi hiện tại

`qwen3.7-plus` — **SMART, `slot_thinking=off`**, `validated_candidate`: hạn mức 992.190/1.000.000 token (ảnh chụp 2026-10-03, hết hạn 2026-12-02), 15.000 RPM,
5.000.000 TPM, thinking lai **mặc định bật**, Free Quota Only `not_enabled` (Owner bỏ qua công tắc vì tài khoản chưa gắn thẻ — lời Owner, ta không tự kiểm chứng).
Số đo canary (6 lượt `off`, 2 lượt `on`) nằm ở `observations`. `input_modalities` **chưa ghi nhận** nên `report` báo `INCOMPLETE` (slot `alibaba-sg-01` đã có và đang ngủ đông;
mức sẵn sàng chỉ nói về việc tạo THÊM slot từ kiểm kê).

**49 model từ bảng Free Quota (Owner dán, chụp 2026-10-02 theo `剩余 N 天`)** — nguồn gốc nguyên văn ở `docs/ai/alibaba_free_quota_console_paste.txt`; bài kiểm khoá tệp JSON không được lệch khỏi nguồn này.
Gồm **43 model `语音模型`** (TTS: `qwen3-tts-*`, `cosyvoice-v3-*`, `qwen-audio-3.0-tts-*`; nhận dạng giọng nói: `qwen3-asr-*`, `fun-asr*`, `qwen-audio-3.x-asr-*`; dịch trực tiếp: `*-livetranslate-*`; `qwen3-omni-30b-a3b-captioner`;
`qwen-voice-design`) và **6 model `向量模型`** (`text-embedding-v3/v4`, `qwen3.7-text-embedding`, `tongyi-embedding-vision-flash/plus`, `qwen3-rerank`). Số dư đều còn nguyên (còn = tổng); hạn dùng 2026-12-01, 12-02, 12-15 hoặc 12-20;
Free Quota Only đều `未开启`. Tất cả đang **INCOMPLETE** (chưa có tầng, đơn vị, RPM/TPM, thinking, đa phương thức) — **không có gì được đoán**.

Hai điều bản dán cho thấy:
* **Không có model chat nào trong bản dán** (ngoài `qwen3.7-plus` đã có): chưa thấy các dòng văn bản/đa phương thức thường (ứng viên FAST/ADVANCED/TRANSLATION/VISION). Bảng đầy đủ còn các danh mục khác.
* **Các model giọng nói không khớp tầng chat nào** trong sáu tầng, và không đi qua router chat (cần TTS/ASR riêng — gần với `desktop_app/providers` của sản phẩm TTS hơn là `ControlledGateway`). Cần Owner quyết:
  để chúng ngoài định tuyến chat (chỉ lưu kiểm kê), hay mở một đường tích hợp riêng sau. Gợi ý theo danh mục (không lưu thành tầng): `向量模型` → `EMBEDDING` (riêng `qwen3-rerank` là mô hình xếp hạng lại, Owner quyết); `语音模型` → chưa có tầng tương ứng.

## 3. Thinking: quy tắc bắt buộc

* Model **lai thinking mặc định bật** (như `qwen3.7-plus`) PHẢI cấu hình slot `thinking=off`, nếu không sẽ tốn token suy luận ẩn.
* **`max_output_tokens` KHÔNG chặn token suy luận ẩn** (đo thật 2026-10-03: `max_output_tokens=400` nhưng `thinking=on` ra 1.233–1.482 token, chậm ~12 lần ở TTFT, gấp 3,7–6 lần
  token, văn bản hiển thị gần như không khác). Vì vậy bất kỳ đường chạy production nào bật thinking **phải làm ngân sách suy luận RIÊNG, có giới hạn, TRƯỚC** — chưa có, nên
  kiểm kê **từ chối** `slot_thinking=on` (số đo của lần chạy `on` vẫn ghi được ở `observations`: đó là dữ liệu, không phải cấu hình). Không bật thinking mặc định ở đâu cả.

## 4. Lộ trình định tuyến theo tầng (mỗi pha chỉ làm khi pha trước xong; **chưa pha nào được phép chạy thật**)

| Pha | Việc | Cần Owner |
|---|---|---|
| N0 (xong) | định dạng kiểm kê + công cụ + bản ghi `qwen3.7-plus` | — |
| N1 | Owner gửi ảnh chụp console (mục 5); Claude chép vào kiểm kê, `report` cho biết model nào READY, tầng nào còn trống | ảnh chụp |
| N2 | Owner chọn model nào vào tầng nào; tạo slot **TẮT** từ kiểm kê (`slot …` → `POST /api/admin/ai/slots`), không thêm vào hồ sơ nào | duyệt |
| N3 | probe + benchmark từng model qua tuyến Owner-only (như `ALIBABA_CANARY`), ghi `observations` | duyệt (có gọi Alibaba thật, tốn hạn mức) |
| N4 | định tuyến công khai theo **tầng** (gói/tính năng → tầng → slot), vẫn không gắn gói với tên model; Gemini giữ nguyên là nền | duyệt riêng |
| N5 | chỉ khi N4 ổn: cân nhắc `FAS_AI_PREFER_FREE_QUOTA=1` (ưu tiên hạn mức sắp hết hạn; đã cài, đang NGỦ ĐÔNG) | duyệt riêng |

Máy móc đã có sẵn ở router (`plan(..., tier=…)`, `serves_tier`, `tier_map`, `order_by_expiring_free_quota`) và hiện **không route chat nào truyền tier**; PR này không đổi điều đó.

## 5. Owner cần cung cấp gì (ảnh chụp Model Studio — cắt bỏ khoá API / WorkspaceId)

0. **Đã có (2026-10-03):** phần bảng Free Quota gồm 43 model `语音模型` + 6 model `向量模型` (bản dán văn bản). **Còn thiếu:** các danh mục khác của bảng — nhất là **model văn bản/chat và đa phương thức** (ứng viên
   FAST/ADVANCED/TRANSLATION/VISION), vì bản dán không có dòng nào ngoài giọng nói và vector.
1. **Phần còn lại của bảng Free Quota** (Model usage → tab **Free Quota**; dán nguyên văn như lần trước, hoặc chụp mọi trang). Với **mỗi model** cần: *tên model đầy đủ* · *còn lại / tổng* ·
   ***đơn vị*** (token/ảnh/giây/ký tự/lần — **bản dán lần trước không có đơn vị**) · *ngày hết hạn* · *cột/công tắc **Free Quota Only***. **Kèm tiêu đề các cột** (để xác nhận `未开启/已开启` đúng là Free Quota Only) và **ngày giờ + múi giờ** lúc chụp.
2. **Trang chi tiết (model card) của TỪNG model muốn dùng** (ưu tiên ứng viên cho FAST, ADVANCED, TRANSLATION, VISION, EMBEDDING; SMART đã có qwen3.7-plus): *danh mục/khả năng* ·
   *giới hạn tốc độ **RPM** và **TPM*** · *đầu vào hỗ trợ* (văn bản/ảnh/âm thanh/video) · *chế độ thinking* (không có / lai bật-tắt được / chỉ-thinking) và *mặc định bật hay tắt*.
3. **Bổ sung cho `qwen3.7-plus`** (đang thiếu): đầu vào hỗ trợ (đa phương thức hay chỉ văn bản).
4. **Quyết định của Owner**: model nào là ứng viên cho tầng nào (không suy từ tên); có muốn bật **Free Quota Only** trên console cho từng model hay không (tài khoản hiện chưa gắn thẻ;
   thay đổi có hiệu lực không tức thì, ~30 phút).
5. Nếu console cho **xuất bảng** (CSV/Excel) thì gửi luôn tệp đó — nhập CSV nhanh và ít sai hơn đọc ảnh.

Không cần gửi: khoá API, WorkspaceId, endpoint (đã có sẵn). Không có lượt gọi Alibaba thật nào được thực hiện cho tới khi Owner duyệt pha N3.
