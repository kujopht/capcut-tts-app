# Fanfic Audio Studio

Ứng dụng **desktop Windows** (PySide6) tạo audio từ văn bản, dùng toàn bộ thư
viện giọng trong `Voice.json` và xử lý **nhiều file hàng loạt**.

- Không web server, không trình duyệt, không localhost.
- Giao diện không bao giờ treo khi gọi API (mọi request chạy trong thread riêng).
- Bản Gradio của giai đoạn trước vẫn được giữ nguyên làm **phương án dự phòng**
  (`legacy_gradio_app.py` + `run_gradio.bat`).

---

## 1. Cài đặt lần đầu (Windows PowerShell)

```powershell
# cd tới thư mục chứa repo này, ví dụ:
cd $HOME\Documents\CapCut-TTS-App

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-gui.txt
```

Yêu cầu: **Python 3.9+** (đã kiểm tra trên 3.12).
Nếu PowerShell chặn script khi kích hoạt `.venv`, chạy một lần:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**ffmpeg (khuyến nghị, không bắt buộc):** chỉ cần khi một văn bản dài bị chia
thành **nhiều phần** và bạn muốn có 1 file MP3 hoàn chỉnh. Không có ffmpeg thì
app vẫn tạo đủ `part_001.mp3`, `part_002.mp3`… và nói rõ là **chưa** ghép được —
không bao giờ báo giả rằng file full đã tạo. Xem mục 8.

---

## 2. Cách chạy

**Nhấp đúp `run_app.bat`** — tự vào đúng thư mục, kích hoạt `.venv`, kiểm tra
package (không cài lại mỗi lần), rồi mở app. Nếu khởi động lỗi, cửa sổ được
giữ mở và chạy lại bằng `python.exe` để in traceback chi tiết.

Chạy tay:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

---

## 3. Kiến trúc

```text
app.py                      # entry point desktop (PySide6)
legacy_gradio_app.py        # bản Gradio dự phòng (giữ nguyên)
desktop_app/
    __init__.py             # tên app, version
    models.py               # dataclass/enum, hằng số timeout, slugify, mask_secret
    voice_catalog.py        # đọc Voice.json động, tìm/lọc/sắp xếp/yêu thích
    text_importer.py        # .txt/.md/.docx, thư mục, kéo-thả, Unicode tiếng Việt
    text_chunker.py         # chia văn bản dài theo đoạn/câu, không cắt giữa từ
    tts_service.py          # gọi API: timeout, poll, 429 backoff, phân loại lỗi
    queue_manager.py        # hàng đợi job (Python thuần, test được độc lập)
    workers.py              # QThread + Signal: nối hàng đợi với giao diện
    output_manager.py        # thư mục kết quả, manifest/report, checkpoint, ghép, ZIP
    result_library.py       # đọc lại kết quả các lần chạy trước
    settings_manager.py     # QSettings, thư mục dữ liệu người dùng, device.json
    theme.py                # Qt stylesheet (dark mặc định + light)
    main_window.py          # 4 trang: Tạo TTS / Hàng đợi / Kết quả / Cài đặt
assets/
    app_icon.ico            # icon nguyên bản (sách mở + sóng âm)
    app_icon.png
    make_icon.py            # script sinh lại icon
tests/                      # 233 unit test, KHÔNG gọi API thật
capcut_tts_api/             # package gốc — KHÔNG bị sửa
```

**Nguyên tắc quan trọng:** `capcut_tts_api` chỉ được dùng để **dựng request đã
ký** (`build_tts_new_request`, `build_query_request`). Phần HTTP do
`tts_service.py` tự quản lý để kiểm soát timeout từng bước, poll và lệnh dừng.
`generate_speech()` **không** được dùng (chờ mù, không kiểm soát timeout).

---

## 4. Bốn trang

### Tạo TTS
- Ô văn bản lớn + đếm ký tự & số phần dự kiến.
- Kéo & thả **nhiều file hoặc thư mục** vào bất kỳ đâu trong cửa sổ.
- `📄 Chọn nhiều file...`, `📁 Nhập cả thư mục...` (`.txt`, `.md`, `.docx`).
- Bảng nguồn: **tên · đường dẫn · số ký tự · số phần · giọng được gán · trạng thái**.
- Xoá một dòng / nhiều dòng / tất cả.
- Thư viện giọng đọc: tìm theo tên & `voice_type` (có/không dấu), lọc theo ngôn
  ngữ, 5 chế độ sắp xếp, ★ yêu thích, chọn nhiều, **Chọn tất cả (đang lọc)**,
  **Bỏ chọn tất cả**, **Tải lại catalog**.
