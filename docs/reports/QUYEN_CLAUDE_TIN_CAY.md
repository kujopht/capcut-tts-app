# Ma sát quyền của Claude Code — nguyên nhân THẬT và cách sửa

*2026-09-10 · nhánh `feat/v06-project-memory`*

Báo cáo này trả lời một câu hỏi: **vì sao việc soi kho vô hại vẫn đòi
người bấm duyệt, kể cả sau khi hồ sơ quyền đã được nới đúng chỗ?**

Câu trả lời không phải "một luật viết sai". Có hai cơ chế, và cả hai đều
được đo bằng phiên `claude -p` thật, không suy từ tài liệu.

---

## 1. Hai cơ chế, đo được

### 1a. Thư mục CHƯA ĐƯỢC TIN làm cả hồ sơ kho biến mất

Chính Claude Code nói ra, nguyên văn:

```
Ignoring 241 permissions.allow entries from .claude/settings.json:
this workspace has not been trusted. Run Claude Code interactively here
once and accept the trust dialog, or set
projects["<đường>"].hasTrustDialogAccepted: true in
C:\Users\<u>\.claude.json.
```

Ở một thư mục như thế, **cả** `.claude/settings.json` của kho (241 allow /
513 deny) **và** hook `PreToolUse` của kho (`guard_indirect_exec.py`, 43 KB
logic ranh giới) đều bị bỏ qua. Chỉ còn tầng người dùng và lớp phân loại
nội tại.

Và "thư mục chưa được tin" đúng là nơi làm việc tự động: **mỗi worktree
Router V4 vừa dựng là một thư mục mới.**

Đo trong một hộp cát chưa được tin, **trước** khi sửa — 28 lệnh nguy hiểm,
**12 lệnh CHẠY THẬT**:

| Lệnh | Trước khi sửa | Đáng ra |
|---|---|---|
| `cat khoa.pem` | **CHẠY** | DENY |
| `tail -3 khoa.pem` | **CHẠY** | DENY |
| `rm -f khoa.pem` | **CHẠY** | DENY |
| `sed -i 's/a/b/' README.md` | **CHẠY** | DENY |
| `find . -name "*.py" -delete` | **CHẠY** (xoá thật) | DENY |
| `python -c "print(1)"` | **CHẠY** | DENY (hook) |
| `awk 'BEGIN{system(...)}'` | **CHẠY** | DENY (hook) |
| `reg add HKCU\... /f` | **CHẠY** | DENY |
| `cmdkey /list` | **CHẠY** | DENY |
| `npx wrangler r2 bucket delete x` | **CHẠY** | DENY |
| `npm run cf:deploy:production` | **CHẠY** | DENY |
| `ssh ... "sudo systemctl restart fanfic-farmer"` | **CHẠY** | DENY |

`cat .env` và `git reset --hard` **vẫn** bị chặn — vì hai cái đó cũng có
luật ở tầng NGƯỜI DÙNG. Đó là mẩu bằng chứng khoá lại chẩn đoán: những gì
sống sót đúng là những gì tầng người dùng phủ.

### 1b. `Read()` deny khớp theo ĐƯỜNG DẪN được NHẮC TÊN, bất kể động từ

Claude Code phân giải những đường dẫn mà một lệnh Bash nhắc tên rồi đối
chiếu với các luật `Read(...)`. Đo được (hộp cát chưa được tin):

```
git check-ignore -v README.md            -> ALLOW
git check-ignore -v scripts/mau.py       -> ALLOW
git check-ignore -v .env                 -> DENIED
git check-ignore -v khoa.pem             -> DENIED
git check-ignore -v cai_dat/credentials.json -> DENIED
ls -la .env                              -> DENIED
stat .env                                -> DENIED
test -f .env                             -> DENIED   (đọc 0 byte!)
git log --oneline -- .env                -> DENIED
git status --porcelain --ignored          -> ALLOW
```

`test -f` không đọc một byte nội dung nào mà vẫn bị chặn. Và vì
`deny` > `allow`, một luật `Bash(git check-ignore:*)` trong `allow`
**không cứu được**.

