# V0.7 Phase 1 — NHẬN dự án có sẵn + VIÊN NANG DỰ ÁN duy trì liên tục

Mục tiêu của pha này: Router phải **nhận** được một dự án THẬT đang chạy
(Fanfic) mà không đụng vào nó, rồi tự dựng và duy trì một **Viên nang dự án**
đủ để một phiên mới trả lời được câu hỏi bối cảnh **không cần dán handoff và
không cần phái worker đi khám phá lại**.

Không thêm Strategist/Reviewer, không browser automation, không Artifact
Vault, không GitHub Stars Vault, không tự cập nhật. Không merge/tag/release
lên `main`.

Nghiệm thu chạy trên **ứng dụng thật ở chế độ source-mode**, gốc dữ liệu
chính tắc `%LOCALAPPDATA%\RouterControlCenter`, kho thật
`C:\Users\nguye\Documents\CapCut-TTS-App`.

---

## 1. Kết luận

| Pha nghiệm thu | Kết quả |
|---|---|
| `--chi nhan` — nhận dự án | **10/10 ĐẠT** |
| `--chi nang` — viên nang + kiểm liên tục | **9/9 ĐẠT** |
| `--chi hoi` — 12 câu hỏi thật + 1 câu sống | **17/17 ĐẠT** |
| Số lần sửa kho production | **0** |
| Số worker phái đi cho 12 câu hỏi lịch sử | **0** |
| Lần chạy ĐẦY ĐỦ cuối cùng (`--mo-lai`, cả ba pha) | **32/32 ĐẠT** |

Viên nang Fanfic: **19 mục, 18 có nội dung, 1 UNKNOWN, 18/18 mục có nội dung
đều mang bằng chứng lần về được**. Kiểm liên tục: **13/13 PASS, phủ bằng
chứng 95%, READY FOR PRIMARY WORKSPACE = YES**.

---

## 2. Ba khuyết tật THẬT mà chính bài nghiệm thu bắt được

Đây là phần đáng đọc nhất của pha này. Cả ba chỉ lộ ra khi hỏi ứng dụng thật
bằng câu hỏi thật — không bài kiểm đơn vị nào bắt được. Hai cái đầu là lỗi
**cắt ngữ cảnh**, cái thứ ba là lỗi **lấp chỗ trống bằng kiến thức chung**;
không cái nào là lỗi tính toán, nên chỉ đo trên ứng dụng thật mới thấy.

### 2.1. Leader BỊA một con số khi mục tương ứng bị cắt

Câu hỏi: *"hiện Router có bao nhiêu Antigravity account cho project?"*

Leader trả lời **"5 Antigravity accounts"** kèm một danh sách nghe rất hợp
lý, không dẫn mã bằng chứng nào và không nói là mình không chắc.

Sự thật đo được:

| Nguồn | Số tài khoản Antigravity |
|---|---|
| Viên nang (mục `tai_nguyen_agent`, bằng chứng `fabric`) | **8** (`ag-account-01` … `ag-account-08`) |
| Câu trả lời của Leader | **5** |

Viên nang **đúng**. Lỗi nằm ở chỗ khác: bản gọn nạp cho Leader có trần 900
token, mục `Tài nguyên agent / provider` xếp thứ 15/19 trong bảng ưu tiên cố
định, nên nó **bị cắt khỏi lượt đó**. Leader không có dữ liệu, và thay vì
nói "chưa nạp", nó lấp chỗ trống.

### 2.2. Dòng báo cắt chỉ ĐẾM, nên nó vô dụng

Bản gọn kết thúc bằng `(còn 10 mục nữa trong Viên nang — hỏi khi cần, đừng
đoán)`. Dòng này **đếm** mục bị cắt nhưng không **nêu tên**, nên Leader
không thể phân biệt hai tình huống hoàn toàn khác nhau:

* dự án KHÔNG CÓ bằng chứng cho thứ đang hỏi → phải nói "chưa có"; và
* dự án CÓ, chỉ là lượt này chưa nạp → phải nói "chưa nạp" rồi hỏi.

Không phân biệt được thì đoán là kết cục tự nhiên.

