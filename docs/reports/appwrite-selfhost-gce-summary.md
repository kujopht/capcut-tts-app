# Appwrite tự lưu trữ tạm thời trên GCE — báo cáo tổng kết

Nhánh: `infra/appwrite-selfhost-gce`, branch từ `integration/pre-prod-v1`
(`295d470`). Không merge main, không deploy production. Appwrite Cloud
production **hoàn toàn không bị ghi/xoá/thay đổi** trong toàn bộ phiên này.

## ⚠️ Sự cố bảo mật — ĐÃ XỬ LÝ (khoá production đã được xoay vòng thủ công)

Trong lúc thử cơ chế migration chính thức Cloud → self-host, một lời gọi API
thất bại (lỗi validate tham số `resources`) và Appwrite trả về stack trace
debug-mode chứa **toàn bộ giá trị `APPWRITE_API_KEY` production thật** trong
phần `trace.args` — điều này KHÔNG được lường trước (sanitize ban đầu chỉ lọc
key cấp cao nhất của JSON, không lọc đệ quy vào `trace`). Giá trị đó đã xuất
hiện trong output hiển thị của phiên làm việc này.

**Cập nhật**: bạn đã tự xoay vòng khoá này thủ công qua Appwrite Cloud
console. Xem mục 13 bên dưới cho đợt audit/vá lỗi hệ thống sau sự cố này
(gốc rễ, chỗ đã sửa, kết quả quét lịch sử git).

**Hành động ĐÃ HOÀN TẤT (giữ nguyên lịch sử báo cáo)**: đăng
nhập Appwrite Cloud console, vào phần API Keys của dự án production, **thu
hồi/tạo mới khoá `APPWRITE_API_KEY` đang dùng trong `server/.env.production`
ngay bây giờ**, rồi cập nhật file đó với khoá mới. Đây là ưu tiên cao hơn bất
kỳ mục nào khác dưới đây.

Sau sự cố này, tôi đã dừng NGAY mọi nỗ lực migration tiếp theo (không thử
lại với tham số đã sửa), dọn các file tạm cục bộ có tham chiếu tới key, và
từ đó về sau CHỈ dùng key production qua script đọc trực tiếp từ file, KHÔNG
BAO GIỜ hiển thị JSON lỗi thô nữa (chỉ in `message`/`status`, không đệ quy
vào các trường khác).

## 1. VM — không có gì bất thường

`fanfic-appwrite-temp` (us-central1-c, `gen-lang-client-0793420657`):
Ubuntu 24.04.4 LTS, `c4-standard-2` (2 vCPU, 6.8GiB RAM khớp đúng kỳ vọng),
disk 48G (31G còn trống sau khi cài đặt + 1 bản backup), IP ngoài
`35.225.209.115`, IP trong `10.128.0.6`. Đã thêm 4GB swap (trước đó chưa
có). Không bật root SSH, không bật password SSH (đã tắt sẵn từ ảnh Ubuntu
cloud mặc định, không đụng tới).

## 2. Chuẩn bị máy chủ

Docker Engine 29.7.2 + Compose v5.4.0 cài qua repo APT chính thức của
Docker (định dạng `.sources` deb822 MỚI — khác định dạng `.list` cũ, xác
nhận qua tài liệu hiện tại thay vì dùng lệnh cũ từ trí nhớ). Docker bật
cùng boot. Swap 4GB đã thêm, ghi bền trong `/etc/fstab`.

## 3. Cài Appwrite tự lưu trữ — 3 lỗi thật gặp và đã sửa

Dùng `docker-compose.yml`/`.env` chính thức ghim đúng bản **1.9.6** (xác
nhận qua GitHub Releases API, không đoán) — cách "advanced/custom
installation" README chính thức mô tả, KHÔNG dùng wizard tương tác (không
scriptable qua SSH không TTY). Kiến trúc DB đã đổi khác nhiều so với các bản
Appwrite cũ: **MongoDB** là adapter chính (`_APP_DB_ADAPTER=mongodb`),
**PostgreSQL** cho vector DB, MariaDB vẫn còn trong stack nhưng không phải
adapter mặc định — xác nhận qua `.env`/`docker-compose.yml` thật, không dựa
trí nhớ huấn luyện (từng nghĩ Appwrite chỉ dùng MariaDB).

