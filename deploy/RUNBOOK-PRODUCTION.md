# Runbook — dựng production (phương án C)

Production **không phụ thuộc máy cá nhân**: worker chạy trên Render. Giọng Piper
(Ngọc Huyền) **tắt** ở phiên bản này; còn 26 giọng Việt (24 CapCut + 2 Edge).

Staging **không bị đụng tới** ở bất kỳ bước nào dưới đây.

> **Chưa có gì được tạo.** Tài liệu này là danh sách thao tác tay. Việc tạo
> project Appwrite, bucket R2 và service Render đều cần đăng nhập console —
> không có API nào làm thay được từ máy phát triển.

---

## 0. Nguyên tắc không được vi phạm

| Không bao giờ | Vì sao |
|---|---|
| Dùng chung **project** Appwrite với staging | Appwrite Auth quản lý user theo **project**. Dùng chung = tài khoản staging đăng nhập được vào production. Database riêng **không** đủ. |
| Dùng chung **bucket** R2 với staging | `reconcile_audio.py` có chế độ xoá và bộ nghiệm thu xoá object nó tạo. Một lần chạy ở staging sẽ xoá nhầm object production. |
| Đặt `FAS_CORS_ORIGINS=*` | `Settings.validate()` **dừng ngay** — backend gửi kèm credentials nên wildcard là lỗ hổng, không phải tiện lợi. |
| Đặt bất kỳ secret nào vào `NEXT_PUBLIC_*` | Mọi biến `NEXT_PUBLIC_*` nằm trong bundle, ai cũng đọc được. |
| Để `FAS_INLINE_WORKER=true` | `validate()` dừng ngay. Restart web sẽ giết job đang chạy. |

---

## 1. Appwrite production

1. Console Appwrite → **Create project** (khác project staging). Vùng **sgp**
   cho khớp với Render region `singapore`.
2. Trong project mới → **Databases** → tạo database, ghi lại `databaseId`.
3. **Settings → API keys → Create API key**, scope tối thiểu:
   `users.read`, `users.write`, `sessions.write`, `databases.read`,
   `databases.write`, `collections.*`, `documents.*`.
4. Tạo schema — script **idempotent**, không có thao tác xoá nào:

   ```bash
   PYTHONPATH=. FAS_ENV_FILE=server/.env.production \
     python scripts/setup_appwrite.py
   ```

   Lần chạy thứ hai trở đi phải ra `tạo mới 0, bỏ qua (đã có) N`.

> ⚠️ **Sau migration PHẢI restart backend và worker.**
> `AppwriteMetadataStore._supported_fields()` nhớ schema theo **vòng đời tiến
> trình**. Tiến trình đang chạy sẽ không bao giờ thấy trường vừa thêm, và claim
> tiếp tục chạy ở nhánh **không nguyên tử** mà không báo lỗi gì. Đây là lỗi im
> lặng nguy hiểm nhất trong hệ thống.

## 2. R2 production

1. Cloudflare → R2 → **Create bucket**, ví dụ `fanfic-prod`. **Private**, không
   bật public access.
2. **Manage R2 API Tokens** → tạo token **chỉ có quyền trên bucket này**.
3. Ghi lại `account_id`, `bucket`, `access_key_id`, `secret_access_key`.

`account_id` **trùng** với staging là bình thường — một tài khoản Cloudflare
dùng chung account id cho mọi bucket. Cô lập nằm ở **bucket** và **token**.

## 3. `server/.env.production` (trên máy bạn, không commit)

Chỉ dùng để chạy migration và nghiệm thu từ máy phát triển. Render giữ bản của
riêng nó. `.gitignore` đã chặn `.env.*`.

```
FAS_ENV=production
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite
STORAGE_BACKEND=r2
FAS_LOCAL_VOICES=
FAS_PUBLIC_VOICE_LANGUAGES=vi

APPWRITE_ENDPOINT=
APPWRITE_PROJECT_ID=
APPWRITE_DATABASE_ID=
APPWRITE_API_KEY=

R2_ACCOUNT_ID=
R2_BUCKET=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
```

Kiểm không trỏ nhầm staging — lệnh này **chỉ in tiền tố**, không in secret:

```bash
FAS_ENV_FILE=server/.env.production PYTHONPATH=. python scripts/print_config.py
```

Đối chiếu `project_id` và `bucket` **phải khác** staging.

## 4. Render — ba service

Blueprint: **`deploy/render.prod.yaml`**. Nhập Blueprint Path đó trên Render,
rồi điền các biến `sync: false` ở giao diện.

| Service | Loại | Ghi chú |
|---|---|---|
| `fas-prod-api` | Web | `healthCheckPath=/api/health` |
| `fas-prod-worker` | **Worker** | không cổng, không healthcheck |
| `fas-prod-web` | Web | `rootDir: web` |

Thứ tự: **API trước** (để có URL) → điền `NEXT_PUBLIC_API_BASE` cho web và
`FAS_CORS_ORIGINS` cho API → worker lúc nào cũng được.

Cả ba đặt `plan: starter`, **không dùng Free**: service Free ngủ sau 15 phút và
request đầu tiên mất ~50 giây; gói Free cũng không có Background Worker.

## 5. ⚠️ ffmpeg trên worker — xác minh trước khi tin

Chương ra **nhiều hơn một đoạn** thì `_concat_mp3` ghép bằng `ffmpeg -c copy`.
Với `chunk_chars` mặc định 2000, gần như mọi chương thật đều nhiều đoạn. Thiếu
ffmpeg → job hỏng `MERGE_FFMPEG_MISSING`.

