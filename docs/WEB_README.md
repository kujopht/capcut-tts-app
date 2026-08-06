# Fanfic Audio Studio — Web & Backend

Nền tảng nghe audio tiểu thuyết. **Bản MVP kỹ thuật, dùng riêng — chưa thương mại.**
Chưa có thanh toán, và giọng đọc chạy cục bộ chưa xác minh giấy phép.

Phần desktop nằm ở `app.py` / `desktop_app/`; xem `CLAUDE.md`.

## Chạy nhanh ở chế độ mock

Không cần Appwrite hay Cloudflare. Mặc định đã là mock.

```bash
# Backend (cửa sổ 1)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000

# Frontend (cửa sổ 2)
cd web
npm install
npm run dev            # http://localhost:3000
```

Phụ thuộc backend nằm ở **`server/requirements.txt`** — tách riêng khỏi
`requirements-gui.txt` của desktop để backend không kéo theo PySide6. File này
đã khai báo sẵn `boto3` (cần cho R2), nên **không phải `pip install` thủ công**
bất cứ gói nào. Ngoài Python, cần `ffmpeg` trong `PATH` để ghép MP3.

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
| `DATA_BACKEND` | `mock` (mặc định) | Danh tính + metadata trong bộ nhớ — **không bền vững**, khởi động lại là mất sạch |
| | `appwrite` | Dùng Appwrite thật |
| `STORAGE_BACKEND` | `local` (mặc định) | Lưu file xuống `server/var/storage` |
| | `r2` | Cloudflare R2 |

Chọn chế độ cloud mà thiếu hoặc sai cấu hình thì backend **dừng ngay khi khởi động**
với thông báo rõ ràng — không bao giờ âm thầm quay về mock.

## Biến môi trường

### Cấu hình được nạp thế nào

`server/config.py` nạp `server/.env` bằng đường dẫn tính **theo vị trí module**,
không theo thư mục làm việc — chạy từ repo root hay từ đâu cũng nạp đúng một
file. Không cần `--env-file` cho uvicorn, và `python -m scripts.setup_appwrite`
cũng thấy cùng cấu hình đó.

**Thứ tự ưu tiên: `shell / CI / production` > `server/.env`.** Biến đã có trong
môi trường tiến trình luôn thắng file (`override=False`), nên biến thật tiêm lúc
triển khai không bao giờ bị một file `.env` cũ ghi đè.

Không có file cũng không sao — backend chạy mock/local như thường. Muốn biết file
đã có tác dụng chưa: `GET /api/health` trả `"env_file_loaded": true`.

`FAS_ENV_FILE` có thể trỏ sang file khác; đặt chuỗi rỗng = không nạp file nào.
Bộ test dùng đúng cơ chế này để chạy hermetic, không bao giờ chạm cloud thật.

Việc nạp file **không làm mềm fail-fast**: đặt `DATA_BACKEND=appwrite` hay
`STORAGE_BACKEND=r2` mà thiếu biến vẫn dừng ngay khi khởi động.

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
4. `boto3` đã nằm trong `server/requirements.txt`; nếu venv được cài từ file đó
   thì không cần làm gì thêm. Kiểm nhanh:
   `.\.venv\Scripts\python.exe -c "import boto3"`
5. Khởi động lại. `/api/health` phải trả `"storage_backend": "r2"`.

### Audio riêng tư được bảo vệ thế nào

- Database **chỉ lưu object key**, không bao giờ lưu dữ liệu nhị phân.
- `GET /api/audio/{chapter_id}` kiểm tra quyền **trước** khi trả bất kỳ byte nào:
  chương thuộc truyện đã xuất bản thì ai cũng nghe được; truyện nháp thì bắt buộc
  đăng nhập và phải đúng chủ sở hữu.
- Chỉ **sau khi** qua được kiểm tra đó, backend mới cấp URL ký hạn 5 phút (R2)
  hoặc stream trực tiếp (local).
- Không bao giờ trả URL công khai cố định.

## Xuất bản truyện được lưu thế nào

`POST /api/novels/{id}/publish` đi trọn vẹn qua metadata adapter:
**`store.publish_novel(novel_id, owner_id)`**. Route không tự đổi thuộc tính của
novel — làm vậy thì bản mock "có vẻ" chạy được (dùng chung tham chiếu) còn
Appwrite sẽ mất trắng thay đổi.

