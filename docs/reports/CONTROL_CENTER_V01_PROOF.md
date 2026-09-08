# Control Center V0.1 — bằng chứng lượt chạy (2026-09-08)

Chạy trên kho THẬT (`C:\FanficWorkers\router-control-center`), agent THẬT do
Router V4 gọi ra, không mock. Lệnh:

```bash
python scripts/control_center_real_proof.py --probe --write --timeout 900
```

---

## 1. Lát cắt dọc — từng bước, có bằng chứng

| Bước đề bài | Kết quả đo được |
|---|---|
| Project Chat | Một câu → 2 việc độc lập, có hợp đồng + phạm vi + phong bì quyền |
| → tạo việc | `QUEUED` ngay; việc GATED vào thẳng `BLOCKED` |
| → quyết định Router | `Scheduler.decide()` của V4 chọn theo NĂNG LỰC, có `explain()` |
| → worktree cô lập | `.router/worktrees/AG01/proof.<task>-<phiên>` + nhánh `router/AG01/…` |
| → dựng phiên agent | tiến trình `agy` thật, **PID ghi được** (13776, 20320, 24328…) |
| → stream trạng thái/log | `TASK_CREATED → SESSION_DECISION → WORKTREE_CREATED → TASK_CLAIMED → TASK_STARTED → TASK_FINISHED` |
| → ghi sổ việc + phiên | SQLite `.router/control_center/control.db` |
| → Pause/Stop | có, và `stop` ghi rõ **có cắt được tiến trình hay không** |
| → sống sót khởi động lại | `ControlCenter` mới đọc lại đủ dự án/việc/phiên/worktree/khoá/chat |

## 2. Số đo thật

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Việc CHỈ ĐỌC chạy bằng agent thật | hỏng: `worker không trả về khối JSON nào` | **DONE**, 46–95s, câu trả lời đúng về mã thật |
| Lý do một lượt rỗng | không đọc được (log 0 byte) | `tool_permission_denied` + nguyên văn stderr của `agy` |
| Ý định `deploy … production` | — | **BỊ CHẶN** ở `BLOCKED` trước khi tới worker |
| Tài khoản thật dùng song song | 1 (AG01) | **2** (AG01 + AG02) |
| Phiên nhận >1 việc (dùng lại) | 0 | **4 / 10** |
| Khoá còn giữ sau khi chạy | — | **0** (nhả hết trong `finally`) |
| Worktree bị xoá tự động | — | **0** (đúng luật: chỉ đánh dấu) |

Ví dụ câu trả lời thật của agent (việc chỉ đọc, `AG02/gemini-3.8-flash-high`):

> *"Cơ chế chọn provider của TTS ProviderRegistry
> (`desktop_app/providers/registry.py`) hoạt động theo nguyên tắc định tuyến
> đơn giản, tất định và gắn chặt theo thuộc tính `voice.provider`…"*

Đúng tệp, đúng cơ chế — không phải một lượt "chạy xong" rỗng nghĩa.

## 3. Bằng chứng DÙNG LẠI PHIÊN (yêu cầu lõi V0.1)

```
s-c90a46e6d9  AG02/gemini-3.8-flash-high    IDLE  pid=21708  việc=2
s-267039f7f0  AG02/gemini-3.8-flash-medium  IDLE  pid=23524  việc=2
s-d78dd4bd9b  AG01/gemini-3.8-flash-high    IDLE  pid=13776  việc=2
s-14b6a28574  AG02/gemini-3.8-flash-high    IDLE  pid=24328  việc=2
```

**Cùng một PID nhận hai việc** — tiến trình `agy` được giữ ấm, không dựng
lại. Đây là điều `RouterV4.run_task()` không làm được (nó chọn placement
mới cho mỗi việc), và là lý do Control Center gọi thẳng `Executor.run()`.

## 4. Lỗi THẬT do chính lượt chạy này phát hiện

