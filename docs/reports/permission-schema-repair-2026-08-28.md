# Sửa luật quyền hỏng + guard PreToolUse + mở lại bypassPermissions (2026-08-28)

Tiếp nối `permission-security-review-2026-08-28.md`. Lượt này **không** dựa
trên matrix tĩnh nữa — mọi kết luận đều kiểm chứng bằng **runtime Claude Code
thật đang cài** (2.1.231, `claude doctor` + phiên `claude -p` thật).

## 1. Phát hiện nghiêm trọng: 34 luật deny CHƯA BAO GIỜ được nạp

Commit `eeb64c1` ghi "close 40 confirmed permission bypasses". Thực tế runtime
**bỏ qua 34 luật** vì lỗi ngoặc không cân:

```
Invalid permission rule "Bash(*$(cat *)" was skipped: Mismatched parentheses
```

Thân luật `*$(cat *` có một `(` thừa. Cả 33 bộ ba `$(…)` + luật
`*awk*system(*` đều hỏng. Các anh em backtick và `${…}` của cùng bộ ba thì
hợp lệ và vẫn chạy — nên lỗi bị che, không ai thấy.

**Hệ quả:** lớp chặn laundering qua `$(…)` mà §4 báo cáo trước tuyên bố đã
đóng, thực tế **mở suốt từ đầu**.

## 2. Cách sửa, và bằng chứng runtime

Dạng cân bằng `Bash(*$(cat *)*)` được runtime chấp nhận. Kiểm bằng thư mục
nháp trước khi đụng file thật: 486/486 luật hợp lệ, 0 bị bỏ qua.

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Luật deny bị runtime bỏ qua | **34** | **0** |
| Tổng luật deny | 486 (452 hiệu lực) | **494** (494 hiệu lực) |
| Cảnh báo lúc khởi động | 34 + 9 | **0** |
| Luật `Write(...)`/`Glob(...)` vô hiệu | 9 | **0** |
| Lớp chặn thực thi gián tiếp | chỉ glob (34 luật chết) | glob **+** guard PreToolUse |
| `defaultMode` | `acceptEdits` | **`auto`** |
| `disableBypassPermissionsMode` | `"disable"` (project + user) | **bỏ** — bật thủ công được |

### 9 luật vô hiệu khác, chỉ runtime mới báo

`claude doctor` **không** hiện nhóm này; chỉ phiên thật mới báo:

```
Permission allow rule: Write(**) is not matched by file permission checks
  — only Edit(path) rules are.
```

`Write(path)` và `Glob(path)` **không bao giờ khớp** — `Edit(path)` đã bao
toàn bộ công cụ ghi, `Read(path)` bao toàn bộ công cụ đọc. 6 luật
`Write(...)` trong `ask` (gồm `Write(.claude/settings.json)` có từ trước) và
3 luật `Write(**)`/`Glob(**)` trong `allow` đều là rác. Đã xoá; ranh giới
không đổi vì bản `Edit(...)`/`Read(...)` vẫn còn.

## 3. Guard PreToolUse — lớp thứ hai

`.claude/hooks/guard_indirect_exec.py`. Glob chỉ khớp chuỗi thô; guard **tách
cấu trúc shell**: chẻ theo `;` `&&` `||` `|`, và bóc thân mọi `$( )`, backtick,
`${ }` **đệ quy, có đếm độ sâu ngoặc** — regex không làm được vì thân lệnh có
thể chứa ngoặc cân (`$(python -c 'f(1)')`, ca này bắt hụt ở bản đầu).

Chặn: `-c`/`-e` của python/node/perl/ruby/bash, `-Command`/`-EncodedCommand`
(khớp **tiền tố** như PowerShell thật: `-Comm`, `-enc`), `cmd /c`, git phá
huỷ, force push, xoá đệ quy, schtasks/registry/service/Defender/firewall,
`gh secret`/`gh auth token`, `awk system()`, `xargs`, `eval`, và mọi thao tác
đụng `.claude/hooks/`.

