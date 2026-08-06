# HANDOFF — Fanfic Audio Studio Web MVP

Cập nhật: 2026-08-06 · Branch `feature/web-mvp` · Mốc 4: **code xong, chưa
smoke-test cloud thật**

Tài liệu này để một phiên khác tiếp tục được khi phiên hiện tại hết context.

## Bối cảnh

Desktop app đã hoàn thiện và có installer. Nay xây thêm nền tảng web dùng chung
pipeline TTS. **Bản MVP riêng tư — chưa thương mại**, chưa có thanh toán, chưa
xác minh giấy phép cho giọng chạy cục bộ.

Checkpoint desktop: `15f215d`. Toàn bộ `desktop_app/`, `capcut_tts_api/`,
`app.py`, `build_app.bat`, `installer.iss` **không bị sửa** trong công việc web.

## Quyết định kiến trúc đã chốt

1. **Chưa tách `packages/tts_core`.** `server/tts_bridge.py` import trực tiếp
   `desktop_app`. Đã xác minh không kéo theo PySide6 — kiểm lại bằng:
   ```python
   import sys
   from desktop_app.providers.registry import build_default_registry
   assert not [m for m in sys.modules if "PySide6" in m]
   ```
2. **Adapter thay vì phụ thuộc cứng.** `server/adapters.py` định nghĩa
   `IdentityAdapter` và `StorageAdapter`. Thiếu credential thì dùng bản mock;
   có credential mà chưa cài adapter thật thì **báo lỗi rõ**, không âm thầm
   quay về mock.
3. **`signed_url()` có sẵn trong Protocol** để Mốc 4 chuyển sang R2 mà tầng
   trên không phải đổi.
4. **Idempotency theo `job_fingerprint(content, voice, rate, chunk_chars)`.**
   Job `failed` không được tái dùng.
5. **Mọi transition của TTS job đi qua một giao diện metadata duy nhất.**
   `store.create_job()` lưu `pending`; `store.save_job()` lưu `running`,
   `completed`, `failed`. Job runner **không bao giờ** gọi thẳng Appwrite.
   Chi tiết thứ tự và giới hạn: `docs/WEB_README.md` mục "Vòng đời TTS job".
6. **Có Protocol `MetadataStore` chính thức** trong `server/adapters.py`.
   `MockMetadataStore` và `AppwriteMetadataStore` cùng tuân theo một contract:
   kiểm quyền sở hữu ở phía server, `NotFoundError`/`PermissionDenied` thống
   nhất, và **ghi bền vững xong mới trả về**. Xuất bản truyện cũng đi qua đây:
   `store.publish_novel(novel_id, owner_id)`.

## Trạng thái các mốc

| Mốc | Nội dung | Trạng thái |
|---|---|---|
| 1 | Nền móng: `web/` + `server/`, mock adapter, healthcheck, landing | ✅ Xong |
| 2 | TTS service, job API, idempotency, test | ✅ Xong phần backend |
| 3 | Vertical slice giao diện | ✅ Đủ 5 trang, đã kiểm thử thật |
| 4 | Appwrite + R2 adapter, cấu hình, tài liệu | ⚠️ Code xong, **chưa smoke-test cloud thật** |

**Mốc 4 KHÔNG được coi là hoàn tất hoàn toàn.** Tách bạch cho rõ:

| Hạng mục | Trạng thái |
|---|---|
| Adapter đã hiện thực | ✅ `AppwriteIdentityAdapter`, `AppwriteMetadataStore`, `R2StorageAdapter` |
| Automated/mock tests | ✅ Đạt toàn bộ, chạy offline |
| Runtime dependencies đã khai báo | ✅ `server/requirements.txt` (gồm `boto3>=1.34,<2.0`) |
| Live Appwrite/R2 verification | ❌ Vẫn cần tài khoản và credential do **người vận hành** cấu hình ngoài source |

### Đã xong

