# Handoff: Public Dev Backend + Real YouTube WebSub E2E

Nhánh: `infra/public-dev-backend-websub-v1`, từ `integration/pre-prod-v1` @
`4634fd0`. KHÔNG merge trong phiên này — chỉ push/freeze.

## Ranh giới an toàn (nhắc lại)

KHÔNG: sửa `main`, deploy Fanfic World production, đụng Appwrite Cloud
production, đổi DNS production, xoá/sửa secret production, mở cổng
DB/cache Appwrite ra ngoài, làm yếu xác thực, in secret, commit `.env`, sửa
hành vi `appwrite-dev.fanfic.world` hiện có trừ khi thật cần và an toàn.

## Hạ tầng đã xác nhận (đọc thật, không suy đoán)

- GCE project `gen-lang-client-0793420657`, 3 instance đang chạy:
  `fanfic-appwrite-temp` (us-central1-c, `35.225.209.115`, có tag
  `http-server`/`https-server`, chạy Appwrite tự lưu trữ + Traefik +
  Let's Encrypt — chính là host của `appwrite-dev.fanfic.world`),
  `fanfic-v7` (asia-southeast1-b, không tag public, mục đích KHÔNG rõ trong
  tài liệu — KHÔNG dùng cho việc này, để nguyên), `fanfic-worker-prod`
  (asia-southeast1-b, worker production, không liên quan).
- `deploy/render.yaml`/`render.free.yaml`: cấu hình STAGING (Appwrite
  Cloud + R2), CHƯA từng deploy thật (không có tài khoản Render) — KHÔNG
  phải con đường cho việc này (mục tiêu là backend nói với
  `appwrite-dev.fanfic.world`, không phải Cloud staging).
- Route WebSub đã có sẵn, đúng khớp path mong đợi:
  `GET/POST /api/youtube/websub` (`server/main.py:5292`/`5315`).
- `fanfic-appwrite-temp` chạy Traefik (`traefik:3.6`, container
  `appwrite-traefik`) với `--providers.docker.constraints=Label(
  'traefik.constraint-label-stack','appwrite')` (chỉ container Appwrite mới
  được docker-provider tự nhận) VÀ `--providers.file.directory=/storage/config
  --providers.file.watch=true` (file-provider độc lập — đây là đường dùng
  cho dịch vụ mới). Mạng `gateway` tồn tại sẵn, dùng cho đúng mục đích này
  (Traefik đã nối cả hai mạng `appwrite` và `gateway`).
- Cert Let's Encrypt của `appwrite-dev.fanfic.world` được cấp qua certbot
  THỦ CÔNG một lần (không phải ACME tự động của Traefik), rồi ghi file TLS
  vào `/storage/config/appwrite-dev.fanfic.world.yml` — mẫu này lặp lại
  cho `api-dev.fanfic.world` sau khi DNS phân giải.
- Không có Cloudflare API token/`wrangler` trong môi trường agent này — bản
  ghi DNS phải người dùng thêm tay (đúng như đặc tả yêu cầu).

## Việc đã làm (code, tại chỗ)

- **Sửa lỗ hổng bảo mật thật** trước khi công khai route:
  `POST /api/youtube/websub` dùng `await request.body()` — đệm TOÀN BỘ thân
  vào bộ nhớ TRƯỚC khi có cơ hội kiểm tra kích thước; kẻ tấn công bỏ
  qua/giả mạo `Content-Length` (hoặc chunked encoding) vẫn ép đệm được thân
  không giới hạn. Đổi sang đọc theo khối qua `request.stream()`, dừng SỚM
  khi vượt `MAX_NOTIFICATION_BYTES` bất kể header. Test mới:
  `test_thong_bao_qua_lon_bi_chan_413_du_khong_co_content_length_dung`.
  Backend: **2409/2409 pass** (1 skip không liên quan). Commit `520e724`.
- Re-audit phần còn lại của callback WebSub (Phase 5 đặc tả): XXE — SẠCH
  (`defusedxml`, không dùng `xml.etree.ElementTree` trần); chữ ký — SẠCH
  (`hmac.compare_digest`, kiểm định dạng hex trước để tránh `TypeError`,
  không bao giờ ném lỗi); xác thực kênh — SẠCH (`entry.channel_id !=
  source.youtube_channel_id` → bỏ qua); idempotency — đã xác nhận từ đợt
  smoke test WebSub trước (14/14), không lặp lại ở đây. Rate limiting tầng
  ứng dụng: KHÔNG có — dựa vào bảo vệ biên Cloudflare (chấp nhận được cho
  dev, ghi nhận cho production sau).
- `deploy/Dockerfile.dev-api` — image nhỏ, chỉ `server/` + `desktop_app/`
  (đúng 4 module CLAUDE.md cho phép), ffmpeg, chạy user không phải root,
  không `--reload`.
- `deploy/docker-compose.dev-api.yml` — container `fanfic-dev-api`, mạng
  `gateway` (external, đã có sẵn), `restart: unless-stopped`, healthcheck
  gọi `/api/health` nội bộ, `.env` cạnh file (KHÔNG commit).
- `deploy/traefik-dynamic/api-dev.fanfic.world.yml` — router file-provider
  cho `api-dev.fanfic.world`, KHÔNG đụng `docker-compose.yml` của Appwrite.
- `docs/DEV_PUBLIC_BACKEND.md` — kiến trúc, endpoint, biến môi trường, bản
  ghi DNS cần thêm.

## Phase 6 — Deploy backend dev: XONG, đã xác minh THẬT

- Clone nhánh `infra/public-dev-backend-websub-v1` thẳng từ GitHub (public)
  vào `/home/robux/fanfic-dev-api/repo` trên `fanfic-appwrite-temp`.
- `.env` chuyển bằng `gcloud compute scp` (KHÔNG qua tham số dòng lệnh,
  KHÔNG in ra terminal) — phát hiện VÀ SỬA một lỗi khi thao tác: file gốc
  không kết thúc bằng newline nên lần nối đầu tiên bị dính liền vào cuối
  dòng `YOUTUBE_API_KEY` (làm hỏng CẢ HAI giá trị) — đã phát hiện qua kiểm
  tra tên khoá (không in giá trị) và sửa bằng cách đảm bảo newline cuối file
  trước khi nối. Đã thêm `YOUTUBE_WEBSUB_CALLBACK_BASE_URL=https://api-dev.
  fanfic.world` và `FAS_ENV=development`.
- `docker compose -f docker-compose.dev-api.yml build && up -d` — container
  `fanfic-dev-api` **Up, health: healthy**.
- Xác minh THẬT (không suy đoán):
  - `GET /api/health` nội bộ: `data_backend: appwrite`, `appwrite_configured:
    true`.
  - Đăng ký một user thật qua container này → **201**, ghi thật vào
    `appwrite-dev.fanfic.world` (Appwrite dev connectivity THẬT).
  - `GET /api/admin/overview` không token → **401** (xác thực KHÔNG bị suy
    yếu — container public không giữ quyền admin/owner cục bộ nào).
  - `YouTubeClient.get_video('jNQXAC9IVRw')` thật → trả đúng tiêu đề "Me at
    the zoo" (YouTube Data API connectivity THẬT).
  - Cổng 8010 KHÔNG lộ ra host/Internet (`ss -tlnp` chỉ thấy 80/443 của
    Traefik) — container chỉ tới được qua mạng docker `gateway`.
  - Router Traefik mới copy vào
    `/var/lib/docker/volumes/appwrite_appwrite-config/_data/
    api-dev.fanfic.world.yml` (file-provider, watch tự nạp) — xác minh
    bằng `curl --resolve api-dev.fanfic.world:443:35.225.209.115` TỪ MÁY
    NGOÀI VM → **200**, đúng response của `fanfic-dev-api` (chưa có cert
    Let's Encrypt thật nên phải `-k`, dùng cert dự phòng của Traefik tạm
    thời).
  - Xác nhận `appwrite-dev.fanfic.world` (route cũ, `PathPrefix('/')`)
    KHÔNG bị ảnh hưởng — vẫn trả đúng qua cùng phép test `--resolve` giả
    lập.
- Full verification lại trên nhánh: backend **2409/2409 pass**, frontend
  **635/635 pass**, typecheck/lint/build sạch, quét secret sạch.

### Phát hiện thêm khi audit Phần 11 (quan sát được): `youtube_websub` báo sai "healthy"

Trong lúc audit tiêu chí Phần 11 ("KHÔNG BAO GIỜ báo HEALTHY khi trạng thái
thật còn chưa rõ"), phát hiện `/api/admin/overview` báo `youtube_websub:
healthy` CHỈ dựa trên "đã cấu hình URL callback" (biến môi trường) — không
chứng minh gì về việc hub đã từng xác minh/gọi lại thật. Vì sắp công khai
callback này lần đầu, rủi ro đọc nhầm "healthy" thành "đã chứng minh hoạt
động" là thật. Đã sửa (commit `940cf94`): thêm
`has_active_websub_subscription()` (một truy vấn bị chặn, an toàn cho
dashboard chính) ở cả hai kho; `youtube_websub` giờ là `not_configured` /
`degraded` (đã cấu hình nhưng chưa nguồn nào đạt `ACTIVE`) / `healthy` (ít
nhất một nguồn `ACTIVE` thật). Test mới:
`test_he_thong_khong_bao_healthy_khi_websub_chua_tung_xac_minh`. Backend:
**2410/2410 pass**. Đã redeploy lên VM (`docker compose up -d --build`),
xác nhận lại container healthy và định tuyến ngoài vẫn đúng.

## Phase 7 — DNS/TLS: BLOCKED (thao tác tay)

Let's Encrypt cấp chứng chỉ qua thử thách HTTP-01 — CẦN DNS đã phân giải
công khai trước khi certbot chạy được (đúng mẫu đã làm cho
`appwrite-dev.fanfic.world`, xem `docs/reports/appwrite-selfhost-gce-summary.md`
mục 15.3). Không có Cloudflare API token trong môi trường agent này nên
không tự thêm bản ghi được.

**Bản ghi DNS cần thêm (Cloudflare dashboard, giống hệt cách đã làm cho
`appwrite-dev.fanfic.world`):**

```
TYPE: A
NAME: api-dev
VALUE: 35.225.209.115
PROXY STATUS: Proxied
```

Sau khi DNS phân giải, các bước còn lại (chạy certbot thủ công một lần,
copy cert vào `/storage/certificates/api-dev.fanfic.world/`, thêm khối
`tls.certificates` vào `deploy/traefik-dynamic/api-dev.fanfic.world.yml`,
rồi mới đăng ký WebSub thật với hub) đều đã CHUẨN BỊ SẴN kịch bản, chỉ chờ
DNS. Phase 8/9/10/11 phụ thuộc trực tiếp vào Phase 7 nên CHƯA thực hiện
được trong phiên này.

## Tiến độ theo phase (đặc tả gốc)

- [x] Phase 0 — an toàn, tạo nhánh.
- [x] Phase 1 — audit hạ tầng hiện có.
- [x] Phase 2 — kiến trúc mục tiêu xác định (`api-dev.fanfic.world` →
      `fanfic-appwrite-temp`, tái dùng Traefik/Let's Encrypt có sẵn).
- [x] Phase 3 — thiết kế triển khai (Dockerfile + compose + Traefik
      file-provider, không secret trong tham số dòng lệnh).
- [x] Phase 4 — xác nhận route WebSub GET/POST đã đúng đặc tả, không viết
      lại logic Phase 6.
- [x] Phase 5 — re-audit bảo mật callback công khai — 1 lỗ hổng thật đã sửa
      (mục trên), phần còn lại sạch.
- [x] Phase 6 — deploy backend dev. XONG, xác minh THẬT (health/Appwrite dev/
      auth/YouTube API đều thật, xem mục "Phase 6" bên dưới).
- [ ] Phase 7 — DNS/TLS. **BLOCKED — cần thao tác tay** (xem mục "Phase 7"
      bên dưới để lấy đúng TYPE/NAME/VALUE/PROXY STATUS).
- [ ] Phase 8 — đăng ký WebSub thật (phụ thuộc Phase 7).
- [ ] Phase 9 — E2E thật từ YouTube (phụ thuộc Phase 7/8).
- [ ] Phase 10 — xác nhận reconciliation vẫn là dự phòng tần suất thấp.
- [ ] Phase 11 — Admin System/Trusted Source UI phản ánh đúng trạng thái
      thật (không hiện HEALTHY khi chưa biết).
- [ ] Phase 12 — xác minh đầy đủ cuối cùng.
- [ ] Phase 13 — hoàn thiện nhánh (commit/push/freeze, KHÔNG merge, quay về
      `integration/pre-prod-v1` sạch).

## Nếu context bị nén: đọc file này + `git log --oneline -10` trên nhánh
`infra/public-dev-backend-websub-v1` + `gcloud compute instances list`
trước khi làm bất cứ gì.
