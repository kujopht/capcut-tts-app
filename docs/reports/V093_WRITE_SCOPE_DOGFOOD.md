# V0.9.3 — DOGFOOD THẬT: TỪ "ok triển khai" TỚI MÃ CHẠY ĐƯỢC

Nhánh `feat/v093-write-scope-propagation`. Dự án: `RouterDogfood02`, sổ
CHÍNH TẮC, một người ghi duy nhất.

Báo cáo gốc về khuyết tật lan truyền thẩm quyền: `V093_WRITE_SCOPE.md`.
Tệp này ghi phần còn lại — thứ chỉ lộ ra khi chạy THẬT tới cùng.

## Tóm tắt

Sửa xong phạm vi ghi **chưa** làm cho câu "ok triển khai" chạy được. Phía
sau nó còn **bốn** khuyết tật nữa, mỗi cái chặn đứng ở một tầng khác nhau,
và không cái nào lộ ra cho tới khi cái trước được gỡ. Đây là hồ sơ của cả
năm, theo đúng thứ tự gặp.

| # | Chữ ký hỏng | Tầng sở hữu | Trạng thái |
|---|---|---|---|
| 1 | `type: analysis` + `ALLOWED_SCOPE: (không)` | lan truyền thẩm quyền | ĐÃ SỬA (V093_WRITE_SCOPE.md) |
| 2 | `git rev-parse HEAD thất bại` | dự án mới không có mốc git | ĐÃ SỬA |
| 3 | `tool_permission_denied`, 27s, `changes=[]` | phong bì quảng cáo quyền runtime không có | ĐÃ SỬA |
| 4 | sản phẩm nằm trong `repair/replan/` | đọc văn xuôi thành đường dẫn | ĐÃ SỬA |
| 5 | `gate_scope` / `gate_contract_scope` trên việc làm ĐÚNG | ba tầng hiểu `.` khác nhau | ĐÃ SỬA |
| 6 | "Sandbox chặn mọi thao tác ghi" | Codex khai `implement` nhưng chạy sandbox CHỈ ĐỌC | ĐÃ SỬA |
| 7 | rào năng lực chưa bao giờ chặn một lần xếp chỗ nào | `isinstance(hd, dict)` LUÔN sai ở chỗ gọi thật | ĐÃ SỬA |
| 8 | hoàn tác để lại thư mục mồ côi | `rmtree` không xoá được `.git/objects` CHỈ ĐỌC | ĐÃ SỬA |

**Sáu trong tám khuyết tật là cùng một hình dạng**: hai (hoặc ba) chỗ cùng
giữ một sự thật, và chúng nói ngược nhau. Khuyết tật #8 là hồi quy do CHÍNH
bản vá #2 gây ra, và bộ hồi quy bắt được.

## 6. Codex khai một năng lực nó không có

Việc Todo bị xếp sang `CODEX01`. Sau 226 giây:

> Sandbox hệ thống chặn mọi thao tác ghi và không cho phép yêu cầu nâng
> quyền. … workspace đang ở chế độ read-only.

`CodexAdapter` gọi `codex exec --skip-git-repo-check -m <model> --color
never -` — KHÔNG cờ sandbox, và `codex exec` mặc định chạy sandbox CHỈ ĐỌC.
Nhưng nó khai `capabilities={"review", "implement"}`.

**Sửa:** rút `implement` (giữ `review` — thế mạnh thật, và review không cần
ghi), cộng `refuses: ["repo_write"]` trong `fabric.json`.

**KHÔNG bật `--sandbox workspace-write`.** Đó là CẤP THÊM quyền ghi cho một
CLI ngoài; nó cần một probe có giới hạn và một lần duyệt của chủ sở hữu, chứ
không phải một dòng lọt vào giữa bản vá phạm vi ghi. `test_04` khoá lại rằng
không cờ nào len vào.

## 7. Rào năng lực CHƯA BAO GIỜ CHẠY

Lượt tiếp theo **vẫn** vào CODEX01, lần này vì phiên còn ấm và luật DÙNG LẠI
chỉ xét phạm vi. Thêm `refuses` vẫn không đổi gì. Vết quyết định không hề có
dòng `năng lực: CẤM`.

Nguyên nhân:

```python
can = NL.nang_luc_viec(hd if isinstance(hd, dict) else {})
```

