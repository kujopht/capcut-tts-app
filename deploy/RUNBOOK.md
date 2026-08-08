# Runbook vận hành — staging

Mọi lệnh ở đây giả định biến môi trường đã được đặt cho **staging**, không phải
dev. Kiểm tra trước khi chạy bất cứ thứ gì:

```bash
python scripts/print_config.py      # in tiền tố định danh, KHÔNG in secret
```

---

## 1. Migration schema

Idempotent — chạy lại lúc nào cũng an toàn. Script **không có** thao tác xoá nào.

```bash
PYTHONPATH=. python scripts/setup_appwrite.py
```

Kết quả mong đợi ở lần chạy thứ hai trở đi: `tạo mới 0, bỏ qua (đã có) N`.

### ⚠️ Migration xong PHẢI restart backend và worker

`AppwriteMetadataStore._supported_fields()` dò xem collection thật sự có thuộc
tính nào rồi **nhớ trong suốt vòng đời tiến trình**. Tiến trình đang chạy sẽ
không bao giờ thấy trường vừa thêm — claim tiếp tục chạy ở nhánh **không nguyên
tử** mà không báo lỗi gì.

Đây là lỗi im lặng nguy hiểm nhất trong hệ thống. Không có cách nào phát hiện từ
bên ngoài ngoài việc nhớ restart.

---

## 2. Restart backend

```bash
# Render
render services restart fas-staging-api      # hoặc bấm "Manual Deploy" → "Restart"

# Cục bộ
# Ctrl+C rồi chạy lại; hoặc:
#   Windows: taskkill /PID <pid> /T /F
#   Linux:   kill <pid>
FAS_INLINE_WORKER=false python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

**Restart backend không ảnh hưởng job đang chạy** — job nằm ở tiến trình worker.
Đã kiểm chứng: giết web giữa lúc worker đang xử lý, job vẫn hoàn tất với
`attempts=1`.

Xác nhận sau khi restart:

```bash
curl -s $API/api/health | jq '{status, inline_worker, data_backend, storage_backend}'
curl -s -o /dev/null -w '%{http_code}\n' $API/api/ready     # phải là 200
```

`inline_worker` **phải** là `false`. Nếu là `true` thì web đang tự chạy job —
sai hình dạng của staging.

---

## 2b. Worker cục bộ cho staging gói Free

Gói Free của Render **không có Background Worker**, nên worker chạy trên máy bạn
và nối thẳng vào Appwrite/R2 staging. Backend trên Render không tham gia đường
này.

> Muốn worker chạy 24/7 mà không phụ thuộc máy cá nhân: xem
> **`deploy/RUNBOOK-WORKER.md`** — unit systemd cho VM Linux, tự lên sau reboot,
> tự restart khi crash, dừng sạch, và healthcheck theo lịch.

### Chuẩn bị `server/.env.staging` một lần

Tệp này **đã bị `.gitignore` chặn** (luật `.env.*`). Nội dung:

```
FAS_ENV=staging
FAS_INLINE_WORKER=false
DATA_BACKEND=appwrite
STORAGE_BACKEND=r2

APPWRITE_ENDPOINT=<endpoint staging>
APPWRITE_PROJECT_ID=<project id staging>
APPWRITE_DATABASE_ID=<database id staging>
APPWRITE_API_KEY=<api key staging>