**Lỗi 1 — MongoDB không khởi động (exit 126)**: `docker-compose.yml` tham
chiếu `./mongo-entrypoint.sh`/`./mongo-init.js` như bind-mount cục bộ, nhưng
tải riêng `docker-compose.yml`+`.env` không kèm hai file này — Docker tự
tạo chúng thành THƯ MỤC RỖNG, làm entrypoint thất bại. Đã tải đúng hai file
từ repo (cùng tag 1.9.6), xoá thư mục rỗng, tạo lại container — khoẻ mạnh.

**Lỗi 2 — Traefik không route được (404 "no matching router" dù label
đúng)**: khám phá Docker provider của Traefik lúc khởi động lần đầu không
bắt được container `appwrite` (đua thời điểm khởi động, không phải lỗi
cấu hình — nhãn `traefik.*` hoàn toàn đúng khi kiểm tra). Restart một lần
là đủ, `GET /v1/health/version` trả `{"version":"1.9.6"}` sau đó.

**Không có restart loop nào** — mọi container `RestartCount=0`. RAM 3.6/6.8
GiB dùng, disk 17/48G dùng (trước backup), tất cả container `healthy`/`Up`.

## 4. Mạng công khai

Firewall dự án: chỉ SSH (22), HTTP (80), HTTPS (443) mở ra `0.0.0.0/0` cho
VM này (nhờ network tag `http-server`/`https-server`) — cổng nội bộ Mongo
(27017)/MariaDB (3306)/Redis (6379)/PostgreSQL (5432) **KHÔNG** được publish
ra host (`docker-compose.yml` gốc của Appwrite vốn không publish chúng —
xác nhận bằng `ss -tulnp` trên VM: chỉ 22/80/443 lắng nghe `0.0.0.0`).

**Cần bạn thao tác thủ công (chỉ mục này)**:

| TYPE | NAME | VALUE |
|---|---|---|
| A | `appwrite-dev.fanfic.world` | `35.225.209.115` |

Chưa có bản ghi này nên hiện dùng IP trực tiếp qua HTTP (chưa TLS — Let's
Encrypt không cấp chứng chỉ cho IP trần). Sau khi bạn thêm DNS, đổi
`_APP_DOMAIN` trong `~/appwrite/.env` (trên VM) sang tên miền rồi
`docker compose up -d` lại để Appwrite tự xin chứng chỉ.

## 5. Dự án tự lưu trữ tạm thời

Tạo team + project `fanfic-world-selfhost-dev` (project id lưu trong
`server/.env.selfhost`, không phải secret nhưng vẫn giữ cục bộ). Hai API
key riêng biệt (khớp mẫu `APPWRITE_API_KEY`/`APPWRITE_SCHEMA_API_KEY` có
sẵn trong `server/config.py`):

- **schema-migration-key**: `databases.*`, `collections.*`, `attributes.*`,
  `indexes.*`, `documents.*` — chỉ dùng cho `scripts/setup_appwrite.py`.
- **backend-runtime-key-v2**: `documents.*`, `users.*`, `sessions.write`,
  `teams.*`, và **bổ sung** `collections.read`/`databases.read` sau khi phát
  hiện thiếu (mục 6). Đây là quyền TỐI THIỂU runtime thực sự cần.

Một session console admin và một API key migration một-lần bị lộ do sự cố ở
đầu báo cáo — cả hai đã bị **thu hồi ngay lập tức** trên self-host (không
liên quan tới sự cố production ở trên, nhưng cùng nguyên tắc xử lý).

## 6. Cloud → self-host migration — KHÔNG hoàn tất, dừng vì sự cố bảo mật

