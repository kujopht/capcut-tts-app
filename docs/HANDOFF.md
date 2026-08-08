# HANDOFF — Fanfic Audio Studio Web MVP

Cập nhật: 2026-08-08 · Branch `feature/web-mvp` · HEAD `14f4a31`

Tài liệu này để một phiên khác tiếp tục được khi phiên hiện tại hết context.

## Trạng thái hiện tại — đọc mục này trước

| Hạng mục | Trạng thái |
|---|---|
| Repository | **PUBLIC** |
| Staging (Render) | **ĐÃ DEPLOY** commit `8001cfc`, cả API lẫn web đều Live |
| Nghiệm thu staging | **82/82 đạt** với `--web`, trên hạ tầng thật |
| CI của HEAD `14f4a31` | **XANH** |
| PR #1 → `main` | **CHƯA MERGE** |
| Production | **CHƯA DEPLOY** — chưa có môi trường production nào được dựng |

Phân biệt hai commit, vì chúng khác nhau và dễ nhầm:

* **`8001cfc`** — mã đang **chạy** trên staging. Toàn bộ kết quả nghiệm thu
  82/82 là của bản này.
* **`14f4a31`** — HEAD hiện tại. So với `8001cfc` nó **chỉ thêm tài liệu**
  (`docs/HANDOFF.md`, `deploy/RUNBOOK-WORKER.md`), không đụng một dòng mã thực
  thi nào. Vì vậy kết quả 82/82 vẫn áp dụng cho HEAD.

**82 hay 77?** 82 là tổng số kiểm tra khi chạy kèm `--web` (kiểm cả frontend).
Bỏ `--web` thì còn 77. Khác **số kiểm tra**, không phải khác kết quả.

**Chưa làm, để phase sau:**

* **Hạn mức TTS theo chu kỳ cho từng người dùng.** `Profile.tier` và
  `tts_characters_used` có trong domain nhưng chưa chỗ nào ghi. Xem mục "Hạn
  mức" bên dưới để biết cái gì *đã* có.
* **Chạy NghiTTS/Piper trên GPU đám mây (Modal hoặc tương đương).** Chưa khảo
  sát, chưa dựng gì. Hiện Ngọc Huyền chạy CPU trên laptop Windows.

## Bối cảnh

Desktop app đã hoàn thiện và có installer. Nay xây thêm nền tảng web dùng chung
pipeline TTS. Chưa có thanh toán, chưa có hạn mức theo người dùng.

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

1. ~~**Đối soát object / metadata.** Chưa có công cụ nào.~~ **ĐÃ CÓ** —
   `scripts/reconcile_audio.py`, mặc định dry-run; xem mục "Đối soát object audio
   mồ côi" bên dưới. Bối cảnh vẫn đúng: đường sinh object mồ côi là `create_track`
   hỏng sau khi upload xong, còn metadata mồ côi chỉ đến từ xoá ngoài hệ thống.
   Đo live vẫn 0 mồ côi cả hai chiều, nên công cụ này là để phòng xa và để đối
   soát định kỳ, không phải để chữa một sự cố đang xảy ra.
2. **Chương dài.** Giới hạn 1.000.000 ký tự của thuộc tính `content` chưa chạm tới.
3. **Tải cao.** Mới thử tối đa 5 job song song.
4. ~~**Job kẹt ở `running`.**~~ ĐÃ SỬA — xem "Worker recovery" bên dưới.
5. Chưa có thanh toán, lịch sử nghe, trừ quota, moderation.
6. **Chưa có project/bucket Appwrite riêng cho test.** E2E cô lập ở tầng dữ liệu
   (tài khoản mới + tiền tố `[E2E]` + đối chiếu ảnh chụp id trước/sau). Đủ cho MVP
   riêng tư; **phải có** trước khi hệ thống chứa dữ liệu người dùng thật.
7. **Chưa xoá được tài khoản test.** Không có route xoá tài khoản, nên tài khoản
   `@example.test` còn lại trong Appwrite Auth dù dữ liệu đã sạch.
8. **Reconciler chưa tự động.** Phải chạy tay, chưa có cron.
9. **Job chạy trong thread của tiến trình web.** Restart web là giết luôn worker.
   Recovery xử lý được (đã chứng minh live), nhưng deploy nhiều bản sao sẽ cần
   worker tách riêng.

## Biến môi trường

