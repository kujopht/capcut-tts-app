# Runbook — dựng production ($0 cho MVP)

Ba nơi, ba nhà cung cấp, **không tốn phí ở mức MVP**:

```
      Cloudflare Workers (Free)            ← frontend Next.js qua OpenNext
              │  HTTPS
              ▼
      Render Free Web Service              ← fas-prod-api (FastAPI)
              │
              ▼
      Appwrite production + R2 fanfic-prod
              ▲
              │ claim job
      TTS worker trên LAPTOP                ← không phải Render
```

**Staging tách hoàn toàn**: project Appwrite khác, bucket R2 khác, worker khác,
tệp env khác. Không thao tác nào dưới đây chạm tới staging.

> **Chưa deploy gì.** Tài liệu này là danh sách thao tác tay. Việc tạo service
> Render và deploy Cloudflare đều cần đăng nhập console — không có API nào làm
> thay được từ máy phát triển.

---

## 0. Đánh đổi đã chấp nhận

| Điều | Hệ quả |
|---|---|
| Render **Free** cho API | Service **ngủ sau 15 phút** không traffic; request đầu tiên sau đó mất ~50 giây |
| Worker chạy trên **laptop** | Không bật máy thì **không audio nào được tạo** — kể cả Edge/CapCut |
| **Ngọc Huyền tắt** trên production | Còn 26 giọng Việt (24 CapCut + 2 Edge) |

**API ngủ KHÔNG làm dừng job đang chạy.** Tạo job thì cần API thức
(`POST /api/jobs` đi qua nó), nhưng job đã vào hàng đợi thì worker nói chuyện
thẳng với Appwrite.

## 1. Nguyên tắc không được vi phạm

| Không bao giờ | Vì sao |
|---|---|
| Dùng chung **project** Appwrite với staging | Appwrite Auth quản lý user theo **project**. Dùng chung = tài khoản staging đăng nhập được vào production. |
| Dùng chung **bucket** R2 với staging | `reconcile_audio.py` có chế độ xoá và bộ nghiệm thu xoá object nó tạo. |
| Đặt `FAS_CORS_ORIGINS=*` | `Settings.validate()` **dừng ngay** — backend gửi kèm credentials. |
| Đặt secret vào `NEXT_PUBLIC_*` | Mọi biến `NEXT_PUBLIC_*` nằm trong bundle, ai cũng đọc được. |
| Để `FAS_INLINE_WORKER=true` | `validate()` dừng ngay. Service Free ngủ giữa chừng sẽ giết job. |
| Dùng chung `FAS_VAR_DIR` giữa hai worker | Hai worker ghi đè **tệp nhịp** của nhau; `--check` thành vô nghĩa. |

---

## 2. Tài nguyên đã có và đã xác minh

| Hạng mục | Trạng thái |
|---|---|
| Appwrite production | project riêng, đã dọn sạch |
| Schema | **khớp HEAD `main`** — không cần migration |
| Auth users / 6 bảng | **0** |
| R2 `fanfic-prod` | **0 object** |
| Cách ly | credential production **không** vào được bucket staging (403) |
| `server/.env.production` | đã có, `validate()` ĐẠT |
| `server/.env` (dev) | đã trỏ lại staging — không còn chạm production |

---

## 3. Frontend — Cloudflare Workers

### Vì sao không xuất tĩnh

`/novels/[id]` và `/chapters/[id]` nhận id là dữ liệu người dùng lúc chạy.
`output: 'export'` bắt mọi route động phải khai `generateStaticParams()`, mà id
không thể liệt kê lúc build. Đã thử thật, lỗi nguyên văn:

```
Error: Page "/chapters/[id]" is missing "generateStaticParams()"
so it cannot be used with "output: export" config.
```

Muốn xuất tĩnh thì phải đổi sang dạng query (`/novels?id=…`) — đổi URL công
khai, đổi liên kết, đổi test. Không làm. Vì vậy: **OpenNext trên Workers**.

### Tệp cấu hình

| Tệp | Vai trò |
|---|---|
| `web/open-next.config.ts` | Cấu hình adapter. Không khai cache/queue/tag — ứng dụng không dùng ISR |
| `web/wrangler.jsonc` | Worker: `nodejs_compat`, assets, `compatibility_date` khớp workerd |
| `web/package.json` | Thêm `cf:build`, `cf:preview`, `cf:deploy`, `cf-typegen` |

