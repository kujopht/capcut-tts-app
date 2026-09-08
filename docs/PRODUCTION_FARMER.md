# Production Farmer — hướng dẫn vận hành

Vòng lặp sản xuất nội dung chạy 24/7 trên máy AWS `t3a.medium`
(`13.212.224.218`), **cùng máy** với `fanfic-worker-prod` và
`fanfic-translation-worker-prod`.

## Máy gặt là người gặt, không phải nơi suy diễn

Đây là ràng buộc trung tâm, và nó do phần cứng quyết định chứ không phải sở
thích: máy có **2 vCPU / 4 GiB**, và ASR đo được **0,96× thời gian thực**.
Một tập 30 phút ăn trọn một trong hai vCPU nửa tiếng.

| Việc | Chạy ở đâu |
|---|---|
| Khám phá nguồn, khử trùng lặp, điều phối, giữ hạn mức | **Máy gặt** |
| Đánh giá chất lượng | Gemini API |
| Tổng hợp giọng đọc | Cloud Run (đã có) |
| Sinh ảnh bìa | Endpoint HTTP ngoài, hoặc nền SVG tất định |
| Bóc lời (ASR) | **Không chạy trên máy gặt** — farmer chỉ *nạp hàng đợi* |

## Hai lằn

```
A. AUDIO CÓ SẴN   nguồn → khử trùng lặp → nạp content_queue → (dừng)
                  orchestrator chạy riêng làm phần còn lại

B. TRUYỆN CHỮ     nguồn → khử trùng lặp → lấy/làm sạch → Gemini duyệt →
                  bản nháp → TTS Cloud Run → ẢNH BÌA → ứng viên xuất bản
```

Lằn B là lằn **thật sự sản xuất** trên máy này: nó không có ASR nên không
nghẽn. Lằn A cố ý dừng ở bước nạp hàng đợi.

## Thứ tự trong lằn là có chủ đích

```
khử trùng lặp TRƯỚC khi lấy  → không tải lại thứ đã có
duyệt TRƯỚC khi sản xuất     → không trả tiền TTS cho rác
kho chính tắc là cổng CUỐI   → không xuất bản ô trống
```

Đầy đủ, theo đúng thứ tự mã chạy:

```
khám phá → khử trùng lặp → lấy nội dung → DUYỆT → bản nháp → TTS
        → bìa đường phục vụ (cố gắng) → KHO CHÍNH TẮC (cổng) → ứng viên
```

## Ba cổng fail closed

Không cổng nào có nhánh "cứ chạy thử xem sao":

1. **Khử trùng lặp** — không hỏi được kho dữ liệu → coi như đã tồn tại, bỏ
   qua. Đoán "chắc chưa có" rồi gặt lại lần hai sẽ tạo bản trùng trên
   production.
2. **Cổng đĩa** — không *đo* được dung lượng cũng là một lần từ chối. Máy này
   nuôi hai worker production; làm đầy đĩa ở đây làm đổ cả hai.
3. **Đánh giá** — không đánh giá được (mạng hỏng, API từ chối, JSON vỡ) →
   **không duyệt**. Khác hẳn "đã đánh giá và bị từ chối", vốn là kết quả bình
   thường.

## Hạn mức

Hai **hình dạng** khác nhau, và sự khác nhau là có thật:

| Hạn mức | Hình dạng | Mặc định | Biến môi trường |
|---|---|---|---|
| Tải về đồng thời | `concurrent` | 2 | `FARMER_MAX_CONCURRENT_DOWNLOADS` |
| Yêu cầu đánh giá | **`per_round`** | 8 | `FARMER_MAX_REVIEW_REQUESTS` |
| Job TTS | **`per_round`** | 3 | `FARMER_MAX_TTS_JOBS` |
| Đĩa trống tối thiểu | ngưỡng | 5 GiB | `FARMER_MIN_FREE_DISK_BYTES` |

Giới hạn *đồng thời* không bảo vệ được chi phí: một farmer đơn luồng sẽ lần
lượt gọi Gemini 10.000 lần mà không bao giờ chạm trần "2 cái cùng lúc". Nên
đánh giá và TTS đếm theo **số lần gọi mỗi vòng**.

Biến môi trường đánh sai (`abc`, `0`, `-5`) → quay về mặc định, **không** mở
toang cổng.