**Không** chặn: `python -m unittest`, `npm run *`, `git status/diff/log`,
`$(git rev-parse …)`, `reg query`, `git clean -n`, `git branch -d`.

Lỗi nội bộ của guard → trả `ask`, **không bao giờ** `allow`.

### Một lỗi thật do runtime bắt được

Đường dẫn tương đối `.claude/hooks/…` giải theo **cwd của phiên**, mà cwd giữ
nguyên giữa các lệnh Bash. Sau một `cd web`, hook trỏ vào `web/.claude/hooks/`
→ lỗi. Nó **fail closed** (chặn lệnh, đúng hướng) nhưng chặn cả việc hợp lệ.
Đã đổi sang `${CLAUDE_PROJECT_DIR}/.claude/hooks/…`, xác nhận runtime có thay
thế biến này và guard chạy đúng từ cwd bất kỳ.

## 4. bypassPermissions: kiểm chứng, không suy đoán

Câu hỏi quyết định kiến trúc mới: ranh giới có sống sót khi bật bypass không?
Dựng lab riêng, chạy phiên `claude -p --dangerously-skip-permissions` thật:

| Câu hỏi | Mồi thử | Kết quả |
|---|---|---|
| Luật deny còn chặn? | `echo "$(wget …)"` (chỉ glob phủ) | ✅ **CÒN CHẶN** |
| Guard còn chặn? | `node --eval …` (chỉ guard phủ) | ✅ **CÒN CHẶN** |

**Cả hai lớp đều độc lập với permission mode.** Mode bypass bỏ qua *prompt*,
không bỏ qua deny rule và không bỏ qua PreToolUse hook. Kiến trúc "AUTO khi ở
xa, bypass thủ công khi ngồi máy" là an toàn.

Lệnh khởi chạy đích:

```
claude --remote-control "Fanfic World Home" --permission-mode auto \
       --allow-dangerously-skip-permissions
```

`--allow-dangerously-skip-permissions` chỉ **mở khả năng** chuyển sang bypass,
không bật sẵn. Lần đầu chuyển sẽ có hộp thoại xác nhận
(`skipDangerousModePermissionPrompt: false`) — giữ nguyên là đúng.

## 5. Nghiệm thu

```
claude doctor                       : 0 invalid, 0 skipped
khởi động phiên thật (user+project+local): 0 Settings Warning
matrix đối kháng (mới, 98 ca)       : 98/98 (66 chặn, 32 chạy được)
guard dưới bypassPermissions        : CHẶN
deny rule dưới bypassPermissions    : CHẶN
server/tests                        : 3263 OK (skipped=3)
tests (desktop)                     : OK
web typecheck                       : sạch
web lint                            : 0 lỗi, 2 cảnh báo có sẵn
compileall                          : OK
```

Matrix nằm ở `.claude/hooks/test_guard_indirect_exec.py`, chạy lại bằng
`python .claude/hooks/test_guard_indirect_exec.py`. Kho **chưa từng có** matrix
chạy được — bản 109 ca của lượt trước là mô hình tĩnh trong đầu, tự nhận là
"XẤP XỈ engine thật". Đây là bản đầu tiên chạy được thật.

## 6. Giới hạn còn lại — nói thẳng

- Guard là **denylist**. Lệnh nguy hiểm không có trong danh sách, lồng trong
  `$()`, vẫn lọt. Đóng hẳn phải chặn *mọi* `$()` — đã cân nhắc và loại vì phá
  việc thường ngày.
- Che tên tệp (`cat "$HOME/.e""nv"`) vẫn qua được lớp chặn theo tên.
- Xoá được `.claude/hooks/*` thì guard im lặng biến mất (hook lỗi → tuỳ ca).
  Đã chặn đường Bash (`rm`/`cp`/`mv`/`>`/`tee`/`dd`/`sed -i` vào
  `.claude/hooks/`) và cổng `Edit(.claude/hooks/**)` ở `ask`. Không tuyệt đối.
- Bash đọc được mọi tệp người dùng đọc được — bản chất, không phải lỗi cấu hình.
