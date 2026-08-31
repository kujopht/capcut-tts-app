# Tự lưu trữ provider dịch (Hy-MT2 qua vLLM/TGI) — chuẩn bị

Ngày: 2026-08-31
Kho: Fanfic Audio Studio (subsystem `server/translation_*`)

Báo cáo này mô tả những gì **đã sẵn sàng** để kết nối một endpoint dịch tự
lưu trữ tương thích OpenAI — cụ thể họ mô hình Tencent Hy-MT2 phục vụ qua
vLLM/TGI lộ ra API chuẩn `/v1/chat/completions` — và những gì **còn thiếu**
(GPU server). Không build engine dịch mới: chunking (tach_chuong), glossary
bền vững, carryover tóm tắt chương trước (tom_tat_truoc), custom_instruction
(style/dialogue) đều đã có sẵn.

## Kết luận chính

Một server Hy-MT2 tự lưu trữ phơi `/v1/chat/completions` **đã có thể được
phục vụ qua cơ chế provider "tuỳ chỉnh" sẵn có, KHÔNG cần viết provider mới**.
Lớp `DocuTranslateProvider` trong `server/translation_providers.py` và lớp
`_OpenAICompatFreeProvider` trong `server/translation_provider_registry.py`
(gentên chung Groq/Cerebras/Pollinations kế thừa) đều là "bất kỳ endpoint
tương thích OpenAI nào" với `base_url`/`api_key`/`model` do người gọi cung
cấp. Việc nối `TRANSLATION_BASE_URL` vào một vLLM chạy Hy-MT2 là đường dữ
liệu đã có, chỉ cần cấu hình.

## 3 biến môi trường cần thiết

| Biến | Vai trò |
|---|---|
| `TRANSLATION_BASE_URL` | Gốc URL của endpoint tương thích OpenAI, ví dụ `https://hymt2.example.com/v1`. `_OpenAICompatFreeProvider`/`DocuTranslateProvider` POST tới `${BASE_URL}/chat/completions`. |
| `TRANSLATION_API_KEY` | Bí mật Bearer. Tự lưu trữ có thể là một chuỗi tuỳ ý (vd `sk-local-hymt2`); phải khớp `--api-key` của vLLM nếu bật xác thực. |
| `TRANSLATION_MODEL` | **Phải khớp chính xác** `--served-model-name` của vLLM (xem phần GPU ở dưới). |

Ngoài ra, để provider thực sự **vào** registry (không chỉ được cấu hình), cần
`TRANSLATION_CUSTOM_PROVIDER_FREE=true` — xem phần `TRANSLATION_ALLOW_PAID_PROVIDER`
ngay dưới.

## `TRANSLATION_ALLOW_PAID_PROVIDER` nghĩa gì cho provider tự lưu trữ

Dò theo mã thật trong `build_provider_registry` (`server/translation_provider_registry.py`):

```python
custom_free = e.get("TRANSLATION_CUSTOM_PROVIDER_FREE", "false")... == "true"
if custom_url and custom_key and custom_model and (custom_free or cho_phep_tra_phi):
    providers.append(ConfiguredProvider(
        provider_id="custom", model_id=custom_model,
        provider=DocuTranslateProvider(...),
        free_tier=custom_free))                      # <- mấu chốt

if not cho_phep_tra_phi:
    providers = [p for p in providers if p.free_tier]
return ProviderRegistry(providers)                   # <- ProviderRegistry.__init__ LẠI lọc `if p.free_tier`
```

Kết luận chính xác (đã dò đường mã, không đoán):

- `TRANSLATION_ALLOW_PAID_PROVIDER=true` CHỈ làm cho nhánh tạo `ConfiguredProvider`
  chạy khi không đặt `TRANSLATION_CUSTOM_PROVIDER_FREE`. Nhưng cho dù nó chạy,
  provider được tạo với `free_tier=custom_free` (mặc định `False`).
- **`ProviderRegistry.__init__` lọc `[p for p in providers if p.free_tier]`
  VÔ ĐIỀU KIỆN** — đây là "an toàn kép" đã được kiểm chứng bởi
  `test_rao_chan_chung_MOT_MINH_van_KHONG_du` trong `test_translation_pollinations.py`.
  Hệ quả: provider có `free_tier=False` **không bao giờ** vào được registry,
  dù `TRANSLATION_ALLOW_PAID_PROVIDER=true` hay không.
- Do đó, một provider tự lưu trữ **bắt buộc** đặt `TRANSLATION_CUSTOM_PROVIDER_FREE=true`
  (tức đặt `free_tier=True` trên `ProviderCatalogEntry` của nó) để xuất hiện.
  Không có đường "miễn" — không có ngoại lệ dành riêng cho self-host.

