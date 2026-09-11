# V0.8 — NGHIỆM THU THẬT: vai suy luận trên MODEL THẬT

Nhánh `feat/v08-strategist-reviewer-model-router`. Chạy 2026-09-11 trên **ứng
dụng THẬT** (`python -m scripts.control_center.webmain`, đúng điểm vào của
`router-cc-web.cmd`), **sổ CHÍNH TẮC** (`%LOCALAPPDATA%\RouterControlCenter`),
**dự án `fanfic` thật**, Leader BẬT.

Bài này lấp đúng lỗ hổng mà báo cáo v0.8 tự nêu: *"chưa có lượt model THẬT nào
của Strategist/Reviewer được đo — chất lượng nội dung chưa có số liệu."*

Kịch bản: `scripts/control_center_v08_real_acceptance.py`.

**Kết quả, nói chính xác:** lần chạy đầy đủ (có model thật) cho **27/28 ĐẠT**.
Mục hỏng DUY NHẤT là *"UI đồng bộ lại chế độ từ server"* — một khuyết tật
giao diện có thật, đã sửa (§6) và **đã xác minh lại bằng Chrome thật** ở một
lần chạy `--chi 9` (không tình huống nào → 0 lượt model), nơi mục đó ĐẠT.

Cố ý KHÔNG chạy lại trọn bộ để lấy một con số 28/28: chạy lại tốn thêm bảy
lượt model thật cho một mục không liên quan gì tới model, và bể Claude/GPT
đang ở 10% hạn mức tuần. Con số được báo cáo là con số ĐÃ ĐO, không phải
con số mong muốn.

## 1. Ngân sách — bảy lượt model, một chạm bể khan hiếm

Bể Claude+GPT của Antigravity đo được **10% hạn mức tuần** ngay trước khi
chạy, nên kịch bản chạy **số lượt tối thiểu**: bốn tình huống, một chế độ
(AUTO). Bốn chế độ được chứng minh bằng phép định tuyến TẤT ĐỊNH, không bằng
bốn lần gọi model.

| Bể | Còn lại (ĐO THẬT) | Cửa sổ | Reset |
|---|---|---|---|
| `antigravity_gemini` | **40%** | tuần | 2026-09-12T05:39:35Z |
| `antigravity_claude_gpt` | **10%** | tuần | 2026-09-14T19:58:56Z |
| AI credit trả phí | 0 | — | (rủi ro tính phí vượt hạn mức = 0) |

Đo bằng `agy --print /usage`, áp vào bể của **đúng tài khoản đã đo**
(`ag-account-01`), không lan sang bảy tài khoản còn lại.

Tổng tiêu thụ: **7 lượt model** — 6 trên bể Gemini, **1** trên bể Claude/GPT.

## 2. Bốn tình huống — định tuyến THẬT

| TH | Câu | Phân loại | Vai | Việc tạo | Giây |
|---|---|---|---|---|---|
| 1 | `ê bro` | TAM_THUONG / THAP (tin 0.95) | **Leader** | 0 | 44.7 |
| 2 | `vụ SSH key fanficappwrite trước đây bị gì?` | TAM_THUONG / THAP (tin 0.90) | **Leader** | 0 | 13.3 |
| 3 | `…nên ưu tiên phát triển phần nào tiếp theo và tại sao?` | KHO / TRUNG (tin 0.45) | **Leader + Strategist** | 0 | 48.2 |
| 4 | `…redesign lớn… sau đó tự phản biện… có nên làm ngay không` | RAT_KHO / CAO (tin 0.90) | **Leader + Strategist + Reviewer** | 0 | 148.2 |

Model cho từng vai:

| TH | Vai | Placement | Bậc giá | Độc lập | Astra | Giây |
|---|---|---|---|---|---|---|
| 3 | Strategist | `AG01/gemini-3.8-flash-high` | TRUNG | — | KHÔNG | 32.6 |
| 4 | Strategist | `AG01/gemini-3.8-flash-high` | TRUNG | — | KHÔNG | 21.7 |
| 4 | Reviewer | `AG01/claude-opus-4-6-thinking` | CAO_CAP | **CÓ** (`claude` ≠ `gemini`) | KHÔNG | 97.0 |

Phán xử của Reviewer: **REVISE**, 6 phát hiện cụ thể.

Chính sách bậc cao cấp ở CẢ HAI lượt: `nguon=ky_uc`, `ma=qd_0001`,
`han_che=True` — tra từ ký ức dự án, không phải hằng số trong mã.

## 3. Chất lượng nội dung — chấm theo rubric

<a id="rubric"></a>

Thang mỗi mục: 0 = không đạt · 1 = một phần · 2 = đạt. Chấm trên VĂN BẢN
THẬT Leader trả về.