`_find_ffmpeg()` gọi `find_ffmpeg(None)`, và hàm đó **chỉ tra `shutil.which`**.
Không có biến môi trường nào trỏ đường dẫn ffmpeg — nó **bắt buộc** phải nằm
trên PATH của tiến trình worker.

**Kiểm trước, đừng đoán.** Render → `fas-prod-worker` → Shell:

```bash
which ffmpeg && ffmpeg -version | head -1
```

**Có** → không phải làm gì.

**Không có** → hai cách, cả hai ở tầng triển khai, **không sửa mã ứng dụng**:

* **Cách 1 — ffmpeg tĩnh trong buildCommand.** Đổi `buildCommand` của worker
  thành: cài requirements, tải một bản ffmpeg tĩnh vào `./bin`, rồi đổi
  `startCommand` thành `PATH="$PWD/bin:$PATH" python -m server.worker
  --require-env production`. Nhẹ nhất, nhưng thêm một lần tải từ nguồn ngoài
  vào quy trình build — hãy ghim URL và kiểm tổng kiểm tra.
* **Cách 2 — runtime Docker.** `runtime: docker` với một Dockerfile nhỏ
  `apt-get install -y ffmpeg`. Chắc chắn và tự chứa hơn, đổi lại build chậm
  hơn và thêm một tệp phải bảo trì.

Chọn cách nào cũng được, nhưng **phải chọn trước khi có người dùng thật** —
nếu không, chương ngắn thì chạy còn chương dài thì hỏng, và triệu chứng đó rất
dễ bị đọc nhầm thành lỗi TTS.

## 6. Xác minh sau khi deploy — trước khi chạy nghiệm thu

```bash
curl -s https://fas-prod-api.onrender.com/api/health
curl -s https://fas-prod-api.onrender.com/api/ready
```

Phải đúng **tất cả**:

| Trường | Giá trị bắt buộc | Sai thì nghĩa là |
|---|---|---|
| `environment` | `production` | Trỏ nhầm môi trường |
| `inline_worker` | `false` | Web đang tự chạy job |
| `data_backend` / `storage_backend` | `appwrite` / `r2` | Đang dùng kho giả |
| **`local_voices`** | **`[]`** | Ngọc Huyền vẫn được chào bán mà worker không có model → job sẽ `failed` sau 3 lần |
| `public_voice_languages` | `["vi"]` | Sai phạm vi giọng |
| `/api/ready` → `status` | `ready` | Không nối được Appwrite hoặc R2 |

Nếu `local_voices` trả `["piper:ngochuyen"]` thì Render đã bỏ qua biến rỗng —
đặt `FAS_LOCAL_VOICES=none` thay cho chuỗi rỗng rồi deploy lại (id không thuộc
bộ NghiTTS bị loại ở vòng lọc thứ hai, kết quả vẫn là rỗng).

Kiểm CORS **và** kiểm rằng origin lạ bị chặn:

```bash
curl -s -o /dev/null -D - -X OPTIONS https://fas-prod-api.onrender.com/api/auth/login \
  -H "Origin: https://fas-prod-web.onrender.com" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin

curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS https://fas-prod-api.onrender.com/api/auth/login \
  -H "Origin: https://ke-tan-cong.example" -H "Access-Control-Request-Method: POST"
```

Dòng đầu phải trả đúng origin của web production; dòng sau phải là **400**.

Kiểm bundle frontend không còn `localhost` — bộ nghiệm thu làm sẵn việc này.

## 7. Nghiệm thu production — ĐỌC KỸ TRƯỚC KHI CHẠY

```bash
PYTHONPATH=. FAS_ENV_FILE=server/.env.production python scripts/staging_smoke.py \
  --api https://fas-prod-api.onrender.com \
  --web https://fas-prod-web.onrender.com \
  --skip-local-voice
```

**Bộ này TẠO VÀ XOÁ dữ liệu thật** trong Appwrite/R2 production: 2 tài khoản,
1 truyện, 1 chương, 1 job TTS, 1 object. Nó tự dọn trong `finally`, kể cả khi
có bước hỏng. Vì vậy:

* chạy **ngay sau khi deploy, TRƯỚC khi có người dùng thật**;
* `--skip-local-voice` là bắt buộc ở phương án C — Ngọc Huyền đã tắt, không bỏ
  qua thì bước đó sẽ hỏng đúng như thiết kế. Tổng khi đó là **77** kiểm tra.

> ⚠️ **Bước dọn tài khoản sẽ không chạy.** `don_tai_khoan()` chỉ xoá khi
> `FAS_ENV=staging` — một rào chắn cố ý để không bao giờ xoá nhầm tài khoản
> production. Với `FAS_ENV=production` nó bỏ qua và **để lại 2 tài khoản
> `@example.test`**. Phải xoá tay theo đúng ID mà bộ nghiệm thu đã in ra.

**`--skip-local-voice` bỏ qua bước duy nhất ép đường ghép ffmpeg chạy.** Nên
mục 5 phải xong trước, nếu không 77/77 xanh vẫn chưa chứng minh được chương dài
tạo được audio.

## 8. Sau khi production xanh

* Bật reconciler ở chế độ **chỉ đọc** theo `deploy/reconcile-cron.md`. Không
  bao giờ bật xoá tự động trên production.
* Custom domain: chưa làm ở phase này.
* Ngọc Huyền: chờ phase Modal/GPU rồi mới bật lại `FAS_LOCAL_VOICES`.
