# Backend Fanfic World DEV công khai (WebSub E2E thật)

Đây KHÔNG PHẢI production. Mục tiêu duy nhất: cho hub PubSubHubbub của
YouTube gọi được callback WebSub thật (`POST /api/youtube/websub`), việc
không thể mô phỏng nội bộ.

## Kiến trúc

```
YouTube WebSub hub
      │ HTTPS
      ▼
Cloudflare (proxy, TLS công khai — Universal SSL)
      │ HTTPS (origin)
      ▼
fanfic-appwrite-temp (GCE us-central1-c, 35.225.209.115)
  ├── appwrite-traefik (đã có sẵn — chia sẻ, KHÔNG sửa cấu hình Appwrite)
  │     ├── router "appwrite_api" (PathPrefix `/`)      → appwrite-dev.fanfic.world
  │     └── router "api_dev_*" (Host, file-provider MỚI) → api-dev.fanfic.world
  │           xem deploy/traefik-dynamic/api-dev.fanfic.world.yml
  └── fanfic-dev-api (container MỚI, mạng `gateway`)
        server/main.py (uvicorn) — nói tới appwrite-dev.fanfic.world/v1
        xem deploy/Dockerfile.dev-api, deploy/docker-compose.dev-api.yml
```

Lý do dùng lại `fanfic-appwrite-temp` thay vì VM mới: đã có Traefik +
Let's Encrypt hoạt động thật (`appwrite-dev.fanfic.world`), tránh tốn thêm
VM/firewall rule mới, và backend cần gọi Appwrite dev — cùng VM giảm độ trễ.
Router mới đi qua **file-provider** của Traefik (`/storage/config/*.yml`),
hoàn toàn tách biệt khỏi docker-provider mà Appwrite dùng (có
`constraint-label-stack=appwrite` — container này KHÔNG mang nhãn đó nên
Traefik của Appwrite sẽ không tự động lấy nó qua docker-provider; router
được khai báo tường minh qua file-provider thay vào đó) — không cần sửa
`docker-compose.yml` của Appwrite.

## Endpoint

- Backend công khai: `https://api-dev.fanfic.world`
- Callback WebSub: `https://api-dev.fanfic.world/api/youtube/websub`
- Appwrite dev (không đổi): `https://appwrite-dev.fanfic.world/v1`

## Biến môi trường (server-side, `.env` cạnh
`docker-compose.dev-api.yml` trên VM — KHÔNG commit, KHÔNG qua tham số dòng lệnh)

Kế thừa từ `server/.env.selfhost` (đã kiểm chứng qua các phase trước), cộng
thêm:

```
YOUTUBE_WEBSUB_CALLBACK_BASE_URL=https://api-dev.fanfic.world
FAS_ENV=development
```

## DNS (thao tác tay — xem báo cáo cuối)

Bản ghi A trỏ `api-dev.fanfic.world` → `35.225.209.115` (IP ngoài của
`fanfic-appwrite-temp`), Proxied qua Cloudflare — cùng khuôn với
`appwrite-dev.fanfic.world` đã có.

## Đối chiếu WebSub định kỳ (renewal + fallback discovery)

`fanfic-websub-reconcile.timer`/`.service` (`deploy/`, cài trên
`fanfic-appwrite-temp` qua `/etc/systemd/system/`) chạy mỗi 4 giờ
`docker compose exec fanfic-dev-api python -m scripts.run_websub_reconciliation`
— đây là nơi DUY NHẤT tự động gia hạn đăng ký WebSub sắp hết hạn
(`RENEWAL_WINDOW=24h`, xem `TrustedSourceService`) và bắt lại video bị
WebSub bỏ lỡ. Không có cơ chế này thì đăng ký chỉ hết hạn âm thầm sau lease
(mặc định ~5 ngày) mà không ai gia hạn. `Dockerfile.dev-api` đã thêm
`COPY scripts/` (trước đó chỉ có `server/`/`desktop_app/`) để script này
chạy được bên trong container. Kiểm tra: `systemctl list-timers
fanfic-websub-reconcile.timer` trên VM.

## Kiến trúc pipeline ingestion (Auto-Ingestion Phase 4)

```
YouTube
    │ WebSub (PubSubHubbub) — video mới/cập nhật/gỡ
    ▼
POST /api/youtube/websub?source_id=... (api-dev, CÔNG KHAI, không qua admin_profile)
    │ verify_signature (HMAC) + parse_notification (defusedxml)
    ▼
TrustedSourceService.handle_websub_notification()
    │ tra cứu AUTHORITATIVE qua YouTube Data API (không tin payload)
    │ _phan_loai_va_ghi_mot_video() — MỘT đường quyết định DUY NHẤT,
    │ dùng chung bởi WebSub/quét thủ công/đối chiếu/discovery
    ▼
VideoImport (idempotent theo youtube_video_id, discovered_via ghi nguồn gốc)
    │ đủ điều kiện auto_import/auto_publish?
    ▼
AnimationEpisode (episode_slot_id tất định theo (series_id, episode_number)
                  — an toàn dưới tải đua nhau giữa mọi đường: WebSub/quét/
                  đối chiếu/nhập thủ công)
```

