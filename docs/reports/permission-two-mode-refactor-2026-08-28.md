# Tái cấu trúc hồ sơ quyền theo hai chế độ — 2026-08-28

Tiếp sau `permission-audit-2026-08-28.md`, `permission-schema-repair-2026-08-28.md`
và `permission-security-review-2026-08-28.md` (commit `db61a05`).

## 1. Vấn đề đã tái hiện

Hồ sơ quyền tuy đã "kín" nhưng còn **false positive**: luật `ask` quá rộng
bắt xác nhận cả thao tác chỉ-đọc, phá hỏng mục tiêu chạy tự chủ từ xa.

- `Bash(gh api*)` bắt duyệt cho một lệnh GET thuần chỉ-đọc
  (`gh api repos/<owner>/<repo>/branches/main/protection`).
- `Bash(gh release*)` chặn cả `gh release list` / `gh release view`.
- Việc tra cứu chỉ-đọc `gh workflow` / `gh run` không có luật `allow` nào
  phủ, nên rơi vào phán đoán của chế độ `auto` và vẫn có thể bị hỏi.

Nguyên nhân gốc: **glob khớp trên chuỗi lệnh thô, không nhìn thấy cờ.**
`gh api` là GET hay POST phụ thuộc `-X/--method/-f/--input` nằm ở bất kỳ
vị trí nào trong argv — một glob không thể phân biệt, nên nó buộc phải hỏi
tất cả.

## 2. Sự thật đo được về thứ tự ưu tiên (Claude Code 2.1.231)

Toàn bộ thiết kế dựa trên đo trực tiếp bằng hook thăm dò trong thư mục
tạm biệt lập, **không suy đoán từ tài liệu**:

| Lớp | Đè được luật `allow`? | Có hiệu lực trong `bypassPermissions`? |
|---|---|---|
| `deny` của hook PreToolUse | Có | **Có** |
| `ask` của hook PreToolUse | Có | (hook tự quyết theo chế độ) |
| `allow` của hook PreToolUse | **Không — bị bỏ qua hoàn toàn** | — |
| `ask` trong `settings.json` | — | **Có** |

Hai phát hiện quyết định kiến trúc:

1. **`ask` trong `settings.json` vẫn kích hoạt ở `bypassPermissions`.**
   Chứng minh bằng cặp đối chứng: cùng một lệnh, cùng chế độ bypass, chỉ
   khác việc có thêm luật `ask` → `RAN` đổi thành `DENIED`. Vì vậy mọi
   luật `ask` dạng `Bash(...)` đều phá chế độ B và phải bị gỡ.
2. **`allow` của hook không cấp quyền.** Hook trả `permissionDecision:
   "allow"` vô điều kiện vẫn không chạy được lệnh. Do đó tầng "chỉ-đọc,
   không hỏi" **bắt buộc** phải nằm ở `permissions.allow`, không thể nằm
   ở hook.

Trường `permission_mode` nằm ở cấp cao nhất của payload hook (snake_case),
giá trị quan sát được: `auto`, `default`, `acceptEdits`, `bypassPermissions`.

## 3. Kiến trúc mới — ba tầng, hai chế độ

| Tầng | Nơi thực thi | Chế độ A (`auto`) | Chế độ B (`bypassPermissions`) |
|---|---|---|---|
| 1. DENY cứng | hook `guard_indirect_exec.py` | chặn | **vẫn chặn** |
| 2. ASK (ghi lên remote) | hook, đọc `permission_mode` | hỏi | im lặng, cho chạy |
| 3. Chỉ-đọc, không hỏi | `permissions.allow` (hẹp) | chạy thẳng | chạy thẳng |

Hook phân loại `gh` theo argv thật (tách cờ khỏi subcommand) chứ không
theo tiền tố chuỗi — đó là điều glob không làm được, và là lý do
false positive biến mất mà không phải nới lỏng gì.

Nguyên tắc an toàn cho lệnh ghép: chỉ cấp "chỉ-đọc" khi **mọi** đoạn của
câu lệnh đều chỉ-đọc. `gh api ... && rm -rf build` vẫn bị DENY; `gh api
... > out.json` mất quyền chỉ-đọc vì có chuyển hướng ghi tệp; `2>&1`
được chuẩn hoá trước khi tách đoạn nên không bị hiểu nhầm thành lệnh thứ hai.

