# V0.4 — nghiệm thu trên BẢN EXE ĐÓNG GÓI

Nhánh `feat/ux-v04`. **Chưa tag, chưa phát hành.**

Vật chứng nghiệm thu là **chính `Router Control Center.exe` đã đóng gói**,
mở qua `ShellExecuteW` (đúng API Explorer gọi khi bấm đôi), điều khiển qua
cửa sổ **WebView2 của chính nó**. Không có Chrome chạy từ mã nguồn ở bất
kỳ bước nào.

```
EXE   : dist-v04/Router Control Center/Router Control Center.exe
        11.399.448 byte (thư mục 62 MB)
lệnh  : python scripts/build_desktop_exe.py --clean --dist dist-v04
        python scripts/control_center_desktop_acceptance.py \
            --exe "dist-v04/Router Control Center/Router Control Center.exe"
kết quả: 53/53 ĐẠT, hai lần chạy liên tiếp
```

`--dist dist-v04` chứ không phải `dist/`: một bản đang CHẠY khoá chính thư
mục của nó, nên "dựng bản mới để nghiệm thu" và "giữ bản người dùng đang
mở" không thể dùng chung một chỗ.

---

## 1. Ba lỗi THẬT chỉ lộ ra ở bản đóng gói

Không lỗi nào trong ba lỗi này thấy được từ mã nguồn.

### 1a. WebView2 chết lúc mở: `0x8007139F`

```
[pywebview] WebView2 initialization failed with exception:
(0x8007139F): The group or resource is not in the correct state to
perform the requested operation.
```

`pywebview` mặc định đặt hồ sơ WebView2 ở `%APPDATA%\pywebview\EBWebView`
— **một thư mục dùng chung cho MỌI ứng dụng pywebview trên máy**. WebView2
cho nhiều tiến trình dùng chung một hồ sơ, nhưng **chỉ khi
`AdditionalBrowserArguments` giống nhau**; khác một cờ là nó từ chối với
đúng HRESULT trên. Hệ quả thật:

* mở bản thứ hai của app trong khi bản của người dùng đang chạy → **không
  cửa sổ nào mở được**;
* một ứng dụng pywebview của **bên thứ ba** cũng đủ làm app này chết lúc
  mở, với một thông điệp không ai suy ra được nguyên nhân.

Đây đúng là bất biến `ten_mutex_cua` đã chọn: "một thực thể" tính theo
**thư mục gốc**, không theo cả máy, để một bản KIỂM chạy được cạnh bản
người dùng mà không phải tắt ứng dụng của ai. Hồ sơ WebView2 toàn máy phá
lại đúng bảo đảm đó.

**Sửa:** `desktop_shell.duong_webview2(goc)` — hồ sơ riêng theo thư mục
gốc, băm bằng **cùng một khoá** với mutex, đặt dưới `%LOCALAPPDATA%\
FanficAudioStudio\router\webview2\<hash16>`. Không đặt dưới `goc`: WebView2
tạo cây sâu (`EBWebView/Default/…`) và một `goc` đã dài sẽ đẩy tổng đường
dẫn qua `MAX_PATH`. **Không cần di trú** — app không giữ gì đáng kể trong
hồ sơ WebView2 (token ở `sessionStorage`, mọi trạng thái thật ở SQLite).

### 1b. `verify_scope` và `pool/validation` vẫn nhấp cửa sổ console

Bản V0.4 đầu thêm `**an_cua_so()` vào `WorktreeManager._git()`. Chưa đủ:

| Chỗ | Vì sao lọt |
|---|---|
| `worktree.py::verify_scope` | gọi `self._run(["git", …])` **trực tiếp**, không qua `_git()` |
| `pool/validation.py::_git` | `runner(["git", …])` — runner được tiêm |
| `pool/validation.py::cong_test` | `runner(lenh, …)` — lệnh test cũng là tiến trình console |

Và **bài kiểm AST cũng trượt cùng chỗ**: nó tìm `subprocess.run`/`Popen`,
còn đây là một **runner được tiêm** nên tên hàm không khớp. Hai lớp phòng
vệ cùng bỏ sót một hình dạng.

**Sửa:** `_boc_an_cua_so(runner)` — bọc **một lần** ở chỗ nhận runner thay
vì thêm kwargs ở từng điểm gọi, nên điểm gọi thêm về sau cũng được phủ tự
động. Chỉ bọc khi runner LÀ `subprocess.run` thật: bộ kiểm tiêm runner giả
không nhận `creationflags`, và truyền vào đó sẽ nổ `TypeError`.