`npm run dev` **giữ nguyên** `next dev` — quy trình phát triển không đổi.

### Lệnh

```bash
cd web

# Xem thử tại chỗ (build + wrangler dev)
NEXT_PUBLIC_API_BASE=https://<url-api>.onrender.com npm run cf:preview

# Deploy thật
NEXT_PUBLIC_API_BASE=https://<url-api>.onrender.com npm run cf:deploy
```

PowerShell:

```powershell
cd web
$env:NEXT_PUBLIC_API_BASE = "https://<url-api>.onrender.com"
npm run cf:deploy
```

⚠️ `NEXT_PUBLIC_API_BASE` được **nướng vào bundle lúc build**, không đọc lúc
chạy. Đổi URL API thì phải **build lại**, restart không đủ. Đã kiểm: URL truyền
qua env xuất hiện đúng trong bundle, và không còn vết URL staging.

Lần đầu `wrangler` sẽ hỏi đăng nhập Cloudflare.

---

## 4. Backend — Render Free

Blueprint: **`deploy/render.prod.yaml`** (một service, `plan: free`).

Nhập Blueprint Path đó trên Render, rồi điền 9 biến `sync: false`:

| Biến | Giá trị |
|---|---|
| `FAS_CORS_ORIGINS` | URL Worker Cloudflare. **Không** wildcard |
| `APPWRITE_ENDPOINT` `APPWRITE_PROJECT_ID` `APPWRITE_DATABASE_ID` | từ `server/.env.production` |
| `APPWRITE_API_KEY` | **secret** |
| `R2_ACCOUNT_ID` `R2_BUCKET` | `R2_BUCKET` = `fanfic-prod` |
| `R2_ACCESS_KEY_ID` `R2_SECRET_ACCESS_KEY` | **secret** |

Có ràng buộc vòng: API cần URL Worker cho CORS, Worker cần URL API lúc build.
Thứ tự: **tạo API trước** (chưa cần CORS) → build/deploy Worker với URL API →
quay lại điền `FAS_CORS_ORIGINS` → **restart API**.

`autoDeploy: false` nên push không tự deploy — phải bấm **Manual Deploy**.

### Nếu muốn tạo tay thay vì Blueprint

New → Web Service → repo này → Branch `main` → Region `Singapore` → Runtime
`Python` → Plan `Free` →
Build `pip install -r server/requirements.txt` →
Start `python -m uvicorn server.main:app --host 0.0.0.0 --port $PORT` →
Health check path `/api/health` → rồi thêm 9 biến ở trên cộng bốn biến cố định:
`FAS_ENV=production`, `FAS_INLINE_WORKER=false`, `DATA_BACKEND=appwrite`,
`STORAGE_BACKEND=r2`, `FAS_LOCAL_VOICES=` (rỗng), `FAS_PUBLIC_VOICE_LANGUAGES=vi`.

---

## 5. TTS worker production trên laptop

Chạy **song song** với worker staging. Hai worker **không thể** lấy nhầm job
của nhau: mỗi worker chỉ nhìn thấy database mà env của nó trỏ tới, và hai môi
trường dùng hai project Appwrite khác nhau. Đó là cách ly thật, không phải quy ước.

### `FAS_VAR_DIR` bắt buộc phải khác

`HEARTBEAT_FILE = var_dir/worker/heartbeat.json`. Hai worker dùng chung thư mục
sẽ **ghi đè tệp nhịp của nhau** và `--check` trở nên vô nghĩa.

### Yêu cầu trên máy

* **ffmpeg trong PATH** — chương ra nhiều hơn một đoạn thì `_concat_mp3` ghép
  bằng ffmpeg. `_find_ffmpeg()` chỉ tra `shutil.which`, **không có biến môi
  trường nào trỏ đường dẫn**. Kiểm: `ffmpeg -version`.
* Phụ thuộc Python: `server/requirements.txt` (đã có trong `.venv`). Edge và
  CapCut không cần model cục bộ.
* **Không** cần `piper-tts`: Ngọc Huyền đang tắt trên production.

### Chạy (PowerShell)

```powershell
cd C:\Users\robux\Documents\CapCut-TTS-App

$env:FAS_ENV_FILE = "server/.env.production"
$env:PYTHONPATH   = "."
$env:FAS_VAR_DIR  = "C:\Users\robux\Documents\CapCut-TTS-App\server\var-production"

.\.venv\Scripts\python.exe -m server.worker --require-env production
```