**Backend `server/`**
- `config.py` — đọc env, không hard-code endpoint/secret, tự chọn mock khi thiếu credential
- `domain.py` — `Profile`, `Novel`, `Chapter`, `TtsJob`, `AudioTrack`; enum `PublishState`, `Tier`, `JobStatus`; đã chuẩn bị sẵn draft/published, quota, tier
- `adapters.py` — Protocol `IdentityAdapter` / `StorageAdapter` / **`MetadataStore`**; `MockIdentityAdapter` (băm mật khẩu kèm salt), `LocalStorageAdapter` (ghi file tạm rồi đổi tên), `MockMetadataStore` (kiểm tra quyền sở hữu ở mọi truy vấn, **chỉ tồn tại trong vòng đời tiến trình**)
- `tts_bridge.py` — bọc chunker + registry, ghép MP3 bằng ffmpeg, atomic rename, **không fallback giọng**
- `main.py` — auth, novels, chapters, jobs, stream audio, healthcheck; job runner lưu **mọi** transition qua metadata adapter; route publish gọi `store.publish_novel()` chứ không tự đổi object
- `requirements.txt` — phụ thuộc runtime của backend, tách khỏi `requirements-gui.txt`; **gồm `boto3>=1.34,<2.0`**
- `tests/` — chạy offline hoàn toàn (pipeline TTS bị thay bằng bản giả lập):
  `test_api.py`, `test_security.py`, `test_job_persistence.py` (vòng đời job),
  `test_publish_persistence.py` (xuất bản + permissions Appwrite bằng client giả lập),
  `test_dependencies.py` (khai báo + import/startup verification)

**Web `web/`**
- Next.js 16 + TypeScript strict, giao diện tối
- `src/lib/api.ts` — lớp gọi backend đầy đủ kiểu
- Landing page, layout có skip-link và nhãn ARIA
- `tests/*.test.mjs` — **9 test** bảo vệ: không lộ secret, không hard-code endpoint

### Chưa làm — việc tiếp theo

1. **Smoke test Appwrite thật.** Cần người vận hành tạo project, API key và
   database, rồi chạy `python -m scripts.setup_appwrite --dry-run` trước khi
   chạy thật. Phải xác minh: cú pháp query, hành vi document permission, giới
   hạn kích thước thuộc tính `content`.
2. **Smoke test R2 thật.** Bucket private, token S3-compatible. Phải xác minh
   presigned URL có phát được trực tiếp trong thẻ `<audio>` hay không.
3. **Dọn object mồ côi.** Chưa có transaction phân tán, nên khi ghi `completed`
   hỏng sau lúc upload, object vẫn nằm lại trong kho. Cần một job quét định kỳ.
4. Chưa có thanh toán, lịch sử nghe, trừ quota, moderation.

## Biến môi trường