## Triển khai HYBRID — hai máy, hàng đợi kéo

```
   AWS t3a.medium                     Appwrite                Windows laptop
   ──────────────                     ────────                ──────────────
   khám phá nguồn                                             Router V4
   FanFicFare                    review_jobs                  pool Antigravity
   khử trùng lặp     ──ghi PENDING──►  (hàng)  ◄──poll RA NGOÀI──  reviewer
   điều phối                                                   (chọn tài khoản)
   TTS dispatch      ◄──đọc bản án──                          
   R2 / Appwrite
   fanfic-gdrive
```

**Laptop không mở cổng nào.** Nó gọi ra, giành việc, chạy, ghi kết quả. Đó là
lý do hàng đợi nằm ở Appwrite chứ không phải một HTTP endpoint trên máy cá
nhân.

**Router V4 chọn tài khoản.** Farmer không đọc, không chọn, và không bao giờ
biết tài khoản Antigravity nào đã chạy — kết quả chỉ ghi tên *nhà cung cấp*
(`antigravity`). Tính khả dụng, hạn mức/cooldown và thử lại đều là việc của
Router V4.

**Nội dung không nằm trong hàng đợi.** `sample_key`/`verdict_key` trỏ tới R2:
một chương dài vượt giới hạn chuỗi của Appwrite, và nhét nó vào một cột sẽ làm
mọi truy vấn hàng đợi kéo cả nội dung về.

### Máy đánh giá tắt = công việc chờ mãi

Đó là hành vi **đúng**. Farmer thấy `REVIEW_PENDING`, đếm nó vào
`lanes.text.review_pending`, và **không sản xuất gì**. Không có đường rơi về
Gemini API — một bản rơi về âm thầm sang một hạn mức **có trả phí** là đúng
thứ đã được nói không.

Một lần `agy` hỏng trả công việc về `PENDING` chứ không phải `FAILED`: sự cố
tạm thời của máy đánh giá không phải một phán xét về tác phẩm.

### Chạy máy đánh giá (trên Windows)

```bash
python scripts/router_review_worker.py --dry-run --once   # giành rồi trả lại
python scripts/router_review_worker.py --once             # một lượt thật
python scripts/router_review_worker.py                    # poll liên tục
```

## Kho sản xuất chính tắc

`FanficWorld/archive/` là **LEGACY** và được để yên: raw scraping, rendered
cũ, backup hạ tầng. Không đổi tên, không sắp xếp lại.

Sản phẩm **mới** đi vào `FanficWorld/production/`:

```
works/fanfic-tts/     works/existing-audio/     works/chinese-media/
quarantine/           rejected/                 manifests/
```

Mỗi tác phẩm được duyệt có **một** thư mục chính tắc và bộ tên cố định:

```
manifest.json · source/original.* · text/normalized.txt
transcript/transcript.json · subtitles/vi.srt · audio/vi.mp3
artwork/cover.webp · artwork/background.webp
```

### Gemini chuẩn hoá siêu dữ liệu; MÃ đặt tên

Đây là ranh giới quan trọng nhất của phần này, và nó là một *tính chất* chứ
không phải sở thích:

> Cùng một tác phẩm chạm qua hai lần đánh giá có thể ra hai tiêu đề hơi khác
> ("Lều chõng" / "Leu Chong" / "Lều Chõng (bản đầy đủ)"). Nếu tên thư mục bám
> vào tiêu đề, một lần **thử lại** sẽ đẻ ra thư mục thứ hai cho cùng tác phẩm
> — đúng điều khử trùng lặp tồn tại để ngăn.

Nên định danh được dẫn ra từ **danh tính nguồn**, thứ không đổi:

| Thứ | Nguồn |
|---|---|
| `work_id` | `sha256(bucket + canonical_url)` — tất định, ổn định mãi mãi |
| slug thư mục | **đường dẫn URL**, không phải tiêu đề |
| thùng (`bucket`) | **lằn sản xuất** (mã biết), không phải `content_type` của model |

Gemini trả về: canonical/display title, fandom, category, author, language,
content type, completeness, quality score, tags, và quyết định
`approve`/`quarantine`/`reject` kèm lý do. **Không** trường nào trong số đó
chạm vào một đường dẫn.

