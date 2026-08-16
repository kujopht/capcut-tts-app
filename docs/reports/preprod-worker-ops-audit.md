# Phase 14 — Worker/restart/ops audit

Chỉ đọc mã nguồn + tài liệu vận hành (`deploy/`, `docs/`). Không chạm SSH,
không restart worker thật trên staging/production, không sửa hạ tầng GCE.

Phạm vi đọc: `server/worker.py`, `server/translation_worker.py`,
`server/main.py` (healthcheck + `recover_stale_jobs`/sweeper),
`server/config.py`, `server/tests/test_worker_deploy.py`, toàn bộ
`deploy/fanfic-worker*.service`, `deploy/fanfic-worker-health.*`,
`deploy/fanfic-translation-worker-prod.service`,
`scripts/install_gce_worker.sh`, `deploy/RUNBOOK-WORKER.md`,
`deploy/RUNBOOK-PRODUCTION.md`, `docs/GCE-WORKER-CAPACITY.md`,
`docs/HANDOFF.md`.

## Tóm tắt theo 4 mục

| # | Mục | Kết quả |
|---|---|---|
| 1 | Graceful shutdown SIGTERM/SIGINT + stale job | **SẠCH** — đúng thiết kế, có test khoá bất biến |
| 2 | `/api/health`, `/api/ready` phản ánh trạng thái worker | **PHÁT HIỆN (minor, theo đúng ý đồ thiết kế nhưng đáng ghi rõ)** — hai endpoint này KHÔNG biết gì về worker riêng, chỉ nói về tiến trình web |
| 3 | Tài liệu vận hành khớp code | **SẠCH cho staging** — nhưng lộ ra khoảng trống ở mục 4 |
| 4 | `FAS_INLINE_WORKER=false` mà quên chạy worker riêng → có cảnh báo không | **PHÁT HIỆN (moderate)** — im lặng ở lớp code; cơ chế phát hiện (health-timer) chỉ tồn tại cho staging, **không tồn tại cho production** |

Không có bug graceful-shutdown/stale-job nào ở tầng code. Phát hiện đáng
chú ý nhất là một **khoảng trống vận hành** (thiếu file, không phải thiếu
logic): `deploy/` có `fanfic-worker-health.service` +
`fanfic-worker-health.timer` cho worker **staging**, nhưng không có bản
tương đương cho `fanfic-worker-prod.service` lẫn
`fanfic-translation-worker-prod.service`.

---

## 1. `server/worker.py` — graceful shutdown + stale job

**SẠCH.** Đọc trực tiếp `server/worker.py:118-202`:

- `_xin_dung()` (dòng 118-120) là handler chung cho cả `SIGINT`/`SIGTERM`
  (đăng ký ở dòng 161-167), chỉ set một `threading.Event()` — không gọi
  `sys.exit()` ngay, đúng kiểu graceful.
- Vòng lặp chính (`while not _dung.is_set()`, dòng 170-183) dừng nhận job
  mới ngay khi cờ được set (không `recover_stale_jobs()` thêm lần nào).
- Đoạn "dừng sạch" (dòng 185-202): set `api._sweeper_stop`, rồi chờ tối đa
  `GRACE_SECONDS` (`FAS_WORKER_GRACE_SECONDS`, mặc định 120s, dòng 51) cho
  các thread job hiện có tự kết thúc (`_so_job_dang_chay()` dòng 113-115,
  đếm qua `api._job_threads`). Đúng như yêu cầu kiểm: "chờ job đang chạy
  tối đa `FAS_WORKER_GRACE_SECONDS` rồi mới thoát".
- Nếu hết hạn ân hạn mà vẫn còn job chạy (`con_lai > 0`, dòng 193-200):
  worker **KHÔNG** giả vờ đã xong — ghi log `dung_khi_con_job` rồi
  `return 1` (exit code khác 0, để hệ giám sát biết là dừng "bẩn"). Job dở
  dang đó **không** bị đánh dấu `failed` một cách vũ đoán — nó vẫn nằm
  `running` với lease còn hạn, và comment ở dòng 196-199 xác nhận đúng ý:
  "job con lai se duoc worker khac nhan lai sau khi lease het han — dung
  duong recovery da co".

