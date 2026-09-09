# V0.3 — Project Leader: ô chat trở thành sản phẩm

## 1. Vấn đề V0.2 để lại

Không phải một danh sách thiếu sót — là một sản phẩm sai hình dạng:

- mọi tin nhắn đều thành một việc Router, kể cả `ê bro`
- hỏi "project tới đâu rồi?" cũng dựng phiên agent để trả lời thứ **sổ và
  `git` đã biết sẵn**
- việc xong → một huy hiệu `DONE`, **không có câu trả lời nào**; muốn biết
  kết quả phải mở tab Logs
- id phiên, worktree, cơ chế lập lịch chiếm hết mặt tiền

Ô chat là một **biểu mẫu nộp việc**, không phải một trợ lý.

## 2. Kiến trúc

```
người dùng
   │  tin nhắn
   ▼
PROJECT LEADER  ── AnhChupDuAn (tất định: sổ + git, KHÔNG agent)
   │  QuyetDinhLeader {reply, y_dinh, actions[]}
   ├── CHAT     → trả lời, KHÔNG việc, KHÔNG phiên worker
   ├── STATUS   → trả lời TỪ ẢNH CHỤP, KHÔNG worker
   ├── CONTROL  → hành động CÓ CẤU TRÚC (pause/resume/cancel/approve…)
   └── WORK     → bộ phân rã → ROUTER V4 (nguyên vẹn)
                                   │
                                   ▼
                          việc kết thúc → tin nhắn assistant
                                          trong ĐÚNG hội thoại đó
```

**Router V4 không đổi một dòng nào** về lập lịch, khoá, worktree, vòng đời
executor, kiểm định, thử lại, sức khoẻ nhà cung cấp. Leader chỉ thêm một
lớp Ý ĐỊNH ở phía trước.

## 3. Vòng đời Leader

| | |
|---|---|
| Danh tính | bảng `leader`: `project_id`, `thread_id`, `che_do`, `provider`, `model`, `context` |
| Hội thoại | bảng `chat` như cũ — **không** phụ thuộc phiên bên nhà cung cấp |
| Phiên | một `agy` **ấm** cho mỗi dự án, `allow_edits=False`, `workspace=None` |
| Model | `gemini-3.8-flash-high`, **ghim tường minh** |
| Làm ấm | ở nền, khi `start()` và khi thêm dự án |
| Khởi động lại | dựng lại từ `chat` + `AnhChupDuAn` — **không mất hội thoại** |

Leader **không sở hữu worktree** và **không có quyền ghi** — rào ở tầng
tiến trình, không chỉ ở lời dặn trong nhắc nhở. Có bài kiểm đọc AST của
`leader.py` để giữ điều đó.

## 4. Định tuyến tin nhắn — MỘT lượt, không phải hai

Ảnh chụp được đính kèm **ngay** vào lượt hỏi, nên câu hỏi trạng thái được
trả lời trong **một** lần gọi model. Không có "bộ phân loại" riêng chạy
trước: ý định hiện ra trong chính phong bì hành động Leader trả về.

Không có JSON hợp lệ → coi là `CHAT`. Đó **không** phải nới lỏng: `CHAT`
là hành động vô hại nhất (chỉ nói). Mọi thứ có hậu quả — uỷ thác, dừng,
duyệt — đều đòi JSON hợp lệ, nên một câu trả lời méo **không bao giờ** vô
tình dừng một việc thật.

## 5. Hợp đồng hành động

Danh sách **đóng**. Tên lạ, thiếu tham số bắt buộc, `task_id` không phải
chuỗi → **ném**, và người dùng đọc được lý do. Một lệnh "dừng task đó" bị
nuốt còn tệ hơn một lệnh báo lỗi.

```
reply_only · get_project_status · get_task · get_agent_status · get_usage
delegate_work · pause_task · resume_task · cancel_task · reassign_task
approve_gate
```

Hành động điều khiển còn bị kiểm `task_id` **có thật và thuộc đúng dự án**
trước khi chạy.

## 6. ProjectSnapshot

Đọc **sổ SQLite** + **`git`**. Không model, không worker, không mạng.

`project_id`/`name`/`repo_path` · có phải kho git · nhánh · HEAD · cây làm
việc sạch/bẩn + tệp đổi · commit gần đây · việc đang chạy/chờ/bị chặn/vừa
xong · phiên agent · worktree · khoá · sự kiện gần đây · tài liệu bàn giao
· usage **đo được**.

Usage không đo được thì **bỏ khỏi ảnh chụp**, không điền `0` —
`UsageMetric.__post_init__` cấm mâu thuẫn đó ở tầng dưới, và ảnh chụp
không được phá luật đó ở tầng trên.

## 7. Kết quả về ô chat — yêu cầu CHẶN PHÁT HÀNH

