# Kiểm toán khả năng chống chịu lỗi (Error/Resilience) — Phase 10

Overnight Pre-Production Hardening Marathon V1. Phạm vi: đọc code tĩnh trong
`server/` (không dựng lỗi thật trên Appwrite Cloud). Mục tiêu: tìm lỗi
resilience KHÁC với lỗi `UnicodeEncodeError` đã sửa trước đó trong phiên này
(một `print()` non-ASCII ở handler fallback `admin_overview`, `server/main.py`).

## Tóm tắt theo 5 mục yêu cầu

| Mục | Phạm vi | Kết luận |
|---|---|---|
| 1. TTS job pipeline (`server/main.py`, `server/worker.py`, `desktop_app/providers/`) | Job thất bại giữa chừng, giới hạn retry, worker restart | SẠCH |
| 2. Translation job pipeline (`server/translation_service.py`, `translation_providers.py`, `appwrite_translation_store.py`) | Lease hết hạn, backoff 429/5xx | SẠCH |
| 3. `print()`/log non-ASCII có nguy cơ `UnicodeEncodeError` trên console Windows | Toàn bộ `server/*.py` | SẠCH — không tìm thêm lỗi nào khác |
| 4. `except Exception` nuốt lỗi âm thầm | Toàn bộ `server/*.py` | SẠCH về mặt đúng-sai, 1 ghi nhận MINOR (thiếu log quan sát) |
| 5. Timeout cho HTTP ra ngoài (YouTube, translation provider, R2, Appwrite) | Toàn bộ client HTTP trong `server/` | SẠCH, 1 ghi nhận MINOR (R2/boto3) |

## Chi tiết

### 1. TTS job pipeline — SẠCH

- `server/main.py::_run_job` (dòng 1789-1996): claim TRƯỚC `try` (đã có ghi
  chú lịch sử về lỗi từng gặp khi claim nằm trong `try`), MỌI lần ghi trạng
  thái đều kèm fencing token (`save_job_fenced`), thứ tự bắt buộc
  synthesize → upload → create_track → `completed` nên không bao giờ có job
  `completed` mà thiếu audio.
- `recover_stale_jobs()` (dòng 2081-2192): idempotent, kiểm tra
  `job.lease_is_live()` trước khi nhận lại, kiểm tra `_job_threads` trong bộ
  nhớ tiến trình TRƯỚC khi claim để tránh 2 thread cùng chạy 1 job (bug này
  đã từng xảy ra trên staging theo comment, đã vá).
- `JOB_MAX_ATTEMPTS`: có giới hạn số lần thử (dòng 2158-2168) — job vượt trần
  bị chuyển `failed` với thông báo đọc được, KHÔNG xoay vòng vô hạn.
- Worker restart giữa job đang chạy: lease hết hạn (`FAS_JOB_LEASE_SECONDS`)
  + heartbeat gia hạn định kỳ (`JOB_HEARTBEAT_SECONDS`) + fencing token chặn
  worker cũ ghi đè kết quả của worker mới — đã có test riêng
  (`test_lease_hardening.py`, `test_recovery_and_reconcile.py`,
  `test_worker_split.py`).
- `desktop_app/providers/edge_provider.py`: retry có giới hạn
  (`MAX_ATTEMPTS`) kèm `RETRY_BACKOFF_SECONDS` tăng dần — không phải vòng lặp
  retry vô hạn.

### 2. Translation job pipeline — SẠCH

- `server/translation_service.py::recover_stale_jobs`/`_run_job`/`_thuc_thi_job`
  dùng đúng khuôn claim/lease/fence với TTS, bảng riêng
  (`translation_jobs`/`translation_job_claims`).
- `TRANSLATION_JOB_MAX_ATTEMPTS = 3` (dòng 96) — có trần, NHƯNG cố ý loại trừ
  trạng thái `WAITING_FOR_PROVIDER` khỏi kiểm tra trần này (dòng 603-613):
  đây là thiết kế đúng ý đồ (chờ hạn mức miễn phí reset là vòng lặp BÌNH
  THƯỜNG, không phải dấu hiệu worker chết) — đã ghi rõ trong comment, không
  phải bug.