**Và phép quét được mở rộng** để nhận hình dạng runner-được-tiêm: một lời
gọi mà **tham số đầu** là danh sách bắt đầu bằng tên một chương trình
console (`git`, `agy`, `codex`, `python`, `npm`…) là một chỗ sinh tiến
trình, bất kể hàm tên gì. Kèm hai bài chống rỗng: một bài đòi phép quét
BẮT được `self._run(['git', …])`, một bài đòi nó KHÔNG báo bừa.

### 1c. `build_desktop_exe.py` chết ở dòng báo cáo của chính nó

`print(f"  cỡ   : …")` — chữ **ỡ** (U+1EE1) ngoài cp1252 → `UnicodeEncodeError`
**ngay sau khi build xong**, tức là mất báo cáo của một lần dựng vài phút.
Chỗ thứ tư của sự cố Mission 13. `control_center_desktop_acceptance.py`
cũng vậy — một bộ **nghiệm thu** chết ở dòng tiêu đề thì không nghiệm thu
được gì. Cả hai chuyển sang `GhiUTF8`.

---

## 2. Smart App Control: `WinError 4551`, và cách đi đúng

Bản mới build bị chặn thẳng:

```
OSError: [WinError 4551] An Application Control policy has blocked this file
```

`Microsoft-Windows-CodeIntegrity/Operational` ghi **3077** + **3118 (Smart
App Control Block)**, policy `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`,
`VerifiedAndReputablePolicyState=0x1` (cưỡng chế) — đúng như `CLAUDE.md`
mô tả về máy này.

Sự kiện 3077 nói rõ: *"a process (**python.exe**) attempted to load … Router
Control Center.exe"*. Phán quyết của SAC tính **cả tiến trình cha**. Cùng
một tệp EXE, mở bằng **`ShellExecuteW`** thì chạy bình thường.

Và đó **không phải một đường lách**: `ShellExecuteW` LÀ API Explorer gọi
khi người dùng bấm đôi một tệp, nên nó vừa là đường người dùng thật đi,
vừa đúng tiêu chí nghiệm thu số 1. Bộ nghiệm thu đã chuyển sang dùng nó.
**Không tắt Smart App Control** (bị cấm, và không hoàn tác được) và không
ký số (cần chứng thư — việc sau MVP).

Đánh đổi: `ShellExecuteW` không cho ống dẫn stdout. Thực ra tốt hơn — bản
`--noconsole` không có ai đọc `stdout`, nên nhật ký thật của nó là
`<goc>/.router/control_center/desktop.log` do `GhiUTF8` ghi, và bộ nghiệm
thu giờ đọc đúng tệp đó. `terminate()` cũng chuyển sang `taskkill` **không**
`/F`, nên `_khi_dong()` của `desktop.py` CHẠY THẬT — đúng đường "người
dùng đóng cửa sổ" mà tiêu chí 8 đang hỏi.

---

## 3. Đo "không nhấp cửa sổ console" cho ra bằng chứng, không cho ra cảm giác

Một cửa sổ `conhost` do `git.exe` sinh ra sống 30–120ms. Mắt người thấy nó
như một cái nhấp, nhưng không nói được nó thuộc tiến trình nào, xảy ra bao
nhiêu lần, hay có xảy ra ở lần chạy này không. `scripts/giam_sat_cua_so.py`
đo bằng:

1. **`SetWinEventHook`** (`EVENT_OBJECT_CREATE` + `EVENT_OBJECT_SHOW`) —
   hướng sự kiện, nên một cửa sổ sống 5ms cũng không lọt. Lớp chính.
2. **Poll 25ms** làm lớp phủ nếu hook bị hệ thống ngắt.
3. **Mốc nền** chụp TRƯỚC khi app mở: máy người dùng (và cả phiên bash
   chạy bộ nghiệm thu) có sẵn cửa sổ console.

### Ba định chính của chính phép đo — mỗi cái từng cho một kết luận SAI