## 4. Bảng so sánh

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `Bash(gh api*)` trong `ask` | Có — bắt duyệt cả GET chỉ-đọc | Đã gỡ; hook phân loại theo method/cờ |
| `Bash(gh release*)` trong `ask` | Có — chặn cả `list`/`view` | Đã gỡ; chỉ `create/delete/edit/upload` mới hỏi |
| Số luật `ask` dạng `Bash(...)` | 24 | **0** (chuyển hết vào hook) |
| Luật `ask` còn lại | 30 (24 Bash + 6 Edit) | 6 — chỉ `Edit(...)` bảo vệ cấu hình/hook |
| `gh` chỉ-đọc trong `allow` | 3 luật (`run watch`, `secret list`, `variable list`) | 21 luật phủ `run/workflow/pr/repo/issue/release/auth status/search/label/cache` |
| Hook nhận biết chế độ | Không — quyết định như nhau mọi chế độ | Có — đọc `permission_mode`, tầng 2 tự tắt ở bypass |
| `git push` thường ở chế độ B | Bị luật `ask` chặn | Hook im lặng; không còn luật `ask` chặn |
| Phân loại `gh` mutating | Không có | 40 cặp subcommand + phân tích cờ của `gh api` |
| `gh api -X DELETE` | Chỉ chặn bằng glob `*DELETE*` | Chặn bằng glob **và** phân tích method (`-X`, `-XDELETE`, `--method=`) |
| Ma trận kiểm thử | 98 ca, một chế độ, gộp "im lặng" với "allow" | **326 ca, cả hai chế độ**, tách bạch `deny`/`ask`/`allow`/`silent` |

## 5. Kết quả kiểm chứng

Chạy trên runtime thật (`claude` 2.1.231), không phải mô phỏng:

| Yêu cầu | Kết quả |
|---|---|
| Khởi động: 0 invalid, 0 skipped, 0 warning | **Đạt** — stdout/stderr sạch, `claude doctor` không nêu vấn đề |
| `settings.json` hợp lệ | **Đạt** |
| Chế độ A — tra cứu GitHub chỉ-đọc không hỏi | **Đạt** cho `gh run list`, `gh workflow list`, `gh pr view`, `gh repo view`… |
| Chế độ A — `git push` thường phải hỏi | **Đạt** ở tầng hook (đè được cả luật `allow`) |
| Chế độ B — `git push` thường không hỏi | **Đạt ở tầng hook** (hook im lặng); xem hạn chế mục 6 |
| Lệnh phá huỷ ở chế độ A → DENY | **Đạt** |
| Lệnh phá huỷ ở chế độ B → DENY | **Đạt** — `rm -rf` bị hook chặn ngay trong phiên bypass |
| Ma trận đối kháng | **326/326 PASS**, cả hai chế độ, 0 bypass |

## 6. Hạn chế thật, không che giấu

**`gh api` và `git push` bị chính runtime bắt xác nhận.** Đã kiểm chứng
bằng đối chứng: kể cả khi có luật `allow` khớp (`Bash(gh api:*)`,
`Bash(gh api*)`, `Bash(git push:*)`) **và gỡ bỏ hoàn toàn hook**, hai lệnh
này vẫn bị chặn; trong khi `Bash(gh run list:*)` cùng cú pháp thì chạy
bình thường. Đây là cổng chặn có sẵn của Claude Code, **không phải**
false positive của hồ sơ quyền này và không sửa được từ `settings.json`
hay hook.

- Ở phiên tương tác: bấm duyệt một lần là xong.
- Ở phiên không tương tác: fail-closed.
- Cách đi vòng hợp lệ cho việc tra cứu: dùng lệnh con `gh` tương đương
  (`gh run list`, `gh workflow list`, `gh pr view --json`, `gh repo view
  --json`) — đã được `allow` và đã kiểm chứng chạy tự chủ.

**Chưa kiểm chứng đầu-cuối:** chế độ B ở phiên tương tác thật trên laptop.
Trong phiên headless, `--permission-mode bypassPermissions` không thực sự
cấp quyền cho lệnh chưa có luật `allow`, và phiên hiện tại bị chặn không
cho khởi chạy tiến trình con `--dangerously-skip-permissions`. Bằng chứng
hiện có là ở tầng hook (326/326 với `permission_mode=bypassPermissions`)
cộng với việc `settings.json` không còn luật `ask` dạng `Bash(...)` — hai
điều kiện đủ để không còn gì trong hồ sơ này gây hỏi khi push ở chế độ B.
Cần một lần xác nhận thủ công tại laptop để đóng hoàn toàn mục này.

## 7. Ghi chú bảo trì

Luật `allow` `Bash(gh api:*)` **rộng hơn** tập chỉ-đọc một cách có chủ ý,
và chỉ an toàn nhờ tầng 1/2 của hook soi lại từng lệnh khớp và đè lên nó
(`-X DELETE` → deny, `-X POST` → ask). **Nới lỏng bộ phân loại trong hook
đồng nghĩa với nới lỏng luật `allow` đó** — sửa cả hai, hoặc không sửa gì.
