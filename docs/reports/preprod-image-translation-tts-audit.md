# Phase 8 + 9 — Image Studio / Translation / TTS audit

Chỉ đọc mã nguồn + chạy test có sẵn (mock). Không gọi bất kỳ endpoint sinh
ảnh/dịch/TTS trả phí thật nào, không chạm Appwrite Cloud, không deploy.

Phạm vi đọc: `server/image_wallet_store.py`, `server/image_domain.py`,
`server/image_service.py`, `server/image_spending_guard.py`,
`server/image_provider_registry.py`, `server/image_byop_service.py`,
`server/image_byop_crypto.py`, `server/main.py` (khối khởi tạo Image Studio,
dòng ~289-349, và endpoint kill switch dòng ~6376-6416),
`web/src/app/image-studio/page.tsx`; `server/translation_provider_registry.py`,
`server/translation_integrity.py`, `server/worker.py`,
`server/translation_worker.py`.

## Tóm tắt theo mục

| # | Mục | Kết quả |
|---|---|---|
| 8.1 | Nhãn trạng thái Quick Free / Community Free / kill-switch Shared Premium | **SẠCH** |
| 8.2 | Vòng đời ví (`MockWalletStore`) reserve/settle/refund, double-spend/double-refund | **SẠCH** |
| 8.3 | BYOP secret không lộ ra frontend/log/lỗi | **SẠCH** |
| 8.4 | Lỗi provider được làm sạch trước khi tới client | **SẠCH** |
| 9.1 | Trạng thái khi thiếu cấu hình provider dịch | **SẠCH** |
| 9.2 | Fallback Cerebras/Groq + `TRANSLATION_ALLOW_PAID_PROVIDER` | **SẠCH** |
| 9.3 | Kiểm tra tính vẹn bản dịch | **SẠCH** |
| 9.4 | TTS lease/fencing (so với `translation_worker.py`) | **SẠCH** — dùng chung đúng một cơ chế qua `server/worker.py` gọi lại `main.recover_stale_jobs()`/`main._run_job()` |

**Không phát hiện lỗi nào cần sửa.** Toàn bộ 8 mục đều đạt thiết kế đúng đặc
tả overnight; không có edit nào được thực hiện trong phiên này.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| (không có mục nào cần sửa) | — | — |

---

## PHASE 8 — Image Studio

### 8.1 Nhãn trạng thái các chế độ