**Nếu bị `kill -9` (không kịp graceful)**: đúng như tài liệu mô tả — job
kẹt ở `running` với lease chưa gia hạn. Đường hồi phục:

- `server/main.py::recover_stale_jobs()` (dòng 2081-2192) quét job
  `RUNNING` có `lease_is_live() == False` (lease hết hạn,
  `JOB_LEASE_SECONDS=90`, phải dài hơn `JOB_HEARTBEAT_SECONDS*3` — cưỡng
  chế cứng ở `server/main.py:406-411`), nhận lại bằng `claim_job()`
  (compare-and-set thật qua transaction Appwrite, dòng 2170), tăng
  `attempts`, và giới hạn `JOB_MAX_ATTEMPTS=3` (dòng 2158-2168) trước khi
  đánh `failed` với `error_kind=worker_lost` và thông báo đọc được cho
  người dùng.
- Ai gọi `recover_stale_jobs()`: chính worker riêng tự gọi mỗi
  `POLL_SECONDS` (mặc định 3s, dòng 48+176) — **không cần** một tiến
  trình khác. Nếu worker A chết hẳn, worker B (nếu có chạy) hoặc chính A
  sau khi được `systemd Restart=always` khởi động lại sẽ tự nhận lại job
  cũ của chính mình sau khi lease hết hạn.
- `FAS_WORKER_STALE_SECONDS` (mặc định `POLL_SECONDS*10+30` = 60s, dòng
  206-207) là ngưỡng cho `python -m server.worker --check` (dòng
  210-236) — đọc tệp `heartbeat.json`, dùng làm healthcheck ngoài (xem
  mục 4). Đây là cơ chế phát hiện worker "treo" (còn tiến trình nhưng
  vòng quét không quay), khác với "job kẹt running" (đã có
  `recover_stale_jobs`).

Không sửa gì — không tìm thấy lỗi.

## 2. `/api/health`, `/api/ready` — có phản ánh trạng thái worker không

**Trả lời thẳng câu hỏi kiểm tra: KHÔNG.** Đọc `server/main.py:619-710`:

- `/api/health` (dòng 624-652) là **liveness của chính tiến trình đang trả
  lời request đó** — cố ý không chạm Appwrite/R2 (comment dòng 629-631).
  Trường `job_lock_ready` (dòng 651) chỉ nói "giao dịch khoá job đã từng
  chứng minh chạy được trên **tiến trình này**" (3 trạng thái null/true/
  false, dòng 640-650) — đây là thuộc tính của `store` (adapter Appwrite),
  **không phải** nhịp tim của worker riêng.
- `/api/ready` (dòng 655-710) kiểm các phụ thuộc đọc/ghi (metadata,
  storage, 4 bảng V2) của **chính tiến trình web**, cũng không đọc
  `heartbeat.json` của worker và không gọi worker qua bất kỳ kênh nào.

