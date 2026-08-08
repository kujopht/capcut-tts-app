# Runbook — TTS worker chạy 24/7 trên VM

Dành cho việc chuyển TTS worker từ máy Windows cá nhân sang một VM Linux đã có
sẵn (Google Cloud Compute Engine). Vận hành staging nói chung xem
`deploy/RUNBOOK.md`.

**Chưa có gì được triển khai.** Các tệp trong `deploy/` là bản chuẩn bị đã kiểm
tra cú pháp; bước chạy trên VM cần quyền SSH và phải do người vận hành thực
hiện. Xem mục "Còn thiếu gì để chạy được" ở cuối.

---

## 1. Vì sao worker phải rời khỏi máy cá nhân

Ở gói Free của Render không có Background Worker, nên worker đang chạy trên máy
Windows. Ba hệ quả đo được:

| Hạng mục | Trên máy cá nhân | Trên VM |
|---|---|---|
| Máy ngủ / reboot | Job đứng cho tới khi bật lại | Không đổi |
| Job đang chạy khi tắt máy | Chờ hết lease (90s) rồi mới có người nhận | Dừng sạch, hoặc recovery |
| Encoding console | cp1252, đã từng làm worker chết vì một dòng log tiếng Việt | UTF-8 |
| Ai thấy log | Chỉ cửa sổ terminal đang mở | `journalctl`, còn sau reboot |

---

## 2. Yêu cầu trên VM

* **Python 3.12** (khớp với `.venv` đang dùng).
* **ffmpeg** — bắt buộc, không phải tuỳ chọn.

  Chương ra **nhiều hơn một đoạn** thì `server/tts_bridge.py` ghép các phần bằng
  `ffmpeg -c copy`. Thiếu ffmpeg thì job hỏng với `MERGE_ERROR`.

  Cái bẫy: chương ngắn chỉ có **một** đoạn, và một đoạn thì chỉ đổi tên tệp,
  không gọi ffmpeg. `scripts/staging_smoke.py` từng dính đúng bẫy này — chương
  3 câu nên nó **xanh trên một VM thiếu ffmpeg**. Nay mục 8 của bộ nghiệm thu
  cố ý ép ra nhiều đoạn nên lỗi này bị bắt; nhưng thêm `--skip-local-voice` là
  bẫy quay lại. Kiểm tra thẳng cho chắc:

  ```bash
  ffmpeg -version | head -1
  ```

* Ra được Internet tới Appwrite (`*.cloud.appwrite.io`) và R2
  (`*.r2.cloudflarestorage.com`). Worker **không** mở cổng nào và **không** cần
  bất kỳ cổng vào nào — đừng mở firewall cho nó.
* Không cần GPU, không cần âm thanh. `edge-tts` gọi qua mạng, `piper` chạy CPU.

RAM/CPU: worker giữ trong bộ nhớ đúng một đoạn audio đang xử lý. Một VM
`e2-micro` là đủ cho một người dùng; giới hạn thật là mạng, không phải CPU.

---

## 3. Cài đặt

Chạy trên VM, theo thứ tự.

```bash
# 3.1 người dùng riêng, không login được
sudo useradd --system --home /opt/fanfic-audio --shell /usr/sbin/nologin fanfic

# 3.2 mã nguồn
sudo install -d -o fanfic -g fanfic /opt/fanfic-audio
sudo -u fanfic git clone -b feature/web-mvp <URL-REPO> /opt/fanfic-audio

# 3.3 venv — CHỈ phụ thuộc backend, không có PySide6
cd /opt/fanfic-audio
sudo -u fanfic python3.12 -m venv .venv
sudo -u fanfic .venv/bin/pip install -r server/requirements.txt

# 3.4 ffmpeg
sudo apt-get update && sudo apt-get install -y ffmpeg
```

### 3.5 Secret

```bash
sudo install -d -m 0750 -o root -g fanfic /etc/fanfic-audio
sudo install -m 0600 -o root -g fanfic /dev/null /etc/fanfic-audio/worker.env
sudo -e /etc/fanfic-audio/worker.env      # dán nội dung, mẫu ở fanfic-worker.env.example
```

Quyền `0600` chủ sở hữu `root`: systemd đọc `EnvironmentFile=` **trước khi** hạ
quyền xuống `fanfic`, nên worker vẫn nhận được biến, còn tiến trình worker thì
không đọc lại được tệp. Một worker bị chiếm cũng không lấy lại được secret gốc.

**Đừng** `cat` tệp này trong phiên SSH có ghi log, và **đừng** đưa giá trị vào
`systemctl edit` — `systemctl show` in ra tất cả.