### 2.3. Vì sao đổi thứ tự ưu tiên KHÔNG phải là cách sửa

Cách sửa đầu tiên tôi thử là đẩy `tai_nguyen_agent` lên vị trí 7. Câu hỏi
account đạt ngay — và câu hỏi **R2/Google Drive hỏng**, vì mục `luu_tru` bị
đẩy xuống và bị cắt thay. Bảng ưu tiên cố định nào cũng cắt mất đúng mục
đang bị hỏi ở *một* câu hỏi nào đó; đây là trò đuổi bắt, không phải cách
sửa. Điều này được ghi thành nhận xét ngay trong mã (`thu_tu_nap`) để lần
sau không ai đi lại đường cũ.

### 2.4. Cách sửa thật

Ba thay đổi, tất định, không LLM, không mạng:

1. **Chọn mục theo CÂU HỎI, không theo bảng cố định.** `thu_tu_nap(cau_hoi)`
   giữ nguyên đầu bảng (thứ Leader cần mọi lượt), còn phần đuôi xếp theo độ
   khớp từ khoá với câu đang hỏi. Khớp **không phụ thuộc dấu**, nên "bao
   nhieu tai khoan antigravity" và "bao nhiêu tài khoản Antigravity" cho
   cùng một thứ tự.
2. **Mục khớp mạnh nhất chen lên ngay sau danh tính.** Khi ngân sách chật,
   đầu bảng có thể ăn hết trần và mục đang bị hỏi vẫn chết — chính bài kiểm
   `test_dong_CAT_khong_duoc_hy_sinh_muc_LIEN_QUAN_NHAT` bắt được điều này.
   Mục khớp mạnh nhất *chính là* thứ "cần ở lượt này", nên nó được một chỗ
   bảo đảm. Chỉ chen **một** mục, để không phá đầu bảng.
3. **Dòng cắt NÊU TÊN mục chưa nạp**, và được **nhường chỗ TRƯỚC** thay vì
   trừ sau. Bản trừ-sau (tôi viết đầu tiên) đuổi đúng mục liên quan nhất ra
   để lấy chỗ cho dòng cắt, rồi tên nó rơi vào phần `+N mục` — Leader mất cả
   nội dung lẫn tên, tức là quay lại đúng lỗi cũ. Thứ được phép hy sinh là
   **tên trong dòng cắt**, không bao giờ là **mục**.

Kèm theo: luật cho Leader (`leader.LUAT_NANG`) nói thẳng rằng dòng cắt là
danh sách "CÓ dữ liệu, chỉ là chưa nạp" — **không phải giấy phép để đoán**.

### 2.5. Trước / sau

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Câu "bao nhiêu Antigravity account" | "**5** accounts", không dẫn bằng chứng, không nói không chắc | "**8 tài khoản Antigravity** (8 runtime)", dẫn thẳng mục *Tài nguyên agent / provider* của Viên nang v6 |
| Câu "R2 và Google Drive giữ vai trò gì" | khẳng định chắc nịch, không bằng chứng | trả lời có căn cứ, mục `luu_tru` được nạp đúng lượt |
| Câu "issue quan trọng hiện tại" | (không đo) | "*Issue đang mở* có trong Viên nang v6 nhưng **chưa được nạp ở lượt này** do bị cắt" |
| Chọn mục nạp | bảng ưu tiên **cố định** | theo **độ liên quan với câu hỏi** + đầu bảng cố định |
| Dòng báo cắt | chỉ **đếm** ("còn 10 mục nữa") | **nêu tên** tối đa 10 mục + `+N mục` |
| Trần token | **nói dối**: trần 900, thực tế 922 (dòng chân cộng sau) | **thật**: đo 759–897 token trên mọi câu hỏi, mọi trần thử (300/600/900) — xem ngoại lệ ở mục 2.6 |
| Bộ đệm viên nang | đệm **văn bản đã render** → lượt sau nhận bản cắt của câu hỏi trước | đệm **`muc`** (thứ đắt vì đọc sổ), render theo từng câu hỏi |
| Nghiệm thu Phần G | 15/16 | **17/17** |