- Backoff 429/5xx: `server/translation_provider_registry.py`
  (`_OpenAICompatFreeProvider.translate_segment`, dòng 291-300) phân biệt rõ
  429-quota vs 429-rate-limit, đọc header `Retry-After` nếu có
  (`_retry_after_to_iso`), và có `DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60`
  khi provider không kèm header — KHÔNG hammer liên tục, cũng KHÔNG coi
  provider "chết vĩnh viễn" khi thiếu header (bug này được ghi chú đã từng
  tồn tại trước "V6 cerebras-groq-translation", nay đã sửa).
- `AllProvidersUnavailable` → job chuyển `waiting_for_provider` (không phải
  `failed`), `retry_not_before` lấy mốc SỚM NHẤT trong các provider, có
  backoff mặc định (`TRANSLATION_WAITING_DEFAULT_RETRY_SECONDS = 300`) khi
  không provider nào báo mốc cụ thể.
- `appwrite_translation_store.py::claim_job`/`renew_lease`/`save_job_fenced`:
  dùng transaction Appwrite thật (create+update trong 1 transaction), so
  khớp `attempts`/`lease_owner` trước khi ghi — đúng compare-and-set.

### 3. `print()`/log non-ASCII — SẠCH, không tìm thêm lỗi

Đã grep toàn bộ `server/*.py` cho `print(...)` chứa ký tự có dấu tiếng Việt.
Kết quả:

- `server/main.py:3786-3791` (`_an_toan` trong `admin_overview`) — CHÍNH LÀ
  handler đã sửa trong phiên này (nay ASCII thuần), xác nhận lại còn nguyên
  vẹn.
- `server/main.py:317-320` (`_canh_bao_ngan_sach_image_studio`) — ASCII
  thuần (`thang=`, `da_chi=`, `han_muc=`), an toàn.
- `server/main.py:1910-1911`, `1938-1939` — `print("canh bao: ...")` ASCII
  thuần (không dấu), an toàn.
- `server/worker.py` và `server/translation_worker.py` — CÓ in JSON kèm
  tiếng Việt có dấu (`ensure_ascii=False`), NHƯNG cả hai file đều tự gọi
  `_ep_utf8()` ngay khi import (`sys.stdout/stderr.reconfigure(encoding="utf-8",
  errors="replace")`) TRƯỚC bất kỳ lệnh `print` nào — nên không thể tái phát
  `UnicodeEncodeError` kiểu đã sửa. Đây là thiết kế đã phòng thủ đúng, không
  phải lỗ hổng.

Không tìm thấy `print()`/log non-ASCII nào khác có nguy cơ tương tự lỗi đã
sửa.

### 4. `except Exception` nuốt lỗi âm thầm — SẠCH, 1 ghi nhận MINOR

Rà toàn bộ `except Exception` trong `server/*.py` (không tính `tests/`).
Phần lớn có comment giải thích rõ lý do chấp nhận được (mạng chập chờn,
dọn dẹp không quan trọng, ghi tiến độ mất thì lần sau ghi lại). Một số điểm
swallow lỗi bằng `pass` MÀ KHÔNG log, tuy đúng về mặt thiết kế (không được
phép làm hỏng hành động chính) nhưng thiếu quan sát vận hành:

- `server/main.py:1053` (xoá cover cũ khi gỡ ảnh bìa), `:1300` (xoá object
  rác khi xoá chương), `:1471`/`:1513` (thưởng XP khi xuất bản/tạo chương),
  `:1680` (báo người theo dõi có chương mới), `:3077` (thưởng XP khi nghe đủ
  điều kiện) — tất cả đều là "việc phụ không được phép làm hỏng request
  chính", chủ đích đúng, NHƯNG nếu tầng thưởng XP (`gamification_store`) có
  lỗi hệ thống dai dẳng, không ai biết được vì lỗi bị nuốt hoàn toàn không
  log. Mức độ: MINOR — gợi ý (không sửa trong phiên này) là thêm một dòng
  log cấu trúc (giống style `_an_toan`/`admin_overview`) khi các nhánh này
  bắt được exception, để vận hành đối soát được mà không làm hỏng request
  chính.