Chỗ gọi **duy nhất** (`_giao_khong_luoi`) bình `hd = TaskContract.from_dict(…)`
— một ĐỐI TƯỢNG. Nên vế `else` luôn đúng, và hàm trả `()` mọi lần. Rào chưa
bao giờ chặn một lần xếp chỗ nào, kể từ V0.7.

**Nặng hơn phạm vi bản vá này:** cùng rào đó là đường thi hành
`security_review` — thứ giữ cho việc hình dạng bảo mật không rơi vào Codex
(Codex trả kết quả RỖNG cho loại việc đó, bằng chứng 2026-08-28). Nó cũng đã
chết, cũng im lặng y hệt.

Một phép phòng thủ biến rào an toàn thành hàm rỗng là kiểu hỏng tệ nhất: mọi
thứ trông như bình thường, và không có gì để đọc.

---

## 2. Dự án mới không có MỐC GIT

```
BLOCKED: không cấp được cây làm việc: git rev-parse HEAD thất bại:
fatal: ambiguous argument 'HEAD': unknown revision
```

`tao_du_an` (V0.9.2) chạy `git init` TRẦN. Kho không có `HEAD`, và tầng
worktree cần `base_sha` để dựng cây cô lập. Nên **mọi việc GHI trên mọi dự
án Router tự tạo đều chết ngay lúc xin cây làm việc** — ngõ cụt thứ hai của
cùng một dự án mới.

Sâu hơn một lỗi git: toàn bộ mô hình kiểm định của Router là SO VỚI MỘT MỐC
(`base_sha`, `git status` trong worktree). Kho không có commit nào thì không
có mốc để so.

Và `la_kho_git` — hàm mà docstring của chính nó nói tồn tại để bắt lỗi kho
*"ở CỔNG VÀO … chứ không để `git rev-parse HEAD` ném ra giữa đường điều
phối"* — hỏi `--is-inside-work-tree`, câu trả `true` cho kho chưa commit.
Nên đúng thứ nó hứa chặn vẫn lọt, rồi nổ ở tầng dưới bằng một câu git thô.

**Sửa:** `tao_du_an` tạo commit đầu tiên (khung README/.gitignore/docs —
đúng thứ đáng commit); `co_moc_git()` là phép kiểm riêng; engine chặn TRƯỚC
khi xin cây, chỉ với việc CẦN worktree, kèm câu nói được phải làm gì.

**Ranh giới cố ý:** kho NHẬN NUÔI thì Router **không** tự commit hộ. Kho của
người dùng là tài sản của họ; Router chỉ được nói là thiếu mốc (`test_09`).

## 3. Phong bì quảng cáo quyền mà runtime KHÔNG có

Hai lượt agent liên tiếp chết y hệt: `tool_permission_denied`, 27 giây,
`changes=[]`, nhật ký thô rỗng — chỉ còn đúng một dòng của `agy`:

> a tool required the "command" permission that headless mode cannot prompt
> for, so it was auto-denied

Hợp đồng đã nói thẳng *"ĐỪNG chạy lệnh để build/test"*. NGAY DƯỚI đó, phong
bì quyền liệt kê:

```
ĐƯỢC TỰ LÀM, không phải hỏi:
  - run_tests
  - run_lint
  - run_build
```

Agent tin phong bì, gọi một lệnh, và **mất trắng cả lượt**.

`AUTO_OPERATIONS` là danh sách CỐ ĐỊNH để hiển thị, không phản ánh thứ
runtime thật sự làm được. Agent của Router chạy headless (`agy --print`), và
headless tự chối `command`.

**Bằng chứng, không phải giả thuyết:** một probe có giới hạn chạy
`run_native` thật trong một thư mục tạm với `allow_edits=True` + workspace,
prompt nói rõ "không chạy lệnh nào" → **status=SUCCESS, 15.6s, `index.html`
được tạo**. Runtime ghi được; thứ hỏng là lời hứa trong phong bì.

**Sửa:** phong bì thôi liệt kê thao tác cần shell, và nói thẳng phân công —
*agent làm ra tệp, Router chạy kiểm định*. Không nới quyền nào
(`CLAUDE.md` đã trả giá BỐN lần cho bài học đó).

## 4. Văn xuôi bị đọc thành đường dẫn

Câu uỷ quyền thật có cụm *"tự **repair/replan** trong phạm vi cần thiết"*.
Leader chép cụm đó vào mục tiêu; `duong_dan_trong` đọc `repair/replan` thành
một đường dẫn; nó trở thành PHẠM VI GHI của việc.

