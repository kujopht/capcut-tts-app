# Rà soát quyền của phiên remote-control (2026-08-28)

Báo cáo chi tiết cho commit `b6541f4`. Mục tiêu: để công việc phát triển
Fanfic thường ngày chạy được gần như không cần trông, mà **không** bật
`bypassPermissions`.

## 1. Phương pháp

Đọc transcript thật của kho này (`~/.claude/projects/*CapCut*/*.jsonl`,
3 phiên): **96 lệnh Bash → 719 đoạn lệnh** sau khi tách `&&`/`||`/`;`/`|`
và **loại bỏ thân heredoc** (nếu không, thân script Python và bảng
markdown bị đếm nhầm thành lệnh).

Mô phỏng đúng cách Claude Code so khớp:

| Dạng luật | Ngữ nghĩa |
|---|---|
| `Bash(foo:*)` | prefix — khớp `foo` hoặc `foo ` + phần còn lại |
| `Bash(foo*)` | glob trên toàn đoạn lệnh |
| `Bash(foo)` | khớp chính xác |

Thứ tự: **deny > ask > allow > (không khớp → hỏi)**. Lệnh ghép được xét
**theo từng đoạn**, không theo cả chuỗi — xác nhận bằng bản ghi denial
`permission-rule` khớp `git push*` nằm giữa chuỗi
`cd … && cp … && git push …`.

Cũng loại các lệnh Claude Code **tự cho qua sẵn** (`ls`, `cat`, `grep`,
`git status`, `gh pr view`, …) để không đếm chúng thành "đã sửa".

## 2. Thực sự bị chặn: 2 / 96

Bằng chứng cứng: trường `toolDenialKind` trong transcript.

| # | Lệnh | Phân loại | Kind | Nguyên nhân gốc |
|---|---|---|---|---|
| 1 | `python -c … && git add && git commit -m "<thông điệp chứa ví dụ force-push>"` | ROUTINE_WRITE | `automode-blocked` | **Không phải luật settings nào.** Classifier auto mode thấy văn bản force-push trong thông điệp commit của chuỗi lệnh ghép. Không luật nào sửa được — cách đúng là dùng `-F <file>` cho thông điệp dài |
| 2 | `cd … && cp … && git push -u origin feat/safe-remote-fanfic-ops` | SENSITIVE | `permission-rule` | Khớp `Bash(git push*)` trong `ask`. Cổng chạy đúng; người dùng từ chối |

**Kết luận:** prompt fatigue chưa bao giờ là vấn đề thật của phiên này.
Vấn đề thật là **cổng báo động sai** và **allow quá rộng**.

Ghi chú quan trọng: `ask` **vẫn tới được điện thoại**. Bằng chứng —
`gh api --method PUT` khớp `Bash(gh api*)` trong `ask` của
`~/.claude/settings.json` mà **vẫn chạy được**, nghĩa là nó đã hỏi và
được chấp thuận. Không có chuyện `ask` tự động thành `deny`.

## 3. Bốn lỗi khớp-chuỗi-con (cùng một lớp lỗi)

| Luật lỗi | Bắt oan cái gì | Phân loại thật | Sửa thành |
|---|---|---|---|
| `Bash(git merge*)` (ask) | `git merge-base` | READ_ONLY | `Bash(git merge)` + `Bash(git merge *)` |
| `Bash(npx wrangler deploy*)` / `Bash(wrangler deploy*)` (ask) | `wrangler deployments list` | READ_ONLY | tách `deploy` / `deploy *` |
| `Bash(git push *-f*)` (deny) — đã sửa ở `bad6832` | nhánh `saf`+`e-fanfic` | — | khớp đúng cờ |
| `Bash(npm run typecheck)` (allow, dạng chính xác) | không khớp vì lệnh thật có `2>&1` | ROUTINE_WRITE | dạng prefix `:*` |

Bảy luật `Bash(powershell.exe -NoProfile -Command Get-*)` **không thể
khớp** bất cứ gì, vì lệnh thật đặt script trong dấu ngoặc kép. Đã xoá chứ
không sửa — xem mục 4.

## 4. Phát hiện nghiêm trọng nhất: allow vô hiệu hoá deny

Lượt trước đã thêm vào `allow`: `python:*`, `python3:*`, `py:*`,
`node:*`, `npm:*`, `npx:*`, `pnpm:*`, `yarn:*`, `pip:*`, `uv:*`,
venv-python trần, và 7 luật PowerShell. **Mỗi luật đó cho thực thi mã
tuỳ ý**, nên toàn bộ 120 luật deny chỉ còn trang trí:

```
python -c "import os; os.system('reg add ...')"
```

đi thẳng qua mọi luật chặn Defender / registry / Task Scheduler / dịch vụ
/ tường lửa / xoá đệ quy.

Đã thay bằng **điểm vào có tên cụ thể**:

- venv: chỉ 3 module thật — `-m unittest:*`, `-m pytest:*`,
  `-m compileall:*`, thêm `-m pip install -r:*`
- npm: đúng các script trong `web/package.json`, dạng prefix.
  `npm install` giữ **chính xác** có chủ ý — dạng prefix sẽ cho cài gói
  tuỳ ý; còn `npm ci:*` an toàn vì `npm ci` bỏ qua tham số gói và chỉ cài
  theo lockfile
