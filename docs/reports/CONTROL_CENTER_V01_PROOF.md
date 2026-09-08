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

## 5. Còn chặn (cần người) — xem `ROUTER_CONTROL_CENTER_OVERNIGHT_BLOCKERS.md`

- **B4** `agy` headless tự chối quyền `command`/`read_file` ⇒ việc CÓ GHI
  chưa chạy hết được. Hai đường sửa đều là quyết định của bạn; đường
  `--dangerously-skip-permissions` **bị cấm** và không được dùng.
- **B5** Cổng `diff` của V4 đánh hỏng một lượt làm đúng khi worker khai
  thiếu. Đã sửa ở tầng hợp đồng; có nên hạ cổng xuống mức cảnh báo là quyết
  định của bạn.
- **B1** Hồ sơ router toàn cục `CLAUDE_CONSERVATION` đã quá hạn 11 ngày.
- **B2** AG03–AG08 chưa cấp phát (cần đăng nhập Google từng hồ sơ Windows).

## 6. Bài kiểm

```
scripts/tests/test_control_center_core.py    81 bài — sổ, khoá, quyền, phân rã, rào tĩnh
scripts/tests/test_control_center_slice.py   61 bài — lát cắt dọc, kho git thật, 2 tiến trình
scripts/tests/test_control_center_ui.py      13 bài — 7 màn hình, Textual headless
                                            ─────
toàn bộ scripts/tests                      1100 bài — OK (1 skipped)
tests/ (desktop, kiểm hồi quy)               397 bài — OK
```

Thay đổi duy nhất chạm Router V4 là **một tham số tuỳ chọn**
(`Executor(worktree_provider=...)`), mặc định `None` = hành vi cũ nguyên vẹn.
177 bài kiểm V3/V4 vẫn xanh.