`server/.env` (chép từ `server/.env.example`) — **chỉ ở backend**:
`FAS_ENV`, `FAS_CORS_ORIGINS`, `FAS_VAR_DIR`, `FAS_ALLOW_UNVERIFIED_LOCAL_VOICES`,
`APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY`, `APPWRITE_DATABASE_ID`,
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`.

Appwrite chỉ bật khi đủ **cả 4** biến; R2 cũng vậy.

### Núm điều chỉnh — đều có mặc định dùng được, chỉ đụng khi có lý do đo được

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `FAS_LOCAL_VOICES` | `piper:ngochuyen` | Giọng chạy trên máy worker được phục vụ. Chuỗi **rỗng = tắt hết** |
| `FAS_PUBLIC_VOICE_LANGUAGES` | `vi` | Ngôn ngữ web phục vụ, khớp theo tiền tố. Chuỗi **rỗng = không giới hạn** |
| `FAS_MAX_CHAPTER_CHARS` | `100000` | Độ dài nội dung một chương |
| `FAS_MAX_ACTIVE_JOBS` | `3` | Job đang xếp hàng mỗi người |
| `FAS_JOB_LEASE_SECONDS` | `90` | Lease sống bao lâu nếu không gia hạn |
| `FAS_JOB_HEARTBEAT_SECONDS` | `30` | Chu kỳ gia hạn lease (lease phải ≥ 3 lần số này) |
| `FAS_WORKER_POLL_SECONDS` | `3` | Chu kỳ quét job của worker |
| `FAS_WORKER_GRACE_SECONDS` | `120` | Chờ job đang chạy khi dừng worker |

Hai biến đầu có ý nghĩa **ngược nhau** khi để rỗng, và đó là chủ ý: một bên là
danh sách cho phép (rỗng = không cho ai), bên kia là bộ lọc thu hẹp (rỗng =
không lọc gì).

`/api/health` báo ra `local_voices` và `public_voice_languages` để người vận
hành thấy ngay cấu hình đang có tác dụng, thay vì phải đoán.

`web/.env` — chỉ một biến công khai: `NEXT_PUBLIC_API_BASE`.

## E2E đầy đủ — ĐÃ CHẠY

Báo cáo chi tiết: **`docs/reports/e2e/BAO_CAO_E2E.md`**. Ảnh chụp ở
`docs/screenshots/e2e/`, báo cáo đối soát ở `docs/reports/e2e/*.json`.

Chạy trên **production build** (`next build` + `next start`), Chromium thật qua
Playwright, Appwrite + R2 + Edge TTS thật, **không stub** trong hành trình chính.

| Hành trình | Kết quả |
|---|---|
| A — Xác thực và phân quyền | ĐẠT 31/31 |
| B — Library, novel, chapter, validation | ĐẠT 27/27 + giao diện |
| C — Phân trang và N+1 | ĐẠT 19/19 |
| D — Studio và TTS | ĐẠT sau khi sửa 1 lỗi |
| E — Dấu vân tay và cảnh báo audio cũ | ĐẠT 21/21 |
| F — Recovery trong hành trình thực tế | ĐẠT 12/12 |
| G — Reconciler | ĐẠT (4 chế độ) |
| H — Responsive và bàn phím | ĐẠT (7 route × 2 viewport) |

Số request API (đã loại static/source map/HMR) — **không** tăng theo số bản ghi:

| Trang | 0 bản ghi | 26–27 bản ghi |
|---|---|---|
| `/library` | 4 | **4** |
| `/studio` | — | **5** |
| `/novels/{id}` (3 chương) | — | **2** |

`/library` với 27 audio phát **0** request `/api/audio/*/url` — presigned URL chỉ
sinh khi người dùng bấm nghe hoặc tải.

Hai lỗi thật đã sửa trong lượt này (kèm regression test đã kiểm chứng là hỏng trên
mã cũ):

1. **`/studio` kẹt ở "Đang xử lý"** sau khi tải lại trang giữa lúc job chạy —
   `activeJob` chỉ đặt trong hàm submit nên sau reload là `null`, vòng poll thoát
   ngay. Sửa ở `web/src/app/studio/page.tsx`; test ở
   `web/tests/e2e-regressions.test.mjs`.
2. **Tiêu đề chỉ gồm khoảng trắng** lọt qua rồi lưu thành `''` (trong khi `""` bị
   422). Sửa bằng `StringConstraints(strip_whitespace=True, ...)` ở
   `server/main.py`; test ở `server/tests/test_e2e_regressions.py`.

Dọn dẹp: 42 truyện / 42 chương / 42 job / 42 track / 41 object / 48 dòng
`job_claims` fixture đã xoá. Đối chiếu ảnh chụp trước-sau: **mất 0, sót 0** ở cả
sáu tập hợp — không đụng bản ghi nào có từ trước.

## Chuẩn bị staging — ĐÃ LÀM (nay đã deploy)

> **Ghi chú lịch sử.** Mục này viết khi staging chưa được deploy. Nay staging
> đã chạy `8001cfc` trên Render và nghiệm thu 82/82 — xem "Trạng thái hiện tại"
> ở đầu tài liệu. Phần dưới giữ nguyên vì nó mô tả *cách* mọi thứ được dựng.

Báo cáo đầy đủ: **`docs/reports/staging/BAO_CAO_STAGING.md`**.
Cấu hình và runbook: **`deploy/`**.

**TTS worker đã tách khỏi web.** Cờ `FAS_INLINE_WORKER` (mặc định `true`, giữ
nguyên hành vi cũ). Đặt `false` ở staging/production thì web **chỉ** phục vụ
request, còn `python -m server.worker` nhận job. Worker không sao chép logic —
nó gọi lại đúng `recover_stale_jobs()` → `claim_job()` → `_run_job()`.

Đã diễn tập trên Appwrite + R2 thật (fixture `[REHEARSAL]`, đã xoá sạch, đối
chiếu trước/sau: mất 0 sót 0):

| Kiểm tra | Kết quả |
|---|---|
| Web không chạy job khi đã tách | ĐẠT |
| Worker riêng nhận và chạy | ĐẠT (~3 giây) |
| **Restart web** giữa lúc worker chạy | ĐẠT — job hoàn tất, `attempts=1` |
| **Kill worker** → web gián đoạn? | ĐẠT — web trả 200 ngay |
| Lease còn hạn không bị giật | ĐẠT — worker mới bỏ qua 75 giây |
| Sau khi lease hết hạn thì nhận lại | ĐẠT — `attempts=2`, cách nhau 126 giây |
| Kết quả cuối | **1 track, 1 object** |

**Chưa kiểm chứng được:** dừng sạch bằng SIGTERM — Windows không gửi được tín
hiệu mềm cho tiến trình nền. Phải xác minh trên host Linux.

Hai lỗi thật tìm được trong lượt này, cả hai đều hỏng trên mã cũ:

1. **Worker nhận job rồi không chạy** — gộp "web có chạy job không" và "tiến
   trình này có chạy job không" vào một cờ, nên worker tự cấm chính mình rồi đốt
   `attempts` mỗi vòng quét cho tới khi job `failed` oan. Tách thành
   `settings.inline_worker` và `main._CAN_RUN_JOBS`.
2. **`delete_job` bỏ lại `job_claims`** — collection chỉ tăng không giảm; sau hai
   lượt kiểm thử còn hàng chục dòng mồ côi. Nay dọn ở cả hai store.

**Ba tài nguyên staging chưa tạo được** vì thiếu credential — API key Appwrite là
service key phạm vi project (`GET /v1/projects` → 401), credential R2 giới hạn
trong một bucket (`ListBuckets` → AccessDenied), và không có tài khoản/CLI
hosting nào. Các bước thủ công ở mục 8 của báo cáo staging.

**Branch protection cho `main`** — trước đây không bật được vì repo private cần
GitHub Pro (cả hai API đều trả 403). **Repo nay đã PUBLIC, nên rào này miễn phí
và bật được.** Chưa bật. Cấu hình đã soạn sẵn ở mục 9 của báo cáo; nên bật
trước khi merge PR đầu tiên vào `main`.

## Triển khai staging — ĐÃ DEPLOY (2026-08-08)

> **Ghi chú lịch sử.** Mục này viết lúc chưa có credential trên máy phát
> triển. Trở ngại đó đã qua: staging chạy `8001cfc`, cả `fas-staging-api-free`
> lẫn `fas-staging-web-free` đều Live, nghiệm thu 82/82. Phần dưới giữ nguyên
> làm bản ghi những gì đã chặn lúc đó.

Chi tiết: `docs/reports/staging/BAO_CAO_STAGING.md` mục 11–12.

Tài nguyên staging đã được tạo ở phía nhà cung cấp, nhưng **credential chưa có
trên máy phát triển**: `server/.env` vẫn trỏ vào **dev** (`print_config.py` cho
thấy tiền tố định danh trùng **dev**), không có `RENDER_API_KEY`, không CLI
Render/Cloudflare. Nên chưa chạy được migration staging, chưa deploy, chưa đọc
được URL/SHA của service.

**`deploy/render.yaml` đã validate**: 3 service, không secret viết sẵn, worker
không có `healthCheckPath`, cả hai service Python đặt `FAS_INLINE_WORKER=false`.

**`scripts/staging_smoke.py`** — smoke test một lệnh, chạy với bất kỳ bản triển
khai nào qua HTTP API công khai (không cần credential kho dữ liệu), tự dọn
fixture `[SMOKE]` trong `finally`:

```bash
PYTHONPATH=. python scripts/staging_smoke.py --api <URL backend> --web <URL frontend>
```

Đã chạy thử với backend + worker cục bộ dựng đúng hình dạng staging
(`FAS_INLINE_WORKER=false`, `FAS_ENV=staging`, Appwrite + R2 + Edge TTS thật):
**43/43 đạt**, `pending → running → completed`, file 553.248 byte, `attempts=1`.
Fixture đã xoá, đối chiếu trước/sau: mất 0, sót 0.

Một lỗi tự phát hiện và đã sửa: `rut_gon_url()` bản đầu chỉ bỏ query nên **in
nguyên host và đường dẫn presigned URL** — lộ R2 account id, tên bucket,
`owner_id`, `chapter_id`. Nay che cả host lẫn đường dẫn. Regression test 9 test,
**5 hỏng** trên bản cũ.

Cách đưa credential vào mà không phải dán vào chat: mục 12 của báo cáo staging.

## Staging gói FREE — không cần thẻ

**Blueprint Path nhập trên Render: `deploy/render.free.yaml`**

`deploy/render.yaml` (trả phí) giữ nguyên. Bản Free có **2 service** (`plan: free`),
**không** Background Worker — gói Free không hỗ trợ. Worker TTS chạy trên máy bạn:

```powershell
$env:FAS_ENV_FILE = "server/.env.staging"
.\.venv\Scripts\python.exe -m server.worker --require-env staging
```

Frontend **không** thể là Static Site: `output: 'export'` báo
`Page "/chapters/[id]" is missing "generateStaticParams()"`. Web Service gói Free
vẫn miễn phí và không phải sửa app.

Hai rào chắn chống trỏ nhầm tài nguyên: `--require-env` (worker thoát **mã 2**
nếu `FAS_ENV` lệch — bắt đúng lỗi quên `FAS_ENV_FILE` và nạp `server/.env` của
dev), và `Settings.validate()` chặn `FAS_ENV=staging` + `FAS_INLINE_WORKER=true`.

Một lỗi thật đã sửa: **worker sập khi log tiếng Việt** trên console cp1252 của
Windows. Nay ép UTF-8 lúc import.

Chi tiết: `docs/reports/staging/BAO_CAO_STAGING.md` mục 13.

## Kết quả kiểm thử gần nhất

| Bộ | Kết quả |
|---|---|
| `server/tests` | **641 test: 640 đạt, 1 bỏ qua** |
| `tests` (desktop) | **371/371 đạt** |
| Live Appwrite + R2 | Đạt — xem mục "Live smoke test" |
| `scripts/staging_smoke.py` trên staging THẬT | **82/82 đạt, `attempts=1`**, dọn sạch (77 nếu bỏ `--web`) |
| `web` (`node --test`) | **156/156 đạt** |
| `npx eslint .` | Sạch, exit 0 |
| `npx tsc --noEmit` | Sạch, exit 0 |
| `npx next build` | Thành công, 13 route |
| Vertical slice thật (mock/local) | Đăng ký → novel → chương → job Edge TTS → MP3 **45.936 byte** → idempotency tái dùng job → ẩn danh bị chặn 401 |
| Desktop | `desktop_app/` không bị sửa dòng nào; vẫn chạy lại để chắc |

Test bị bỏ qua là test kiểm tra **thông báo lỗi khi thiếu `boto3`**; nay `boto3`
đã nằm trong `server/requirements.txt` nên nó tự bỏ qua — đúng như thiết kế.

### Kiểm chứng trong venv sạch — ĐÃ CHẠY

Mục đích: xác nhận backend **không kéo theo PySide6** và `server/requirements.txt`
đủ để chạy — hai điều không bộ test nào trong venv phát triển kiểm được.

Venv đặt **ngoài working tree** để không có gói nào rò rỉ vào và không có file nào
lọt vào `git status`. Xoá `PYTHONPATH` để chứng minh không cần đường dẫn thủ công.

```powershell
# 1. Venv mới, ngoài repo
Remove-Item -Recurse -Force $env:TEMP\fas-clean-venv -ErrorAction SilentlyContinue
py -3.12 -m venv $env:TEMP\fas-clean-venv