R2_ACCOUNT_ID=<account id>
R2_BUCKET=<bucket staging>
R2_ACCESS_KEY_ID=<access key id>
R2_SECRET_ACCESS_KEY=<secret access key>
```

`FAS_CORS_ORIGINS` không cần: worker không phục vụ request nào.

### Chạy worker

**PowerShell** (Windows):

```powershell
cd C:\Users\robux\Documents\CapCut-TTS-App
$env:FAS_ENV_FILE = "server/.env.staging"
.\.venv\Scripts\python.exe -m server.worker --require-env staging
```

**bash** (macOS/Linux/Git Bash):

```bash
cd /duong/dan/CapCut-TTS-App
FAS_ENV_FILE=server/.env.staging ./.venv/bin/python -m server.worker --require-env staging
```

Kiểm nhịp ở một cửa sổ khác:

```powershell
$env:FAS_ENV_FILE = "server/.env.staging"
.\.venv\Scripts\python.exe -m server.worker --check
```

### `--require-env staging` là rào chắn, không phải trang trí

`server/config.py` mặc định nạp `server/.env` — tệp của máy phát triển, trỏ vào
tài nguyên **dev**. Quên `FAS_ENV_FILE` thì worker sẽ **lặng lẽ** xử lý job của
dev bằng credential dev, không có gì báo lỗi.

`--require-env staging` biến im lặng đó thành một lần dừng hẳn: tệp dev ghi
`FAS_ENV=development`, không khớp, worker thoát ngay với **mã 2** và in rõ lý do.

Thử chính xác điều đó trước khi tin:

```powershell
# KHÔNG đặt FAS_ENV_FILE — cố ý nạp nhầm tệp dev
.\.venv\Scripts\python.exe -m server.worker --require-env staging
# mong đợi: thoát mã 2, "dung_vi_sai_moi_truong"
```

### Lớp rào chắn thứ hai

`Settings.validate()` chặn cấu hình sai hình dạng: `FAS_ENV` là `staging` hoặc
`production` mà `FAS_INLINE_WORKER` vẫn bật → **dừng ngay khi khởi động**. Muốn
cố ý (chữa cháy tạm) phải đặt thêm `FAS_ALLOW_INLINE_WORKER_IN_REAL_ENV=true`.

Nhờ vậy backend trên Render không thể vô tình tự chạy job TTS rồi bị Render ngủ
giữa chừng.

### Khi tắt máy

Worker dừng, job đang chạy mất lease sau 90 giây. **Không mất dữ liệu**: job đã
bền vững trong Appwrite, và lần sau bật worker lên nó sẽ nhận lại đúng một lần.
Job mới tạo trong lúc worker tắt nằm `pending` cho tới khi có worker.

## 3. Restart worker

```bash
# Render
render services restart fas-staging-worker

# Cục bộ
FAS_INLINE_WORKER=false python -m server.worker
```

**Restart worker không làm web gián đoạn** — đã kiểm chứng: giết cưỡng chế
worker giữa chừng, web vẫn trả HTTP 200 ngay lập tức.

Job đang chạy lúc worker chết sẽ **không mất**: lease hết hạn sau 90 giây và
worker mới nhận lại. Đã đo: 2 claim cách nhau 126 giây, kết thúc đúng 1 track và
1 object.

Xác nhận worker sống:

```bash
python -m server.worker --check        # exit 0 = nhịp còn mới
```

### Dừng sạch

SIGTERM/SIGINT làm worker ngừng nhận job **mới**, rồi chờ job đang chạy kết thúc
trong `FAS_WORKER_GRACE_SECONDS` (mặc định 120 giây). Đặt giá trị này **dài hơn**
thời gian tổng hợp một chương dài thì không bao giờ bỏ job giữa chừng.

> Chưa kiểm chứng được trên Windows: Windows không gửi được tín hiệu dừng mềm
> cho tiến trình nền không có cửa sổ console. Phải xác minh trên host Linux của
> staging.

---

## 4. Chạy nhiều worker

Chạy thêm tiến trình `python -m server.worker`. Không cần cấu hình gì thêm.

Mỗi tiến trình có `WORKER_ID` riêng, và claim là compare-and-set thật (uniqueness
của `rowId` bên trong transaction), nên một job chỉ một worker thắng. Đã kiểm
chứng trên Appwrite thật: 5 lượt × 10 worker → đúng 1 worker thắng mỗi lượt.

---

## 5. Kiểm tra job kẹt

```bash
# Job đang running và lease của chúng
curl -s $API/api/jobs -H "Authorization: Bearer $TOKEN" \
  | jq '[.jobs[] | select(.status=="running")
         | {job_id, attempts, lease_owner, lease_expires_at, done_parts, total_parts}]'
