# Router Control Center V0.2

Phòng điều khiển cho Router V4 **đã có**. Mở một dự án, gõ mục tiêu vào ô
chat, và Router tự phân rã việc, chọn agent, dựng worktree, dựng/dùng lại
phiên, khoá tài nguyên, chạy, báo cáo — không phải mở tay một terminal
Claude/Codex/Antigravity nào.

> **V0.2: giao diện chính là một GIAO DIỆN WEB CỤC BỘ.** Bấm đôi
> `router-cc-web.cmd` — nó tự chạy server trên `127.0.0.1` và tự mở trình
> duyệt. Backend điều phối không đổi một dòng nào.
>
> Giao diện Qt (`router-cc-gui.cmd`) và TUI (`router-cc.cmd`) **ở lại làm
> đường gỡ lỗi/dự phòng**. Cả ba dùng **chung một sổ SQLite**, nên mở cạnh
> nhau vẫn thấy cùng dự án/việc/phiên.
>
> Vì sao đổi: clipboard và kéo-thả của **trình duyệt** là thứ người dùng
> đã quen và tin, và nó không phải do ta cài đặt lại.

> **Nó KHÔNG thiết kế lại Router V4.** Bốn thứ khó nhất — chấm điểm
> placement theo năng lực, cô lập worktree, cổng kiểm định "không tin worker
> tự khai PASS", phong bì kết quả — đã có, đã chạy thật, và được dùng
> NGUYÊN VẸN. Xem `docs/AI_ROUTER_V4.md` và
> `docs/reports/ROUTER_V4_REAL_PROOF.md`.

---

## 1. Chạy

### Giao diện WEB (đường chính từ V0.2)

**Bấm đôi `router-cc-web.cmd` trong Explorer.** Hết. Không PowerShell,
không Node, không cần tự khởi động backend, không cần đặt biến môi trường
nào trước.

Nó làm bốn việc, theo thứ tự: sinh token phiên → xin hệ điều hành một cổng
rỗng trên `127.0.0.1` → mở trình duyệt tới `http://127.0.0.1:<cổng>/?t=…`
→ chạy server.

```bash
# hoac tu dong lenh
./router-cc-web
python -m scripts.control_center.webmain

# phu thuoc: chi fastapi + uvicorn (da co trong server/requirements.txt)
python -m pip install -r requirements-control-center-web.txt
```

| Cờ | Ý nghĩa |
|---|---|
| `--root` | thư mục giữ sổ `.router/control_center/control.db` |
| `--port N` | cổng cố định (mặc định: hệ điều hành cấp một cổng rỗng) |
| `--khong-mo` | chạy server, KHÔNG tự mở trình duyệt |
| `--check` | chỉ kiểm phụ thuộc rồi thoát (launcher gọi cờ này trước) |

Cửa sổ console của launcher **là nhật ký server, và giữ nó lại là cố ý:
đóng cửa sổ = tắt server.** Dòng đầu in cả URL kèm token, nên nếu bạn đóng
tab thì mở lại được mà không phải khởi động lại.

**Không có bước build.** Frontend là SPA không bundler (ES module + `fetch`
+ WebSocket) do chính server phục vụ tĩnh. Nếu dùng Vite/Next thì bấm đôi
lần đầu sẽ phải `npm install` — cần mạng, cần chờ, và cần Node. Ngoài ra
`web/` của kho này là app Next.js của production `fanfic.world`; trộn giao
diện điều hành vào đó sẽ để một sự cố bên này làm hỏng bên kia.

Bố cục: thanh trên (dự án · đang chạy · bị chặn · pool · tìm · `?` · Cài
đặt), sidebar dự án bên trái, năm khung ở giữa (**Chat** mặc định · Tasks ·
Agents · Logs · Usage), inspector "đang chạy" bên phải.

### Giao diện ĐỒ HOẠ Qt (gỡ lỗi / dự phòng)

Bấm đôi `router-cc-gui.cmd` trong Explorer. Hết. Không cần terminal, không
cần đặt biến môi trường nào trước.

```bash
# hoac tu dong lenh
./router-cc-gui
python -m scripts.control_center.gui

# phu thuoc: chi PySide6
python -m pip install -r requirements-control-center-gui.txt
```

Bố cục: thanh trên (dự án · đang chạy · bị chặn · pool · tìm · `?` · `⚙`),
sidebar dự án bên trái, năm khung ở giữa (**Chat** mặc định · Tasks ·
Agents · Logs · Usage), inspector "đang chạy" bên phải gấp lại được.

**Dùng được mà không cần nhớ phím nào.** Mọi thao tác có nút. Hai lối tắt
duy nhất là *tuỳ chọn* và đều có nút tương đương: `Ctrl+Enter` gửi tin,
`F1` mở trợ giúp. `Esc` đóng hộp thoại. Clipboard hoạt động đúng như mọi
app Windows khác — xem mục 13.

`router-cc-gui.cmd` chạy bằng `pythonw.exe` nên **không** nhảy ra một cửa
sổ console đen kèm theo. Nếu không tìm thấy venv nào, nó rơi về `python`
trên PATH và **giữ cửa sổ lại** khi lỗi, để câu "thiếu PySide6" còn đọc
được thay vì nhấp nháy rồi mất.

### Giao diện TERMINAL (gỡ lỗi / dự phòng)

Vẫn nguyên vẹn, vẫn dùng **chung một sổ SQLite**, nên mở cạnh GUI vẫn thấy
cùng dự án/việc/phiên.

```bash
# giao dien
python -m scripts.control_center

# khong co TTY / kiem nhanh / CI
python -m scripts.control_center --headless

# gui mot cau vao o chat roi thoat
python -m scripts.control_center --chat "finish the production web and separately investigate AWS cleanup"
```

Phụ thuộc TUI dùng chung với Control Room đã có:

```bash
python -m pip install -r requirements-control-room.txt
```

| Cờ | Ý nghĩa |
|---|---|
| `--root` | thư mục giữ sổ `.router/control_center/control.db` (mặc định `cwd`) |
| `--probe` | dò sức khoẻ provider **ngay lúc khởi động**. CHẬM và tốn một lượt mỗi provider — mặc định TẮT. Tắt **không** có nghĩa là không bao giờ dò: xem dưới |
| `--max-parallel` | trần việc chạy song song (mặc định 3, trùng trần WRITE worker của router toàn cục) |
| `--no-recover` | bỏ qua đối soát phục hồi lúc khởi động |

Phím trong giao diện: `q` thoát · `enter` chi tiết việc · `p` tạm dừng ·
`o` tiếp tục · `s` dừng hẳn · `r` giao lại · `g` duyệt cổng · `u` đo usage.

---

## 2. Ranh giới với Router V4

Chỗ duy nhất đáng tranh cãi trong bản này, nên nói thẳng.

| Việc | Ai làm |
|---|---|
| Chấm điểm và chọn `(runtime, model)` | **Router V4** `Scheduler.decide()` |
| Dựng adapter, gọi tiến trình agent | **Router V4** `Executor.run()` |
| Cô lập worktree, kiểm phạm vi ghi | **Router V3** `WorktreeManager` + `pool/validation` |
| Lease KHE runtime | **Router V4** `LeaseStore` |
| Phong bì kết quả, nhật ký thô | **Router V4** `ResultEnvelope` / `RawLogStore` |
| Dự án, ô chat, phân rã ý định | Control Center |
| Trạng thái việc 8 giá trị, phụ thuộc, ưu tiên | Control Center |
| REUSE / CREATE / WAIT phiên | Control Center |
| Khoá tài nguyên fs/dịch vụ/production | Control Center |
| Phong bì quyền AUTO/GATED | Control Center |
| Bền + phục hồi sau khởi động lại | Control Center |

**Vì sao Control Center gọi thẳng `Executor.run()` chứ không gọi
`RouterV4.run_task()`:** `run_task` tự chọn placement cho từng việc — đúng
cho một mission chạy một lần, nhưng nó **không thể dùng lại một phiên**, vì
với nó phiên không tồn tại. Dùng lại phiên là yêu cầu lõi của V0.1, nên
placement do `SessionManager` chốt, còn mọi cơ chế bên trong `Executor`
chạy y nguyên.

### Thay đổi DUY NHẤT chạm vào Router V4

`scripts/router_v4/executor.py` được thêm **một tham số tuỳ chọn**:

```python
Executor(..., worktree_provider=None)
```

`None` = hành vi mặc định, không đổi một bit nào (177 bài kiểm V3/V4 vẫn
xanh). Điểm nối này tồn tại cho một bên gọi sống lâu hơn một mission:
Control Center giữ một phiên agent ấm qua nhiều việc, và phiên đó sở hữu
MỘT worktree. Không có hook này, bên gọi phải chép lại cả `run()` chỉ để
đổi ba dòng tạo cây — và bản chép sẽ lệch dần khỏi bản thật.

---

## 3. Trạng thái việc

```
QUEUED    sẵn sàng, chờ tới lượt.                    Không phải làm gì.
WAITING   chờ thứ SẼ TỰ HẾT: phụ thuộc, hoặc khoá.   Không phải làm gì.
BLOCKED   chờ thứ KHÔNG tự hết: cần NGƯỜI quyết.     ← phải can thiệp
RUNNING   đang chạy trên một phiên agent.
REVIEW    xong, nhưng hợp đồng đòi review độc lập.
DONE / FAILED / PAUSED
```

Tách `WAITING` khỏi `QUEUED` và `BLOCKED` là để bảng điều khiển trả lời
được câu hỏi quan trọng nhất lúc 3 giờ sáng: **"có việc nào đang chờ TÔI
không?"** Gộp ba trạng thái này (như hàng đợi V3 làm với `queued`) thì
không trả lời được.

