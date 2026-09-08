# Router Control Center V0.1

Phòng điều khiển cho Router V4 **đã có**. Mở một dự án, gõ mục tiêu vào ô
chat, và Router tự phân rã việc, chọn agent, dựng worktree, dựng/dùng lại
phiên, khoá tài nguyên, chạy, báo cáo — không phải mở tay một terminal
Claude/Codex/Antigravity nào.

> **Nó KHÔNG thiết kế lại Router V4.** Bốn thứ khó nhất — chấm điểm
> placement theo năng lực, cô lập worktree, cổng kiểm định "không tin worker
> tự khai PASS", phong bì kết quả — đã có, đã chạy thật, và được dùng
> NGUYÊN VẸN. Xem `docs/AI_ROUTER_V4.md` và
> `docs/reports/ROUTER_V4_REAL_PROOF.md`.

---

## 1. Chạy

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
| `--probe` | dò sức khoẻ provider lúc khởi động. **CHẬM và tốn một lượt mỗi provider** — mặc định TẮT |
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

## 11. Chưa làm (cố ý, V0.1)

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