- Gán giọng: cho **tất cả** nguồn, cho **dòng đã chọn**, hoặc bỏ gán riêng.
- **Thử giọng** một câu ngắn — chỉ gọi API khi bạn chủ động bấm nút.
- Tóm tắt: `số nguồn × số giọng = số job`. Trên **50 job** phải xác nhận rõ ràng.

### Hàng đợi
Start · Pause · Resume · Stop · Retry failed · Retry job đang chọn.
Bảng job (nguồn, giọng, trạng thái màu, progress bar từng job, số phần, thời
gian, chi tiết lỗi), progress tổng, và panel Nhật ký.

### Kết quả
Danh sách các lần chạy trước → cây `nguồn / giọng / file`, kèm
**Nghe / Mở MP3** (trình phát mặc định của Windows), **Mở thư mục**,
**Xuất ZIP lần chạy**, **Sao chép đường dẫn**. Chỉ đọc — không bao giờ sửa/xoá
kết quả cũ.

### Cài đặt
Thư mục kết quả · kích thước mỗi phần · tốc độ đọc · số worker · theme ·
đường dẫn ffmpeg · `device.json` · `Voice.json`.

Trạng thái **API / hàng đợi / ffmpeg** luôn hiển thị ở status bar.

---

## 5. Toàn bộ giọng trong Voice.json

Catalog được đọc **động**, không hardcode số lượng hay tên giọng.
Với `Voice.json` hiện tại: **129 bản ghi → 127 giọng** (2 bản ghi trùng
`voice_type` + `resource_id` bị gộp), **10 ngôn ngữ**, trong đó 24 giọng vi-VN.

Mỗi giọng hiển thị **tên hiển thị, ngôn ngữ, `voice_type`, `resource_id`** —
chỉ hiển thị khi dữ liệu có sẵn; bản ghi thiếu `voice_type` bị bỏ qua và được
báo số lượng, các field khác thiếu thì để trống chứ không phỏng đoán.

3 giọng của bản Gradio cũ vẫn còn nguyên: Nhỏ Ngọt Ngào (`BV421_vivn_streaming`),
Cô Gái Hoạt Ngôn (`BV074_streaming`), Review Phim new
(`multi_female_richgirl_uranus_bigtts`).

★ Yêu thích được lưu bằng QSettings (khoá là `voice_type|resource_id` để 2 giọng
trùng `voice_type` không bị lẫn).

**App không bao giờ tự chọn tất cả giọng** — số job = `số nguồn × số giọng` nên
việc đó sẽ tạo rất nhiều request.

---

## 6. Văn bản dài: chia phần & tiếp tục dở dang

- Mặc định tối đa **2.000 ký tự/phần** (đổi được trong Cài đặt: 200–5.000).
- Chia tại **ranh giới đoạn → câu → mệnh đề → khoảng trắng**; **không cắt giữa
  từ**. Chỉ khi một "từ" dài hơn giới hạn mới buộc phải cắt theo ký tự.
- Các phần của cùng một job luôn chạy **tuần tự**, lưu thành `part_001.mp3`,
  `part_002.mp3`…
- **Checkpoint:** `manifest.json` được ghi lại sau **mỗi phần thành công**.
- **Tiếp tục dở dang:** lần chạy sau tự tìm các phần đã xong của cùng nội dung
  (theo SHA-256) + cùng giọng + cùng kích thước phần, sao chép sang lần chạy mới
  và chỉ tạo lại phần còn thiếu. Kết quả lần chạy cũ **không bị sửa hay xoá**.

---

## 7. Hàng đợi & API

- Mỗi cặp **input × voice** là một job.
- Concurrency mặc định **1**, tối đa **2** worker.
- Nghỉ 5 giây giữa các job, 2 giây giữa các phần.

| Bước | Connect | Read |
|---|---|---|
| Tạo task | 8 s | 20 s |
| Kiểm tra task (poll) | 8 s | 12 s |
| Tải audio | 8 s | 30 s |

- Poll tối đa **60 s**, chu kỳ **3 s**.
- Thành công: `success`, `succeed`, `completed`, `done`.
- Thất bại: `failed`, `error`, `cancelled`, `canceled`.
- **HTTP 429:** tự backoff (5s → 15s → 30s), thử lại tối đa **3 lần**, ký lại
  request mỗi lần thử (chữ ký chứa `device-time`), rồi mới báo lỗi. Job sau vẫn
  được chạy.