Đường đối chiếu định kỳ (dự phòng + gia hạn đăng ký):

```
systemd timer (fanfic-websub-reconcile.timer, mỗi 4h)
    ▼
docker compose exec fanfic-dev-api python -m scripts.run_websub_reconciliation
    ▼
TrustedSourceService.run_reconciliation()
    │ quét lại các nguồn enabled+auto_discover (scan_source, bounded 1 trang)
    │ gia hạn đăng ký WebSub sắp hết hạn (RENEWAL_WINDOW=24h)
    ▼
CÙNG _phan_loai_va_ghi_mot_video() ở trên — không có đường xử lý riêng.
```

## Kham pha nhieu series cung luc (Auto-Ingestion Phase 5)

`POST /api/admin/animation/sources/{source_id}/discover-channel` — chi ap
dung cho nguon kieu kenh/playlist (nguon `youtube_video` tra 400, dung
`/discover` mot seed nhu cu). Khac `/discover` (Phase 1, MOT video seed do
quan tri chon dai dien cho MOT series): khong can seed, tu dong quet toan
nguon roi GOM NHOM cac video CHUA khop mapping nao thanh nhieu cum suy doan
la nhieu series khac nhau, dua tren tuong dong fingerprint LAN NHAU (thanh
phan lien thong, khong phai chi so voi mot video co dinh):

```
discover_channel(source_id)
    │ _lay_ung_vien() — CUNG ham bounded/batched voi scan_source (khong
    │                    duong fetch YouTube rieng nao ca)
    ▼
Video da co quyet dinh quan tri truoc do (khac NEW)?
    │ co -> already_tracked++, bo qua (existing admin decisions must win)
    ▼
classify_video() khop MOT mapping da co qua alias/tu khoa?
    │ co -> _xu_ly_mot_video_discovery() ngay, KHONG can gom cum
    ▼
Con lai (chua khop mapping nao) — loai truoc tu khoa AM mac dinh
(NEGATIVE_KEYWORDS: trailer/OST/...), roi GOM NHOM theo similarity()
fingerprint >= CANDIDATE_SIMILARITY_THRESHOLD (thanh phan lien thong)
    ▼
TUNG cum: chon dai dien (uu tien so tap don le thap nhat) ->
_giai_quyet_hoac_tao_series() — helper CHUNG voi discover_series_from_seed
(Phase 1), resolve series da co qua fingerprint HOAC tao series MOI (LUON
DRAFT, khong bao gio tu dong xuat ban)
    ▼
_xu_ly_mot_video_discovery() cho TUNG video trong cum — CUNG pipeline
Phase 1/scan_source, khong co duong ghi rieng nao ca.
```

Khong them scheduler/timer nao — `discover_channel` la mot HANH DONG quan
tri chu dong (nut "Kham pha toan nguon"), khac han
`fanfic-websub-reconcile.timer` (van la vong lap dinh ky DUY NHAT). Mapping
moi tao ra tu mot cum tuong thich NGAY voi WebSub/doi chieu dinh ky sau do
(cung mot `SeriesMapping`, khong can kham pha lai).

## Quy trình triển khai DEV thật sự đang dùng (Phase 4 xác nhận lại)

**KHÔNG phải git-pull.** Repo clone trên VM tại
`/home/robux/fanfic-dev-api/repo` (nhánh `infra/public-dev-backend-websub-v1`
lúc clone ban đầu) đã LỆCH lịch sử git so với `origin` — các phiên sau
(Phase 2-4) đưa code mới lên bằng cách **đồng bộ file trực tiếp**
(`gcloud compute scp` từng file đã đổi vào `/tmp/` trên VM, rồi `cp` đè vào
đúng đường dẫn trong repo checkout) thay vì `git pull`/`git push` lên
nhánh đó. Sau khi file đã đúng, rebuild:

```bash
# Tại VM (qua SSH), trong deploy/:
docker compose -f docker-compose.dev-api.yml up -d --build
```

Đây là quyết định CÓ CHỦ ĐÍCH, không phải sơ suất: nhánh `infra/...` chỉ
tồn tại để dựng hạ tầng ban đầu (Traefik/DNS/TLS) và không được cập nhật
song song với nhánh làm việc chính (`feature/...`) mỗi khi có thay đổi
nghiệp vụ — đồng bộ file trực tiếp tránh phải quản lý một nhánh git thứ hai
luôn phải rebase theo nhánh chính. Migration schema Appwrite (thêm thuộc
tính mới, vd `discovered_via`) chạy THỦ CÔNG một lần từ máy cục bộ
(`FAS_ENV_FILE=server/.env.selfhost python -m scripts.setup_appwrite --only <collection>`)
TRƯỚC khi rebuild container — script này an toàn chạy lại nhiều lần
("dòng-thiếu-thì-bỏ-qua").

**Không tự động chuyển sang git-pull** trong phiên này hay bất kỳ phiên
nào sau — nếu muốn đổi quy trình triển khai, đó là quyết định cần người
dùng xác nhận trước.

## Trạng thái

Xem `docs/handoffs/public-dev-backend-websub-v1.md` để biết mốc nào đã
xong/đang chờ DNS.
