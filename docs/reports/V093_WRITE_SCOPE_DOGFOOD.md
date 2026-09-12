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

**Bốn trong năm khuyết tật là cùng một hình dạng**: hai (hoặc ba) chỗ cùng
giữ một sự thật, và chúng nói ngược nhau.

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