- **HTTP 403 / shark block:** **dừng cả hàng đợi**, cảnh báo rõ ràng, các job
  còn lại chuyển sang `skipped` — không gửi tiếp hàng loạt request.
- Một job lỗi thường **không** làm dừng các job khác.
- Không exception nào làm đóng ứng dụng.

### Về Stop và Pause

> **Nói thẳng:** app **không thể hủy một HTTP request đang chạy giữa đường**.
> Stop dùng `threading.Event`, chỉ có hiệu lực **sau khi request hiện tại kết
> thúc hoặc hết timeout** (chậm nhất 30 giây ở bước tải audio). Trong lúc nghỉ
> giữa job/phần và giữa các lần poll, lệnh dừng có hiệu lực ngay.
> Pause có hiệu lực ở **ranh giới phần/job**.

Các phần đã tạo luôn được giữ lại, và lần sau tiếp tục được từ đó.

---

## 8. Kết quả

Mặc định: `%USERPROFILE%\Documents\Fanfic Audio Studio\outputs\`
(nếu Documents đã được OneDrive chuyển hướng, app dùng đúng đường dẫn Documents
thật của máy — đổi được trong Cài đặt).

```text
outputs/
  2026-08-06_09-14-02/
    chuong_1/
      nho_ngot_ngao/
        part_001.mp3
        part_002.mp3
        chuong_1_nho_ngot_ngao_full.mp3
        manifest.json
    report.json
```

Mỗi lần chạy là một thư mục dấu thời gian riêng — **không bao giờ ghi đè** lần
trước (trùng giây thì thêm `_2`, `_3`…).

`manifest.json` chứa: SHA-256 nội dung, file nguồn / loại input trực tiếp,
`voice_type`, `resource_id`, ngôn ngữ, tốc độ, kích thước chunk, trạng thái từng
part, `task_id`, đường dẫn audio, thời gian bắt đầu/kết thúc, lỗi, ghi chú ghép.

**Dữ liệu nhạy cảm:** token **không bao giờ** được ghi nguyên văn — chỉ lưu dạng
đã che (`tok…(N ký tự, đã che)`). URL audio chỉ lưu `host/path`, bỏ query string
vì có thể chứa chữ ký. Nội dung `device.json` không hiển thị trong app và không
ghi vào log.

### Ghép file full

- **1 phần:** sao chép trực tiếp, không cần ffmpeg.
- **Nhiều phần:** ffmpeg `concat -c copy`, dự phòng re-encode `libmp3lame 192k`.
- **Không có ffmpeg:** giữ nguyên toàn bộ part, hiện hướng dẫn cài đặt, job ở
  trạng thái *Một phần*, **không** tạo file full giả. Cài ffmpeg rồi bấm
  *Retry* để ghép.

Cài ffmpeg: tải bản *release essentials* tại https://www.gyan.dev/ffmpeg/builds/,
giải nén (ví dụ `C:\ffmpeg\bin\ffmpeg.exe`), rồi trỏ **Cài đặt → Đường dẫn
ffmpeg** tới file đó (hoặc thêm vào PATH và mở lại app).

---

## 9. device.json & dữ liệu nhạy cảm

- App dùng device mặc định của SDK. Nếu bị **403** hoặc **shark block**, vào
  **Cài đặt → Cấu hình API** và nhập `device.json` của bạn.
- File được **copy vào `%LOCALAPPDATA%\FanficAudioStudio\`** — không nằm trong
  Program Files, **không** đóng gói vào EXE, **không** commit vào repo
  (`.gitignore` đã chặn `device.json`, `*.token`, `*.secret`, `*.pem`, `*.key`).
- Thiếu cấu hình thì app hiện hướng dẫn, không crash.

Cài đặt được lưu trong registry `HKCU\Software\FanficAudioStudio`. Muốn dùng
bản **portable** (hoặc để test), đặt biến môi trường `FAS_SETTINGS_FILE` trỏ tới
một file `.ini`.

---

## 10. Build EXE & bộ cài đặt

### EXE

Nhấp đúp **`build_app.bat`** (hoặc chạy trong PowerShell). Script dùng
PyInstaller `--onedir --windowed`, tên `FanficAudioStudio`, gắn
`assets/app_icon.ico`, kèm `Voice.json` + assets, loại trừ gradio/pandas/
matplotlib, và **kiểm tra chắc chắn không lọt `device.json`** vào bản build.

Kết quả: `dist\FanficAudioStudio\FanficAudioStudio.exe`

### Bộ cài đặt

Cần [Inno Setup 6](https://jrsoftware.org/isdl.php). Mở **`installer.iss`** →
**Compile** (hoặc `iscc installer.iss`).

Kết quả: `installer_output\FanficAudioStudioSetup.exe` — shortcut Start Menu,
shortcut Desktop (tuỳ chọn), có entry uninstall, và **không yêu cầu người dùng
cài Python**. Khi uninstall, `outputs` của người dùng và `device.json` trong
AppData **không** bị xoá.

---

## 11. Kiểm tra

```powershell
# Toàn bộ unit test (không gọi API thật)
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v