| Định chính | Nếu không có nó |
|---|---|
| Không lọc theo **tổ tiên tiến trình** | Đo được 6/6 lần: cửa sổ console do một tiến trình con gây ra thuộc về một `WindowsTerminal.exe` **dùng chung cả phiên** (tổ tiên `svchost <- services <- wininit`) — console mới chỉ là một TAB dựng qua DCOM. Lọc theo tổ tiên làm phép kiểm **không bao giờ đỏ được**. Đã suýt cho một PASS giả. |
| Bộ nghiệm thu phải **tự tuân luật nó kiểm** | `python.exe` chạy bộ nghiệm thu có `GetConsoleWindow() == 0` — đúng điều kiện bản `--noconsole`. `dem_webview2()` gọi `tasklist` không cờ ẩn, và tự sinh ra đúng vi phạm nó đang đi tìm. |
| **Cửa sổ đối chứng** + quy trách nhiệm theo chùm tiến trình | Một lần chạy cho 8 `bash.exe` + `jq.exe` xuất hiện cùng lúc với cửa sổ console — phiên Claude Code và hook shell của nó, không phải app. Cùng lần đó app sinh `git.exe` ×45 mà không một cửa sổ nào đi kèm. |

Phép quy trách nhiệm cuối: trong chùm tiến trình **vừa xuất hiện** quanh
cửa sổ (±1.5s), có ít nhất một tiến trình là **con của ứng dụng** hay
không — giải NGAY lúc đó, khi tiến trình còn sống và chuỗi cha còn đọc
được. Đợi đến lúc báo cáo thì `git.exe` (~30ms) đã chết.

**Phép lọc này vẫn ĐỎ được**: bộ chứng cứ chống rỗng sinh `cmd.exe` không
cờ ẩn và bị quy trách nhiệm **6/6**.

### Nhịp nền, đo thật

| Điều kiện | Cửa sổ console mới |
|---|---|
| Không mở app, 90s | 0 |
| Không mở app, 150s | 0 |
| App mở qua Explorer, để yên 150s (không `--debug-cdp`) | **0** — kèm `git.exe`×12, `agy.EXE`×1 |
| App mở qua Explorer, để yên 150s (CÓ `--debug-cdp`) | **0** — kèm `git.exe`×12 |
| Nghiệm thu đầy đủ, lần 1 | **0 của app** / 0 tổng — kèm `git.exe`×43, `agy.EXE`×5, `python.exe`×5, `codex.exe`×1 |
| Nghiệm thu đầy đủ, lần 2 | **0 của app** / 0 tổng — kèm `git.exe`×43, `agy.EXE`×5 |
| Đối chứng trong chính lần chạy: app mở + rảnh 30s | **0** |

`git.exe`×43 với 0 cửa sổ là chứng cứ chống rỗng: nếu app không sinh tiến
trình console nào thì "không có cửa sổ" là một câu vô nghĩa.

Hai phép đo cô lập riêng, mỗi phép 3 lượt, `agy` **được xác minh còn
sống**: `agy.exe` với `an_cua_so()` → 0/3 vi phạm; và với **env của chính
ứng dụng** (`USERPROFILE`/`HOME` riêng theo tài khoản) + `switch(acc1)`
chạy trước → 0/3.

---

## 4. Kết quả theo mười tiêu chí

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Mở bình thường từ Explorer | **ĐẠT** | `ShellExecuteW`; cửa sổ WebView2 1297×817 hiện lúc 4.3–8.6s |
| 2 | Không cửa sổ console ở CẢ 8 pha | **ĐẠT** | 0 vi phạm ×2 lần chạy; từng pha có nhãn riêng (khởi động / Leader warm / chat / xem trạng thái / giao việc / sinh agent / xong-hỏng / usage) |
| 3 | Ô soạn trống ngay sau khi gửi | **ĐẠT** | `còn lại ""`; và gửi HỎNG thì **không** xoá (bài kiểm so vị trí `await api(` với `o.value=''`) |
| 4 | Hội thoại Leader hiện và cập nhật | **ĐẠT** | 5–6 bong bóng, có thẻ việc + kết quả chảy về chat |
| 5 | Tasks/Agents/Logs/Usage + trạng thái đang chạy | **ĐẠT** | 5 ô quan sát cùng màn hình; Usage 43 hạng mục (24 ACTUAL / 16 ESTIMATED / 3 UNAVAILABLE) |
| 6 | Chủ đề tối + ảnh nền | **ĐẠT** | nền `rgb(8,11,20)` Σ39, chữ Σ712, `--neon=#35e0d0`; ảnh nền qua ĐÚNG đường đính kèm, tự hiện lại sau khi mở lại |
| 7 | Tiếng Việt / Unicode | **ĐẠT** | tên dự án, chat `ă â đ ê ô ơ ư Ă Â Đ Ê Ô Ơ Ư`, tên tệp đính kèm; **hash + cỡ khớp từng byte**; nhật ký UTF-8 hợp lệ, giữ chữ `ư` |
| 8 | Đóng/mở lại: trạng thái không cũ, không hỏng | **ĐẠT** | đếm TRỰC TIẾP trong SQLite hai đầu vòng đóng/mở, không mất bản ghi nào; `PRAGMA integrity_check = ok`; giao diện hiện đúng số của sổ |
| 9 | Không đổi hạ tầng production / Router V4 | **ĐẠT** | `scripts/router_v4/` **0 thay đổi**; hai tệp Router V3 chỉ đổi đường sinh tiến trình, cùng lệnh cùng tham số |
| 10 | Bộ kiểm sau khi đóng gói | **ĐẠT** | 711 bài, xem dưới |