`--require-env production` là rào chắn: nạp nhầm cấu hình staging thì worker
thoát ngay với **mã 2** thay vì lặng lẽ xử lý job của môi trường khác.

### Kiểm tra sức khoẻ (cửa sổ PowerShell khác)

```powershell
cd C:\Users\robux\Documents\CapCut-TTS-App

$env:FAS_ENV_FILE = "server/.env.production"
$env:PYTHONPATH   = "."
$env:FAS_VAR_DIR  = "C:\Users\robux\Documents\CapCut-TTS-App\server\var-production"

.\.venv\Scripts\python.exe -m server.worker --check
```

Mong đợi: `{"trang_thai": "dang_chay", "tuoi_nhip_giay": <nhỏ>, ...}`, mã thoát 0.

### Đối chiếu với worker staging

| | staging | production |
|---|---|---|
| `FAS_ENV_FILE` | `server/.env.staging` | `server/.env.production` |
| `--require-env` | `staging` | `production` |
| `FAS_VAR_DIR` | mặc định (`server/var`) | `server/var-production` |
| Appwrite project | staging | production |
| R2 bucket | `fanfic-staging` | `fanfic-prod` |

Dòng `khoi_dong` trong log phải có `environment=production`,
`inline_worker=false`, `chay_job_duoc=true`.

---

## 5b. Worker production trên Google Compute Engine

Thay cho worker laptop ở mục 5. VM: `fanfic-worker-prod`, `asia-southeast1-b`,
`e2-standard-2`, Ubuntu 24.04 Minimal.

### Cài

```bash
# 1. Tệp env — NGƯỜI VẬN HÀNH tự tạo. Script cài KHÔNG tạo, KHÔNG sửa.
sudo install -d -m 0750 /etc/fanfic-audio
sudo install -m 0600 /dev/null /etc/fanfic-audio/worker-prod.env
sudo -e /etc/fanfic-audio/worker-prod.env      # dán cấu hình production

# 2. Kiểm model (chỉ đọc)
/opt/fanfic-audio/.venv/bin/python   /opt/fanfic-audio/scripts/validate_nghitts_models.py   --models-dir /opt/fanfic-models/nghitts/piper-tts

# 3. Cài unit — KHÔNG khởi động
sudo /opt/fanfic-audio/scripts/install_gce_worker.sh --install-only

# 4. Chỉ khi thật sự muốn worker bắt đầu nhận job THẬT
sudo /opt/fanfic-audio/scripts/install_gce_worker.sh --enable-and-start
```

Bước 3 và 4 tách nhau có chủ ý: cài đặt là thao tác an toàn, còn khởi động
worker production nghĩa là nó bắt đầu **nhận job thật** và ghi vào Appwrite/R2
production.

### Kiểm tra

```bash
systemctl is-active fanfic-worker-prod && systemctl is-enabled fanfic-worker-prod
journalctl -u fanfic-worker-prod -n 30 --no-pager

sudo -u fanfic env PYTHONPATH=/opt/fanfic-audio   FAS_VAR_DIR=/var/lib/fanfic-audio-prod   /opt/fanfic-audio/.venv/bin/python -m server.worker --check
```

Dòng `khoi_dong` phải có `environment=production`, `inline_worker=false`,
`chay_job_duoc=true`.

### Đo tốc độ trên chính VM

```bash
/opt/fanfic-audio/.venv/bin/python /opt/fanfic-audio/scripts/benchmark_piper.py   --models-dir /opt/fanfic-models/nghitts/piper-tts --all --repeat 3   --json /tmp/bench.json
```

Không dùng hàng đợi production. Xem `docs/GCE-WORKER-CAPACITY.md`.

---

