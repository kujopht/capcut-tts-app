# Việc thật HỎNG 3 lượt — gốc rễ, cách sửa, bằng chứng

Nghiệm thu tay 2026-09-09: người dùng gõ `ê` vào `Router Control Center.exe`.
Việc **HỎNG sau 3 lượt**. Đây là truy vết đầy đủ, đọc từ sổ và từ mã —
không đoán từ giao diện.

---

## 1. Việc đã hỏng, đọc từ sổ THẬT

Sổ: `dist/Router Control Center/.router/control_center/control.db`

| Hạng mục | Giá trị |
|---|---|
| Việc | `fanfic.t53fb-1` và `fanfic.tb324-1` (gửi hai lần) |
| Trạng thái | `FAILED`, `attempts=3` |
| Phiên | 6 phiên: AG01 → AG02 → AG03 cho MỖI việc |
| Nhà cung cấp | `antigravity`, model `gemini-3.8-flash-high` |
| `failure_reason` | `no_session` |
| `summary` | `chưa start_session` |
| Thời gian mỗi lượt | **~2 giây** |

Nhịp sự kiện của lượt 1 (từ `cc_events`):

```
+1155.94s TASK_CREATED     analysis: ê          (AUTO, scope [])
+1160.29s FABRIC_PROBED    10/11 runtime nhận dispatch
+1160.33s SESSION_DECISION CREATE AG01/gemini-3.8-flash-high (89.13đ / 50 ứng viên)
+1160.34s SESSION_CREATED  s-0d9b580a4d
+1160.35s TASK_STARTED     @900s trần
+1162.22s TASK_STATE       RUNNING -> FAILED (no_session)      <- 1.9 giây
+1162.22s TASK_STATE       FAILED -> QUEUED (thử lại lượt 2/3)
```

Bộ lập kế hoạch, bộ lập lịch, chấm điểm, dựng phiên: **tất cả đều đúng**.
Hỏng nằm ở bước gọi agent.

---

## 2. Gốc rễ: `sys.executable` trong bản ĐÃ ĐÓNG GÓI

`switch()` nạp credential bằng cách chạy launcher của người vận hành:

```python
subprocess.run([sys.executable, str(LAUNCHER), "switch", acc])
```

`sys.executable` là **"tệp thực thi đang chạy"**. Chạy từ mã nguồn thì đó
là `python.exe` và mọi thứ đúng. Trong bản PyInstaller nó là **chính
`Router Control Center.exe`**. Nên lệnh trên trở thành một lần **tự gọi lại
chính mình**:

```
$ "Router Control Center.exe" "…\agy_profile.py" switch acc1
Router Control Center: error: unrecognized arguments: …\agy_profile.py switch acc1
(mã thoát 2)
```

Đo được, không suy đoán. Chuỗi đầy đủ:

```
switch() -> False        (lý do "unrecognized arguments" bị VỨT ĐI)
start_session() -> False (giá trị trả về bị BỎ QUA ở executor.py:219)
send_task() thấy `_worker is None` -> "no_session"
-> thử lại AG02, AG03: hỏng y hệt, vì lỗi không phụ thuộc runtime
```

`agy` **không có lỗi gì**: gọi tay đúng cách nó trả `init` sau 8.66s, mã
thoát 0, stderr rỗng, model `gemini-3.8-flash-high` hợp lệ.

### Vì sao nó chỉ lộ ra ở bản đóng gói

Chạy từ mã nguồn thì `sys.executable` LÀ python — nên mọi bài kiểm, mọi
lần chạy `python -m`, mọi lượt CI đều xanh vĩnh viễn. Chỉ EXE mới sai.

---

## 3. BỐN khuyết tật, không phải một

Sửa mình cái (1) thì hôm nay xanh, nhưng lần sau vẫn mất một buổi để tìm.

| # | Khuyết tật | Sửa ở |
|---|---|---|
| 1 | `sys.executable` bị dùng như "một Python" | `router_v4/thong_dich.py` (mới) |
| 2 | `switch()`/`start()` bắt được lý do rồi VỨT đi | `antigravity_launcher.py`, `warm_pool.py` |
| 3 | executor BỎ QUA giá trị trả về của `start_session` | `executor.py` |
| 4 | lỗi CẤU HÌNH vẫn bị thử lại 3 lượt | `engine.py` |

**(1)** `thong_dich.argv_python()` tìm một thông dịch THẬT: chưa đóng gói
thì `sys.executable`; đã đóng gói thì `ROUTER_PYTHON` → `python` trên PATH
→ `py.exe` → cạnh EXE. Mỗi ứng viên đều được **thử chạy** (`--version`)
trước khi tin — `WindowsApps\python.exe` là một stub của Microsoft Store:
`which` thấy nó, chạy thì nó mở Store.

