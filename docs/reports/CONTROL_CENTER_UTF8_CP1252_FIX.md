# Sự cố cp1252 — `Router Control Center.exe` chết ngay khi mở

Bằng chứng sửa gốc rễ, chạy trên **EXE đã đóng gói**, dưới **locale của
máy**, không một biến môi trường nào được đặt.

---

## 1. Sự cố, đúng như người dùng gặp

```
Failed to execute script 'desktop' due to unhandled exception:
UnicodeEncodeError: 'charmap' codec can't encode character 'ư'
character maps to <undefined>
  ... desktop.py line 145 -> encodings/cp1252.py
```

`U+01B0` là chữ **ư**. Dòng 145 là `print(f"[desktop] {kh.ly_do}")`, và ở
lần mở đầu tiên `quyet_dinh()` trả về:

```
ly_do = "chưa có backend nào — tự chạy"
```

Bốn ký tự trong câu đó nằm ngoài cp1252: `ư` (U+01B0), `—` (U+2014),
`ự` (U+1EF1), `ạ` (U+1EA1).

**Máy này thật sự là locale hẹp** — đã đo, không phải suy đoán:

| Hạng mục | Giá trị |
|---|---|
| `locale.getencoding()` | `cp1252` |
| `sys.flags.utf8_mode` | `0` (chế độ UTF-8 KHÔNG bật) |
| `sys.getfilesystemencoding()` | `utf-8` (nên tên tệp tiếng Việt vẫn được) |

Nghĩa là **mọi `open()` không có `encoding=` trên máy này dùng cp1252**.

---

## 2. Gốc rễ

`print()` giao chuỗi cho **tầng văn bản** của luồng, và codec của tầng đó
do **locale của Windows** quyết định. Lỗi không nằm ở tiếng Việt và không
nằm ở console — lỗi là **để locale quyết định codec** cho dữ liệu ta đã
biết chắc là Unicode.

**Cách sửa** (`scripts/control_center/ghi_utf8.py`): tự mã hoá sang UTF-8
rồi ghi **BYTE** vào tầng nhị phân của luồng. UTF-8 biểu diễn được mọi
điểm mã Unicode nên phép mã hoá đó **không thể thất bại** — không cần
`errors=` gì cả, và không mất một byte tiếng Việt nào.

### Cách KHÔNG dùng (yêu cầu số 2), và không có cái nào bị dùng

| Cách bị cấm | Có trong mã? |
|---|---|
| `chcp 65001` | không |
| đổi locale Windows | không |
| đòi `PYTHONUTF8` | không — và bộ nghiệm thu giờ **gỡ** biến này ra |
| bọc bằng shell/`.cmd` | không |
| bỏ dấu / phiên âm | không |
| `errors="ignore"` / `"replace"` | không |

Có bài kiểm quét bằng AST cưỡng chế từng dòng trong bảng này.

---

## 3. HAI chỗ, không phải một

Yêu cầu số 4 đòi soi **cả đường khởi động**, không chỉ dòng 145. Việc đó
tìm ra một chỗ thứ hai vẫn còn chết sau khi dòng 145 đã sửa:

| # | Chỗ | Ký tự làm vỡ | Lộ ra khi |
|---|---|---|---|
| 1 | `desktop.py:145` — `print(ly_do)` | `ư` U+01B0 | **bấm đôi**, mọi lần mở đầu |
| 2 | `argparse._print_message` — help/usage | `ứ` U+1EE9 | `--help`, hoặc một cờ sai |

Chỗ thứ hai được xác nhận **trên EXE đã đóng gói** trước khi sửa:

```
Router Control Center.exe --help
  File "argparse.py", line 2627, in _print_message
  File "encodings\cp1252.py", line 19, in encode
UnicodeEncodeError: 'charmap' codec can't encode character 'ứ'
```

Sửa: `BoDocUTF8(argparse.ArgumentParser)` ghi thông điệp bằng byte UTF-8 và
**giữ nguyên** luồng đích (help ra `stdout`, lỗi ra `stderr`).

---

## 4. Soi cả đường khởi động — bằng AST, không bằng mắt

"Đường khởi động trực tiếp" được định nghĩa bằng **bao đóng import** của
`desktop.py`, tính bằng AST: **50 tệp**. Thêm một import mới thì phạm vi
tự nới theo, nên bài kiểm không lặng lẽ hụt đi.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `print()` trong vỏ khởi động | 17 | **0** |
| `sys.std*.reconfigure(errors=...)` | 2 | **0** |
| `open`/`read_text`/`write_text` thiếu `encoding=` | 0 | **0** |
| `subprocess(text=True)` thiếu `encoding=` | 1 | **0** |
| `json.dumps` thiếu `ensure_ascii=False` (không có miễn trừ) | 3 | **0** |
| `argparse` ghi qua tầng văn bản | 2 | **0** |

