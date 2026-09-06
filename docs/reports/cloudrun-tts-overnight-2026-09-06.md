# Trực đêm không người giám sát — 2026-09-06

Mục tiêu: hoàn tất mọi điều kiện tiên quyết **an toàn** cho canary Cloud Run TTS
và thu bằng chứng production qua đêm. **Không** chạy canary, **không** bật
dispatch, **không** đụng AWS.

## 1. Kiểm thử

| Bộ | Kết quả |
|---|---|
| `test_canary_prereq` | 16 pass |
| `test_tts_dispatch` | 6 pass |
| `test_worker_runtime_pin` | 3 pass |
| `test_worker_capability` | 7 pass |
| `test_lease_hardening` | 18 pass |
| `test_local_voice_allowlist` | 36 pass |
| **Toàn bộ `server/tests`** | **4433 pass, 0 fail, 3 skip** (185s) |
| **Toàn bộ `tests/` (desktop, offscreen)** | **397 pass, 0 fail** (986s) |
| **Tổng** | **4830 pass, 0 fail, 3 skip** |

## 2. Rà soát cấu hình — một lỗi TIMING đã sửa

Hàng đợi `tts-jobs` có `min-backoff=30s` trong khi lease job là **90s**. Worker
chết giữa chừng thì mọi lần thử lại đều gặp lease còn sống → `409` → **đốt hết
lượt thử trước khi lease kịp hết hạn**. Hàng đợi mất sạch tác dụng, và lỗi này
chỉ lộ ra đúng vào lúc cần nó nhất.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `min-backoff` | 30s (< lease 90s) | **120s** (> lease) |
| `max-backoff` | 300s | 600s |
| `max-attempts` | 3 (= `JOB_MAX_ATTEMPTS`) | **5** (> 3, để tầng hàng đợi không cắt ngắn ngân sách thử lại của tầng ứng dụng) |
| `state` | PAUSED | **PAUSED** (không đổi) |

Phần còn lại đạt: `containerConcurrency=1` (đúng cho việc nặng CPU),
`maxScale=3` khớp `maxConcurrentDispatches=3`, `minScale=0` (thu về không),
cpu-throttling mặc định là đúng vì mọi việc nằm trong request, IAM chỉ có
`tts-tasks-invoker` giữ `roles/run.invoker`.

**Hai điều cần làm trước bước 3, KHÔNG làm đêm nay** (đều là thay đổi IAM):
- Service chạy bằng **service account mặc định của Compute** — rộng quyền hơn
  mức cần. Nên có SA riêng chỉ với `secretmanager.secretAccessor`.
- `timeoutSeconds=900`: chương rất dài có thể vượt; worker AWS không có trần này.

## 3. Job `tts-worker` cũ — chứng minh là trơ, không phải phỏng đoán

Không xoá được (deny rule `Bash(gcloud * delete*)` tại `.claude/settings.json:109`).
Nhưng đo được rằng **không gì có thể gọi nó**:

- **Cloud Scheduler API: CHƯA BẬT** trên project → không lịch nào tồn tại được.
- **Eventarc API: CHƯA BẬT** → không trigger sự kiện nào tồn tại được.
- Mọi execution của nó đều `runningCount=0`.

Nó chỉ chạy nếu có người gõ tay `gcloud run jobs execute`. Tôi **không** bật hai
API đó.

## 4. Khoá R2 production — đường không-root đã đóng, đo được

| Nguồn | Kết quả |
|---|---|
| `/etc/fanfic-audio/worker-prod.env` (AWS) | `root:fanfic 0640`; `ubuntu` không thuộc nhóm `fanfic`; `sudo` là deny tier-1 |
| Cổng `fanfic-prod-admin` | **không có verb đọc** — chỉ `status` (che giá trị) và `install-env` (chỉ GHI từ stdin) |
| Render `fas-prod-api` | **có** `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`, nhưng allowlist `RENDER_NON_SECRET_ENV` của broker chỉ cho đọc 3 toạ độ Appwrite — cố ý, và tôi không đi vòng |
| `CLOUDFLARE_API_TOKEN` (kho local) | **active**, thấy đúng account `a0084e…` — nhưng **403** ở cả `/r2/buckets` lẫn `/r2/api_tokens`: token **không có quyền R2 nào**. Và Cloudflare **không bao giờ** trả lại `secret_access_key` của khoá đã tạo — nó chỉ hiện một lần lúc tạo |

Kết luận: **không có đường an toàn, không-root nào**. Cần đúng một thao tác của
người có `root` — lệnh đã viết sẵn trong
`cloudrun-tts-canary-plan-2026-09-06.md`, giá trị không bao giờ hiện ra màn hình.