- `server/creator_service.py:124/136/377`, `server/appwrite_store.py:782` —
  cùng loại (dọn avatar cũ, callback thông báo quyết định kiểm duyệt, khoá
  job) — cùng đánh giá MINOR, không sửa.

Không tìm thấy trường hợp nào là lỗi thật bị che giấu (ví dụ: nuốt lỗi rồi
báo thành công giả cho client) — mọi đường ghi trạng thái `completed`/`published`
đều đi qua kiểm tra rõ ràng trước khi trả 200.

### 5. Timeout HTTP ra ngoài — SẠCH, 1 ghi nhận MINOR

- Appwrite (`appwrite_adapter.py`, `appwrite_store.py`,
  `appwrite_animation_store.py`, `appwrite_trusted_source_store.py`,
  `youtube_websub.py`, `youtube_client.py`): `REQUEST_TIMEOUT = 15.0`.
- Appwrite translation (`appwrite_translation_store.py`): `REQUEST_TIMEOUT = 30.0`.
- Appwrite gamification (`appwrite_gamification_store.py`): `REQUEST_TIMEOUT = 30.0`.
- Translation provider (Groq/Cerebras/Cloudflare/custom,
  `translation_provider_registry.py`/`translation_providers.py`):
  `TIMEOUT_SECONDS = 60.0` cho lần dịch thật (đoạn văn dài, LLM trả lời
  chậm — có chủ đích), `_KIEM_TRA_TIMEOUT_SECONDS = 15.0` cho kiểm tra kết
  nối (GET /models, nhẹ hơn).
- R2 (`r2_adapter.py`): dùng `boto3.client("s3", ..., config=Config(...,
  retries={"max_attempts": 3}))` nhưng KHÔNG đặt `connect_timeout`/
  `read_timeout` tường minh trong `Config` — dựa vào giá trị mặc định của
  botocore (thường ~60s, KHÔNG phải vô hạn). MINOR — không phải "treo vô
  hạn" nhưng nên đặt tường minh (vd `Config(..., connect_timeout=15,
  read_timeout=60)`) để nhất quán với các client khác và không phụ thuộc
  hành vi mặc định của thư viện bên thứ ba. Không sửa trong phiên này (rủi
  ro thấp, cần test lại toàn bộ đường ghi R2 nếu đổi).

## Bugs tìm thấy

Không có bug mới nào ở mức BLOCKER hoặc cần sửa ngay. Hai ghi nhận MINOR nêu
trên (mục 4 và 5) mang tính cải thiện quan sát/nhất quán, không phải lỗi gây
hỏng chức năng.

## Bugs đã sửa trong phase này

Không có (không tìm thấy lỗi đủ rõ ràng và đủ nhỏ để sửa an toàn theo tiêu
chí của nhiệm vụ).

## Kết luận

Pipeline TTS và Translation đã được thiết kế resilience rất kỹ từ trước
(claim nguyên tử qua transaction Appwrite, fencing token, lease + heartbeat,
giới hạn số lần thử, backoff có cấu trúc cho rate-limit, phân biệt rõ "lỗi
thật" và "chờ hạn mức reset"). Không tìm thấy `UnicodeEncodeError` non-ASCII
nào khác ngoài lỗi đã sửa trước đó trong phiên. Không có exception bị nuốt
theo kiểu che giấu sự cố thật. Timeout HTTP ra ngoài đều được đặt tường minh
trừ một ngoại lệ nhỏ ở R2/boto3 (không phải treo vô hạn).