`server/.env` (chép từ `server/.env.example`) — **chỉ ở backend**:
`FAS_ENV`, `FAS_CORS_ORIGINS`, `FAS_VAR_DIR`, `FAS_ALLOW_UNVERIFIED_LOCAL_VOICES`,
`APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY`, `APPWRITE_DATABASE_ID`,
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`.

Appwrite chỉ bật khi đủ **cả 4** biến; R2 cũng vậy.

`web/.env` — chỉ một biến công khai: `NEXT_PUBLIC_API_BASE`.

## Kết quả kiểm thử gần nhất

| Bộ | Kết quả |
|---|---|
| `server/tests` (api + security + job persistence + dependencies) | 87 test: 86 đạt, 1 bỏ qua |
| ↑ cùng bộ, chạy trong **venv sạch** cài từ `server/requirements.txt` | 86 đạt, 1 bỏ qua |
| `web` (`node --test`) | 10/10 đạt |
| `npx eslint .` | Sạch, exit 0 |
| `npx tsc --noEmit` | Sạch, exit 0 |
| `npx next build` | Thành công, 7 route |
| Vertical slice thật (mock/local) | Đăng ký → novel → chương → job Edge TTS → MP3 **45.936 byte** → idempotency tái dùng job → ẩn danh bị chặn 401 |
| Desktop | Không chạy lại — `desktop_app/` không bị sửa dòng nào |

Test bị bỏ qua là test kiểm tra **thông báo lỗi khi thiếu `boto3`**; nay `boto3`
đã nằm trong `server/requirements.txt` nên nó tự bỏ qua — đúng như thiết kế.

Venv sạch cũng xác nhận backend **không kéo theo PySide6** và nạp được 452 giọng.

## Chưa kiểm chứng với cloud thật

`AppwriteIdentityAdapter`, `AppwriteMetadataStore`, `R2StorageAdapter` và
`scripts/setup_appwrite.py` mới chỉ được test bằng client giả lập. Cần
credential thật để xác minh cú pháp query Appwrite, hành vi document
permission, và việc presigned URL của R2 có phát được trong thẻ `<audio>`.

Credential do **người vận hành** đặt trong `server/.env` (không được commit).
Repo này không chứa và không bao giờ được chứa secret thật.

### Ba mức độ khác nhau — đừng lẫn

| Mức | Nghĩa là gì |
|---|---|
| **Mock persistence** | `MockMetadataStore` chỉ sống trong **vòng đời tiến trình**. Khởi động lại backend là mất sạch novels/chapters/jobs. Không phải kho bền vững, chỉ để phát triển và kiểm thử. |
| **Appwrite adapter đã mock-test** | `AppwriteMetadataStore` được test bằng **client giả lập**: xác nhận đúng request, đúng payload `state`, đúng chuỗi permissions. Không hề chạm mạng. |
| **Live Appwrite verification** | ❌ **Chưa làm.** Cần tài khoản thật để xác minh Appwrite có thực sự áp `read("any")` như mong đợi, document permission có chặn đúng người lạ, và cú pháp query có khớp phiên bản đang chạy hay không. |

Nói riêng về **permissions khi xuất bản**: bộ test khẳng định adapter *gửi đi*
đúng chuỗi quyền (`read("any")` công khai, `update`/`delete` chỉ chủ sở hữu).
Việc Appwrite *thực thi* đúng chuỗi đó chỉ có thể kiểm chứng trên tài khoản thật.

## Giới hạn đã biết

**Chưa có transaction phân tán giữa kho file và kho metadata.** Job runner đi
theo thứ tự: tổng hợp → upload → tạo `audio_track` → lưu `completed`. Mỗi bước
hỏng đều đẩy job sang `failed` và xoá `output_key`.

| Bước hỏng | Job | Hệ quả còn lại |
|---|---|---|
| Tổng hợp giọng | `failed` | Không có gì được upload |
| Upload | `failed` | Không có `audio_track`, không có `output_key` |
| Ghi `completed` | `failed` | Object đã upload nằm lại làm rác; không bao giờ được công bố vì `output_key` bị xoá |

Ưu tiên đã chọn: **thà báo `failed` còn hơn báo thành công giả.** Rác ở dòng
cuối cần một job quét định kỳ để dọn — chưa làm.

Tiến độ từng đoạn (`done_parts`) chỉ giữ trong bộ nhớ, không ghi mỗi tick để
tránh làm ngập Appwrite. Worker chết giữa chừng sẽ để job kẹt ở `running` cho
tới khi có cơ chế hồi phục — cũng chưa làm.

## Bẫy đã gặp

- Heredoc trong bash nuốt mất một dấu gạch chéo: `\\b` thành `\b` (backspace) trong template literal JS. Viết file test bằng công cụ Write thay vì heredoc.
- Next.js 15.1.6 có CVE-2025-66478 — đã nâng lên 16.x.
- `MergeResult` của desktop dùng thuộc tính `.path`, không phải `.output_path`.