### 2.6. Ngoại lệ đã biết của trần token — nói ra thay vì che

Trần được giữ **thật** trong mọi cấu hình vận hành, nhưng có đúng một ngoại
lệ, cố ý: bản gọn luôn giữ **ít nhất một mục cộng dòng cắt**. Nếu một mục
đơn lẻ đã lớn hơn cả trần (trần bệnh lý như 80–150 token, hoặc một mục
khổng lồ bất thường) thì khối trả về sẽ vượt trần — đo được 240 token ở trần
80. Bỏ nốt dòng cắt để cho vừa là bỏ đúng thứ ngăn Leader đoán, nên đây là
đánh đổi có chủ ý, được ghi trong docstring của `render_gon` và trong bài
kiểm. Ở trần vận hành 900 với viên nang Fanfic thật: **759–897 token**.

### 2.7. Khuyết tật thứ ba — mục CÓ MẶT nhưng MỎNG cũng bị lấp bằng phỏng đoán

Sau khi sửa 2.1–2.4, câu *"R2 và Google Drive giữ vai trò lưu trữ gì?"* vẫn
hỏng **không ổn định** (đạt ở một lần chạy, hỏng ở hai lần khác). Đây không
phải nhiễu của bài kiểm — nó là một lỗ hổng khác cùng họ.

Mục `luu_tru` **được nạp đúng lượt** (đã kiểm), nhưng nội dung thật của nó là:

```
Kiến trúc lưu trữ:
  - tài liệu: docs\APPWRITE_MIGRATION.md, docs\APPWRITE_PROD_CUTOVER.md, …
  - [ku_61431e4b61b8591e] kết quả việc fanfic.t9a4c-1
  - [ku_d7a9cd6d1250dc85] … quy trình backup có khớp hạ tầng hiện tại không
  - [ku_438deca843083c89] A regression test asserts it reads `STORAGE_BACKEND` …
```

Không một dòng nào nói **R2 chứa gì** hay **Drive chứa gì**. Tức là dự án
thật sự **chưa có bằng chứng** cho điều đang hỏi — nhưng Leader thấy mục có
mặt nên coi đó là giấy phép để nói tiếp bằng **kiến thức chung về công nghệ**,
trình bày như thể đó là sự thật của dự án này.

Luật cũ chỉ phủ trường hợp mục **BỊ CẮT**, không phủ trường hợp mục **CÓ MẶT
NHƯNG MỎNG**. Đã bổ sung vào `leader.LUAT_NANG`: tên tài liệu và trích đoạn
ký ức là **CHỖ ĐỂ TRA, không phải câu trả lời**; nội dung nạp được mà không
nói ra điều đang hỏi thì phải trả lời "hồ sơ dự án có *mục X* nhưng chưa ghi
rõ *điều đang hỏi*" kèm danh sách tài liệu/mã đáng tra; và **mỗi khẳng định
về dự án phải kèm mã** (`qd_…`, `ku_…`, `sk#…`, `doc:…`).

Đo lại đúng câu đó, 4 lượt liên tiếp trên app thật sau khi sửa:

| Lượt | Kết quả | Việc mới | Có căn cứ | Thành thật |
|---|---|---|---|---|
| 1 | ĐẠT | 0 | có | có |
| 2 | ĐẠT | 0 | có | có |
| 3 | ĐẠT | 0 | có | có |
| 4 | ĐẠT | 0 | có | có |

Câu trả lời điển hình sau khi sửa: *"Hồ sơ dự án có mục **Kiến trúc lưu trữ**
(Viên nang v8), nhưng dữ liệu hiện tại chưa ghi rõ vai trò lưu trữ cụ thể của
R2 và Google Drive"*, rồi liệt kê đúng những tài liệu đáng tra. Đây là hành vi
mong muốn: **nói thẳng chỗ trống và chỉ đường**, thay vì lấp bằng phỏng đoán.

Bài kiểm khoá lại: `test_LUAT_NANG_cam_doan_khi_muc_bi_CAT_hoac_MONG` — cả hai
luật phải còn trong `LUAT_NANG`, và luật chỉ được gắn khi lượt đó THỰC SỰ có
khối viên nang.