Đây **không phải bug** — nó khớp đúng kiến trúc "worker không mở cổng
HTTP nào" đã ghi rõ trong `server/worker.py:53-55` ("mo cong chi de
healthcheck la thu bay khong can thiet") và đúng tách bạch
liveness-vs-readiness kinh điển. Nhưng có một hệ quả cần ghi lại rõ:
**không có endpoint HTTP nào ở web nói được "worker riêng có đang sống
không"** — người vận hành gọi `curl /api/health` hoặc `/api/ready` trên
Render/host của web sẽ luôn thấy "ok"/"ready" ngay cả khi worker (chạy
trên máy/VM hoàn toàn khác) đã chết từ lâu và mọi job đang xếp hàng
`pending` vô thời hạn. Cơ chế đúng để biết worker sống là
`python -m server.worker --check` chạy **trên chính host của worker**
(mục 5 `deploy/RUNBOOK-PRODUCTION.md`) — một lệnh CLI riêng, không qua
HTTP của web. `deploy/RUNBOOK-PRODUCTION.md` mục 6 ("Xác minh sau khi
deploy") cũng chỉ kiểm `inline_worker: false` qua `/api/ready` — tức xác
nhận "web không tự chạy job", không xác nhận "có ai khác đang chạy job
thật".

Không sửa — thay đổi endpoint `/api/health`/`/api/ready` để gọi chéo qua
worker sẽ đòi worker mở cổng HTTP, đúng thứ design đã chủ động từ chối
(và đúng lý do: worker chạy trên VM khác, không có địa chỉ mạng cố định
để web gọi tới). Ghi nhận làm phát hiện tài liệu/vận hành, không phải
lỗi code.

## 3. Đối chiếu tài liệu vận hành (`docs/`, `deploy/`) với code

**SẠCH cho toàn bộ đường staging.** Đối chiếu từng điểm:

| Tuyên bố trong tài liệu | Khớp code? |
|---|---|
| `deploy/RUNBOOK-WORKER.md` mục "Dừng sạch nghĩa là gì": SIGTERM → ngừng nhận job mới → chờ tối đa `FAS_WORKER_GRACE_SECONDS` | Khớp `server/worker.py:185-200` |
| `TimeoutStopSec` phải dài hơn `FAS_WORKER_GRACE_SECONDS` | Khớp — `fanfic-worker.service`: `TimeoutStopSec=150` > `GRACE_SECONDS=120`; **cưỡng chế bằng test** `server/tests/test_worker_deploy.py::DungSachDuocThat.test_timeout_dai_hon_thoi_gian_an_han` |
| "KHÔNG restart web giữa job đang chạy" | Đúng — job chạy trong tiến trình worker riêng khi `FAS_INLINE_WORKER=false`; restart web (Render/uvicorn) không đụng thread worker (thread nằm ở tiến trình khác hẳn). `deploy/RUNBOOK-PRODUCTION.md` dòng 35-37 phát biểu đúng: "API ngủ KHÔNG làm dừng job đang chạy" |
| "PHẢI chạy worker riêng ở production" | Cưỡng chế ở code: `server/config.py:483-493` — `Settings.validate()` **raise `ConfigError` ngay khi nạp module** nếu `FAS_ENV` không phải `development` và `inline_worker=True` mà chưa bật cờ thoát hiểm `FAS_ALLOW_INLINE_WORKER_IN_REAL_ENV`. Không phải chỉ là khuyến nghị trong docs — có rào chắn cứng |
| `fanfic-worker-health.timer` tự `systemctl restart` worker khi nhịp cũ (staging) | Khớp `deploy/fanfic-worker-health.service:37`, có test `HealthcheckDungCach` trong `test_worker_deploy.py` |

**Khoảng trống phát hiện được (tài liệu + `deploy/` không nói một đằng
code làm một nẻo — mà đơn giản là **thiếu file** cho nhánh production):**

- `server/tests/test_worker_deploy.py` (toàn bộ file) chỉ tham chiếu
  `deploy/fanfic-worker.service` + `fanfic-worker-health.{service,timer}`
  — tức **chỉ khoá bất biến cho bản staging**. Không có test tương đương
  đọc `deploy/fanfic-worker-prod.service` hay
  `deploy/fanfic-translation-worker-prod.service`.
- `deploy/RUNBOOK-PRODUCTION.md` mục 5b (cài worker TTS production trên
  GCE) chỉ copy **một** unit (`fanfic-worker-prod.service`) qua
  `scripts/install_gce_worker.sh` — không có bước cài
  `fanfic-worker-health-prod.service`/`.timer` nào, vì **file đó không
  tồn tại** trong `deploy/`.
- Xác nhận bằng grep toàn repo: `fanfic-worker-health` chỉ xuất hiện
  trong 3 chỗ (`test_worker_deploy.py`, `fanfic-worker-health.service`,
  `fanfic-worker-health.timer`, `RUNBOOK-WORKER.md`) — không chỗ nào nhắc
  tới một bản `-prod` của health-timer.
- Hệ quả: `fanfic-worker-prod.service` (và
  `fanfic-translation-worker-prod.service`) có `Restart=always`, bắt
  được **crash** (tiến trình chết hẳn), nhưng **không có gì bắt được
  "treo"** — đúng kịch bản mà chính comment trong
  `fanfic-worker-health.service:3-11` mô tả là lý do cần health-timer:
  "vòng quét kẹt ở một lời gọi mạng không timeout, hoặc thread chính bị
  chặn... tiến trình vẫn 'đang chạy' với systemd trong khi không job
  nào được nhận nữa." Rủi ro này tồn tại y hệt ở production nhưng không
  có cơ chế tự phục hồi tương ứng — chỉ còn cách người vận hành tự chạy
  `--check` bằng tay (mục 5b `RUNBOOK-PRODUCTION.md`, không tự động, không
  lịch trình).

**Mức độ**: minor-to-moderate, không phải lỗi code, không phải rủi ro dữ
liệu (claim/lease/fencing vẫn đúng dù worker treo bao lâu — job chỉ đứng
yên, không hỏng). Đây là khoảng trống **thời gian phát hiện sự cố** ở
production: một worker treo (không crash) sẽ không được `systemd` tự khởi
động lại, và sẽ nằm im cho tới khi người vận hành tình cờ kiểm tra hoặc
người dùng report job đứng yên.

**Không tự sửa** — tạo thêm 2 file unit mới
(`fanfic-worker-health-prod.service`/`.timer` + bản translation tương ứng)
, sửa `scripts/install_gce_worker.sh` để cài chúng, và mở rộng
`test_worker_deploy.py` để khoá bất biến cho bản production là việc có
phạm vi rõ ràng nhưng **không nhỏ** (nhiều file mới + thay đổi script cài
đặt trên máy chủ thật) — vượt ngưỡng "sửa an toàn/nhỏ" của phase này. Ghi
lại làm phát hiện cụ thể để quyết định ở phase release-candidate
(Phase 17) hoặc một phiên riêng.

## 4. `FAS_INLINE_WORKER=false` mà quên chạy worker riêng — có cảnh báo không

**Trả lời: KHÔNG, im lặng ở lớp code.** Không tìm thấy bất kỳ đoạn nào
trong `server/main.py` theo dõi tuổi của job `pending`/`running` để tự
log cảnh báo hay trả lỗi rõ ràng khi không có worker nào nhận job. Cụ
thể:

- `POST /api/jobs` (dòng 2263+) tạo job ở trạng thái `pending` rồi trả về
  ngay — không kiểm tra "có ai đang chạy job không" tại thời điểm tạo.
- Khi `FAS_INLINE_WORKER=false`, web **không** khởi động bộ quét
  (`start_job_sweeper()`, dòng 2207-2224, `if not settings.inline_worker:
  return` — cố ý, vì "Recovery la viec cua `server/worker.py`"). Vậy nếu
  không có tiến trình `server.worker` nào đang chạy thật, **không ai gọi
  `recover_stale_jobs()` cả** — không có sweeper nào để phát hiện gì.
- `server/config.py` có đúng MỘT rào chắn liên quan (dòng 483-493), nhưng
  nó chặn tình huống ngược lại: `inline_worker=True` ở môi trường thật.
  Tình huống được hỏi ở đây — `inline_worker=False` (đúng) nhưng **quên
  khởi động** tiến trình `server.worker` — hoàn toàn không có rào chắn
  tương ứng, vì bản chất nó không thể phát hiện được **từ phía tiến
  trình web**: web không biết gì về việc có worker khác đang chạy hay
  không (đúng thiết kế tách rời, không dùng heartbeat tập trung).
- Hệ quả quan sát được: job sẽ nằm `pending` vô thời hạn, `GET
  /api/jobs/{id}` sẽ tiếp tục trả `pending` mãi mãi mà không có
  `error_kind` nào giải thích, và người dùng chỉ thấy tiến trình tạo
  audio "không bao giờ xong" — không có thông báo lỗi nào phân biệt được
  "đang xếp hàng bình thường" với "không có worker nào tồn tại".

**Cơ chế phát hiện DUY NHẤT hiện có** cho tình huống này không nằm ở
phía web mà ở phía worker/hosting:

1. `docs/GCE-WORKER-CAPACITY.md` mục 5 đề xuất "Tuổi nhịp worker
   (`$FAS_VAR_DIR/worker/heartbeat.json`)" như một trong ba chỉ số nên
   dùng cho autoscale — nhưng tài liệu tự ghi rõ **"Chưa triển khai
   autoscaling"** — đây chỉ là đề xuất, chưa phải cảnh báo thật đang chạy.
2. `fanfic-worker-health.timer` (chỉ có bản **staging**, xem mục 3) tự
   restart worker khi *chính worker đó* còn tiến trình nhưng treo — nhưng
   nó **không** giải quyết được trường hợp "chưa từng khởi động worker
   nào cả", vì `Requisite=fanfic-worker.service` (dòng 17 của
   `fanfic-worker-health.service`) khiến healthcheck tự bỏ qua khi chính
   service đó chưa được enable/start.
