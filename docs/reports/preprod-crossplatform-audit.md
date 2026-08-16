# Kiểm toán Cross-platform/Windows test robustness (Phase 15)

Phạm vi: tìm các chỗ code/test/tài liệu giả định line-ending hoặc shell POSIX
mà có thể vỡ trên checkout Windows (`core.autocrlf=true`) hoặc PowerShell/
cmd.exe — cùng dạng lỗi đã tìm thấy và sửa trước đó ở
`web/tests/admin-trusted-sources.test.mjs` (commit `a0420e6`: helper `read()`
không chuẩn hoá CRLF -> LF trước khi so khớp chuỗi chính xác chứa `\n`).

## 1. `web/tests/*.test.mjs` — readFileSync + so khớp chuỗi chứa `\n`

Đã rà 31 file test dùng `readFileSync` (utf8) để đọc mã nguồn thật rồi khẳng
định bằng `assert.match`/`.includes`/`.indexOf`. Phân loại:

- **10 file đã tự chuẩn hoá CRLF -> LF** trong helper `read()` (dùng
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
  `ui`) — về mặt helper thì có CÙNG lỗ hổng lý thuyết, NHƯNG đã soát kỹ từng
  khẳng định so khớp chuỗi/`indexOf`/`.includes` chứa `\n` literal (dạng đúng
  gây lỗi ở `admin-trusted-sources.test.mjs`) và **không tìm thấy trường hợp
  nào khác** dùng chuỗi chính xác (double/single-quote hay template literal)
  có `\n` nhúng bên trong so khớp với `indexOf`/`.includes`. Toàn bộ so khớp
  đa dòng còn lại trong các file này đều dùng regex với `\s*`/`[\s\S]` (khoảng
  trắng bất kỳ, đã bao trọn `\r`), nên AN TOÀN với CRLF lẫn LF. Ví dụ đại
  diện: `admin.test.mjs:156` (`/Truyện đã xuất bản vẫn\s*\n?\s*công khai/`),
  `fanfic-first-shell.test.mjs:103`, `motion-v2.test.mjs:219`,
  `m3-m4.test.mjs:199`, `ui.test.mjs:356-357` — tất cả dùng `\s*\n?\s*`
  (khoảng trắng bất kỳ + newline tuỳ chọn + khoảng trắng bất kỳ), không phải
  `\n` trần.
- Rà toàn bộ `.split("\n")` (5 chỗ: `admin-analytics-ai-credits-system-
  phase7.test.mjs:71`, `fantasy-identity.test.mjs:51,93`, `m3-m4.test.mjs:247`,
  `ui.test.mjs:815`) — chỉ dùng để lọc dòng bằng `regex.test(line)` hoặc
  `.includes(...)`, không có so sánh bằng-tuyệt-đối từng dòng (`assert.equal`)
  nên `\r` thừa cuối dòng không ảnh hưởng kết quả. Không có regex nào dùng
  anchor `$` cuối dòng (thứ sẽ vỡ nếu dòng có `\r` thừa).
- Đã tìm CHÍNH XÁC 1 chỗ dùng `.indexOf("...\n...")` với `\n` trần (không
  `\s*`): `admin-trusted-sources.test.mjs:94` — đây LÀ chỗ đã được sửa trước
  đó (helper `read()` chuẩn hoá CRLF trước khi hàm này chạy). Không tìm thấy
  bản sao/biến thể nào khác của lỗi này ở file test khác.

**Kết luận mục 1**: Không tìm thêm lỗi CRLF/LF nào khác ngoài lỗi đã biết và
đã sửa trước đó. Các file dùng helper `read()` không chuẩn hoá CRLF về lý
thuyết có cùng rủi ro cấu trúc, nhưng KHÔNG có khẳng định nào trong chúng thực
sự phụ thuộc vào `\n` chính xác — nên KHÔNG có bug thật cần sửa thêm. Không
sửa gì thêm ở mục này (không có lỗi để sửa).

## 2. `server/tests/*.py` — đọc file rồi so sánh nội dung/hash

SẠCH, về cấu trúc miễn nhiễm. Toàn bộ chỗ đọc file trong `server/tests/*.py`
dùng `Path.read_text(encoding="utf-8")` (13 file: `test_dependencies.py`,
`test_env_loading.py`, `test_free_tier_guards.py`, `test_gce_worker_deploy.py`,
`test_local_voice_allowlist.py`, `test_limits.py`, `test_oauth.py`,
`test_nghitts_web_labels.py`, `test_staging_smoke_script.py`,
`test_validate_models.py`, `test_worker_deploy.py`, v.v.) — mặc định
`newline=None` của Python tự bật **universal newlines**: `\r\n`, `\r`, `\n`
đều được dịch về `\n` ngay khi đọc, khác hẳn `fs.readFileSync(..., "utf8")`
của Node (giữ nguyên byte, không dịch line-ending). Vì vậy dạng lỗi CRLF-vs-LF
y hệt bên Node KHÔNG THỂ xảy ra ở đây trừ khi ai đó chủ động mở file bằng
`newline=""` hoặc chế độ nhị phân (`"rb"`/`read_bytes()`) rồi so sánh với
chuỗi có `\n`. Đã rà toàn bộ: chỉ có 1 chỗ dùng `read_bytes()`
(`test_progress_telemetry.py:75`, ghép byte audio WAV — không liên quan tới
so khớp text). Không tìm thấy `newline=""` nào trong `server/`. Không sửa gì
(không có gì để sửa).