Bốn chỗ được sửa ngoài `desktop.py`:

1. `desktop_shell.py` — tệp khoá: `ensure_ascii=False`
2. `worker_identity.py` — tệp danh tính: `ensure_ascii=False`
3. `worker_identity.py` — `icacls` chạy với `text=True` **không** `encoding=`:
   giải mã đầu ra bằng codec của locale, và vì cả khối nằm trong
   `except Exception: pass` nên một `UnicodeDecodeError` sẽ **âm thầm** làm
   ACL không được siết. Đầu ra ấy không ai đọc → chuyển sang **nhị phân**.
4. `worker_adapter.py` — nhánh thất bại bỏ sót `ensure_ascii=False` mà
   nhánh thành công ngay dưới đã có.

Sáu chỗ `json.dumps` còn lại được **miễn trừ kèm lý do đã soi** (dấu vân
tay so sánh giữa hai nhịp WebSocket; đã có `.encode("utf-8")` tường minh
ngay sau đó; chỉ đo độ dài rồi bỏ chuỗi đi). Một
miễn trừ **mồ côi** cũng làm bài kiểm đỏ, nên miễn trừ không mục ruỗng
được.

**IPC:** Starlette đã dùng `ensure_ascii=False` + UTF-8 cho cả
`JSONResponse` lẫn `WebSocket.send_json` — đã kiểm mã nguồn gói, không
phải giả định.

---

## 5. Vì sao 19/19 bài kiểm cũ vẫn xanh khi EXE đang chết

`control_center_desktop_acceptance.py` **tự tiêm** vào tiến trình con:

```python
moi = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1",
           PYTHONIOENCODING="utf-8")
```

Đúng hai thứ không được phép dựa vào. Nó đo một môi trường **không người
dùng nào có**: bấm đôi từ Explorer thì không ai đặt biến nào cả.

Giờ bộ nghiệm thu **gỡ** các biến đó ra, và một bài kiểm quét AST (bắt cả
ba hình dạng `dict(env, X=…)`, `{"X": …}`, `env["X"] = …`) chặn chúng quay
lại. Bài kiểm đó có **bài kiểm chống rỗng** của riêng nó.

Bài học lớn hơn Unicode: **một bài kiểm chạy trong môi trường do chính nó
dựng lên chỉ chứng minh được điều gì nếu môi trường ấy là môi trường người
dùng có.**

---

## 6. Bài kiểm chống tái phạm

`scripts/tests/test_control_center_utf8_locale.py` — **42 bài**. Nó
**cưỡng chế** `PYTHONIOENCODING=cp1252:strict` + `-X utf8=0` cho tiến
trình con *để làm hẹp*, rồi **tự xác minh rằng đã làm hẹp được** trước khi
tin bất kỳ kết quả nào:

- kịch bản con tự thoát mã `9` nếu luồng của nó không phải cp1252
- mã **CŨ** (`print`) phải **VẪN chết** trong khung đó — đó là phép chứng
  minh không-rỗng, và nó là phép kiểm đột biến được đóng thành bài kiểm
- mã **MỚI** (`GhiUTF8`) phải sống và giữ đủ byte trong **cùng** khung ấy

Ba câu và mười bốn ký tự yêu cầu nghiệm thu đòi đều có mặt đúng từng chữ.
Một chi tiết đã đo được và đáng ghi: **`â ê ô Â Ê Ô` NẰM TRONG cp1252**
(khối Latin-1), chỉ tám ký tự `ă đ ơ ư Ă Đ Ơ Ư` là ngoài. Ai chỉ kiểm bằng
`â` sẽ có một bài kiểm xanh mà không chứng minh gì.

---

## 7. Nghiệm thu trên EXE ĐÃ ĐÓNG GÓI — 27/27

```
dist/Router Control Center/Router Control Center.exe
13.435.164 byte · thư mục 96 MB
sha256 1a5bd8786bc5950a1c3b5c255f1463a7a38f73c7d411a2fb4b0bdc1828fa9136
```

Trạng thái tiếng Việt được **gieo sẵn TRƯỚC** lần mở đầu tiên (tên dự án,
chat, tên tệp đính kèm), vì sự cố lộ ra đúng ở lúc khởi động — một sổ rỗng
không chứng minh được gì.