Agent làm **đúng phạm vi được giao**. Kết quả: cả ứng dụng Todo — 6 tệp,
~30 KB — nằm gọn trong một thư mục tên `repair/replan/`.

```
status=ok  changes=["repair/replan/index.html", "repair/replan/app.js", …]
```

Việc `DONE`. Cổng kiểm định XANH. Mọi tầng nhất quán với nhau — và với một
tiền đề sai. **Không một phép kiểm nào của Router bắt được**, vì không tầng
nào biết sản phẩm phải nằm ở đâu.

**Sửa:** hai đoạn đều là từ chỉ quy trình (`repair/replan`, `test/verify`,
`start/stop`) thì đó là văn xuôi — trừ khi câu viết nó như đường dẫn (`/`
cuối, phần mở rộng) hoặc nó có thật trong kho.

## 5. Ba tầng hiểu dấu chấm khác nhau

V0.9.3 cấp phạm vi "gốc cây làm việc" bằng token `.` (chính `locks.GOC`).
Phép so phạm vi thì làm thế này:

```python
tep == "." or tep.startswith("./")
```

`app.js` ở NGAY GỐC cây không khớp gì cả. Nên một agent làm đúng bị đánh
hỏng:

```
gate_scope         : ghi NGOÀI write_scope: ['README.md','app.js','index.html','style.css']
gate_contract_scope: đổi tệp ngoài allowed_scope: [… 5 tệp, 50 test case …]
```

Phép so đó tồn tại ở **BA** chỗ: `WorktreeManager.verify_scope`,
`pool/validation.kiem_dinh`, và `TaskContract.scope_violations`. Sửa hai chỗ
đầu xong, lượt sau vẫn hỏng — ở chỗ thứ ba.

**Sửa:** một hàm `chuan_hoa_scope()` duy nhất, cả ba tầng gọi chung. Trả
`None` cho gốc cây chứ không phải `[]`: `[]` nghĩa là *không cho ghi gì*,
gốc cây nghĩa là *cho ghi mọi chỗ trong cây* — hai điều ngược nhau, và nhầm
chúng là mở toang một rào. Rào THẬT vẫn là bản thân worktree cô lập:
`git status` chỉ thấy tệp bên trong nó. `forbidden_scope` vẫn THẮNG
(`test_41`).

---

## KẾT QUẢ — chạy THẬT, sổ CHÍNH TẮC

```
việc      routerdogfood02.t2ff8-1   DONE   type=implementation
phạm vi   allowed_scope=['.']  WRITE:FILESYSTEM:.
kết quả   status=ok
tệp       index.html · style.css · script.js · test.html · test.js
```

### Sản phẩm — DÙNG THẬT, không chỉ đọc sổ

Phục vụ repo-local qua `http.server` trên `127.0.0.1` (localStorage không
chạy đúng trên `file://`), bấm thật bằng Chrome + CDP. **20/20 đạt**:

```
giao diện     tiêu đề · ô nhập · nút Add · danh sách
dark mode     BẬT sẵn, nền thật sự tối (đo `getComputedStyle`)
thêm việc     2 việc hiện đúng thứ tự, ô nhập tự trống
hoàn thành    tick -> class `completed` + ghi vào localStorage
TẢI LẠI       2 việc còn nguyên, trạng thái hoàn thành còn nguyên
xoá           còn 1, và BỀN sau khi tải lại
theme         toggle -> sáng, BỀN sau tải lại, bấm lại -> tối
```

### Bộ kiểm của CHÍNH dự án — và một phát hiện

`test.html` chạy **2 lần**, và khác biệt giữa hai lần mới là phát hiện:

```
kho lưu trữ CÒN DỮ LIỆU CŨ : 2 đạt / 3 HỎNG
kho lưu trữ SẠCH           : 5 đạt / 0 hỏng
```

Ứng dụng ĐÚNG. Bộ kiểm agent viết ra thì **phụ thuộc trạng thái trước**: nó
gọi `localStorage.clear()` 500ms sau khi trang tải, trong khi ứng dụng đã đọc
localStorage vào một biến closure lúc `DOMContentLoaded`. Xoá kho lưu trữ
không reset biến đó, nên mọi phép đếm lệch đúng bằng số việc còn sót.