- **Quick Free**: `ImageStudioService.sinh_anh_quick_free` (`image_service.py:128-136`)
  không chạm ví, không chạm spending guard — hoàn toàn miễn phí/không giới
  hạn theo Fanfic Credit như nhãn đã ghi. Lỗi provider truyền thẳng lên,
  KHÔNG tự động fallback sang Shared Premium (đúng yêu cầu "không tự đổi
  giọng/chế độ khi thất bại").
- **Community Free**: `catalogue_cong_dong()` (`image_service.py:201-210`)
  phân biệt rõ `available=False` (lỗi lấy danh sách — không phải danh sách
  rỗng hợp lệ) khỏi trường hợp danh sách rỗng thật. `sinh_anh_cong_dong`
  kiểm tra LẠI danh sách ngay trước mỗi lần gọi (không dùng cache cũ), và
  nếu model không còn miễn phí thì ném `CommunityModelNoLongerFree` — CHẶN
  hẳn, không bao giờ âm thầm chuyển sang Shared Premium/trừ Fanfic Credit.
  Frontend (`web/src/app/image-studio/page.tsx:417,426`) hiển thị đúng
  trạng thái "không khả dụng" trung thực, không giả một kết quả thành công.
- **Shared Premium kill-switch**: `server/main.py:299-333` — nếu thiếu
  `POLLINATIONS_API_KEY`, `image_shared_premium_provider = None` và mọi lời
  gọi `sinh_anh_shared_premium`/`sinh_anh_cong_dong` ném lỗi rõ ràng
  ("chưa được cấu hình"), không lùi về một khóa rỗng ngầm. Nếu
  `settings.image_studio.shared_premium_enabled=False`, kill switch của
  `SharedPremiumSpendingGuard` được bật NGAY từ lúc khởi động
  (`dat_kill_switch(True)`) — `bat_dau_request()` sẽ ném
  `SharedPremiumDisabled` TRƯỚC khi ví bị giữ tiền, nên đường trả phí thực
  sự bị chặn khi cờ tắt. Đã xác nhận qua test
  `test_image_spending_guard.py` và `test_image_service.py` (đều pass).

### 8.2 `MockWalletStore` — vòng đời reserve/settle/refund

Đọc toàn bộ `server/image_wallet_store.py` + `server/image_domain.py`:

- **Reserve** (`dat_cho`): ghi một dòng sổ cái ÂM (`RESERVE`,
  `amount_micro=-estimated_cost_micro`) — số dư khả dụng giảm ngay vì
  `available_micro` là tổng cộng dồn của sổ cái, không phải một số có thể
  sửa. `reserved_micro` chỉ là nhãn hiển thị riêng, không trừ thêm lần hai
  (đã đọc kỹ docstring `lay_so_du` dòng 56-78 — không có double-count).
- **Idempotency**: cùng `idempotency_key` gọi lại `dat_cho` trả về CHÍNH
  reservation cũ, không tạo giao dịch mới, không trừ tiền lần hai — chặn ở
  điểm ghi duy nhất `_ghi_giao_dich` (dòng 259-277), đúng yêu cầu "never
  allow double charging on retries".
- **Settle** (`tat_toan`): chỉ chuyển trạng thái reservation đang RESERVED
  (`_reservation_dang_giu` từ chối nếu không đúng trạng thái —
  `InvalidReservationTransition`). Nếu giá thật thấp hơn ước tính, hoàn
  phần chênh lệch bằng một dòng `SETTLE` dương, khóa idempotency riêng
  (`{key}:settle-diff`) — không hoàn hai lần dù gọi lại.
- **Refund** (`hoan_tien`)/**Release** (`giai_phong`): mỗi cái có khóa
  idempotency riêng (`:refund`/`:release`), chỉ áp dụng cho reservation
  đang RESERVED — không có đường nào double-refund vì sau khi hoàn,
  trạng thái chuyển sang `REFUNDED` và `_reservation_dang_giu` sẽ từ chối
  lần gọi lặp lại.
- **Giới hạn đã biết, được ghi rõ**: docstring đầu file
  `image_wallet_store.py` (dòng 4-7) nói thẳng `MockWalletStore` là kho
  MOCK trong bộ nhớ, "ban ben vung Appwrite se noi tiep sau" — giới hạn này
  cũng được ghi trong `docs/reports/image-studio-v1-summary.md`. Đây là
  giới hạn ĐÃ BIẾT/ĐÃ CHẤP NHẬN/HOÃN LẠI theo đúng chỉ định của nhiệm vụ,
  không sửa.

Test `server/tests/test_image_wallet_store.py` (đã chạy, pass) khoá đúng
các bất biến trên bằng test case cụ thể.

### 8.3 BYOP secret handling

- `image_byop_crypto.py`/`image_byop_service.py`: access/refresh token được
  mã hoá ngay sau khi đổi code (`ma_hoa(...)`) trước khi lưu vào
  `MockByopConnectionStore` — không có điểm nào giữ plaintext token lâu hơn
  một lần gọi.
- `giai_ma_access_token` có docstring rõ: "CHI goi tu tang service NGAY
  TRUOC khi goi Pollinations — khong bao gio giu plaintext token lau hon
  mot lan goi, khong bao gio log". Đọc lại toàn bộ file xác nhận không có
  `print`/log nào chứa token thô.
- `ProviderCatalogEntry`/`ProviderProvenance` (phía dịch, tương tự pattern)
  và các lỗi BYOP (`ByopStateMismatch`, `ByopExchangeFailed`) đều dùng
  thông điệp tiếng Việt an toàn, không dump response gốc của Pollinations
  (`ByopExchangeFailed` docstring dòng 59-62 nói rõ điều này).
- `SharedPremiumImageProvider.__init__` gắn `Authorization: Bearer` chỉ vào
  header request server-side, không có đường nào trả header/khóa xuống
  response cho client.

### 8.4 Redaction lỗi provider

`image_provider_registry.py`, hàm `_thong_diep_loi_an_toan` (dòng 87-98):
không dump nguyên văn body provider, chỉ ánh xạ mã trạng thái HTTP sang một
câu tiếng Việt chung (401/403 → "từ chối xác thực", 402 → "hết hạn mức",
429 → "giới hạn tần suất", 5xx → "gặp sự cố"). Cả `QuickFreeImageProvider`
và `SharedPremiumImageProvider` đều dùng hàm này cho mọi nhánh lỗi HTTP —
không có đường nào để lộ exception/stack trace thô ra ngoài.

---

## PHASE 9 — Translation/TTS

### 9.1 Trạng thái khi thiếu cấu hình provider

`build_provider_registry()` (`translation_provider_registry.py:917-1013`):
mỗi provider (Cerebras, Groq, Cloudflare Workers AI, custom) chỉ được thêm
vào registry nếu ĐỦ biến môi trường bắt buộc của nó — thiếu biến thì BỎ QUA
ÂM THẦM (không ném lỗi khởi động), để môi trường dev/test không cấu hình
credential vẫn chạy được, registry chỉ rỗng. Khi registry rỗng,
`ProviderRegistry.translate_segment` ném `AllProvidersUnavailable` — tầng
service xử lý đây KHÔNG PHẢI lỗi "job hỏng" mà chuyển job sang trạng thái
`waiting_for_provider` (xác nhận qua docstring `AllProvidersUnavailable`
dòng 87-102). Đây là trạng thái sạch, không phải crash.

### 9.2 Fallback Cerebras/Groq + `TRANSLATION_ALLOW_PAID_PROVIDER`

- Thứ tự AUTO mặc định: Cerebras được đăng ký TRƯỚC Groq trong danh sách
  đầu vào (dòng 930-961) đúng chiến lược sản xuất tạm thời (Cerebras GPT-OSS
  120B → Groq Qwen → …), và `_sap_theo_vai_tro` định tuyến lại theo
  `quality_mode`/`vai_tro` mà vẫn giữ nguyên vị trí tương đối của các
  provider không phải Groq.
- Khi provider chính rate-limit/hết hạn mức (`ProviderRateLimited`/
  `ProviderQuotaExhausted`), `ConfiguredProvider.translate_segment` cập
  nhật `_status`/`_reset_at` và ném lại lỗi; `_thu_theo_thu_tu` bắt lỗi
  này, ghi nhận mốc reset sớm nhất, rồi thử provider TIẾP THEO trong danh
  sách — đúng hợp đồng fallback.
- `TRANSLATION_ALLOW_PAID_PROVIDER` (mặc định `"false"`): dòng 1011-1012
  xác nhận — khi cờ tắt, registry được lọc lại chỉ giữ
  `p.free_tier == True` NGAY TRƯỚC KHI trả về, bất kể provider nào được
  thêm vào trước đó trong hàm. Hiện tại cả Cerebras/Groq/Cloudflare đều
  được đánh dấu `free_tier=True` nên cờ này chưa chặn gì trong thực tế,
  nhưng đây CHÍNH XÁC là hàng rào bảo vệ tương lai được yêu cầu — không có
  đường nào để một provider `free_tier=False` lọt vào registry khi cờ tắt
  (`ProviderRegistry.__init__` dòng 583-584 cũng lọc lại `p.free_tier` một
  lần nữa — an toàn kép).
- Test `test_translation_cerebras_groq.py`, `test_translation_role_routing.py`
  (khoá thứ tự fallback Qwen → GPT-OSS 120B → GPT-OSS 20B), và
  `test_translation_provider_registry.py` đều pass.

### 9.3 Kiểm tra tính vẹn bản dịch

`server/translation_integrity.py::kiem_tra_tinh_ven` — 5 quy tắc kiểm
chứng được (không phải suy đoán văn phong): bản dịch rỗng, vi phạm glossary
đã chốt, còn sót ký tự Hán, mất đáng kể số dòng/hội thoại (ngưỡng tỷ lệ
0.5, cần nguồn ≥2 dòng để tránh cảnh báo giả khi gộp câu văn học bình
thường), và cắt cụt cuối câu (nguồn kết thúc trọn câu nhưng dịch thì
không). Test `test_translation_integrity.py` pass đầy đủ.

### 9.4 TTS lease/fencing so với pattern trong `worker.py`

`server/worker.py` (tiến trình worker TTS riêng) đọc rõ trong docstring đầu
file (dòng 12-22): nó KHÔNG có logic lease/fencing riêng — nó gọi LẠI đúng
`main.recover_stale_jobs()` (claim nguyên tử qua `store.claim_job()`) và
`main._run_job()` (mọi lần ghi đều kèm fencing token) — CÙNG một mã nguồn
mà tiến trình web dùng ở chế độ inline. Do đó TTS dùng chung chính xác một
cơ chế claim/lease/heartbeat/fencing/giới hạn số lần thử với đường dịch
thuật (`translation_worker.py`), không phải một pattern implement riêng có
nguy cơ lệch nhau. Không có gì cần sửa ở đây.

---

## Kết quả test

Chạy các bộ test liên quan (image + translation, 20 file):

```
Ran 363 tests in 9.671s
OK
```

Chạy toàn bộ `server/tests/` để xác nhận không có hồi quy:

```
Ran 2408 tests in 64.356s
OK (skipped=1)
```

Khớp đúng baseline đã ghi trong nhiệm vụ (~2408/2408, 1 skip không liên
quan). Không có edit nào được thực hiện trong phiên audit này.
