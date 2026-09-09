# Router Control Center V0.4 — sửa UX cho phòng làm việc leader-first

Nhánh `feat/ux-v04`. **Chưa tag, chưa deploy** — tài liệu này để nghiệm thu
tay trước khi phát hành.

Thứ tự làm theo đúng thứ tự ưu tiên đã nhận: (1) cửa sổ terminal nhấp
nháy, (2) một màn hình thấy hết, (3) ô soạn tự trống + giữ focus, (4) chủ
đề tối, (5) ảnh nền, (6) mài thêm.

---

## 0. Ảnh trước / sau

Cùng **một sổ SQLite**, cùng **một bộ dữ liệu gieo**, cùng cỡ
`1680x1000@2x`, Chrome thật qua DevTools Protocol. Chỉ khác **ba tệp
`web/`** — bản `git HEAD` so với cây làm việc. Sinh lại bằng:

```bash
python scripts/control_center_web_anh.py
```

| Tệp | Là gì |
|---|---|
| `anh/control_center_v04/truoc.png` | V0.3 — chủ đề sáng, cột phải chỉ có một `<pre>` |
| `anh/control_center_v04/truoc_tasks.png` | V0.3 — khung Tasks |
| `anh/control_center_v04/sau.png` | V0.4 — chủ đề tối, năm ô quan sát cùng một màn hình |
| `anh/control_center_v04/sau_usage.png` | V0.4 — bảng Usage theo NGUỒN (43 hạng mục; trước là 0) |
| `anh/control_center_v04/sau_cai_dat.png` | V0.4 — hộp thoại Cài đặt: ảnh nền, làm tối, làm nhoè |
| `anh/control_center_v04/sau_anh_nen.png` | V0.4 — ảnh nền thật, qua ĐÚNG đường đính kèm |

Kịch bản chụp **không bơm CSS** cho ảnh nền: nó tải ảnh qua
`KhoDinhKem.them_tu_luong()` rồi ghi `cai_dat_ui`, y như người dùng bấm
trong hộp thoại. Nếu đường đó hỏng thì ảnh chụp phải hỏng theo — một ảnh
đẹp nhờ bơm CSS sẽ che mất đúng cái cần chứng minh.

---

## 1. Cửa sổ terminal nhấp nháy — GỐC RỄ, không phải giấu đi

Người dùng báo: *"mỗi lần xử lý lại bật/tắt terminal window trên Windows,
rất khó chịu"*.

**Cơ chế.** `Router Control Center.exe` được build `--noconsole`, nên tiến
trình **không có console**. Trên Windows, một tiến trình không có console
mà sinh ra một ứng dụng **console** (`git.exe`, `agy.exe`, `codex.exe`,
`python.exe`, `icacls.exe`) thì hệ điều hành **cấp cho nó một console
mới** — kèm một cửa sổ nhấp lên và **giành focus**. Chạy từ mã nguồn thì
cửa sổ đó trùng console sẵn có nên không ai thấy. Lại đúng một lớp lỗi
"chỉ lộ ra ở bản EXE", giống `sys.executable` và giống cp1252.

**Số lần nhấp tỉ lệ với số lệnh.** `AnhChupDuAn.chup()` chạy ~6 lệnh
`git` cho **mỗi** tin nhắn chat, nên một câu "ê" cũng đủ thấy. Đó là chỗ
nhấp nhiều nhất trong app.

**Bản sửa.** Một helper duy nhất, `scripts/router_v3/tien_trinh.py`:

```python
def an_cua_so() -> Dict[str, Any]:
    if sys.platform != "win32":
        return {}
    return {"creationflags": _CREATE_NO_WINDOW,     # 0x08000000
            "startupinfo": _startupinfo()}          # STARTF_USESHOWWINDOW + SW_HIDE

AN_HIEN: Dict[str, Any] = {}     # khi NGƯỜI DÙNG CỐ Ý muốn thấy cửa sổ
```