Đây là khuyết tật CHẤT LƯỢNG của sản phẩm worker giao ra, không phải của
Router — nhưng Router đánh `DONE` mà **không chạy bộ kiểm đó lần nào**, vì
cổng `tests` không có lệnh test nào được cấu hình. Đúng điều mục A3 cảnh báo:
*DONE trong sổ Router KHÔNG đủ.*

**Một khẳng định của tôi đã SAI và đã sửa:** bản kiểm đầu tìm chữ `"fail"`
trong kết quả, trong khi báo cáo dùng dấu ❌ — nó XANH vì lý do SAI. Nay đếm
dấu ❌.

### Liên tục — ngữ cảnh Leader MỚI, 7/7

Hỏi *"ê bro cái Todo project làm tới đâu rồi?"* trong một tiến trình mới:

* nêu đúng `routerdogfood02.t2ff8-1` DONE kèm HTML/CSS/JS, Dark Mode,
  localStorage;
* liệt kê việc còn WAITING;
* tóm tắt đúng lịch sử hỏng đêm nay ("4 task từng bị BLOCKED … do sandbox
  read-only và gate scope");
* **0 execution tạo thêm, 0 việc sinh thêm**, không một chữ Fanfic.

### Cổng an toàn — ĐO, không khẳng định suông

```
thao tác chạm production      0
khoá PRODUCTION được cấp      0
việc GATED chờ người duyệt    0   (không việc repo-local nào bị hỏi thừa)
việc fanfic tạo mới đêm nay   0   (76 -> 76, không đụng)
hồi quy đầy đủ                2580 đạt · 4 bỏ qua · 0 hỏng (117 module)
```

## Giới hạn TÀI NGUYÊN gặp phải (không phải khuyết tật)

Một lượt trên `AG02/claude-sonnet-4-6` chạy 596 giây rồi trả:

> Individual quota reached. Please upgrade your subscription to increase your
> limits. Resets in 48h57m19s.

Hạn mức thật của bể Antigravity Claude. **Không mua thêm credit, không bật
overage** (`CLAUDE.md`: cấm tuyệt đối). Router định tuyến sang bể khác, và
lượt thành công cuối cùng chạy trên Gemini.

## Khoảng trống ĐÃ BIẾT, chưa vá (ghi lại, không tự ý mở rộng phạm vi)

1. **Không có đường XẾP LẠI một việc bị chặn vì môi trường.** Sau khi sửa
   xong kho, việc `BLOCKED` nằm im: `mo_khoa_gated` chỉ dành cho lớp GATED,
   `_thu_lai_neu_dang` chỉ chạy cho việc đã có phong bì kết quả, `recover()`
   chỉ cứu việc đang `RUNNING` lúc tắt máy. Phải can thiệp tay. → V1.0 B6
   (`STALE_STATE`).
2. **Không có bước TÍCH HỢP.** Kết quả worker nằm trên nhánh
   `router/<agent>/<task>` trong worktree cô lập và **không bao giờ** về cây
   chính của dự án. Đúng thiết kế an toàn hiện tại ("không tự xoá worktree"),
   nhưng nghĩa là sau một lượt "triển khai" thành công, thư mục dự án của
   người dùng vẫn trống. Gộp là một ĐỘT BIẾN git trên kho người dùng — cần
   một quyết định có phạm vi riêng, không phải một bản vá đêm.
3. **Khởi động lại harness ĐỐT `attempts`.** Một tiến trình điều phối thoát
   giữa lúc agent đang chạy để lại việc ở `RUNNING`; lần `recover()` sau
   tính thêm một lượt. Ba lần là việc chết, dù agent chưa hỏng lần nào.
4. **Cổng `tests` không chạy gì.** Việc có tiêu chí "viết test và verify"
   được đánh `DONE` mà bộ kiểm của chính dự án chưa từng được chạy — và khi
   chạy thì nó đỏ 3/5 (do chính bộ kiểm phụ thuộc trạng thái). Router cần
   một đường CHẠY ĐƯỢC bộ kiểm của dự án, hoặc phải báo `THIEU_BANG_CHUNG`
   thay vì `DONE`. Đây đúng là luật V0.9 đã có ("tiêu chí không buộc được
   vào phép kiểm nào thì KHÔNG mặc nhiên đạt") nhưng không được thi hành cho
   trường hợp này.
5. **Cấp quyền ghi cho Codex** (`--sandbox workspace-write`) — đề xuất, cần
   probe có giới hạn + duyệt của chủ sở hữu. Chưa làm.