Không dùng lệnh migration đoán mò: xác nhận endpoint `/v1/migrations`
tồn tại thật qua chính OpenAPI/behaviour của instance (401 "missing scopes"
khi chưa cấp quyền — chứng minh route có thật). Cấp quyền `migrations.*`,
gọi thật `POST /v1/migrations/appwrite` với endpoint/projectId/apiKey của
Cloud production — **thất bại ở bước validate tham số `resources`** (lỗi
400 rõ ràng, chưa chạm tới bước đọc dữ liệu Cloud thật), và chính lỗi 400 đó
làm lộ key (mục đầu báo cáo). Tôi dừng NGAY, không thử lại.

**Không xác nhận lại quota Cloud qua chính đường migration** (chưa kịp thử
với tham số đúng thì đã dừng vì lý do bảo mật) — nhưng phiên làm việc TRƯỚC
đó trong ngày đã xác nhận bằng một lần đọc thật riêng biệt (`store.
list_events`) rằng Cloud production **vẫn đang bị chặn hạn mức đọc**
("Database reads limit for the current billing cycle has been exceeded").
Không có lý do để tin trạng thái đó đã đổi trong vài giờ giữa hai lần kiểm
tra. Theo đúng yêu cầu gốc ("nếu migration thất bại vì hạn mức Cloud → dừng
migration, áp schema sạch") — tôi coi điều kiện này đã thoả và chuyển sang
mục 7, dù lý do dừng thực tế là sự cố bảo mật chứ không phải một lần thử
migration thất bại vì 402 cụ thể.

## 7. Schema — 2 lỗi thật trong `scripts/setup_appwrite.py` + 4 collection mới

Áp toàn bộ schema hiện có của `integration/pre-prod-v1` lên self-host bằng
chính `scripts/setup_appwrite.py` (không viết công cụ song song). Gặp và
sửa hai lỗi thật (không đoán, tái hiện được nhiều lần):

1. **`_call()` chỉ coi HTTP 409 là "đã tồn tại"** — Appwrite 1.9.6 tự lưu
   trữ trả **400** kèm thông điệp `"already an index with the same
   attributes and orders"` cho index trùng, không phải 409 như bản Appwrite
   script được viết ra để chạy trước đó. Đã thêm nhánh khớp CHÍNH XÁC thông
   điệp này (không phải mọi lỗi 400) để không che giấu lỗi thật khác.
2. **Tạo index ngay sau khi tạo thuộc tính mới** — thuộc tính ở Appwrite là
   BẤT ĐỒNG BỘ (POST trả về ngay, thuộc tính ở trạng thái "processing" vài
   giây trước khi "available"); tạo index tham chiếu thuộc tính chưa sẵn
   sàng bị từ chối 400 "not yet available". Đã thêm bước chờ có giới hạn
   (`_doi_thuoc_tinh_san_sang`, tối đa 30 lần × 1 giây) — CHỈ chạy khi
   collection vừa có thuộc tính MỚI, không làm chậm các lần chạy lại ổn
   định.

Sau hai bản vá: chạy `scripts.setup_appwrite` (không `--dry-run`) đạt
**exit code 0**, chạy lại lần nữa xác nhận **"tạo mới 0, bỏ qua (đã có)
456"** — hoàn toàn idempotent.

**4 collection mới cho Image Studio** (thiết kế mới, THEO ĐÚNG dataclass ở
`server/image_domain.py`, không phát minh trường nào khác):

- `image_wallet_transactions` — sổ cái append-only, `idempotency_idx`
  UNIQUE trên `idempotency_key` — đây chính là cơ chế chặn tính tiền hai
  lần, giờ được Appwrite tự thi hành (không chỉ ở tầng code).
- `image_generation_reservations` — vòng đời reserve/settle/refund.
- `image_saved_library` — chỉ metadata + `storage_key`, không lưu ảnh nhị
  phân trong Appwrite.
- `image_byop_connections` — **CHỈ** hai trường `encrypted_access_token`/
  `encrypted_refresh_token` (AES-256-GCM qua `ByokCrypto` có sẵn) — dataclass
  gốc không có trường plaintext nào để lỡ ghi nhầm.

Đây là schema THIẾT KẾ cho tương lai — `image_service.py` vẫn chạy trên
`MockWalletStore`/`MockByopConnectionStore`/`MockImageLibraryStore` trong bộ
nhớ như đã ghi trong `docs/reports/image-studio-v1-summary.md`; KHÔNG viết
adapter Appwrite thật trong đợt này (đúng phạm vi Phase 7: chỉ schema).

## 8. Cấu hình dev

`server/.env.selfhost` (bị `.gitignore` chặn, không commit) — **KHÔNG ghi
đè** `server/.env`/`server/.env.production`/`server/.env.staging`. Chuyển
đổi giữa các backend chỉ bằng `FAS_ENV_FILE=server/.env.selfhost`.

## 9. Smoke test — chạy backend thật, nối self-host Appwrite thật

Khởi động `uvicorn server.main:app` trỏ `FAS_ENV_FILE=server/.env.selfhost`.

**Lỗi thật thứ ba phát hiện qua smoke test** (không phải lỗi cache tiến
trình như nghi ngờ ban đầu — đã loại trừ bằng cách khởi động tiến trình HOÀN
TOÀN MỚI, xác nhận qua PID, vẫn lỗi giống hệt): `backend-runtime-key-v2`
ban đầu **thiếu scope `collections.read`**. `AppwriteIdentityAdapter.
_profile_attributes()` cần đọc metadata schema (KHÔNG sửa schema) để biết
các trường V2 tuỳ chọn (username/bio/author_status/...) đã tồn tại chưa —
thiếu quyền đọc này khiến lời gọi thất bại âm thầm, hàm coi như "chưa
migrate" và ném lỗi 500 dù schema đã đúng 100%. Đã thêm `collections.read`
+ `databases.read` vào đúng key đó (không đổi giá trị key, chỉ mở rộng
scope).

Sau khi sửa, kết quả smoke test THẬT (không giả lập):
- `POST /api/auth/register` → 201, ghi đúng document `profiles` thật.
- `POST /api/progress/read` gọi **hai lần liên tiếp cùng payload** → cả hai
  đều 200; `streak.current_streak=1` (không phải 2), quest `doc_hang_ngay`
  `count=1, completed=true` (không phải 2) — xác nhận idempotent thật qua
  Appwrite thật, không phải mock.
- `GET /api/leaderboard?mode=all_time|weekly` → 200.
- `GET /api/account/{quests,progress,cosmetics}` → 200.
- Image Studio schema (chưa có adapter, kiểm trực tiếp qua REST): tạo
  document `image_wallet_transactions` với `idempotency_key` đã dùng →
  **HTTP 409 bị chính Appwrite từ chối** (kể cả với `documentId` mới hoàn
  toàn qua `unique()`) — xác nhận unique index hoạt động đúng, không phải
  giả định lý thuyết. Đã xoá sạch mọi document smoke-test sau khi kiểm.

## 10. Bảo mật + backup

- Không có secret nào bị commit (`server/.env.selfhost` xác nhận
  `git check-ignore` khớp `.env.*`).
- Cổng nội bộ DB/cache không public (mục 4).
- API key đã scope tối thiểu theo mục đích (mục 5), sự cố lộ key đã xử lý
  (thu hồi + tạo mới, mục 5).
- Volume Docker là named volume bền vững (`appwrite_appwrite-*`).
- **Restart policy**: hầu hết service lõi (`traefik`, `appwrite`, `mariadb`,
  `postgresql`, `redis`) có policy `no` trong compose gốc của Appwrite —
  nghĩa là sau khi VM khởi động lại, Docker daemon tự chạy (đã `enable`)
  nhưng CÁC CONTAINER NÀY sẽ không tự lên lại. Đã thêm
  `/etc/systemd/system/appwrite-selfhost.service` (oneshot, chạy
  `docker compose up -d` sau khi `docker.service` sẵn sàng), đã `enable` —
  **chưa kiểm chứng bằng một lần reboot thật** (chưa chủ động khởi động lại
  VM trong phiên này).
- Backup: `~/appwrite/backup.sh` (đã chạy thật, tạo 566MB tại
  `~/appwrite/backups/20260816T022120Z`, kèm `RESTORE.md` hướng dẫn khôi
  phục từng volume). Chỉ chạy thủ công, không lịch tự động, không upload ra
  ngoài VM.

## 11. Git

Nhánh `infra/appwrite-selfhost-gce`, branch từ `integration/pre-prod-v1`
(`295d470`). Thay đổi DUY NHẤT trong repo: `scripts/setup_appwrite.py` (2
bản vá tương thích Appwrite 1.9.6 + 4 collection Image Studio mới) và tài
liệu này. `server/.env.selfhost` không commit (đúng thiết kế). Chưa merge,
chưa deploy.

## 12. Tổng kết theo đúng yêu cầu

| Mục | Kết quả |
|---|---|
| GCE health | Khoẻ, không bất thường so với 2 vCPU/~7GB/Ubuntu 24.04 |
| External IP | `35.225.209.115` |
| Appwrite version | 1.9.6 |
| Container status | Tất cả `Up`/`healthy`, 0 restart loop |
| Appwrite endpoint | `/v1/health/version` trả 200 cục bộ và qua backend thật |
| Cloud migration | KHÔNG hoàn tất — dừng vì sự cố lộ khoá production (mục đầu), không phải vì xác nhận trực tiếp lỗi hạn mức qua chính API migration |
| Quota có chặn migration không | Không xác nhận trực tiếp qua migration; xác nhận GIÁN TIẾP qua lần đọc thật ở phiên trước cùng ngày |
| Schema đã tạo | Toàn bộ ~29 collection cũ + 4 collection Image Studio mới, idempotent xác nhận |
| Cấu hình dev đã tạo | `server/.env.selfhost`, tách biệt hoàn toàn production |
| Kết quả DB smoke-test | Thành công (auth/progress/streak/quest/leaderboard/cosmetics/Image-Studio-schema, kể cả kiểm idempotency thật) |
| Test backend/frontend | 2128 backend / 563 frontend, đều xanh |
| Typecheck/lint/build | Sạch, thành công |
| RAM/disk | 3.6/6.8 GiB, 17→17.5G/48G (sau backup thêm 566MB) |
| Cổng public | 22, 80, 443 — không cổng DB/cache nào lộ |
| Backup | `~/appwrite/backup.sh`, đã chạy thật, có RESTORE.md |
| Nhánh + SHA | `infra/appwrite-selfhost-gce`, xem `git log` sau commit |
| DNS/TLS còn thiếu | Bản ghi A `appwrite-dev.fanfic.world → 35.225.209.115` (mục 4) |
| Khoá production đã lộ | **ĐÃ xoay vòng thủ công (xác nhận từ bạn)** — xem mục 13 |

## 13. Audit bảo mật sau sự cố lộ khoá (follow-up)

Không đọc/in/echo giá trị khoá `APPWRITE_API_KEY` MỚI trong toàn bộ đợt
audit này — không cần thiết, đây là audit CODE PATTERN, không phải thao tác
với credential thật.

### 13.1 Gốc rễ thật sự

Toàn bộ 5 lớp đọc Appwrite hiện có trong repo
(`server/appwrite_store.py`, `appwrite_adapter.py`,
`appwrite_gamification_store.py`, `appwrite_animation_store.py`,
`appwrite_translation_store.py`) và `scripts/setup_appwrite.py` **đã luôn
an toàn** — cả 6 file chỉ trích xuất đúng trường `message` từ response, KHÔNG
BAO GIỜ in nguyên văn `trace`/`args`/header. Sự cố lộ khoá KHÔNG đến từ code
production, mà từ một **script chẩn đoán tạm thời** (viết ngoài repo, đã bị
xoá sau khi dùng) tự gọi `httpx` trực tiếp và in `resp.json()` nguyên văn —
bỏ qua hoàn toàn các lớp `_call()` an toàn đã có sẵn.

### 13.2 Đã thêm — lớp phòng thủ THÊM (không thay thế cách làm cũ)

`server/secret_redaction.py` (mới):
- `loc_bo_de_qui(du_lieu)` — duyệt đệ quy dict/list, thay giá trị của các
  TÊN TRƯỜNG nhạy cảm đã biết (`SECRET_KEY_NAMES`, so khớp CHÍNH XÁC không
  phải substring — tránh xoá nhầm `storage_key`/`avatar_key`/`cosmetic_key`
  vốn là ID chứ không phải bí mật) bằng `<redacted>`.
- `loc_bo_theo_gia_tri(van_ban)` — lọc theo MẪU (regex) bất kể tên trường:
  khoá Appwrite dạng `standard_<hex dài>`, header `Bearer <token>`, JWT —
  bắt đúng trường hợp đã xảy ra (bí mật nằm trong `args[2]`, một vị trí
  không tên, không thể liệt kê hết trước).
- `thong_diep_loi_an_toan(body, status_code)` — hàm DÙNG CHUNG mới cho mọi
  script/adapter tương lai, thay vì mỗi nơi tự viết lại logic trích message.

Đã nối `thong_diep_loi_an_toan` vào cả 6 file kể trên (thay logic trích
`message` cục bộ bằng lời gọi hàm dùng chung) — hành vi quan sát được
KHÔNG đổi cho lỗi bình thường, chỉ thêm một lớp lọc theo mẫu phòng khi
`message` vô tình chứa chuỗi giống bí mật.

### 13.3 Kiểm tra các đường khác theo đúng danh sách yêu cầu

- **subprocess/curl verbose**: quét toàn bộ `scripts/*.py`/`server/*.py` —
  KHÔNG tìm thấy lời gọi `subprocess` nào chuyển secret qua tham số dòng
  lệnh (rủi ro lộ qua danh sách tiến trình), KHÔNG tìm thấy `curl -v`/
  `--verbose` nào trong repo.
- **BYOP/OAuth token** (`image_byop_service.py`): đã xác nhận lại — thông
  điệp lỗi (`ByopExchangeFailed`, ...) đều là chuỗi CỐ ĐỊNH viết tay, không
  bao giờ nhúng body/token thật của Pollinations.
- **Provider lỗi khác** (`image_provider_registry.py`,
  `translation_provider_registry.py`): đã có `_thong_diep_loi_an_toan` kiểu
  ánh xạ mã trạng thái → câu cố định, không đổi.

### 13.4 Test hồi quy mới (`server/tests/test_secret_redaction.py`, 17 test)

Quan trọng nhất: `test_tai_hien_su_co_that_apikey_trong_trace_long_nhau` —
tái hiện CHÍNH XÁC hình dạng response đã gây rò rỉ thật (message ở ngoài,
`apiKey` nằm sâu trong `trace[0]["args"][2][2]["apiKey"]`) và xác nhận giá
trị bí mật không còn xuất hiện sau khi lọc. Cộng thêm test riêng cho từng
loại được liệt kê: `X-Appwrite-Key`, `Authorization`, API key (cả hai cách
viết), BYOP/OAuth token, khoá mã hoá, cookie/session — và một test xác nhận
KHÔNG lọc nhầm trường ID hợp lệ có hậu tố `_key`.

### 13.5 Quét lịch sử git (chỉ báo cáo LOẠI + đường dẫn, không giá trị)

Quét toàn bộ lịch sử (`git log --all -p`) của nhánh này và các nhánh tổ tiên
cho các dạng bí mật: khoá Appwrite (`standard_`/`console_` + hex dài), JWT,
header `Bearer`, khối PEM private key, gán biến `*_KEY=`/`*_SECRET=`/
`*_PASSWORD=`/`*_TOKEN=` có giá trị dài không phải placeholder, khoá AWS
(`AKIA...`).

**Kết quả: KHÔNG tìm thấy bí mật nào bị commit** trong toàn bộ lịch sử đã
quét. Các chuỗi dạng "secret" duy nhất từng xuất hiện trong lịch sử là dữ
liệu test cố ý viết tay từ trước (vd `tok-secret-value` trong
`tests/mocks.py` của desktop app — giá trị giả, không phải khoá thật).

### 13.6 Kiểm chứng cuối

Backend **2145/2145** (2128 cũ + 17 test mới), frontend **563/563**,
typecheck/lint sạch, build thành công.

## 14. Follow-up: DNS `appwrite-dev.fanfic.world` — CHƯA phân giải

Bạn báo đã cấu hình bản ghi A `appwrite-dev.fanfic.world → 35.225.209.115`.
Kiểm tra thật qua **hai resolver công khai độc lập** (Google 8.8.8.8,
Cloudflare 1.1.1.1), lặp lại nhiều lần cách nhau ~15-20 phút: cả hai đều trả
**NXDOMAIN** ("Non-existent domain") cho subdomain này. Zone gốc
`fanfic.world` xác nhận CÓ cấu hình DNS thật (nameserver Cloudflare, apex
domain phân giải bình thường) — nên đây không phải lỗi toàn zone, chỉ riêng
bản ghi con `appwrite-dev` chưa thấy. Vì zone đã dùng Cloudflare (thường
gần như tức thời, không có độ trễ TTL truyền thống), khả năng cao là bản ghi
chưa thực sự được lưu, sai chính tả subdomain, hoặc đang ở trạng thái nào đó
chưa active — **không phải vấn đề lan truyền cần chờ thêm**.

**Vì lý do này, các mục sau CHƯA thực hiện** (phụ thuộc domain phân giải
được, thử Let's Encrypt lúc domain chưa phân giải sẽ chỉ thất bại và phí một
lượt thử): cấu hình Traefik/Appwrite cho `https://appwrite-dev.fanfic.world`,
xin/xác minh chứng chỉ TLS, xác nhận redirect HTTP→HTTPS, đổi
`server/.env.selfhost` sang endpoint HTTPS mới.

**Đã hoàn thành trong lần này (không phụ thuộc DNS)**:

- **Khôi phục sau khởi động lại VM — đã kiểm chứng THẬT** (không chỉ đọc
  cấu hình): chạy `gcloud compute instances reset`, đợi SSH sống lại, đợi
  `appwrite-selfhost.service` tự chuyển `active` — **không cần can thiệp
  thủ công**. Toàn bộ ~30 container lên lại đầy đủ, tất cả healthcheck qua,
  0 container exited, 0 restart loop (xác nhận qua `uptime` chỉ "1 min" lúc
  kiểm — đúng là sau reboot thật). Traefik cũng route đúng ngay sau reboot
  lần này (không tái diễn lỗi đua thời điểm khởi động đã gặp lần đầu).
- **Smoke test lại qua backend thật**: đăng ký mới, gọi
  `POST /api/progress/read` hai lần cùng payload → `streak.current_streak=1`
  (không phải 2, đúng idempotent), leaderboard/cosmetics đều 200.
- Backend 2145/2145, frontend 563/563, typecheck/lint sạch, build thành
  công (mục 5 ở trên) — chạy lại sau reboot, không phải chỉ trước đó.

**Cần bạn xác nhận lại**: kiểm tra bản ghi DNS trên Cloudflare dashboard
(đúng tên `appwrite-dev.fanfic.world`, đúng loại A, đúng giá trị
`35.225.209.115`, trạng thái Proxied hay DNS-only — Proxied có thể ảnh
hưởng cách Let's Encrypt HTTP-01 challenge xác minh vì traffic đi qua
Cloudflare trước khi tới VM). Sau khi xác nhận và phân giải được thật, chạy
lại các mục 2-5/8 còn thiếu ở trên.

