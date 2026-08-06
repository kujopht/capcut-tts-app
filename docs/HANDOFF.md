# HANDOFF — Fanfic Audio Studio Web MVP

Cập nhật: 2026-08-06 · Branch `feature/web-mvp` · Mốc 4: **đã smoke-test
Appwrite + R2 thật**

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
6. **Client chỉ được ĐỌC trên Appwrite.** Quyền mức collection rỗng; document
   chỉ cấp `read` cho chủ sở hữu (`read("any")` thêm khi đã xuất bản). Mọi ghi
   đi qua backend bằng API key. Lý do và danh sách trường server-authoritative:
   `docs/APPWRITE_SCHEMA.md`.
7. **`server/.env` được nạp bằng `python-dotenv`** theo đường dẫn tính từ vị trí
   module, không theo thư mục làm việc. Biến trong môi trường tiến trình luôn
   thắng file. Bộ test chạy hermetic — `server/tests/__init__.py` ép mock/local
   nên không bao giờ chạm cloud thật.
8. **Có Protocol `MetadataStore` chính thức** trong `server/adapters.py`.
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
| 4 | Appwrite + R2 adapter, cấu hình, tài liệu | ✅ Xong, **đã kiểm chứng live** |

Tách bạch cho rõ:

| Hạng mục | Trạng thái |
|---|---|
| Adapter đã hiện thực | ✅ `AppwriteIdentityAdapter`, `AppwriteMetadataStore`, `R2StorageAdapter` |
| Automated/mock tests | ✅ Đạt toàn bộ, chạy offline |
| Runtime dependencies đã khai báo | ✅ `server/requirements.txt` (gồm `boto3>=1.34,<2.0`) |
| Live Appwrite/R2 verification | ✅ Đã chạy trên Appwrite Cloud 1.9.6 + R2, môi trường dev. Bảy lỗi phát hiện và đã sửa — xem "Live smoke test" |

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
  `test_env_loading.py` (nạp `.env`, thứ tự ưu tiên, fail-fast, hermetic),
  `test_profile_permissions.py` (quyền hai tầng, chống tự nâng tier/quota),
  `test_dependencies.py` (khai báo + import/startup verification)

**Web `web/`**
- Next.js 16 + TypeScript strict, giao diện tối
- `src/lib/api.ts` — lớp gọi backend đầy đủ kiểu
- Landing page, layout có skip-link và nhãn ARIA
- `tests/*.test.mjs` — **9 test** bảo vệ: không lộ secret, không hard-code endpoint

### Chưa làm — việc tiếp theo

1. **Bấm tay trên giao diện với backend cloud.** Mới kiểm qua API; chưa mở
   trình duyệt chạy `/library` → `/studio` với `DATA_BACKEND=appwrite`.
2. **Chương dài và nhiều job song song.** Mới thử chương ngắn, chạy tuần tự.
   Giới hạn 1.000.000 ký tự của thuộc tính `content` chưa chạm tới.
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
| `server/tests` | 182 test: 181 đạt, 1 bỏ qua |
| ↑ cùng bộ, chạy trong **venv sạch** cài từ `server/requirements.txt` | 181 đạt, 1 bỏ qua |
| Live Appwrite + R2 | Đạt — xem mục "Live smoke test" |
| `web` (`node --test`) | 10/10 đạt |
| `npx eslint .` | Sạch, exit 0 |
| `npx tsc --noEmit` | Sạch, exit 0 |
| `npx next build` | Thành công, 7 route |
| Vertical slice thật (mock/local) | Đăng ký → novel → chương → job Edge TTS → MP3 **45.936 byte** → idempotency tái dùng job → ẩn danh bị chặn 401 |
| Desktop | Không chạy lại — `desktop_app/` không bị sửa dòng nào |

Test bị bỏ qua là test kiểm tra **thông báo lỗi khi thiếu `boto3`**; nay `boto3`
đã nằm trong `server/requirements.txt` nên nó tự bỏ qua — đúng như thiết kế.

Venv sạch cũng xác nhận backend **không kéo theo PySide6** và nạp được 452 giọng.

## Mức độ kiểm chứng

Credential do **người vận hành** đặt trong `server/.env` (không được commit).
Repo này không chứa và không bao giờ được chứa secret thật.

### Ba mức độ khác nhau — đừng lẫn

| Mức | Nghĩa là gì |
|---|---|
| **Mock persistence** | `MockMetadataStore` chỉ sống trong **vòng đời tiến trình**. Khởi động lại backend là mất sạch novels/chapters/jobs. Không phải kho bền vững, chỉ để phát triển và kiểm thử. |
| **Appwrite adapter đã mock-test** | Test bằng **client giả lập**: đúng request, đúng payload, đúng chuỗi permissions. Không chạm mạng. |
| **Live Appwrite verified** | ✅ **Đã chạy** trên Appwrite Cloud 1.9.6 — xem mục "Live smoke test" ở trên. |
| **Live R2 verified** | ✅ **Đã chạy** — upload, `head`, `Content-Type`, presigned URL còn hạn/hết hạn, URL công khai bị chặn. |

