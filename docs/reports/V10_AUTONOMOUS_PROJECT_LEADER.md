# V1.0 — NỀN MÓNG PROJECT LEADER TỰ CHỦ

Nhánh `feat/v10-autonomous-project-leader`, dựng từ `main @ f974b5a`
(`router-control-center-v0.9.3`). **CHƯA merge, CHƯA tag, CHƯA phát hành.**

Tệp này là **nền móng**, không phải một hệ đã chạy. Phần nào chạy được thì
nói rõ; phần nào chỉ là trừu tượng chờ cắm runtime thật thì cũng nói rõ.

## Hình dạng

```
    NGƯỜI DÙNG
        ↓
    PROJECT LEADER   (vai ổn định; model ưu tiên Opus 5 KHI CÓ)
        ↓
    Router control plane        ← QUYẾT ĐIỀU GÌ ĐƯỢC PHÉP XẢY RA
        ↓
    agent/model chuyên biệt
        ↓
    điều tra / sửa chữa tự chủ  ← CÓ TRẦN
        ↓
    kiểm định
        ↓
    DONE
```

**Ranh giới không được xoá (B9):** Leader quyết *điều gì nên làm*. Router
quyết *điều gì được phép xảy ra*. Gói `v10/` **không có một lời gọi tiến
trình nào** — không `subprocess`, không `os`, không `shutil`, không `open()`.
Một bài kiểm đọc AST của cả gói và bắt bất kỳ import/lời gọi nào như thế
(`test_33`), và nó đã được thử bằng đột biến: thêm `import subprocess` vào
một module làm bài kiểm đỏ ngay.

## Cái gì đã có

| Module | Làm gì | B |
|---|---|---|
| `vai_tro.py` | vai ỔN ĐỊNH, model THAY ĐƯỢC; cổng review chéo họ | B4, B5 |
| `phien_leader.py` | danh tính Leader theo dự án + phiên nối lại/xoay | B2, B3 |
| `su_co.py` | phân loại hỏng → vòng sửa chữa CÓ TRẦN → leo thang | B6 |
| `su_kien.py` | bus sự kiện CÓ KIỂU cho Team Activity | B7 |
| `han_muc.py` | bể quota đo được; `UNKNOWN` là giá trị hợp lệ | B8 |

**41 bài kiểm** (`test_v10_nen_mong.py`) phủ 20 khẳng định B10 cộng bốn bài
kiểm CẤU TRÚC.

### Vì sao có bài kiểm cấu trúc ở đây

Đêm V0.9.3 vừa trả giá cho việc thiếu chúng: `isinstance(hd, dict)` biến cả
một rào an toàn thành hàm rỗng, và **không bài kiểm nào đỏ** — vì mọi bài
kiểm đều gọi hàm đó thuận chiều bằng một `dict`. Chính sách quan trọng phải
được neo bằng một phép đọc cấu trúc, không chỉ bằng một lần gọi thuận chiều.

## Những quyết định đáng nêu

**Vai là danh tính, model là ưu tiên.** `UU_TIEN` xếp theo thứ tự; model đầu
không có ở fabric thì rơi xuống và **ghi lại là đã rơi**. Không bao giờ trả
về một `model_id` fabric không biết — đó là cách một lượt dispatch chết ở tận
nơi. Không còn model nào thì vai đó **không khả dụng** và nói thẳng, chứ
không lấy bừa.

**`qd_0001` được THI HÀNH, không định nghĩa lại.** `gpt-6-astra` và
`fable-5-1` nằm trong `CAO_CAP`, và `chon_model` bỏ qua chúng trừ khi người
gọi truyền `cho_phep_cao_cap=True`. Nên "chế độ MAX" một mình KHÔNG kéo được
Astra vào — phải có một quyết định leo thang tường minh (`test_14`).

**Review chéo hẹp có chủ đích.** Gemini + sửa mã sản phẩm → BẮT BUỘC phản
biện khác họ. Việc dữ liệu (cạo/tin/metadata/phân loại/nghiên cứu) đã có
kiểm schema tất định → KHÔNG bắt buộc: bắt một model thứ hai đọc lại một tệp
JSON đã validate là tốn quota để mua một ý kiến. Không có reviewer độc lập
thì **báo suy giảm**, không lặng lẽ để cùng họ tự chấm (`test_13b`).

