# Triển khai — kiến trúc và lựa chọn nền tảng

Tài liệu này mô tả **ba workload tách rời** và cách chạy chúng. Nó cố ý **không**
khoá vào một nền tảng cụ thể: repo chưa từng chọn nền tảng nào, và việc chọn phụ
thuộc vào tài khoản của bạn.

> Lượt chuẩn bị này **chưa deploy**. Ba tài nguyên staging (Appwrite project,
> R2 bucket, hosting) cần credential mà môi trường hiện tại không có — xem
> `docs/reports/staging/BAO_CAO_STAGING.md` để biết chính xác các bước thủ công.

---

## Ba workload

| # | Workload | Chạy bằng | Kiểu tiến trình | Cổng |
|---|---|---|---|---|
| 1 | **Frontend** | `npm ci && npx next build && npx next start -p $PORT` | web, có HTTP | có |
| 2 | **Backend / API** | `python -m uvicorn server.main:app --host 0.0.0.0 --port $PORT` | web, có HTTP | có |
| 3 | **TTS worker** | `python -m server.worker` | **worker chạy dài**, không HTTP | **không** |

```
   trình duyệt
        │
        ▼
 ┌─────────────┐        ┌──────────────┐
 │  Frontend   │──HTTP─▶│ Backend/API  │
 │  (Next.js)  │        │  (FastAPI)   │
 └─────────────┘        └──────┬───────┘
                               │ đọc/ghi
                        ┌──────▼───────┐        ┌──────────────┐
                        │   Appwrite   │◀──────▶│  TTS worker  │
                        │  (metadata)  │  claim │  (dài hạn)   │
                        └──────────────┘        └──────┬───────┘
                        ┌──────────────┐               │ upload
                        │      R2      │◀──────────────┘
                        │   (audio)    │
                        └──────────────┘
```

Backend và worker **không nói chuyện trực tiếp** với nhau. Chúng phối hợp qua
Appwrite bằng claim nguyên tử (transaction + uniqueness của `rowId`). Nhờ đó:
thêm worker chỉ là chạy thêm tiến trình, không cần hàng đợi riêng, không cần
khoá ngoài.

### Vì sao worker phải là tiến trình riêng

`FAS_INLINE_WORKER=true` (mặc định) cho tiện lúc phát triển: web tự chạy job
trong thread nền. Ở staging/production điều đó sai:

- restart web là **giết job đang chạy giữa chừng**;
- một chương dài giữ thread hàng chục phút **trong tiến trình phục vụ request**;
- web và worker **không scale độc lập** được.

Recovery vẫn cứu được job (đã chứng minh live), nhưng "cứu được" không phải lý do
để thiết kế như vậy.

**Không bao giờ đặt worker vào serverless request handler.** Một request handler
bị giới hạn thời gian chạy và bị đóng băng giữa các lần gọi; lease sẽ hết hạn
giữa chừng và job xoay vòng vô ích. Worker phải là *background worker* /
*service* chạy liên tục.

---

## Biến môi trường — mỗi workload cần gì

Danh sách đầy đủ kèm mô tả: `server/.env.example` và `web/.env.example`.
Dưới đây là **ai cần gì**:

| Biến | Frontend | Backend | Worker | Loại |
|---|:--:|:--:|:--:|---|
| `NEXT_PUBLIC_API_BASE` | ✅ | — | — | công khai |
| `FAS_ENV` | — | ✅ | ✅ | cấu hình |
| `FAS_CORS_ORIGINS` | — | ✅ | — | cấu hình |
| `FAS_VAR_DIR` | — | ✅ | ✅ | cấu hình |
| `FAS_INLINE_WORKER` | — | ✅ (`false`) | ✅ (`false`) | cấu hình |
| `DATA_BACKEND` | — | ✅ | ✅ | cấu hình |
| `STORAGE_BACKEND` | — | ✅ | ✅ | cấu hình |
| `APPWRITE_ENDPOINT` | — | ✅ | ✅ | định danh |
| `APPWRITE_PROJECT_ID` | — | ✅ | ✅ | định danh |
| `APPWRITE_DATABASE_ID` | — | ✅ | ✅ | định danh |
| `APPWRITE_API_KEY` | — | ✅ | ✅ | **secret** |
| `R2_ACCOUNT_ID` | — | ✅ | ✅ | định danh |
| `R2_BUCKET` | — | ✅ | ✅ | định danh |
| `R2_ACCESS_KEY_ID` | — | ✅ | ✅ | **secret** |
| `R2_SECRET_ACCESS_KEY` | — | ✅ | ✅ | **secret** |
| `FAS_WORKER_POLL_SECONDS` | — | — | ✅ | cấu hình |
| `FAS_WORKER_GRACE_SECONDS` | — | — | ✅ | cấu hình |
| `FAS_WORKER_STALE_SECONDS` | — | — | ✅ | cấu hình |

**Chỉ `NEXT_PUBLIC_API_BASE` được phép đến trình duyệt.** Mọi biến
`NEXT_PUBLIC_*` đều nằm trong bundle và ai cũng đọc được.