## 5c. Checklist bảo mật / vận hành cho worker VM

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| VM **không cần** inbound HTTP | ✅ theo thiết kế | Worker không mở cổng nào; nó chỉ gọi ra |
| **Không** mở 80/443 trên firewall | ⬜ bạn kiểm | Không có gì lắng nghe — mở là tăng bề mặt tấn công vô ích |
| Chạy dưới người dùng **không phải root** | ✅ `User=fanfic` | Người dùng hệ thống, `nologin`, không sudo |
| Secret **không** nằm trong repo | ✅ | `EnvironmentFile=/etc/fanfic-audio/worker-prod.env`; test cấm mọi `Environment=` mang secret |
| Quyền tệp env **0600** | ⬜ bạn đặt | Script cài chỉ **cảnh báo**, không tự sửa quyền tệp secret |
| Credential chỉ ở worker host | ⬜ bạn kiểm | Đừng chép `worker-prod.env` sang máy khác |
| Thư mục model **không** cho service ghi | ✅ | `ReadWritePaths` chỉ có StateDirectory; có test |
| Log **không** in secret | ✅ | `_ghi()` chỉ in định danh; `settings.describe()` chỉ có cờ boolean |
| SSH bằng khoá, không mật khẩu | ⬜ bạn kiểm | Mặc định của GCE |
| Không chạy service nào khác trên VM | ⬜ bạn kiểm | VM chỉ để chạy worker |

Nếu nghi ngờ log đã lộ gì:

```bash
journalctl -u fanfic-worker-prod --since '7 days ago' | grep -Ei 'key|secret|token|password'
```

Không ra gì là đúng.

---

## 6. Xác minh sau khi deploy — trước khi nghiệm thu

```bash
curl -s https://<url-api>.onrender.com/api/health
curl -s https://<url-api>.onrender.com/api/ready
```

| Trường | Bắt buộc | Sai thì nghĩa là |
|---|---|---|
| `environment` | `production` | Trỏ nhầm môi trường |
| `inline_worker` | `false` | Web đang tự chạy job |
| `data_backend` / `storage_backend` | `appwrite` / `r2` | Đang dùng kho giả |
| **`local_voices`** | **`[]`** | Ngọc Huyền vẫn được chào bán mà worker không có model |
| `public_voice_languages` | `["vi"]` | Sai phạm vi giọng |
| `/api/ready` → `status` | `ready` | Không nối được Appwrite hoặc R2 |

CORS — origin hợp lệ phải được chấp nhận, origin lạ phải bị chặn:

```bash
curl -s -o /dev/null -D - -X OPTIONS https://<url-api>.onrender.com/api/auth/login \
  -H "Origin: https://<worker>.workers.dev" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin

curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS https://<url-api>.onrender.com/api/auth/login \
  -H "Origin: https://ke-tan-cong.example" -H "Access-Control-Request-Method: POST"
```

Dòng đầu phải trả đúng origin Worker; dòng sau phải là **400**.

---

## 7. Nghiệm thu production — ĐỌC KỸ TRƯỚC KHI CHẠY

```bash
PYTHONPATH=. FAS_ENV_FILE=server/.env.production python scripts/staging_smoke.py \
  --api https://<url-api>.onrender.com \
  --web https://<worker>.workers.dev \
  --skip-local-voice
```

**Bộ này TẠO VÀ XOÁ dữ liệu thật** trong Appwrite/R2 production: 2 tài khoản,
1 truyện, 1 chương, 1 job TTS, 1 object. Nó tự dọn trong `finally`. Vì vậy chạy
**ngay sau khi deploy, TRƯỚC khi có người dùng thật**.

`--skip-local-voice` là bắt buộc khi Ngọc Huyền đang tắt.

> ⚠️ **Bước dọn tài khoản sẽ không chạy.** `don_tai_khoan()` chỉ xoá khi
> `FAS_ENV=staging` — rào chắn cố ý để không bao giờ xoá nhầm tài khoản
> production. Nó sẽ để lại **2 tài khoản `@example.test`**; phải xoá tay theo
> đúng ID mà bộ nghiệm thu in ra.

**`--skip-local-voice` bỏ qua bước duy nhất ép đường ghép ffmpeg chạy.** Nên
phải tự kiểm `ffmpeg -version` trên máy chạy worker.

---

## 8. Sau khi production xanh

* Gắn **fanfic.world**: thêm Custom Domain cho Worker trên Cloudflare, rồi cập
  nhật `FAS_CORS_ORIGINS` (Render) **và** `NEXT_PUBLIC_API_BASE` (build lại
  frontend). Chưa làm ở lượt này.
* **Thu hồi API key cũ** (tên `' cl'`, 105 scope) sau khi key production chạy ổn.
* Bật lại **Ngọc Huyền**: đổi `FAS_LOCAL_VOICES=piper:ngochuyen` sau khi worker
  laptop hoặc Modal được nghiệm thu. Chỉ là biến môi trường, không sửa mã.
* Reconciler: chạy tay, chế độ **chỉ đọc**, theo `deploy/reconcile-cron.md`.
