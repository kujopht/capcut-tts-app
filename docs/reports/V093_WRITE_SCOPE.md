# V0.9.3 — LAN TRUYỀN THẨM QUYỀN GHI

Nhánh `feat/v093-write-scope-propagation`, dựng từ `main @ c1c9dda`
(`router-control-center-v0.9.2`). **Chưa merge/tag/push.**

## Hỏng đo được

Trên `RouterDogfood02`, người dùng gõ:

> ok triển khai luôn web todo theo kế hoạch vừa lập. Tự code, chạy test và
> verify từ đầu tới cuối. **Chỉ repo-local, không deploy.** Nếu có lỗi thì tự
> repair/replan trong phạm vi cần thiết rồi tiếp tục.

Leader hiểu ĐÚNG: `y_dinh = WORK`, hành động `delegate_work`. Nhưng gói việc
gửi worker ra:

```
type: analysis
ALLOWED_SCOPE: (không)
resources: READ:FILESYSTEM:HTML/CSS/JS
```

Worker trả `blocked`, và nêu đúng lý do:

> Loại việc được thiết lập là 'analysis', không sở hữu phạm vi ghi nào
> (ALLOWED_SCOPE là (không) — chỉ đọc). Việc triển khai ứng dụng bắt buộc
> phải ghi tệp ra đĩa, trực tiếp kích hoạt STOP_CONDITION.

**Worker làm đúng. Tầng trên cấp sai quyền.**

## Đường đi, và chỗ sự thật chết

```
câu người dùng      "ok triển khai luôn … Tự code …"      ← CÓ thẩm quyền
        │
Leader              y_dinh=WORK, delegate_work            ← HIỂU đúng
        │
engine.py:906       planner.plan(goal, project)           ← ✗ CHẾT Ở ĐÂY
        │                        ↑
        │                        chỉ một CHUỖI mục tiêu; không mang
        │                        theo việc người dùng vừa cho phép gì
        │
planner.plan()      loai_viec(md.text) → "analysis"       ← ✗ SAI (2)
                    duong_dan_trong()  → ("HTML/CSS/JS",) ← ✗ SAI (3)
                    không path + không default_write_scope
                        → hạ xuống CHỈ ĐỌC
        │
TaskContract        allowed_scope=()                      ← hệ quả
        │
PermissionEnvelope  "KHÔNG sở hữu phạm vi ghi nào"        ← hệ quả
        │
worker              blocked                                ← ĐÚNG
```

### Ba khuyết tật độc lập

**(1) Thẩm quyền không đi cùng kế hoạch.** `engine` gọi
`planner.plan(goal, ctx.project)` — chỉ một chuỗi. Sự thật *"người dùng vừa
cho phép ghi trong kho"* được tính ở tầng Leader rồi vứt đi, và bộ lập kế
hoạch phải tự suy lại phạm vi ghi bằng regex trên một mệnh đề.

Chỗ này còn có một bản sao đau hơn: ở đường vòng-kín V0.9
(`engine.py:1101`), `EYD.tao_y_dinh(...)` **tính xong thẩm quyền ngay dòng
trên** — `LopThamQuyen.REPO_LOCAL`, mà chính docstring của nó định nghĩa là
*"đọc kho, **sửa trong worktree của mình**, chạy test/build, commit"* — rồi
dòng ngay sau đó gọi `planner.plan()` **không truyền nó vào**.

**(2) Bộ phân loại cãi nhau với bộ từ vựng của chính nó.**
`loai_viec("Triển khai ứng dụng Web Todo…")` ra `analysis`: bảng `_LOAI_VIEC`
đòi chữ `code` ngay sau (`"triển khai code"`), nên `"triển khai ứng dụng"`
trượt hết mọi mẫu rồi rơi về mặc định an toàn. Nhưng `_Y_GHI` — bộ từ vựng
ĐỘNG TỪ GHI của **cùng một tệp** — đã liệt `triển khai` là động từ ghi từ
lâu.