### 3.6 Unit

```bash
sudo cp /opt/fanfic-audio/deploy/fanfic-worker.service        /etc/systemd/system/
sudo cp /opt/fanfic-audio/deploy/fanfic-worker-health.service /etc/systemd/system/
sudo cp /opt/fanfic-audio/deploy/fanfic-worker-health.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fanfic-worker.service          # `enable` = tự chạy sau reboot
sudo systemctl enable --now fanfic-worker-health.timer
```

---

## 4. Xác minh sau khi cài

```bash
# đang chạy, và `enabled` (tức là sẽ tự lên sau reboot)
systemctl is-active fanfic-worker && systemctl is-enabled fanfic-worker

# nhịp còn mới -> mã thoát 0
sudo -u fanfic env PYTHONPATH=/opt/fanfic-audio FAS_VAR_DIR=/var/lib/fanfic-audio \
  /opt/fanfic-audio/.venv/bin/python -m server.worker --check

# log khởi động: phải thấy environment=staging và inline_worker=false
journalctl -u fanfic-worker -n 20 --no-pager
```

Bốn thứ phải đúng trong dòng `khoi_dong`:

| Trường | Giá trị bắt buộc | Sai thì nghĩa là |
|---|---|---|
| `environment` | `staging` | Đang trỏ nhầm môi trường |
| `inline_worker` | `false` | Web cũng tự chạy job — sai hình dạng |
| `data_backend` | `appwrite` | Đang dùng kho giả |
| `chay_job_duoc` | `true` | Worker sẽ nhận job rồi không chạy |

Chạy trọn vẹn một lượt nghiệm thu từ máy lập trình (worker trên VM sẽ là bên
nhận job):

```bash
PYTHONPATH=. FAS_ENV_FILE=server/.env.staging python scripts/staging_smoke.py \
  --api https://fas-staging-api-free.onrender.com \
  --web https://fas-staging-web-free.onrender.com
```

Phải ra **82/82** và `attempts=1` — lệnh trên có `--web`, tức là kiểm cả
frontend. Bỏ `--web` thì tổng là **77**; khác số kiểm tra, không phải
khác kết quả.

Bộ nghiệm thu **có** chạy một job bằng giọng chạy trên worker
(`piper:ngochuyen`) với `chunk_chars` nhỏ, cố ý ép ra **nhiều đoạn** để đường
ghép ffmpeg thật sự được chạy. Đó là lý do mục 2 nói ffmpeg là bắt buộc —
trước đây chương smoke chỉ có một đoạn nên một máy thiếu ffmpeg vẫn cho kết
quả xanh.

Máy tạo giọng đang tắt thì thêm `--skip-local-voice`; nhưng khi đó đường ghép
ffmpeg **không** được kiểm, nên đừng dùng cờ này để nghiệm thu một máy mới.

---

## 5. Vận hành hằng ngày

```bash
systemctl status fanfic-worker            # trạng thái
journalctl -u fanfic-worker -f            # log theo thời gian thực
journalctl -u fanfic-worker --since '1 hour ago' | grep -v '"muc": "da_quet"'
sudo systemctl restart fanfic-worker      # dừng sạch rồi lên lại
sudo systemctl stop fanfic-worker         # bảo trì
```

### Dừng sạch nghĩa là gì

`systemctl stop` gửi SIGTERM. Worker **ngừng nhận job mới** rồi chờ job đang
chạy xong, tối đa `FAS_WORKER_GRACE_SECONDS` (mặc định 120s). `TimeoutStopSec`
trong unit là 150s — dài hơn, có chủ ý.

Tăng `FAS_WORKER_GRACE_SECONDS` thì **phải** tăng `TimeoutStopSec` theo. Ngược
lại thì systemd SIGKILL đúng lúc worker đang chờ tử tế: job bị giết giữa chừng
và phải đợi hết lease mới có người nhận lại.

### Cập nhật mã

```bash
cd /opt/fanfic-audio
sudo -u fanfic git pull
sudo -u fanfic .venv/bin/pip install -r server/requirements.txt
sudo systemctl restart fanfic-worker
```

Sau khi đổi **schema** Appwrite thì bắt buộc restart — lý do ở
`deploy/RUNBOOK.md` mục 1.

---

## 6. Log và secret

`server/worker.py::_ghi` in mỗi sự kiện một dòng JSON và **không bao giờ** in
nội dung chương, token, hay khoá object đầy đủ. Dòng `khoi_dong` chứa
`settings.describe()`, vốn chỉ có tên chế độ và cờ boolean
(`appwrite_configured: true`), không có giá trị nào.