# 2. Chỉ cài từ file requirements trong repo, không cài tay gói nào
& $env:TEMP\fas-clean-venv\Scripts\python.exe -m pip install --upgrade pip
& $env:TEMP\fas-clean-venv\Scripts\python.exe -m pip install -r server/requirements.txt
& $env:TEMP\fas-clean-venv\Scripts\python.exe -m pip list          # đối chiếu, phải không có PySide6

# 3. Chạy test — không đặt PYTHONPATH
$env:PYTHONPATH = $null
Set-Location C:\Users\robux\Documents\CapCut-TTS-App
& $env:TEMP\fas-clean-venv\Scripts\python.exe -m unittest discover -s server/tests -t . -v

# 4. Phía web (Node, không liên quan venv)
Set-Location web
npm ci
npm test
npx tsc --noEmit
npx eslint .
npx next build
```

Kết quả lần chạy gần nhất:

| Hạng mục | Kết quả trong venv sạch |
|---|---|
| Python | 3.12.10 |
| Gói cài từ `server/requirements.txt` | 39 gói, **không có PySide6**, không cài tay gói nào |
| `PYTHONPATH` | Rỗng — không cần đặt thủ công |
| `server/tests` | **577 test: 576 đạt, 1 bỏ qua** |
| `web` `npm test` | **152/152 đạt** |
| `npx tsc --noEmit` | exit 0 |
| `npx eslint .` | exit 0 |
| `npx next build` | Thành công |

Test bị bỏ qua vẫn là test thông báo lỗi khi thiếu `boto3` — nay `boto3` đã nằm
trong `server/requirements.txt` nên nó tự bỏ qua, đúng thiết kế.

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
- **Đối soát mồ côi**: chưa có công cụ (xem "Xử lý mồ côi").
- **Frontend đấu với backend cloud**: ✅ đã bấm tay 2026-08-07, xem
  "Kiểm tra thủ công trên giao diện".

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

### Kiểm tra thủ công trên giao diện — ĐÃ CHẠY

Người vận hành tự thao tác trên trình duyệt ngày **2026-08-07**, backend ở chế
độ `DATA_BACKEND=appwrite` + `STORAGE_BACKEND=r2`, web ở `localhost:3000`.
**Toàn bộ các bước đều đạt:**

| Bước | Nội dung |
|---|---|
| 1 | Đăng ký tài khoản mới trên `/login` (mật khẩu ≥ 8 ký tự theo yêu cầu Appwrite) |
| 2 | Đăng xuất rồi đăng nhập lại bằng chính tài khoản đó |
| 3 | Tạo truyện ở `/studio`, tiêu đề tiếng Việt có dấu → hiện nhãn **Bản nháp**, chưa lọt `/library` |
| 4 | Thêm chương, dán nội dung tiếng Việt → hiện số ký tự |
| 5 | Chọn giọng, gửi job TTS → trạng thái tự nhảy `pending` → `running` → `completed` |
| 6 | Bấm phát nghe được; tải MP3 về máy; **cửa sổ ẩn danh bị chặn** khi truyện chưa xuất bản |
| 7 | Xuất bản truyện → hiện trong `/library` → **cửa sổ ẩn danh nghe được** |

Đây là mảnh cuối cùng chưa tự động hoá được. Với nó, luồng đầu-cuối của Mốc 3
và Mốc 4 đã được kiểm chứng bằng **cả** API tự động **lẫn** thao tác người thật
trên backend cloud.

### Còn lại trong môi trường dev

Bucket còn **1 object** là audio của smoke test. Cố ý giữ: xoá sẽ để lại
metadata mồ côi trong Appwrite. Object thăm dò đã xoá. Dữ liệu thử trong
Appwrite (vài tài khoản, novel, chương) cũng giữ nguyên.

## Quyền đọc truyện nháp — ĐÃ SỬA

Trước đây `GET /api/novels/{id}` và `GET /api/chapters/{id}` **không kiểm tra
quyền gì cả**. Chỉ cần biết id là người lạ đọc được toàn bộ truyện chưa xuất bản
kèm nội dung mọi chương. Đo live: gọi không token trả về `200` với đủ 12 chương
của một truyện `draft`.

Quy tắc hiện tại, áp dụng cho **cả hai** route:

| Người gọi | Truyện `published` | Truyện `draft` |
|---|---|---|
| Khách vãng lai | 200 | **404** |
| Người dùng khác | 200 | **404** |
| Chủ sở hữu | 200 | 200 |
| Token hỏng/hết hạn | 200 | **404** (không phải 401) |

Trả `404` chứ không phải `403`: người lạ không cần biết truyện nháp đó tồn tại.
Token hỏng bị coi như chưa đăng nhập chứ không phải lỗi, để người hết phiên vẫn
đọc được truyện công khai như khách.

Chương không còn truyện cha (dữ liệu lẻ loi) thì chỉ chủ sở hữu đọc được — không
xác minh được trạng thái xuất bản thì chọn phía an toàn.

`GET /api/novels` (thư viện công khai) **không đổi**: vẫn chỉ liệt kê truyện đã
xuất bản. Bộ test khoá lại toàn bộ bảng trên ở
`server/tests/test_chapter_list_batching.py::TestReadAuthorization`.

## Tìm kiếm và phân trang — cú pháp truy vấn Appwrite

Ba điều đã đo trực tiếp trên Appwrite Cloud 1.9.6, đừng đoán lại:

| Việc cần làm | Cú pháp SAI | Cú pháp ĐÚNG |
|---|---|---|
| Lọc theo thẻ (`tags` là mảng) | `equal` → *Cannot query equal on attribute "tags" because it is an array* | `contains` |
| Tìm trong `title` | `search` → *Searching by attribute "title" requires a fulltext index* | `contains` |
| Tìm `title` HOẶC `description` | `or` với điều kiện lồng dạng **chuỗi JSON** → *Server Error* | `or` với điều kiện lồng dạng **đối tượng** |

`contains` **không phân biệt hoa/thường và không phân biệt dấu** — tìm `tac` ra
`Hải Tặc`. Rất tiện cho tiếng Việt, và có nghĩa là chưa cần index fulltext.

Phản hồi của Appwrite có `total` **độc lập với `limit`/`offset`**, nên biết được
còn trang sau hay không mà không phải đếm lại.

## Cảnh báo "audio cũ" — đo bằng mốc thời gian, không phải mã băm

`audio_outdated` so `chapter.updated_at` với `created_at` của track mới nhất.
Đây là cảnh báo **có thể**, không phải bằng chứng: sửa riêng tiêu đề cũng làm cờ
này bật, nên có thể báo oan.

Chọn hướng này có chủ đích: báo oan thì người dùng tốn một lần đọc cảnh báo; bỏ
sót thì người dùng tưởng audio đã khớp nội dung mới trong khi không phải — đúng
cái lỗi M4 đang sửa.

Muốn chính xác tuyệt đối thì phải lưu mã băm **của riêng nội dung** cùng track.
`AudioTrack.content_hash` hiện tại là dấu vân tay của nội dung + giọng + tốc độ +
kích thước đoạn (xem `job_fingerprint`), không tách ra được. Đó là thay đổi lược
đồ Appwrite, chưa làm.

Hai điều bắt buộc phải giữ:

- **Không so sánh hai mốc thời gian bằng chuỗi.** `now_iso()` sinh
  `...T03:01:36+00:00`, Appwrite trả `...T03:01:36.000+00:00`. So chuỗi thì `+`
  (0x2B) nhỏ hơn `.` (0x2E), nên bản không có mili giây luôn bị coi là sớm hơn.
  Dùng `_parse_iso()`.
- **`reorder_chapters` không được bump `updated_at`.** Sắp xếp lại không sửa nội
  dung; bump ở đó thì mọi chương đều bị báo "audio cũ" oan sau một lần kéo thứ tự.

### ĐÃ SỬA: so dấu vân tay, không so mốc thời gian

Cách đo bằng `updated_at` không bao giờ tắt được cảnh báo sau khi hoàn nguyên nội
dung, vì hoàn nguyên cũng làm mốc thời gian mới hơn. Nay:

`AudioTrack.content_hash` là `job_fingerprint(nội dung, giọng, tốc độ, kích thước
đoạn)`. Track không lưu `rate`/`chunk_chars`, nhưng **bản ghi job thì có** — và
`track.content_hash == job.content_hash`. Nên lấy hai tham số đó từ job
(`MetadataStore.job_settings`), tính lại dấu vân tay với nội dung **hiện tại**, rồi
so. Chính xác, và **không cần thêm thuộc tính Appwrite nào**.

Kiểm chứng live: sửa nội dung → cờ bật; hoàn nguyên đúng nguyên bản → cờ **tự
tắt**; sửa riêng tiêu đề → cờ không bật.

Bắt buộc dùng tham số **của chính track đó**, không dùng giá trị mặc định: một
track render ở `rate=1.5` mà đem so với `rate=1.0` sẽ bị báo cũ vĩnh viễn.

Cách dự phòng: job đã bị xoá (chương bị xoá sẽ dọn job) thì không tính lại được
→ quay về so mốc thời gian như cũ. Báo oan nhưng không bỏ sót. Track cũ **không
bị ghi lại hay xoá** để "nâng cấp".

Một lần `job_settings` cho **cả danh sách** chương, không phải một lần mỗi chương
— nếu không lại thành đúng cái N+1 đã bỏ đi.

## Worker recovery — job kẹt ở `running`

### State machine

```
(không có) ──create_job──► pending ──claim──► running ──► completed
                              ▲                 │  ▲
                              │                 └──┘ heartbeat mỗi 30 giây
                              │                 │
                              └── quét lại ─────┤ lease hết hạn
                                                └──► failed (hết lượt thử)