| # | Lỗi | Sửa ở đâu |
|---|---|---|
| 1 | Việc bị ghi đè trạng thái về `QUEUED` ngay sau `claim` (đọc–sửa–ghi trên đối tượng cũ) | `engine.py` — đọc lại việc sau `claim` |
| 2 | Khoá đã hết hạn vẫn CHIẾM khoá chính ⇒ tài nguyên treo vĩnh viễn sau một lần tiến trình chết | `store.them_lock` — upsert nguyên tử có điều kiện hết hạn, đúng khuôn `LeaseStore` |
| 3 | Lượt `agy` rỗng không nói được lý do; stderr có câu trả lời nhưng bị vứt | cả hai transport Antigravity trả `tool_permission_denied` + stderr |
| 4 | Bộ lọc GATED khớp với **khuôn mẫu do chính Control Center sinh ra** ⇒ mọi việc phân tích vô hại đều bị chặn | chỉ quét văn bản NGƯỜI DÙNG |
| 5 | Việc `PAUSED` mà lượt đang bay chạy xong thì mất kết quả và bị đánh `FAILED` oan | mở `PAUSED → DONE/REVIEW/BLOCKED` |
| 6 | Cây bẩn KHÔNG BAO GIỜ được dùng lại ⇒ dùng lại worktree không bao giờ xảy ra | chỉ từ chối khi thay đổi nằm **ngoài phạm vi phiên** |
| 7 | `TaskDetail.task` / `.log` đụng thuộc tính chỉ đọc của Textual ⇒ sập khi mở modal | đổi tên `viec` / `nhat_ky` |
| 8 | Việc CHỈ ĐỌC hiện worktree nó không sở hữu (thừa hưởng từ phiên) | chỉ ghi worktree cho việc có ghi |
| 9 | Khai báo `write:` bị hiểu thành một dịch vụ khoá được | bỏ tiền tố khỏi bảng tài nguyên |
| 10 | Việc có ghi không được bảo phải khai `changes` ⇒ cổng `diff` đánh hỏng lượt làm đúng | hợp đồng nêu rõ, có ví dụ |
| 11 | **`pause` rồi `resume` chạy được một việc GATED mà KHÔNG ai duyệt** | xem §4a — sửa ở 3 chỗ, lưới cuối ở bộ lập lịch |
| 12 | `"and"` nối hai DANH TỪ bị cắt thành hai việc (`"investigate the auth"` + `"permission checks in …"`) ⇒ đốt một lượt agent cho một câu hỏi không tồn tại | vế phải phải mở đầu bằng ĐỘNG TỪ |
| 13 | Mất lease bị bỏ qua im lặng, phá đúng chế độ hỏng "hai chủ" mà lease tồn tại để chặn | sự kiện ALERT `LEASE_LOST` + ngừng đập nhịp |
| 14 | Một lượt hỏng = việc hỏng vĩnh viễn (không có đường thử lại nào) | thử lại có trần, đổi chỗ, 4 lý do không bao giờ thử lại |
| 15 | Ở tab Agent, phím vận hành tác động lên con trỏ bảng Việc — dừng nhầm việc, và `s` giết tiến trình thật | chọn theo tab đang mở |
| 16 | **Việc mồ côi kẹt `RUNNING` VĨNH VIỄN** khi phiên chủ còn sống nhưng đang rảnh — `recover()` bỏ qua, bộ lập lịch không nhặt (nó không ở QUEUED). Đo thật: kẹt qua BA lần `recover()` liên tiếp | đòi cả ba: phiên tồn tại + còn sống + `current_task == task_id` |
| 17 | Ví dụ đường dẫn trong hợp đồng sinh ra `docs/reports/note.md/vi-du.md` — một đường dẫn không tồn tại, đặt ngay trong câu đang dạy agent khai đường dẫn cho đúng | nhận biết phạm vi là tệp hay thư mục |
| 18–22 | **5 lỗi từ review đối kháng độc lập** — xem §4d. Nghiêm trọng nhất: khoá FILESYSTEM giao nhau theo tiền tố KHÔNG nguyên tử (`ON CONFLICT` chỉ che được trùng khoá chính) | `BEGIN IMMEDIATE` + 4 bản vá khác |

## 4a. LỖI NGHIÊM TRỌNG NHẤT, tìm bằng cách TỰ TẤN CÔNG bất biến

Sau khi bộ kiểm đã xanh, tôi viết một kịch bản cố **phá bất biến số 1**:
"việc GATED không bao giờ chạy nếu chưa có người duyệt". Nó phá được:

```
after chat      : BLOCKED | permission: GATED
after pause     : PAUSED          <- hợp lệ
after resume    : QUEUED          <- hợp lệ
tick dispatched : ['demo.t5ee9-1']
final state     : RUNNING | attempts: 1
GATE_APPROVED   : 0
>>> BYPASS: một việc GATED đã chạy với KHÔNG một lần duyệt nào.
```

Hai bước **đều hợp lệ** nối lại thành một đường vòng đầy đủ quanh cổng an
toàn quan trọng nhất của hệ thống. Một `deploy … production` sẽ chạy thật.

Đã sửa ở **ba** chỗ, và chỗ thứ hai mới là chỗ đáng kể:

1. `mo_khoa_gated` ghi **dấu duyệt lên chính việc** (`contract._permission.
   approved_by`), không chỉ vào nhật ký sự kiện. Một sự kiện là thứ *đọc lại
   được*; bộ lập lịch cần thứ *kiểm được*.
2. `_san_sang` — **lưới cuối**. Bất kỳ việc GATED nào lọt vào `QUEUED` mà
   chưa được duyệt đều bị đẩy lại `BLOCKED` kèm sự kiện `GATE_REASSERTED`
   mức ALERT. Sửa riêng `resume()` là bịt đúng một lỗ và để ngỏ mọi lỗ chưa
   nghĩ ra; kiểm ở **cổng vào của bộ lập lịch** thì mọi đường — hiện tại và
   về sau — đều phải đi qua đó.
3. `resume()` từ chối tường minh và chỉ người dùng sang phím `g`.

Sau khi sửa, cùng kịch bản đó: `>>> held: cổng sống sót qua đường
pause/resume.` 4 bài kiểm khoá lại cả đường tấn công lẫn đường hợp lệ.

**Bài học đáng giữ:** bộ kiểm xanh không có nghĩa là bất biến đúng. Bộ kiểm
chỉ kiểm những đường tôi đã nghĩ ra; tấn công bất biến tìm ra đường tôi chưa
nghĩ tới.

## 4b. Khép vòng REVIEW (thêm sau lượt chạy đầu)

Lượt chạy đầu để lộ một lỗ: hợp đồng rủi ro cao đòi review độc lập, việc vào
`REVIEW` — rồi **nằm đó mãi mãi**. Một trạng thái không ai đưa ra khỏi được
tệ hơn là không có trạng thái đó.

Nay Control Center tự đặt một việc review **là CON** của việc vừa xong, dùng
thẳng `hop_dong_review()` của Router V4 (loại họ model tác giả, không cấp
`repo_write`, trỏ reviewer vào worktree của cha). Review xong → cha `DONE`;
review **không chạy được** → cha `BLOCKED`, vì không kiểm chéo được thì không
được tuyên bố là xong.

Kèm một nới lỏng HẸP trong bộ chọn việc sẵn sàng: việc review phụ thuộc vào
cha, mà cha chỉ rời `REVIEW` sau khi review xong — đòi cha `DONE` trước thì
hai bên khoá nhau vĩnh viễn. Nới lỏng chỉ áp cho đúng `parent_id` của chính
việc đó; phụ thuộc thường vẫn phải `DONE` thật. 5 bài kiểm khoá lại.

## 4c. Review độc lập bằng agent THẬT — CHƯA chứng minh được

Vòng REVIEW được khoá bằng 5 bài kiểm (đặt việc con, loại họ model tác giả,
không cấp `repo_write`, khép cha `DONE`/`BLOCKED`, không đặt hai lần). Nhưng
chứng minh nó bằng **agent thật** thì **chưa đạt**, và lý do nằm ở B4:

Review độc lập chỉ kích hoạt cho việc **rủi ro cao CÓ GHI** — mà đúng loại
việc đó là loại đang bị bức tường quyền của `agy` headless chặn. Lượt thử
cuối chạy trên `AG03/claude-sonnet-4-6` (tài khoản thứ BA, họ model khác),
xác nhận `independent_review_required: True`, rồi việc cha hỏng ở tầng
worker trước khi kịp vào `REVIEW`.

Nói rõ ra thay vì để bảng bài kiểm xanh ngụ ý nhiều hơn sự thật: **vòng
REVIEW đúng theo bài kiểm, chưa đúng theo bằng chứng chạy thật.**

Một điểm phụ đáng giữ: lượt đó cho thấy **AG01, AG02 và AG03 đều dùng được**,
trên cả Gemini lẫn Claude. Câu "chỉ AG01 là thật" trong
`docs/AI_ROUTER_V4.md` §2.1 (ghi 2026-09-03) nay đã **cũ**.

## 4d. Review đối kháng độc lập — 5 phát hiện, CẢ NĂM đều thật

`ai_router_dispatch.py --task-class SECURITY_REVIEW --risk HIGH` →
`claude-opus-4-6-thinking` qua Antigravity **hỏng sau 9.4s** với đúng bức
tường quyền của B4. Một `code-reviewer` (Claude, chỉ đọc) thì **trả về sau
~4 giờ** với 5 phát hiện — tôi đã sớm kết luận nhầm rằng nó treo.

