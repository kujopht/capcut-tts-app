# Farmer sản xuất — chứng minh E2E với fanfiction thật (2026-09-08)

Bốn tác phẩm fanfiction **thật** đã đi hết đường dây, từ URL nguồn tới bộ
hiện vật đầy đủ trên R2 và bản gương trên Google Drive.

## Kết quả

| work_id | Tác phẩm | Điểm | READY | Drive |
|---|---|---|---|---|
| `w_48c9…76e` | Always Know Where Your Towel Is | 82 | ✅ | ✅ |
| `w_4de1…e1e` | Let it Ride | 78 | ✅ | ✅ |
| `w_9a24…22f` | With Sprinkles 2: The Quest for More Funny | 74 | ✅ | ✅ |
| `w_746f…9ad` | Fire Bird | 72 | ✅ | ✅ |
| `w_f94d…64a` | Land and Sea | 62 | — | cách ly, đúng ý |

Nguồn: [Twisting the Hellmouth](https://www.tthfanfic.org/) — kho fanfiction
crossover Buffy, mở, lấy được bằng FanFicFare từ địa chỉ AWS.

Mỗi tác phẩm được duyệt có đủ:

```
FanficWorld/production/works/fanfic-tts/<slug>-<work_id>/
    text/normalized.txt
    artwork/cover.webp
    artwork/background.webp
    manifest.json
```

Kiểm chứng độc lập: `python scripts/verify_farmer_production.py --ssh-key …`

```
TONG: 4 tac pham DAY DU bo hien vat va da READY
LEGACY FanficWorld/archive: 240 muc
OBJECT R2 lot vao cay legacy: 0 (phai la 0)
```

## Đường dây đã chạy thật

```
tthfanfic.org → FanFicFare → khử trùng lặp → hàng đợi đánh giá (Appwrite)
   → laptop poll ra ngoài → Router V4 → pool Antigravity → bản án
   → bản nháp (novel + chapter) → Cloud Run TTS → kho chính tắc
   → gương Google Drive → READY
```

Máy laptop **không mở cổng nào**. Nó gọi ra, giành việc, chạy, ghi kết quả.

## Bốn lỗi thật, tìm ra bằng cách chạy chứ không bằng cách đọc

### 1. Lớp kho chính tắc được xây xong rồi để đó

`canonical.py`, `drive_archive.py` và bộ hiện vật chuẩn đều đã có và đã qua
kiểm thử — nhưng **không cái nào được gọi từ `loop.py`**.

Tôi đã bàn giao chúng như một việc đã xong. "Đã xây" không phải "đã nối vào",
và tôi đã báo cáo hai thứ đó như một.

### 2. FanFicFare chỉ được tìm ở đường dẫn Windows

`_fanficfare_binary()` chỉ có bản dự phòng `<venv>/Scripts/fanficfare.exe`.
Trên Linux, dịch vụ systemd chạy với PATH không chứa `<venv>/bin`, nên
`shutil.which` trượt rồi bản dự phòng không bao giờ khớp.

Hậu quả **không phải một lỗi mà là một sự im lặng**:
`resolve_acquisition_route()` luôn trả `"engine"`, nên FanFicFare đã cài vẫn
không bao giờ được chọn. Sau khi sửa: **159 host** được hỗ trợ.

### 3. Cổng bìa luôn đóng trên máy sản xuất

`CoverGate` gọi `store.list_assets(novel_id)`. `MediaAssetStore` là một
`Protocol` mà bản triển khai **duy nhất** là `MockMediaAssetStore` —
`AppwriteMetadataStore` không có phương thức đó.

Nên bước này ném `AttributeError` **mỗi lần**, và vòng lặp `continue`. Đây
không phải "thỉnh thoảng thiếu bìa" mà là một cổng **luôn đóng**, đặt **sau**
khi đã tạo novel và đã xếp TTS.

Cổng thật phải **kiểm chứng được**: hai tệp `.webp` có thật, đọc bằng một lần
liệt kê object. Yêu cầu "phải có tranh trước READY" không bị nới lỏng — nó
được chuyển từ một cổng không bao giờ mở sang một cổng đo được.

### 4. "Đã gặt" được đo bằng bản ghi thay vì bằng hiện vật

Lỗi này **ăn bốn tác phẩm**, và ăn theo kiểu tệ nhất: không ồn ào, không hồi
lại được.

`text_already_farmed` hỏi *"đã có novel chưa"*. Nhưng bản nháp được tạo ở
**giữa** dây chuyền. Một tác phẩm hỏng sau bước đó sẽ có novel mà không có
hiện vật — và từ vòng sau, **chính novel của nó làm nó "trùng lặp" với chính
mình**. Vĩnh viễn.

| Trạng thái | Đo bằng | Hành động |
|---|---|---|
| xong | có `manifest.json` **và** `ready` | bỏ qua |
| đang dở | có novel, chưa có manifest | **chạy tiếp** |
| mới | không có gì | chạy từ đầu |

Bản chạy tiếp dùng lại `novel_id` cũ nên không tạo bản trùng.

### 4b. Và bản vá của tôi tự tạo lại lỗi đó, chỗ khác

Bản vá đầu đặt *"đang chạy tiếp ⇒ lần trước đã xếp TTS rồi"*. Sai — xuất bản
và TTS là hai bước khác nhau. Đo thật ngay sau khi triển khai: hai tác phẩm
vừa đạt READY **không có lấy một job TTS nào**, tức sẽ câm lặng vĩnh viễn.

Sửa: hỏi thẳng kho (`novel_has_tts_job`). Không hỏi được thì **hoãn** một
vòng — đoán "đã có" thì câm lặng và không ai thấy; đoán "chưa có" thì trả tiền
cho job trùng mỗi vòng.

## Hạ tầng đã cài trong đợt này

| Thứ | Cách | Vì sao |
|---|---|---|
| rclone 1.60.1 | kho Ubuntu, apt tự kiểm chữ ký | không dán URL vào một shell đặc quyền |
| cấu hình Drive | `/var/lib/fanfic-farmer/rclone.conf` 0600 | `ProtectHome=true` + `ProtectSystem=strict`; rclone **ghi đè** tệp cấu hình mỗi lần làm mới token |
| FanFicFare 4.61 | venv sản xuất, `root:root 755` | không đổi chủ sở hữu, không nới quyền, không venv thứ hai |
| ảnh bìa/nền | ffmpeg | Pillow không có trong venv sản xuất; ffmpeg thì có trên cả hai máy |

Bí mật đi đúng một đường: **tệp → systemd/ssh-stdin → tiến trình**. Không qua
argv, biến shell, tệp tạm cục bộ, log, hay git. `worker-prod.env` không bị đọc
— hai script kiểm tra lấy khoá R2 qua `systemd-run -p EnvironmentFile=…`, đúng
cơ chế chính dịch vụ farmer đang dùng.

## Trạng thái sản xuất

- `fanfic-farmer` active, **một** bản, `NRestarts=0`
- `fanfic-worker-prod` và `fanfic-translation-worker-prod` **không bị đụng**
- `worker-prod.env` không đổi quyền, không bị đọc
- `FanficWorld/archive` (legacy) — 240 mục, **0** object mới lọt vào
- Hạn mức giữ nguyên: 2 tải đồng thời, 8 đánh giá/vòng, 3 TTS/vòng, sàn đĩa 5 GB

### 5. Một tác phẩm ĐÃ XONG vẫn còn việc — và không ai nhìn lại nó

READY **không** đòi hỏi âm thanh (TTS bất đồng bộ). Nhưng *"đã xong"* lại là
điều kiện để vòng lặp **bỏ qua** một tác phẩm. Nên một tác phẩm đạt READY
trước khi có âm thanh sẽ không bao giờ được nhìn lại.

Đo thật: `Let it Ride` và `Always Know Where Your Towel Is` có job TTS
`completed` và mp3 thật trên R2. `Fire Bird` và `With Sprinkles 2` **không có
job TTS nào** — hậu quả trực tiếp của bản vá số 4b của chính tôi. Chúng đã
READY nên sẽ câm lặng vĩnh viễn, và **không một bộ đếm nào báo điều đó**.

`_doi_soat_am_thanh` chạy trên tác phẩm đã xong và chỉ đọc kho: có mp3 thì
gắn vào manifest, đang chạy thì để yên, **không có job nào thì xếp bù**.

Lại đúng khuôn mẫu *"xây xong rồi để đó"*: `attach_audio` là hàm duy nhất đọc
manifest và **nó không có người gọi** — ở chính module tôi vừa viết, ngay sau
khi phê phán khuôn mẫu đó.

## Còn lại

1. **Bản mp3 không được gương lên Drive.** Phải tải từ R2 về trước, và kích
   thước đáng kể. Manifest ghi khoá R2 nên vẫn truy nguyên được.
2. **`MediaAssetStore` chưa có bản triển khai Appwrite.** Bìa đường phục vụ sẽ
   còn báo lỗi (không chặn) cho tới khi có.
3. **`StartLimitIntervalSec` đặt sai mục** trong `fanfic-farmer.service`
   (`[Service]` thay vì `[Unit]`) — systemd bỏ qua, đã in cảnh báo. Vô hại,
   chưa sửa.
4. **Khám phá cắt theo lô trước khi lọc trùng lặp**, nên một tác phẩm bị cách
   ly vẫn chiếm một suất mỗi vòng.