---

## 3. Phần A/B — Nhận dự án, chỉ đọc, danh tính ổn định

`nhan_du_an()` **không sao chép, không dời, không khởi tạo lại, không ghi**
gì vào kho được nhận.

Đo được ở lần nhận Fanfic thật:

| Kiểm | Kết quả |
|---|---|
| Nhận diện kho | git, nhánh, HEAD, remote, số commit, commit gốc |
| Số byte của kho bị đổi | **0** (`git status --porcelain` sạch trước và sau) |
| Cây `.router` của kho Fanfic | **127.279 mục, không đổi** (chụp trước/sau) |
| Sổ ký ức tạo trong kho Fanfic | **không có** |
| Nhận lại lần hai | **idempotent**, không tạo dự án thứ hai |
| Nhận từ thư mục con | ra đúng dự án gốc |
| Đổi nhánh | danh tính **không đổi** |
| `project_id` đã dùng cho kho khác | **từ chối**, nói rõ lý do |
| URL remote | **lọc credential** trước khi lưu |

Danh tính suy từ **gốc worktree đã phân giải** + commit gốc, **không** từ
nhánh hiện tại. Hai chi tiết phải sửa vì đo sai lúc đầu:

* `git log --reverse -n1` trả về commit **mới nhất**, không phải commit gốc
  (giới hạn `-n1` áp trước khi đảo). Phải dùng
  `git rev-list --max-parents=0 HEAD`.
* Khoá chống trùng phải đặt trên **gốc worktree**, không phải
  `--git-common-dir`: Fanfic và Router dùng **chung một `.git`**, nên khoá
  theo git-dir sẽ coi hai dự án là một.

## 4. Phần C/D/E — Viên nang, nguồn gốc, ưu tiên nguồn, phiên bản

19 mục. Mỗi mục mang `{gia_tri, trang_thai, nguon, bang_chung, ghi_chu, ts}`.

| Đo trên Fanfic | Giá trị |
|---|---|
| Mục có nội dung | **18/19** |
| Mục UNKNOWN | **1** (không bịa) |
| Mục có nội dung mà có bằng chứng | **18/18** |
| Phiên bản giữ trong sổ | **9** (không ghi đè bản cũ) |
| Viên nang đầy | **3.754 token** |
| Bản gọn cho Leader | **890 token** |

Ưu tiên nguồn: `quyet_dinh > kho > ky_uc > tai_lieu > git > suy_luan`.
UNKNOWN là **một giá trị hợp lệ**, không phải lỗi.

Giá trị SỐNG **không bị đóng băng**: mục *Tham chiếu trạng thái SỐNG* chỉ
ghi **đo được cái gì và bằng provider nào**
(`ssh_service · id=fanfic_farmer · unit=fanfic-farmer`), không ghi phán
quyết. Câu hỏi "bây giờ còn chạy không" vẫn phải đi đo thật.

Bí mật **không vào viên nang** — có bài kiểm khoá lại.

## 5. Phần F — Kiểm toán liên tục

13 hạng mục, mỗi hạng mục PASS/PARTIAL/FAIL kèm lý do. Không có hạng mục nào
được cho điểm chỉ vì "đã khai": *Live observability* chỉ PASS khi trong sổ
có **phép đo sống thật**, khai suông là PARTIAL.

```
Project identity PASS · Mission PASS · Architecture PASS
Production topology PASS · Critical decisions PASS · Known incidents PASS
Open issues PASS · Roadmap PASS · Live observability PASS
Historical coverage PASS (8.034 dòng L0) · Evidence coverage PASS (18/19)
Agent/provider avail PASS
→ Evidence coverage 95% · READY FOR PRIMARY WORKSPACE: YES
```

## 6. Phần G/O — 12 câu hỏi thật trên ứng dụng thật

Hỏi qua đúng ô chat của app source-mode đang chạy, đếm việc mới sinh ra
trong sổ trước/sau mỗi câu.