| # | Phát hiện | Trạng thái |
|---|---|---|
| 1 | Khoá FILESYSTEM giao nhau theo tiền tố **không nguyên tử** | THẬT — dựng lại 3/3 lần |
| 2 | Luồng nhịp tim chết vĩnh viễn sau MỘT ngoại lệ (`return` thay vì `continue`) | THẬT |
| 3 | `_giao()` không có `finally` ⇒ khoá PRODUCTION rò = treo vĩnh viễn | THẬT |
| 4 | `reassign()` dùng `force=True` ⇒ `DONE` hết là ngõ cụt, ghi đè mất kết quả | THẬT |
| 5 | Đọc–sửa–ghi trên `tasks` nuốt mất một lệnh `pause` | THẬT |

**#1 là lỗi nghiêm trọng nhất của cả đêm**, và nó đáng nói vì sao nó sống sót
lâu đến thế: `INSERT ... ON CONFLICT(lock_id)` chỉ nguyên tử khi hai bên tranh
**đúng một khoá chính**. Luật xung đột của khoá FILESYSTEM là *giao nhau tiền
tố*, nên `web/admin` và `web/admin/content-queue` — hai tài nguyên đụng nhau
thật — sinh ra **hai** `lock_id` khác nhau. Không có xung đột PK nào để bắt.

Bài kiểm đồng thời tôi tự viết **không bắt được**, vì nó cho hai luồng tranh
*cùng một* tài nguyên — đúng trường hợp duy nhất mà khoá chính che được. Bài
kiểm xanh, bất biến hỏng, và tôi đã đọc lại đoạn mã đó nhiều lần trong đêm.

Đã sửa cả 5, mỗi lỗi kèm một bài kiểm khoá lại (6 bài mới).

**Bài học đáng giữ hơn cả bản vá:** vòng tự tấn công của tôi tìm ra #11 và #16;
một cặp mắt độc lập tìm ra 5 lỗi khác mà tôi nhìn thẳng vào vẫn không thấy.
Hai thứ đó không thay thế nhau.

## 4e. Review đối kháng TRƯỚC PHÁT HÀNH — 6 phát hiện, 2 trong đó CHẶN TAG

Lượt review cuối trước khi tag. Sáu phát hiện, cả sáu đều thật, và người
review nói thẳng: **"chưa nên tag khi #1/#2 còn"**.

| # | Phát hiện | Mức |
|---|---|---|
| 1 | Động từ `tests` = **thực thi mã tuỳ ý** qua một allow-rule hẹp | NGHIÊM TRỌNG |
| 2 | `recover()` của tiến trình thứ hai **cướp** việc đang chạy của tiến trình thứ nhất | NGHIÊM TRỌNG |
| 3 | `_doi_soat_khai_thieu` là **mã chết** — và bài kiểm của tôi dùng hình dạng bất khả | QUAN TRỌNG |
| 4 | Cả ba động từ bị từ chối **100%** trên đúng dự án MẶC ĐỊNH | QUAN TRỌNG |
| 5 | `xoa_project` không từ chối việc đang RUNNING ⇒ nhả khoá PRODUCTION giữa lúc ghi | QUAN TRỌNG |
| 6 | Sự kiện `TASK_CLAIMED` thiếu `project_id` ⇒ gỡ dự án để lại rác | NHỎ |

**#1 đáng kể chi tiết, vì nó là đúng thứ cả mục 4b dựng lên để chặn.**
Worktree của việc là nơi agent **được phép ghi**, còn
`unittest discover -s scripts/tests` **nạp rồi chạy** mọi `test_*.py` ở đó.
Agent không cần thoát rào `cwd` — nó chỉ cần trồng `scripts/tests/test_x.py`
vào cây của chính nó rồi gọi đúng chuỗi lệnh đã được duyệt. Các cổng
`scope`/`diff`/`security` chạy **sau lượt**, nên thấy tệp lạ khi mã đã chạy
xong. Động từ bị **rút khỏi allowlist**; nó ở lại trong wrapper cho Control
Center (đã tin cậy) tự gọi.

**#2 là một lỗi hai-tiến-trình mà một tiến trình không thể thấy.** Trong lượt
đầu của một việc, `pid` của phiên còn NULL, nên đối soát phục hồi của một
tiến trình thứ hai không phân biệt được "phiên chết" với "phiên vừa sinh ra
và đang chạy". Nó đưa việc đang chạy về hàng đợi. Đã đổi sang dùng **lease
V4 còn sống** làm dấu hiệu liên tiến trình.