# Kiểm tra syntax
.\.venv\Scripts\python.exe -m compileall -q app.py legacy_gradio_app.py desktop_app tests assets
```

Test bao gồm: đọc `Voice.json` thật + các file lỗi, tìm/lọc/sắp xếp/yêu thích,
TXT/MD/DOCX + Unicode tiếng Việt + tên file có dấu, chunking (không cắt giữa từ),
`file × voice` job count, pause/resume/stop, retry, checkpoint-resume qua 2 lần
chạy, HTTP 403 (chặn hàng đợi), 429 (backoff, không chặn), timeout,
task thất bại, thiếu audio URL, ghép có/không ffmpeg, ZIP, và smoke test giao
diện PySide6 ở chế độ offscreen.

Test **không bao giờ** ghi vào cài đặt thật: chúng dùng `FAS_SETTINGS_FILE` trỏ
vào file `.ini` tạm.

---

## 12. Bảng lỗi

| `error_kind` | Ý nghĩa | Nên làm gì |
|---|---|---|
| `connect_timeout` | Không kết nối được trong 8 s | Kiểm tra internet/VPN/firewall |
| `read_timeout` | Máy chủ không trả lời kịp | Thử lại, hoặc giảm kích thước phần |
| `network_error` | Lỗi mạng / DNS | Kiểm tra kết nối |
| `ssl_error`, `proxy_error` | Lỗi SSL / proxy | Kiểm tra proxy, chứng chỉ |
| `http_403` | Bị từ chối — **dừng hàng đợi** | Nhập `device.json` riêng |
| `http_429` | Giới hạn tần suất | App tự backoff 3 lần; giảm số worker/job |
| `shark_block` | Hệ thống bảo vệ chặn — **dừng hàng đợi** | Chờ, đổi mạng, cập nhật device |
| `api_error` | API trả `ret` khác 0 | Đọc `error_detail` trong manifest |
| `no_task` | API không trả task | Thử lại |
| `task_missing_fields` | Task thiếu `id`/`token` | Thử lại |
| `task_failed` | Task báo thất bại | Thử lại, đổi/rút ngắn văn bản |
| `poll_timeout` | Hết 60 s chờ | Giảm kích thước phần rồi thử lại |
| `no_audio_url` | Thành công nhưng **không có URL audio** | Xem `error_detail` để biết payload thật |
| `download_error`, `empty_audio` | Lỗi tải audio | Retry job |
| `disk_error` | Không ghi được file | Kiểm tra dung lượng/quyền ghi |
| `read_file_error` | Không đọc được file nguồn | Kiểm tra file, đóng Word |
| `merge_ffmpeg_missing` | Chưa có ffmpeg để ghép | Cài ffmpeg rồi Retry |
| `merge_error` | ffmpeg ghép lỗi | Xem ghi chú; part vẫn còn |
| `stopped` | Bạn đã bấm Stop | Retry để tiếp tục |
| `unexpected` | Lỗi ngoài dự kiến | Gửi `error_detail` để chẩn đoán |

---

## 13. Bản Gradio dự phòng

```powershell
# Nhấp đúp run_gradio.bat, hoặc:
.\.venv\Scripts\Activate.ps1
python legacy_gradio_app.py
```

Mở tại http://127.0.0.1:7860 — vẫn đúng 3 giọng tiếng Việt như giai đoạn trước,
kết quả lưu ở `outputs/` trong thư mục dự án. Cần `gradio` (đã có trong
`requirements-gui.txt`).

---

## 14. Chưa có trong giai đoạn này

Theo đúng phạm vi đã thống nhất: **chưa** có trình soạn tiểu thuyết và **chưa**
có quản lý arc/chương theo tuyến truyện.
