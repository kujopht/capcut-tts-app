# V1.0 — KIỂM KÊ NĂNG LỰC RUNTIME (audit, chưa kích hoạt gì)

Nhánh `feat/v10-autonomous-project-leader`, dựng từ `main @ f974b5a`
(`router-control-center-v0.9.3`).

Ba mức, và tệp này giữ chúng TÁCH BẠCH:

* **ĐO ĐƯỢC** — chạy trên máy này, có đầu ra dán lại được;
* **SUY RA** — đọc tài liệu/`--help`, chưa chạy thử;
* **KHÔNG CÓ** — không chứng minh được ở đây, và vì thế KHÔNG được bật.

---

## 1. Claude Code CLI — ĐO ĐƯỢC

`claude` có ở `C:\Program Files\nodejs\claude.cmd`. `--help` khai TƯỜNG MINH
các cờ phiên (trích nguyên văn):

```
  -c, --continue            Continue the most recent conversation in ...
  -r, --resume [value]      Resume a conversation by session ID, or
                            open interactive picker with optional search term
  --session-id <uuid>       Use a specific session ID for the
                            conversation (must be a valid UUID)
  --fork-session            When resuming, create a new session ID
                            instead of reusing the original
  -p, --print               Print response and exit (useful for pipes)
  --model <model>           Model for the current session
  --output-format <format>  Output format (only works with --print)
  --permission-mode <mode>  Permission mode to use for the session
  --agents <json>           JSON object defining custom agents
  --bg, --background        Start the session as a background agent
```

**Kết luận:** phiên Leader bền (B3) có một đường **được hỗ trợ chính thức**:
`--session-id <uuid>` để tạo, `-r <uuid>` để nối lại, `--fork-session` để
tách nhánh khi phiên quá nặng. KHÔNG cần đọc tệp phiên nội bộ, KHÔNG cần
cookie trình duyệt.

Điều này quan trọng vì nó tách `V10` khỏi mọi thứ không chính thức: định danh
phiên là một UUID **do Router sinh và Router giữ**, không phải một thứ moi ra
từ trạng thái riêng của một công cụ khác.

## 2. Codex CLI — ĐO ĐƯỢC

`codex-cli 0.153.4`. `codex exec --help` khai:

```
  resume                     Resume a previous session by id or pick the most
                             recent with --last
  fork                       Fork a previous session by id into a new session
  -m, --model <MODEL>
  -s, --sandbox <SANDBOX_MODE>   Select the sandbox policy ...
      --dangerously-bypass-approvals-and-sandbox   EXTREMELY DANGEROUS
```

**Hai điều đáng ghi:**

1. Codex CÓ `resume`/`fork` — cùng hình dạng với Claude Code. Một trừu tượng
   phiên chung là khả thi, không phải khiên cưỡng.
2. Codex CÓ `--sandbox`. Adapter của Router **không truyền cờ này**, nên
   `codex exec` chạy sandbox CHỈ ĐỌC — đó là nguyên nhân đã đo được của
   "Sandbox hệ thống chặn mọi thao tác ghi" ở V0.9.3. Mở nó là CẤP THÊM
   quyền ghi cho một CLI ngoài: cần probe có giới hạn + duyệt của chủ sở
   hữu. **Chưa làm.** `--dangerously-bypass-approvals-and-sandbox` thì không
   bao giờ.

## 3. Antigravity (`agy`) — ĐO ĐƯỢC

Đã đo ở V0.9.3 bằng một probe có giới hạn (`run_native`, thư mục tạm):

* `--mode accept-edits` + `--add-dir <workspace>` → **GHI ĐƯỢC** (tạo
  `index.html`, 15.6s, `status=SUCCESS`);
* headless **tự chối** `command` (không hỏi người dùng được) → một lượt chạm
  vào là mất trắng;
* hạn mức là THẬT và đo được: một tài khoản trả
  `Individual quota reached … Resets in 48h57m19s`.

## 4. Hai kho tham chiếu người dùng chỉ định — AUDIT, KHÔNG TÍCH HỢP

### 4a. `miuuyy/codex-chatgpt-web` — adapter TUỲ CHỌN cho vai GPT

**Là gì:** ứng dụng desktop KHÔNG CHÍNH THỨC, đưa ChatGPT Web vào Codex như
model bản địa, để dùng gói Pro mà không đốt quota API của Codex. Giấy phép
**MIT**.

**Cách nối:** **tự động hoá trình duyệt bằng Playwright**, không phải API
OpenAI. Chromium nhúng, phiên đăng nhập riêng.

**Điểm kỹ thuật đáng học** (theo README):

* phiên theo TÁC VỤ + nén ngữ cảnh bản địa; checkpoint ghi trước ranh giới
  ngữ cảnh — cùng ý tưởng với `B3` ở đây;
* gọi công cụ ngược về tác vụ Codex hiện tại qua tunnel-client chính thức;
  có MCP + giao thức subagent;
* `Settings → Run doctor` cho kiểm tra đầu-cuối;
* **fail-closed tường minh**: *"drift fails explicitly instead of silently
  switching model or transport"* — đúng nguyên tắc Router đã theo.

**Phán quyết cho tối nay: KHÔNG TÍCH HỢP.** Lý do, theo đúng ràng buộc người
dùng đặt ra:

* Router **không được phụ thuộc** tự động hoá trình duyệt không chính thức.
  Nó chịu ToS của ChatGPT, và selector drift là một dạng hỏng mà Router không
  kiểm soát được.
* Giá trị cận biên là **quota**, không phải năng lực: Router ĐÃ có đường
  chính thức tới GPT qua `codex-cli` (cùng bản CLI phơi ra `gpt-5.6-sol` và
  `gpt-6-astra`). Đánh đổi "tiết kiệm quota" lấy "một transport không chính
  thức ở giữa đường thực thi" là sai chiều với mọi thứ V0.9.x vừa sửa.
