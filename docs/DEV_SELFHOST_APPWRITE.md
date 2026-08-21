# Chạy dev/staging trên Appwrite tự lưu trữ (GCE tạm thời)

Tài liệu thao tác — chi tiết hạ tầng đầy đủ (VM, Docker, chứng chỉ, sự cố
đã gặp) nằm ở `docs/reports/appwrite-selfhost-gce-summary.md`. File này chỉ
trả lời "làm sao để chạy code cục bộ chống lại instance đó".

## Phân tách bắt buộc — KHÔNG BAO GIỜ trộn lẫn

| | Production | Dev/staging (tài liệu này) |
|---|---|---|
| Backend | `server/.env`/`server/.env.production` | `server/.env.selfhost` |
| Appwrite | Cloud thật (`sgp.cloud.appwrite.io`) | Tự lưu trữ (`appwrite-dev.fanfic.world`) |
| Ai được chạm | Vận hành viên, có kiểm soát | Bất kỳ ai lập trình tính năng mới |

`server/.env.selfhost` bị `.gitignore` chặn (khớp `.env.*`) — **không bao
giờ** xuất hiện trong git. Không copy giá trị bí mật của nó sang bất kỳ
file nào khác được commit.

## Chạy backend chống lại self-host

```powershell
$env:FAS_ENV_FILE = "server/.env.selfhost"
$env:FAS_INLINE_WORKER = "true"
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

```bash
FAS_ENV_FILE=server/.env.selfhost FAS_INLINE_WORKER=true \
  ./.venv/Scripts/python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

Xác nhận đã trỏ đúng nơi:

```bash
curl -s http://127.0.0.1:8010/api/health | jq '{identity, data_backend}'
# ki vong: {"identity": "appwrite", "data_backend": "appwrite"}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/api/ready
# ki vong: 200
```

## Frontend

```bash
cd web
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010 npm run dev
```

## Smoke test tự động

```bash
FAS_ENV_FILE=server/.env.selfhost PYTHONIOENCODING=utf-8 \
  ./.venv/Scripts/python.exe -m scripts.smoke_test_selfhost_appwrite
```

Kịch bản: tự khởi backend tạm (nếu chưa chạy sẵn ở `--base-url`), đăng ký
một tài khoản dev dùng-một-lần, gọi `/api/progress/read` HAI LẦN cùng
payload để xác nhận streak/quest không bị đếm trùng (idempotent), kiểm
leaderboard/cosmetics. KHÔNG gọi bất kỳ endpoint sinh ảnh trả phí nào
(Shared Premium/BYOP) — chỉ kiểm kiến trúc Image Studio qua route model
list, không tiêu Pollen.

`--help` để xem tuỳ chọn (`--base-url` nếu backend đã chạy sẵn ở cổng
khác, `--keep-user` để giữ lại user test thay vì log ra để tự xoá thủ
công qua Appwrite console).

## Áp schema lên self-host (khi thêm collection mới)

```bash
FAS_ENV_FILE=server/.env.selfhost PYTHONIOENCODING=utf-8 \
  ./.venv/Scripts/python.exe -m scripts.setup_appwrite
```

An toàn chạy lại nhiều lần — chỉ tạo phần còn thiếu, không xoá/sửa gì đã
có (xem docstring đầu file).

## Khi hạ tầng tự lưu trữ gặp sự cố

- VM tự khởi động lại vẫn tự phục hồi (`appwrite-selfhost.service`, xem
  báo cáo hạ tầng mục 10/14) — không cần SSH vào chạy `docker compose up`.
- Chứng chỉ Let's Encrypt hết hạn `2026-11-14` — xem báo cáo hạ tầng mục
  15.3 để lặp lại thao tác cấp mới (worker không tự động renew do task bảo
  trì chạy theo giờ cố định, không phải theo hạn chứng chỉ còn lại).
- Không bao giờ tự ý đổi `DATA_BACKEND`/`APPWRITE_*` trong
  `server/.env`/`server/.env.production` để "thử nhanh" — luôn dùng
  `FAS_ENV_FILE=server/.env.selfhost` thay vì sửa file production.
