# Báo cáo ứng viên năng lực — model Alibaba Model Studio

> **Sinh tự động** từ `docs/ai/alibaba_model_inventory.json` và bản dán nguồn bằng `python scripts/alibaba_inventory.py candidates docs/ai/alibaba_model_inventory.json --paste docs/ai/alibaba_free_quota_console_paste.txt --md docs/ai/ALIBABA_CAPABILITY_CANDIDATES.md`. Một bài kiểm so lại từng ký tự, nên đừng sửa tay.

**Đây là GỢI Ý để Owner duyệt, không phải tầng định tuyến.** `CAPABILITY_TIERS` của slot không đổi, `tiers` của kiểm kê không bị ghi. Bằng chứng có hai bậc:

* **category** — danh mục console tự nói (bằng chứng mạnh);
* **name** — dấu hiệu trong tên model (chỉ là giả thuyết; console còn xếp sai chỗ, xem mục 3).

Mốc dữ liệu: **2026-10-03** (ngày chụp bảng Free Quota) · vùng `ap-southeast-1` · **249 model**. Mọi model đều là một mục hạn mức riêng (id + ảnh chụp riêng).

## 1. Số model theo danh mục console

| Danh mục console | Số model |
|---|---|
| 向量模型 | 6 |
| 多模态模型 | 21 |
| 大语言模型 | 102 |
| 视觉模型 | 67 |
| 语音模型 | 53 |
| **Tổng** | **249** |

Mức sẵn sàng tạo slot: READY 0 · INCOMPLETE 247 · BLOCKED 2. Free Quota Only (cột `用完即停`): bật 159 · chưa bật 88 · chưa biết 2. **Thiếu đơn vị hạn mức: 248/249** (bảng không có cột đơn vị).

## 2. Ứng viên theo nhóm

Một model có thể thuộc nhiều nhóm. Nhóm tổng quát FAST/SMART/ADVANCED chỉ xét model văn bản không chuyên biệt và không phải model suy luận.

| Nhóm | Số ứng viên | Bằng chứng category | Bằng chứng name |
|---|---|---|---|
| FAST | 13 | 0 | 13 |
| SMART | 14 | 0 | 14 |
| ADVANCED | 13 | 0 | 13 |
| DEEP | 9 | 0 | 9 |
| CODING | 9 | 0 | 9 |
| CHARACTER | 2 | 0 | 2 |
| TRANSLATION | 12 | 0 | 12 |
| VISION | 40 | 21 | 19 |
| IMAGE | 32 | 0 | 32 |
| VIDEO | 36 | 0 | 36 |
| AUDIO | 74 | 74 | 0 |
| EMBEDDING_RERANK | 6 | 6 | 0 |

**Baseline đã kiểm chứng:** `qwen3.7-plus` — SMART · `thinking=off` · trạng thái `validated_candidate` · đơn vị `tokens` · Free Quota Only `confirmed_on`.

### FAST (13)

* **name** (13; luật: `N-FAST`): `deepseek-v4-flash`, `deepseek-v4-flash-0731`, `deepseek-v4.1-flash`, `qwen-flash`, `qwen-flash-2025-07-28`, `qwen-turbo`, `qwen3.5-flash`, `qwen3.5-flash-2026-02-23`, `qwen3.6-flash`, `qwen3.6-flash-2026-04-16`, `qwen3.7-flash`, `qwen3.7-flash-2026-07-15`, `qwen3.8-flash`
* Free Quota Only: bật 13 · chưa bật 0 · chưa biết 0; hạn dùng sớm nhất 2026-10-03.

### SMART (14)

* **name** (14; luật: `N-SMART`): `qwen-plus`, `qwen-plus-2025-04-28`, `qwen-plus-2025-07-14`, `qwen-plus-2025-07-28`, `qwen-plus-2025-09-11`, `qwen-plus-2025-12-01`, `qwen-plus-latest`, `qwen3.5-plus`, `qwen3.5-plus-2026-02-15`, `qwen3.5-plus-2026-04-20`, `qwen3.6-plus`, `qwen3.6-plus-2026-04-02`, `qwen3.7-plus`, `qwen3.7-plus-2026-05-26`
* Free Quota Only: bật 13 · chưa bật 0 · chưa biết 1; hạn dùng sớm nhất 2026-10-03.

### ADVANCED (13)