**Chưa xác minh** (cần môi trường/việc khác):

- Hành vi ở **production**: chưa chạy với CORS production, chưa có domain thật.
- **Tải và đồng thời**: mới chạy tuần tự vài request, chưa test nhiều job song song.
- **Chương dài**: mới thử chương ngắn một đoạn; giới hạn 1.000.000 ký tự của
  thuộc tính `content` chưa chạm tới.
- **Giọng Piper cục bộ** qua backend web: chưa thử, và vẫn `commercial_ready: false`.
- **Dọn object mồ côi**: chưa có job quét (xem "Giới hạn đã biết").
- **Frontend đấu với backend cloud**: mới kiểm qua API, chưa bấm tay trên
  giao diện với `DATA_BACKEND=appwrite`.

## Live smoke test — ĐÃ CHẠY

Chạy trên Appwrite Cloud **1.9.6** (region `sgp`) và Cloudflare R2, môi trường
dev. Trước khi chạy: 0 collection, bucket 0 object.

### Bảy lỗi chỉ lộ ra khi chạy thật

| Lỗi | Triệu chứng | Bản sửa |
|---|---|---|
| `/v1` nhân đôi | Endpoint đã có `/v1`, code thêm `/v1/` nữa → mọi request nhận **trang 404 HTML** | `AppwriteSettings.api_base` chuẩn hoá một chỗ, nhận cả hai dạng |
| Session secret gửi như JWT | `Failed to verify JWT. Invalid token: Incomplete segments` → mọi route cần đăng nhập hỏng | Tạo session **kèm API key** (không kèm thì `secret` rỗng), gửi qua `X-Appwrite-Session`. Bỏ fallback `$id` |
| Cú pháp query cũ | `Invalid query: Syntax error` — Appwrite 1.5+ chỉ nhận JSON qua `queries[]` | Helper `q_equal`/`q_order_*`/`q_limit` dùng `json.dumps`; **đóng luôn lỗ query injection** |
| Trường tính toán | `Unknown attribute: "char_count"` (và `progress` cũng vậy) | `persistable()` tách hình dạng lưu trữ khỏi hình dạng API |
| `POST /v1/databases` 404 | Appwrite Cloud mới không cho tạo database qua API cũ | Kiểm tra tồn tại trước, báo rõ nếu thiếu |
| Setup script crash | `UnicodeEncodeError` trên console cp1252 của Windows | Ép UTF-8 cho stdout/stderr |
| Login trả 500 | `profile_from_token()` nằm ngoài `try` | Đưa vào `try` → 401 đúng nghĩa |

### Kết quả đã kiểm chứng

**Appwrite**: 5 collection, mọi thuộc tính `available`, đủ 11 index,
`documentSecurity: True`, **quyền collection `[]`**. Setup idempotent (lần 1 tạo
66; lần 2 tạo 0, bỏ qua 67). Đăng ký/đăng nhập/`/api/auth/me` đều 200; sai mật
khẩu, token bịa, thiếu token đều **401**.

**Phân quyền hai tài khoản A/B**: giả mạo `owner_id` không ăn · B không thêm
chương vào truyện A (403) · B không publish truyện A (403) · danh sách riêng
không lẫn · bản nháp không lọt thư viện công khai · nghe chương nháp: ẩn danh
401, người khác 403.

**Publish**: lưu thật trong Appwrite (`state: published`), quyền document đúng
`read("user:…")` + `read("any")`, **không** `update`/`delete`/`create` cho
client. Publish lại idempotent.

**R2**: object 27.504 byte, `Content-Type: audio/mpeg`, MP3 hợp lệ. Database chỉ
lưu object key, không byte nhị phân. Chủ sở hữu nhận **307** → presigned URL
`X-Amz-Expires=300`; URL còn hạn tải được đủ 27.504 byte, hết hạn → **403**;
URL công khai cố định **không** hoạt động. Quyền `audio_tracks` chỉ có `read`.

**Vòng đời TTS**: `pending` ghi vào Appwrite ngay khi tạo → `running` →
`completed` kèm `output_key`. Không đổi sang giọng khác.

**Sau restart backend**: novel, trạng thái `published`, chương, job `completed`,
`output_key`, audio metadata — còn nguyên. Phát audio vẫn được. Gửi lại cùng
nội dung + giọng + thiết lập → **idempotency tái dùng đúng job cũ**.

**Đường lỗi cũng tự kiểm chứng**: lần chạy đầu token R2 thiếu quyền ghi, job
chuyển `running → failed`, **không** có `completed`, **không** có `output_key`.
Đúng thiết kế — không báo thành công giả.

### Còn lại trong môi trường dev

Bucket còn **1 object** là audio của smoke test. Cố ý giữ: xoá sẽ để lại
metadata mồ côi trong Appwrite. Object thăm dò đã xoá. Dữ liệu thử trong
Appwrite (vài tài khoản, novel, chương) cũng giữ nguyên.

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