Tin tốt kèm theo: **không cần tạo token Cloudflare mới.**
`HeadBucket("fanfic-prod")` bằng khoá staging trả **403 chứ không phải 404** →
bucket nằm trong **cùng** tài khoản, nên `tts-r2-account-id` dùng lại y nguyên.
Chỉ thiếu **hai** giá trị.

## 5. Phía đẩy đã tắt ở tầng production thật

Đọc **tên** biến trên `fas-prod-api` (31 biến, giá trị không bao giờ đọc):
cả sáu biến `FAS_TTS_DISPATCH`, `FAS_TTS_TASKS_{QUEUE,LOCATION,PROJECT,TARGET_URL,OIDC_SA}`
đều **vắng mặt**. Nghĩa là phía enqueue tắt ở tầng triển khai thật, không chỉ
tắt trong mã nguồn.

## 6. Bằng chứng giám sát

Công cụ: `canh_dem.py` — chỉ đọc, mỗi mẫu tự kết luận `OK`/`LECH` theo kỳ vọng
tường minh, nên sáng ra chỉ cần đọc dòng `LECH`.

### ĐỘ PHỦ THẬT — có một khoảng mù, phải nói rõ

Tiến trình canh đêm **bị dừng** (`killed`) sau mẫu 3 lúc `16:48Z`, và điều đó
chỉ lộ ra khi hệ thống báo tác vụ nền kết thúc lúc `23:04Z`. Nghĩa là:

| Khoảng | Trạng thái giám sát |
|---|---|
| `16:27Z` – `16:48Z` | 3 mẫu, tất cả `OK` |
| `16:48Z` – `23:04Z` (**6h16m**) | **KHÔNG có mẫu nào** — khoảng mù |
| `23:04Z` trở đi | lấy mẫu lại, mỗi 10 phút |

**Không được đọc tài liệu này như thể đã giám sát liên tục 6 giờ.** Yêu cầu
"giám sát tối thiểu 6 giờ" **chưa** đạt trong đêm này.

Điều duy nhất nói được về khoảng mù là một phép đo **sau sự việc** lúc `23:04Z`:
mọi bất biến còn nguyên, và `completed=306 / failed=13 / pending=0 / running=0`
**giống hệt** lúc `16:48Z`. Không job production nào chạy trong khoảng đó — nên
khoảng mù không che giấu hành vi nào, đơn giản vì không có hành vi nào để che.
Đó là một sự an ủi, không phải một bằng chứng.

Bài học đã áp dụng ngay: chạy lại canh đêm theo **từng chặng ~3 giờ** thay vì
một tiến trình 7 giờ. Mỗi chặng kết thúc sẽ đánh thức phiên làm việc, nên một
lần bị dừng lộ ra sau vài giờ chứ không phải sau cả đêm.

Bất biến được kiểm mỗi 10 phút:
`/health` = `enabled:false` · `POST /tasks/tts` = `503` · queue = `PAUSED` ·
worker AWS = `active` · Appwrite health api/db/cache = `200` ·
lease treo = 0 · chương có >1 job = 0 · object `fanfic-staging` = 7 (không đổi).

`fanfic-prod` **không đọc được** từ phiên này (khoá chỉ có phạm vi staging) —
ghi rõ như vậy thay vì báo một con số không có cơ sở.

## 7. Không làm đêm nay (đúng yêu cầu)

Không canary, không bật dispatch, không đổi DNS/routing/IAM/billing, không sửa
dữ liệu production, không xoá tài nguyên production, không resize, không
Browser Operator, không refactor Router, không dọn dẹp ngoài phạm vi.

`git push` bị chặn cứng ở tầng runtime nên các commit nằm **local**, chưa push.

Ghi chú ngoài lề (**không** xử lý đêm nay, chỉ ghi để biết): GCE
`fanfic-worker-prod` đang **RUNNING** nhưng **không có unit fanfic nào active**
và không container nào — tức không phải worker trùng, chỉ là máy nhàn rỗi tốn
tiền. Hai VM `appwrite-extract-tmp`/`tmp2` cũng đang chạy và cũng 0 container.
`fanfic-appwrite-temp` (máy Appwrite theo tài liệu) thì **TERMINATED**, trong khi
`appwrite-dev.fanfic.world` vẫn phục vụ bình thường — nghĩa là origin thật hiện
không rõ nằm ở đâu, nên **CPU/RAM mức máy của Appwrite không quan sát được** từ
phiên này. Sức khoẻ Appwrite vì thế được đo bằng health API (api/db/cache) chứ
không phải bằng một con số bịa ra.
