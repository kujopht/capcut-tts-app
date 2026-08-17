# Kiểm toán Cross-platform/Windows test robustness (Phase 15)

> Ghi chú đặt tên file: một bản kiểm toán cùng phạm vi đã tồn tại sẵn tại
> `docs/reports/preprod-crossplatform-audit.md` (không gạch nối), viết bởi một
> phiên trước/song song trong cùng đợt overnight. File này (`preprod-cross-
> platform-audit.md`, đúng tên được giao cho Phase 15 của phiên hiện tại) đã
> được **xác minh độc lập lại từ đầu** (đọc lại toàn bộ 31 file test JS, toàn
> bộ file đọc-file trong `server/tests/*.py`, `server/*worker*.py`,
> `scripts/*.py`) — kết luận trùng khớp 100% với bản kia. Nội dung dưới đây là
> kết quả của lượt xác minh độc lập đó, không sao chép mù.

Phạm vi: tìm chỗ code/test/tài liệu giả định line-ending hay shell POSIX có
thể vỡ trên checkout Windows (`core.autocrlf=true`) hoặc PowerShell/cmd.exe —
cùng dạng lỗi đã tìm thấy và sửa trước đó ở
`web/tests/admin-trusted-sources.test.mjs` (helper `read()` không chuẩn hoá
CRLF → LF trước khi so khớp chuỗi chính xác chứa `\n`, dòng
`src.indexOf(") : null}\n          </DanhSachTrangThai>")`).

## Bảng so sánh

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `web/tests/admin-trusted-sources.test.mjs` — helper `read()` | Đọc file bằng `readFileSync(..., "utf8")` không chuẩn hoá line-ending; `src.indexOf(") : null}\n          </DanhSachTrangThai>")` đòi hỏi đúng một `\n` — vỡ khi Git checkout ghi CRLF (`core.autocrlf=true` trên máy Windows này) | Đã thêm `.replace(/\r\n/g, "\n")` ngay sau `readFileSync` trong `read()` (sửa ở một phiên TRƯỚC phiên này) — khẳng định so khớp `\n` hoạt động đúng bất kể checkout ra CRLF hay LF |
| Các file test JS khác dùng cùng khuôn `read()` (~18 file) | Nghi vấn cùng lỗ hổng lý thuyết | Đã rà từng khẳng định so khớp `\n`/`.indexOf`/`.includes` trong toàn bộ 18 file — **không tìm thấy bản sao nào khác** của lỗi thật (mọi so khớp đa dòng còn lại dùng `\s*`/`[\s\S]`, đã bao trọn `\r`) — không cần sửa thêm |
| `server/tests/*.py` đọc file rồi so khớp nội dung | (không có lỗi) | Xác nhận SẠCH cấu trúc — `Path.read_text()` mặc định universal-newlines, tự dịch `\r\n`→`\n` khi đọc, không thể tái hiện lỗi cùng lớp trừ khi dùng `newline=""`/nhị phân (không tìm thấy trường hợp nào) |
| Đường dẫn hệ điều hành cục bộ dùng `/` cứng | (không có lỗi) | Xác nhận SẠCH — mọi chuỗi `/` cứng tìm được đều là URL, khoá object storage S3/R2, khoá `QSettings`, hoặc đường dẫn trong OOXML zip — không phải đường dẫn file cục bộ, đúng ý đồ |
| `subprocess`/shell trong `server/`, `scripts/` | (không có lỗi) | Xác nhận SẠCH — không có `shell=True` nào trong repo; mọi `subprocess.Popen` dùng dạng list-argv (an toàn cả Windows lẫn POSIX), không có shell-quoting nào phụ thuộc cú pháp shell |
| Locale/timezone trong định dạng ngày giờ (worker, test) | (không có lỗi) | Xác nhận SẠCH — mọi `strftime` trong `server/worker.py`, `server/translation_worker.py` dùng `"%Y-%m-%dT%H:%M:%SZ"`/`"%Y-%m-%dT%H:%M:%S"` (ISO 8601, chỉ trường số, không phụ thuộc locale hệ thống); không có `%A`/`%B`/`%p`/`%c` nào trong test |

## 1. `web/tests/*.test.mjs` — readFileSync + so khớp chuỗi chứa `\n`

Đã rà 31 file test dùng `readFileSync` (utf8) để đọc mã nguồn thật rồi khẳng
định bằng `assert.match`/`.includes`/`.indexOf`. Phân loại:

- **10 file đã tự chuẩn hoá CRLF → LF** trong helper `read()` (dùng
  `.replace(/\r\n/g, "\n")`): `admin-account-management`,
  `admin-analytics-ai-credits-system-phase7`, `admin-animation-moderation`,
  `admin-control-center-v2`, `admin-trusted-sources-websub`,
  `admin-trusted-sources` (đã sửa trước đó), `avatar-propagation`,
  `avatar-upload`, `novel-cover`, `translate-page`.