| # | Tiêu chí | TH1 | TH2 | TH3 | TH4 |
|---|---|:--:|:--:|:--:|:--:|
| R1 | Dùng bằng chứng THẬT của dự án (có mã) | — | 2 | 2 | 2 |
| R2 | Tôn trọng Quyết định / Ràng buộc hiệu lực | — | — | 2 | 2 |
| R3 | Phân biệt SỰ THẬT với GIẢ ĐỊNH | — | 2 | 2 | 2 |
| R4 | KHÔNG bịa trạng thái dự án | — | 2 | 2 | 2 |
| R5 | Lời khuyên DÙNG ĐƯỢC | — | — | 2 | **1** |
| R6 | Reviewer phản biện THẬT | — | — | — | 2 |
| R7 | Leader hoà giải mạch lạc | — | — | — | 2 |
| R8 | Thảo luận VẪN là thảo luận | 2 | 2 | 2 | 2 |
| | **Tổng** | 2/2 | 8/8 | 12/12 | **15/16** |

**Điểm tổng: 37/38 = 0.974** (ngưỡng đạt 0.70; `R4 ≥ 1` ở mọi tình huống —
đạt, cả bốn đều 2).

**R5 = 1 cho TH4, và đây là chỗ duy nhất bị trừ.** Phần "redesign" của
Strategist là kiến trúc đám mây CHUNG CHUNG (message queue tách rời, worker
co giãn ngang, lưu trữ phân tầng, observability tập trung) — đúng nhưng
không riêng cho Fanfic. Giá trị dùng được nằm ở mục 3 của câu trả lời
("CHƯA NÊN làm ngay, ổn định trước"), và chính Reviewer đã gọi tên điểm yếu
đó. Hệ thống xử lý đúng; nội dung mục 1 thì mỏng.

### R4 được kiểm bằng phép ĐO LẠI, không bằng đọc lại

Sáu khẳng định "cứng" trong câu trả lời TH3/TH4 được đối chiếu với một lần
đo ĐỘC LẬP của lớp quan sát sống (`quan_sat.anh_chup(buoc_moi=True)`):

| Khẳng định của Leader | Phép đo lại |
|---|---|
| farmer `fanfic-farmer` ACTIVE | ✅ `fanfic_farmer` = ACTIVE |
| `MainPID = 684324` | ✅ có trong phép đo |
| `NRestarts = 0` | ✅ có trong phép đo |
| đĩa dùng 21% | ✅ `khoa=disk, gia_tri=21, nguon=ssh:13.212.224.218` |
| `cat: /var/lib/fanfic-farmer/status.json: Permission denied` | ✅ khớp NGUYÊN VĂN |
| `appwrite`, `r2` UNAVAILABLE | ✅ cả hai UNAVAILABLE |

**6/6 khớp. Không một khẳng định trạng thái nào bị bịa.**

### Reviewer phản biện THẬT — nó bắt được một lỗi THẬT

Phát hiện đáng giá nhất của Reviewer (`claude-opus-4-6-thinking`):

> *"Strategist dùng một ràng buộc chưa xác minh (`ku_668f6cce0b6de423`) làm
> luận điểm rủi ro chính để chống redesign."*
>
> *"Giả định hướng scale bị gán cụ thể (TTS/farmer/metadata) mà không xác
> nhận với người dùng."*

Đây không phải phản biện lịch sự. Kê khai ngữ cảnh xác nhận Reviewer **đúng
về mặt sự thật**: gói của nó là `2724/3400` token và các khối
`['vien_nang', 'ky_uc', 'trang_thai_kho']` **đã bị cắt** — nên nó không thể
xác minh `ku_668f6cce0b6de423`, và nó nói thẳng điều đó thay vì đóng dấu.
Đó chính là hành vi mà `LUAT_NANG` của V0.7 tồn tại để ép, nay do một model
KHÁC HỌ thực thi lên đầu ra của model kia.

## 4. Bốn chế độ — tất định, 0 lượt model

| Chế độ | Strategist cho câu RẤT KHÓ | Astra |
|---|---|---|
| ECO | `AG01/gemini-3.8-flash-high` [TRUNG] | KHÔNG — *"chế độ ECO cấm Astra tuyệt đối"* |
| AUTO | `AG01/gemini-3.8-flash-high` [TRUNG] | KHÔNG — có lý do leo thang, nhưng không placement nào chạy được |
| STRONG | `AG01/claude-opus-4-6-thinking` [CAO_CAP] | KHÔNG |
| MAX | `AG01/claude-opus-4-6-thinking` [CAO_CAP] | KHÔNG — vẫn qua chính sách `qd_0001` + `GacAstra` |

**MAX ≠ "luôn dùng Astra"** — chứng minh được: MAX có lý do `nguoi_yeu_cau`
và vẫn không chạm bậc cao cấp. Ở MỌI chế độ, câu tầm thường gọi **0 vai**.