**#3 là lần thứ hai tôi mắc đúng một loại lỗi trong cùng bản phát hành:**
viết bài kiểm cho một **hình dạng dữ liệu không tồn tại**. `Executor.run` ghi
đè `pb.status` thành `"failed"`, nên nhánh đối soát không bao giờ chạy trên
đường thật; bài kiểm của tôi xanh vì nó tự dựng một envelope mà sản phẩm
không bao giờ sinh ra. Đã đổi sang phát hiện qua chuỗi chi tiết của cổng
`diff`, với một bài kiểm **khoá đúng chuỗi đó**.

**#4 là lỗi mà mọi bài kiểm đều xanh trong khi sản phẩm hỏng từ đầu tới
cuối.** `REPO_ROOT` suy ra từ vị trí tệp wrapper, tức kho control-center;
nhưng dự án `fanfic` trỏ tới **kho chính**, nên worktree của nó nằm ở
`<kho chính>/.router/worktrees/`. Rào `cwd` chỉ nhận cây dưới `REPO_ROOT` ⇒
từ chối 100%. Nới rào thành "có `.router` rồi `worktrees` kề nhau trong tổ
tiên đã resolve".

Việc nới đó **chỉ an toàn vì #1 đã được sửa** — không động từ nào được cấp
còn nạp mã theo `cwd`. Ràng buộc đó trước giờ không được khoá ở đâu cả, nên
đã thêm một bài kiểm dựng cây giả ở **chỗ khác trên đĩa**, xác minh rào thật
sự cho qua, rồi đòi không động từ được cấp nào chạy tệp trong đó.

**Bài kiểm đó, lần đầu viết, là một bài kiểm rỗng.** Kiểm bằng mutation (cấp
lại `tests`) vẫn xanh: từ Python 3.11 `unittest discover` chỉ nạp thư mục
**import được**, và cây giả thiếu `__init__.py` nên không tìm thấy gì. Cây
thật của agent là một bản checkout của kho nên **có sẵn** hai tệp đó. Thêm
vào cây giả thì mutation làm bài kiểm hỏng đúng như mong đợi.

Ba lần trong một bản phát hành — #3 ở trên, và hai lần ở đây — cùng một loại
lỗi: **bài kiểm xanh vì nó mô phỏng một thế giới không tồn tại.** Cách duy
nhất tôi bắt được nó là chạy mutation, không phải đọc lại.

**Một chỗ nữa lệch khỏi đường thật, tìm được lúc chạy lại bằng chứng:** prompt
của `control_center_allowlist_proof.py` không nhắc agent ĐỪNG mở tệp công cụ
ra đọc, trong khi hợp đồng thật (`planner.py:554`) có nhắc. Thiếu dòng đó,
bài chứng minh **hỏng ngẫu nhiên theo tính ý của model** — cùng mã nguồn, một
lần `compile` bị từ chối vì agent tự ý mở tệp công cụ, lần sau thì không. Đã
đồng bộ prompt với hợp đồng.

**Phát hiện thứ bảy, và là phát hiện nặng nhất của lượt này** — tìm được vì
tôi chạy lại bằng chứng bằng **đúng cờ mặc định** thay vì cờ mà các lượt
trước dùng:

`probe=False` là mặc định có chủ đích ("dựng Control Center không gọi
mạng"). Nhưng `dung_fabric` đặt mọi runtime ở `OFFLINE`, và
`Scheduler.decide` loại sạch **cả 42 ứng viên** với lý do *"runtime KHÔNG
nhận dispatch"*. Ghép lại: `router-cc` — đúng lệnh trong tài liệu và trong
launcher — **không bao giờ giao được việc nào.** Mọi việc nằm `WAITING`
vĩnh viễn.

```
probe=False -> selected=None   "runtime KHÔNG nhận dispatch x1; ..."
probe=True  -> AG01/gemini-3.8-flash-high   (89.13 điểm, 42 ứng viên)
```

Mọi lượt chứng minh trước đây đều chạy **có** `--probe`, nên đường mặc định
của bản phát hành chưa từng được chứng minh. Bài học: *chạy bằng chứng bằng
đúng cờ người dùng sẽ dùng, không phải cờ làm nó chạy được.*

Và một lần nữa, cùng loại lỗi bài kiểm: `fabric_gia()` dựng runtime ở
`RuntimeStatus.IDLE` — mô phỏng một fabric **đã được dò**. Không bài kiểm
nào đi qua trạng thái mà sản phẩm thật khởi động từ. Đã sửa bằng dò **lười**
(dò khi thật sự có việc chờ, hạn 300s, không dò fabric dựng tay, dò hỏng thì
fail closed) và 6 bài kiểm mới — trong đó có một bài **canh chính cái stub**,
vì `_dam_bao_suc_khoe` bắt mọi ngoại lệ nên một stub viết sai hỏng âm thầm
và bài kiểm vẫn xanh vì sai lý do. Đúng cái bẫy đó đã sập một lần khi tôi
viết `for r in f.runtimes` (`runtimes` là **dict**).

## 4f. V0.1.1 — giao diện đồ hoạ, và bảy lỗi của lượt review đối kháng

Bản V0.1.1 không đổi một dòng backend nào. Nó thêm một GUI Qt và giữ TUI
làm đường dự phòng. Nhưng lượt review đối kháng cho một bài học rõ hơn cả
bản vá:

> **Bốn lỗi clipboard, và không lỗi nào nằm trong mã clipboard.**

Cả bốn do *nhịp làm mới giao diện* phá: `_Inspector.cap_nhat`,
`_PanelChiTietViec.dat` và `KhungNhatKy._ve_lai` gọi `setPlainText()` vô
điều kiện mỗi giây. Người dùng bôi đen rồi mới với tay bấm Ctrl+C — quá 1
giây là chuyện thường — nên clipboard ra rỗng. Đo được **217 ký tự đang
chọn → 0 sau đúng một nhịp**.

Tệ nhất là ở nhật ký: mất vùng chọn khiến nút **Copy** rơi về nhánh "copy
tất cả" và dán ra **cả** nhật ký thay vì 3 dòng người dùng đã chọn. Sai âm
thầm, không báo gì.

| # | Phát hiện | Mức |
|---|---|---|
| 1 | vùng đang bôi đen bị xoá mỗi giây ở Inspector + panel chi tiết | NGHIÊM TRỌNG |
| 2 | nhật ký của việc ĐANG chạy: cùng lỗi, và nút Copy dán sai | NGHIÊM TRỌNG |
| 3 | `_copy_bang` bỏ trắng cột dùng cell widget (Trạng thái, Usage) | QUAN TRỌNG |
| 4 | tài liệu nói sai: Qt6 KHÔNG copy cả hàng bằng Ctrl+C | QUAN TRỌNG |
| 5 | đổi trạng thái một việc dựng lại CẢ danh sách tin chat | QUAN TRỌNG |
| 6 | mã dự án đúc từ tên thư mục + UPSERT ⇒ đè dự án thật | QUAN TRỌNG |
| 7 | ô tìm ở thanh trên nối vào `lambda _: None` — điều khiển chết | NHỎ |

### Và CỔNG NGHIỆM THU của chính bản này là một bài kiểm rỗng

Đây là phát hiện đáng giá nhất của lượt review, nên nói đủ.

`test_khong_QShortcut_nao_chiem_to_hop_clipboard` lọc
`sc.context() == Qt.ApplicationShortcut`. Nhưng phạm vi **mặc định** của
`QShortcut`/`QAction` là `WindowShortcut` — đã đo trên PySide6 6.11.2. Nên
bộ lọc đó bỏ qua gần như **mọi cách người ta thật sự thêm một lối tắt**.

Mutation: thêm `QShortcut(QKeySequence("Ctrl+C"), self)` vào cửa sổ.

| Ô đang focus | Ctrl+C sau mutation |
|---|---|
| ô soạn (editable) | vẫn copy đúng — Qt gửi `ShortcutOverride` cho widget editable |
| thẻ chat, nhật ký, panel chi tiết, Inspector, bảng Tasks | **bị ăn mất** |

Tức là bài kiểm được quảng cáo "khoá cả sản phẩm" chỉ bảo vệ đúng cái ô mà
Qt đã tự bảo vệ, và bỏ ngỏ **cả năm** vùng chỉ-đọc.

Đã bỏ bộ lọc, và thêm một bài **bơm Ctrl+C bằng sự kiện thật** vào từng
vùng. Bài bơm phím đó, **lần đầu viết, cũng rỗng**: thiếu
`activateWindow()` + `processEvents()` thì máy lối tắt chưa vào cuộc và
`QTest.keyClick` giao thẳng sự kiện cho widget. Phải mutation lại lần nữa
mới thấy. Ba bài kiểm rỗng khác cùng lượt: nút Copy/Copy All được gọi bằng
hàm chứ không bấm, `cs.isVisible() or True`, và hợp đồng dữ liệu kiểm trên
**văn bản mã nguồn** của `snapshot()`.

**Bài học, và nó lặp lại lần thứ tư trong hai bản phát hành:** một bài kiểm
chỉ có giá trị khi đã thấy nó HỎNG đúng lúc cần hỏng. Đọc lại không bao giờ
đủ; mutation thì đủ.

### Chứng minh sống 10/10 tiêu chí

`scripts/control_center_gui_proof.py --that` — `ControlCenter` THẬT, cửa sổ
Qt THẬT (offscreen), bấm đúng những nút người dùng bấm, một lượt agent thật:

```
1. cửa sổ mở được                     ĐẠT
2. mở được dự án Fanfic               ĐẠT
3. gõ việc trong Chat rồi bấm Gửi     ĐẠT   1 việc được tạo
4. Router tạo & quản lý việc          ĐẠT   bảng Tasks có 1 hàng
5. agent/phiên/worktree cập nhật sống ĐẠT   phiên hiện ở Agents, worktree gán
6. xem chi tiết + nhật ký bằng chuột  ĐẠT
7. Copy nhật ký ra clipboard          ĐẠT   323 ký tự
8. Pause/Resume bằng nút              ĐẠT
9. hộp thoại đóng bằng X và Esc       ĐẠT
10. khởi động lại, trạng thái còn     ĐẠT   1 việc + 2 tin chat từ SQLite
```

Lượt agent thật đó kết thúc ở `FAILED` (công việc của agent không qua cổng
kiểm định). Tiêu chí 5 đo **giao diện có phản ánh trạng thái sống hay
không**, và nó phản ánh đúng — nên ĐẠT. Nói rõ để không ai đọc bảng này
tưởng lượt đó thành công.

Một chi tiết nữa đáng ghi: lần chạy đầu, tiêu chí 5 báo HỎNG với
`trạng thái cuối=QUEUED`. Đó là lỗi của **kịch bản chứng minh** — nó quên
gọi `bat_dau()` nên vòng điều phối không hề chạy. *Một bài chứng minh thiếu
một cú gọi khởi động sẽ tố cáo sản phẩm thay vì tố cáo chính nó.*


## 4g. V0.2 — giao diện WEB cục bộ là đường chính, và đính kèm hạng nhất

Hai thứ được thêm, backend điều phối không đổi một dòng.

### Đính kèm: bốn bất biến, và một lời hứa

37 bài kiểm ở `scripts/tests` (CI cưỡng chế, vì tầng này không cần Qt).
Bài đáng nói nhất là bài của bất biến #3: **mô hình đối thủ là kẻ tấn công
GHI ĐƯỢC vào sổ.** Nên bài kiểm sửa tay `rel_path` thành
`../../../Windows/System32/config/SAM` rồi đòi `duong_dan()` TỪ CHỐI. Một
phép kiểm bằng chuỗi sẽ lọt bài này; phép kiểm đúng là so sánh sau
`resolve()`.

Lời hứa "không tải tệp lên đâu cả" được kiểm trên **cây cú pháp** — đòi
tầng đính kèm không import `requests`/`urllib`/`socket`/`boto3`/… Grep văn
bản sẽ báo động vì chính docstring nói về việc không tải lên; cùng cái bẫy
đã gặp ở `cc_agent_tool`.

Và một bài kiểm **đếm số lần gọi `read`**: dòng chảy 1 MiB phải là dòng
chảy thật, nên nếu một ngày ai đổi sang `f.read()` thì bài kiểm hỏng — chứ
không phải chờ tới lúc ai đó kéo một tệp 2 GB vào.

### API cục bộ: localhost KHÔNG phải là riêng tư

Đây là phần tôi dành nhiều công nhất, vì nó là rủi ro mà bản Qt không có.
Ba lớp, 37 bài kiểm:

| Đe doạ | Chặn bằng |
|---|---|
| mọi trang web đang mở đều GỬI được request tới `127.0.0.1` (trình duyệt chỉ ngăn *đọc* phản hồi) | token mọi request, **kể cả `GET`**; `hmac.compare_digest` |
| DNS rebinding đi vòng qua phép kiểm origin | allowlist `Host`, kiểm **TRƯỚC** token |
| CORS mở đường đọc cho origin khác | không CORS; bài kiểm đòi `CORSMiddleware` không được import |
| lộ ra mạng LAN | bind `127.0.0.1`; bài kiểm đọc AST đã bỏ docstring |

Thứ tự "Host trước token" không phải chi tiết: chính việc token *có thể*
đúng là điều đang được phòng.

### Ba lỗi tìm được bằng cách CHẠY THẬT, không bằng bài kiểm

1. **`webmain.py` bỏ qua `khoi_tao()`** nên mở giao diện web trên một máy
   mới ra một **sidebar rỗng** — không dự án nào. Hai launcher kia (TUI,
   Qt) đều gọi nó. Phát hiện bằng cách chụp DOM thật bằng Chrome cục bộ.
2. **Với `--khong-mo`, token không được in ở đâu cả** — tức là KHÔNG CÓ
   CÁCH NÀO mở được giao diện. Và nếu đóng tab thì mất đường vào cho tới
   khi khởi động lại server.
3. **MCP Chrome không dùng được cho việc kiểm này.** Nó tải được
   `https://example.com` nhưng KHÔNG tới được `127.0.0.1:8791` trong khi
   Python trên máy này tới được — tức trình duyệt đó không ở cùng máy. Đã
   đổi sang Chrome cục bộ qua DevTools Protocol, và nói rõ điều đó thay vì
   báo "đã kiểm bằng trình duyệt".

### Bằng chứng sống

```
scripts/tests/test_control_center_attachments.py   37 bài  (CI)
scripts/tests/test_control_center_webapi.py        37 bài  (CI)
tests/test_control_center_gui_attachments.py       20 bài
smoke HTTP thật trên một cổng thật                 13/13
smoke Chrome CỤC BỘ qua CDP                        18/18
```

Smoke CDP bắn đúng những sự kiện trình duyệt bắn khi người dùng dán/thả —
`ClipboardEvent('paste')` và `DragEvent('drop')` với `DataTransfer` mang
`File` thật — rồi đối chiếu `sha256` với server. Nó chứng minh: dán văn bản
thuần KHÔNG bị handler chặn, dán ảnh ra thumbnail thật, kéo-thả PDF + tệp
mã nguồn, bỏ một đính kèm trước khi gửi (server bỏ theo), agent được cấp
đúng đính kèm của tin đó, việc không liên quan thấy 0, hộp thoại đóng bằng
`×` **và** `Esc`, và không lỗi JS nào.

**GIỚI HẠN, nói thẳng:** kịch bản KHÔNG tự bấm được `Win+Shift+S` hay
`Ctrl+V` của hệ điều hành. Nó chứng minh *mã của ta* xử lý đúng sự kiện mà
trình duyệt giao cho — không phải chuỗi phím Windows. Bước đó cần một cú
bấm của con người.


## 5. Còn chặn (cần người) — xem `ROUTER_CONTROL_CENTER_OVERNIGHT_BLOCKERS.md`

- **B4 ĐÃ ĐÓNG.** Hai mục `command(...)` khớp chuỗi chính xác, trỏ tuyệt đối
  tới wrapper hữu hạn động từ. Không `command(*)`, không
  `--dangerously-skip-permissions`. Xem `docs/CONTROL_CENTER.md` §4b.
- **B5 ĐÃ ĐÓNG, và VẪN FAIL CLOSED** — không hạ xuống mức cảnh báo. Khi
  agent khai thiếu: ghi sự kiện `UNDERDECLARED_CHANGES`, suy ra tập tệp
  thật từ `git`, **chạy lại** cổng `scope`/`diff`/`security` trên tập THẬT,
  và chỉ cho hoàn thành nếu mọi thay đổi thật đều hợp lệ và trong phạm vi.
- **B1** Hồ sơ router toàn cục `CLAUDE_CONSERVATION` đã quá hạn 11 ngày.
- **B2** AG03–AG08 chưa cấp phát (cần đăng nhập Google từng hồ sơ Windows).

## 6. Bài kiểm

```
scripts/tests/test_control_center_core.py      80 bài — sổ, khoá, quyền, phân rã, rào tĩnh
scripts/tests/test_control_center_slice.py     82 bài — lát cắt dọc, kho git thật, 2 tiến trình
scripts/tests/test_control_center_ui.py        13 bài — 7 màn hình, Textual headless
scripts/tests/test_control_center_allowlist.py 24 bài — allowlist, rào cwd, gỡ dự án, đóng gói
                                              ─────
toàn bộ scripts/tests                        1155 bài — OK (1 skipped)
tests/ (desktop, kiểm hồi quy)                 397 bài — OK
```

`skipped=1` là `test_router_v3_opencode_adapter`: bài đó chỉ nói về đường
HỎNG nên nó tự bỏ qua khi trên máy CÓ server thật. Không liên quan tới
Control Center, và đã `skipped=1` từ trước lượt này.

Thay đổi duy nhất chạm Router V4 là **một tham số tuỳ chọn**
(`Executor(worktree_provider=...)`), mặc định `None` = hành vi cũ nguyên vẹn.
177 bài kiểm V3/V4 vẫn xanh.