| Đo | Kết quả |
|---|---|
| Tổng worker phái đi cho **12 câu hỏi lịch sử** | **0** |
| Câu trả lời có căn cứ **hoặc** nói thẳng chưa có | **12/12** |
| Câu hỏi HIỆN TẠI → có phép đo sống | **1 probe thật** (`ssh:13.212.224.218`) |
| Việc mới sinh ra do câu hỏi sống | **0** |
| Sửa kho production | **0** |

Ba câu trả lời đáng chú ý, vì chúng cho thấy hệ thống **thành thật** chứ
không phải chỉ trôi chảy:

* *"bug/limitation >100k chapter?"* → "**chưa có** trong ký ức dự án và dữ
  liệu nạp ở lượt này" thay vì bịa một con số.
* *"work production nào đã validate?"* → nói thẳng chưa có trong ký ức.
* *"issue quan trọng hiện tại?"* → "*Issue đang mở* **có** trong Viên nang
  v6 nhưng **chưa được nạp ở lượt này** do bị cắt" — đúng thứ mục 2.2 sinh
  ra để có.

## 7. Phần I — Leader hydrate RẺ

Viên nang đầy ~3.75k token; bản nạp mỗi lượt ~0,9k, **có trần thật**. Không
nạp hàng nghìn sự kiện lịch sử — đó là việc của truy hồi sâu khi lượt cần.

Bộ đệm giữ `muc` (thứ đắt, vì phải đọc sổ) với TTL 30 s, còn **render lại
theo từng câu hỏi**. Đệm văn bản đã render là sai: lượt sau sẽ nhận đúng bản
cắt của câu hỏi trước.

## 8. Phần K — An toàn dự án

Không tự động: deploy, migrate, xoá R2, sửa Appwrite, xoá Drive, sửa AWS,
khởi động lại production, rút bí mật. Credential vẫn chỉ là **tham chiếu**
tới kho bí mật của hệ điều hành. Nghiệm thu đo `git status` của kho Fanfic
trước/sau: **không tệp tracked nào đổi**.

## 9. Phần L/N — Hồi quy và bài kiểm

Hồi quy toàn bộ hai cây kiểm (`scripts/tests` + `tests`):

| Đo | Số |
|---|---|
| Đạt | **2.194** (+ 1.742 subtest) |
| Bỏ qua | 175 |
| Hỏng | **10 — toàn bộ cùng MỘT nguyên nhân MÔI TRƯỜNG** |

Mười bài hỏng đều là `ModuleNotFoundError: No module named 'PySide6'` trong
`tests/test_output_manager.py::TestSettings` — bài kiểm của **ứng dụng
desktop**, không phải Router Control Center. Chúng *hỏng* thay vì *bỏ qua* vì
tệp đó `import PySide6` bên trong thân bài kiểm (dòng 449) chứ không có
`skipIf` ở đầu tệp. `pip show PySide6` xác nhận gói không có trong worktree
này, và tệp đó **không bị pha này sửa** (`git status` sạch cho nó). Không một
bài kiểm nào của Router hỏng.



Bài kiểm mới cho pha này: `scripts/tests/test_nhan_du_an_v07.py` — **30 bài,
7 subtest**, gồm 5 bài mới khoá lại đúng các khuyết tật ở mục 2:

* `test_thu_tu_nap_DAY_MUC_LIEN_QUAN_len_theo_cau_hoi`
* `test_thu_tu_nap_KHOP_KHONG_PHU_THUOC_DAU`
* `test_dong_CAT_phai_NEU_TEN_muc_chua_nap`
* `test_dong_CAT_khong_duoc_hy_sinh_muc_LIEN_QUAN_NHAT`
* `test_render_gon_GIU_TRAN_ke_ca_khi_co_dong_cat`

Bài thứ tư **thất bại lần đầu** và bắt được lỗi thật (đầu bảng ăn hết ngân
sách, mục đang bị hỏi vẫn chết) — dẫn tới thay đổi số 2 ở mục 2.4.

## 10. Việc CỐ Ý không làm ở pha này

Strategist/Reviewer, browser automation, Artifact Vault, GitHub Stars Vault,
tự cập nhật — **chưa làm**, đúng phạm vi pha 1. Không merge, không tag,
không release lên `main`.