Điểm thấp hơn ngưỡng nhưng model nói "approve" → hạ xuống **quarantine**, không
phải reject: model thấy nó dùng được, chỉ là chưa đạt ngưỡng tự động — đó là
việc cho người xem lại.

`manifest.json` giữ **nguyên vẹn** bản gốc (tiêu đề nguồn, URL, provider ID,
hashes, toàn bộ metadata thô) bên cạnh bản chuẩn hoá. Nếu sau này phép chuẩn
hoá đổi, còn đối chiếu được.

### Ảnh bìa + nền là cổng cứng

`artwork/cover.webp` **và** `artwork/background.webp` đều phải có trước
READY/PUBLISHABLE. Thiếu một cái → chưa xuất bản được.

Sinh bằng **ffmpeg**, không phải Pillow: Pillow không có trong venv máy sản
xuất, ffmpeg thì có trên cả hai máy. Thêm một gói Python vào một venv thuộc
root trên máy đang chạy sản xuất là một thay đổi hạ tầng thật; gọi một nhị
phân đã có thì không. Màu dẫn ra từ `sha256(work_id)` nên chạy lại ra đúng
ảnh cũ.

### Bìa đường phục vụ KHÁC cổng này, và không phải cổng

`CoverGate` gắn một `MediaAsset` vào bản ghi novel bên Appwrite. Đó là một
cơ chế **khác** và nó **cố gắng**, không chặn.

Lý do là một sự thật khó chịu: `MediaAssetStore` là một `Protocol` mà bản
triển khai duy nhất là `MockMediaAssetStore` — `AppwriteMetadataStore` không
có `list_assets`. Trên máy sản xuất bước này ném `AttributeError` **mỗi
lần**. Khi nó còn là cổng, hai tác phẩm đã được duyệt 82 và 78 điểm đã tạo
novel, đã xếp TTS, rồi dừng im lặng — và vì khử trùng lặp xét theo novel đã
tồn tại nên chúng **không bao giờ được thử lại**.

Cổng thật phải **kiểm chứng được**: hai tệp `.webp` có thật trong kho chính
tắc, đọc được bằng một lần liệt kê object.

## Lưu trữ Drive là gương, không phải đường phục vụ

| Vai | Nơi |
|---|---|
| **Phục vụ** (người dùng đọc/nghe) | R2 + Appwrite |
| **Gương bền vững** | Google Drive, remote chính tắc `fanfic-gdrive` |

`server/farmer/drive_archive.py` chỉ `copy` — không `sync`, `move`, `delete`,
`purge`, và không bao giờ chạm tới R2. Có bài test đọc **cây cú pháp** để chặn
điều đó: `sync` ở đây sẽ biến một lỗi cục bộ thành mất dữ liệu trên bản lưu
trữ.

Drive hỏng → `ARCHIVE_PENDING` + thử lại vòng sau. **Không** xoá, **không**
làm hỏng một object R2 hợp lệ.

## Chạy

```bash
# một vòng rồi thoát — dùng cho lô có kiểm soát
/opt/fanfic-audio/.venv/bin/python -m server.farmer --once

# không ghi gì: chỉ khám phá + khử trùng lặp + báo cáo
/opt/fanfic-audio/.venv/bin/python -m server.farmer --dry-run

# xem trạng thái hiện tại
/opt/fanfic-audio/.venv/bin/python -m server.farmer --status

# chạy mãi (systemd gọi kiểu này)
sudo systemctl enable --now fanfic-farmer
journalctl -u fanfic-farmer -f
```

## Cài đặt lên máy AWS

Hai bước dưới đây cần `sudo` và một **bí mật** — đó là lý do chúng nằm ở đây
thay vì được chạy tự động. Kho mã ở `/opt/fanfic-audio` thuộc user `fanfic`,
và `worker-prod.env` **cố ý không đọc được** bởi `ubuntu`.

