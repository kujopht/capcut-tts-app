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
python scripts/alibaba_inventory.py candidates docs/ai/alibaba_model_inventory.json --paste docs/ai/alibaba_free_quota_console_paste.txt --md docs/ai/ALIBABA_CAPABILITY_CANDIDATES.md   # báo cáo ứng viên 12 nhóm
python scripts/alibaba_inventory.py from-csv bang.csv --captured-at <ISO> --region ap-southeast-1 > kiem_ke.json
python scripts/alibaba_inventory.py slot docs/ai/alibaba_model_inventory.json <model_id> --slot-id alibaba-sg-02 --secret-ref ALIBABA_SG_02 --endpoint <endpoint workspace>
python scripts/alibaba_inventory.py template                                          # khung MỘT model (model_id để trống có chủ ý)
```

CSV (`docs/ai/alibaba_model_inventory.template.csv`): một dòng mỗi model, ô trống = chưa biết, danh sách ngăn bằng `|`, số theo kiểu console
(`1,000,000`, `992.19K`, `1M`). **Lưu ý**: console làm tròn (`992.19K` ≈ 992.190 token) — số dư là gần đúng tới hàng chục token. `observations` chỉ nhập bằng JSON.
Mã thoát: 0 ổn, 1 không hợp lệ, 2 model chưa READY (không in payload).

### Nhập thẳng từ bảng Free Quota của console (`parse-console`)

Dán nguyên văn bảng vào một tệp rồi chạy lệnh trên. Khuôn của bảng: tiêu đề cột 6 dòng (`模型 Code / 模型类型 / 剩余额度 / 到期时间 / 状态 / 用完即停`, lặp lại mỗi trang) rồi mỗi model một khối **3–4 dòng**:
`<id>  <模型类型>` · `剩 X / 共 Y` · `<YYYY/MM/DD>剩余 N 天` · `[已开启|未开启]`. Dòng cuối là giá trị cột **`用完即停`** ("dừng khi dùng hết" = Free Quota Only); cột `状态` không có chữ trong bản dán. Khối có thể **thiếu dòng cuối**
(hàng bị ngắt trang) → cảnh báo `missing_state`, trạng thái để chưa biết, không đoán.

Bộ đọc gom **mọi** vấn đề theo từng dòng thay vì dừng ở lỗi đầu tiên: dòng lạ (`bad_line`), khối thiếu dòng hạn mức/hạn dùng (`incomplete_row`), số không đọc được (`bad_number`), còn lại > tổng (`quota_over_total`), ngày không tồn tại (`bad_date`),
id lặp (`duplicate_model`), dòng mồ côi (`orphan_line`), tiêu đề cột sai (`header_incomplete`), các dòng cho nhiều ngày chụp khác nhau (`capture_day_conflict`). Khối lỗi **bị loại và được báo kèm số dòng**, khối lành vẫn được đọc; còn lỗi thì CLI **không ghi** kết quả.
CLI in bảng **số model theo danh mục console (đếm thô bằng regex độc lập → đọc được)**, số dòng hạn mức/hạn dùng/trạng thái/tiêu đề, và "Đối chiếu số đếm: KHỚP/LỆCH" (số dòng trạng thái phải bằng số model trừ số cảnh báo `missing_state`).

Gộp: model mới được thêm; model đã có chỉ được **làm mới các trường do console quyết định** (`console_category`, tổng/còn lại, thời điểm chụp, hạn dùng, Free Quota Only; khối thiếu dòng trạng thái KHÔNG xoá giá trị đã biết) — tầng, RPM, TPM, thinking, đa phương thức,
số đo do Owner/benchmark ghi **không bao giờ bị ghi đè**; một lần đổi Free Quota Only được ghi vào `free_quota_only_note`; ghi chú chung `[console]` được thay (không nhân đôi); chạy lại là idempotent.

Giới hạn của nguồn (ghi vào `notes` của tệp): bảng **không có cột đơn vị** (→ `quota_unit=null`; riêng `qwen3.7-plus` đã đối chiếu = tokens); `10K`/`1M`/`984.2K` là số làm tròn của console; hạn dùng chỉ có NGÀY (lưu 00:00 UTC của ngày đó, sớm hơn hạn thật tới ~1 ngày — thận trọng);
**ngày chụp = ngày hết hạn − (N − 1)** với `剩余 N 天` (console đếm cả ngày hết hạn; bằng chứng: số dư `qwen3.7-plus` 984.2K đã phản ánh canary ngày 2026-10-03, và `qwen-plus` còn "1 ngày" vào đúng ngày hết hạn — phiên bản đầu của công cụ này trừ `N` và suy ra sai 2026-10-02, đã sửa);
vị trí dòng cuối ↔ cột `用完即停` là suy ra từ tiêu đề cột (chờ Owner xác nhận).

## 2. Bản ghi hiện tại

`qwen3.7-plus` — **baseline SMART đã kiểm chứng, `slot_thinking=off`**, `validated_candidate`: còn 984.200/1.000.000 token (bảng đầy đủ, ngày chụp 2026-10-03; số dư khớp ước tính của ta 992.190 − 7.918 token canary), hết hạn 2026-12-02,
15.000 RPM, 5.000.000 TPM, thinking lai **mặc định bật**, đơn vị `tokens` (đối chiếu được). **Free Quota Only trên console nay là `confirmed_on`** (cột `用完即停` = 已开启; sáng 2026-10-03 Owner còn bỏ qua công tắc) — nhưng cờ `free_quota_only` ở phía
ứng dụng của slot `alibaba-sg-01` VẪN là `false` (chưa đổi; slot đang ngủ đông). Số đo canary (6 lượt `off`, 2 lượt `on`) nằm ở `observations`. `input_modalities` **chưa ghi nhận** nên `report` báo `INCOMPLETE`.

**249 model từ bảng Free Quota đầy đủ (Owner dán, ngày chụp 2026-10-03)** — mỗi model ID là một mục hạn mức riêng (id + số dư + hạn dùng + ảnh chụp riêng); nguồn gốc nguyên văn ở `docs/ai/alibaba_free_quota_console_paste.txt`, và bài kiểm khoá tệp JSON không được lệch khỏi nguồn này.
Đếm thô độc lập khớp số đọc được theo từng danh mục: **大语言模型 102 · 视觉模型 67 · 多模态模型 21 · 语音模型 53 · 向量模型 6 = 249**; 249 dòng hạn mức, 249 dòng hạn dùng, 247 dòng trạng thái (đúng 2 khối thiếu: `qwen3.6-plus-2026-04-02`, `fun-asr-2025-11-07`), 2 khối tiêu đề; **0 dòng parse lỗi**, 2 cảnh báo.
Free Quota Only (cột `用完即停`): bật 159 · chưa bật 88 · chưa biết 2. **Thiếu đơn vị hạn mức: 248/249** (bảng không có cột đơn vị). 247 model INCOMPLETE (chưa có tầng, đơn vị, RPM/TPM, thinking, đa phương thức), 2 BLOCKED (`qwen-plus`, `qwen-turbo`: hết hạn 2026-10-03) — **không có gì được đoán**.

Báo cáo **ứng viên năng lực** theo 12 nhóm (FAST, SMART, ADVANCED, DEEP, CODING, CHARACTER, TRANSLATION, VISION, IMAGE, VIDEO, AUDIO, EMBEDDING/RERANK) nằm ở `docs/ai/ALIBABA_CAPABILITY_CANDIDATES.md` (sinh tự động bằng `candidates`, có bài kiểm so từng ký tự). **Chỉ là gợi ý**: `CAPABILITY_TIERS` của slot (6 tầng, đang
được bộ kiểm tra slot ở production dùng) KHÔNG đổi và `tiers` không bị ghi cho model nào ngoài baseline. Bằng chứng có hai bậc — `category` (danh mục console tự nói) và `name` (dấu hiệu trong tên: chỉ là giả thuyết, luật nào bắn được ghi rõ); 23 model không đủ bằng chứng nằm ở "unclassified".

Điều dữ liệu thật cho thấy:
* **Danh mục console không đồng nghĩa khả năng**: `wan2.2-kf2v-flash` (tên là model video) nằm ở `大语言模型` với hạn mức 50 — báo cáo đánh dấu và xếp nó vào VIDEO theo tên.
* **Cỡ hạn mức gợi ý đơn vị nhưng không xác nhận**: `1M` (văn bản/đa phương thức/vector) giống token; `10–200` (ảnh/video) giống số lần; `10K/36K/1K/10` (giọng nói) có thể là ký tự/giây/lần. Chỉ `qwen3.7-plus` đã đối chiếu.
* **Hạn mức còn bị tiêu từ nơi khác**: 12 model đã mất một phần (`qwen-plus` −29.330, `qwen3.7-plus` −15.800 trong đó ~7,9K là canary của ta, `qwen3.5-flash` −330, …) trong khi ta chỉ từng gọi `qwen3.7-plus` — đúng giới hạn "tài khoản có thể có nơi tiêu hạn mức khác" ở `ALIBABA_PROVIDER.md` mục 7.
* **Model giọng nói (53) không khớp tầng chat nào** và không đi qua router chat (TTS/ASR gần với `desktop_app/providers` của sản phẩm TTS hơn là `ControlledGateway`); 21 model omni (`多模态模型`) được gợi ý cả VISION và AUDIO nhưng đầu vào hỗ trợ chưa xác nhận. Owner quyết: chỉ lưu kiểm kê hay mở đường tích hợp riêng.
* `qwen-plus` và `qwen-turbo` **hết hạn ngày 2026-10-03** (còn 970.670 / 999.990).

## 3. Thinking: quy tắc bắt buộc

* Model **lai thinking mặc định bật** (như `qwen3.7-plus`) PHẢI cấu hình slot `thinking=off`, nếu không sẽ tốn token suy luận ẩn.
* **`max_output_tokens` KHÔNG chặn token suy luận ẩn** (đo thật 2026-10-03: `max_output_tokens=400` nhưng `thinking=on` ra 1.233–1.482 token, chậm ~12 lần ở TTFT, gấp 3,7–6 lần
  token, văn bản hiển thị gần như không khác). Vì vậy bất kỳ đường chạy production nào bật thinking **phải làm ngân sách suy luận RIÊNG, có giới hạn, TRƯỚC** — chưa có, nên
  kiểm kê **từ chối** `slot_thinking=on` (số đo của lần chạy `on` vẫn ghi được ở `observations`: đó là dữ liệu, không phải cấu hình). Không bật thinking mặc định ở đâu cả.

## 4. Lộ trình định tuyến theo tầng (mỗi pha chỉ làm khi pha trước xong; **chưa pha nào được phép chạy thật**)

| Pha | Việc | Cần Owner |
|---|---|---|
| N0 (xong) | định dạng kiểm kê + công cụ + bản ghi `qwen3.7-plus` | — |
| N1 (một phần xong) | bảng Free Quota đầy đủ đã vào kiểm kê (249 model) + báo cáo ứng viên; còn đơn vị, RPM/TPM, thinking, đa phương thức (mục 5); `report` cho biết model nào READY, tầng nào còn trống | thông tin còn thiếu (mục 5) |
| N2 | Owner chọn model nào vào tầng nào; tạo slot **TẮT** từ kiểm kê (`slot …` → `POST /api/admin/ai/slots`), không thêm vào hồ sơ nào | duyệt |
| N3 | probe + benchmark từng model qua tuyến Owner-only (như `ALIBABA_CANARY`), ghi `observations` | duyệt (có gọi Alibaba thật, tốn hạn mức) |
| N4 | định tuyến công khai theo **tầng** (gói/tính năng → tầng → slot), vẫn không gắn gói với tên model; Gemini giữ nguyên là nền | duyệt riêng |
| N5 | chỉ khi N4 ổn: cân nhắc `FAS_AI_PREFER_FREE_QUOTA=1` (ưu tiên hạn mức sắp hết hạn; đã cài, đang NGỦ ĐÔNG) | duyệt riêng |

Máy móc đã có sẵn ở router (`plan(..., tier=…)`, `serves_tier`, `tier_map`, `order_by_expiring_free_quota`) và hiện **không route chat nào truyền tier**; PR này không đổi điều đó.

## 5. Owner cần cung cấp gì (ảnh chụp Model Studio — cắt bỏ khoá API / WorkspaceId)

0. **Đã có (2026-10-03):** toàn bộ bảng Free Quota (249 model, cả 5 danh mục, kèm tiêu đề cột). Còn lại là những thứ **bảng không có**:
1. **Đơn vị hạn mức** của từng danh mục (token / ký tự / giây / ảnh / video / lần) — bảng chỉ có con số. Cách nhanh nhất: xem trang giá/chi tiết của một model đại diện mỗi danh mục (và `qwen-image*`/`wan*` cho ảnh/video, `qwen3-tts*`/`qwen3-asr*`/`fun-asr*` cho giọng nói).
2. **Xác nhận một điều**: dòng cuối mỗi khối (`已开启/未开启`) đúng là cột **`用完即停`** (Free Quota Only), không phải cột `状态`. Và với 2 khối thiếu dòng này (`qwen3.6-plus-2026-04-02`, `fun-asr-2025-11-07`) thì công tắc đang bật hay chưa.
3. **Trang chi tiết (model card) của TỪNG model muốn dùng** — ưu tiên ứng viên mỗi nhóm trong báo cáo ứng viên: *giới hạn tốc độ **RPM** và **TPM***, *đầu vào hỗ trợ* (văn bản/ảnh/âm thanh/video), *chế độ thinking* (không có / lai bật-tắt được / chỉ-thinking) và *mặc định bật hay tắt*.
   Với 23 model "chưa đủ bằng chứng" (`glm-5.x`, `kimi-k3`, `deepseek-*`, `qwen3-8b/14b/32b`, `qwen3.5-*b`, `qwen3.8-27b`, `qwen3.8-2.4t-a95b`, …) cần model card để biết thuộc nhóm nào.
4. **Bổ sung cho `qwen3.7-plus`**: đầu vào chỉ văn bản hay đa phương thức.
5. **Quyết định của Owner**: duyệt (hoặc sửa) các gợi ý trong `ALIBABA_CAPABILITY_CANDIDATES.md`; 53 model giọng nói chỉ lưu kiểm kê hay mở đường tích hợp TTS/ASR riêng; có muốn bật cờ `free_quota_only` phía ứng dụng cho slot canary nay khi console đã bật (`confirmed_on`) hay không.
6. Nếu console cho **xuất bảng** (CSV/Excel) thì gửi luôn tệp đó — nhập CSV nhanh và ít sai hơn đọc ảnh.

Không cần gửi: khoá API, WorkspaceId, endpoint (đã có sẵn). Không có lượt gọi Alibaba thật nào được thực hiện cho tới khi Owner duyệt pha N3.