Con trỏ giữ ở ô soạn: **ĐẠT** — và phép kiểm này từng đỏ vì một lỗi của
**bộ nghiệm thu**: bước trước đó mở khung Logs, nên `#khung-chat` đang
`display: none`, và `element.focus()` trên phần tử trong cây `display:none`
**không làm gì cả**. Đo dòng thời gian `activeElement` mỗi 150ms cho thấy
khi khung Chat đang hiện, ô soạn giữ focus suốt cả lượt gửi (`value` trống
ở 6.12s, nút bật lại ở 6.27s, `activeElement` là `o-soan` ở mọi mẫu).

---

## 5. Bộ kiểm sau khi đóng gói

| Bộ | Kết quả |
|---|---|
| `test_control_center_ux_v04` (+7 bài mới) | 33/33 |
| control-center: webapi, web_deps, leader, desktop_shell, allowlist, attachments, repo_ngoai_git, ux_v04 | **225/225** |
| Router V3 + V4: launcher, scheduler, compat, cloud_capabilities, profile_crypto, dispatch_frozen, premium_astra, worktree, pool_validation, pool_orchestrator, warm_bridge, warm_executor | **318/318** |
| `test_control_center_core` + `slice` | **168/168** |
| **Tổng** | **711 ĐẠT, 0 hỏng** |

Bài kiểm mới trong lượt này:

* 6 bài cho hồ sơ WebView2 theo thư mục gốc — gồm một bài đòi nó dùng
  **cùng khoá băm** với mutex (đổi một chỗ mà quên chỗ kia thì "một thực
  thể" và "một hồ sơ" lệch nhau), và một bài đòi nó **không** nằm dưới
  `goc` (`MAX_PATH`).
* 2 bài chống rỗng cho phép quét AST: một đòi nó bắt được runner được
  tiêm, một đòi nó không báo bừa.

Phụ thuộc phải cài để chạy được trên máy này: `pywebview` (đã khai ở
`requirements-control-center-desktop.txt`), `python-multipart` (đã khai),
`websockets` (cho CDP của bộ nghiệm thu).

---

## 6. Còn lại — không chặn phát hành

1. **EXE chưa ký.** Smart App Control chặn `CreateProcess` từ một tiến
   trình cha không có danh tiếng; đường Explorer chạy được. Ký số là việc
   sau MVP, và **không** được tắt Smart App Control.
2. **Chưa có ô chọn ECO/AUTO/STRONG/MAX.** Chế độ bền trong bảng `leader`
   và hiện ra thanh trên dưới dạng chip đọc-được; đổi vẫn phải qua backend.
3. **Leader chỉ chạy trên Antigravity.** `MODEL_LEADER` là hằng số.
4. **Lần mở Leader lạnh ~68s.** V0.4 làm nó *nhìn thấy được* (dòng tiến độ
   sống, đồng hồ đếm tổng thời gian chờ), không làm nó *nhanh hơn*.
5. **Ba launcher gỡ lỗi vẫn chết trên cp1252**: `router-cc --help`,
   `router-cc-gui --help`, `router-cc --headless`. Đường CHÍNH (vỏ desktop,
   `router-cc-web.cmd`) đã sạch.
6. **13 chỗ sinh tiến trình chưa ẩn** vẫn còn trong `scripts/router_v3/`
   và `scripts/router_v4/`, nhưng **không chỗ nào nằm trên đường chạy của
   ứng dụng**: `control_room/state_reader.py` chỉ dùng bởi TUI Textual (mà
   bản EXE `--exclude-module textual`), `setup_*.py` là CLI dựng máy,
   `cloud_capabilities.py` không được module nào import, `bridge_store.py`
   chỉ từ `pair_bridge`/`bridge_status`. Nên sửa khi chạm tới chúng.