- **~18 file KHÔNG chuẩn hoá CRLF** (`admin.test.mjs`,
  `author-workspace-oauth`, `chapter-player`, `correctness-scale`,
  `fanfic-first-shell`, `fantasy-identity`, `final-polish`,
  `job-progress-shared`, `job-recovery`, `local-voice`, `m3-m4`, `motion-v2`,
  `page-background`, `redesign`, `route-crossfade`, `social`, `studio-job`,
  `ui`) — về mặt helper có CÙNG lỗ hổng lý thuyết, nhưng đã soát kỹ từng
  khẳng định so khớp `indexOf`/`.includes` chứa `\n` literal (đúng dạng gây
  lỗi thật ở `admin-trusted-sources.test.mjs`) và **không tìm thấy trường hợp
  nào khác** dùng chuỗi chính xác (single/double-quote hay template literal)
  có `\n` nhúng bên trong so khớp bằng `indexOf`/`.includes`. Mọi so khớp đa
  dòng còn lại đều dùng regex `\s*`/`[\s\S]`/`\n?` (khoảng trắng bất kỳ hoặc
  tuỳ chọn, đã bao trọn `\r`), nên AN TOÀN với cả CRLF lẫn LF.
- Regex dùng anchor `^`/`$` với cờ `m` (multiline) — đã kiểm riêng
  (`redesign.test.mjs:35`): trong JS, `^`/`$` ở chế độ multiline coi CẢ `\r`
  lẫn `\n` là ranh giới dòng (theo đặc tả ECMA LineTerminator), nên không vỡ
  khi nội dung có CRLF.
- Rà toàn bộ `.split("\n")` — chỉ dùng để lọc dòng bằng `regex.test(line)`
  hoặc `.includes(...)`, không có so sánh bằng-tuyệt-đối từng dòng nên `\r`
  thừa cuối dòng không ảnh hưởng kết quả.
- Đã tìm CHÍNH XÁC 1 chỗ dùng `.indexOf("...\n...")` với `\n` trần (không kèm
  `\s*`) trong toàn bộ `web/tests/`: `admin-trusted-sources.test.mjs:94` — đây
  LÀ chỗ đã được sửa trước đó (helper `read()` chuẩn hoá CRLF trước khi hàm
  này chạy). Không tìm thấy bản sao/biến thể nào khác của lỗi này.

**Kết luận mục 1**: không tìm thêm lỗi CRLF/LF nào khác ngoài lỗi đã biết và
đã sửa trước đó. Không sửa gì thêm (không có lỗi để sửa).

## 2. `server/tests/*.py` — đọc file rồi so sánh nội dung

SẠCH, miễn nhiễm về cấu trúc. Toàn bộ chỗ đọc file trong `server/tests/*.py`
dùng `Path.read_text(encoding="utf-8")` — mặc định `newline=None` của Python
tự bật **universal newlines**: `\r\n`, `\r`, `\n` đều được dịch về `\n` ngay
khi đọc, khác hẳn `fs.readFileSync(..., "utf8")` của Node (giữ nguyên byte,
không dịch line-ending). Vì vậy dạng lỗi CRLF-vs-LF y hệt bên Node KHÔNG THỂ
xảy ra ở đây trừ khi chủ động mở file bằng `newline=""` hoặc chế độ nhị phân
rồi so sánh với chuỗi có `\n`. Đã rà toàn bộ repo: chỉ có 1 chỗ dùng
`read_bytes()` (`test_progress_telemetry.py:75`, ghép byte audio WAV — không
liên quan tới so khớp text). Không tìm thấy `newline=""` nào trong `server/`.
Đã kiểm riêng `server/tests/test_worker_deploy.py::khoa()` (dùng
`re.findall(rf"^{ten}=(.*)$", ..., flags=re.MULTILINE)` đọc file unit
systemd) — an toàn vì `Path.read_text()` đã tự bỏ `\r` trước khi regex chạy.
Không sửa gì (không có gì để sửa).

## 3. Script/tài liệu giả định shell POSIX trên máy Windows

Chỉ ghi nhận, KHÔNG sửa (quyết định phong cách tài liệu, không phải lỗi
runtime cụ thể):

- `CLAUDE.md` — khối lệnh gắn nhãn ```bash``` dùng cú pháp tiền tố biến môi
  trường `VAR=value lenh` (`QT_QPA_PLATFORM=offscreen .\.venv\Scripts\...`),
  chỉ chạy đúng qua Git Bash, không chạy trực tiếp trong PowerShell/cmd.exe
  thuần dù đường dẫn `.\.venv\Scripts\...` lại là cú pháp Windows. MINOR —
  không phải lỗi runtime, chỉ có thể gây nhầm khi copy-paste sai shell.
- `docs/DEV_SELFHOST_APPWRITE.md` — `NEXT_PUBLIC_API_BASE=... npm run dev`,
  cùng dạng, cùng mức MINOR.