Về bản chất chi phí: biến tên "PAID_PROVIDER" nhưng được thực thi thuần bằng
cờ `free_tier`, không nhìn vào giá mỗi token. Một server riêng của bạn được
điều hành trên phần cứng GPU bạn trả tiền là "tốn phí **compute**, không tốn
phí **mỗi token** như SaaS", nhưng mã hiện tại **không phân biệt** hai loại —
nó chỉ biết cờ `free_tier`. Vì vậy hãy đối xử với self-host giống bất kỳ nhà
cung cấp muốn vào registry: đặt `TRANSLATION_CUSTOM_PROVIDER_FREE=true` là
tuyên bố rõ ràng "khoản này nằm ở hạng miễn phí/không phải trả theo token đáng
kể" để đưa nó vào AUTOMATIC routing. Nếu bạn **không** muốn nó tự động tham
gia mà chỉ thử thủ công, hãy để `TRANSLATION_CUSTOM_PROVIDER_FREE` chưa đặt và
chọn nó qua chế độ MANUAL nếu có đường BYOK — nhưng ở đây BYOK không áp dụng
cho shared custom (không có phiên "kết nối cá nhân" nào xây custom), nên trong
thực tế cờ này là đường duy nhất.

## Nó đã được chứng minh bằng test chưa?

Có. Test mới `server/tests/test_translation_selfhosted.py`:
- `CustomProviderHyMT2Test::test_build_provider_registry_va_doc_ban_dich_tu_hy_mt2`
  dựng registry với 3 biến custom + `TRANSLATION_CUSTOM_PROVIDER_FREE=true`,
  thay client bằng `httpx.MockTransport` (không mạng thật) mô phỏng phản hồi
  OpenAI chat-completions **dạng Hy-MT2** (có `id`, `model`, `choices[0].message.content`,
  `usage`), rồi gọi `custom.translate_segment` và khẳng định rút ra đúng bản
  dịch tiếng Việt. Điều này xác nhận `build_provider_registry` tạo provider
  đi qua cổng `TRANSLATION_*` + đường `DocuTranslateProvider` gọi/chỉ đọc đúng
  endpoint chuẩn.

Đồng thời hai khoảng trống kia đã khép trong cùng tập test này:
- `detect_source_language` — nhận diện zh/ja/ko/vi/en/unknown bằng đếm dải
  Unicode (không thêm pip dep), có đồng hồ `create_project` tự phát hiện thay
  vì hardcode "zh" khi không truyền `source_language`.
- `source_text_hash` (đặt lúc `create_project`) + `translated_content_hash`
  (đặt trong `_ghi_version_tu_dong`) + `create_project_or_reuse` idempotent:
  cùng owner + cùng title + cùng `source_text_hash` + job cuối COMPLETED ->
  trả lại project cũ, không tạo trùng, không xếp job mới; nội dung khác ->
  tạo mới.

## Bước còn thiếu để "đi vào sản phẩm" (blocker đã có, ngoài phạm vi)

Việc **cung cấp/khởi chạy GPU server thực sự** nằm **NGÒI phạm vi** của đợt
này — hiện không có quyền truy cập compute nào tại máy này để khởi động một
con vLLM/TGI. Đây là blocker riêng, đã được gắn cờ và **không được giải quyết
ở đây**. Khi có GPU, việc cần làm cụ thể:

1. Khởi chạy vLLM phục vụ mô hình Hy-MT2, ví dụ:
   `vllm serve <model-id-hy-mt2> --served-model-name <TRANSLATION_MODEL> --port 8000`
   — `--served-model-name` **phải khớp** `TRANSLATION_MODEL` đặt trong env
   của backend, nếu không `model` trong request sẽ bị vLLM từ chối.
2. (Tuỳ chọn) đặt `--api-key <TRANSLATION_API_KEY>` và truyền khớp key đó.
3. Đặt 4 biến env: `TRANSLATION_BASE_URL`, `TRANSLATION_API_KEY`,
   `TRANSLATION_MODEL`, `TRANSLATION_CUSTOM_PROVIDER_FREE=true`.
4. Khởi động lại backend, kiểm `GET /api/translate/providers` thấy `custom`
   với model tương ứng rồi chạy một job dịch thật.

Cho đến khi GPU đó hiện diện, đường `custom` vẫn đúng nghĩa là "tự lưu trữ cá
nhân/tổ chức", tách biệt với các provider SaaS (Cerebras/Groq/Cloudflare/
Pollinations) — mã không cần đổi.

## Hạng mục | Trước khi sửa | Sau khi sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Ngôn ngữ nguồn | Hardcode `"zh"` cho mọi project | `create_project` tự phát hiện qua `detect_source_language` khi không truyền `source_language` |
| Theo dõi thay đổi nguồn | Không có | `TranslationProject.source_text_hash` (sha256 sau chuẩn hoá khoảng trắng) |
| Theo dõi bản dịch | Không có | `TranslationVersion.translated_content_hash` ghi lúc auto-save |
| Bỏ qua chương không đổi | Chưa có (luôn tạo mới/dịch lại) | `create_project_or_reuse` idempotent dựa title+hàsh+job COMPLETED |
| Route custom self-host | Đã tồn tại nhưng được "tin" chứ không được chứng minh | Test fixture Hy-MT2 qua MockTransport chứng minh đường custom đọc đúng bản dịch |