Nếu nền tảng cho phép, hãy cấp **hai** credential Appwrite/R2 khác nhau cho
backend và worker, để thu hồi riêng được từng bên khi lộ.

### Fail fast

`Settings.validate()` chạy ngay khi import `server.main` và cả trong
`server/worker.py`. Chọn `DATA_BACKEND=appwrite` mà thiếu bất kỳ biến nào trong
bốn biến Appwrite → **dừng ngay**, không âm thầm lui về mock. R2 cũng vậy.
`FAS_INLINE_WORKER` nhận giá trị không hiểu được → dừng ngay, không lấy mặc định.

### Không để staging gọi nhầm tài nguyên production

1. Dùng **project Appwrite khác** và **bucket R2 khác**, không phải database/prefix
   khác trong cùng project — API key rò rỉ sẽ vượt qua mọi ranh giới mềm.
2. Credential staging chỉ được cấp quyền trên tài nguyên staging.
3. Sau khi deploy, kiểm tra `GET /api/health` và đối chiếu `appwrite_configured`
   / `storage_backend`, rồi xác nhận `APPWRITE_PROJECT_ID` bằng
   `scripts/print_config.py` (chỉ in **tiền tố** định danh, không in secret).
4. Đặt `FAS_ENV=staging` để phân biệt trong log và trong `/api/health`.

---

## Chạy cục bộ đúng hình dạng của staging

```bash
# Terminal 1 — backend, KHÔNG tự chạy job
FAS_INLINE_WORKER=false python -m uvicorn server.main:app --port 8000

# Terminal 2 — worker
FAS_INLINE_WORKER=false python -m server.worker

# Terminal 3 — frontend, production build
cd web && npx next build && npx next start --port 3000
```

Windows PowerShell:

```powershell
$env:FAS_INLINE_WORKER = "false"
.\.venv\Scripts\python.exe -m uvicorn server.main:app --port 8000
# cửa sổ khác, cũng đặt $env:FAS_INLINE_WORKER = "false"
.\.venv\Scripts\python.exe -m server.worker
```

`Procfile` ở thư mục này khai báo đúng ba tiến trình đó cho các nền tảng đọc
được Procfile.

---

## Health / readiness

| Thành phần | Liveness | Readiness |
|---|---|---|
| Frontend | `GET /` trả 200 | — (Next tĩnh, không phụ thuộc runtime) |
| Backend | `GET /api/health` — **không** chạm Appwrite/R2 | `GET /api/ready` — chạm cả hai, trả **503** khi hỏng |
| Worker | tiến trình còn sống | `python -m server.worker --check` — đọc tệp nhịp, thoát khác 0 nếu nhịp cũ |

`/api/health` cố ý **không** kiểm tra phụ thuộc: một sự cố tạm thời của Appwrite
không được làm nền tảng giết tiến trình web đang lành mạnh. Việc kiểm tra kết nối
thuộc về `/api/ready`.

Worker **không mở cổng HTTP**. Nó không phục vụ request; mở cổng chỉ để
healthcheck là thêm một thứ có thể hỏng mà không được gì. Nhịp ghi ra
`$FAS_VAR_DIR/worker/heartbeat.json`.

---

## So sánh nền tảng

Repo **chưa từng chọn** nền tảng nào — không có `Dockerfile`, `vercel.json`,
`render.yaml`, `fly.toml` hay `Procfile` trong lịch sử. Bảng dưới là khuyến nghị,
không phải quyết định đã chốt.

| Nền tảng | Frontend | Backend | Worker chạy dài | Đánh giá |
|---|---|---|---|---|
| **Render** | Static Site / Web Service | Web Service | ✅ **Background Worker** | Hỗ trợ thẳng cả ba kiểu; biến môi trường tách theo service; có gói miễn phí (worker thường cần gói trả phí) |
| **Fly.io** | Machine | Machine | ✅ process group | Linh hoạt, nhưng cần Dockerfile — repo chưa có và tôi chưa test build được (Docker không cài trên máy này) |
| **Railway** | service | service | ✅ service | Ba service trong một project, dễ; theo mức dùng |
| **Vercel** | ✅ xuất sắc | ⚠️ serverless | ❌ **không** | Không có tiến trình chạy dài. Dùng cho frontend thì tốt, nhưng backend + worker phải đặt nơi khác |

**Khuyến nghị: Render.** Nó là nền tảng duy nhất trong bảng hỗ trợ **cả ba** kiểu
workload một cách trực tiếp mà không cần Dockerfile, và "Background Worker" đúng
là hình dạng của `server/worker.py`. `render.yaml` mẫu nằm cùng thư mục này —
**chưa** được kiểm chứng vì chưa có tài khoản; hãy coi là điểm khởi đầu.

Nếu bạn muốn giữ frontend trên Vercel: được, nhưng backend và worker vẫn phải
nằm ở nơi có tiến trình chạy dài, và `FAS_CORS_ORIGINS` phải liệt kê đúng origin
của Vercel.
