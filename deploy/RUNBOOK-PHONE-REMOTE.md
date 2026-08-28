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
toàn cục. Không bật `bypassPermissions`, không dùng
`--dangerously-skip-permissions`; ngược lại
`disableBypassPermissionsMode: "disable"` được giữ nguyên nên chế độ bỏ
qua quyền **không thể bật được** trong dự án này, kể cả bằng tay.

Thứ tự áp dụng của Claude Code là **deny > ask > allow**, nên danh sách
`allow` rộng vẫn không thể vượt qua `deny`/`ask`.

| | Nội dung |
|---|---|
| **allow** (chạy thẳng, không hỏi) | đọc/tìm/sửa tệp trong repo; `git` chỉ-đọc + add/commit/checkout/stash/worktree; `gh` chỉ-đọc (pr/run/issue/workflow list-view, secret/variable **list tên**); `npm`/`npx`/`node`/`pnpm`/`yarn`; `python`/`pytest`/`pip`/`uv`/`ruff`/`mypy`; lint/typecheck/test/build; `npm run cf:build`, `opennextjs-cloudflare build`, `wrangler types/dev/whoami/deployments list/tail`; `curl` chỉ-đọc; Playwright; PowerShell chỉ-đọc (`Get-*`, `Test-Path`, `Select-String`) |
| **ask** (vẫn hỏi bạn) | `git push`, `git merge`, `gh pr create/merge`, `gh api`, `gh release`, `gh workflow run`, `gh auth login`, `wrangler login/deploy/rollback/versions deploy`, `npm run cf:deploy*`, gọi deploy hook Render, sửa `.github/workflows/**`, `.claude/settings.json`, `deploy/render*.yaml`, `web/wrangler*.jsonc` |
| **deny** (chặn hẳn) | đọc `.env`/khoá riêng/OAuth/cookie/`.wrangler`/`rclone.conf`; `gh auth token`, `gh secret set/delete`; viết lại lịch sử git (`reset --hard`, `rebase`, `filter-branch`, force-push, xoá nhánh từ xa); xoá đệ quy (`rm -r*`, `Remove-Item -Recurse`); `curl` có `-X POST/PUT/PATCH/DELETE`/`-d`/`--data`; xoá tài nguyên production (`wrangler * delete`, `wrangler secret`, `gcloud/aws * delete`, `appwrite * delete`); Defender (`*-MpPreference`); registry (`reg add/delete`, `Set-ItemProperty HK*`); Task Scheduler (`schtasks`, `*-ScheduledTask`); dịch vụ Windows (`sc.exe`, `*-Service`); tường lửa/mạng (`netsh`, `*-NetFirewallRule`); leo thang quyền (`runas`, `Start-Process -Verb RunAs`, `Set-ExecutionPolicy`) |

`defaultMode: "acceptEdits"` — sửa tệp trong repo không hỏi lại từng lần,
nhưng mọi lệnh Bash vẫn đi qua ba danh sách trên.

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
| Worktree sinh ra không có `.claude/settings.json` | `--spawn worktree` tạo worktree từ nhánh hiện tại. Hồ sơ quyền chỉ áp dụng cho worktree khi commit chứa nó đã có mặt trên nhánh đó |
