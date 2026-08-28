# Rà soát bảo mật độc lập hồ sơ quyền (2026-08-28)

Tiếp nối `permission-audit-2026-08-28.md`. Coi `.claude/settings.json` là
**ranh giới an ninh**, không phải cấu hình. Hai người rà soát độc lập, không
dùng quota Claude gốc.

## 1. Ai rà soát — và một thay đổi phải báo

| Vai | Dự kiến | Thực tế | Ghi chú |
|---|---|---|---|
| Cross-family | **Codex CLI** | ❌ **TỪ CHỐI** | Codex `0.149.0-alpha.4.1` có sẵn (ngoài `PATH`, ở `%LOCALAPPDATA%\OpenAI\Codex\bin\…`). Nó chạy, khảo sát thật (tự sinh payload `-EncodedCommand` base64 trong sandbox `read-only`), rồi trả về: *"This content was flagged for possible cybersecurity risk… join the Trusted Access for Cyber program"*. Đây là **từ chối theo chính sách**, không phải thiếu công cụ |
| Cross-family (thay thế) | — | ✅ **GPT-OSS 120B** qua Antigravity | Khác họ model thật (dòng OpenAI). Không phải "âm thầm quay về Opus gốc" |
| Bảo mật/rủi ro cao | Antigravity Claude Opus | ✅ **Claude Opus 4.6 (Thinking)** qua Antigravity | Ưu tiên 1 của yêu cầu, quota Google AI Pro |

**Không dùng một giọt quota Claude gốc nào cho hai lượt rà soát.** Quota
Antigravity lúc bắt đầu: Gemini 98%/99%, Claude&GPT 98%/93%,
`paid_overage_risk_zero: true`.

Hai lỗi giao diện CLI đã gặp và vượt qua: `agy --print` (flag kiểu Go) **ngốn
luôn `--model` làm giá trị** — phải viết `--print="<prompt>"`; và `--effort`
**không được hỗ trợ** cho `claude-opus-4-6-thinking`.

## 2. Kết quả

| Nguồn | Findings | Sau khi tôi tự tái hiện |
|---|---|---|
| Tôi (matrix tĩnh, 109 ca) | 12 | 12 thật |
| Antigravity Claude Opus 4.6 | 16 (6 CRIT, 7 HIGH, 3 MED) | **16 thật** |
| GPT-OSS 120B | 5 (2 CRIT, 3 HIGH) | **3 thật, 2 KHÔNG tái hiện** |

### Hai finding của GPT-OSS bị loại sau khi tái hiện

- **F5 `npm run malicious`** — GPT-OSS tưởng `Bash(npm run)` là luật *prefix*.
  Nó là luật **chính xác**, nên `npm run evil` → `PROMPT`, không phải `ALLOW`.
  **Dương tính giả.**
- **F3 `cat $(git rev-parse --show-toplevel)/.env`** — chuỗi lệnh **có** chứa
  `.env` nên `Bash(cat *.env*)` khớp và chặn. Ví dụ cụ thể **không** bypass
  (dù lớp lỗi chung thì thật — xem OPUS-6). Cách sửa GPT-OSS đề xuất cũng sai
  hướng.

Đúng như yêu cầu: **không tin finding nào mà chưa tự tái hiện.**

## 3. Ba khoảng trống hệ thống (Opus phát hiện, tôi xác nhận bằng thực nghiệm)

Tất cả đã **chạy thật** trên máy này, payload chỉ dùng `echo`, trong
`%TEMP%\fanfic-review`:

| Cơ chế | Kiểm chứng | Kết quả |
|---|---|---|
| `awk 'BEGIN{system("…")}'` | `awk 'BEGIN{system("echo AWK_SYSTEM_EXECUTES")}'` | **thực thi** |
| Thay thế lệnh `$(…)` | `echo "SUBST_RESULT=$(echo INNER_RAN)"` | **thực thi lệnh trong** |
| `sed 'e'` | `echo "echo SED_E_EXECUTES" \| sed 'e'` | **thực thi** (sed của Git-for-Windows CÓ lệnh `e`) |
| `xargs` | `echo XARGS_INNER_RAN \| xargs echo` | **thực thi lệnh trong** |
| `find -delete` | tạo `probe_del.tmp` rồi `find -delete` | **tệp bị xoá thật** |
| `find -exec` | `find … -exec echo …` | được chấp nhận |
| `sed -i` | `sed -i 's/a/b/'` trên tệp tạm | **ghi tại chỗ thật** |
| `curl --json` | `curl 8.21.0`, `--json` có trong `--help all` | **có hỗ trợ** |

**Nguyên nhân gốc — và đây là điều đáng nhớ nhất của cả đợt này:**

1. **Các luật `Bash(<tool>:*)` của tôi đã VÔ HIỆU HOÁ chính lớp kiểm tra cờ
   sẵn có của Claude Code.** `find`, `sed`, `xargs`, `jq`, `grep` vốn đã được
   tự-cho-qua **kèm kiểm tra cờ** (built-in chặn `-delete`/`-exec`, và chỉ
   nhận biểu thức `sed` chỉ-đọc). Thêm `Bash(find:*)` biến kiểm tra đó thành
   "cho qua tất". Cách sửa đúng là **xoá luật**, không phải viết thêm luật
   để đấu pattern với chính nó.
2. **`$(…)`, backtick và `>` không phải biên giới đoạn lệnh.** Lệnh bị chặn
   nằm trong `$( )` của một lệnh được phép sẽ **không bao giờ** được kiểm tra.
