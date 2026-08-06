# HANDOFF — Fanfic Audio Studio Web MVP

Cập nhật: 2026-08-06 · Branch `feature/web-mvp`

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

## Trạng thái các mốc

| Mốc | Nội dung | Trạng thái |
|---|---|---|
| 1 | Nền móng: `web/` + `server/`, mock adapter, healthcheck, landing | ✅ Xong |
| 2 | TTS service, job API, idempotency, test | ✅ Xong phần backend |
| 3 | Vertical slice giao diện | ⏳ Mới có landing page |
| 4 | Appwrite + R2 adapter thật, README | ❌ Chưa bắt đầu |

### Đã xong

**Backend `server/`**
- `config.py` — đọc env, không hard-code endpoint/secret, tự chọn mock khi thiếu credential
- `domain.py` — `Profile`, `Novel`, `Chapter`, `TtsJob`, `AudioTrack`; enum `PublishState`, `Tier`, `JobStatus`; đã chuẩn bị sẵn draft/published, quota, tier
- `adapters.py` — `MockIdentityAdapter` (băm mật khẩu kèm salt), `LocalStorageAdapter` (ghi file tạm rồi đổi tên), `MockMetadataStore` (kiểm tra quyền sở hữu ở mọi truy vấn)
- `tts_bridge.py` — bọc chunker + registry, ghép MP3 bằng ffmpeg, atomic rename, **không fallback giọng**
- `main.py` — auth, novels, chapters, jobs, stream audio, healthcheck
- `tests/test_api.py` — **26 test**, chạy offline hoàn toàn (pipeline TTS bị thay bằng bản giả lập)

**Web `web/`**
- Next.js 16 + TypeScript strict, giao diện tối
- `src/lib/api.ts` — lớp gọi backend đầy đủ kiểu
- Landing page, layout có skip-link và nhãn ARIA
- `tests/*.test.mjs` — **9 test** bảo vệ: không lộ secret, không hard-code endpoint

### Chưa làm — việc tiếp theo

**Mốc 3 (ưu tiên):** các trang còn thiếu trong `web/src/app/`
- `library/page.tsx` — danh sách truyện đã xuất bản
- `novels/[id]/page.tsx` — chi tiết + danh sách chương
- `chapters/[id]/page.tsx` — trình phát audio
- `login/page.tsx` — đăng nhập/đăng ký
- `studio/page.tsx` — Creator Studio: tạo novel/chương, chọn giọng, gửi job, theo dõi trạng thái
- Mỗi trang cần đủ loading / empty / success / error

**Mốc 4:** `AppwriteIdentityAdapter`, `R2StorageAdapter` (cần `boto3`), README hướng dẫn chuyển từ mock sang thật.

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
| `server.tests.test_api` | 26/26 đạt |
| `web` (`node --test`) | 9/9 đạt |
| `npx tsc --noEmit` | Sạch |
| `npx next build` | Thành công, 3 route tĩnh |
| Desktop | Không chạy lại — `desktop_app/` không bị sửa dòng nào |

## Bẫy đã gặp

- Heredoc trong bash nuốt mất một dấu gạch chéo: `\\b` thành `\b` (backspace) trong template literal JS. Viết file test bằng công cụ Write thay vì heredoc.
- Next.js 15.1.6 có CVE-2025-66478 — đã nâng lên 16.x.
- `MergeResult` của desktop dùng thuộc tính `.path`, không phải `.output_path`.
