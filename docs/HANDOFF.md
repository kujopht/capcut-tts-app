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

1. **Đối soát object / metadata.** Chưa có công cụ nào. Đường sinh object mồ
   côi là `create_track` hỏng sau khi upload xong; metadata mồ côi chỉ đến từ
   xoá ngoài hệ thống. Đo live hai lần đều 0 mồ côi, nên đây là việc phòng xa
   chứ chưa cấp bách. **Đang chờ chọn phương án** — xem "Xử lý mồ côi" bên dưới.
2. **Chương dài.** Giới hạn 1.000.000 ký tự của thuộc tính `content` chưa chạm tới.
3. **Tải cao.** Mới thử tối đa 5 job song song.
4. **Job kẹt ở `running`.** Worker chết giữa chừng thì chưa có cơ chế hồi phục.
5. Chưa có thanh toán, lịch sử nghe, trừ quota, moderation.

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
| `server/tests` | 327 test: 326 đạt, 1 bỏ qua |
| ↑ cùng bộ, chạy trong **venv sạch** cài từ `server/requirements.txt` | 181 đạt, 1 bỏ qua (đo ở mốc cũ) |
| Live Appwrite + R2 | Đạt — xem mục "Live smoke test" |
| `web` (`node --test`) | 115/115 đạt |
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
- **`_list()` không lật trang**, mà Appwrite mặc định chỉ trả 25 document → dữ liệu bị cắt âm thầm, không lỗi, không cảnh báo. `list_chapters` từng dính lỗi này: truyện trên 25 chương sẽ mất chương. Đã sửa bằng `_list_all()` (tự đặt `limit` + lật trang). Truy vấn nào có thể vượt 25 phải dùng `_list_all`, không dùng `_list`. Các truy vấn còn lại (`list_novels`, `list_jobs`) vẫn dùng `_list` — sẽ cắt ở 25 khi dữ liệu nhiều lên, **chưa sửa**.
- Next.js 15.1.6 có CVE-2025-66478 — đã nâng lên 16.x.
- `MergeResult` của desktop dùng thuộc tính `.path`, không phải `.output_path`.