- npx: chỉ công cụ cụ thể — `tsc`, `eslint`, `playwright`,
  `opennextjs-cloudflare build`, và các verb chỉ-đọc của wrangler

**Interpreter nay bị chặn bằng cách VẮNG MẶT khỏi allow, không phải bằng
deny.** Lý do quan trọng: luật deny kiểu `Bash(*python.exe -*)` sẽ khớp
luôn `./.venv/Scripts/python.exe -m unittest …` và **giết bộ test
backend**, vì deny thắng allow. Đã thử thêm khối deny đó và bị classifier
chặn — nó chặn đúng.

Hệ quả có chủ ý: `python -c` và `powershell` tuỳ biến giờ **hỏi** — dùng
được khi có người, không âm thầm dùng được khi không ai trông.

## 5. Đếm trước/sau

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `allow` | 145 | 141 (−4) |
| `ask` | 29 | 32 (+3) |
| `deny` | 120 | 130 (+10) |
| Luật deny bị xoá | — | **0** (kiểm bằng phép trừ tập hợp) |
| Trùng lặp | — | không |
| `defaultMode` | `acceptEdits` | `acceptEdits` |
| `disableBypassPermissionsMode` | `disable` | `disable` |
| Wildcard interpreter trong allow | 11 | **0** |
| Luật khớp-chuỗi-con báo động sai | 4 | **0** |

10 luật deny thêm vào bịt đường ghi của `curl` mà luật cũ bỏ sót:
`--request`, `-T`, `--upload-file`, `-F`, `--form`.

## 6. Xác thực schema

```
$ curl -sSL https://www.schemastore.org/claude-code-settings.json -o cc-schema.json
$ npx ajv-cli@5 validate --spec=draft7 --strict=false -s cc-schema.json -d .claude/settings.json
.claude/settings.json valid
```

- URL trong `$schema` (`json.schemastore.org`) trả **301**, phải theo
  redirect sang `www.schemastore.org` — nếu không sẽ nhận HTML thay JSON.
- Phải tắt strict vì **chính schema** dùng keyword phi chuẩn
  `allowTrailingCommas` và format `uri` chưa đăng ký. Lỗi phía schema,
  không phải phía file.
- Schema xác nhận `permissions` là `additionalProperties: false`, và các
  khoá hợp lệ là `allow`/`ask`/`deny`/`defaultMode`/
  `disableBypassPermissionsMode`/`disableAutoMode`/
  `additionalDirectories`. Mọi khoá đang dùng đều hợp lệ.

## 7. Đối chiếu 36 lệnh mẫu (sau khi sửa)

- **allow**: toàn bộ test/build/lint/typecheck của cả 3 bộ; git/gh/curl
  chỉ-đọc; `wrangler whoami`, `wrangler deployments list`;
  `git add`/`commit`/`fetch`/`merge-base`; `gh variable list`,
  `gh secret list`
- **ask**: `git push`, `gh pr merge`, `npm run cf:deploy:production`
- **deny**: force-push, `rm -rf`, `curl --request POST`, `schtasks`,
  `reg add`, `gh secret set`, `wrangler r2 bucket delete`
- **hỏi (không luật)**: `python -c` tuỳ biến, `powershell -Command` tuỳ
  biến — đúng như thiết kế ở mục 4

## 8. Việc cố ý KHÔNG làm

- **Không** xoá các luật allow trùng với danh sách tự-cho-qua sẵn của
  Claude Code. Chúng vô hại về chức năng, và giữ lại là lựa chọn an toàn
  hơn cho mục tiêu "chạy không cần trông" nếu danh sách nội bộ đó khác
  với tài liệu.
- **Không** nới `Bash(gh api*)` khỏi `ask`. Về lý thuyết có thể chặn
  `--method POST/PUT/PATCH/DELETE`, `-f`, `-F`, `--input` bằng deny rồi
  cho GET qua — nhưng dạng `--method=PUT` (dấu bằng) sẽ lọt. Không đổi
  một cổng thật lấy tiện lợi biên.
- **Không** viết test khoá các bất biến này. Bộ so khớp dùng cho rà soát
  là bản **xấp xỉ** nội bộ Claude Code; test dựa trên nó sẽ cho cảm giác
  an toàn giả. Làm được, nhưng phải gọi đúng tên: test đặc tả kỳ vọng,
  không phải test hành vi thật.
- **Không** bật `disableAutoMode` (schema có hỗ trợ) — sẽ phá đúng chế độ
  không-cần-trông mà yêu cầu đang muốn.

## 9. Hiệu lực

Hồ sơ quyền **chỉ nạp lúc bắt đầu phiên** → các thay đổi trên chỉ có tác
dụng sau khi khởi động lại `claude remote-control` (đã được yêu cầu
CHƯA khởi động lại).

Khoảng cách còn lại: file nằm ở nhánh `feat/safe-remote-fanfic-ops`
(5 commit, chưa push), nên worktree do `--spawn worktree` sinh ra vẫn lấy
từ `origin/main` và không thấy nó. Luật cấp người dùng
(`~/.claude/settings.json`) thì luôn có hiệu lực.