3. Production hoàn toàn không có ngay cả cơ chế (2) — xem mục 3.

**Mức độ**: moderate. Đây đúng là kịch bản "người vận hành quên bật
worker riêng ở production" mà câu hỏi kiểm tra nêu — và câu trả lời xác
nhận: hiện tại **im lặng hoàn toàn** ở phía code/web, chỉ có thể phát
hiện bằng cách chủ động kiểm `curl /api/jobs/{id}` của một job cụ thể
(thấy `pending` bất thường lâu) hoặc SSH vào worker host chạy `--check`
tay. Không có cảnh báo chủ động nào (log, email, alert) được kích hoạt tự
động bởi chính sự vắng mặt của worker.

**Không sửa** — thêm một cơ chế cảnh báo (vd. log `canh_bao` khi job
`pending` vượt X giây mà không transition, hoặc alerting ngoài) là một
tính năng mới, không phải một lỗi rõ ràng có thể vá an toàn/nhỏ trong
phạm vi audit này. Ghi lại làm phát hiện cụ thể cho quyết định sau.

---

## Tổng kết BLOCKER / cần xem xét thêm

Không có BLOCKER chặn release liên quan tới graceful-shutdown hay
stale-job — cơ chế lease/claim/fencing đã được kiểm chứng kỹ ở
`server/tests/test_lease_hardening.py` và tài liệu (`docs/HANDOFF.md`
mục "Worker recovery") khớp đúng code.

