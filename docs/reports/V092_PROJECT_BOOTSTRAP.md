# V0.9.2 — TẠO DỰ ÁN MỚI TỪ MỘT CÁI TÊN

Nhánh `feat/v092-project-bootstrap`, dựng từ `main @ 342dc6e`
(`router-control-center-v0.9.1`). **Chưa merge/tag/push.**

## Vấn đề

`+ Dự án mới` chỉ nhận MỘT đường dẫn tuyệt đối tới kho ĐÃ CÓ. Tốt cho việc
nhận nuôi một dự án trưởng thành (Fanfic), nhưng để bắt đầu từ số không thì
người dùng phải tự `mkdir`, tự `git init`, rồi mới quay lại gõ đường dẫn —
ba bước thủ công cho thứ đáng lẽ là một cái tên.

## Hai luồng, tách bạch

| Luồng | Hành vi |
|---|---|
| **Tạo mới** (mặc định) | gõ TÊN → Router dựng thư mục dưới thư mục dự án mặc định, `git init`, khung tối thiểu, rồi NHẬN nó |
| **Nhập repo** | hành vi CŨ, không đổi một dòng: nhận kho đã có tại đường dẫn tuyệt đối, KHÔNG di chuyển |

**Một máy móc đăng ký, không phải hai.** Luồng tạo mới chạm đĩa xong là gọi
thẳng `nhan_du_an()` — nên danh tính, ký ức, viên nang và bản ghi registry
đều đi qua đúng đường mà Fanfic đã đi. Không dựng kiến trúc lưu trữ thứ hai,
và sổ canonical vẫn ở gốc dữ liệu Router, KHÔNG nằm trong cây git của dự án
(`.gitignore` có `.router/`).

**Thư mục dự án mặc định** là một cài đặt thường (`thu_muc_du_an_mac_dinh`,
mặc định `C:\RouterProjects`). Nó CHỈ là mặc định cho dự án TẠO MỚI — dự án
nhận nuôi nằm nguyên chỗ của nó:

```
RouterDogfood01 -> C:\RouterProjects\RouterDogfood01
Fanfic          -> C:\Users\nguye\Documents\CapCut-TTS-App
```

## An toàn

Đây là tính năng ĐẦU TIÊN của Router tự tạo thư mục, nên phần lớn công sức
nằm ở những lần PHẢI TỪ CHỐI:

* đích phải nằm trong thư mục gốc — so sau `resolve()`, nên junction không
  lách được;
* thư mục đã tồn tại → TỪ CHỐI kèm gợi ý dùng tab «Nhập repo»; **không bao
  giờ** trộn hay ghi đè;
* tên dành riêng của Windows (`CON`, `NUL`, `COM1`…) → từ chối;
* hoàn tác chỉ gỡ thứ CHÍNH LẦN GỌI NÀY tạo ra — thư mục gốc có sẵn của
  người dùng không bao giờ nằm trong danh sách xoá.

Không cần credential, không phụ thuộc mạng, không đụng production.

## Dogfood THẬT

Tạo `RouterDogfood01` trên sổ chính tắc:

```
thư mục dự án mặc định: C:\RouterProjects
tạo: True | đã tạo dự án 'routerdogfood01' tại C:\RouterProjects\RouterDogfood01
  CÓ  C:\RouterProjects\RouterDogfood01\{.git, README.md, .gitignore, docs}
  đăng ký: True · repo_path=C:\RouterProjects\RouterDogfood01
  việc: 0
```

Hỏi Leader (model thật) *"project này mới tinh đúng không? … lên kế hoạch
thôi, chưa code"*:

* **hiểu đây là dự án trống** — *"project này mới tinh luôn … repo chưa có
  commit nào"*, dẫn bản ghi ký ức `ku_06ef69df9d2e9ac7` làm bằng chứng;
* **không lẫn bối cảnh Fanfic** — không một chữ fanfic/capcut/tts/farmer nào
  trong câu trả lời (đã kiểm tự động);
* **kế hoạch có giới hạn**: chọn tech stack → giao diện + dark mode qua CSS
  variables → CRUD + localStorage, rồi hỏi lại người dùng;
* **KHÔNG tạo execution, KHÔNG sinh việc worker** — đúng như người dùng nói
  "chưa code".

`execution: (không tạo)` · việc sinh thêm: **0** · thay đổi production: **0**.

## Giao diện

Backend xong rồi thì nút `+ Dự án mới` vẫn mở **một ô duy nhất** nhận đường
dẫn tuyệt đối — tức là luồng tạo mới có tồn tại mà người dùng không bấm tới
được. Phần này nối nốt:

| | |
|---|---|
| `+ Dự án mới` | hộp thoại **hai tab**: `[Tạo mới]` (mặc định) / `[Nhập repo]` |
| Cài đặt | ô **Thư mục dự án mặc định** + nút Lưu, nối vào `thu_muc_du_an_mac_dinh` |

**Không có bản sao logic nào ở frontend.** Cả hai tab gọi API backend; ngay
cả dòng xem trước đường dẫn cũng hỏi `/api/project/create/preview` thay vì
tự suy. Bản cũ tự suy `project_id` bằng JS (`ten.toLowerCase().replace(…)`)
— một bản sao thứ hai của `slug()`, đặt ở tầng không bao giờ được kiểm.

Ô cài đặt phải khai báo tường minh vì `/api/ui` dùng danh sách CHO PHÉP, và
phép kiểm giá trị sống ở `tao_du_an.kiem_thu_muc_goc()` — **một định nghĩa,
dùng chung mọi người gọi**: tuyệt đối, không `..`, không gốc ổ đĩa, không
trỏ vào một tệp; rỗng nghĩa là bỏ thiết lập. Thư mục chưa tồn tại thì CHẤP
NHẬN — bắt người dùng đi `mkdir` trước là đúng cái phiền V0.9.2 xoá đi.