* **name** (13; luật: `N-ADVANCED`): `qwen-max`, `qwen3-max`, `qwen3-max-2025-09-23`, `qwen3-max-2026-01-23`, `qwen3-max-preview`, `qwen3.6-max-preview`, `qwen3.7-max`, `qwen3.7-max-2026-05-17`, `qwen3.7-max-2026-05-20`, `qwen3.7-max-2026-06-08`, `qwen3.7-max-preview`, `qwen3.8-max`, `qwen3.8-max-0902`
* Free Quota Only: bật 13 · chưa bật 0 · chưa biết 0; hạn dùng sớm nhất 2026-12-02.

### DEEP (9)

* **name** (9; luật: `N-DEEP`): `qvq-max`, `qwen3-235b-a22b-thinking-2507`, `qwen3-30b-a3b-thinking-2507`, `qwen3-next-80b-a3b-thinking`, `qwen3-vl-235b-a22b-thinking`, `qwen3-vl-30b-a3b-thinking`, `qwen3-vl-32b-thinking`, `qwen3-vl-8b-thinking`, `qwq-plus`
* Free Quota Only: bật 9 · chưa bật 0 · chưa biết 0; hạn dùng sớm nhất 2026-12-02.

### CODING (9)

* **name** (9; luật: `N-CODING`): `kimi-k2.7-code`, `qwen3-coder-30b-a3b-instruct`, `qwen3-coder-480b-a35b-instruct`, `qwen3-coder-flash`, `qwen3-coder-flash-2025-07-28`, `qwen3-coder-next`, `qwen3-coder-plus`, `qwen3-coder-plus-2025-07-22`, `qwen3-coder-plus-2025-09-23`
* Free Quota Only: bật 9 · chưa bật 0 · chưa biết 0; hạn dùng sớm nhất 2026-12-02.

### CHARACTER (2)

* **name** (2; luật: `N-CHARACTER`): `qwen-flash-character`, `qwen-plus-character`
* Free Quota Only: bật 2 · chưa bật 0 · chưa biết 0; hạn dùng sớm nhất 2026-12-01.

### TRANSLATION (12)

* **name** (12; luật: `N-TRANSLATION`): `qwen-mt-flash`, `qwen-mt-image-2.0`, `qwen-mt-lite`, `qwen-mt-plus`, `qwen-mt-turbo`, `qwen3-livetranslate-flash`, `qwen3-livetranslate-flash-2025-12-01`, `qwen3-livetranslate-flash-realtime`, `qwen3-livetranslate-flash-realtime-2025-09-22`, `qwen3.5-livetranslate-flash-realtime`, `qwen3.5-livetranslate-flash-realtime-2026-05-19`, `qwen3.8-livetranslate-flash-realtime`
* Free Quota Only: bật 5 · chưa bật 7 · chưa biết 0; hạn dùng sớm nhất 2026-12-01.

### VISION (40)

* **category** (21; luật: `C-MULTIMODAL`): `qwen-omni-turbo`, `qwen-omni-turbo-2025-03-26`, `qwen-omni-turbo-realtime`, `qwen-omni-turbo-realtime-2025-05-08`, `qwen2.5-omni-7b`, `qwen3-omni-flash`, `qwen3-omni-flash-2025-09-15`, `qwen3-omni-flash-2025-12-01`, `qwen3-omni-flash-realtime`, `qwen3-omni-flash-realtime-2025-09-15`, `qwen3-omni-flash-realtime-2025-12-01`, `qwen3.5-omni-flash`, `qwen3.5-omni-flash-2026-03-15`, `qwen3.5-omni-flash-realtime`, `qwen3.5-omni-flash-realtime-2026-03-15`, `qwen3.5-omni-plus`, `qwen3.5-omni-plus-2026-03-15`, `qwen3.5-omni-plus-realtime`, `qwen3.5-omni-plus-realtime-2026-03-15`, `qwen3.8-omni-flash`, `qwen3.8-omni-flash-realtime`
* **name** (19; luật: `N-VISION`): `qvq-max`, `qwen-vl-max`, `qwen-vl-ocr`, `qwen-vl-ocr-2025-11-20`, `qwen-vl-plus`, `qwen3-vl-235b-a22b-instruct`, `qwen3-vl-235b-a22b-thinking`, `qwen3-vl-30b-a3b-instruct`, `qwen3-vl-30b-a3b-thinking`, `qwen3-vl-32b-instruct`, `qwen3-vl-32b-thinking`, `qwen3-vl-8b-instruct`, `qwen3-vl-8b-thinking`, `qwen3-vl-flash`, `qwen3-vl-flash-2025-10-15`, `qwen3-vl-flash-2026-01-22`, `qwen3-vl-plus`, `qwen3-vl-plus-2025-09-23`, `qwen3-vl-plus-2025-12-19`
* Free Quota Only: bật 19 · chưa bật 21 · chưa biết 0; hạn dùng sớm nhất 2026-12-02.