## Bảng so sánh (không có fix code nào trong phase này)

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Thông báo lỗi khi thiếu `FAS_ENV_FILE` (`server/worker.py`, `server/translation_worker.py`) | Đã có sẵn, đúng thiết kế: dừng hẳn (exit 2) kèm thông điệp nhắc `FAS_ENV_FILE` khi `FAS_ENV` không khớp `--require-env` | Không đổi — xác nhận vẫn nguyên vẹn, không cần sửa |
| Graceful shutdown SIGTERM/SIGINT + chờ `GRACE_SECONDS` | Đã đúng thiết kế | Không đổi — không tìm thấy lỗi |
| Watchdog "worker treo" (health-timer) cho môi trường production | THIẾU — chỉ có bản staging (`fanfic-worker-health.{service,timer}`), không có bản `-prod` | Chưa sửa trong phase này — ghi nhận làm khuyến nghị cho Phase 17 (tạo file mới + mở rộng test, vượt phạm vi "sửa nhỏ") |
| Cảnh báo khi quên chạy worker riêng ở production (`FAS_INLINE_WORKER=false` nhưng không có tiến trình `server.worker`) | Im lặng hoàn toàn ở lớp code/web | Chưa sửa trong phase này — ghi nhận làm khuyến nghị (cần tính năng mới: cảnh báo job `pending` quá hạn), vượt phạm vi audit |
| Tài liệu quy trình backup Appwrite self-host (`~/appwrite/backup.sh`, `RESTORE.md`) đối chiếu compose hiện tại | Không xác minh được sâu (file sống trên VM, không truy cập trực tiếp được) | Không đổi — xác nhận không có mâu thuẫn ở lớp tài liệu accessible từ repo; có bằng chứng gián tiếp (reboot VM thật thành công, mục 15 báo cáo hạ tầng) ủng hộ tính nhất quán |

Hai phát hiện cần cân nhắc trước khi công bố production rộng hơn (không
phải bug, là khoảng trống vận hành):

1. **Thiếu health-timer watchdog cho worker production** (TTS lẫn dịch
   thuật) — chỉ có `Restart=always` bắt crash, không bắt được treo.
   Khuyến nghị: tạo `fanfic-worker-health-prod.{service,timer}` +
   tương đương cho translation worker, theo đúng khuôn
   `fanfic-worker-health.*` hiện có, và mở rộng
   `test_worker_deploy.py` để khoá bất biến cho cả hai nhánh.
2. **Không có cảnh báo tự động khi quên chạy worker riêng ở production**
   — job kẹt `pending` im lặng vô thời hạn. Khuyến nghị (không làm
   trong phase này): log cảnh báo định kỳ ở web khi job `pending` cũ hơn
   một ngưỡng, hoặc một alert ngoài dựa trên chỉ số "tuổi job pending cũ
   nhất" đã được `docs/GCE-WORKER-CAPACITY.md` gợi ý sẵn.