### Bốn hỏng, cả bốn đều im lặng cho tới lúc bấm

| Hỏng | Vì sao không ai thấy |
|---|---|
| `json({ten})` — `json` là `const` trong một hàm KHÁC | sai **phạm vi**, không phải sai cú pháp: `node --check` vẫn xanh |
| `$('#o-chat')` trong khi ô soạn tên `#o-soan` | không lỗi, không cảnh báo — con trỏ chỉ không nhảy vào ô |
| bản sao logic đặt tên ở JS | chạy đúng, cho tới ngày `slug()` đổi |
| nút Lưu báo «đã lưu» cho giá trị backend vừa TỪ CHỐI | `luuCaiDatUI` **nuốt** lỗi (cố ý), nên `try/catch` quanh nó không bao giờ chạy |

Cái thứ tư là khuyết tật sản phẩm thật, không phải lỗi của tôi lúc viết:
nuốt lỗi là đúng (một lần lưu hỏng không được làm gãy tay kéo thanh trượt),
nhưng nó biến `catch` thành một phép kiểm chết. Nay hàm TRẢ VỀ có/không và
người gọi đọc giá trị đó.

Cả bốn nay có bài kiểm CẤU TRÚC đọc thẳng `app.js`/`index.html`/`style.css`,
và **cả bốn đã được thử bằng ĐỘT BIẾN** — đặt lại lỗi vào thì bài kiểm đó đỏ.
Không có trình duyệt ở CI, nên chỗ duy nhất còn lại bắt được chúng là ngón
tay người dùng.

### Diễn tập đường bấm (Chrome thật, CDP)

Bộ công cụ trình duyệt **không với tới được** máy chủ loopback trên máy này
(đã đo). Chrome + CDP thì với tới được, và cho ra cú **bấm thật**
(`Input.dispatchMouseEvent`) chứ không phải một lời gọi API đội lốt. DOM chỉ
dùng để TÌM TOẠ ĐỘ và ĐỌC LẠI kết quả.

Diễn tập chạy trên một **gốc dữ liệu cách ly** (không phải sổ chính tắc),
thư mục dự án riêng, tên dự án riêng — `C:\RouterProjects\RouterDogfood02`
không bị đụng tới, nó dành cho lần thật. **31/31 ngay lần đầu**:

```
[2] ô Cài đặt   giá trị hỏng BỊ TỪ CHỐI kèm câu người đọc được
                ("'kho-tuong-doi' là đường dẫn tương đối — hãy gõ đường dẫn
                 đầy đủ, ví dụ C:\RouterProjects.")
                giá trị đúng được nhận · mở lại hộp thoại thì giá trị CÒN ĐÓ
[3] modal       hai tab · «Tạo mới» chọn sẵn · khung «Nhập repo» đang ẩn
[4] đổi tab     bấm thật qua lại, đúng khung hiện/ẩn, đúng tab đỏ sáng
[5] xem trước   "Sẽ tạo tại:  …\DuAn\DienTap01"   (hỏi backend, không tự suy)
[6] tạo         hộp thoại tự đóng
[7] trên đĩa    .git · README.md · .gitignore · docs · KHÔNG có .router/
[8] sau khi tạo hiện ở thanh bên · được CHỌN sẵn · con trỏ ở #o-soan · 0 việc
[9] «Nhập repo» đường CŨ vẫn chạy
```

Cái diễn tập này bắt được một khuyết tật thật **trước khi** có trình duyệt
nào mở: nút Lưu báo «đã lưu» cho giá trị backend vừa từ chối (bảng trên).

**Dogfood thật trên sổ chính tắc còn NỢ**, và nó nợ vì một lý do nêu thẳng
ra: một tiến trình Control Center CŨ (có trước V0.9.2 —
`/api/project/create/preview` trả 404) đang giữ sổ chính tắc, và chạy một
người ghi THỨ HAI bên cạnh nó đúng là thứ đã làm hỏng năm lần chạy ở V0.9.
Đóng cửa sổ đó rồi chạy lại là xong. **Không được** báo READY TO RELEASE
trước khi lần đó chạy thật.

## Kiểm

23 bài `test_tao_du_an_v092.py` — phần lớn là những lần phải từ chối (trùng
thư mục, vượt gốc, tên cấm, đăng ký hỏng thì hoàn tác sạch, hoàn tác không
đụng thư mục có sẵn), cộng đường hạnh phúc (khung tối thiểu, `git init`,
đăng ký, viên nang dùng được ngay, sổ sạch) và bất biến "dự án nhận nuôi
không bị dời chỗ". 54 bài webapi vẫn xanh.

26 bài `test_giao_dien_du_an_moi_v092.py` cho phần giao diện: giá trị ô cài
đặt (9), đường API kèm **bền qua khởi động lại** và bất biến "đổi ô này
không dời dự án đã nhận" (7), và đọc cấu trúc `app.js`/`index.html`/
`style.css` cho bốn hỏng ở trên (10).

**Một khẳng định của tôi đã SAI và đã sửa:** bài kiểm ban đầu đòi
`"../thoat-ra"` bị TỪ CHỐI. Thực tế `slug()` nghiền nó thành `thoat-ra` NẰM
TRONG thư mục gốc — an toàn, chỉ là không bị từ chối. Bất biến đúng là
**không thoát được ra ngoài**, và bài kiểm nay khẳng định đúng điều đó trên
ba dạng traversal.