**Phiên là bộ nhớ NÓNG, không phải sự thật.** Sự thật bền ở Ký ức, Viên nang,
git, quyết định, sổ thực thi. Mất phiên là mất tốc độ, không mất kiến thức.
Phiên nguội quá 6 giờ thì **không nối lại** — nối vào một phiên đã trôi ngữ
cảnh tệ hơn dựng mới, vì nó trả lời tự tin bằng bối cảnh sai.

**Không giả vờ có runtime.** Không chứng minh được thì `UNVERIFIED`, và
`kich_hoat` trả về câu "KHÔNG báo là đã nối" (`test_25`). Giả vờ đã nối là
cách một tầng trên tin rằng nó có ngữ cảnh mà thực ra không.

**Vòng sự cố học từ chính đêm V0.9.3.** Hai luật đến thẳng từ đó:

* *cùng chữ ký ba lần = không tiến triển*. Đêm đó mỗi lần hỏng là một nguyên
  nhân KHÁC, nên thử lại là đúng; nếu ba lần cùng chữ ký thì lần bốn chỉ tốn
  quota;
* *một số hỏng không phụ thuộc chỗ chạy*. `git rev-parse HEAD thất bại` hỏng
  y hệt ở mọi runtime — đổi model cho loại đó là vô nghĩa, phải sửa môi
  trường (`test_08`).

Bộ phân loại được kiểm trên **chính những chữ ký thật của đêm đó**
(`test_09`): `tool_permission_denied`, `gate_scope`, `Individual quota
reached`, `ambiguous argument 'HEAD'`.

**Hạn mức: `UNKNOWN` ≠ `0`.** `0` nghĩa là đã cạn; `UNKNOWN` nghĩa là không
biết, và hai điều đó dẫn tới hai quyết định xếp chỗ ngược nhau. Bể `UNKNOWN`
**vẫn dùng được** — fail-closed ở đây sẽ tự bỏ đói cả hệ, vì phần lớn nhà
cung cấp không phơi ra số. Và đo MỘT tài khoản không được áp cho tài khoản
khác (`test_18`) — bài học V0.8, chép nguyên.

## Cái gì CHƯA có (nói thẳng)

| | |
|---|---|
| Leader chạy THẬT trên Opus 5 dưới quyền Router | **CHƯA** — `claude` CLI có `--session-id`/`-r` (đo được), nhưng chưa lượt nào chạy qua |
| Cắm `v10` vào `engine.py` | **CHƯA, có chủ đích** — `test_35` khoá lại rằng không module V0.9.x nào import `v10`, để nền móng còn tháo ra được |
| UI Team Activity | **CHƯA** — B12 nói backend trước; sự kiện đã có kiểu và đọc được, phần vẽ để sau |
| Probe runtime thật (B11) | **CHƯA** — xem `V10_RUNTIME_CAPABILITY_AUDIT.md` mục 5 |
| codex-chatgpt-web | **KHÔNG TÍCH HỢP** — chỉ có thiết kế adapter + kế hoạch probe |

`v10` hiện là một thư viện thuần: nó mô tả chính sách và giữ trạng thái. Nối
nó vào đường thực thi là bước sau, và bước đó phải đi kèm nghiệm thu thật —
đúng như V0.9.3 vừa cho thấy cái giá của việc tin vào một tầng chưa từng
chạy.

## Hai kho tham chiếu

Ghi ở `V10_RUNTIME_CAPABILITY_AUDIT.md` §4. Tóm tắt phán quyết:

* **codex-chatgpt-web** (MIT): tự động hoá trình duyệt KHÔNG chính thức.
  Router **không được phụ thuộc** vào nó. Giá trị cận biên là quota chứ
  không phải năng lực — Router đã có đường chính thức tới GPT qua `codex`.
  Có thiết kế adapter + kế hoạch probe có giới hạn, TẮT mặc định.
* **CodeLocal**: mô hình là **cây làm việc dùng chung** — ngược hẳn với
  isolation của Router, và thay thế nó là gỡ đúng cái rào V0.9.x vừa chứng
  minh là cần. Giữ ý tưởng CRDT cho **dòng sự kiện/hiện diện**, không cho
  nội dung tệp. Giấy phép không nêu → **không sao chép mã**.