Chuyển trạng thái được **kiểm bằng máy** (`model.kiem_chuyen`). `DONE` là
ngõ cụt — một việc đã DONE quay lại RUNNING sẽ ghi đè `ended_at` và làm sai
mọi báo cáo theo thời gian, một cách im lặng.

### Thử lại: có trần, và đổi chỗ

`Executor.run()` chạy đúng MỘT lượt. Đường thử lại của Router V4 nằm trong
`RouterV4._chay_co_thu_lai`, mà Control Center cố ý không đi qua (nó cần giữ
placement của phiên). Không có gì bù lại thì **một lần nhà cung cấp hắt hơi
là việc hỏng vĩnh viễn** — với một hệ chạy qua đêm không người trực, đó là
chế độ hỏng thường gặp nhất.

Nên: hỏng → nhả phiên cũ → về `QUEUED` → lượt sau `decide()` chọn **chỗ
khác**. Cùng cơ chế `reassign`, không phải một đường định tuyến thứ hai. Đo
thật: lượt 1 `RT01`, lượt 2 `RT02`, lượt 3 `RT01`, rồi `RETRY_EXHAUSTED`.

Trần là `MAX_ATTEMPTS = 3`, đếm bằng `attempts` do `claim_task` tự tăng (nên
nó đếm được, không tin vào bộ nhớ). Thử lại vô hạn là "bão thử lại" — đúng
chế độ hỏng số 4 mà `leases.py` liệt kê.

**KHÔNG BAO GIỜ thử lại** bốn lý do sau, vì chạy lại y hệt sẽ hỏng y hệt và
chỉ tốn thêm quota:

| Lý do | Vì sao |
|---|---|
| `security_gate` | luật lấy thẳng từ V4 — thử lại chỉ tăng cơ hội lọt một thay đổi chưa thử giống credential |
| `tool_permission_denied` | bức tường **cấu hình**, không phải nhiễu |
| `requires_decision` | cần NGƯỜI, không cần lượt nữa |
| `no_eligible_placement` | không có worker đủ năng lực; lượt sau vẫn thế |

---

## 4. Phiên: REUSE / CREATE / WAIT

Luật xét **theo đúng thứ tự này**; luật chặn đứng trước luật cấp phát.

| # | Điều kiện | Kết luận |
|---|---|---|
| 0 | tài nguyên đang do việc khác giữ | **WAIT** |
| 1 | phạm vi ghi giẫm lên một phiên đang BẬN | **WAIT** |
| 2 | có phiên RẢNH, khoẻ, phạm vi tương thích | **REUSE** |
| 3 | đã chạm trần phiên/dự án | **WAIT** |
| 4 | còn lại | **CREATE** |

Xét luật 1 trước luật 2 có lý do: một phiên đang chạy việc khác trên cùng
phạm vi thì **không được dùng lại**, và cũng **không được** để việc mới
chạy song song vào đó bằng một phiên khác.

Tương thích phạm vi = phạm vi việc **nằm gọn trong** phạm vi phiên. Cho
phép vượt ra nghĩa là phiên âm thầm mở rộng quyền ghi của chính nó qua từng
việc. Việc CHỈ ĐỌC tương thích với mọi phiên rảnh.

Mỗi quyết định mang theo `trace` — danh sách luật đã xét, theo thứ tự. Một
bộ chọn phiên không nói được vì sao nó dựng phiên thứ tư là một bộ chọn
không ai gỡ lỗi được.

### REVIEW không phải ngõ cụt

Hợp đồng của việc rủi ro cao (`production`, `auth`, `security`, `migration`,
`concurrency`…) đặt `independent_review_required`, nên việc xong đi vào
`REVIEW` chứ không nhảy thẳng `DONE`. Control Center **tự đặt một việc
review là CON của nó**:

```
demo.t1           fix the auth permission check in web/admin   REVIEW
└─ demo.t1-review review độc lập: fix the auth permission…     QUEUED
```

Độc lập THẬT, không chỉ trên danh nghĩa — dùng thẳng `hop_dong_review()`
của Router V4:

- `exclude_families=(họ model của tác giả,)` — tác giả không tự chấm bài.
- **không** `repo_write` — reviewer đọc và báo cáo, không sửa. Một reviewer
  sửa được thì không còn là kiểm tra độc lập, và không ai review phần sửa đó.
- reviewer được trỏ vào **worktree của việc cha**, không phải gốc kho. Bằng
  chứng thật 2026-09-03: một nút review báo "không tìm thấy tệp" trong khi
  tệp CÓ tồn tại — chỉ là ở worktree của nút trước.

Khép lại:

| Review kết thúc | Việc cha thành |
|---|---|
| xong, không phát hiện gì | `DONE` |
| xong, có phát hiện | `DONE`, phát hiện được gắn vào phong bì của cha + sự kiện mức `WARNING` |
| **không chạy được** | `BLOCKED` — không kiểm chéo được thì KHÔNG được tuyên bố là xong |

Phát hiện của reviewer **không** tự động làm việc cha thất bại (nó là thông
tin cho người tích hợp, đúng như `RouterV4.run_task` đã quyết) — nhưng nó
PHẢI hiện ra, nếu không cả lượt review chỉ là đốt quota.

Một nới lỏng hẹp trong bộ chọn việc sẵn sàng làm cho việc này chạy được:
việc review phụ thuộc vào cha, mà cha chỉ rời `REVIEW` **sau khi** review
xong. Đòi cha phải `DONE` trước thì hai bên khoá nhau vĩnh viễn. Nên với
đúng quan hệ cha–con này, `REVIEW` là đủ điều kiện. Nới lỏng chỉ áp cho
`parent_id` của chính việc đó; phụ thuộc thường vẫn phải `DONE` thật.

---

### Dò sức khoẻ là LƯỜI, không phải không có

`dung_fabric` đặt mọi runtime ở `OFFLINE`/`last_seen=0`, và
`Scheduler.decide` loại sạch mọi ứng viên với lý do *"runtime KHÔNG nhận
dispatch"*. Nên **`--probe` tắt mà không dò gì cả** đồng nghĩa với: không
việc nào được giao, mãi mãi. Đã đo thật — một lượt chứng minh READ+WRITE chờ
**901s, 0 lượt**, không placement nào.