Ba tính chất, mỗi cái ứng với một chế độ hỏng thật:

| Tính chất | Vì sao |
|---|---|
| **Đúng một lần** | vòng lặp có thể thấy lại một việc đã kết thúc |
| **Đúng hội thoại** | `project_id` lấy từ CHÍNH việc đó, không từ ngữ cảnh đang mở |
| **Chưa xong thì chưa báo** | việc còn được xếp lại thì chưa phải kết quả cuối |

**Lưới an toàn** trong `tick()` quét việc đã kết thúc mà chưa có câu trả
lời. Cần nó vì một chuyện đã vấp thật ở nghiệm thu: người dùng bấm **Dừng**
→ việc sang `FAILED` qua `stop()`, một đường **không** đi qua chỗ báo kết
quả → ô chat im lặng. Đúng cái "huy hiệu FAILED không lời giải thích" mà
V0.3 sinh ra để bỏ.

Chống báo lặp dựa vào **bảng chat**, không chỉ bộ nhớ: bộ nhớ rỗng sau mỗi
lần mở lại, nên nếu chỉ tin nó thì lần mở sau sẽ đổ lại mọi kết quả cũ vào
hội thoại. Cộng thêm trần 30 phút: mở lại sau một tuần không được thuật
lại cả trăm việc cũ.

## 8. Giao diện

Tin nhắn `assistant` là mặc định. Thẻ việc **nội tuyến** ngay dưới câu của
Leader: tên việc · trạng thái · agent · nút **Dừng** khi đang chạy · nút
**Duyệt** khi bị chặn. Id phiên và đường worktree nằm dưới **Chi tiết**.

Vai `router` cũ vẫn đọc được — nâng cấp không được làm mất lịch sử chat.

Tasks/Agents/Logs/Usage giữ nguyên làm khung quan sát.

## 9. Nghiệm thu THẬT qua EXE đóng gói

| | Kịch bản | Kết quả |
|---|---|---|
| **A** | `ê bro` | `CHAT` · **0 việc, 0 phiên worker** · **6.5s** |
| **B** | "project tới đâu rồi?" | `STATUS` · 0 việc/phiên · trích đúng `e9b62d2 hat giong`, nhánh `main` |
| **C** | "agent nào đang chạy?" | `STATUS` · 0 việc/phiên · trả lời đúng |
| **D** | "inspect repo, do not modify" | `WORK` · DONE lượt 1 · **kết quả tự về chat** |
| **E** | tạo `docs/e.md` | `WORK` · DONE lượt 1 · worktree **cô lập** · kết quả + tệp đã đổi về chat |
| **F** | bấm **Dừng** giữa chừng | `FAILED` · **"❌ Hỏng: …" xuất hiện ở chat** |

**GPT-6 Astra: 0 lần.** Mọi lượt đi `antigravity/AG01` với
`gemini-3.8-flash-*`.

### Hai khuyết tật do chính nghiệm thu này tìm ra

1. **Kịch bản F im lặng.** `stop()` không đi qua đường điều phối nên chỗ
   báo kết quả không chạy → thêm lưới an toàn ở `tick()`.
2. **Tin nhắn đầu mất 90.2 giây.** Luồng làm ấm ở nền và tin nhắn đầu cùng
   gọi `mo()`, hai lần sinh `agy` tranh nhau **khoá launcher** (TTL 120s)
   → khoá lại `PhienLeader`, một phiên chỉ mở một lần. Còn **6.5s**.

## 10. Bộ kiểm

`scripts/tests/test_control_center_leader.py` — **37 bài**: hợp đồng hành
động (từ chối tên lạ/thiếu tham số), CHAT không tạo việc, STATUS không tạo
worker, WORK mới uỷ thác, điều khiển có cấu trúc + không chạm được việc
của dự án khác, kết quả DONE/FAILED/BLOCKED về chat, không báo hai lần,
không báo nhầm hội thoại, bền qua khởi động lại, Leader không dùng model
đắt, Leader không có worktree/quyền ghi.

Hồi quy: 253 + 177 + 95 (Qt) — tất cả ĐẠT.

## 11. Còn lại

- **Chế độ định tuyến chưa nối vào giao diện.** Bốn chế độ
  ECO/AUTO/STRONG/MAX đã có ở `premium.py`, mặc định `AUTO` lưu trong bảng
  `leader`, nhưng chưa có ô chọn ở màn hình gửi việc.
- **Leader chỉ chạy trên Antigravity.** Đủ cho hôm nay; muốn đổi nhà cung
  cấp thì `PhienLeader` cần một lớp trừu tượng mỏng.
- **Tin nhắn đầu vẫn ~6.5s** khi chưa kịp ấm (làm ấm chạy ở nền).
- **Chưa gắn thẻ.** Chờ nghiệm thu tay.