Đây chính là cơ chế sinh ra thông điệp đã báo — *"một luật `Read()` deny
đang được cấu hình"*. Khi một `cd` làm đường dẫn không phân giải được
TĨNH, nó không chứng minh được đường đó KHÔNG bị deny, nên nó hạ xuống
**ASK** thay vì DENY. Đó là *"sau một `cd` sẽ tìm trong một thư mục không
xác định được"*.

---

## 2. Cách sửa — ba lớp, không phải một quy ước

Yêu cầu nói rõ: **không được chỉ dặn model "đừng dùng `cd && grep`"**. Một
rào dựa vào việc model ngoan thì không phải rào. Nên cả ba lớp dưới đây
đều là cơ chế.

### Lớp A — tầng an toàn chuyển sang HỒ SƠ NGƯỜI DÙNG

`~/.claude/settings.json` **luôn** có hiệu lực: không phụ thuộc nhánh
git, không phụ thuộc trạng thái tin cậy, không phụ thuộc worktree.

`scripts/kiem_quyen.py` giữ định nghĩa của hai nửa dưới dạng **dữ liệu
Python** (nên bài kiểm `import` được đúng thứ đã áp dụng — không có bản
JSON thứ hai để lệch nhau):

* **99 luật `allow`** — `tim.py`, `git` chỉ-đọc, `pytest`/`compileall`/
  `node --check`, `git worktree add`/`checkout -b`/`add`/`commit`, script
  build của kho.
* **422 luật `deny`** — bí mật (đường dẫn *và* chuỗi lệnh), phá huỷ hệ
  tệp/git, hệ thống/an ninh/registry/Defender/firewall, sản xuất
  (AWS/Appwrite/R2/Drive/deploy), thi hành gián tiếp.
* **hook được đăng ký ở tầng người dùng**, trỏ vào một bản sao ở
  `~/.claude/hooks/guard_indirect_exec.py`. Đây là nửa mà
  `${CLAUDE_PROJECT_DIR}` không với tới được. Có bài kiểm đòi hai bản
  **byte-identical**, nên lệch nhau là bộ kiểm đỏ.

**Cố ý KHÔNG thêm** `Bash(grep:*)`, `Bash(find:*)`, `Bash(sed:*)`,
`Bash(cat:*)`, … vào tầng người dùng. Đo được 2026-08-28: viết một luật
như thế vào `allow` **thay** phép cho-phép-có-kiểm-cờ sẵn có của Claude
Code bằng một phép vô điều kiện, và nó mở lại `find -delete`, `find -exec`,
`sed -i` thật. Có bài kiểm khoá điều này lại.

### Lớp B — `scripts/tim.py`: một cửa TÌM/ĐỌC chứng minh được phạm vi

Không cần `cd`. Không dùng shell. Không nhắc tên một đường bí mật nào
trong `argv` — nên nó **không chạm vào cơ chế 1b một lần nào**.

| Tính chất | Cách bảo đảm |
|---|---|
| `cd` vô nghĩa | gốc kho suy từ `Path(__file__).resolve().parents[1]`, không từ `cwd`. Có bài kiểm đòi `Path.cwd()` chỉ được dùng để IN. |
| bí mật không vào tầm nhìn | danh sách tệp từ `git ls-files --cached --others --exclude-standard` → mọi thứ `.gitignore` che (`.env`, `.venv/`, `.router/`, `dist-*/`) không bao giờ được đọc |
| bí mật lỡ commit vẫn không đọc được | 44 mẫu tên + 11 đoạn đường loại trừ, **trên** lớp `.gitignore` |
| không ra ngoài kho | `resolve()` rồi kiểm chứa trong `GOC`; ngoài → exit 2 |
| không in ra credential | 16 mẫu lọc trên đường ra, kể cả với tệp được phép |
| loại trừ KHÔNG lặng lẽ | mỗi lần tìm in `bỏ qua: N loại-trừ`; `--kiem` in cả chính sách |

Nhờ vậy **một** luật tiền tố — `Bash(python scripts/tim.py:*)` — là an
toàn, và nó không cần luật `deny` nào đi kèm để bù.