- Chủ sở hữu **luôn** lấy từ token đã xác minh, không bao giờ từ body.
- Không tồn tại → 404. Không phải chủ sở hữu → 403. Chưa đăng nhập → 401.
- **Idempotent**: publish lại truyện đã xuất bản vẫn trả 200, không tạo bản ghi trùng.
- Ghi metadata hỏng → **502**, không bao giờ trả 200 với trạng thái chỉ tồn tại
  trong bộ nhớ tiến trình.

### Quyền trên Appwrite sau khi xuất bản

Appwrite cho phép PATCH cả `data` lẫn `permissions` trong **một request**, nên
thao tác là **nguyên tử** — không có cửa sổ mà trạng thái đã đổi còn quyền thì
chưa. Quyền được đặt thành:

| Phạm vi | read | create | update | delete |
|---|---|---|---|---|
| Chủ sở hữu (`user:<id>`) | ✅ | ❌ | ❌ | ❌ |
| Công khai (`any`) | ✅ | ❌ | ❌ | ❌ |
| Mức collection | — | ❌ | ❌ | ❌ |

**Client chỉ được đọc.** Mọi thao tác ghi đi qua backend bằng API key, và API
key bỏ qua document permission nên không mất chức năng nào. Bản nháp không có
`read("any")`. Mỗi lần publish đều áp lại quyền, nên quyền bị lệch vì một lần
sửa tay trên console Appwrite sẽ được lần publish sau tự chữa.

Lý do không cấp quyền ghi cho chính chủ sở hữu: người dùng nắm session/JWT hợp
lệ **gọi thẳng Appwrite API ngoài giao diện được**. Chi tiết từng trường
server-authoritative: `docs/APPWRITE_SCHEMA.md`.

API key chỉ nằm ở header của request phía server. Trình duyệt không bao giờ
nhận được credential nào.

## Vòng đời TTS job được lưu thế nào

Mọi transition đều đi qua **một giao diện metadata duy nhất** (`create_job` /
`save_job`). Job runner không bao giờ gọi thẳng Appwrite, nên bản mock và bản
Appwrite hành xử như nhau.

| Transition | Lưu ở đâu | Thời điểm |
|---|---|---|
| `pending` | `store.create_job()` | Ngay khi nhận request, **trước** khi khởi động worker |
| `running` | `store.save_job()` | **Trước** khi gọi tổng hợp giọng |
| `completed` | `store.save_job()` | **Sau** khi upload xong và đã gán `output_key` |
| `failed` | `store.save_job()` | Ngay khi tổng hợp, upload hoặc ghi metadata hỏng |

Thứ tự bắt buộc: **tổng hợp → upload → tạo `audio_track` → lưu `completed`**.
Trạng thái `completed` được **ghi bền vững trước, công bố trong bộ nhớ sau**, nên
một lần poll xen vào giữa cũng không thể thấy thành công chưa được lưu.

Tiến độ từng đoạn (`done_parts`) chỉ cập nhật trong bộ nhớ — ghi mỗi tick sẽ làm
ngập Appwrite mà không thêm giá trị nào.

**Giới hạn — chưa có transaction phân tán.** Kho file và kho metadata là hai hệ
thống tách rời. Nếu ghi `completed` hỏng ngay sau khi upload xong, job sẽ thành
`failed` còn object đã upload vẫn nằm lại trong kho. Đó là rác vô hại: `output_key`
bị xoá nên nó không bao giờ được công bố. Đổi lại là **không bao giờ báo thành
công giả**. Dọn rác này cần một job quét định kỳ — chưa làm.

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
tài khoản cloud thật".** Trạng thái chính xác:

| Hạng mục | Trạng thái |
|---|---|
| Adapter đã hiện thực | ✅ Appwrite (identity + metadata), R2 storage |
| Test tự động / mock | ✅ Đạt toàn bộ, chạy offline |
| Runtime dependencies đã khai báo | ✅ `server/requirements.txt`, gồm `boto3` |
| Kiểm chứng Appwrite/R2 thật | ❌ **Chưa** — cần tài khoản và credential do người vận hành tự cấu hình ngoài source |

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
