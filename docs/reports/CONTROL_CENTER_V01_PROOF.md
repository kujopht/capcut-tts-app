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
scripts/tests/test_control_center_core.py    66 bài — sổ, khoá, quyền, phân rã
scripts/tests/test_control_center_slice.py   35 bài — lát cắt dọc, kho git thật
scripts/tests/test_control_center_ui.py      11 bài — 7 màn hình, Textual headless
                                            ─────
toàn bộ scripts/tests                      1062 bài — OK (1 skipped)
tests/ (desktop, kiểm hồi quy)               397 bài — OK
```

Thay đổi duy nhất chạm Router V4 là **một tham số tuỳ chọn**
(`Executor(worktree_provider=...)`), mặc định `None` = hành vi cũ nguyên vẹn.
177 bài kiểm V3/V4 vẫn xanh.