* **Không** sao chép/lưu credential trình duyệt vào Project Memory — không
  bao giờ, kể cả khi tích hợp sau này.

**Thiết kế adapter + kế hoạch probe CÓ GIỚI HẠN (nếu sau này muốn):**

```
lớp        adapter tuỳ chọn, TẮT mặc định, sau cờ cấu hình tường minh
danh tính  runtime_id riêng (vd GPTWEB01), quota_pool riêng — KHÔNG trộn
           vào bể codex đang đo
năng lực   khai đúng thứ probe chứng minh; KHÔNG khai `implement` cho tới
           khi một lượt ghi thật đi qua cổng kiểm định
sức khoẻ   dùng `Run doctor` của chính nó làm health check; drift -> UNHEALTHY,
           fail closed, KHÔNG âm thầm đổi model/transport
probe      1 lượt đọc + 1 lượt ghi trong worktree tạm, không production,
           không credential đi qua Router, đối chiếu `git status` như mọi
           worker khác
dừng       nếu probe không xanh 2/2 thì adapter ở lại TẮT và ghi
           UNAVAILABLE — không bao giờ "gần như chạy được"
```

### 4b. `danyl-dnl/CodeLocal` — THAM KHẢO Ý TƯỞNG, KHÔNG LẤY MÃ

**Là gì:** nền tảng lập trình cộng tác LAN, offline-first. Đồng bộ thời gian
thực bằng **Yjs**; host lưu thay đổi vào một thư mục `workspace/` **DÙNG
CHUNG**, bền qua khởi động lại. Không xác thực; tên hiển thị lưu cục bộ.

**Không lấy được, và đây là điểm quan trọng nhất:** mô hình của nó là **một
cây làm việc dùng chung, sửa đồng thời**. An toàn của Router đặt trên điều
NGƯỢC LẠI — mỗi việc một worktree CÔ LẬP, và cổng `scope` đối chiếu
`git status` trong đúng cây đó. Thay isolation bằng shared filesystem là gỡ
đúng cái rào mà cả V0.9.x vừa chứng minh là cần.

**Ý tưởng đáng giữ cho Team Activity (B7/B12):**

* CRDT (Yjs) cho **dòng SỰ KIỆN và hiện diện**, không cho nội dung tệp — sự
  kiện là append-only, hợp CRDT tự nhiên, và không đụng tới cây làm việc;
* địa chỉ LAN hiện ra để máy khác xem — nhưng Router bind `127.0.0.1` có chủ
  đích (`webapi.py`, ba bất biến). Mở LAN là một quyết định bảo mật riêng,
  cần token + kiểm `Host` như đường hiện tại, không phải một cờ tiện tay.

**Giấy phép: KHÔNG nêu trong nội dung đọc được.** Nên **không sao chép một
dòng mã nào** cho tới khi giấy phép được xác minh tường minh. Ý tưởng kiến
trúc thì tự do.

---

## 4c. `codex-chatgpt-web` — KHÔNG CÀI TRÊN MÁY NÀY (đo 2026-09-13)

Dò trực tiếp: không có lệnh `codex-chatgpt-web` / `codex-web` / `chatgpt-web`
trên `PATH`, và không có thư mục cài ở `%LOCALAPPDATA%\Programs\`,
`%APPDATA%\`, hay `%USERPROFILE%\`.

Nên **không có probe nào chạy được**, và adapter ở lại **UNVERIFIED**. Đây là
kết luận ĐO ĐƯỢC, không phải một lựa chọn thận trọng.

**Thiếu chính xác những gì** (để lần sau không phải dò lại):

1. bản thân ứng dụng — chưa cài;
2. một phiên ChatGPT đã đăng nhập trong trình duyệt nhúng của nó (Router
   **không** được chạm vào, không được sao chép, không được lưu ở đâu);
3. một quyết định tường minh của chủ sở hữu rằng chấp nhận một transport
   KHÔNG CHÍNH THỨC cho vai Sol/Astra, kèm hiểu rằng nó chịu ToS của ChatGPT;
4. một `runtime_id` + `quota_pool` RIÊNG trong fabric (vd `GPTWEB01`), không
   trộn vào bể `codex` đang đo được.

Cho tới khi đủ bốn thứ đó, Router vẫn đi đường chính thức: `codex-cli`
0.153.4, cùng bản CLI phơi ra `gpt-5.6-sol` và `gpt-6-astra`.

## 5. Thứ KHÔNG chứng minh được ở đây

| Thứ | Trạng thái |
|---|---|
| Claude Opus 5 như một runtime worker do Router điều phối | **CHƯA XÁC MINH** — `claude` CLI có mặt và có cờ phiên, nhưng chưa có lượt Leader nào chạy qua nó dưới quyền Router |
| `gpt-6-astra` / `gpt-5.6-sol` qua Codex | SUY RA từ ghi chú fabric (`codex doctor`, 2026-09-09); chưa đo lại đêm nay |
| Hạn mức theo bể (Gemini / Claude / GPT tách riêng?) | **KHÔNG BIẾT** — chỉ đo được một sự kiện "Individual quota reached" trên một tài khoản. Không suy ra topology từ một điểm |
| `codex --sandbox workspace-write` | CÓ cờ (đo được), **chưa bật**, chưa probe |
| codex-chatgpt-web | KHÔNG cài, KHÔNG bật, chỉ có thiết kế + kế hoạch probe ở trên |

**Không bịa hạn mức, không bịa năng lực.** Chỗ nào không đo được thì ghi
`UNKNOWN` và để nguyên — đó là luật đã có từ V0.6.1 và nó vẫn áp dụng.