`git grep` là cửa thứ hai, cùng tính chất (chỉ thấy tệp git theo dõi) và
**không cần tệp nào được cài** — nên nó dùng được ngay ở một worktree dựng
từ một nhánh chưa có `tim.py`.

### Lớp C — `--tin-cay`: đánh dấu worktree mới, có hai chốt

```bash
python scripts/kiem_quyen.py --tin-cay <đường worktree>
```

Đúng cách mà Claude Code chỉ ra. Hai chốt, vì tin cậy là một quyết định
an ninh:

1. đường phải nằm dưới một gốc phát triển đã biết (`GOC_PHAT_TRIEN`);
2. hồ sơ tại đó không được mang luật `allow` đáng ngờ — tin cậy một thư
   mục là **kích hoạt** `settings.json` nằm trong đó.

---

## 3. Hai lỗi THẬT tìm ra khi sửa

Cả hai là **báo động sai**, và một báo động sai không phải chuyện nhỏ: nó
dạy người dùng đi vòng qua rào, và cái giá đó lớn hơn cái được của lần
chặn oan.

### 3a. `-C` bị đọc thành `-c` (hook)

```
python scripts/tim.py "KHONG" scripts --glob "*.py" -i -C 1
-> Blocked: inline code execution (python -c)
```

Hai chỗ sai, cả hai trong một vòng lặp:

* token bị `.lower()` trước khi so, nên `-C` (một cờ **của script**)
  thành `-c`. `-C` không phải cờ của python. `perl -E` là inline thật và
  đã có sẵn trong bảng dưới dạng `-E`, nên không cần hạ chữ.
* vòng quét chạy tới hết chuỗi. Một thông dịch ngừng đọc cờ **của chính
  nó** ở đối số đầu tiên không phải cờ; mọi thứ sau đường script thuộc về
  script.

Đã sửa, và cụm cờ thật (`bash -lc`, `node -pe`) vẫn bị chặn.

### 3b. Glob không phân biệt được MẪU với ĐƯỜNG DẪN

```
git check-ignore -v .env                    <- bị Bash(* *.env) chặn
grep -c '\* \*\.env' .claude/settings.json  <- bị Bash(grep * *.env*) chặn
```

Cái thứ hai là **tìm chuỗi ".env"** trong một tệp hoàn toàn bình thường:
toán hạng đầu của `grep`/`sed`/`awk` là một MẪU, không phải đường dẫn.

Ranh giới đúng giữa hai lớp, và giờ nó được áp dụng nhất quán:

> **glob** lo thứ glob diễn đạt CHÍNH XÁC (động từ + đường dẫn cố định).
> **hook** lo thứ cần biết cấu trúc lệnh (tách động từ khỏi toán hạng).

Nên: `LUAT_QUA_RONG` khai 186 hình dạng luật phải gỡ (6 neo-theo-đường +
180 neo-động-từ-mẫu-trước); trong hồ sơ KHO có **53** cái đang thật sự
hiện diện và chúng đã bị gỡ (`deny` 512 → 459), tầng người dùng còn 0. Thêm
`guard_indirect_exec.secret_file_read()` — hàm này tách được động từ khỏi
toán hạng, bỏ qua toán hạng mẫu, và **bịt luôn cái lỗ không glob nào bịt
được**:

```
cd /tmp && cat .env   -> deny: credential file read (cat .env)
```

`LUAT_QUA_RONG` trong `kiem_quyen.py` giữ danh sách luật bị gỡ **kèm lý
do**, và `--ap-dung` gỡ chúng ở cả hai tầng — nên không ai lặng lẽ thêm
lại.

### 3c. Bản mô hình chia đoạn khác bản thật

`expand()` tách thân `$(...)`/backtick nhưng **không** tách `&&`. Bản đầu
của cả `kiem_quyen.quyet_dinh()` và bài kiểm gọi `evaluate()` trên nguyên
chuỗi `cd /tmp && cat .env`, chỉ thấy nhị phân `cd`, và kết luận "không
chặn" — trong khi hook thật chặn, vì `main()` còn chạy
`SEGMENT_SPLIT.split(chunk)` một tầng nữa.