Bản vá là **thêm đúng những động từ còn thiếu** vào `_LOAI_VIEC`
(`triển khai` trần, `tự code`, `làm luôn`, `xây dựng`…), KHÔNG phải một luật
tổng quát — xem mục "Ba lần tôi làm quá tay" ở cuối.

**(3) Dấu gạch chéo không phải đường dẫn.** `duong_dan_trong` đọc
`HTML/CSS/JS` trong *"giao diện HTML/CSS/JS thuần"* thành một đường dẫn, rồi
khoá `FILESYSTEM:HTML/CSS/JS` — một thư mục không tồn tại.

**(4) Phong bì tự mâu thuẫn.** Gói việc thật in `edit_in_owned_worktree`
trong danh sách ĐƯỢC TỰ LÀM, ngay trên dòng *"Việc này KHÔNG sở hữu phạm vi
ghi nào — chỉ đọc"*. Hai dòng cạnh nhau nói ngược nhau và agent phải tự đoán
dòng nào thật.

### Vì sao dự án MỚI luôn dính

`default_write_scope` suy từ `project.resources` có tiền tố `write:`
(`engine._scope_mac_dinh`). Dự án tạo bằng V0.9.2 **không khai tài nguyên
nào**. Nên với mọi dự án mới, nhánh "không path + không default" là nhánh
DUY NHẤT chạy được, và nó luôn hạ xuống chỉ đọc. Đó là **ngõ cụt**, không
phải cảnh báo: không có câu tiếng Việt nào mở được nó.

## Nguồn sự thật CHÍNH TẮC (sau V0.9.3)

| Sự thật | Chủ sở hữu DUY NHẤT | Ghi chú |
|---|---|---|
| loại hành động được yêu cầu | `planner.loai_viec()` | và nó phải ĐỒNG Ý với `_Y_GHI`; luật đối xứng: có động từ GHI + không có động từ ĐỌC → việc ghi |
| cho phép ghi repo-local | **câu NGƯỜI DÙNG gõ**, qua `permissions.tham_quyen_ghi_repo()` | mang theo bằng chứng; đường vòng-kín dùng `y_dinh.LopThamQuyen` |
| đường dẫn được ghi | người dùng nói rõ > `write:` của dự án > **gốc cây làm việc, chỉ khi đã cho phép** | luôn đánh dấu `scope_inferred` + ghi chú |
| ranh giới ngoài kho | `permissions.do_gated` / `envelope_for`, chấm trên TỪNG VIỆC | **không ai được dựng phép kiểm thứ hai** |

## Bất biến

Khi người dùng cho phép tường minh (*"ok triển khai"*, *"làm luôn đi"*,
*"code nó đi"*, *"implement theo plan này"*) **và** kế hoạch cần sửa mã
nguồn, Router cấp một quyền ghi repo-local **CÓ TRẦN**:

* phạm vi đúng **một** mục — gốc **cây làm việc của chính việc đó**, tức một
  worktree cô lập, không phải kho thật, không phải dự án khác;
* lớp GATED **không đổi một dòng**: deploy / production / IAM / secret /
  billing / force-push / remote-push vẫn dừng và hỏi người;
* `destructive_actions_allowed` vẫn `False`;
* điều kiện dừng *"phải ghi ra ngoài ALLOWED_SCOPE"* vẫn còn nguyên — nó
  đúng, và nó vẫn là thứ chặn một worker đi quá phạm vi;
* **thảo luận ≠ thực thi**: chưa `delegate_work` thì một câu có chữ "triển
  khai" KHÔNG mở được quyền ghi.

## Cái bẫy tôi đã tự sa vào

Bản nháp đầu của `tham_quyen_ghi_repo` tự chạy `do_gated` trên câu người
dùng như một điều kiện thứ ba. Nó TỪ CHỐI cấp quyền cho chính câu thật ở
đầu báo cáo này — vì chữ `deploy` trong **"Chỉ repo-local, KHÔNG deploy"**
khớp mẫu, bất kể chữ "không" đứng ngay trước. Người dùng nói *đừng* deploy
và bị đọc thành *hãy* deploy.