journald lấy log từ stdout, nên **đừng** thêm `echo $APPWRITE_API_KEY` vào bất
kỳ script bọc nào. Nếu nghi ngờ đã lộ:

```bash
journalctl -u fanfic-worker --since '7 days ago' | grep -Ei 'key|secret|token|password'
```

Không ra gì là đúng.

---

## 7. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Xử lý |
|---|---|---|
| Service `failed`, exit code 2 | `FAS_ENV` khác `staging` — nạp nhầm cấu hình | Sửa `worker.env`. `RestartPreventExitStatus=2` cố tình **không** restart: lỗi cấu hình restart bao nhiêu lần cũng không khỏi |
| `activating` rồi sập lặp lại, dừng sau 5 lần | `StartLimitBurst` chặn | `journalctl -u fanfic-worker -n 50`, sửa, rồi `systemctl reset-failed fanfic-worker` |
| Job hỏng với `MERGE_ERROR` | Thiếu ffmpeg | `apt-get install ffmpeg`. Mục 8 của bộ nghiệm thu bắt được — trừ khi chạy với `--skip-local-voice` |
| Worker `active` nhưng không nhận job | Vòng quét treo | Timer healthcheck tự restart trong ~3 phút. Kiểm tay: `journalctl -u fanfic-worker-health -n 20` |
| Job kết `running` mãi | Worker chết mà lease chưa hết | Tự khỏi sau 90s: bộ quét nhận lại. Quá 3 lần thì job `failed` kèm lý do đọc được |
| `attempts` > 1 với job chạy bình thường | **Đã sửa** ở vòng này. Nếu tái xuất hiện thì lease/heartbeat lại hỏng — xem `server/tests/test_lease_hardening.py` |

---

## 8. Giới hạn độ dài chương (đã đo)

`chunk_chars` mặc định 2000. Đo bằng `desktop_app.text_chunker.chunk_text`:

| Số ký tự | Số đoạn | Ghi chú |
|---|---|---|
| 2.000 | 1 | **Không gọi ffmpeg** — một đoạn thì chỉ đổi tên tệp |
| 10.000 | 6 | |
| 60.000 | 32 | Cỡ một chương fanfic dài |
| 300.000 | 158 | |
| 1.000.000 | 525 | **Trần cứng**: cột `content` của Appwrite tối đa 1.000.000 ký tự (`scripts/setup_appwrite.py`) |

Những gì **không** giới hạn độ dài chương hiện nay:

* Không có kiểm tra độ dài nào ở API — `ChapterIn.content` không đặt
  `max_length`. Trần duy nhất là cột Appwrite ở trên.
* Không có hạn mức TTS theo người dùng. `Profile.tier` và
  `tts_characters_used` đã có trong `server/domain.py` nhưng **chưa chỗ nào đọc
  tới**. Một chương 1.000.000 ký tự sẽ được nhận và tổng hợp hết.
* Không có điểm nối lại giữa chừng. Worker chết ở đoạn 400/525 thì lần chạy lại
  bắt đầu từ đoạn 1. `JOB_MAX_ATTEMPTS=3`.

**Lease không còn là giới hạn.** Nhịp gia hạn mỗi 30 giây suốt thời gian tổng
hợp, nên một chương ba tiếng đồng hồ vẫn chỉ được nhận một lần. Có test:
`server/tests/test_lease_hardening.py::JobDaiHonLease`.

Đặt hạn mức là quyết định sản phẩm, không phải việc của vòng làm cứng này —
ghi ở đây để lần quyết định sau có số liệu.

---

## 9. Còn thiếu gì để chạy được

Chưa thứ nào trong mục 3 được thực hiện. Cần từ người vận hành:

1. **Tên VM, zone và project GCP** đang dự định dùng.
2. **Quyền SSH** vào VM đó.
3. **URL repository** dùng cho `git clone` ở bước 3.2 (repo đang ở chế độ riêng
   tư — cần deploy key hoặc token chỉ-đọc).
4. **Xác nhận VM có ra được Internet** tới Appwrite và R2.
5. Quyết định: worker trên VM **thay thế** worker máy Windows hay chạy song
   song. Chạy song song thì đúng, không hỏng dữ liệu — claim là nguyên tử và
   worker thứ hai bị từ chối — nhưng hai bản cùng quét là lãng phí và làm log
   khó đọc. Khuyến nghị: dừng bản Windows ngay khi bản VM đã xác minh xong.