Một bản mô hình chia đoạn khác bản thật sẽ báo an toàn ở đúng chỗ hệ thống
thật đang chặn. Cả hai chỗ giờ chia đoạn giống hệt `main()`.

---

## 4. Kết quả đo

### Ma trận tĩnh — `python scripts/kiem_quyen.py --kiem`

| | chưa được tin | đã được tin |
|---|---|---|
| AN TOÀN, được bảo đảm (phải `allow`) | 31/31 | 31/31 |
| AN TOÀN, dựa lớp nền (không được `deny`) | 12/12 | 12/12 |
| NGUY HIỂM (phải là `deny`) | 41/41 | 41/41 |
| **tổng** | **84/84** | **84/84** |

Bar của nửa nguy hiểm là **`deny`**, không phải "khác `allow`" — vì một
lệnh không khớp luật nào rơi xuống lớp nội tại, và lớp đó **cho chạy**
phần lớn. Đó chính là cách 12 lệnh trên chạy thật.

### Ma trận THẬT — phiên `claude -p` trong hộp cát CHƯA ĐƯỢC TIN

Nửa nguy hiểm — **cùng một bộ 28 lệnh**, cùng một hộp cát:

| | trước | sau |
|---|---|---|
| CHẠY ĐƯỢC | **12** | **0** |
| bị chặn | 16 | 28 |

Nửa an toàn — hai bộ lệnh **không giống nhau** (bộ sau thêm 7 lệnh, gồm cả
hai lệnh vừa sửa báo động sai), nên đọc theo từng lệnh chứ không theo tỉ
lệ:

| Lệnh | trước | sau |
|---|---|---|
| `python scripts/tim.py "x" scripts --glob "*.py" -i -C 1` | **GATED** (báo động sai 3a) | **ALLOW** |
| 15 lệnh còn lại của bộ trước | ALLOW | ALLOW |
| 7 lệnh thêm vào bộ sau | — | ALLOW |
| `git check-ignore -v .env` | GATED | GATED — cơ chế 1b, mục 5 |
| `git check-ignore -v cai_dat/credentials.json` | — | GATED — cơ chế 1b, mục 5 |

Tổng: 16/18 → **23/25**, và hai lệnh còn bị chặn là hạn chế đã ghi ở mục
5, không phải hồi quy.

### Lớp hook — gọi đúng như Claude Code gọi

32/32, gồm cả `cd /tmp && cat .env` → deny và
`python scripts/tim.py ... -C 1` → im lặng.

### Bộ kiểm

* `.claude/hooks/test_guard_indirect_exec.py` — **560/560**
* `scripts/tests/test_claude_permission_policy.py` — **53 bài / 793
  subtest** (thêm 3 lớp: `TestTangNguoiDungTuDung`, `TestCuaTimAnToan`,
  `TestHookLaLopCHINH_XAC`)
* hồi quy rộng — **333 bài / 1042 subtest**

---

## 5. Hạn chế đã biết, giữ có chủ đích

**Một lệnh Bash NHẮC TÊN một đường bị `Read()` deny thì bị chặn, dù nó
không đọc nội dung.** `ls -la .env`, `stat .env`, `test -f .env`,
`git check-ignore -v .env`, `git log -- .env`. Đây là cơ chế của Claude
Code, `allow` không đè được, và cách duy nhất để sửa là gỡ
`Read(**/.env)` — tức mở đúng thứ phải đóng. Đường đi vòng thật:

```bash
git status --porcelain --ignored      # đường nào bị bỏ qua
python scripts/tim.py --kiem          # tệp nào bị loại trừ
```

Danh sách này là **dữ liệu** (`KHONG_SUA_DUOC` trong `kiem_quyen.py`),
không phải một ghi chú, và `--kiem` in số lượng — để nó không thành một
điều bất ngờ lúc 2 giờ sáng.

