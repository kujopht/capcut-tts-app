# Runbook — điều khiển Fanfic World Home từ điện thoại

## 0. Một lần duy nhất (bắt buộc trước khi dùng lần đầu)

Remote Control từ chối chạy vì thư mục project chưa được "trust" — đây là
hộp thoại tương tác, không tự động hoá được. Mở PowerShell trên máy:

```powershell
cd C:\Users\nguye\Documents\CapCut-TTS-App
claude
```

Chấp nhận hộp thoại workspace trust khi nó hiện ra, rồi thoát (`/exit` hoặc
Ctrl+C). Chỉ cần làm việc này MỘT LẦN cho thư mục này.

Sau đó khởi động server (giữ cửa sổ này mở, hoặc xem mục 3 để tự khởi động):

```powershell
claude remote-control --name "Fanfic World Home" --spawn worktree
```

Terminal sẽ in ra một **session URL** — mở URL đó một lần trên máy tính
hoặc điện thoại để xác nhận liên kết với tài khoản claude.ai của bạn.

## 1. Từ điện thoại

1. Mở Claude mobile app.
2. Vào tab **Code**.
3. Chọn phiên tên **"Fanfic World Home"**.
4. Gõ yêu cầu, gửi.
5. Nhận push notification khi Claude bị chặn (cần bạn quyết định) hoặc đã
   xong việc.
6. Mở app, xem kết quả.
7. Trả lời/tiếp tục ngay trong cùng phiên.

## 2. Bật push notification (nếu chưa thấy)

Trong một phiên Claude Code bất kỳ, gõ `/config` → bật **"Push when
actions required"** và **"Push when Claude decides"**. Cần cài Claude
mobile app, đăng nhập cùng tài khoản, và cho phép notification ở cấp hệ
điều hành điện thoại.

## 3. Quyền tự chủ khi điều khiển từ xa (ĐÃ cấu hình)

Hồ sơ quyền nằm ở `.claude/settings.json` — **phạm vi dự án**, không phải
toàn cục. Hồ sơ được thiết kế cho **hai chế độ**:

- **Chế độ A — `auto`** (điện thoại / điều khiển từ xa, mặc định của dự
  án): việc chỉ-đọc và việc phát triển thường ngày chạy tự chủ; thao tác
  ghi lên remote (push, tạo/merge PR, deploy) mới hỏi.
- **Chế độ B — `bypassPermissions`** (khi bạn ngồi trực tiếp ở laptop):
  không hỏi những việc thường ngày kể trên; **ranh giới cấm tuyệt đối
  vẫn giữ nguyên** — xem hàng `deny`.

Thứ tự áp dụng, **đo trực tiếp trên Claude Code 2.1.231** (không phải suy
đoán — xem `docs/reports/permission-two-mode-refactor-2026-08-28.md`):

| Lớp | Đè được `allow`? | Có hiệu lực trong `bypassPermissions`? |
|---|---|---|
| `deny` của hook PreToolUse | Có | **Có** |
| `ask` của hook PreToolUse | Có | (hook tự tắt theo chế độ) |
| `allow` của hook PreToolUse | **Không — bị bỏ qua** | — |
| `ask` trong `settings.json` | — | **Có** (nên đã bỏ hết `Bash(...)` khỏi `ask`) |

Vì `ask` trong `settings.json` vẫn kích hoạt cả ở chế độ B, toàn bộ luật
`ask` dạng `Bash(...)` đã được chuyển vào hook
`.claude/hooks/guard_indirect_exec.py` — nơi đọc được `permission_mode`
và quyết định theo từng chế độ. `ask` trong `settings.json` nay **chỉ còn
các luật `Edit(...)`** bảo vệ chính tệp cấu hình và hook.

| | Nội dung |
|---|---|
| **allow** (chạy thẳng, không hỏi) | đọc/tìm/sửa tệp trong repo; `git` chỉ-đọc + add/commit/checkout/stash/worktree; `gh` chỉ-đọc (`run list/view`, `workflow list/view`, `pr view/list/checks/diff`, `repo view`, `issue list/view`, `release list/view`, `auth status`, `search`, secret/variable **list tên**); `npm`/`npx`/`node`/`pnpm`/`yarn`; `python`/`pytest`/`pip`/`uv`/`ruff`/`mypy`; lint/typecheck/test/build; `npm run cf:build`, `opennextjs-cloudflare build`, `wrangler types/dev/whoami/deployments list/tail`; `curl` chỉ-đọc; Playwright; PowerShell chỉ-đọc (`Get-*`, `Test-Path`, `Select-String`) |
| **ask** (hỏi ở chế độ A, KHÔNG hỏi ở chế độ B — do hook quyết định) | `git push` thường; `gh pr create/merge/close/review`; `gh workflow run/enable/disable`; `gh run cancel/rerun/delete`; `gh release create/delete/edit`; `gh issue create/edit`; `gh api` với `POST/PUT/PATCH` hoặc `-f/--field/--input`; `gh auth login`; `wrangler login/deploy/rollback/versions deploy`; `npm run cf:deploy*`; gọi deploy hook Render |
| **ask** (luôn hỏi, cả hai chế độ) | sửa `.github/workflows/**`, `.claude/settings.json`, `.claude/settings.local.json`, `.claude/hooks/**`, `deploy/render*.yaml`, `web/wrangler*.jsonc` |
| **deny** (chặn hẳn) | đọc `.env`/khoá riêng/OAuth/cookie/`.wrangler`/`rclone.conf`; `gh auth token`, `gh secret set/delete`; viết lại lịch sử git (`reset --hard`, `rebase`, `filter-branch`, force-push, xoá nhánh từ xa); xoá đệ quy (`rm -r*`, `Remove-Item -Recurse`); `curl` có `-X POST/PUT/PATCH/DELETE`/`-d`/`--data`; xoá tài nguyên production (`wrangler * delete`, `wrangler secret`, `gcloud/aws * delete`, `appwrite * delete`); Defender (`*-MpPreference`); registry (`reg add/delete`, `Set-ItemProperty HK*`); Task Scheduler (`schtasks`, `*-ScheduledTask`); dịch vụ Windows (`sc.exe`, `*-Service`); tường lửa/mạng (`netsh`, `*-NetFirewallRule`); leo thang quyền (`runas`, `Start-Process -Verb RunAs`, `Set-ExecutionPolicy`) |