```

| Hằng số | Giá trị | Ý nghĩa |
|---|---|---|
| `JOB_LEASE_SECONDS` | 90 | lease sống bao lâu nếu không làm mới (`FAS_JOB_LEASE_SECONDS`) |
| `JOB_HEARTBEAT_SECONDS` | 30 | chu kỳ worker làm mới lease (`FAS_JOB_HEARTBEAT_SECONDS`) |
| `JOB_MAX_ATTEMPTS` | 3 | vượt thì `failed` với `error_kind = worker_lost` |
| `JOB_SWEEP_SECONDS` | 60 | chu kỳ quét; lần đầu chạy ngay lúc khởi động |

Lease phải dài **ít nhất gấp ba** chu kỳ nhịp. `server/main.py` cưỡng chế lúc nạp
module: sai thì tiến trình dừng ngay chứ không chạy với cấu hình tự phá. Một nhịp
trễ mạng không được làm job bị worker khác giật.

### Một job bị tổng hợp HAI LẦN — đã sửa (2026-08-08)

Quan sát trên staging: một job TTS duy nhất kết thúc với `attempts=2`. Không ai
bấm hai lần, không có worker thứ hai, job không thất bại lần nào.

Nguyên nhân gốc gồm **hai mảnh**, phải có cả hai mới xảy ra:

1. `claim_job` chỉ từ chối khi lease còn sống **và** thuộc về worker *khác*.
   Lease của chính mình thì nó cấp fence mới.
2. `recover_stale_jobs` quyết định dựa trên một lần đọc danh sách job qua
   Appwrite. Bản đọc đó trễ hơn lần claim vừa rồi vài giây, nên nó thấy "chưa ai
   giữ".

Ghép lại: bộ quét đọc phải ảnh cũ → hỏi `claim_job` → `claim_job` đồng ý vì
người hỏi chính là chủ lease → `attempts` lên 2 → **thread thứ hai gọi TTS cho
cùng một chương**.

Đo trực tiếp trên staging trước khi sửa:

```
claim lần 1 (worker A)                       -> fence=1
claim lần 2 (VẪN worker A, lease còn sống)   -> fence=2   ← lẽ ra phải là None
claim lần 3 (worker B, lease còn sống)       -> None      ← đúng
```

Vì sao không ai phát hiện sớm hơn: `output_key` tất định theo `content_hash` và
`create_track` là tìm-hoặc-tạo, nên kết quả **cuối cùng** vẫn đúng — một track,
một object. Chỉ có quota và thời gian bị đội lên.

Bốn thay đổi:

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `claim_job` khi lease còn sống | Từ chối worker khác, **cho phép chính chủ** | Từ chối tất cả, kể cả chính chủ |
| Heartbeat gia hạn lease | `save_job_fenced` với bản sao `TtsJob` cũ → **đập đè cả hàng** | `renew_lease` chỉ ghi `lease_expires_at` và `lease_owner` |
| Cờ `lost` khi mất quyền | Được đặt nhưng **không ai đọc** — vẫn upload, vẫn tạo track | Buông ngay trước khi chạm vào kho |
| `create_job` trên tiến trình không chạy job được | Vẫn nhận job → đốt `attempts`, giữ lease 90s vô ích | Hỏi `_CAN_RUN_JOBS` **trước khi** nhận |

Bản `save_job_fenced` cũ dùng làm heartbeat còn kéo `status` từ `running` lùi về
`pending` — đo được trên staging. Đó là hệ quả của việc ghi cả hàng từ một ảnh
chụp lúc khởi động thread.

Khoá lại bằng `server/tests/test_lease_hardening.py` (17 test). Bốn test trong
đó đỏ khi hoàn nguyên bản vá và xanh sau khi vá — đã kiểm chứng, không phải suy
đoán.

### Claim là CAS thật — bằng transaction của Appwrite

Ghi chú cũ ở đây nói "Appwrite không có compare-and-swap". **Sai.** Appwrite Cloud
1.9.6 có transaction, đã kiểm chứng trực tiếp bằng REST:

| Bước | Endpoint |
|---|---|
| Mở | `POST /v1/tablesdb/transactions` (`ttl` 60–3600 giây) |
| Dàn thao tác | `POST /v1/tablesdb/transactions/{id}/operations` |
| Chốt | `PATCH /v1/tablesdb/transactions/{id}` `{commit: true}` |

Ba điều đã đo được, không phải suy đoán:

- xung đột ghi-ghi trả **409**, nên transaction thua *không* commit được;
- uniqueness của `rowId` được cưỡng chế **bên trong** transaction;
- phần thao tác **bắt buộc dùng tên TablesDB** (`tableId`/`rowId`). Truyền
  `collectionId`/`documentId` bị từ chối 400 — dù phần còn lại của kho vẫn đi qua
  route tương thích `/v1/databases/.../documents`.

`AppwriteMetadataStore.claim_job()` gói **hai** thao tác vào một transaction:

1. `create` một dòng trong `job_claims` với `rowId = "{job_id}-{fence}"` — id tất
   định, nên hai worker cùng nhắm `fence` giống nhau sẽ đụng uniqueness;
2. `update` dòng job sang `running` với `attempts = fence`, `lease_owner`,
   `lease_expires_at`.

Kẻ thua thất bại ở bước 1 nên **cả** bước 2 cũng không xảy ra: không có chuyện
worker thua ghi đè lease của worker thắng. `claim_job` trả `None` và người gọi
**dừng hẳn** — không gọi TTS, không thử lại mù.

Trước khi vào transaction, `claim_job` đọc lại job và kiểm tra: chưa terminal,
lease đã hết hạn hoặc chính mình là chủ, chưa vượt `JOB_MAX_ATTEMPTS`.

**Fencing token = `attempts`.** Mọi lần ghi sau claim đi qua
`save_job_fenced(job, fence, worker_id)`; nếu `attempts` trong DB đã nhảy lên thì
lần ghi bị từ chối. Nhờ vậy một worker cũ hồi sinh không thể đánh dấu
`completed` đè lên lượt chạy mới. Heartbeat dùng cùng cơ chế và dựng cờ `lost`
khi mất fence, để vòng xử lý tự dừng. Có test đọc mã nguồn chặn việc gọi thẳng
`store.save_job(` trong `_run_job`.

### Tính đúng đắn vẫn KHÔNG chỉ dựa vào lease

Ngay cả khi claim hỏng, dữ liệu vẫn không sai, vì:

- `output_key` là tất định theo `content_hash` — hai lần chạy ghi cùng một khoá
  với cùng nội dung;
- `store.create_track()` là **tìm-hoặc-tạo** theo `(chapter_id, content_hash)`,
  nên không bao giờ sinh hai track cho cùng một kết quả.

Lease chỉ để tránh làm việc thừa. Đừng đổi `create_track` thành "luôn tạo mới" —
đó là thứ đang giữ cho recovery đúng đắn.

### Không bao giờ được làm

- Đánh dấu **mọi** job `running` thành `failed` lúc khởi động. Job của worker khác
  đang chạy bình thường sẽ bị phá.
- Cho bộ quét gọi công cụ đối soát. Hai việc tách rời hoàn toàn: bộ quét chỉ đổi
  trạng thái job, công cụ đối soát mới chạm vào file — và chỉ khi người vận hành
  truyền cờ.

### Schema `job_claims` — migration và rollback

`scripts/setup_appwrite.py` tạo:

| Collection | Thuộc tính | Chỉ mục |
|---|---|---|
| `job_claims` (mới) | `job_id`, `attempt`, `worker_id`, `created_at` | `job_idx` trên `job_id` |
| `tts_jobs` (bổ sung) | `lease_expires_at`, `lease_owner`, `attempts` — đều **optional** | `status_lease_idx` |

Ba thuộc tính thêm vào `tts_jobs` đều optional nên **tương thích ngược**: dòng cũ
không có chúng vẫn đọc được. `AppwriteMetadataStore._supported_fields()` dò một
lần xem collection thật sự có thuộc tính nào rồi nhớ lại, nên mã mới chạy được
trên schema **chưa** migrate — chỉ là chưa có claim nguyên tử.

**Rollback:** xoá collection `job_claims` và ba thuộc tính vừa thêm. Không cần
sửa mã: `_supported_fields()` sẽ tự thấy chúng biến mất. Không có dữ liệu người
dùng nào nằm trong `job_claims` — nó thuần tuý là sổ ghi chép của bộ điều phối.

> **Bắt buộc: đổi schema xong phải khởi động lại backend.**
> `_supported_fields()` cache theo **vòng đời tiến trình**. Một tiến trình đang
> chạy sẽ không bao giờ thấy trường vừa thêm, nên claim tiếp tục chạy ở nhánh
> không nguyên tử mà không báo lỗi gì. Cả migration lẫn rollback đều phải kèm
> một lần restart, và mọi phép đo E2E phải chạy trên tiến trình mới.

### Đã kiểm chứng thật

**Đua claim, 10 worker, trên Appwrite thật.** 5 lượt, mỗi lượt 10 tiến trình hẹn
nhau ở một mốc thời gian chung: **đúng 1 worker thắng mỗi lượt**, 9 worker còn
lại nhận `None` và dừng. Kiểm tra fencing riêng: worker cũ ghi `completed` với
fence hết hạn → bị từ chối, job vẫn `running`, `output_key` vẫn `None`.

**Hai tiến trình OS độc lập.** PID 41012 (`worker-A`) và PID 47044 (`worker-B`)
gọi `claim_job` tại cùng một mốc epoch: `worker-A` nhận `fence=1`, `worker-B`
nhận `null`.

**Kill worker giữ lease giữa lúc đang xử lý** (Appwrite + R2 thật, chương 31.200
ký tự chia 120 đoạn):

| Mốc | status | attempts | tiến độ | lease_owner |
|---|---|---|---|---|
| Trước khi kill | `running` | 1 | 6/120 | `43372-d9345909` |
| — | *kill `-Force` cả cây tiến trình* | | | |
| Sau khi worker thay thế nhận | `running` | 2 | 31/120 | `41784-9ebf1e3f` |
| Kết thúc | `completed` | 2 | 120/120 | `(trống)` — đã nhả |

Sổ `job_claims` của job đó có **đúng hai** dòng, cách nhau **297 giây** — dài hơn
lease 90 giây, tức worker thay thế chỉ nhận sau khi lease **thật sự** hết hạn,
không giật của worker còn sống. Kết quả cuối: **1 track** (12.942.957 byte) và
**1 object** trên R2. Fixture đã xoá sạch sau kiểm tra.

## Đối soát object audio mồ côi

`scripts/reconcile_audio.py` — **mặc định chỉ đọc**. Xoá cần **hai** cờ:
`--delete --yes-really-delete`.

`output_key` tất định: `audio/{owner_id}/{chapter_id}/{content_hash}.mp3`. Công
thức này phải khớp chính xác với `main._run_job` — có test đọc mã nguồn của
`_run_job` để hai chỗ không thể trôi nhau.

| Loại | Xử lý |
|---|---|
| có `audio_track` trỏ tới | để yên |
| khớp output key của job `pending`/`running` còn lease | **không bao giờ chạm** |
| mới hơn thời gian ân hạn (24 giờ) | để yên |
| còn lại | mồ côi — chỉ xoá khi có cả hai cờ |
| `audio_track` trỏ tới object không tồn tại | **chỉ báo**, đây là MẤT DỮ LIỆU |

Trước khi xoá từng object, kiểm tra tham chiếu **lại** một lần nữa: giữa lúc quét
và lúc xoá có thể vừa có job hoàn tất. Lỗi một object không làm mất báo cáo cả
lượt. Không tạo presigned URL nào.

Báo cáo dry-run đã khử dữ liệu nhạy cảm: `docs/reports/`.

## Giới hạn đã biết

**Chưa có transaction phân tán giữa kho file và kho metadata.** Job runner đi
theo thứ tự: tổng hợp → upload → tạo `audio_track` → lưu `completed`. Mỗi bước
hỏng đều đẩy job sang `failed` và xoá `output_key`.

| Bước hỏng | Job | Hệ quả còn lại |
|---|---|---|
| Tổng hợp giọng | `failed` | Không upload gì. Sạch. |
| Upload | `failed` | Không `audio_track`, không `output_key`. Sạch. |
| Tạo `audio_track` | `failed` | **Object mồ côi**: đã upload nhưng không metadata nào trỏ tới. Không route nào chạm được (đã kiểm chứng live) — chỉ tốn dung lượng. |
| Ghi `completed` | `failed` | `audio_track` **đã** tồn tại và trỏ tới object **thật** → chương vẫn phát được, nhưng job báo `failed`. Không mất dữ liệu, chỉ lệch trạng thái. |

Ưu tiên đã chọn: **thà báo `failed` còn hơn báo thành công giả.**

**Đính chính** (bản trước ghi sai): dòng "ghi `completed` hỏng" **không** sinh
object mồ côi, vì `create_track` đã chạy xong trước đó nên object vẫn được tham
chiếu. Đường sinh object mồ côi thật sự là **`create_track` hỏng**.

### Hạn mức — đã đặt (2026-08-08)

| Hạn mức | Giá trị | Biến | Cưỡng chế ở đâu |
|---|---|---|---|
| Độ dài nội dung chương | 100.000 ký tự | `FAS_MAX_CHAPTER_CHARS` | `ChapterIn` và `ChapterPatch` → 422 |
| Job đang xếp hàng mỗi người | 3 | `FAS_MAX_ACTIVE_JOBS` | `POST /api/jobs` → 429 |

Trước vòng này **không có hạn mức nào ở máy chủ**. `/studio` có rào 20.000 ký
tự nhưng đó là rào ở trình duyệt — gọi thẳng API là đi qua, và `/write` không
có rào nào cả. Trần duy nhất là cột `content` của Appwrite: 1.000.000 ký tự =
525 đoạn = vài tiếng CPU trên máy worker cho **một** lần bấm nút.

Trần job xếp hàng tính **theo từng người** và **không** chặn nhánh dùng-lại-job
-cũ (nhánh đó không tạo thêm việc cho worker). Nó là ràng buộc lịch sự, không
phải rào bảo mật — thứ thật sự bảo vệ máy worker là concurrency Piper bằng 1.

`web/src/lib/limits.ts` chép lại con số để giao diện báo trước;
`server/tests/test_limits.py` đọc chính file đó và so hai số, nên chúng không
trôi khỏi nhau được.

**Vẫn chưa có**: hạn mức TTS theo người dùng. `Profile.tier` và
`tts_characters_used` có trong domain nhưng **chưa chỗ nào ghi** — cần thêm
trường mốc chu kỳ vào schema Appwrite, tức là một lần migration. Đó là quyết
định sản phẩm (con số, chu kỳ, chuyện gì xảy ra khi chạm trần), chưa làm.

### Độ dài chương — số đo của chunker

`chunk_chars` mặc định 2000. Đo bằng `desktop_app.text_chunker.chunk_text`:
60.000 ký tự → 32 đoạn; 1.000.000 ký tự → 525 đoạn.

**Trần cứng duy nhất** là cột `content` của Appwrite: 1.000.000 ký tự
(`scripts/setup_appwrite.py`). Ngoài nó ra thì hiện **không có** giới hạn nào:

* `ChapterIn.content` không đặt `max_length`;
* `Profile.tier` và `tts_characters_used` đã có trong `server/domain.py` nhưng
  **chưa chỗ nào đọc tới** — không có hạn mức TTS theo người dùng;
* không có điểm nối lại giữa chừng: worker chết ở đoạn 400/525 thì lần chạy lại
  bắt đầu từ đoạn 1.

**Lease không còn là giới hạn** sau vòng làm cứng — nhịp gia hạn mỗi 30 giây
suốt thời gian tổng hợp. Có test: `test_lease_hardening.py::JobDaiHonLease`.

Đặt hạn mức là quyết định sản phẩm, chưa làm. Chi tiết ở
`deploy/RUNBOOK-WORKER.md` mục 8.

### Phạm vi giọng của web — chỉ tiếng Việt (2026-08-08)

Bản web hiện tại chỉ phục vụ **giọng tiếng Việt**: 27 giọng (CapCut 24, Edge 2,
Piper 1). Registry **vẫn giữ đủ 452 giọng** mọi thứ tiếng — desktop app dùng
chung registry đó. Cái bị thu hẹp là *phạm vi công bố của web*, qua
`FAS_PUBLIC_VOICE_LANGUAGES` (mặc định `vi`), nên mở lại ngôn ngữ khác chỉ là
đổi một biến.

Cưỡng chế **ở máy chủ**, không chỉ lọc ở frontend: `/api/voices` và
`POST /api/jobs` dùng cùng một vị ngữ. Gửi thẳng một `voice_id` nước ngoài →
400 kèm lý do đọc được, và không bao giờ tự đổi sang giọng Việt khác.

Worker **không** áp giới hạn ngôn ngữ — có chủ ý: job cũ đang `pending` từ
trước khi thu hẹp phạm vi vẫn phải chạy xong.

### Mục "Giọng đề xuất" — bảy giọng, lấy từ app desktop

| # | Tên hiển thị | `voice_id` | Provider |
|---|---|---|---|
| 1 | Cô Gái Hoạt Ngôn | `capcut:BV074_streaming\|7102355709945188865` | CapCut |
| 2 | Giọng Bé | `capcut:BV074_streaming_dsp\|7550087831092251920` | CapCut |
| 3 | Giọng Nữ Phổ Thông | `capcut:vi_female_huong\|7264854897953083905` | CapCut |
| 4 | Mai | `capcut:BV562_streaming\|7483736254694035984` | CapCut |
| 5 | Nhỏ Ngọt Ngào | `capcut:BV421_vivn_streaming\|7252594014782755330` | CapCut |
| 6 | Hoài My | `edge:vi-VN-HoaiMyNeural` | Edge TTS |
| 7 | Ngọc Huyền (mới) | `piper:ngochuyen` | Piper local |

**Nguồn chuẩn: `desktop_app/providers/recommended.py`** — backend đọc thẳng
`RECOMMENDED_CODES` từ đó, không gõ tay lại (có test cấm). Đối chiếu bằng mã ổn
định `(provider, engine_voice_id)`, **không** bằng tên hiển thị.

Lưu ý về `voice_id` CapCut: phần sau dấu `|` là `resource_id` lấy từ
`Voice.json`. Đổi `Voice.json` là đổi id — thêm một lý do nữa để đối chiếu bằng
mã ổn định chứ không phải bằng id đầy đủ.

Giao diện: hai mục trong **một** `<select>` (`optgroup`), nên chọn ở mục này
đồng bộ ngay với mục kia và không nhân bản bản ghi voice nào. Mặc định **vẫn là
Hoài My** — Ngọc Huyền chưa được đặt làm mặc định.

### Giọng Ngọc Huyền — đã probe thật trên máy này (2026-08-08)

| Hạng mục | Số đo |
|---|---|
| Nạp model (lần đầu) | 2,3 giây |
| RAM sau khi nạp | +121 MB (đỉnh tiến trình 182 MB) |
| Tổng hợp "Xin chào." | 126 ms ổn định (lần đầu 199 ms — có warm-up) |
| Audio ra | MP3 22050 Hz mono, 0,882 giây, rms 0,188 |
| Thiết bị | **CPU** — `onnxruntime` bản CPU, không CUDA |

12/12 kiểm tra đạt: model nạp được, Smart App Control **không** chặn
`espeakbridge.pyd`, audio có tiếng nói thật, tệp tạm được dọn.

Cưỡng chế: `FAS_LOCAL_VOICES` (mặc định `piper:ngochuyen`) **giao với** vũ trụ
NghiTTS suy từ catalog — không biến môi trường nào mở được một giọng cục bộ nằm
ngoài bộ đó. Thay cho cờ boolean bật-tắt-tất-cả cũ.

Concurrency Piper = **1 job**, khoá ở cấp job (`tts_bridge._PIPER_LOCK`).

`commercial_ready` đã đổi thành `public_enabled` — tên cũ là một phán đoán về
giấy phép, thứ máy chủ không biết. Chủ dự án đã cho phép công bố các giọng
NghiTTS và chịu trách nhiệm về quyền sử dụng.

### Bộ nghiệm thu nay phủ cả đường giọng cục bộ (2026-08-08)

`scripts/staging_smoke.py` lên **77 kiểm tra**, thêm ba mục:

| Mục | Bịt lỗ hổng gì |
|---|---|
| 6. Danh sách giọng | `/api/voices` chỉ tiếng Việt, đúng 7 giọng đề xuất đúng thứ tự, `piper:ngochuyen` có `runs_on_worker` |
| 7. Giọng ngoài phạm vi | gửi thẳng `edge:en-US-AriaNeural` → 400, và **không job nào được tạo** |
| 8. Giọng cục bộ | job Ngọc Huyền với `chunk_chars` nhỏ → **nhiều đoạn**, ép đường ghép ffmpeg chạy |

Mục 8 quan trọng hơn vẻ ngoài của nó: chương smoke cũ chỉ 3 câu = **một đoạn**,
nên `_concat_mp3` chưa bao giờ chạy. Một máy **thiếu ffmpeg vẫn cho 61/61 xanh**
rồi hỏng ở chương dài thật. Piper chạy cục bộ nên mục này không tốn quota.

Đã chạy trên **staging thật** (Render `8001cfc` + Appwrite + R2 + worker
laptop): **82/82**, job Ngọc Huyền `total_parts=2`, `attempts=1`, MP3 192 KB,
dọn sạch 2 chương / 2 track / 2 job / 2 object.

Tổng là 82 khi có `--web` (kiểm cả frontend) và 77 khi không — khác số kiểm
tra, không phải khác kết quả.

### Kiến trúc production — $0 cho MVP (2026-08-08)

```
Cloudflare Workers (Free)  →  Render Free Web Service  →  Appwrite prod + R2 fanfic-prod
   frontend Next.js/OpenNext      fas-prod-api                        ▲
                                                                      │ claim job
                                                       TTS worker trên LAPTOP
```

Chi tiết và lệnh: **`deploy/RUNBOOK-PRODUCTION.md`**. Blueprint:
`deploy/render.prod.yaml` — **một** service, `plan: free`.

| Thành phần | Nơi chạy | Phí |
|---|---|---|
| Frontend | Cloudflare Workers Free, qua `@opennextjs/cloudflare` | $0 |
| API | Render Free Web Service | $0 |
| TTS worker | laptop, `server/.env.production` | $0 |

**Vì sao frontend không xuất tĩnh:** `/novels/[id]` và `/chapters/[id]` nhận id
là dữ liệu người dùng lúc chạy; `output: 'export'` bắt mọi route động phải khai
`generateStaticParams()`. Đã thử thật và build dừng ở đúng lỗi đó.

**Đánh đổi đã chấp nhận:** API Free ngủ sau 15 phút (request đầu ~50 giây);
laptop tắt thì **không audio nào được tạo** — kể cả Edge/CapCut, vì mọi job đều
đi qua worker. API ngủ **không** làm dừng job đang chạy.

**Ngọc Huyền tắt trên production** (`FAS_LOCAL_VOICES=""`), còn 26 giọng Việt.
Bật lại sau khi worker laptop hoặc Modal được nghiệm thu — chỉ là biến môi
trường, không sửa mã.

**Hai worker trên cùng một laptop phải khác `FAS_VAR_DIR`**, nếu không chúng ghi
đè tệp nhịp của nhau và `--check` thành vô nghĩa.

### Worker 24/7 trên VM — đã chuẩn bị, CHƯA triển khai

`deploy/fanfic-worker.service` + `.env.example` + healthcheck timer + runbook
(`deploy/RUNBOOK-WORKER.md`). Bất biến của bộ tệp được khoá bằng
`server/tests/test_worker_deploy.py` — đáng kể nhất là `TimeoutStopSec` phải dài
hơn `FAS_WORKER_GRACE_SECONDS`, nếu không systemd sẽ SIGKILL đúng lúc worker
đang chờ job cuối kết thúc.

**Chưa chạy trên VM nào.** Cần quyền SSH, thông tin VM và URL clone — xem
`deploy/RUNBOOK-WORKER.md` mục 9.

Một cái bẫy đáng nhớ: **VM phải có ffmpeg**. Chương ra nhiều hơn một đoạn thì
`tts_bridge` ghép bằng ffmpeg. Chương một đoạn thì chỉ đổi tên tệp — nên
`staging_smoke.py` (chương 3 câu) sẽ **xanh trên một VM thiếu ffmpeg**.

**Metadata mồ côi** (`audio_track` trỏ tới object không tồn tại) **không sinh ra
từ bất kỳ đường nào trong code** — thứ tự upload → `create_track` bảo đảm điều
đó. Nó chỉ đến từ bên ngoài: xoá thủ công trên console R2, lifecycle rule hết
hạn, hoặc mất mát ở phía R2. Đo live hai lần đều cho **0 mồ côi cả hai chiều**.

Tiến độ từng đoạn (`done_parts`) chỉ giữ trong bộ nhớ, không ghi mỗi tick để
tránh làm ngập Appwrite. Worker chết giữa chừng sẽ để job kẹt ở `running` cho
tới khi có cơ chế hồi phục — cũng chưa làm.

## Xử lý mồ côi — đang chờ quyết định

**Chưa triển khai gì.** Ghi lại phân tích để chọn có căn cứ.

Mức độ cấp bách: **thấp**. Đo live hai lần đều 0 mồ côi cả hai chiều. Mỗi object
chỉ 15–47 KB, và object mồ côi **không route nào chạm tới được** (đã kiểm chứng)
nên chỉ tốn dung lượng, không phải vấn đề bảo mật.

| # | Phương án | Ưu | Nhược |
|---|---|---|---|
| 1 | **Không làm gì** | Không thêm dòng code nào → không thêm rủi ro. Không tốn độ trễ. | Không phát hiện được gì. Object mồ côi tích tụ âm thầm. Nếu object bị xoá ngoài hệ thống, người dùng thấy trình phát hỏng câm lặng. |
| 2 | **`HEAD` trước khi chuyển hướng** | Bắt đúng lúc đọc, trả 404 rõ ràng thay vì trình phát hỏng. | Thêm một round-trip R2 cho **mọi** lần phát (~50–150 ms) và gấp đôi số thao tác R2. **Tạo chế độ hỏng mới**: một cú `HEAD` trượt vì mạng chập chờn sẽ báo "không có audio" cho file hoàn toàn lành. Đổi "hiếm khi hỏng im lặng" lấy "thỉnh thoảng báo sai lúc bình thường". Không dọn được rác. |
| 3 | **Job quét đối soát + xoá** | Phát hiện cả hai chiều. Dọn được rác. Không đụng vào độ trễ đường đọc. | **Là phương án duy nhất XOÁ dữ liệu** → bán kính thiệt hại lớn nhất. Có race chết người: quét đúng lúc một job vừa upload xong mà `create_track` chưa chạy → tưởng mồ côi → **xoá mất audio thật**. Cần thêm code, lịch chạy và giám sát. |
| **3a** | **Đối soát CHỈ ĐỌC** (biến thể của 3) | Đọc thuần → gần như không có bán kính thiệt hại. Phát hiện đầy đủ cả hai chiều. Không đụng độ trễ. Là tiền đề bắt buộc cho bất kỳ bản tự xoá nào về sau. | Không tự dọn, phải người xử lý. Vẫn cần chỗ chạy định kỳ. |

**Khuyến nghị: 3a — đối soát chỉ đọc.**

Lý do: nó là phương án duy nhất *phát hiện được* mà **không** đánh đổi bằng rủi
ro mới. Phương án 2 mua sự rõ ràng bằng một chế độ hỏng mới trên đường nóng;
phương án 3 mua sự sạch sẽ bằng quyền xoá dữ liệu người dùng. Với hiện trạng 0
mồ côi và rác chỉ tốn vài chục KB, **quyền xoá chưa xứng với rủi ro nó mang lại**.

Nếu sau này muốn cho nó tự xoá, điều kiện tối thiểu:

1. Báo cáo chỉ-đọc phải chạy sạch một thời gian đủ dài để tin được.
2. Chỉ coi là mồ côi khi object **già hơn thời gian chạy job dài nhất** (ví dụ
   24 giờ) — chặn đúng cái race ở trên.
3. Chạy `--dry-run` trước, in ra đúng những gì sẽ xoá.
4. Không bao giờ xoá `audio_track`; metadata mồ côi phải do người xem xét, vì
   nó nghĩa là **đã mất dữ liệu** chứ không phải thừa dữ liệu.

## Bẫy đã gặp

- **Heredoc trong bash nuốt mất một dấu gạch chéo** — kể cả dạng đã trích dẫn `<<'EOF'`. Đã mắc hai lần: `\\b` thành `\b` (backspace), và `\\${cls}` thành `\${cls}` — mà `\$` trong template literal JS là **đô-la thoát**, nên regex biến thành chuỗi văn bản `${cls}` không bao giờ khớp, tức là một assertion rỗng. Viết file test bằng công cụ Write, đừng dùng heredoc. Và đừng ghép chuỗi vào `new RegExp` khi có cách so khớp trực tiếp.
- **Assertion phủ định dễ đạt vì lý do sai.** `!src.includes("api.getChapter(")` từng đạt cả trên code cũ, vì code cũ viết `api` xuống dòng rồi `.getChapter(`. Sau khi viết test mới, hãy chạy chính assertion đó lên bản code CŨ (`git show <commit>:<file>`) và xác nhận nó **thất bại** — không làm bước này thì không biết test có răng hay không.
- **`uvicorn --reload` bỏ sót thay đổi.** Đã gặp ba lần: WatchFiles in ra "detected changes... Reloading..." rồi worker không khởi động lại, backend tiếp tục phục vụ code cũ. Triệu chứng là API thiếu hẳn trường vừa thêm. Cách chắc ăn: dừng hẳn rồi chạy lại. Lưu ý tiến trình **con** có thể sống sót sau khi giết tiến trình cha và vẫn giữ cổng 8000 — phải giết cả cây.
- **Truy vấn `select` của Appwrite đặt thuộc tính dưới khoá `values`, không phải `attributes`.** Đặt sai thì Appwrite trả `Invalid query: No attributes selected`. Client giả lập trong test sẽ chấp nhận bất cứ hình dạng nào ta bịa ra, nên lỗi này chỉ lộ khi chạy thật — nay đã có test khoá lại ở `test_appwrite_protocol.py`.
- **`_list()` không lật trang**, mà Appwrite mặc định chỉ trả 25 document → dữ liệu bị cắt âm thầm, không lỗi, không cảnh báo. Truy vấn nào có thể vượt 25 phải dùng `_list_all`, không dùng `_list`. Đã rà soát và sửa **toàn bộ**: `list_chapters`, `chapters_for_owner`, `find_novels`/`list_novels`, `list_jobs`, `tracks_for_chapter`, `find_job_by_fingerprint`, `audio_by_chapter`, `job_settings`, `novel_tags`. Chỗ duy nhất còn dùng `_list` là bên trong chính `_list_all` và `track_for_chapter` (có `q_limit(1)` nên không thể bị cắt). Có test đọc mã nguồn từng phương thức bằng `inspect` để bắt hàm mới viết sai ngay từ đầu.
- **Kiểm giới hạn 25 ở tầng mock là vô nghĩa.** `MockMetadataStore` lọc bằng Python nên không bao giờ cắt. Test biên phải chạy ở tầng Appwrite với client giả lập **có mô phỏng giới hạn mặc định 25** — xem `_PagingRecorder` trong `test_appwrite_protocol.py`. Bộ test biên đầu tiên tôi viết chạy trên mock và đạt cả trên code còn lỗi.
- **`tracks_for_chapter` bị cắt là mất dữ liệu, không chỉ là hiển thị thiếu.** `_purge_chapter` dùng nó để lấy danh sách object cần xoá khỏi R2; cắt ở 25 thì track thứ 26 trở đi không bao giờ được xoá — object mồ côi âm thầm.
- Next.js 15.1.6 có CVE-2025-66478 — đã nâng lên 16.x.
- `MergeResult` của desktop dùng thuộc tính `.path`, không phải `.output_path`.