## 3. Script/tài liệu giả định shell POSIX trên máy Windows

Chỉ ghi nhận, KHÔNG sửa (theo yêu cầu — đây là việc quyết định phong cách tài
liệu, không phải lỗi runtime cụ thể):

- `CLAUDE.md:25` —
  ```
  QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe -m unittest discover -s tests -t .
  ```
  Cú pháp `VAR=value lenh` (tiền tố biến môi trường) là cú pháp POSIX
  shell/Git Bash, KHÔNG chạy được trực tiếp trong PowerShell thuần (`$env:X=`)
  hay `cmd.exe` (`set X=... && lenh`), dù đường dẫn `.\.venv\Scripts\...` lại
  là cú pháp Windows. Khối lệnh gắn nhãn ```bash``` nên chỉ chạy đúng khi qua
  Git Bash — không rõ ràng nếu người đọc chạy trong PowerShell. Mức: MINOR
  (không phải lỗi runtime, chỉ gây nhầm khi copy-paste sai shell).
- `docs/DEV_SELFHOST_APPWRITE.md:45` —
  `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010 npm run dev` — cùng dạng, cùng
  mức MINOR.
- `docs/HANDOFF.md:290` — `PYTHONPATH=. python scripts/staging_smoke.py ...`
  — cùng dạng, cùng mức MINOR.
- `deploy/README.md` (dòng 17, 119, 122, 125) có nhiều lệnh dạng
  `FAS_INLINE_WORKER=false python -m uvicorn ...` — nhưng đây là tài liệu
  triển khai Render.com (container Linux), KHÔNG phải lệnh chạy trên máy dev
  Windows này — ĐÚNG Ý ĐỒ, không phải bug, loại khỏi danh sách.
- `scripts/install_gce_worker.sh` là shell script Bash — nhưng chạy TRÊN VM
  GCE (Linux), không chạy cục bộ trên Windows — ĐÚNG Ý ĐỒ, không phải bug.
- Không tìm thấy `.bat` nào giả định cú pháp POSIX (`run_app.bat`,
  `build_app.bat`, `run_gradio.bat`, `.venv/Scripts/activate.bat` đều đúng cú
  pháp `cmd.exe`).

## 4. Python dùng `/` cứng thay vì `pathlib`/`os.path.join`

SẠCH. Đã rà `desktop_app/`, `server/`, `scripts/`, `capcut_tts_api/`, `app.py`
(loại trừ `.venv/` — thư viện bên thứ ba không thuộc phạm vi sửa). Mọi chỗ
dùng `f"{...}/{...}"` hay `"...+ "/" + ..."` tìm được đều là:
- URL API (`f"{BASE}/api/..."`, OAuth callback, YouTube API, R2 signer scope
  string `f"{date_stamp}/{VOD_REGION}/..."`) — URL/AWS SigV4 scope LUÔN dùng
  `/` bất kể OS, ĐÚNG.
- Khoá lưu trữ object storage kiểu S3/R2 (`"covers/abc.jpg"`,
  `"audio/dung.mp3"`, `"avt/u1.png"`) — khoá S3 luôn dùng `/`, không phải
  đường dẫn hệ điều hành, ĐÚNG.
- Khoá `QSettings` (`"output/dir"`, `"tts/rate"`, `"ui/theme"`, ...) — đây là
  khoá phân cấp nội bộ của Qt `QSettings`, không phải đường dẫn file, ĐÚNG.
- `translation_import.py:139`: `zf.read("word/document.xml")` — đường dẫn
  BÊN TRONG file zip (.docx), định dạng OOXML luôn dùng `/`, ĐÚNG (không phải
  đường dẫn hệ điều hành cục bộ).

Không tìm thấy chỗ nào ghép đường dẫn file hệ điều hành cục bộ bằng `/` cứng
thay vì `os.path.join`/`pathlib`. `desktop_app/output_manager.py` và các
provider dùng `pathlib`/`os.path.join` nhất quán. Không sửa gì.

## 5. Biên dịch/type-check xác nhận không có hồi quy cross-platform

- `.\.venv\Scripts\python.exe -m compileall -q app.py desktop_app server tests`
  → thoát mã 0, không lỗi.
- `cd web && npm run typecheck` (`tsc --noEmit`) → không lỗi, không cảnh báo.

## Tổng kết theo mức độ

| Hạng mục | Kết quả | Mức độ |
|---|---|---|
| 1. Test JS đọc file + so khớp `\n` | Sạch, không tìm thêm bug ngoài bug đã sửa trước đó | — |
| 2. Test Python đọc file + so sánh nội dung | Sạch (miễn nhiễm cấu trúc nhờ universal newlines) | — |
| 3. Docs/script giả định shell POSIX | 3 điểm MINOR (CLAUDE.md:25, DEV_SELFHOST_APPWRITE.md:45, HANDOFF.md:290) | Minor, chỉ ghi nhận |
| 4. Python dùng `/` cứng thay vì os.path/pathlib | Sạch | — |
| 5. compileall + typecheck | Cả hai sạch, không lỗi | — |

Không có thay đổi code nào được thực hiện trong phase này — không phát hiện
bug thật nào cần sửa (lỗi CRLF/LF đã biết đã được sửa từ trước, trong phiên
xét duyệt tích hợp trước khi nhánh overnight này bắt đầu).