3. **Bash không đi qua cổng `ask` của Edit/Write.**
   `Edit(.claude/settings.json)` chỉ gác *công cụ* Edit; `cp`/`mv`/`sed -i`/
   `echo >` sửa được cùng tệp đó mà không kích hoạt gì. Ghi được vào
   `settings.json` nghĩa là **xoá sạch ranh giới an ninh**.

## 4. Đã sửa

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| `allow` | 141 | **77** (−64) |
| `ask` | 32 | **32** (không đổi) |
| `deny` | 130 | **486** (+356) |
| Luật deny bị **xoá** | — | **0** (kiểm bằng phép trừ tập hợp) |
| Bypass trong matrix 109 ca | 12 | **0** |
| Finding của reviewer còn hở | 40 | **0** |
| Lệnh thường ngày bị hỏng | — | **0** / 25 |

Cách sửa theo nhóm:

- **Xoá 64 luật allow**: các tool exec được (`awk`, `sed`, `find`, `xargs`),
  ghi tệp tuỳ ý (`tee`, `chmod`), `curl:*` trần, và **toàn bộ** luật trùng với
  danh sách tự-cho-qua sẵn có (`ls`/`cat`/`head`/`grep`/`git status`/
  `gh pr view`/…). Đây là **đảo ngược** quyết định "giữ lại cho chắc" ở lượt
  trước — lý do cũ sai, vì giữ lại chính là thứ đè mất lớp kiểm tra cờ.
- `Bash(git reflog:*)` → `git reflog show:*` (khoá `git reflog delete`).
- **Chặn đọc credential qua tool khác `cat`**: 12 tool × 6 mẫu tệp × 2 dạng.
- **Chặn cờ exec**: `find*-exec*`, `find*-delete*`, `*awk*system(*`,
  `sed*-i*`, `*sed 'e'*`.
- **Chặn ghi Bash vào đường dẫn được bảo vệ**: `.claude/`,
  `.github/workflows/`, `deploy/render*`, `web/wrangler*`, **và**
  `package.json`/`package-lock.json`/`requirements.txt` — nhóm cuối phát sinh
  từ chính finding **dương tính giả** của GPT-OSS: sửa `package.json` rồi gọi
  một script *đã được phép* (`npm run lint`) là chuỗi tấn công thật.
  Mẫu dùng `*>*<tên tệp>*` để bắt mọi tiền tố đường dẫn (`web/package.json`).
- **Chặn laundering qua `$()`/backtick/`${}`** cho 31 lệnh trong nguy hiểm.
- **`curl`**: chặn `--json`, `-o`/`-O`/`--output`/`--remote-name`. Các biến
  thể **gộp cờ** (`-sd`, `-sF`, `-sT`, `-sXPOST`, `-fsXDELETE`) được đóng
  **về mặt cấu trúc** khi bỏ `Bash(curl:*)`: luật prefix đòi dấu cách, nên
  `curl -sd …` không khớp `Bash(curl -s:*)` → rơi về hỏi. Tốt hơn hẳn cách
  đuổi theo từng pattern.
- **`Bash(*xargs*)` chặn hẳn**: xargs tồn tại chỉ để chạy lệnh khác.

## 5. Giới hạn còn lại — nói thẳng

- **`$()` không thể đóng hoàn toàn** bằng luật pattern. Đã chặn 31 lệnh trong
  nguy hiểm nhất; một lệnh khác lồng trong `$()` vẫn lọt. Đóng hẳn thì phải
  chặn *mọi* `$()`, và như vậy sẽ phá phần lớn công việc thường ngày.
- **Che tên tệp** (`cat "$HOME/.e""nv"`) vẫn qua được lớp chặn theo tên tệp.
  Lớp này là **phòng thủ nhiều tầng, không phải ranh giới**.
- **Bash đọc được mọi tệp người dùng đọc được.** Đây là bản chất, không phải
  lỗi cấu hình.
- **Matrix của tôi là bản XẤP XỈ** engine thật của Claude Code. Vì hồ sơ này
  chưa được nạp trong phiên hiện tại (worktree không có nó lúc phiên bắt
  đầu), **không thể tái hiện trực tiếp trên engine thật** — chỉ kiểm chứng
  được *khả năng của công cụ* (mục 3, đã làm thật) và *ngữ nghĩa luật* (tĩnh).
  4 ca cuối cùng ban đầu "hở" chỉ vì model của tôi rơi về xử lý built-in;
  đã đóng bằng deny (deny ưu tiên cao nhất) nên đúng dưới mọi cách hiểu.
- `npm ci` vẫn chạy script lifecycle của package trong lockfile — **rủi ro
  đã chấp nhận**, vì đó là bản chất của việc phục hồi dependency.

## 6. Bất biến vẫn giữ

- `disableBypassPermissionsMode: "disable"` — không đổi. Không thể bật
  bypassPermissions cho dự án này.
- `defaultMode: "acceptEdits"` — không đổi.
- Không luật deny nào bị xoá hay nới.
- Không có allow interpreter diện rộng nào.
- Deploy/push/merge/`gh api`/`cf:deploy` vẫn ở `ask`.
- 25/25 lệnh phát triển thường ngày vẫn tự chạy.

## 7. Nghiệm thu

```
schema (schemastore draft-07, ajv)      : valid
matrix 109 ca                           : PASS (0 bypass, 0 hỏng)
matrix cuối 65 ca theo finding reviewer : PASS (40/40 chặn, 25/25 dùng được)
backend  server/tests                   : 3263 OK
web typecheck                           : sạch
web lint                                : 0 lỗi (2 cảnh báo có sẵn)
web tests                               : 834 pass / 0 fail / 6 skip
desktop tests                           : 372 OK (chạy ở lượt trước, mã không đổi)
```