### IMAGE (32)

* **name** (32; luật: `N-IMAGE`): `qwen-image`, `qwen-image-2.0`, `qwen-image-2.0-2026-03-03`, `qwen-image-2.0-pro`, `qwen-image-2.0-pro-2026-03-03`, `qwen-image-2.0-pro-2026-04-22`, `qwen-image-2.0-pro-2026-06-22`, `qwen-image-2.1-pro`, `qwen-image-3.0`, `qwen-image-3.0-pro`, `qwen-image-edit`, `qwen-image-edit-max`, `qwen-image-edit-max-2026-01-16`, `qwen-image-edit-plus`, `qwen-image-edit-plus-2025-10-30`, `qwen-image-edit-plus-2025-12-15`, `qwen-image-max`, `qwen-image-max-2025-12-30`, `qwen-image-plus`, `qwen-image-plus-2026-01-09`, `qwen-mt-image-2.0`, `wan2.1-t2i-plus`, `wan2.1-t2i-turbo`, `wan2.2-t2i-flash`, `wan2.2-t2i-plus`, `wan2.5-i2i-preview`, `wan2.5-t2i-preview`, `wan2.6-image`, `wan2.6-t2i`, `wan2.7-image`, `wan2.7-image-pro`, `z-image-turbo`
* Free Quota Only: bật 29 · chưa bật 3 · chưa biết 0; hạn dùng sớm nhất 2026-12-01.

### VIDEO (36)

* **name** (36; luật: `N-VIDEO`): `happyhorse-1.0-i2v`, `happyhorse-1.0-r2v`, `happyhorse-1.0-t2v`, `happyhorse-1.0-video-edit`, `happyhorse-1.1-i2v`, `happyhorse-1.1-r2v`, `happyhorse-1.1-t2v`, `wan2.1-i2v-plus`, `wan2.1-i2v-turbo`, `wan2.1-kf2v-plus`, `wan2.1-t2v-plus`, `wan2.1-t2v-turbo`, `wan2.1-vace-plus`, `wan2.2-animate-mix`, `wan2.2-animate-move`, `wan2.2-i2v-flash`, `wan2.2-i2v-plus`, `wan2.2-kf2v-flash`, `wan2.2-t2v-plus`, `wan2.5-i2v-preview`, `wan2.5-t2v-preview`, `wan2.6-i2v`, `wan2.6-i2v-flash`, `wan2.6-r2v`, `wan2.6-r2v-flash`, `wan2.6-t2v`, `wan2.7-i2v`, `wan2.7-i2v-2026-04-25`, `wan2.7-r2v`, `wan2.7-r2v-2026-06-12`, `wan2.7-t2v`, `wan2.7-t2v-2026-04-25`, `wan2.7-t2v-2026-06-12`, `wan2.7-videoedit`, `wan3.0-video`, `wan3.0-video-prime`
* Free Quota Only: bật 30 · chưa bật 6 · chưa biết 0; hạn dùng sớm nhất 2026-12-02.

### AUDIO (74)