**(2)** `start()` của `WarmAgyWorker` có **bốn** nhánh hỏng và trước đây cả
bốn trả cùng một `False` trần. Giờ mỗi nhánh ghi `start_error` bằng tiếng
người, và nhánh "không phát `init`" phân biệt được hai tình huống khác hẳn
nhau: tiến trình **chết sớm** (kèm mã thoát + stderr) hay **còn sống mà
im** (đang treo ở một màn hình TƯƠNG TÁC).

**(3)** `executor.py` giờ kiểm giá trị trả về và dừng ngay với
`session_start_failed` + lý do thật, thay vì đi tiếp tới `send_task` để
nhận một triệu chứng.

**(4)** Thêm phép "hỏng Y HỆT ở chỗ khác thì thôi": so chữ ký hỏng
(`failure_reason` + 80 ký tự đầu của tóm tắt) giữa hai lượt. **Chỉ áp cho
`LY_DO_KHONG_PHU_THUOC_CHO`** — danh sách hẹp có chủ ý: hai tài khoản cùng
hết quota vẫn có thể còn tài khoản thứ ba, và chặn thử lại ở đó chính là
lỗi "báo FAILED trong khi một nhà cung cấp khoẻ khác đang làm được".

---

## 4. Bằng chứng điều phối THẬT — từ EXE ĐÃ ĐÓNG GÓI

Không CDP, không giả lập: mở EXE thật, đọc token từ tệp khoá của nó, gọi
API cục bộ của chính nó — đúng đường giao diện web đi.

| # | Việc | Kết quả | Lượt | Giây | Worker |
|---|---|---|---|---|---|
| A | liệt kê `docs/*.md` (chỉ đọc) | **DONE** | 1 | 28.9 | AG01 / gemini-3.8-flash-high |
| B | đọc `README.md`, mô tả nội dung | **DONE** | 1 | 16.7 | AG01 / gemini-3.8-flash-high |
| C | tạo `docs/c.md` (CÓ GHI, worktree) | **DONE** | 1 | 36.6 | AG01 / gemini-3.8-flash-medium |

Câu trả lời đúng sự thật: A → `a.md, b.md`; B → `'hat giong'`, 10 byte.

C được kiểm bằng **hiện vật trên đĩa**, không bằng lời khai:

```
.router/worktrees/AG01/proof.t7cee-1-7154f2/docs/c.md   "Ghi chu C" (10 byte)
gốc kho:  docs/ vẫn chỉ có a.md, b.md   <- cách ly worktree ĐÚNG
```

Không lượt nào cần người bấm gì. Không menu, không treo, không phiên mồ
côi, không khoá kẹt.

---

## 5. Một khuyết tật THỨ HAI mà bằng chứng C tìm ra

Lần chạy C đầu tiên **FAILED** — nhưng đúng **một** lượt, với lý do chính
xác thay vì `no_session` (rào (4) đã làm việc):

```
tool_permission_denied / gate_artifacts
stderr của agy: a tool required the "command" permission that headless
mode cannot prompt for, so it was auto-denied
```

Hợp đồng, worktree, phạm vi, và 5/6 cổng đều ĐÚNG; chỉ `artifacts` hỏng vì
tệp chưa được tạo. Worker chọn một **lệnh shell** trong khi `--mode
accept-edits` chỉ tự duyệt **sửa tệp**.

**Cách sửa, và nó KHÔNG nới rào nào:** nói thẳng cho worker biết nó đang
chạy không người trực. `TaskContract.render()` thêm một mục ngắn: dùng công
cụ đọc/ghi tệp, đừng dùng shell nếu còn cách khác, cần lệnh thật thì trả
`blocked` kèm `decision_request`.

Không đụng `permissions.allow`, không `--dangerously-skip-permissions`,
không sửa cấu hình toàn cục của người dùng. Chạy lại → **DONE**.

---

## 6. Codex và GPT-6 Astra — rò rỉ mặc định đã bịt

`CodexAdapter` chạy `codex exec --skip-git-repo-check -` — **không một cờ
`-m` nào**. Nghĩa là nó chạy **model mặc định của chính CLI**.

Đo 2026-09-09 (`codex doctor`, codex-cli 0.153.4): mặc định trên máy này là
`gpt-5.6-sol`. Nhưng **cùng bản CLI đó phơi ra `gpt-6-astra`**, và mặc định
đổi được ở phía nhà cung cấp sau một lần `codex update` — không ai bên này
sửa một dòng nào. Fabric còn có một model tên đúng nghĩa là
**`codex-default`**: một cái tên chỗ, không phải một model thật.