```bash
ssh -i <khoá>.pem ubuntu@13.212.224.218

# 1. Mã nguồn
sudo -u fanfic git -C /opt/fanfic-audio fetch origin
sudo -u fanfic git -C /opt/fanfic-audio checkout main
sudo -u fanfic git -C /opt/fanfic-audio pull --ff-only

# 2. Cấu hình farmer (chứa KHOÁ GEMINI — không commit, không in ra)
sudo install -o fanfic -g fanfic -m 600 /dev/null /etc/fanfic-audio/farmer.env
sudo -e /etc/fanfic-audio/farmer.env      # dán nội dung ở mục "Cấu hình"

# 3. Nguồn truyện chữ
sudo -e /etc/fanfic-audio/farmer-text-sources.json

# 4. Dịch vụ
sudo cp /opt/fanfic-audio/deploy/fanfic-farmer.service /etc/systemd/system/
sudo systemctl daemon-reload

# 5. Kiểm TRƯỚC khi bật chạy mãi — một vòng, không ghi gì
sudo -u fanfic env $(cat /etc/fanfic-audio/farmer.env | xargs) \
  /opt/fanfic-audio/.venv/bin/python -m server.farmer --dry-run

# 6. Lô có kiểm soát — một vòng, có ghi
sudo systemctl start fanfic-farmer
sleep 60 && sudo -u fanfic /opt/fanfic-audio/.venv/bin/python -m server.farmer --status

# 7. Chỉ bật chạy mãi khi bước 6 xanh
sudo systemctl enable fanfic-farmer
```

Gỡ nhanh nếu cần: `sudo systemctl disable --now fanfic-farmer`. Farmer không
giữ trạng thái nào ngoài `/var/lib/fanfic-farmer`, nên tắt nó không để lại gì
dở dang — mỗi công đoạn đã ghi vào Appwrite/R2 vẫn nguyên vẹn và
orchestrator/worker vẫn xử lý tiếp bình thường.

## Cấu hình

`/etc/fanfic-audio/farmer.env` (nạp *sau* `worker-prod.env`, nên ghi đè được):

```
FARMER_GEMINI_API_KEY=...        # BẮT BUỘC — không có thì farmer từ chối chạy
FARMER_REVIEW_MODEL=gemini-3.8-flash
FARMER_REVIEW_MIN_SCORE=70
FARMER_MAX_REVIEW_REQUESTS=8
FARMER_MAX_TTS_JOBS=3
FARMER_ROUND_SLEEP_SECONDS=900
FARMER_COVER_ENDPOINT_URL=       # trống = nền SVG tất định
```

Nguồn truyện chữ ở `/etc/fanfic-audio/farmer-text-sources.json` — **ngoài kho
mã**, để thêm một nguồn không phải là một lần deploy:

```json
{"sources": [{"url": "https://...", "title": "...", "author": "..."}]}
```

## Trạng thái cho Router Control Center

`/var/lib/fanfic-farmer/status.json`, ghi **nguyên tố** (`os.replace`) nên
người đọc không bao giờ thấy JSON cắt dở.

Router Control Center chưa tồn tại, nên đây cố ý **không** là một API mà nó
phải gọi đúng cách — bất cứ thứ gì đọc được tệp đều tiêu thụ được.

```json
{
  "schema_version": 1,
  "healthy": true,
  "unhealthy_reason": "",
  "round": {"number": 12, "seconds": 4.1},
  "lanes": {"text": {"discovered": 3, "approved": 2, "published_candidates": 2, ...}},
  "quotas": {"limits": {...}, "in_flight": {...}, "disk": {"free_bytes": ..., "ok": true}},
  "totals": {...}
}
```

`schema_version` tăng khi hình dạng đổi **không tương thích ngược**; thêm
trường thì không tăng.

## Ưu tiên tài nguyên

Unit systemd đặt farmer **dưới** hai worker production: `Nice=10`,
`IOSchedulingClass=idle`, `CPUWeight=20`, `MemoryMax=1G`. Vượt trần thì
systemd giết farmer — cố ý, thay vì để nó đẩy hai worker kia vào swap.

## Chưa làm (backlog, cố ý)

- **Sinh hoạt hình AI** — không nằm trong phạm vi này.
- **Cắt nhỏ video dài** — vẫn là backlog riêng; cổng thời lượng 2 giờ ở
  `media_eligibility` vẫn áp cho lằn A.
- **Lưu trữ bản gốc lên Google Drive** — đường dẫn có sẵn ở
  `scripts/rclone_archive_copy.py`; farmer chưa gọi. Nội dung phục vụ
  production vẫn nằm ở R2 như cũ.