* **category** (74; luật: `C-MULTIMODAL`, `C-SPEECH`): `cosyvoice-v3-flash`, `cosyvoice-v3-plus`, `fun-asr`, `fun-asr-2025-08-25`, `fun-asr-2025-11-07`, `fun-asr-flash-2026-06-15`, `fun-asr-mtl`, `fun-asr-mtl-2025-08-25`, `fun-asr-realtime`, `fun-asr-realtime-2025-11-07`, `qwen-audio-3.0-asr-flash`, `qwen-audio-3.0-asr-flash-filetrans`, `qwen-audio-3.0-asr-flash-streaming`, `qwen-audio-3.0-tts-flash`, `qwen-audio-3.0-tts-plus`, `qwen-audio-3.1-asr-flash`, `qwen-audio-3.1-asr-flash-filetrans`, `qwen-audio-3.1-asr-flash-message`, `qwen-audio-3.1-asr-flash-streaming`, `qwen-omni-turbo`, `qwen-omni-turbo-2025-03-26`, `qwen-omni-turbo-realtime`, `qwen-omni-turbo-realtime-2025-05-08`, `qwen-voice-design`, `qwen-voice-enrollment`, `qwen2.5-omni-7b`, `qwen3-asr-flash`, `qwen3-asr-flash-2025-09-08`, `qwen3-asr-flash-2026-02-10`, `qwen3-asr-flash-filetrans`, `qwen3-asr-flash-filetrans-2025-11-17`, `qwen3-asr-flash-realtime`, `qwen3-asr-flash-realtime-2025-10-27`, `qwen3-asr-flash-realtime-2026-02-10`, `qwen3-livetranslate-flash`, `qwen3-livetranslate-flash-2025-12-01`, `qwen3-livetranslate-flash-realtime`, `qwen3-livetranslate-flash-realtime-2025-09-22`, `qwen3-omni-30b-a3b-captioner`, `qwen3-omni-flash`, `qwen3-omni-flash-2025-09-15`, `qwen3-omni-flash-2025-12-01`, `qwen3-omni-flash-realtime`, `qwen3-omni-flash-realtime-2025-09-15`, `qwen3-omni-flash-realtime-2025-12-01`, `qwen3-tts-flash`, `qwen3-tts-flash-2025-09-18`, `qwen3-tts-flash-2025-11-27`, `qwen3-tts-flash-realtime`, `qwen3-tts-flash-realtime-2025-09-18`, `qwen3-tts-flash-realtime-2025-11-27`, `qwen3-tts-instruct-flash`, `qwen3-tts-instruct-flash-2026-01-26`, `qwen3-tts-instruct-flash-realtime`, `qwen3-tts-instruct-flash-realtime-2026-01-22`, `qwen3-tts-vc-2026-01-22`, `qwen3-tts-vc-realtime-2025-11-27`, `qwen3-tts-vc-realtime-2026-01-15`, `qwen3-tts-vd-2026-01-26`, `qwen3-tts-vd-realtime-2025-12-16`, `qwen3-tts-vd-realtime-2026-01-15`, `qwen3.5-livetranslate-flash-realtime`, `qwen3.5-livetranslate-flash-realtime-2026-05-19`, `qwen3.5-omni-flash`, `qwen3.5-omni-flash-2026-03-15`, `qwen3.5-omni-flash-realtime`, `qwen3.5-omni-flash-realtime-2026-03-15`, `qwen3.5-omni-plus`, `qwen3.5-omni-plus-2026-03-15`, `qwen3.5-omni-plus-realtime`, `qwen3.5-omni-plus-realtime-2026-03-15`, `qwen3.8-livetranslate-flash-realtime`, `qwen3.8-omni-flash`, `qwen3.8-omni-flash-realtime`
* Free Quota Only: bật 0 · chưa bật 73 · chưa biết 1; hạn dùng sớm nhất 2026-12-01.

### EMBEDDING_RERANK (6)

* **category** (6; luật: `C-VECTOR`): `qwen3-rerank`, `qwen3.7-text-embedding`, `text-embedding-v3`, `text-embedding-v4`, `tongyi-embedding-vision-flash`, `tongyi-embedding-vision-plus`
* Free Quota Only: bật 0 · chưa bật 6 · chưa biết 0; hạn dùng sớm nhất 2026-12-01.

### Chưa đủ bằng chứng (unclassified)

23 model không khớp luật nào, không bị ép vào nhóm nào — cần model card hoặc quyết định của Owner: `deepseek-v3.2`, `deepseek-v4-pro`, `deepseek-v4-pro-0813`, `glm-5.1`, `glm-5.2`, `glm-5.3`, `kimi-k3`, `qwen3-14b`, `qwen3-235b-a22b`, `qwen3-235b-a22b-instruct-2507`, `qwen3-30b-a3b`, `qwen3-30b-a3b-instruct-2507`, `qwen3-32b`, `qwen3-8b`, `qwen3-next-80b-a3b-instruct`, `qwen3.5-122b-a10b`, `qwen3.5-27b`, `qwen3.5-35b-a3b`, `qwen3.5-397b-a17b`, `qwen3.6-27b`, `qwen3.6-35b-a3b`, `qwen3.8-2.4t-a95b`, `qwen3.8-27b`