```

Đọc kết quả:

| Dấu hiệu | Nghĩa là | Làm gì |
|---|---|---|
| `lease_expires_at` trong tương lai | worker đang sống và giữ job | **không làm gì** |
| `lease_expires_at` đã qua, `attempts < 3` | worker chết; worker khác sẽ nhận trong ≤ 90 giây | chờ một chu kỳ rồi xem lại |
| `lease_expires_at` đã qua, `attempts >= 3` | hết lượt thử | job sẽ thành `failed` kèm `worker_lost`; xem log worker tìm nguyên nhân |
| `done_parts` không nhích trong nhiều phút | worker treo, không chết | restart worker; lease hết hạn rồi worker mới nhận |
| Nhiều job `pending` mà không job nào `running` | **không có worker nào chạy** | kiểm tra `worker --check`; đây là hậu quả của `FAS_INLINE_WORKER=false` mà quên chạy worker |

**Tuyệt đối không** đánh dấu thủ công mọi job `running` thành `failed`. Job của
một worker đang chạy bình thường sẽ bị phá.

---

## 6. Chạy reconciler thủ công

```bash
# Chỉ đọc — an toàn, chạy lúc nào cũng được
python scripts/reconcile_audio.py --json /tmp/doi-soat.json

# Hạ ân hạn để thấy object mới (vẫn chỉ đọc)
python scripts/reconcile_audio.py --grace-hours 0
```

Xoá cần **hai** cờ và chỉ chạy thủ công sau khi đã đọc báo cáo dry-run:

```bash
python scripts/reconcile_audio.py --delete --yes-really-delete --json /tmp/sau-khi-xoa.json
```

Chi tiết và cách đọc báo cáo: `deploy/reconcile-cron.md`.

---

## 7. Rollback

### 7a. Rollback mã nguồn

Staging deploy từ một SHA cụ thể của `feature/web-mvp`. Rollback = deploy lại SHA
trước đó.

```bash
git log --oneline -10 feature/web-mvp        # chọn SHA lành
# Render: Manual Deploy → chọn commit → Deploy
```

Rollback **cả ba** service về cùng một SHA. Frontend và backend lệch phiên bản
nhau là nguồn lỗi khó tìm.

### 7b. Rollback schema

Thay đổi schema duy nhất trong nhánh này là **cộng thêm**, không phá huỷ:

| Thêm gì | Rollback |
|---|---|
| Collection `job_claims` | xoá collection |
| `tts_jobs.lease_expires_at`, `.lease_owner`, `.attempts` (đều **optional**) | xoá ba thuộc tính |
| Index `status_lease_idx` | xoá index |

Không cần sửa mã: `_supported_fields()` sẽ tự thấy chúng biến mất và code quay về
nhánh không nguyên tử.

**Restart backend và worker sau khi rollback schema** — cùng lý do cache ở mục 1.

Không có dữ liệu người dùng nào trong `job_claims`; nó thuần tuý là sổ ghi chép
của bộ điều phối.

### 7c. Rollback về chế độ inline (khẩn cấp)

Nếu worker hỏng và cần web tự chạy job để không đứng hẳn:

```bash
# Đặt FAS_INLINE_WORKER=true trên service backend rồi restart
```

Đây là **biện pháp tạm**. Nó đưa lại đúng những vấn đề mà việc tách worker giải
quyết. Dùng để cầm cự, không phải để ở lại.

---

## 8. Việc TUYỆT ĐỐI không làm

- Chạy migration hoặc xoá object **tự động lúc service khởi động**. Startup chỉ
  được đọc.
- Đánh dấu **mọi** job `running` thành `failed` khi khởi động.
- Bật chế độ xoá của reconciler theo lịch tự động.
- Trỏ staging vào Appwrite project hoặc R2 bucket của dev/production.
- Đặt bất kỳ secret nào vào biến `NEXT_PUBLIC_*`.
- Chạy worker trong serverless request handler.
