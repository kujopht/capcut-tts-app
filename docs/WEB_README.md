# Fanfic Audio Studio — Web & Backend

Nền tảng nghe audio tiểu thuyết. **Bản MVP kỹ thuật, dùng riêng — chưa thương mại.**
Chưa có thanh toán, và giọng đọc chạy cục bộ chưa xác minh giấy phép.

Phần desktop nằm ở `app.py` / `desktop_app/`; xem `CLAUDE.md`.

## Chạy nhanh ở chế độ mock

Không cần Appwrite hay Cloudflare. Mặc định đã là mock.

```bash
# Backend (cửa sổ 1)
.\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000

# Frontend (cửa sổ 2)
cd web
npm install
npm run dev            # http://localhost:3000
```

Kiểm tra nhanh: `curl http://localhost:8000/api/health` phải trả
`"data_backend": "mock"` và `"storage_backend": "local"`.

## Kiến trúc

```
Trình duyệt ──HTTP──▶ FastAPI ──▶ tts_bridge ──▶ desktop_app.providers
 (chỉ biết                (giữ mọi                ├─ capcut
NEXT_PUBLIC_API_BASE)     bí mật)                 ├─ edge
                             │                    └─ piper (cục bộ)
                             ├── IdentityAdapter ─▶ mock | Appwrite
                             └── StorageAdapter  ─▶ local | R2
```

Backend **không import GUI**. Kiểm lại bất cứ lúc nào:

```python
import sys
from desktop_app.providers.registry import build_default_registry
assert not [m for m in sys.modules if "PySide6" in m]
```

## Chọn backend — tường minh

Hệ thống **không tự đoán**. Bạn phải nói rõ muốn chạy chế độ nào.

| Biến | Giá trị | Ý nghĩa |
|---|---|---|
| `DATA_BACKEND` | `mock` (mặc định) | Danh tính + metadata trong bộ nhớ |
| | `appwrite` | Dùng Appwrite thật |
| `STORAGE_BACKEND` | `local` (mặc định) | Lưu file xuống `server/var/storage` |
| | `r2` | Cloudflare R2 |

Chọn chế độ cloud mà thiếu hoặc sai cấu hình thì backend **dừng ngay khi khởi động**
với thông báo rõ ràng — không bao giờ âm thầm quay về mock.

## Biến môi trường

### `server/.env` — toàn bộ là **server-only**

| Biến | Bắt buộc khi | Ghi chú |
|---|---|---|
| `FAS_ENV` | luôn | `development` \| `production` |
| `FAS_CORS_ORIGINS` | luôn | Production không được dùng `*` |
| `FAS_VAR_DIR` | tuỳ chọn | Mặc định `server/var` |
| `FAS_ALLOW_UNVERIFIED_LOCAL_VOICES` | tuỳ chọn | Mặc định chỉ bật ở development |
| `DATA_BACKEND` | luôn | `mock` \| `appwrite` |
| `STORAGE_BACKEND` | luôn | `local` \| `r2` |
| `APPWRITE_ENDPOINT` | `DATA_BACKEND=appwrite` | Có thể lộ ra client |
| `APPWRITE_PROJECT_ID` | ↑ | Có thể lộ ra client |
| `APPWRITE_API_KEY` | ↑ | **Bí mật — không bao giờ ra khỏi server** |
| `APPWRITE_DATABASE_ID` | ↑ | |
| `R2_ACCOUNT_ID` | `STORAGE_BACKEND=r2` | |
| `R2_ACCESS_KEY_ID` | ↑ | **Bí mật** |
| `R2_SECRET_ACCESS_KEY` | ↑ | **Bí mật** |
| `R2_BUCKET` | ↑ | Bucket phải **private** |

### `web/.env.local` — chỉ biến công khai

Chỉ có `NEXT_PUBLIC_API_BASE`. Mọi biến `NEXT_PUBLIC_*` đều nằm trong bundle và
ai cũng đọc được, nên **tuyệt đối không đặt credential ở đây**.

## Chuyển sang Appwrite

1. Tạo project, lấy endpoint và project ID.
2. Tạo API key ở phía server với quyền trên Databases và Users.
3. Điền bốn biến `APPWRITE_*` vào `server/.env`, đặt `DATA_BACKEND=appwrite`.
4. Tạo schema:
   ```bash
   .\.venv\Scripts\python.exe -m scripts.setup_appwrite --dry-run   # xem trước
   .\.venv\Scripts\python.exe -m scripts.setup_appwrite             # thực thi
   ```
   Script **idempotent** — chạy lại bao nhiêu lần cũng an toàn, đã có thì bỏ qua.
5. Khởi động lại backend. `/api/health` phải trả `"data_backend": "appwrite"`.

Chi tiết collection, thuộc tính, index và quyền: `docs/APPWRITE_SCHEMA.md`.

## Chuyển sang Cloudflare R2

1. Tạo bucket **private** — không bật public access.
2. Tạo API token S3-compatible, lấy access key và secret.
3. Điền bốn biến `R2_*`, đặt `STORAGE_BACKEND=r2`.
4. `pip install boto3` (chưa có sẵn trong venv).
5. Khởi động lại. `/api/health` phải trả `"storage_backend": "r2"`.

### Audio riêng tư được bảo vệ thế nào

- Database **chỉ lưu object key**, không bao giờ lưu dữ liệu nhị phân.
- `GET /api/audio/{chapter_id}` kiểm tra quyền **trước** khi trả bất kỳ byte nào:
  chương thuộc truyện đã xuất bản thì ai cũng nghe được; truyện nháp thì bắt buộc
  đăng nhập và phải đúng chủ sở hữu.
- Chỉ **sau khi** qua được kiểm tra đó, backend mới cấp URL ký hạn 5 phút (R2)
  hoặc stream trực tiếp (local).
- Không bao giờ trả URL công khai cố định.

## Smoke test

```bash
# 1. Backend sống và đang ở đúng chế độ
curl http://localhost:8000/api/health

# 2. Trọn vòng: đăng ký → novel → chương → job TTS → nghe
#    (cần backend đang chạy; sẽ gọi TTS thật)
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -t .
```

Kiểm tra thủ công trên giao diện: `/` → `/library` → `/login` → `/studio`
→ tạo truyện, thêm chương, chọn giọng, gửi job, chờ `completed`, bấm phát.

## Kiểm thử

```bash
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -t .   # backend
cd web && npm test          # web
cd web && npx eslint .      # lint
cd web && npx tsc --noEmit  # type-check
cd web && npx next build    # production build
```

## Giới hạn hiện tại — đọc kỹ

**"Adapter đã viết và test bằng mock" KHÔNG đồng nghĩa với "đã kiểm chứng trên
tài khoản cloud thật".**

Những phần sau mới chỉ được test với client giả lập, **chưa từng chạy với
credential thật**:

- `AppwriteIdentityAdapter` — đăng ký, đăng nhập, đọc hồ sơ
- `AppwriteMetadataStore` — novels, chapters, tts_jobs, audio_tracks
- `R2StorageAdapter` — upload, head, read, presigned URL
- `scripts/setup_appwrite.py` — chưa chạy lần nào với Appwrite thật

Khi có credential thật, cần kiểm chứng: cú pháp query của Appwrite, hành vi
document permission, giới hạn kích thước thuộc tính `content`, và việc R2
presigned URL có phát được trực tiếp trong thẻ `<audio>` hay không.

Ngoài ra: chưa có thanh toán, chưa có lịch sử nghe, chưa trừ quota, chưa có
moderation. Giọng Piper cục bộ bị đánh dấu `commercial_ready: false`.