| Bước | Kết quả |
|---|---|
| 1 / 1b. cửa sổ WebView2 thật (Chromium, không IE/mshtml) | ĐẠT |
| 2 / 2b. không trình duyệt ngoài; `msedgewebview2.exe` đang chạy | ĐẠT |
| 7 / 7b / 7c. token không lộ; giao diện nạp; WebSocket sống | ĐẠT |
| **7v. tên dự án tiếng Việt** — `Hàng đợi sản xuất` | **ĐẠT** |
| **7w. chat tiếng Việt đã lưu** — `ă â đ ê ô ơ ư Ă Â Đ Ê Ô Ơ Ư` | **ĐẠT** |
| **7x. tên tệp đính kèm** — `Đường dẫn thử nghiệm.csv` | **ĐẠT** |
| **7u. hash + cỡ khớp từng byte** — sha256 `bb6e44e3b5c8…`, 30 byte | **ĐẠT** |
| **7y. nhật ký khởi động là UTF-8 hợp lệ, KHÔNG UnicodeEncodeError** | **ĐẠT** |
| **7z. nhật ký giữ chữ `ư`** — `[desktop] chưa có backend nào — tự chạy` | **ĐẠT** |
| 3 / 3b. dán nhiều dòng không bị chặn; Unicode giữ nguyên | ĐẠT |
| 4 / 5. dán ảnh → thumbnail; kéo-thả PDF | ĐẠT |
| 6 / 6b / 6c / 6d. gửi việc thật; Tasks sống; chi tiết; nhật ký việc | ĐẠT |
| 8 / 9. tệp khoá đúng pid/cổng/token; đóng app thì cổng nhả | ĐẠT |
| 9b / 9c. mở lại: 3 tin nhắn + việc còn nguyên; đính kèm còn xem được | ĐẠT |
| **9d. tiếng Việt còn nguyên sau khi đóng và mở lại** | **ĐẠT** |
| **9e. nhật ký lần mở thứ hai cũng sạch** | **ĐẠT** |

Bước **7z** là bằng chứng trực tiếp nhất: nhật ký của EXE chứa **đúng câu
đã từng làm nó chết**, viết đúng chính tả.

---

## 8. Bộ kiểm

| Bộ | Kết quả |
|---|---|
| `test_control_center_utf8_locale` (mới) + `desktop_shell` + `worker_identity` + `worker_adapter` — các module ĐÃ SỬA | **79/79** |
| `webapi` + `attachments` + `core` + `slice` + `ui` + `allowlist` + `permission_policy` + `router_v4_scheduler` + `router_v3` | **417/417** |
| `tests/test_control_center_gui_*.py` (Qt, offscreen) | **95/95** |
| Nghiệm thu EXE đã đóng gói | **27/27** |

Trong đó `test_control_center_utf8_locale.py` là **42 bài** mới.

---

## 9. CÒN LẠI — cùng lỗi, ba điểm vào GỠ LỖI

Đã **xác nhận bằng cách chạy thật**, chưa sửa, và cố ý báo thay vì tự nới
phạm vi. Cả ba **không** nằm trên đường của `Router Control Center.exe`:

| Lệnh | Ký tự làm vỡ | Mã thoát |
|---|---|---|
| `router-cc --help` (TUI) | `đ` U+0111 | 1 |
| `router-cc-gui --help` (Qt) | `ệ` U+1EC7 | 1 |
| **`router-cc --headless`** | `ả` U+1EA3 | 1 |

`router-cc --headless` là lệnh **có trong tài liệu** cho đường không-TTY,
nên nó đang hỏng trên locale của máy này.

Cách sửa đã có sẵn trong tay và giống hệt: dùng `BoDocUTF8` thay
`ArgumentParser`, và đổi ~11 lời gọi `print()` sang `GhiUTF8`. Nó cần thêm
một tham số `luong=` cho `GhiUTF8` (để giữ `stdout` và `stderr` riêng, vì
`--headless` in JSON ra `stdout` cho `jq`) và một lần build lại. Việc đó
nằm ngoài phạm vi "soi `desktop.py` và đường khởi động của nó", nên nó
đang chờ quyết định.

**Ngoài Control Center**, 196 lời gọi `print()` tiếng Việt trong CLI của
`router_v3`/`router_v4` cùng loại phơi nhiễm — diện rộng hơn nhiều và
không liên quan tới sự cố này.

---

## 10. Một phụ thuộc chưa từng được khai — CI môi trường sạch bắt được

Lần đẩy đầu tiên của bản sửa này làm CI **HỎNG 37 lỗi**, tất cả cùng một gốc:

```
RuntimeError: Form data requires "python-multipart" to be installed.
  ... webapi.py line 213, in dung_app
      @app.post("/api/attachments")
```

`webapi.py` nhận `Form(...)` + `UploadFile` từ `9dff878` (giao diện web
V0.2), và gói `python-multipart` **chưa từng được khai ở đâu cả**.

**Nghiêm trọng hơn vẻ ngoài:** FastAPI kiểm gói này lúc **đăng ký route**,
không phải lúc có request đầu tiên. Thiếu nó thì `dung_app()` ném ngay và
**cả API chết** — không phải riêng đường đính kèm. Trên một máy cài sạch
theo đúng tài liệu, cả giao diện web lẫn vỏ desktop đều không mở được.

Vì sao nó không lộ ra sớm hơn: máy phát triển đã có sẵn gói (một gói khác
kéo theo), bản EXE đóng gói cũng có (PyInstaller gom từ chính venv đó), và
lượt CI ĐẠT gần nhất (`0449dcb1`) có **trước** `9dff878` — nên đây là lần
đầu CI thật sự nạp route đính kèm.

Cùng hình dạng với sự cố `boto3` mà `server/tests/test_dependencies.py` ghi
lại: mã đã viết nhưng không tệp phụ thuộc nào được commit khai báo gói.

**Sửa:** khai `python-multipart>=0.0.9,<1.0` trong
`requirements-control-center-web.txt`, và cài tệp đó trong CI **sau** bước
"Import ứng dụng chỉ với phụ thuộc runtime" để bước ấy vẫn chứng minh đúng
điều nó sinh ra để chứng minh (`server/requirements.txt` **tự nó** đủ cho
backend web). `server/` không dùng một `Form(`/`File(`/`UploadFile` nào của
FastAPI, nên gói này **không** được bỏ vào tập phụ thuộc runtime của backend.

**Bài kiểm** `scripts/tests/test_control_center_web_deps.py` (5 bài), tách
đôi có ý: một nửa đọc **tệp phụ thuộc** (xanh/đỏ độc lập với máy đang
chạy), một nửa dựng `dung_app()` **thật**. Chỉ nửa sau thì không đủ — trên
máy đã có sẵn gói nó xanh dù tệp phụ thuộc rỗng, và đó đúng là cách sự cố
lọt qua. Kèm một bài bắt trường hợp route bỏ multipart, để nghĩa vụ kia
không thành vô cớ mà không ai biết.

Chứng minh trên venv **sạch** (chỉ `fastapi`+`uvicorn`):

| | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `dung_app()` | `RuntimeError` — đúng lỗi của CI | dựng được |
| `test_control_center_web_deps` | 4/5 | **5/5** |
| `test_control_center_webapi` | 37 lỗi | **37/37** |
| `test_control_center_attachments` | 37/37 | **37/37** |

---

## 11. Phát hành

| Hạng mục | Giá trị |
|---|---|
| PR | [#180](https://github.com/kujopht/capcut-tts-app/pull/180) — đã gộp |
| `main` SHA | `1f5c7338933cf9027465e14a4c1d1b003826ff1a` |
| Thẻ | `router-control-center-v0.2.0` |
| SHA đối tượng thẻ | `da8656917c18c111de185ec8619526bdd2373d23` |
| CI | 3/3 ĐẠT (gitleaks · backend môi trường sạch · web) |
| Tác phẩm dựng **từ thẻ** | `31dd5b22e064139499fb728b3cc2c720f0f22ba9689a13bc7172bd1b449b269f` |
| Cỡ | 13.435.164 byte (thư mục 92 MB) |

Bản **người dùng nghiệm thu tay** có sha256
`1a5bd8786bc5950a1c3b5c255f1463a7a38f73c7d411a2fb4b0bdc1828fa9136`, cùng
**đúng cỡ byte**. Hai băm khác nhau vì PyInstaller nhúng đường dẫn build,
**không** vì mã khác nhau: đã đối chiếu bằng `git diff --name-only` giữa
commit đã nghiệm thu (`538ceec`) và đích gắn thẻ — ba tệp đổi là
`requirements-control-center-web.txt`, `.github/workflows/ci.yml` và một
tệp kiểm mới. **Không một tệp nguồn nào nằm trong gói PyInstaller bị đổi.**

Tác phẩm dựng từ thẻ đã được thử khởi động sạch dưới locale máy, không một
biến môi trường nào: `--check` thoát 0, `--help` thoát 0 và in đủ tiếng
Việt (`ứng dụng desktop`), không `UnicodeEncodeError`.