Đó chính là căn bệnh V0.9.3 sinh ra để chữa, tái tạo lại ở tầng mới: **hai
chỗ cùng quyết một sự thật**. Ranh giới ngoài kho có đúng một chủ sở hữu là
`envelope_for`. Bỏ phép kiểm thừa đó là AN TOÀN, vì phạm vi ghi chỉ có nghĩa
khi việc được chạy, mà việc chạm GATED thì bị chặn thành `BLOCKED` kèm
`requires_decision` và không bao giờ được giao (`test_31`, `test_32`).

## Khoảng trống ĐÃ BIẾT, cố ý chưa vá

`envelope_for` hứa trong docstring rằng nó quét *"câu gốc của người dùng"* để
Leader không diễn đạt một yêu cầu nguy hiểm thành một mục tiêu nghe vô hại.
**Lời hứa đó hiện không được giữ**: khi Leader uỷ thác, `engine` truyền
`intent` = mục tiêu do Leader viết lại, nên cả hai tham số đều là văn bản của
Leader.

Tôi đã vá thử trong lần làm này rồi **hoàn tác**: quét thêm câu người dùng
làm câu thật ở trên thành `GATED` (lại vì chữ "không deploy"), tức là chặn
đúng luồng đang sửa. Vá cho đúng thì phải dạy `do_gated` hiểu PHỦ ĐỊNH — tức
là **nới một bộ lọc an toàn**, việc cần một lần xem xét riêng chứ không đi
kèm một bản vá phạm vi ghi. Ghi lại làm việc tiếp theo.

## Kiểm

35 bài `test_pham_vi_ghi_v093.py`, dùng CHÍNH câu và CHÍNH mục tiêu chép từ
sổ chính tắc. Trong đó `test_33`/`test_34` đọc cấu trúc `engine.py` và
`planner.py`: sửa bộ lập kế hoạch mà quên nối ở `engine` thì mọi bài kiểm
đơn vị vẫn xanh còn người dùng vẫn bị chặn y như cũ.

**Đột biến**: tắt nhánh thẩm quyền trong `planner` làm **8/34** bài đỏ — các
bài kiểm có bám vào bản vá, không phải xanh vì tình cờ.

**Hồi quy đầy đủ: 2546 đạt · 4 bỏ qua · 0 hỏng** (115 module, chia 5 khối
không chồng lấn; cả 5 khối chạy lại trên CÂY CUỐI, không tính lần chạy trước
khi thu hẹp).

### Ba lần TÔI làm quá tay — hồi quy bắt được cả ba, đã hoàn tác

1. **Lọc đường dẫn theo "có tồn tại trên đĩa không".** Làm rơi mất
   `web/admin/content-queue` mà người dùng nói rõ, chỉ vì thư mục đó chưa
   được tạo (3 bài đỏ). Không cần cho khuyết tật đo được: thứ thật sự gây
   hại — `HTML/CSS/JS` — đã bị chặn bằng phép kiểm HÌNH DẠNG.
2. **Luật `_Y_GHI → implementation` thiếu vế "và không có động từ ĐỌC".**
   Kéo *"lục lịch sử git tìm commit đổi config"* (thuần đọc) thành việc ghi,
   vì `_Y_GHI` có chữ `commit` (1 bài đỏ).
3. **Luật đó, kể cả sau khi thêm vế thiếu, vẫn RỘNG hơn khuyết tật.** Nó kéo
   `deploy`/`delete`/`install` thành việc ghi, và
   `test_control_center_slice` bắt được: một việc GATED *"deploy the web to
   production"* sau khi DUYỆT kết thúc ở `REVIEW` thay vì `DONE`. Luật đúng
   về nguyên tắc nhưng đổi hành vi ngoài phạm vi bản vá, nên đã bỏ hẳn — chỗ
   thiếu thật sự chỉ là mấy động từ, và chúng được thêm thẳng vào
   `_LOAI_VIEC`.

Cả ba đều là cùng một cám dỗ: thấy một luật tổng quát đẹp hơn cái lỗ cần vá.
Bài kiểm hiện có là thứ duy nhất phân biệt được "tổng quát hơn" với "đổi
hành vi ở chỗ không ai nhờ".