## 3. Dòng cần chú ý

**Parse bản dán nguồn:** SẠCH — 249 khối model thô → 249 đọc được; dòng hạn mức 249, dòng hạn dùng 249, dòng trạng thái 247, khối tiêu đề 2; ngày chụp suy ra 2026-10-03; lỗi bị loại 0; cảnh báo 2.

**Thiếu dòng trạng thái `用完即停` (2):** `fun-asr-2025-11-07`, `qwen3.6-plus-2026-04-02` — free_quota_only để chưa biết (hàng bị ngắt trang/cuối bảng).

**Thiếu đơn vị hạn mức (248):** bảng không có cột đơn vị. Cỡ số gợi ý nhưng KHÔNG xác nhận: `1M` ở nhóm văn bản/đa phương thức/vector giống token; `10–200` ở nhóm ảnh/video giống số lần/ảnh/video; `10K/36K/1K/10` ở giọng nói có thể là ký tự/giây/lần. Riêng `qwen3.7-plus` đã đối chiếu: số dư giảm đúng bằng token ta đã tiêu.

**Danh mục console không khớp tên model:**

* `wan2.2-kf2v-flash`: danh mục 大语言模型 nhưng tên là model VIDEO; hạn mức 50 (không cỡ token).

**Sắp hết hạn (≤ 7 ngày kể từ ngày chụp):** `qwen-plus` (hết 2026-10-03, còn 970670), `qwen-turbo` (hết 2026-10-03, còn 999990) — hạn dùng chỉ có NGÀY và ta lưu 00:00 UTC của ngày đó (sớm hơn hạn thật tới ~1 ngày), nên các model này bị coi là đã hết hạn.

**Đã bị tiêu một phần (12 model):** `deepseek-v3.2` (−10), `deepseek-v4-flash` (−10), `glm-5.3` (−10), `kimi-k3` (−180), `qwen-max` (−20), `qwen-plus` (−29330), `qwen-turbo` (−10), `qwen3.5-flash` (−330), `qwen3.5-plus` (−140), `qwen3.7-plus` (−15800), `qwen3.8-flash` (−100), `qwq-plus` (−80). Ta chỉ từng gọi `qwen3.7-plus` (canary 2026-10-03: ~7,9K token, chỉ là một phần của mức đã tiêu): phần còn lại và mọi model khác cho thấy hạn mức này **còn được tiêu từ nơi khác** (console, ứng dụng khác) — đúng giới hạn đã nêu ở mục 7 của `ALIBABA_PROVIDER.md`.

## 4. Luật phân loại

| Luật | Điều kiện |
|---|---|
| `C-VECTOR` | danh mục console 向量模型 (vector/embedding) |
| `C-SPEECH` | danh mục console 语音模型 (giọng nói: TTS, nhận dạng, dịch trực tiếp) |
| `C-MULTIMODAL` | danh mục console 多模态模型 (đa phương thức) — đầu vào hỗ trợ CHƯA xác nhận |
| `N-IMAGE` | tên chứa image / t2i / i2i |
| `N-VIDEO` | tên chứa t2v / i2v / r2v / kf2v / vace / videoedit / video / animate / happyhorse |
| `N-TRANSLATION` | tên chứa mt (qwen-mt-*) hoặc translate |
| `N-CODING` | tên chứa coder / code |
| `N-CHARACTER` | tên chứa character |
| `N-VISION` | tên chứa vl / ocr / qvq (hiểu ảnh) |
| `N-DEEP` | tên chứa thinking / qwq / qvq (suy luận) |
| `N-FAST` | tên chứa flash / turbo / lite (chỉ cho model văn bản tổng quát, không chuyên biệt, không suy luận) |
| `N-SMART` | tên chứa plus (bậc giữa của dòng Qwen; chỉ cho model văn bản tổng quát, không chuyên biệt, không suy luận) |
| `N-ADVANCED` | tên chứa max (bậc cao nhất của dòng Qwen; chỉ cho model văn bản tổng quát, không chuyên biệt, không suy luận) |