Nên Control Center dò **lười**: không dò lúc dựng (giữ đúng ý "mở app không
gọi mạng"), mà dò lần đầu **khi thật sự có việc chờ giao**, rồi giữ kết quả
trong **300s**.

| Tình huống | Có gọi mạng? |
|---|---|
| Mở giao diện, xem sổ, không có việc chờ | **không** |
| Có việc chờ giao, chưa dò lần nào | có — một lần |
| Nhịp tiếp theo, còn trong hạn 300s | không |
| Quá hạn 300s và vẫn cần placement | có — dò lại |
| Fabric do bên gọi đưa vào (bộ kiểm) | **không bao giờ** |
| Dò hỏng | ghi `FABRIC_PROBE_FAILED`, việc vẫn chờ — không đoán là sống |

Ô cuối là chỗ dễ sai nhất: `do_suc_khoe` gọi thật ra `agy`/`codex`, nên dò
một fabric dựng tay sẽ biến bộ kiểm offline thành bộ kiểm gọi mạng.

## 4b. Lệnh agent được phép — allowlist HẸP, khớp chuỗi CHÍNH XÁC

Quyền `command(...)` của `agy` khớp **chuỗi lệnh chính xác**. Đo 2026-09-08:
`command(git)` và `command(git *)` đều KHÔNG cho chạy `git status
--porcelain`; không glob, không tiền tố. Hệ quả: một thao tác có **tham số
thay đổi** không biểu diễn được bằng một allow-rule an toàn, và lối thoát
duy nhất còn lại — `command(*)` — là truy cập hệ tệp tuỳ ý bằng shell.

Nên agent đi qua **một wrapper cố định** với tập động từ **hữu hạn**:
`scripts/cc_agent_tool.py`. Mỗi động từ ánh xạ 1-1 tới một lệnh **đã có
trong `.github/workflows/ci.yml`** — không phát minh lệnh mới.

| Động từ | Chạy thật | Cấp cho agent? |
|---|---|---|
| `changes` | `git status --porcelain -uall` | **có** |
| `compile` | `python -m compileall -q server scripts` | **có** |
| `tests` | `python -m unittest discover -s scripts/tests -t .` | **KHÔNG** (xem dưới) |

**`tests` KHÔNG được cấp cho agent — và lý do đã đổi hai lần.** Đáng kể lại
đủ, vì cả hai lần đều dạy một điều khác nhau.

*Lần một, lý do SAI.* Bản đầu không cấp `tests`, ghi lý do là "bộ kiểm chạy
~430s trong khi một lượt headless có trần 180s". Con số 180s là của **kịch
bản thử của chính tôi** (`--print-timeout 180s` gõ cứng trong probe), không
phải của sản phẩm. Đường thật:

```
Executor       timeout = c.execution.max_wall_time    (2400s với việc có ghi)
WarmAgyWorker  --print-timeout = turn_timeout * 4     (9600s)
WarmAgyWorker  _cho("result", timeout=turn_timeout)   (2400s)
```

Một lượt 430s nằm thoải mái trong trần; đo lại bằng tiến trình `agy` thật,
`tests` xong trong **239s**. Lý do cũ tan. Động từ được cấp.

*Lần hai, lý do ĐÚNG — và nó chặn hẳn.* Bài review đối kháng trước phát hành
chỉ ra: worktree của việc là nơi agent **được phép ghi**, và
`unittest discover -s scripts/tests` **nạp rồi chạy** mọi tệp khớp `test_*.py`
trong đó. Nên agent chỉ cần ghi `scripts/tests/test_x.py` vào cây của chính
nó rồi gọi đúng chuỗi lệnh đã được duyệt — Python thực thi nội dung đó ngay,
với toàn quyền của tiến trình. Các cổng `scope`/`diff`/`security` chạy **sau
lượt**, nên chúng thấy tệp lạ quá muộn: mã đã chạy rồi.

Đây không phải rủi ro lý thuyết mà là **thực thi mã tuỳ ý qua một allow-rule
hẹp** — đúng thứ cả mục 4b này dựng lên để chặn. Rào `cwd` ở dưới không cứu
được, vì cây độc hại chính là cây hợp lệ. Nên `tests` bị **rút khỏi
allowlist**: động từ vẫn còn trong `cc_agent_tool.py` để *Control Center* (đã
tin cậy) tự chạy, nhưng không có mục `command(...)` nào cấp nó cho agent —
`planner.KHONG_CAP_CHO_AGENT` giữ đúng ranh giới đó và có bài kiểm khoá lại.

Bài học chung của cả hai lần: một lệnh an toàn hay không **không nằm ở tên
lệnh**, mà ở chỗ tệp nó đọc do ai ghi.

Hai mục trong `~/.gemini/antigravity-cli/settings.json`:

```json
"permissions": { "allow": [
  "command(python C:\FanficWorkers\router-control-center\scripts\cc_agent_tool.py changes)",
  "command(python C:\FanficWorkers\router-control-center\scripts\cc_agent_tool.py compile)"
]}
```

**Không có tệp allowlist theo từng dự án** — `agy` chỉ đọc một tệp cấu hình
người dùng duy nhất. Đó là giới hạn của công cụ, không phải lựa chọn.

### `cwd` không mở rộng được phạm vi

`python -m unittest discover -s scripts/tests -t .` giải đường dẫn theo
`cwd`. Đổi `cwd` sang một cây khác có `scripts/tests/` riêng sẽ khiến **cùng
một chuỗi lệnh đã được duyệt** nạp và chạy mã ở đó. Chặn bằng hai lớp:

1. allow-rule ghim **đường dẫn tuyệt đối** tới wrapper → `cwd` không đổi
   được *script nào* chạy;
2. `_kiem_cwd()` bắt buộc `cwd` là gốc kho hoặc trong `.router/worktrees/`,
   ngoài ra **từ chối và thoát 2**.

Thêm: argv của mỗi động từ là **hằng số**, không phần tử nào đến từ dòng
lệnh; không `shell=True`; mọi đầu ra qua `packet.redact`.

Kiểm bằng máy: `scripts/tests/test_control_center_allowlist.py` (offline, 11
bài — khoá cả *lệch* lẫn *nới*) và `scripts/control_center_allowlist_proof.py`
(tiến trình `agy` thật). Quyền được đọc **live**: `agy` nạp settings lúc
sinh tiến trình, nên không cần khởi động lại gì.

### Đối soát lời khai thiếu (B5) — vẫn FAIL CLOSED

Cổng `diff` của Router V4 **không bị sửa một dòng nào**: nó vẫn hard-fail khi
worker báo `ok`, để `changes` rỗng, mà đĩa có đổi. Có một bài kiểm khoá đúng
điều đó lại.

Control Center làm một việc KHÁC và CHẶT HƠN ở tầng trên: thay vì tin danh
sách worker khai, nó lấy danh sách THẬT từ `git` rồi **kiểm lại chính danh
sách đó**.

Chỉ áp đúng một trường hợp hẹp — `changes` **rỗng**, đĩa **có** đổi, và
`diff` là cổng **duy nhất** hỏng. Điều kiện để đi tiếp, tất cả phải đúng:

1. mọi tệp đổi THẬT nằm trong `allowed_scope`, không chạm `forbidden_scope`;
2. `scope_violations` của tầng kiểm định cũng rỗng;
3. cổng `security` ĐẠT — nó vốn chạy trên diff THẬT của đĩa (kể cả tệp chưa
   theo dõi), nên là phán quyết trên tập thật chứ không trên lời khai;
4. mọi cổng khác ĐẠT.

Một tệp ngoài phạm vi ⇒ **TỪ CHỐI**, việc ở lại `FAILED`, kèm sự kiện
`UNDERDECLARED_CHANGES_REJECTED` mức ALERT. Chấp nhận thì ghi
`UNDERDECLARED_CHANGES` (WARNING) và **điền lại `changes` bằng tập THẬT**, để
mọi báo cáo về sau nói đúng thứ đã xảy ra.

Đây không phải nới cổng: nó thay một phép kiểm dựa trên *lời khai* bằng một
phép kiểm dựa trên *trạng thái đĩa*, và không bao giờ bỏ qua một thay đổi
chưa được kiểm. Chiều ngược lại — khai có sửa mà đĩa SẠCH — **không bao giờ**
được đối soát: đó là thất bại im lặng thật.

### Dọn trạng thái thử nghiệm

`./router-cc --remove-project <id>` gỡ MỘT dự án và mọi hàng của nó khỏi sổ,
trong một giao dịch. **Không** phải `xoá control.db` — cách đó xoá luôn mọi
dự án thật, mọi lịch sử, mọi khoá đang giữ.

Từ chối gỡ `fanfic`/`router` (dự án thật của bản phát hành — dùng `archived`
nếu muốn ẩn), đòi xác nhận tường minh ở tầng API, và **không đụng tới
worktree trên đĩa** — luật "không bao giờ tự xoá worktree" áp ở đây như mọi
nơi khác.

---

## 5. Khoá tài nguyên

Ba lớp, **không cùng luật**:

| Lớp | Xung đột khi | Tự thu hồi khi hết hạn |
|---|---|---|
| `FILESYSTEM` | giao nhau **tiền tố đường dẫn**, cả hai chiều | có |
| `SERVICE` | trùng khớp định danh | có |
| `PRODUCTION` | trùng khớp định danh | **KHÔNG BAO GIỜ** |

`web/admin` xung đột với `web/admin/content-queue` theo **cả hai chiều** —
cha chặn con, con chặn cha. So theo ĐOẠN chứ không theo chuỗi trần:
`web/admin` **không** được xung đột với `web/administration`.

**Vì sao khoá production không tự hết hạn.** Khoá có hạn tồn tại để một
tiến trình chết không khoá hệ thống vĩnh viễn — đánh đổi đó đúng cho
worktree và SAI cho production. Một khoá production quá hạn có hai khả
năng: tiến trình đã chết, hoặc một thao tác production đang chạy lâu hơn
dự kiến. Đoán sai khả năng thứ hai nghĩa là để việc thứ hai chen vào giữa
một lần cutover. Nên `reclaim()` chỉ đụng hai lớp đầu; khoá production quá
hạn được **báo cáo cho người**, và chỉ người mới gỡ được. Dấu hết hạn ở lớp
đó là **ngưỡng báo động**, không phải hạn thuê.

Xin khoá là **tất cả hoặc không cái nào**, và thứ tự xin được **sắp xếp** —
hai việc xin cùng hai tài nguyên luôn xin theo cùng thứ tự, nên không ôm
chéo nhau.

---

## 6. Phong bì quyền

| AUTO — tự làm, không hỏi | GATED — DỪNG, hỏi người |
|---|---|
| đọc/tìm kiếm kho | deploy production |
| sửa tệp **trong worktree mình sở hữu** | thay đổi phá huỷ trên production |
| lint / test / build | IAM / gốc tin cậy |
| xem phụ thuộc | xoay hoặc lộ bí mật |
| commit cục bộ | hoá đơn / mở rộng tài nguyên |
| | `git push`, viết lại lịch sử |

Việc chạm lớp GATED được tạo thẳng ở `BLOCKED` kèm **câu hỏi cụ thể** —
không bao giờ vào hàng đợi. Cho nó `QUEUED` rồi chặn ở bước sau nghĩa là
chỉ cần MỘT lỗi lập lịch là nó chạy.

Mở cổng chỉ có một đường: người dùng bấm `g` và xác nhận. Việc đó ghi một
sự kiện `GATE_APPROVED` mức `ALERT` kèm tên người duyệt.

**Ba thứ module này KHÔNG làm:**

1. **Không nới rào có sẵn.** Phong bì chỉ biết nói KHÔNG.
   `destructive_actions_allowed` vẫn luôn `False`, `forbidden_scope` vẫn
   được `contract.py` nhồi thêm `FORBIDDEN_ALWAYS`, cổng kiểm định của V3
   vẫn chạy y nguyên. Đây là tầng thứ BA, không phải tầng thay thế.
2. **Không `--dangerously-skip-permissions`, không `bypassPermissions`.**
3. **Không tự quyết việc GATED.** `PermissionClass` chỉ có hai giá trị và
   không giá trị nào nghĩa là "bỏ qua".

Phong bì được **render vào chính văn bản hợp đồng gửi agent**, không chỉ
lưu bên cạnh: một agent không biết vì sao nó bị chặn sẽ thử một đường vòng
khác thay vì dừng và báo `blocked`.

---

## 7. Worktree

- Một **phiên** sở hữu **một** worktree. Việc tiếp theo của chính phiên đó
  dùng lại nó.
- **Không dùng lại giữa hai phiên**, kể cả khi phạm vi trông rời nhau.
  "Phạm vi rời nhau" là lời khai của hợp đồng; thứ thật sự nằm trên đĩa là
  `git status`. Một worktree thừa tốn vài trăm MB; một lần trộn công việc
  của hai agent tốn cả buổi để gỡ.
- Cây **bẩn** (còn thay đổi chưa commit) **không** được dùng lại — và cũng
  **không** bị xoá. Việc mới nhận cây sạch, cây cũ được đánh dấu `DIRTY`.
- **KHÔNG TỰ XOÁ, không bao giờ.** `doi_soat()` chỉ đánh dấu. Một cây hỏng
  là bằng chứng, và nó có thể chứa công việc chưa commit của một agent vừa
  chết.
- `assert_exclusive()` **ném** thay vì cảnh báo. Một cảnh báo sẽ bị nuốt
  trong log lúc 3 giờ sáng và hai agent vẫn giẫm lên nhau.

---

## 8. Usage — không bao giờ bịa số

| Nhãn | Nghĩa |
|---|---|
| `ACTUAL` | Control Center hoặc Router **tự đếm được tại chỗ**. |
| `ESTIMATED` | ước lượng có nguồn khai báo (`Source.DECLARED` của V4). |
| `UNAVAILABLE` | không quan sát được. Giá trị là `None`, **không phải `0`**. |

Vế cuối được ép bằng `UsageMetric.__post_init__` — khai `UNAVAILABLE` mà
vẫn có giá trị thì ném lỗi. Lý do: `0` trong cột "còn lại" đọc thành "đã
cạn", `0` trong cột "đã dùng" đọc thành "chưa tiêu gì". Cả hai đều là kết
luận, và cả hai đều sai khi sự thật là "không đo được".

Sự thật đo được về từng nhà cung cấp:

| Provider | Quan sát được gì |
|---|---|
| Antigravity | `agy --print /credits` trả **văn bản cho người đọc**. Đọc được dòng `Remaining credits` thì đó là ACTUAL; phần còn lại giữ nguyên làm văn bản thô. |
| Codex | **không có** lệnh usage/quota. Tín hiệu duy nhất: còn đăng nhập hay không → `UNAVAILABLE`. |
| Claude Code | **không lộ ra** usage. Chỉ suy ra được từ phản hồi rate-limit thật → `UNAVAILABLE`. |

Gọi CLI nhà cung cấp là thao tác **chậm và tốn một lượt**, nên nó **không
bao giờ** chạy trong vòng lặp vẽ giao diện — chỉ khi người dùng bấm `u`.
Có một bài kiểm khoá lại điều đó.

---

## 9. Bền + phục hồi

Sổ ở `.router/control_center/control.db` (SQLite, WAL, một kết nối mỗi
luồng — cùng khuôn đã chứng minh của `router_v3/pool/store.py`).

`recover()` chạy lúc khởi động, theo thứ tự an toàn tăng dần:

1. **khoá** — hết hạn thì thu, **trừ** khoá production (cần người).
2. **phiên** — có PID sống → gắn lại; chết → `DEAD`; **không có PID → KHÔNG
   coi là chết**, chỉ đưa về `IDLE`. Tuyên bố chết một phiên còn sống sẽ
   khiến Control Center dựng phiên thứ hai chồng lên nó.
3. **worktree** — đối soát với đĩa; chỉ đánh dấu.
4. **việc** — `RUNNING` mà chủ đã chết → `QUEUED` để xét lại, **không phải
   `FAILED`**. Tiến trình agent có thể vẫn đang chạy thật (tắt Control
   Center không giết nó); đánh `FAILED` là vứt luôn công việc đã làm. Chỉ
   khi đã cạn lượt thử mới chuyển `BLOCKED` để người xem.

`shutdown()` **không** giết agent đang chạy và **không** xoá worktree. Tắt
Control Center không được phép phá công việc đang dở.

---

## 10. Bằng chứng

| Loại | Ở đâu | Chạy gì |
|---|---|---|
| Lát cắt dọc, tất định, offline | `scripts/tests/test_control_center_slice.py` | agent giả **ghi tệp thật vào worktree thật** |
| Lõi: sổ, khoá, quyền, phân rã | `scripts/tests/test_control_center_core.py` | thuần hàm |
| Giao diện | `scripts/tests/test_control_center_ui.py` | Textual `run_test()`, không cần màn hình |
| **Agent THẬT** | `scripts/control_center_real_proof.py` | tiến trình `agy`/`codex` thật, kho thật |

```bash
python -m unittest discover -s scripts/tests -t .
python scripts/control_center_real_proof.py --probe          # tốn quota
```

Bằng chứng thật tách khỏi bộ kiểm có chủ đích: nó **tốn quota**, **không
tất định**, và **chậm**. Ba lý do đó không làm nó bớt cần thiết — nhưng một
bộ kiểm tự tiêu quota mỗi lần chạy là một bộ kiểm không ai dám chạy.

---

## 11. API cục bộ — vì sao localhost KHÔNG phải là riêng tư

Đây là ranh giới mới của V0.2, và nó mang một lớp rủi ro mà app desktop
không có. Ba điều phải nói thẳng, vì mỗi điều là một cách người ta hay làm
sai một localhost server:

**1. Mọi trang web bạn đang mở đều GỬI được request tới
`http://127.0.0.1:<cổng>`.** Trình duyệt cho phép request cross-origin; nó
chỉ ngăn *đọc* phản hồi. Nghĩa là nếu không có gì chặn, một quảng cáo ở tab
khác có thể `POST /api/chat` và tạo việc trong Router của bạn — và bạn sẽ
không thấy request đó ở đâu cả.

⇒ **Mỗi request phải mang token của phiên.** Không token thì `401`, **kể cả
`GET`**. Token sinh mới mỗi lần chạy, so bằng `hmac.compare_digest`.

**2. DNS rebinding đi vòng qua phép kiểm origin.** Một tên miền của kẻ tấn
công có thể trỏ về `127.0.0.1`; lúc đó `Origin` là của họ nhưng request tới
đúng server này.

⇒ **`Host` được kiểm tường minh**, chỉ nhận `127.0.0.1`/`localhost`. Và
kiểm `Host` **TRƯỚC** kiểm token: chính việc token *có thể* đúng là điều
đang được phòng, nên đừng để phép kiểm token quyết định trước.

**3. CORS là cửa, không phải khoá.** Frontend là same-origin (server tự
phục vụ nó) nên nó **không cần** CORS. Thêm CORS chỉ mở cửa cho người khác.

⇒ **Không có CORS**, và có bài kiểm đòi `CORSMiddleware` không được import.

Cộng thêm:

| Thứ | Vì sao |
|---|---|
| bind `127.0.0.1`, không bao giờ `0.0.0.0` | một ký tự khác biệt giữa "công cụ cá nhân" và "mở cổng điều khiển Router ra cả mạng LAN" |
| cổng NGẪU NHIÊN do hệ điều hành cấp | cổng cố định làm một trang web đoán được đích; cổng đổi mỗi lần thì nó phải quét, và token vẫn chặn |
| token đi qua URL rồi bị XOÁ khỏi URL | `history.replaceState` ngay khi trang nạp, nên nó không nằm lại trong lịch sử hay trong `Referer` |
| `docs_url=None` | trang `/docs` của FastAPI liệt kê toàn bộ API — với công cụ cá nhân thì đó chỉ là bề mặt tấn công |
| `nosniff` trên blob | không để trình duyệt tự đoán một `.txt` thành HTML rồi chạy nó |
| CSP chỉ `'self'` | không CDN, không font ngoài, không `unsafe-eval` |
| mọi payload qua `packet.redact` | có bài kiểm đòi API không bao giờ phát ra thứ giống credential |

**Token phiên KHÔNG phải credential của nhà cung cấp.** Nó là bí mật cục bộ
giữa trang và server của chính nó. Ranh giới "không rò bí mật ra frontend"
vẫn giữ nguyên: không API key, không cookie, không mật khẩu nào đi ra.

37 bài kiểm ở `scripts/tests/test_control_center_webapi.py` — đặt ở đó chứ
không ở `tests/` vì tầng này không cần Qt, nên **CI cưỡng chế** chúng trên
Linux mỗi PR. Một ranh giới an toàn không nên phụ thuộc vào việc ai đó có
nhớ chạy bộ kiểm cục bộ hay không.

---

## 12. Tệp đính kèm — cục bộ, địa chỉ hoá theo nội dung

Bốn đường vào, một đường xử lý: dán `Ctrl+V` (kể cả ảnh `Win+Shift+S`),
kéo-thả, nút **Đính kèm tệp…**, và dán tệp copy từ Explorer. Trình duyệt
biến cả bốn thành cùng một `multipart/form-data`, nên phía server chỉ có
**một** cửa và **một** chỗ để kiểm.

**Bốn bất biến**, mỗi cái có bài kiểm khoá lại ở
`scripts/tests/test_control_center_attachments.py` (37 bài, CI cưỡng chế):

1. **Nhị phân KHÔNG vào SQLite.** Sổ chỉ giữ metadata. Có bài kiểm đo kích
   cỡ tệp `.db` trước/sau khi thêm một tệp 4 MB.
2. **Đường dẫn lưu trữ do backend sinh:** `objects/<sha[:2]>/<sha>.<đuôi>`,
   suy ra hoàn toàn từ băm nội dung + một đuôi lấy từ allowlist. **Không
   một byte nào** của tên tệp người dùng đi vào đường dẫn, nên `../../`
   không có chỗ chen vào. Tên gốc chỉ để hiển thị.
3. **Đọc phải qua `attachment_id`.** `duong_dan()` kiểm lại containment
   **sau `resolve()`**, mỗi lần. Mô hình đối thủ là *kẻ tấn công ghi được
   vào sổ* — nên có bài kiểm sửa tay `rel_path` thành
   `../../../Windows/System32/config/SAM` và đòi bị TỪ CHỐI. Kiểm bằng
   chuỗi thì lọt.
4. **Agent chỉ nhận đính kèm của ĐÚNG việc của nó.** `cho_agent(task_id)`
   không bao giờ trả cả kho dự án; "cùng dự án" là phạm vi quá rộng để làm
   ranh giới quyền. Mặc định là **không cấp cho ai**.

Và một lời hứa: **tầng này không tải tệp lên đâu cả.** Có bài kiểm đọc cây
cú pháp đòi nó không import `requests`/`urllib`/`socket`/`boto3`/… — grep
văn bản sẽ báo động vì chính docstring nói về việc không tải lên, cùng cái
bẫy đã gặp ở `cc_agent_tool`.

An toàn khác:

- **Đuôi tệp phải khớp CHỮ KÝ BYTE.** Đổi đuôi tệp là thao tác dễ nhất thế
  giới; một tệp thi hành đổi tên thành `anh.png` bị từ chối.
- **Allowlist fail-closed.** `.exe/.dll/.msi/.scr/.vbs/.lnk/.reg/.jar`
  không bao giờ nhận được — nên đường "bấm để mở" không thể mở một thứ thi
  hành.
- **Tên tệp được làm sạch:** bỏ mọi thành phần thư mục (`\` và `/`), ký tự
  điều khiển, ký tự Windows cấm, dấu chấm/khoảng trắng hai đầu (Windows tự
  cắt chúng nên `..` là đường dẫn nguỵ trang), tên dành riêng của hệ điều
  hành (`CON.txt` không mở được), cắt độ dài nhưng GIỮ đuôi.
- **Dòng chảy thật:** băm và chép cùng một lượt, khối 1 MiB, vào tệp tạm
  rồi mới đổi tên vào chỗ. Một tệp 2 GB thì tiến trình cũng chỉ giữ 1 MiB.
  Có bài kiểm **đếm số lần gọi `read`**, để một ngày nào đó ai đổi sang
  `f.read()` thì nó hỏng.
- Trần 200 MB/tệp; tệp rỗng bị từ chối; tệp bị từ chối **không để lại rác**
  trong kho.

Định dạng hỗ trợ: ảnh (png/jpg/jpeg/webp/gif/bmp) · tài liệu
(pdf/txt/md/docx/rtf/odt) · dữ liệu (csv/json/xlsx/tsv/xml/yaml) · mã &
cấu hình & nhật ký (py/js/ts/sql/toml/ini/log/…) · nén (zip).

**Mã đính kèm là TẤT ĐỊNH:** cùng phạm vi + cùng nội dung + cùng tên → cùng
mã. Nên dán lại đúng một ảnh vào đúng một tin nhắn hai lần không sinh ra
hai bản ghi. Cùng nội dung ở hai dự án thì **dùng chung blob** nhưng là
**hai bản ghi** — vì quyền truy cập khác nhau. Xoá một bản ghi không làm
hỏng bản ghi kia; blob chỉ bị dọn khi không còn ai tham chiếu.

---

## 13. Clipboard và chuột — cổng nghiệm thu của V0.1.1

Bản V0.1 bị từ chối vì đúng một câu: *"ordinary clipboard interaction is not
reliable"*. Nên đây không phải một mục tính năng, nó là **điều kiện phát
hành**, và nó được kiểm bằng máy ở
`tests/test_control_center_gui_clipboard.py` (17 bài).

Nguyên tắc duy nhất, và mọi thứ khác là hệ quả: **để Qt làm việc của Qt.**
`QPlainTextEdit`/`QTextEdit`/`QTableWidget` đã mang sẵn clipboard thật của
Windows. Gần như mọi lỗi clipboard trong một app Qt là do tác giả *giành*
tổ hợp phím hoặc *chặn* `keyPressEvent`. Nên ba luật:

| Luật | Vì sao |
|---|---|
| Không `QShortcut`/`QAction` nào ở phạm vi ứng dụng đăng ký Ctrl+C/V/X/A | Giành một trong số đó là lấy mất hành vi clipboard của chính ô đang gõ. Bài kiểm **quét cửa sổ thật** và đòi danh sách rỗng |
| `keyPressEvent` chỉ bắt ĐÚNG `Ctrl+Return`, mọi phím khác gọi `super()` | Một `return` sớm cho "mọi phím có Ctrl" là cách dễ nhất ăn mất Ctrl+V |
| Ô chỉ-đọc dùng `setReadOnly(True)`, **không bao giờ** `setEnabled(False)` | Cách thứ hai làm mất luôn khả năng chọn — và nó là cách phổ biến nhất người ta làm một ô "chỉ đọc" |

Còn `Ctrl+Enter` (gửi tin) ở **phạm vi widget**, không phạm vi ứng dụng: ở
phạm vi ứng dụng nó sẽ bắn cả khi con trỏ đang ở ô tìm kiếm.

Cụ thể những gì hoạt động, và ở đâu:

| Việc | Đường chuột | Đường bàn phím |
|---|---|---|
| Dán prompt nhiều dòng vào ô chat | chuột phải → Paste | Ctrl+V |
| Copy tin nhắn / báo cáo agent | bôi đen → chuột phải → Copy | Ctrl+C |
| Copy một khối mã | nút **Copy** trên khối | Ctrl+C sau khi bôi đen |
| Copy nhật ký | nút **Copy** / **Copy All** | Ctrl+A rồi Ctrl+C |
| Copy hàng bảng Tasks/Agents/Usage | **Copy hàng đang chọn** / **Copy All** | Ctrl+C |
| Đóng hộp thoại | nút **✕** | `Esc` |

Ba thứ được kiểm riêng vì chúng là ba dòng riêng trong danh sách nghiệm
thu: **nhiều dòng** dán nguyên vẹn (kể cả dấu xuống dòng cuối), **tiếng
Việt có dấu** không hỏng, và **prompt 200 000 ký tự** không bị cắt.

Một chi tiết nhỏ nhưng hay sai: `QTextCursor.selectedText()` trả U+2029
(PARAGRAPH SEPARATOR) thay cho mọi ngắt dòng. Copy thẳng giá trị đó ra
clipboard sẽ khiến người dùng dán vào Notepad và thấy **một dòng dài**.
`KhungNhatKy.copy_chon()` đổi lại thành `\n`, và có bài kiểm khoá.

**Enter xuống dòng, KHÔNG gửi.** Ngược thói quen của nhiều app chat, nhưng
ở đây gõ nhiều dòng là việc thường ngày và một cú Enter vô tình sẽ mất bản
nháp. Nút **Gửi** là đường chính.

---

## 14. UTF-8 tường minh — vì sao locale không được quyết định codec

**Sự cố:** `Router Control Center.exe` đã đóng gói **chết ngay khi bấm
đôi**, trên máy Windows locale mặc định:

```
Failed to execute script 'desktop' due to unhandled exception:
UnicodeEncodeError: 'charmap' codec can't encode character 'ư'
character maps to <undefined>
  ... desktop.py line 145 -> encodings/cp1252.py
```

`U+01B0` là chữ **ư**. Dòng gây lỗi là `print(f"[desktop] {kh.ly_do}")`,
và ở lần mở đầu tiên `quyet_dinh()` trả về `ly_do = "chưa có backend nào
— tự chạy"`. Câu ấy có bốn ký tự ngoài cp1252: `ư` `—` `ự` `ạ`.

**Gốc rễ, nói cho đúng:** `print()` giao chuỗi cho **tầng văn bản** của
luồng, và codec của tầng đó do **locale của Windows** quyết định. Lỗi
không nằm ở tiếng Việt và không nằm ở console — lỗi là *để locale quyết
định codec* cho dữ liệu ta đã biết chắc là Unicode.

**Cách sửa:** `scripts/control_center/ghi_utf8.py`. Tự mã hoá sang UTF-8
rồi ghi **BYTE** vào tầng nhị phân của luồng. UTF-8 biểu diễn được mọi
điểm mã Unicode, nên phép mã hoá này **không thể thất bại** — không cần
`errors=` gì cả, và không mất một byte tiếng Việt nào. Cùng đối tượng đó
ghi thêm vào một tệp nhật ký mở với `encoding="utf-8"` tường minh, ở
`.router/control_center/desktop.log` — với bản `--noconsole` thì đó là
nơi DUY NHẤT đọc được chẩn đoán.

### Những cách KHÔNG dùng, và vì sao

| Cách | Vì sao không |
|---|---|
| `chcp 65001` | đổi console của người dùng, không sửa mã |
| đổi locale Windows | bắt người dùng đổi hệ thống vì lỗi của ta |
| đòi `PYTHONUTF8=1` | một biến bị quên là lỗi quay lại; bấm đôi trong Explorer thì không ai đặt |
| bọc bằng `.cmd` | EXE phải tự đúng; launcher chỉ là tiện nghi |
| `errors="replace"` / `"ignore"` | biến `ư` thành `?` hoặc mất hẳn — làm hỏng dữ liệu để giấu lỗi |
| bỏ dấu / phiên âm | văn bản tiếng Việt phải nguyên vẹn từng byte |

Bản trước **đã** dùng `sys.stdout.reconfigure(encoding="utf-8",
errors="replace")` và nó vừa lossy vừa **không đủ**: trong bản build
`--noconsole`, `sys.stdout` có thể là `None` hoặc không có
`.reconfigure`, nên phép gọi bị bỏ qua âm thầm rồi `print()` vẫn đi qua
codec của locale.

### Luật cho mọi tệp Router sở hữu

- `Path.read_text(encoding="utf-8")` / `write_text(..., encoding="utf-8")`
- `open(..., encoding="utf-8")` — hoặc chế độ **nhị phân**, không có codec
- `json.dumps(..., ensure_ascii=False)` cho mọi thứ người sẽ đọc
- `subprocess.run(..., text=True)` **phải** kèm `encoding=` — nếu đầu ra
  không ai đọc thì bỏ `text=True` và ở chế độ nhị phân

Cưỡng chế bằng `scripts/tests/test_control_center_utf8_locale.py`: nó
tính **bao đóng import** của `desktop.py` bằng AST rồi soi từng lời gọi
trên đó, nên thêm một import mới không làm phạm vi lặng lẽ hụt đi. Miễn
trừ phải ghi kèm lý do, và một miễn trừ **mồ côi** cũng làm bài kiểm đỏ.

### Vì sao 19/19 bài kiểm cũ vẫn xanh khi EXE đang chết

`control_center_desktop_acceptance.py` **tự tiêm `PYTHONUTF8=1` và
`PYTHONIOENCODING=utf-8`** vào tiến trình con — đúng hai thứ không được
phép dựa vào. Nó đo một môi trường không người dùng nào có: bấm đôi từ
Explorer thì không ai đặt biến nào cả.

Giờ bộ nghiệm thu **gỡ** các biến đó ra khỏi môi trường con, và có một
bài kiểm quét bằng AST để nó không thể quay lại. Bài kiểm cp1252 thì làm
điều ngược lại — nó **cưỡng chế** `PYTHONIOENCODING=cp1252:strict` cho
tiến trình con *để làm hẹp*, và tự xác minh rằng mình đã làm hẹp được
(mã cũ phải VẪN chết trong khung đó) trước khi tin bất kỳ kết quả nào.

Bài học chung, và nó lớn hơn Unicode: **một bài kiểm chạy trong môi
trường do chính nó dựng lên chỉ chứng minh được điều gì nếu môi trường ấy
là môi trường người dùng có.**

## 14b. Không cửa sổ console nào được nhấp lên (V0.4)

`Router Control Center.exe` build `--noconsole` nên tiến trình **không có
console**. Trên Windows, một tiến trình không có console mà sinh ra một
ứng dụng **console** (`git.exe`, `agy.exe`, `codex.exe`, `python.exe`,
`icacls.exe`) thì hệ điều hành **cấp cho nó một console mới** — kèm một
cửa sổ nhấp lên và **giành focus** của người đang gõ. Chạy từ mã nguồn
thì cửa sổ đó trùng console sẵn có nên không ai thấy: lại đúng một lớp
lỗi "chỉ lộ ra ở bản EXE", cùng họ với `sys.executable` (§ dispatch) và
cp1252 (§14).

Số lần nhấp tỉ lệ với số lệnh, và `AnhChupDuAn.chup()` chạy ~6 lệnh `git`
cho **mỗi** tin nhắn chat — một câu "ê" cũng đủ thấy.

**Luật:** mọi lời gọi `subprocess.run`/`Popen` trên đường của ứng dụng
phải mang `**an_cua_so()` (`scripts/router_v3/tien_trinh.py`):
`CREATE_NO_WINDOW` + `STARTUPINFO(SW_HIDE)` trên Windows, `{}` ở nơi
khác. Ngoại lệ duy nhất được phép là `AN_HIEN` — dành cho đường mà
**người dùng cố ý** muốn thấy cửa sổ.

Ẩn cửa sổ **không** đánh đổi bằng mất log: `capture_output=True` giữ
nguyên, đầu ra vẫn vào nhật ký app.

Phép cưỡng chế là một bài kiểm **AST trên cả bao đóng khởi động**
(`test_control_center_ux_v04.py`), không phải một lần rà tay: nó tính mọi
tệp `scripts/**` mà việc mở EXE có thể nạp tới và đòi từng chỗ sinh tiến
trình phải ẩn cửa sổ. Thêm adapter mới mà quên là đỏ, kèm số dòng.

## 14c. Cài đặt giao diện và ảnh nền (V0.4)

Bảng `cai_dat_ui` là khoá–giá trị, thuộc **người dùng trên máy này**,
không thuộc một dự án — đổi dự án không đổi ảnh nền. Lưu từng khoá riêng
(không phải một khối JSON) để hai lần ghi khác khoá không đè nhau: đổi độ
tối không được xoá mất ảnh nền. Bảng thêm bằng `CREATE TABLE IF NOT
EXISTS` nên sổ cũ tự có nó ở lần mở sau; không có bước di trú tay.

**`wallpaper` giữ MỘT MÃ ĐÍNH KÈM, không phải đường dẫn tệp.** Đây là bất
biến an toàn của tính năng: nhận đường dẫn thì để *vẽ* được ảnh phải mở
một endpoint đọc tệp tuỳ ý trên đĩa, tức là dựng lại đúng lỗ mà §12 tồn
tại để bịt. Đi qua đường đính kèm thì được thừa cả bốn bất biến ở §12 —
kể cả phép kiểm **chữ ký byte**: `anh.png` mà không mở đầu bằng
`\x89PNG` thì bị từ chối.

`POST /api/ui` chỉ nhận allowlist khoá, xác minh mã đính kèm tồn tại và
**là ảnh**, và kẹp `dim`/`blur` vào khoảng hợp lệ. Có bài kiểm đọc chính
mã endpoint và đòi nó không chứa `open(`/`read_bytes`/`read_text`/
`FileResponse`.

## 14d. Smart App Control và bản đóng gói (2026-09-10)

Máy phát triển bật Smart App Control cưỡng chế. Bản EXE PyInstaller **không
ký** chỉ mở được khi đám mây ISG trả "known good" cho **đúng băm** của tệp —
đạt thì Code Integrity ghi EA `$KERNEL.PURGE.ESBCACHE` lên tệp và không hỏi
lại; không đạt thì chặn (3033/3077, "we could not verify its publisher").
Mỗi lần dựng là một băm mới (mốc dựng trong đầu PE + overlay), nên với bản
không ký, "mở được" là kết quả xổ số, không phải thuộc tính của mã. Đo thật:
`dist-v0612` chạy, `dist-v061` dựng lại 50 phút sau từ cùng commit bị chặn.

Bốn luật:

1. **Sau khi dựng, đọc `KIEM_DONG_GOI.txt`** (`build_desktop_exe.py` tự gọi
   `scripts/kiem_ban_dong_goi.py`): SHA256, chữ ký/người ký, MOTW, dự đoán
   SAC. Không có báo cáo thì mọi so sánh "bản cũ chạy, bản mới không" là đoán.
2. **Không tự ký, không cài gốc tự ký, không tắt SAC, không sửa chính sách/
   registry, không tự ghi EA.** SAC chỉ tin CA trong Microsoft Trusted Root
   Program và không tra kho gốc cục bộ; ba việc sau là nới rào không hoàn tác.
3. **Đường dev chắc chắn không cần chứng chỉ**: `router-cc-desktop.cmd` —
   `pythonw.exe` của PSF (đã ký, đã tin) chạy `scripts.control_center.desktop`
   từ mã nguồn; mã Python không thuộc phạm vi kiểm của SAC ở cả hai cách đóng
   gói, nên không có gì bị nới.
4. **Phát hành thì ký bằng chứng chỉ của CA công cộng** qua
   `scripts/ky_ban_dong_goi.py --thumbprint <sha1>` (khoá trên token/HSM, kho
   chỉ biết vân tay) hoặc Artifact Signing nơi được hỗ trợ. Giữ nguyên các
   thư mục `dist-v*` đã chạy được — EA nằm trên tệp.

`docs/reports/SMART_APP_CONTROL_V061.md` có nhật ký sự kiện, bảng sáu bản,
thí nghiệm mở có kiểm soát, và đánh giá bốn phương án launcher.

## 14e. V0.6.1 — TRẠNG THÁI ĐÓNG BĂNG (canonical, 2026-09-10)

Nhân V0.6.1 được **đóng băng** ở đây. Mười năng lực dưới đây đã được nghiệm thu
trên ứng dụng THẬT (source-mode và/hoặc bản đóng gói), không phải chỉ bằng bài
kiểm đơn vị. Sau mốc này: sửa lỗi và tài liệu — **không thêm tính năng vào nhân
V0.6.1**.

| Năng lực | Trạng thái | Bằng chứng |
|---|---|---|
| Gốc dữ liệu bền theo NGƯỜI DÙNG, chính tắc | ĐÓNG BĂNG | `GOC_DU_LIEU_CHINH_TAC_V061.md`; 27 bài |
| Liên tục ký ức QUA CÁCH KHỞI CHẠY (source ⇄ đóng gói) | ĐÓNG BĂNG | nghiệm thu hai chiều 15/15 |
| Leader LÀM ĐẦU bằng ký ức | ĐÓNG BĂNG | `PROJECT_MEMORY_RECALL_V061.md`; 10/10 |
| Nhập lịch sử (backfill) có nguồn gốc | ĐÓNG BĂNG | 7.557 mục vào sổ live; 0 rò bí mật |
| WebReader (đọc web công khai, an toàn SSRF) | ĐÓNG BĂNG | `WEB_READER_V061.md`; 9/9 + 19 bài |
| Toả đa agent tường minh ("gọi N agent…") | ĐÓNG BĂNG | `MULTI_AGENT_FANOUT_V061.md`; 8 con thật |
| Đồng thời READ/READ thật (khoá có chế độ) | ĐÓNG BĂNG | `MULTI_AGENT_FANOUT_V061.md` §7; 4 con song song đo bằng mốc thời gian |
| Bể đa tài khoản Antigravity (AG01..AG08) | ĐÓNG BĂNG | `ANTIGRAVITY_POOL_AUDIT_V061.md` |
| Nền móng credential provider | ĐÓNG BĂNG | `PROVIDER_CREDENTIAL_ARCHITECTURE_V061.md` |
| Quan sát SỐNG dự án Fanfic | ĐÓNG BĂNG | probe SSH thật, `PROJECT_OBSERVABILITY_V05.md` |

**Bốn bất biến của nhân đã đóng băng** — phá một cái là phá nhân:

1. **Gốc dữ liệu KHÔNG suy từ vị trí mã.** `duong_du_lieu.py` là nơi duy nhất
   định nghĩa; `%LOCALAPPDATA%\RouterControlCenter`. Không `__file__`, không
   `cwd`, không `sys.executable`, không thư mục dist. Mọi điểm vào đi qua nó.
2. **Bậc thẩm quyền: SỐNG > SỔ/KHO > KÝ ỨC > SUY LUẬN.** Câu hỏi hiện tại phải
   đi đo; ký ức không bao giờ trả lời thay một phép đo sống.
3. **Không nới quyền cho agent.** `agy --print` tự chối mọi công cụ cần prompt
   (`command`, `read_file`, `read_url`) — kể cả khi LEADER gọi. Cách sửa duy
   nhất được phép: **Router tự làm phép đọc an toàn rồi đính BẰNG CHỨNG**
   (`nguon_git`, `web_reader`, ký ức). Không `--dangerously-skip-permissions`.
4. **Một người ghi trên một kho.** `KhoaKho` (khoá OS) + phiên bản KHO tách
   khỏi phiên bản ứng dụng; sổ mới hơn mã thì DỪNG, không hạ cấp âm thầm.

**Hồi quy đóng băng:** 931 bài xanh, 0 hỏng (95 bài Qt GUI BỎ QUA — python hệ
thống không có PySide6). Chạy theo TỆP RIÊNG cho các bộ chậm/đa luồng
(`slice`, `ui`, `utf8_locale`) — gộp hết vào một tiến trình từng làm treo và
từng cho hỏng GIẢ do định thời lượng.

**Giữ nguyên, không xoá:** `dist-v04/v05/v06` (+ `v0611/v0612/v0613`) và mọi sổ
`.router` cũ đã đánh mốc `DA_DI_TRU.json`. Việc dọn dẹp là quyết định của người
vận hành, không tự động.

## 15. Chưa làm (cố ý — ranh giới đã chọn)

Không phải thiếu sót — là ranh giới đã chọn:

- **Bộ phân rã mặc định chạy theo LUẬT**, không gọi model.
  `RouterPlanner` (nhờ một worker rẻ phân rã) đã có và đã kiểm, nhưng phải
  bật tường minh. Ô chat là cổng vào của mọi thứ khác; nếu nó chỉ hoạt động
  khi có mạng và còn quota thì cả Control Center cũng vậy.
- **Không tự xoá worktree.** Sẽ cần một lệnh dọn *do người bấm*.
- **Không tự gộp nhánh, không tự push, không deploy.**
- **`pause` một việc ĐANG chạy không cắt lượt đang bay.** `Executor.run`
  là đồng bộ; cách duy nhất cắt thật là giết tiến trình, và đó là `stop`.
  Nói rõ thay vì giả vờ đã dừng.
- **"Stream log" ở đây là stream SỰ KIỆN, không phải stream token.** Sự kiện
  (`SESSION_DECISION`, `WORKTREE_CREATED`, `TASK_STARTED`…) hiện ra ngay khi
  chúng xảy ra. Nhưng đầu ra THÔ của agent chỉ có sau khi lượt kết thúc:
  `agy` ở chế độ này trả một sự kiện `result` duy nhất, nên **không có gì
  để stream dần** — không phải Control Center bỏ qua, mà là nhà cung cấp
  không đưa ra. Nhật ký thô nằm sau `raw_log_ref` và mở được ở Chi tiết việc.
- **Việc mở lại một dự án KHÔNG tự chạy gì.** Vòng lặp điều phối chỉ nhận
  việc ở `QUEUED`/`WAITING`; `BLOCKED` (gồm mọi việc GATED) đứng yên cho tới
  khi có người duyệt.
- **Chưa có Browser Operator, chưa có app di động, chưa có cloud.**

## 16. Ký ức dự án vô hạn + ảo hoá ngữ cảnh (V0.6)

Một phiên LLM không còn là vòng đời của dự án. Lịch sử được giữ **trọn**,
chỉ-thêm, trên đĩa cục bộ; Leader nhận một **gói ngữ cảnh** có trần token
độc lập với kích thước lịch sử (đo: 20 k → 200 k sự kiện, gói 1 047 → 1 056
token). Đầy đủ ở `docs/reports/PROJECT_MEMORY_V06.md`; mã ở
`scripts/control_center/memory/`.

Bốn luật không được phá:

1. **Ký ức ở bậc 3, không bao giờ trả lời câu hỏi HIỆN TẠI khi có probe
   sống.** `leader.LUAT_KY_UC` đi kèm khối ký ức ở MỌI lượt có khối, đặt
   SAU ảnh chụp tĩnh; nhãn khối không bắt đầu bằng "TRẠNG THÁI"; một lần
   `LIVE_PROBE` được nhớ là "kết quả một lần đo sống (ĐÃ CŨ)". Bài kiểm so
   vị trí bằng `index()` và cấm cụm "LUẬT THẨM QUYỀN"/"tin được".
2. **L0 (`su_kien`) chỉ-thêm.** Không có đường sửa/xoá trong mã — bài kiểm
   quét `kho.py`. Không có endpoint xoá, không có nút "xoá lịch sử".
3. **Không bí mật vào sổ.** `bi_mat.loc()` ở cổng vào, phủ `packet.redact`
   và lọc cả khối PEM, AKIA, KEY=value…; thứ tự mẫu THÊM trước mẫu gốc.
   `da_loc=N` được ghi, nội dung thì không.
4. **Ký ức không được giết Router.** Provider không phương thức nào ném;
   sổ không mở được → `MEMORY_UNAVAILABLE`, chat/live vẫn chạy; người ghi
   hỏng → sổ chính vẫn ghi (`ControlStore._bao` nuốt).

Vị trí sổ: `<gốc>/.router/memory/<ns>/memory.db` — cạnh `control.db`,
mỗi dự án một tệp, **không** trong cây git của dự án được quản. FTS5
`unicode61 remove_diacritics 2` (bắt buộc ghi rõ — mặc định gấp dấu tiếng
Việt nửa vời), external content, dự phòng `LIKE` trên cột `chuan` (gấp
dấu + `đ→d`). Không vector, không trigram, không LLM trong đường chọn lọc.

## 17. Đề bạt ký ức, nhập lịch sử, provider ngoài + kho bí mật (V0.6.1)

Ba báo cáo: `docs/reports/PROJECT_MEMORY_V061.md`,
`docs/reports/PROVIDER_CREDENTIAL_ARCHITECTURE_V061.md`,
`docs/reports/ANTIGRAVITY_POOL_AUDIT_V061.md`. Mã:
`scripts/control_center/memory/{de_bat,nhap_khau}.py`,
`scripts/control_center/nguon_git.py` (`git log`/`git worktree list` chỉ-đọc —
đặt NGOÀI `memory/` vì gói đó không được có `subprocess`),
`scripts/control_center/providers/`.

Tám luật (5–12) thêm vào bốn luật của §16:

5. **Tuyên bố tường minh của người dùng thành bản ghi NGAY tại cổng vào, tất
   định, không LLM.** `de_bat.xet()` cần một dấu hiệu TUYÊN BỐ ("ghi nhớ…",
   "quyết định của project:", "từ giờ rule là"…); một câu chỉ có "không được"
   không phải quyết định. Bản ghi mang `authority = user_explicit`,
   `nguon_loai = chat_user`, bằng chứng trỏ về đúng dòng L0. Leader nhận
   "VỪA GHI TỰ ĐỘNG … `qd_xxxx`" và chỉ XÁC NHẬN, không ghi lại.
6. **Thay thế kiểu ADR, hai chiều, không xoá.** `thay_the_ky_uc` một giao dịch:
   bản cũ `thay_the` + `bi_thay_the`, bản mới `thay_the_cho`; cả hai truy được.
   Mã `qd_*` người dùng nêu được quy về ký ức đứng sau trước khi so khớp.
7. **Lịch sử nhập luôn `backfill`, không bao giờ `user_explicit`.** Vai "user"
   trong tệp phiên không chứng minh người gõ (tóm tắt nén, skill, nhắc hệ
   thống). Chỉ đề bạt trước mốc ký ức; phiên đang mở (mtime < 600 s) bị bỏ
   qua; chỉ phiên của các worktree của ĐÚNG kho (`git worktree list`);
   idempotent, chỉ đọc nguồn, resumable, thử khô.
8. **Giá trị credential chỉ đi qua `KhoBiMat`.** Sổ (`providers.db`) giữ
   `credential_ref`; mọi chuỗi giống khoá bị từ chối ghi. `BiMat` là tay cầm
   mờ (`dung(fn)`), không pickle/json/repr ra giá trị. Không kho an toàn →
   `luu()` NÉM, không rơi về tệp thường.
9. **Provider ngoài vào fabric ở trạng thái KHÔNG nhận dispatch.**
   `AUTO_ROUTING = False` là hằng trong mã; định tuyến thủ công = "Hỏi thử"
   do người bấm. Bật AUTO là bước tiếp theo, có adapter thực thi + ngân sách.
10. **Chỗ Leader chiếm trên AG01 HIỆN RA với bộ lập lịch.**
    `leader.chiem_cho_fabric` ghi nhãn `LEADER:<project>` vào `running_tasks`
    khi mở phiên, `tra_cho_fabric` ở `shutdown`; không đi qua `mark_finished`.
11. **Số agent người dùng xin là một trường riêng, đọc từ CÂU NGƯỒI DÙNG.**
    `toa.xet_toa(text)` (tất định) → 1 việc cha (vật chứa) + N việc con độc
    lập, mỗi con `AGENT i/N` với ràng buộc không trùng. Sức chứa đo từ fabric
    lúc tách (khe rảnh đã trừ `LEADER:`, tài khoản rảnh, trần song song) và
    câu trả lời nói đúng "K chạy ngay, N−K chờ" — không bao giờ cắt yêu cầu
    trong im lặng, không bao giờ nói "8" khi tạo 1. Con tránh runtime anh em
    đang chạy (`SessionManager.decide(tranh_runtime=)`), khe được đánh dấu
    NGAY lúc giao. Gộp kết quả khi mọi con xong: khử trùng, giữ nguồn gốc,
    MỘT tin tổng hợp. `che_do` (chất lượng) ≠ `so_agent` ≠ `max_parallel`
    (trần; `0` = tự theo bể). `docs/reports/MULTI_AGENT_FANOUT_V061.md`.
12. **Khoá tài nguyên có CHẾ ĐỘ; việc chỉ đọc không bao giờ đi đường GHI.**
    `ResourceLock.mode ∈ {read, write}` (`locks.py`): READ+READ sống chung (một
    hàng `…#r:<task>` mỗi người đọc), READ+WRITE và WRITE+WRITE giao nhau thì
    tranh chấp, không giao nhau thì song song. Chuỗi cũ `FILESYSTEM:x` không
    chế độ = WRITE — không nới gì cho dữ liệu cũ. Giao nhau tất định sau
    `chuan_hoa` (`docs/`, `docs/**`, `Docs\sub` → `docs`, `docs/sub`; `.`/`*` =
    gốc kho giao mọi đường dẫn; so theo ĐOẠN). `LockKind.GIT`: `history` (đọc)
    tách `worktree` (ghi); đọc lịch sử git không giữ khoá hệ tệp. Bộ phân rã
    xét Ý ĐỌC trước (`_Y_DOC` mà không `_Y_GHI` → `analysis/review`, không
    `repo_write`, không worktree, khoá READ); danh từ `tests`/`README` trần
    không còn là việc `testing`. Toả: tài nguyên theo TỪNG con từ mục của nó
    (`READ FILESYSTEM <đường>` · `READ FILESYSTEM .` · `READ GIT history` ·
    việc GHI `WRITE FILESYSTEM <đường>`), KHÔNG sao chép khoá mẫu cho mọi con;
    cha không xin khoá, `RUNNING` khi con đầu được nhận. Song song được ĐO bằng
    khoảng chạy thật (`khoang_chay` → `song_song_toi_da` quét mốc), không đếm
    trạng thái. Khoá được nhả NGAY khi việc ở trạng thái cuối (trước thử
    lại/báo chat/gộp cha), `finally` chỉ là lưới. Việc đọc lịch sử git nhận
    NHẬT KÝ GIT do Router đọc (`nguon_git.git_nhat_ky_doc`, lọc bí mật) — agent
    headless không chạy được lệnh shell và quyền của nó KHÔNG được nới.
    `MULTI_AGENT_FANOUT_V061.md` §7, `scripts/tests/test_khoa_doc_ghi_v061.py`.

## 18. Nhận dự án có sẵn + Viên nang dự án (V0.7 Phase 1)

Báo cáo: `docs/reports/NHAN_DU_AN_VIEN_NANG_V07.md`. Mã:
`scripts/control_center/nhan_du_an.py` (nhận, CHỈ ĐỌC),
`scripts/control_center/vien_nang_du_an.py` (19 mục + bản gọn có trần),
`scripts/control_center/kiem_lien_tuc.py` (13 hạng mục kiểm toán).

Năm luật (13–17) thêm vào §16–§17:

13. **NHẬN không được đụng vào kho.** `nhan_du_an()` chỉ đọc: không sao
    chép, không dời, không `git init` lại, không ghi tệp nào vào kho được
    nhận, không tạo sổ ký ức bên trong cây git của nó. Đo bằng
    `git status --porcelain` trước/sau và bằng ảnh chụp cây `.router`
    (127.279 mục, không đổi). Nhận lại là idempotent, không sinh dự án thứ
    hai.

14. **Danh tính suy từ GỐC WORKTREE + COMMIT GỐC, không từ nhánh.** Đổi
    nhánh không được đổi danh tính. Hai cái bẫy đã đo được: `git log
    --reverse -n1` trả về commit MỚI NHẤT (giới hạn áp trước khi đảo) —
    phải dùng `git rev-list --max-parents=0 HEAD`; và khoá chống trùng phải
    đặt trên gốc worktree chứ KHÔNG phải `--git-common-dir`, vì Fanfic và
    Router dùng chung một `.git`. URL remote bị lọc credential trước khi
    lưu.

15. **UNKNOWN là một giá trị hợp lệ; giá trị SỐNG không được đóng băng.**
    Mỗi mục mang `{gia_tri, trang_thai, nguon, bang_chung, ghi_chu, ts}`;
    ưu tiên nguồn `quyet_dinh > kho > ky_uc > tai_lieu > git > suy_luan`.
    Mục *Tham chiếu trạng thái SỐNG* chỉ ghi ĐO ĐƯỢC CÁI GÌ và BẰNG
    PROVIDER NÀO, không ghi phán quyết — "bây giờ còn chạy không" vẫn phải
    đi đo. Phiên bản viên nang chỉ tăng khi có mục ĐỔI THẬT, và bản cũ
    không bao giờ bị ghi đè.

16. **Bản gọn nạp cho Leader chọn mục THEO CÂU HỎI, không theo bảng ưu
    tiên cố định.** Đo được ở nghiệm thu: bảng cố định cắt mất đúng mục
    đang bị hỏi, và Leader lấp chỗ trống bằng cách BỊA (trả lời "5
    Antigravity account" trong khi sổ ghi 8). Đổi thứ tự cố định chỉ làm
    lỗi nhảy sang câu khác (mục `luu_tru`, câu R2/Drive) — đó là trò đuổi
    bắt, không phải cách sửa. `thu_tu_nap(cau_hoi)` giữ đầu bảng, xếp phần
    đuôi theo độ khớp từ khoá (không phụ thuộc dấu), và chen MỘT mục khớp
    mạnh nhất lên ngay sau danh tính để nó sống cả khi ngân sách chật.

17. **Dòng báo cắt phải NÊU TÊN mục chưa nạp, và được nhường chỗ TRƯỚC.**
    Dòng chỉ ĐẾM ("còn 10 mục nữa") không cho Leader phân biệt "dự án không
    có bằng chứng" với "có mà lượt này chưa nạp", nên nó đoán. Nêu tên biến
    câu bịa thành câu "mục X có trong viên nang nhưng chưa nạp ở lượt này".
    Dòng chân CŨNG tốn token: cộng sau khi đã đóng ngân sách thì trần thành
    lời nói dối (đo được 900 → 922), còn trừ-sau thì đuổi đúng mục liên
    quan nhất ra để lấy chỗ. Thứ được phép hy sinh là TÊN trong dòng cắt,
    không bao giờ là MỤC. Bộ đệm giữ `muc` chứ không giữ văn bản đã render —
    giữ văn bản thì lượt sau nhận bản cắt của câu hỏi trước.

## 19. Môi giới probe vận hành — đọc production, không có shell (V0.7)

Báo cáo: `docs/reports/PROBE_VAN_HANH_V07.md`. Mã:
`scripts/control_center/probe_van_hanh.py`, luật Leader ở
`leader.LUAT_VAN_HANH` + `leader.la_cau_hoi_van_hanh()`, đính bằng chứng ở
`engine._khoi_probe` / `engine._kem_probe_vao_hd`.

Bốn luật (18–21) thêm vào §16–§18:

18. **Câu hỏi VẬN HÀNH không được biến thành việc PHÂN TÍCH KHO.** Đo được
    (`fanfic.t2efd-1`, 2026-09-11): câu "vì sao Drive chưa có artifact mới"
    bị xếp `type=analysis` với danh sách lệnh chỉ có
    `cc_agent_tool.py changes|compile` — không lệnh nào chạm được tới
    production, nên worker gọi công cụ `command` chung và `agy --print` tự
    chối (`tool_permission_denied`), lượt kết thúc rỗng. Lời giải vẫn là lời
    giải cũ, lần thứ tư: **Router đo hộ rồi đính BẰNG CHỨNG**, không nới
    quyền agent, không bỏ qua kiểm quyền.

19. **Không có lối thoát ra shell, và có LƯỚI THỨ HAI.** `MoiGioiProbe.chay`
    nhận TÊN THAO TÁC + tham số, không bao giờ nhận chuỗi lệnh; chín thao
    tác `systemd.*`/`filesystem.*`/`rclone.*` đều CHỈ ĐỌC. Tham số kiểm theo
    CẤU HÌNH dự án: unit phải đã khai, đường dẫn phải nằm dưới gốc đã khai
    (so theo ĐOẠN — `/var/lib/x-evil` không lọt qua `/var/lib/x`), thuộc
    tính systemd theo bảng và bảng KHÔNG có `Environment*`. Ngoài ra
    `_kiem_chi_doc()` quét chuỗi lệnh cuối và từ chối mọi động từ đột biến +
    mọi ký tự nối/chuyển hướng. **Không nâng quyền** — trên farmer thật tài
    khoản quan sát CÓ quyền nâng không mật khẩu, và lớp này vẫn không dùng;
    chỗ sửa đúng nằm ở phía máy chủ và được BÁO CÁO chứ không tự làm.

20. **Thiếu bằng chứng thì phân loại là F, không phải một nguyên nhân nghe
    hợp lý.** `kiem_duong_ong()` chỉ khẳng định A–E khi có quan sát ĐO ĐƯỢC
    chống lưng; thiếu thì trả `F` KÈM danh sách đúng thứ còn thiếu. `grep`
    trả mã 1 là "không có dòng khớp" — một phép đo THẬT, không phải một lần
    đo hỏng, nên không được ghi thành `UNKNOWN`. Bộ lọc bí mật dùng
    `memory.bi_mat.loc` chứ không dùng `packet.redact`: bộ sau KHÔNG có khoá
    AWS `AKIA…`/`ASIA…`, đúng hình dạng dễ gặp nhất trong log EC2.

21. **Việc mang hình dạng bảo mật KHÔNG được xếp vào Codex.** Codex từ chối
    loại đó (bằng chứng 2026-08-28), `pool/adapters.py` chặn sẵn, nhưng
    `codex_security_shaped_refusal` lại nằm trong `KHONG_THU_LAI` — nên việc
    CHẾT ở `BLOCKED` dù thông báo hứa "định tuyến sang worker khác" (đo được:
    `fanfic.t78ce-1`). Nặng hơn: lời nhắc công cụ tiêu chuẩn của MỌI việc đều
    chứa chữ "quyền", nên gần như mọi việc xếp vào Codex đều chết như thế.
    Nay kiểm hình dạng TRƯỚC khi xếp chỗ và thêm runtime Codex vào
    `tranh_runtime` — tránh là ưu tiên, không phải rào.
