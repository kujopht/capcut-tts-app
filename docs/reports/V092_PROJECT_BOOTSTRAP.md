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

## Kiểm

23 bài `test_tao_du_an_v092.py` — phần lớn là những lần phải từ chối (trùng
thư mục, vượt gốc, tên cấm, đăng ký hỏng thì hoàn tác sạch, hoàn tác không
đụng thư mục có sẵn), cộng đường hạnh phúc (khung tối thiểu, `git init`,
đăng ký, viên nang dùng được ngay, sổ sạch) và bất biến "dự án nhận nuôi
không bị dời chỗ". 54 bài webapi vẫn xanh.

**Một khẳng định của tôi đã SAI và đã sửa:** bài kiểm ban đầu đòi
`"../thoat-ra"` bị TỪ CHỐI. Thực tế `slug()` nghiền nó thành `thoat-ra` NẰM
TRONG thư mục gốc — an toàn, chỉ là không bị từ chối. Bất biến đúng là
**không thoát được ra ngoài**, và bài kiểm nay khẳng định đúng điều đó trên
ba dạng traversal.