Hai rào ĐỘC LẬP:

1. **`CodexAdapter` FAIL CLOSED** khi chưa ghim model — `no_model_pinned`,
   không bao giờ rơi về mặc định. Rào này chặn cả model cao cấp **chưa ai
   kịp đặt tên**.
2. **`premium.py`** — bậc 3 chỉ vào được bằng lý do leo thang tường minh.

`fabric.json`: `codex-default` giờ ghim `provider_model: "gpt-5.6-sol"`.

### Astra: ĐÃ CHUẨN BỊ, CHƯA BẬT

`gpt-6-astra` có trong `fabric.json` với `premium_tier: 3`, và **cố ý
không** nằm trong `supported_models` của `CODEX01` — nên bộ lập lịch
**không thể** chọn nó. Bật = thêm nó vào danh sách đó; khi ấy `premium.py`
vẫn còn là rào cuối.

| Bậc | Dùng cho |
|---|---|
| T0 | tra cứu, tóm tắt, việc cơ học |
| T1 | code hằng ngày |
| T2 | agentic/suy luận mạnh |
| **T3** | **Astra — chỉ leo thang, không bao giờ mặc định** |

| Chế độ | Astra |
|---|---|
| ECO | cấm tuyệt đối |
| **AUTO** | **mặc định (gồm Fanfic)** — hiếm, chỉ leo thang |
| STRONG | leo thang với bằng chứng chặt hơn |
| MAX | được chọn ngay CHO MỘT VIỆC khi người yêu cầu tường minh |

Rào cứng: `max_parallel_astra_sessions = 1`; Astra **không** sinh ra Astra;
trần mỗi việc; **fail closed** khi cạn ngân sách (không âm thầm hạ cấp);
việc tầm thường (grep/docs/format/CRUD/test/deps/git/summary…) bị từ chối
**kể cả ở chế độ MAX**. Mỗi lần dùng ghi `task_id`, `provider`, `model`,
`reason`, `escalated_from`, `timestamp`, `turns`.

**Không bịa giá.** Chưa có nguồn usage/giá chính thức đọc được, nên `turns`
là `None` khi không đo được — không bao giờ là `0`.

**Số lần Astra được gọi đêm nay: 0.** Cả bốn lần chạy bằng chứng đều đi
Antigravity/AG01; chuỗi "astra" không xuất hiện trong bất kỳ sổ nào.

---

## 7. MCP tuỳ chọn

`.agy-sessions/accN/.gemini/config/mcp_config.json` **rỗng (0 byte)** trên
máy này — không MCP nào được cấu hình cho phiên Antigravity của Router, nên
`cloudflare-api` chưa xác thực **không** chạm tới đường này. Không cần tắt
gì, không cần đăng nhập gì.

---

## 8. Một thực thể: theo NƠI LÀM VIỆC, không theo cả máy

Mutex trước đây là `Global\…SingleInstance` — toàn máy. Hệ quả thực tế: gặp
ngay đêm nay, **không thể mở một bản thứ hai trên một thư mục tạm để KIỂM
trong khi bản của người dùng đang mở**, tức là không chứng minh được điều
phối trên chính bản đã đóng gói mà không phải tắt ứng dụng của người khác.

Thứ cần chặn là hai tiến trình giành MỘT sổ SQLite và MỘT tệp khoá — đó là
chuyện **theo thư mục gốc**. Giờ tên mutex kèm băm của đường dẫn gốc.

**Người dùng không thấy gì khác**: bấm đôi cùng một EXE luôn ra cùng một
thư mục gốc, nên lần bấm thứ hai vẫn nhường đúng như trước.

---

## 9. Bộ kiểm

| Bộ | Kết quả |
|---|---|
| `test_router_dispatch_frozen` (mới, 20 bài) | ĐẠT |
| `test_router_premium_astra` (mới, 23 bài) | ĐẠT |
| router v3 + v4 (10 bộ) | **260/260** |
| Điều phối THẬT từ EXE đóng gói | **3/3 DONE** |

---

## 10. Còn lại

- **Chế độ định tuyến chưa nối vào giao diện.** Bốn chế độ đã có ở
  `premium.py` với 23 bài kiểm, mặc định `AUTO`. Chưa có trường lưu theo
  dự án/việc — cần một lần đổi lược đồ sổ, và việc đó không nên làm vội.
- **Astra chưa từng chạy thật.** `capability_source` để `declared`, không
  được nâng lên `probed` nếu chưa có lượt chạy thật.
- **Chưa gắn thẻ v0.2.0.**