`CREATE_NO_WINDOW` bảo hệ điều hành **đừng cấp console**; `STARTUPINFO`
với `SW_HIDE` phủ nốt trường hợp chương trình con tự xin hiện cửa sổ.
Trên nền khác trả `{}` — không có console window nào để ẩn, và một cờ
Windows truyền vào `subprocess` trên Linux là một `ValueError`.

**Không mất log.** Ẩn cửa sổ *không* đánh đổi bằng mất đầu ra: mọi chỗ
sinh tiến trình vẫn `capture_output=True` và đầu ra vẫn vào nhật ký app.
Có bài kiểm chạy thật một lệnh console và đòi bắt được `stdout` — đó
mới là chỗ một bản sửa "cho yên tĩnh" dễ làm sai.

**17 chỗ đã sửa** (16 chỗ trên bao đóng khởi động + `worktree.py::_git`):

| Tệp | Chỗ |
|---|---|
| `control_center/snapshot.py` | `git` (×6 mỗi tin nhắn — chỗ nhấp nhiều nhất) |
| `control_center/bootstrap.py` | 3 lệnh `git` |
| `control_center/worktrees.py` | 2 lệnh `git` |
| `router_v3/worktree.py` | `_git` (có rào an toàn cho bộ kiểm, xem dưới) |
| `router_v3/warm_pool.py` | `Popen` agy |
| `router_v3/pool/adapters.py` | `codex login status`, `Popen` codex |
| `router_v3/native_worker.py` | 2 chỗ |
| `router_v3/grok_adapter.py` | 2 chỗ |
| `router_v3/worker_identity.py` | `icacls` |
| `router_v4/antigravity_launcher.py` | `switch` |
| `router_v4/thong_dich.py` | dò `--version` |
| `scripts/ai_router_quota_check.py` | `agy`/`codex` |

`worktree.py::_git` nhận một bộ chạy được tiêm từ ngoài, nên cờ chỉ được
thêm khi bộ chạy đó thật sự là `subprocess.run`:

```python
kw = an_cua_so() if self._run is subprocess.run else {}
```

**Sửa từng chỗ là không đủ**, nên phép cưỡng chế là một bài kiểm **AST
trên cả bao đóng khởi động**: nó tính mọi tệp `scripts/**` mà việc mở EXE
có thể nạp tới, rồi đòi **mọi** lời gọi `subprocess.run/Popen/...` trong
đó phải mang kwargs ẩn cửa sổ. Thêm một adapter mới mà quên là **đỏ**, và
thông điệp lỗi chỉ ra đúng dòng. Miễn trừ duy nhất là
`router_v3/pool/daemon.py`, tệp tự quản cờ của nó và có lý do riêng
trong docstring.

`router_v3/pool/daemon.py` là chỗ **duy nhất** trong kho từng dùng
`CREATE_NO_WINDOW` trước bản này. Nói cách khác: một người đã đúng ở một
chỗ, và mười sáu chỗ còn lại thì không — đúng hình dạng lỗi mà một phép
kiểm trên bao đóng tồn tại để chặn.

---

## 2. Một màn hình là biết hệ thống đang làm gì

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Cột phải | một `<pre id="inspector">` liệt kê việc đang chạy | năm ô: Đang chạy, Việc gần đây, Agent đang sống, Usage theo agent/provider, Ảnh chụp dự án |
| Biết nhánh / HEAD / sạch-bẩn | phải đổi tab, hoặc không có ở đâu cả | ô "Ảnh chụp dự án", kèm commit gần đây và backend đang sống |
| Biết usage | tab Usage, và **bảng luôn rỗng** (xem §5) | ô Usage + tab Usage, 43 hạng mục có mức tin cậy |
| Chế độ định tuyến | không hiện ở đâu | chip `AUTO` trên thanh trên |
| Bảng đầy đủ + lọc + copy | tab Tasks/Agents/Logs/Usage | **giữ nguyên** — chúng thành đường ĐIỀU TRA, không phải đường đọc chính |

**Nhịp làm mới khác nhau, có chủ ý.** Ba ô đầu vẽ từ `snapshot()` đã có
sẵn qua WebSocket (không thêm một request nào). Hai ô đắt có nhịp riêng:

| Ô | Nhịp | Vì sao |
|---|---|---|
| Usage | 60s + khi đổi dự án | có thể gọi CLI của nhà cung cấp |
| Ảnh chụp dự án | 45s + khi đổi dự án + nút ↻ | chạy ~6 lệnh `git` = 6 tiến trình con |

Gắn ảnh chụp vào nhịp WebSocket (1s) sẽ là **~6 tiến trình con mỗi giây**
— tức là tự dựng lại đúng sự cố ở §1 bằng một tính năng mới. Nên
`/api/snapshot` là một endpoint **riêng**, không nhập vào `/api/state`.
Cả hai ô cũng dừng khi tab bị ẩn (`document.hidden`).

Ô Usage gấp các bể quota vào một `<details>` ("19 bể quota · 38 hạng
mục"): mỗi tài khoản cho hai hàng gần như giống nhau, và mở hết thì cột
phải dài hơn màn hình, đẩy "Ảnh chụp dự án" xuống dưới mép — phá đúng
yêu cầu đang làm.

---

## 3. Ô soạn: trống khi nên trống, và không mất chữ khi hỏng

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Gửi | nút Gửi, hoặc `Ctrl+Enter` | **Enter** gửi, **Shift+Enter** xuống dòng, nút Gửi vẫn còn |
| Sau khi gửi | ô soạn được xoá, con trỏ rơi ra ngoài | xoá **sau khi server nhận**, `focus()` trả về ô soạn |
| Gửi hỏng | `noi()` ở thanh dưới, xa chỗ đang nhìn | lý do hiện **cạnh nút Gửi** bằng màu đỏ, và **văn bản vẫn còn nguyên trong ô** |
| Bấm Enter liên tục lúc chờ | gửi trùng | chặn bằng cờ `dangGui` |
| Bộ gõ tiếng Việt | — | tôn trọng `isComposing`/`keyCode 229`: Enter chốt chữ Telex/VNI **không** gửi |
| Lúc mở app | phải bấm vào ô trước khi gõ | con trỏ đã nằm trong ô soạn |

Thứ tự **gọi API → thành công → xoá** là điểm chính, không phải chi tiết:
xoá trước (hoặc xoá trong `finally`) là một lỗi **mất dữ liệu** — server
từ chối vì mất token hay mất mạng, và câu người dùng vừa gõ biến mất
không lấy lại được. Có bài kiểm so **vị trí** của `await api(` với vị trí
của `o.value = ''` trong thân hàm gửi.

**Tiến độ SỐNG.** `chat()` chạy đồng bộ, và một lần mở phiên Leader lạnh
đo được **67.87s** (lượt hỏi khi đã ấm: 2.40s). Trước bản này, trong suốt
khoảng đó màn hình chỉ có một cái nút bị vô hiệu hoá — không phân biệt
được "đang nghĩ" với "treo", nên người dùng bấm lại hoặc đóng app.

Giờ `engine.py` ghi **bước đang làm** theo dự án và nó đi ra qua
`snapshot()`, tức là qua WebSocket:

```
Leader đang đọc ảnh chụp dự án
đang mở phiên Leader          <- chỉ ở lần LẠNH
Leader đang suy nghĩ
đang phân rã mục tiêu thành việc
đang giao việc cho Router V4
```

Hai chi tiết là quyết định, không phải ngẫu nhiên:

* **Mốc thời gian giữ nguyên qua các bước.** Đồng hồ đếm TỔNG thời gian
  chờ. Reset mỗi bước thì nó nói dối đúng ở chỗ người dùng đang mất kiên
  nhẫn.
* **`"buoc"` nằm trong vân tay WebSocket.** Không có nó thì tiến độ
  không bao giờ được đẩy đi: một lần `chat()` dài không đổi
  task/session/chat nào cả, nên vân tay cũ sẽ trùng và server im lặng.

Vì nhãn đến từ **server**, mọi tab đang mở đều thấy — không chỉ tab vừa
bấm Gửi.

---

## 4. Chủ đề tối, và ảnh nền

Bảng màu nằm ở **một chỗ duy nhất** (`:root`), mọi màu khác trỏ về đó.
Neon (`--neon: #35e0d0`) **chỉ** dùng cho viền, chip và chữ ≥600 — không
bao giờ cho văn bản dài. `--chu` trên `--nen` khoảng **12.6:1**; `--mo`
trên `--the` khoảng **5.6:1**.

Thanh trượt và ô chọn tệp **không** để mặc định hệ điều hành
(`accent-color`, `::file-selector-button`): mặc định của chúng là track
trắng + nút xanh Windows trên một hộp thoại tối, trông như một mảnh giao
diện khác dán vào. Vòng xoay tiến độ tắt dưới
`prefers-reduced-motion` — một hiệu ứng không tắt được là lỗi trợ năng,
không phải chi tiết thẩm mỹ.

**Ảnh nền là hai lớp cố định `z-index: -2/-1`, không phải `background`
của `body`.** `filter: blur()` làm nhoè **cả con** của phần tử nó đặt
lên, nên nếu ảnh là nền của `body` thì cả giao diện bị nhoè theo. Lớp
riêng cũng cho `transform: scale(1.04)` để viền ảnh không bị hạ nhạt khi
blur ăn vào trong.

### `wallpaper` giữ MÃ ĐÍNH KÈM, không phải đường dẫn tệp

Đây là quyết định an toàn quan trọng nhất của tính năng này. Nhận đường
dẫn thì để **vẽ** được ảnh phải mở một endpoint đọc tệp tuỳ ý trên đĩa —
dựng lại đúng lỗ mà `attachments.py` tồn tại để bịt. Đi qua đường đính
kèm thì được thừa cả bốn bất biến sẵn có:

1. nhị phân không vào SQLite;
2. đường lưu do **băm nội dung** sinh, không do tên người dùng đặt;
3. đọc lại **chỉ** qua `attachment_id`, có kiểm containment sau
   `resolve()`;
4. kiểm **chữ ký byte** — `anh.png` mà không mở đầu bằng `\x89PNG` thì bị
   từ chối.

`POST /api/ui` chỉ nhận allowlist khoá (`wallpaper`, `dim`, `blur`,
`fit`, `theme`), xác minh mã đính kèm **tồn tại** và **là ảnh**, và kẹp
`dim`/`blur` vào khoảng hợp lệ. Có bài kiểm đọc chính mã của endpoint và
đòi nó **không** chứa `open(`/`read_bytes`/`read_text`/`FileResponse`.

### Di trú

Một bảng khoá–giá trị mới, `cai_dat_ui`, thêm bằng `CREATE TABLE IF NOT
EXISTS` trong `SCHEMA` — `ControlStore.__init__` chạy `executescript(SCHEMA)`
mỗi lần dựng, nên **sổ cũ tự có bảng mới ở lần mở sau; không có bước di
trú tay, không dữ liệu nào phải dịch chuyển.** Sổ mới mở bằng bản cũ vẫn
chạy: bảng thừa không ai đọc.

Lưu **từng khoá riêng**, không phải một khối JSON, để hai lần ghi khác
khoá không đè nhau — đổi độ tối không được xoá mất ảnh nền (có bài kiểm).
Cả nhóm khoá đi trong **một** `BEGIN IMMEDIATE`, nên vòng vẽ đang đọc
song song không thấy trạng thái nửa vời.

Cài đặt thuộc **người dùng trên máy này**, không thuộc một dự án: đổi dự
án không đổi ảnh nền.

---

## 5. Hai lỗi thật tìm được khi làm việc này

Cả hai đều là lỗi **im lặng** — không ngoại lệ, không dòng log — và cả
hai đều xanh ở CI.

### 5a. Bảng Usage luôn rỗng

`UsageReporter.report()` trả về `{local, pools, runtimes, accounts,
providers}`. Frontend V0.2/V0.3 đọc `bc.metrics` — **một khoá không tồn
tại** — nên bảng Usage luôn rỗng và dòng tóm tắt luôn là "0 hạng mục".
Không ai thấy vì một bảng trắng trông y như "chưa có dữ liệu".

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Tab Usage với dữ liệu gieo | `0 hạng mục — 0 ACTUAL, 0 ESTIMATED, 0 UNAVAILABLE` | `43 hạng mục — 24 ACTUAL, 16 ESTIMATED, 3 UNAVAILABLE` |
| Cột | Hạng mục / Giá trị / Đơn vị / Mức tin cậy / Ghi chú | thêm **Nguồn** ở đầu |
| Nguồn | không biết số thuộc provider nào | `sổ Control Center`, `antigravity_gemini · ag-account-01`, … |

Bài kiểm so **hai đầu của ranh giới với nhau**: nó gọi `report()` thật
và đòi khoá `metrics` **không** tồn tại, đồng thời đòi frontend đọc
`bc.local`/`bc.pools`/`bc.providers` qua **một** bộ gom dùng chung. Đổi
hình dạng ở một bên mà quên bên kia là đỏ.

### 5b. `cc_agent_tool.py` in câu từ chối thành `T\u1eea CH\u1ed0I`

Chỗ **thứ ba** của đúng sự cố UTF-8 ở Mission 13, và nó có một chế độ
hỏng khác hai chỗ đầu:

* `stdout` nối vào pipe → `errors='strict'` → `UnicodeEncodeError`, công
  cụ chết giữa lúc báo kết quả.
* `stderr` → CPython mặc định **`errors='backslashreplace'`** trên
  Windows → câu `TỪ CHỐI: …` ra thành `T\u1eea CH\u1ed0I: …`. **Không
  chết**, nên nó lặng lẽ đúng ở CI (Linux/UTF-8) và lặng lẽ sai trên máy
  người dùng.

`scripts/tests/test_control_center_allowlist.py::test_cwd_NGOAI_kho_bi_tu_choi`
bắt được đúng cái này khi chạy dưới locale thật của máy — bài kiểm quan
trọng nhất của tệp đó, và nó **hỏng 3/3 động từ** trước bản sửa. Đã
chuyển sang ghi UTF-8 bằng byte + `BoDocUTF8` cho `argparse`; 26/26 xanh
lại.

---

## 6. Bộ kiểm

`scripts/tests/test_control_center_ux_v04.py` — **25 bài, tất cả xanh**,
đúng năm đường người dùng đã yêu cầu cộng phần usage:

| Nhóm | Bài | Chốt điều gì |
|---|---|---|
| `TestKhongNhapCuaSo` | 4 | AST trên **cả bao đóng khởi động**; cờ đúng trên Windows; tiến trình con thật vẫn bắt được stdout |
| `TestOSoanTuTrong` | 4 | xoá **sau** khi API thành công; giữ focus; Enter/Shift+Enter; gửi hỏng **không** xoá |
| `TestMotManHinh` | 2 | năm ô quan sát có mặt; khung cũ vẫn còn làm đường gỡ lỗi |
| `TestUsageDungHinhDang` | 3 | `report()` không có khoá `metrics`; frontend đọc `local`/`pools`/`providers`; mọi hàng mang tên Nguồn |
| `TestTienDoSong` | 6 | bước rỗng khi rảnh; mốc thời gian giữ nguyên qua các bước; theo từng dự án; `"buoc"` trong vân tay WS |
| `TestAnhNen` | 4 | lưu/đọc lại; bền qua khởi động lại; ghi đè giữ khoá không gửi; endpoint **không** đọc tệp |
| `TestChuDeToi` | 2 | bảng màu khai bằng biến; `body` không còn nền trắng |

### Đã chạy lại, kết quả thật

| Bộ | Kết quả |
|---|---|
| `test_control_center_ux_v04` | **25/25 OK** |
| `test_control_center_webapi` + `web_deps` + `leader` | **92/92 OK** |
| `test_control_center_core` + `slice` | **168/168 OK** |
| `test_control_center_attachments` | **37/37 OK** |
| `test_control_center_allowlist` | **26/26 OK** (3 đỏ trước bản sửa §5b) |
| `test_control_center_repo_ngoai_git` | **11/11 OK** |
| `test_control_center_utf8_locale` | 42 bài — **41 OK, 1 quá hạn** (xem dưới) |
| router v3 (mọi bộ) | **396 OK, 1 skip** |
| router v4 (mọi bộ) | **201 OK** (chung lượt với warm bridge/executor) |
| Qt GUI (`tests/`) | **25 OK, 95 skip** — thiếu PySide6 trong Python toàn cục của máy này |

**Nói thẳng về bài quá hạn.** `test_desktop_check_khong_no_tren_cp1252`
chạy `-m scripts.control_center.desktop --check` trong tiến trình con và
vượt trần 180s **khi chạy cùng cả module**. Chạy riêng: **8s / 3s / 93s**
qua ba lượt liên tiếp. Đó là dao động của môi trường (import `pywebview`
+ quét của Defender trên máy này), không phải một hồi quy: bài này không
chạm mã V0.4 nào, và nó xanh mỗi lần chạy riêng. Không "sửa" bằng cách
nới trần — ghi lại ở đây để lần sau gặp thì biết.

### Phụ thuộc phải cài để chạy bộ kiểm trên máy này

`python-multipart` (đã khai ở `requirements-control-center-web.txt`) và
`websockets` (cho kịch bản chụp ảnh qua CDP). Thiếu gói thứ nhất thì
`dung_app()` **ném lúc đăng ký route** và 36 bài đỏ — cùng hình dạng sự
cố đã ghi trong chính tệp requirements đó.

---

## 7. Ranh giới KHÔNG bị chạm

* Router V4 không đổi: `Scheduler`/`Executor`/`LeaseStore` nguyên vẹn.
* Không nới rào an toàn: không `--dangerously-skip-permissions`, không
  `bypassPermissions`, `destructive_actions_allowed` vẫn `False`, việc
  GATED vẫn dừng chờ người. `approve_gate` của Leader vẫn chỉ là **đề
  xuất**.
* Không bịa số usage: không đo được thì `UNAVAILABLE` + để trống, không
  phải `0`. Ô Usage mới **bỏ hẳn** hạng mục `value is None` khỏi ảnh
  chụp thay vì điền 0.
* Không tự xoá worktree.
* Bind vẫn `127.0.0.1`, không CORS, token mọi request kể cả `GET`, kiểm
  `Host` trước kiểm token. Hai endpoint mới (`/api/snapshot`, `/api/ui`)
  đi qua **cùng** middleware đó.
* CSP không nới một chữ: ảnh nền đi qua `/api/attachments/<id>/blob` của
  chính server này nên `img-src 'self'` là đủ.
* Ba luật clipboard của tầng Qt không bị chạm — Qt là mã khác, và ở
  frontend web thì `dat()` chỉ ghi khi nội dung THẬT SỰ đổi và không có
  vùng nào đang bôi đen.

---

## 8. Còn thiếu — mang sang bản sau

1. **Chưa có ô chọn ECO/AUTO/STRONG/MAX.** Chế độ đã bền trong bảng
   `leader` và hiện ra thanh trên dưới dạng chip đọc-được, nhưng đổi nó
   vẫn phải qua backend.
2. **Leader chỉ chạy trên Antigravity.** `MODEL_LEADER` là một hằng số;
   chưa có đường chọn provider khác từ giao diện.
3. **Lần mở Leader lạnh vẫn ~68s.** Bản này làm nó *nhìn thấy được*, chứ
   không làm nó *nhanh hơn*. Rút ngắn thật sẽ phải làm ấm phiên trước
   khi người dùng gõ câu đầu.
4. **Ba launcher gỡ lỗi vẫn chết trên cp1252**: `router-cc --help`,
   `router-cc-gui --help`, `router-cc --headless`. Đường CHÍNH
   (`router-cc-web.cmd`, vỏ desktop) đã sạch.
5. **Chưa dựng lại bản EXE.** Mọi thứ ở trên đo trên mã nguồn + Chrome
   thật. Nghiệm thu §1 **phải** làm trên bản EXE đóng gói: đó là nơi
   duy nhất cửa sổ console thật sự nhấp.