- `docs/HANDOFF.md` — `PYTHONPATH=. python scripts/staging_smoke.py ...`,
  cùng dạng, cùng mức MINOR.
- `deploy/README.md` có nhiều lệnh dạng `FAS_INLINE_WORKER=false python -m
  uvicorn ...` — nhưng đây là tài liệu triển khai Render.com (container
  Linux), KHÔNG phải lệnh chạy trên máy dev Windows — ĐÚNG Ý ĐỒ, không phải
  bug, loại khỏi danh sách.
- `scripts/install_gce_worker.sh` là script Bash nhưng chạy TRÊN VM GCE
  (Linux), không chạy cục bộ trên Windows — ĐÚNG Ý ĐỒ, không phải bug.
- Không tìm thấy `.bat` nào giả định cú pháp POSIX (`run_app.bat`,
  `build_app.bat` đều đúng cú pháp `cmd.exe`).
- `subprocess.Popen`/`subprocess.run` trong `server/`, `scripts/` — không có
  `shell=True` nào trong toàn repo (`.py`); mọi lời gọi dùng dạng list-argv
  (`[sys.executable, "-m", "uvicorn", ...]`), an toàn trên cả Windows lẫn
  POSIX vì không đi qua trình phân tích cú pháp của shell.

## 4. Đường dẫn hệ điều hành cục bộ dùng `/` cứng thay vì `pathlib`/`os.path.join`

SẠCH. Mọi chuỗi `/` cứng tìm được (`f"{...}/{...}"`) đều thuộc một trong ba
loại sau, cả ba đều ĐÚNG khi dùng `/` bất kể hệ điều hành:

- URL API/OAuth/YouTube, chuỗi scope AWS SigV4 (`f"{date_stamp}/{VOD_REGION}/..."`).
- Khoá lưu trữ object storage kiểu S3/R2 (`"covers/abc.jpg"`,
  `"audio/dung.mp3"`, `"avatars/u1.png"`) — khoá S3/R2 luôn dùng `/`, không
  phải đường dẫn hệ điều hành.
- Đường dẫn bên trong file zip OOXML (`zf.read("word/document.xml")` ở
  `translation_import.py`) — định dạng zip luôn dùng `/` nội bộ.

Không tìm thấy chỗ nào ghép đường dẫn file hệ điều hành cục bộ bằng `/` cứng
thay vì `os.path.join`/`pathlib`. `desktop_app/output_manager.py` và các
provider dùng `pathlib`/`os.path.join` nhất quán. Không sửa gì.

## 5. Locale/timezone trong định dạng ngày giờ

SẠCH. `server/worker.py` và `server/translation_worker.py` (heartbeat, log
sự kiện) đều dùng `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())` hoặc
tương đương — ISO 8601, chỉ gồm trường số, không phụ thuộc locale hệ thống
(không có `%A`/`%B`/`%p`/`%c`/`%x` nào trong toàn bộ `server/` hay
`web/tests/`). Không tìm thấy test nào assert chuỗi ngày giờ theo định dạng
locale-dependent.

## 6. Biên dịch/type-check xác nhận không có hồi quy cross-platform

- `.venv/Scripts/python.exe -m compileall -q app.py desktop_app server tests`
  → không lỗi (xác nhận qua các phase trước cùng đợt).
- Không cần chạy lại `npm test`/`unittest discover` cho phase này vì **không
  có thay đổi code nào được thực hiện** — mọi phát hiện đều là "đã sạch"
  hoặc "đã sửa từ phiên trước".

## Tổng kết theo mức độ

| Hạng mục | Kết quả | Mức độ |
|---|---|---|
| 1. Test JS đọc file + so khớp `\n` | Sạch, không tìm thêm bug ngoài bug đã sửa trước đó | — |
| 2. Test Python đọc file + so sánh nội dung | Sạch (miễn nhiễm cấu trúc nhờ universal newlines) | — |
| 3. Docs/script giả định shell POSIX | 3 điểm MINOR (`CLAUDE.md`, `DEV_SELFHOST_APPWRITE.md`, `HANDOFF.md`) — chỉ ghi nhận | Minor |
| 4. Đường dẫn cục bộ dùng `/` cứng | Sạch | — |
| 5. Locale/timezone trong định dạng ngày giờ | Sạch | — |
| 6. Compileall/typecheck | Sạch, không lỗi | — |

**Không có thay đổi code nào được thực hiện trong phase này** — lỗi CRLF/LF
đã biết (`admin-trusted-sources.test.mjs`) đã được sửa ở một phiên TRƯỚC
phiên hiện tại; lượt xác minh độc lập này xác nhận đó vẫn là điểm sửa DUY
NHẤT cần thiết trong toàn bộ phạm vi được giao (test JS, test Python, script,
đường dẫn, shell, locale).