Không có thay đổi code nào được thực hiện trong phase này.

---

## 5. Bổ sung (xác minh độc lập, cùng phase) — quy trình backup có khớp hạ tầng hiện tại không

Máy làm việc này KHÔNG có quyền truy cập trực tiếp VM GCE, nên mục này chỉ
xác minh được ở mức TÀI LIỆU/CODE — đánh dấu rõ phần nào không xác minh được.

- **Không có `docker-compose.yml` nào được commit trong repo này** (đã
  `Glob` toàn repo `**/*compose*.yml` và `**/Dockerfile*` — không có kết
  quả). Điều này ĐÚNG Ý ĐỒ: theo `docs/reports/appwrite-selfhost-gce-
  summary.md` mục 3, Appwrite tự lưu trữ dùng `docker-compose.yml`/`.env`
  CHÍNH THỨC của dự án Appwrite (tải trực tiếp theo tag `1.9.6`), sống trên
  VM tại `~/appwrite/docker-compose.yml` — KHÔNG phải file do repo này quản
  lý. Vì vậy không có gì trong repo để đối chiếu "tên service/volume trong
  compose" — hạ tầng Appwrite hoàn toàn tách biệt khỏi repo ứng dụng.
- **Quy trình backup đã ghi trong tài liệu**: `docs/reports/appwrite-
  selfhost-gce-summary.md` mục 10 — `~/appwrite/backup.sh` (đã chạy thật một
  lần, tạo 566MB tại `~/appwrite/backups/20260816T022120Z`, kèm `RESTORE.md`
  hướng dẫn khôi phục TỪNG VOLUME). Cả `backup.sh` lẫn `RESTORE.md` đều sống
  TRÊN VM, không phải file trong repo — không thể đọc nội dung thật của
  chúng từ máy này để đối chiếu tên volume/service với compose hiện tại.
  **Không xác minh được nội bộ nhất quán của hai file này** (BLOCKED — cần
  SSH vào VM, ngoài phạm vi an toàn của phiên overnight này).
- **Tính nhất quán GIÁN TIẾP có thể xác minh được từ tài liệu**: mục 10 cùng
  báo cáo ghi rõ "Volume Docker là named volume bền vững
  (`appwrite_appwrite-*`)" và mục 15.4 mô tả việc sửa `command:` của service
  `traefik` "trong `docker-compose.yml` (tệp vendor trên VM, không phải file
  repo)" — nghĩa là tài liệu tự nhận thức đúng rằng compose là vendor file
  ngoài repo, không có tuyên bố nào trong tài liệu mâu thuẫn với chính nó về
  tên file/volume.
- **Đã kiểm chứng THẬT một phần liên quan (không phải chạy lại backup)**:
  cùng báo cáo mục 14 xác nhận đã chạy `gcloud compute instances reset` thật
  (khởi động lại VM thật) và service `appwrite-selfhost.service` tự đưa toàn
  bộ ~30 container lên lại đúng, 0 restart loop — đây là bằng chứng GIÁN
  TIẾP mạnh rằng tên service/volume trong compose vendor trên VM vẫn khớp
  với những gì systemd unit mong đợi (nếu lệch tên, `docker compose up -d`
  sau reboot đã thất bại rõ ràng, nhưng không thất bại).
- **Không lặp lại backup/restore thật trong phiên này** — đúng ranh giới an
  toàn được giao (không đụng VM, không phá huỷ dữ liệu dev thật).

**Kết luận mục 5**: tài liệu backup TỒN TẠI, đã CHẠY THẬT một lần (theo báo
cáo trước), và không có mâu thuẫn nào phát hiện được ở lớp tài liệu accessible
từ repo. Không thể xác minh sâu hơn (nội dung `backup.sh`/`RESTORE.md`, tên
volume chính xác) từ máy này — đánh dấu là **giới hạn xác minh (chỉ tài
liệu), không phải BLOCKED nghiêm trọng**, vì bằng chứng gián tiếp (reboot
thật thành công) đã cho tín hiệu tích cực về tính nhất quán hạ tầng.