## 5. Vòng phản hồi chất lượng — đã đóng

`.router/v4/benchmark-reasoning.jsonl` (tệp RIÊNG, không trộn lịch sử worker):

```
reasoning_strategist  antigravity/gemini-3.8-flash-high      32.6s ok=True  verdict=—       proj=fanfic
reasoning_strategist  antigravity/gemini-3.8-flash-high      21.7s ok=True  verdict=—       proj=fanfic
reasoning_reviewer    antigravity/claude-opus-4-6-thinking   97.0s ok=True  verdict=REVISE  proj=fanfic
```

Mỗi bản ghi mang: vai (`task_type`), provider/model/runtime, **dự án**, mốc
thời gian, thời gian tường ĐO ĐƯỢC, kết quả, `verdict` trong bộ ĐÓNG, số
phát hiện của Reviewer, số lần thử lại, và **tham chiếu rubric** (trỏ về
chính mục §3 này). `tokens`/`cost_usd` = `None` — nhà cung cấp không lộ ra,
và `None` không bao giờ bị thay bằng `0`.

**Chưa đủ mẫu để lấn át tiên nghiệm**: `summary_for` đòi `MAU_TOI_THIEU = 3`
mẫu cho CÙNG `(model, task_type)`; hiện có 2 Strategist + 1 Reviewer, nên
tổng hợp đo được = **0**. Đó là đúng thiết kế — một model thắng một lần
không được coi là "100% đáng tin". Cơ chế đã sống; số liệu sẽ tích luỹ theo
lần dùng thật.

## 6. Khuyết tật tìm ra trong lần chạy thật

**Thanh trên giữ chế độ CŨ tới 30 giây.** Ô chọn và chip chỉ đồng bộ trong
`veInspSnapshotTuCache()` — đường ảnh chụp `git`, có bộ đệm 30s vì nó chạy
~6 lệnh `git`. Đổi chế độ ở một tab thì tab kia vẫn hiện giá trị cũ: người
dùng tưởng mình đang ở MAX trong khi sổ ghi AUTO. Đo được bằng Chrome thật,
không bằng bài kiểm nào.

Sửa: `snapshot()` mang thêm `che_do` (một phép đọc SQLite rẻ) → vào dấu vân
tay WebSocket → `veCheDo()` đồng bộ theo NHỊP NHANH, và không ghi đè khi ô
đang được mở. Có bài kiểm khoá lại, và đã xác minh lại bằng Chrome thật.

## 7. An toàn

* **Production mutation: 0.** Mọi phép chạm production là CHỈ ĐỌC qua
  `ProductionProbeBroker` (thao tác CÓ KIỂU, lưới chặn động từ đột biến,
  không nâng quyền). Không `restart`, `deploy`, `upload`, `chmod` nào.
* **Việc tạo ra: 0.** Đếm TRƯỚC/SAU cả phiên: 14 → 14. Cả bốn tình huống
  đều là thảo luận, và cả bốn đều giữ nguyên là thảo luận.
* **Không rò token.** Token phiên đọc từ nhật ký của chính ứng dụng vào bộ
  nhớ, không in ra, không vào tệp kết quả.
* Không merge, không tag, không push. Không tích hợp chatgpt-web.

## 8. Giới hạn còn lại (đo được, KHÔNG sửa ở v0.8)

1. **Trần ngữ cảnh của Reviewer (3400 token) quá chật khi bản chiến lược
   dài.** Ở TH4, bản chiến lược + câu người dùng chiếm hết, nên `vien_nang`,
   `ky_uc` và `trang_thai_kho` đều bị cắt — và Reviewer mất đúng thứ nó cần
   để xác minh một mã ràng buộc. Nó xử lý đúng (nói ra, hạ phán xử REVISE)
   nên **đây không phải một lần nghiệm thu hỏng**; nhưng chất lượng phản
   biện bị giới hạn bởi một hằng số. Sửa đúng là một con số trong
   `vai.HO_SO_VAI`, không phải kiến trúc mới — để v0.9 quyết dựa trên số
   liệu tích luỹ, đúng nguyên tắc "không thêm kiến trúc khi chưa có bằng
   chứng bắt buộc".
2. **Chưa đủ mẫu benchmark** (mục §5) — cơ chế sống, dữ liệu cần thời gian.
3. **`gpt-6-astra` vẫn chưa có placement nào** — đường leo thang kiểm được
   đầu-cuối trong fabric bài kiểm, chưa bật trên fabric thật.
4. **Phần "redesign" của Strategist còn chung chung** (R5 = 1). Một trần ngữ
   cảnh rộng hơn cho Strategist, hoặc một vòng truy hồi viên nang theo mục,
   có thể là câu trả lời — nhưng cần số liệu, không nên đoán.