`defaultMode: "auto"` — sửa tệp trong repo không hỏi lại từng lần, nhưng
mọi lệnh Bash vẫn đi qua ba danh sách trên **và** qua hook PreToolUse.

**Hai lệnh runtime tự chặn, không sửa được bằng hồ sơ quyền:** `gh api`
và `git push` bị chính Claude Code 2.1.231 bắt xác nhận, kể cả khi đã có
luật `allow` khớp và kể cả khi gỡ bỏ hoàn toàn hook. Đây **không phải**
false positive của hồ sơ này. Ở phiên tương tác bạn bấm duyệt là xong; ở
phiên không tương tác chúng fail-closed. Muốn tra cứu GitHub tự chủ từ
điện thoại, hãy dùng các lệnh con tương đương thay cho `gh api`:

```bash
gh run list --limit 10          # thay cho gh api .../actions/runs
gh workflow list                # thay cho gh api .../actions/workflows
gh pr view <n> --json state     # thay cho gh api .../pulls/<n>
gh repo view --json visibility  # thay cho gh api repos/<owner>/<repo>
```

**Đây là so khớp mẫu văn bản, không phải hộp cát ngữ nghĩa.** Nó chặn
đúng những dạng lệnh đã liệt kê; một lệnh viết vòng vo đủ khác đi vẫn có
thể lọt. Coi nó là hàng rào giảm ma sát cho việc thường ngày, không phải
biên giới an ninh.

## 4. Giữ server sống qua reboot (thiết kế — CHƯA tự tạo, CỐ Ý)

Khuyến nghị: **Windows Task Scheduler**, trigger "At log on" (KHÔNG dùng
auto-login Windows), chạy dưới tài khoản người dùng hiện tại (không phải
SYSTEM, để giữ đúng phiên đăng nhập claude.ai của bạn).

Tác vụ này **phải do bạn tự tạo**: `schtasks` và `*-ScheduledTask` nằm
trong danh sách `deny` ở mục 3, đúng theo yêu cầu "giữ phê duyệt thủ công
cho Task Scheduler". Lệnh chính xác, chạy trong PowerShell thường (không
cần quyền admin vì tác vụ chạy dưới chính tài khoản bạn):

```powershell
$claude = (Get-Command claude).Source
$action  = New-ScheduledTaskAction -Execute $claude `
    -Argument 'remote-control --name "Fanfic World Home" --spawn worktree' `
    -WorkingDirectory 'C:\Users\nguye\Documents\CapCut-TTS-App'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'FanficWorldHome-RemoteControl' `
    -Action $action -Trigger $trigger -Settings $set -Description `
    'Claude Code Remote Control cho Fanfic World Home (chay duoi tai khoan nguoi dung)'
```

Kiểm tra sau khi tạo:

```powershell
Get-ScheduledTask -TaskName 'FanficWorldHome-RemoteControl' | Get-ScheduledTaskInfo
```

Gỡ bỏ:

```powershell
Unregister-ScheduledTask -TaskName 'FanficWorldHome-RemoteControl' -Confirm:$false
```

**Vì sao Task Scheduler chứ không phải Windows Service:** service chạy
dưới SYSTEM hoặc một tài khoản dịch vụ riêng, không thấy phiên đăng nhập
claude.ai lưu trong hồ sơ người dùng của bạn — server sẽ khởi động rồi
lập tức hỏng vì không xác thực được. Trigger "At log on" giữ đúng ngữ
cảnh người dùng. Đổi lại: phải đăng nhập Windows thì server mới chạy —
đây là đánh đổi có chủ ý, vì cách khắc phục duy nhất là bật auto-login
Windows, tức lưu mật khẩu Windows ở dạng khôi phục được.

## 5. Sự cố thường gặp

| Triệu chứng | Xử lý |
|---|---|
| "Workspace not trusted" | Chạy lại mục 0, bước `claude` tương tác |
| Không thấy phiên trên điện thoại | Kiểm tra đã đăng nhập ĐÚNG tài khoản claude.ai trên cả hai nơi |
| Server đóng khi tắt cửa sổ | Bình thường — cần mục 4 (Task Scheduler) để sống qua reboot/đăng xuất |
| Vẫn bị hỏi phê duyệt việc thường ngày | Hồ sơ quyền chỉ được nạp lúc **bắt đầu phiên**. Khởi động lại `claude remote-control`. Nếu vẫn hỏi, lệnh đó nằm trong `ask`/`deny` ở mục 3 — đó là cố ý |
| Bị hỏi khi chạy `gh api` hoặc `git push` | Runtime tự chặn, không phải hồ sơ quyền (mục 3). Dùng lệnh con `gh` tương đương cho việc chỉ-đọc; `git push` thì đằng nào cũng thuộc nhóm cần xác nhận |
| Worktree sinh ra không có `.claude/settings.json` | `--spawn worktree` tạo worktree từ nhánh hiện tại. Hồ sơ quyền chỉ áp dụng cho worktree khi commit chứa nó đã có mặt trên nhánh đó |