**Khoá riêng vẫn neo THÔ.** `Bash(*.pem*)` và họ của nó (`*.ppk*`,
`*.p12*`, `*.pfx*`, `*.kdbx*`) khớp cả chuỗi lệnh, nên một lệnh chỉ nhắc
phần mở rộng cũng bị chặn. Với `.env` thì cách neo-thô đã được gỡ; với
khoá riêng thì **không** — cái giá của một lần lọt là một khoá production
bị đọc, còn cái giá của lần chặn oan là đổi mẫu tìm từ `*.pem` thành
`pem`.

**`tim.py` chưa có trên `main`.** Một worktree dựng từ `main` chưa có tệp
đó; dùng `git grep` (đã ở tầng người dùng, không cần cài gì). Merge nhánh
này vào `main` là bước còn lại để `tim.py` có mặt ở mọi worktree.

---

## 6. Nạp lại: có cần khởi động lại Claude Code?

Đo được, không suy:

| Thay đổi | Có hiệu lực khi nào | Cách đo |
|---|---|---|
| `~/.claude/settings.json` — `permissions` | **NGAY, trong phiên đang chạy** | Sau khi ghi tầng cấm, chạy `echo "Set-Acl …"` trong **chính phiên đang mở** → *"Permission to use Bash … has been denied"*. Luật `Bash(*Set-Acl*)` được viết vài phút trước đó và chưa khởi động lại gì. |
| `~/.claude/hooks/guard_indirect_exec.py` — nội dung | **ngay lần gọi sau** | hook là một tiến trình con, đọc lại tệp mỗi lần gọi; bản sửa `-C` có hiệu lực ở lần gọi tiếp theo |
| đăng ký hook trong `settings.json` | **NGAY** (cùng cơ chế đọc lại `permissions`) | hook bắt đầu chặn ở hộp cát ngay sau khi `--ap-dung` ghi phần đăng ký |
| `~/.claude.json` → `hasTrustDialogAccepted` | **phiên MỚI** — chưa đo được chiều ngược lại | trạng thái tin cậy được đọc lúc khởi tạo phiên |
| `<kho>/.claude/settings.json` | như tầng người dùng, **và chỉ khi thư mục ĐƯỢC TIN** | |

**Nên: KHÔNG cần khởi động lại để nhận tầng luật mới.** Đây là điểm đã
sửa so với phỏng đoán ban đầu của báo cáo này: `permissions` được đọc lại
trong phiên, không chỉ lúc khởi động. Chỉ **trạng thái tin cậy** là thứ
cần một phiên mới — nên sau `--tin-cay` một worktree, phiên trong worktree
đó phải mở lại để hồ sơ kho được nạp.

*Ghi chú về `Bash(*Set-Acl*)`:* phép đo trên cũng cho thấy luật đó chặn cả
một `echo` vô hại chỉ vì chuỗi xuất hiện trong lệnh — cùng lớp báo động
sai với mục 3b. Ở tầng hệ thống/an ninh thì giữ neo thô là có chủ đích, và
bề mặt chặn oan (`echo Set-Acl`) không đáng kể.

---

## 7. Tệp đã đổi

| Tệp | Việc |
|---|---|
| `scripts/tim.py` | **MỚI** — cửa TÌM/ĐỌC an toàn |
| `scripts/kiem_quyen.py` | **MỚI** — định nghĩa + áp dụng + kiểm tầng quyền, `--tin-cay` |
| `.claude/hooks/guard_indirect_exec.py` | sửa `-C`→`-c`; thêm `secret_file_read()` + `PATTERN_FIRST_OPERAND` |
| `.claude/settings.json` | gỡ 53 luật `deny` quá rộng, 512 → 459 (qua `--ap-dung`) |
| `scripts/tests/test_claude_permission_policy.py` | +3 lớp, +2 bài; `_quyet()` xét cả hook |
| `.gitignore` | bỏ qua `*.truoc-kiem-quyen` |
| `~/.claude/settings.json` | +99 allow, +422 deny, +đăng ký hook (ngoài kho) |
| `~/.claude/hooks/guard_indirect_exec.py` | **MỚI** — bản sao, có bài kiểm đòi khớp byte |
| `~/.claude.json` | `hasTrustDialogAccepted: true` cho worktree này |

Bản lưu trước khi ghi: `*.truoc-kiem-quyen` cạnh mỗi tệp.
