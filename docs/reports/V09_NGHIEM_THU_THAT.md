# V0.9 — NGHIỆM THU THẬT: C 5/5 · D 5/5 · R 3/3

Nhánh `feat/v09-closed-loop-execution`. Sổ CHÍNH TẮC
(`%LOCALAPPDATA%\RouterControlCenter`), dự án Fanfic THẬT, agent THẬT.

## Kết quả

| Kịch bản | Yêu cầu | Kết quả | Thời gian |
|---|---|---|---|
| C — đa agent GHI THẬT, worktree cô lập | 5/5 | **5/5 · 25/25** | 1,1–1,5 phút |
| D — v1 trượt → sửa → v2 → DONE | 5/5 | **5/5 · 25/25** | 1,4–3,0 phút |
| R — khởi động lại GIỮA LÚC SỬA | 3/3 | **3/3 · 28/28** | 3,2–4,4 phút |
| Thay đổi production | 0 | **0** | — |
| Khởi động lại dịch vụ production | 0 | **0** | — |
| Nhắc quyền tương tác ngoài ý muốn | 0 | **0** | — |
| Kho Fanfic `main` | sạch | **sạch mọi lần** | — |

`kb_R` chứng minh ĐÚNG chuỗi, không phải "khởi động lại sau khi xong":
v1 chạy → trượt tiêu chí BẮT BUỘC → `PLAN_REVISED v1→v2` bền trên đĩa →
**tắt máy khi còn bước v2 dở dang** → mở lại trên CÙNG sổ → `recover()` →
cùng `execution_id`, v1 + bằng chứng hỏng còn nguyên, v2 đang hiệu lực,
không nhân đôi kế hoạch/việc, bước đã XONG không bị lùi, khoá đối soát,
sửa chạy tiếp → `VERIFYING → DONE` → Leader MỚI trả lời được trạng thái từ
sổ. Không bắt được cửa sổ thì kịch bản báo **VÔ HIỆU**, không bao giờ tự hạ
xuống PASS (`diem_dung_sua()`, 17 bài kiểm tất định).

## Khuyết tật SẢN PHẨM đã sửa (6)

Tất cả cùng một hình dạng: **hai cái nhìn về một sự thật, nói ngược nhau.**

1. **Cổng chấm worker trên một trường ta không bao giờ xin** — lời nhắc bắt
   khai vào `changes`, `parse_result` chỉ đọc `files_changed`. 9/9 việc ghi
   hỏng TẤT ĐỊNH. (`router_v3/packet.py`)
2. **Trần khe phiên thành BẾ KHOÁ** — luật 2 từ chối dùng lại một phiên RẢNH,
   luật 3 vẫn đếm nó rồi CHỜ nó; phiên rảnh không bao giờ "xong việc".
   Cộng hai nguồn rò: phiên dựng ở bước (2) không được trả lại khi (3)/(4)
   hỏng, và nhãn `current_task` chết không ai xoá. (`sessions.py`, `engine.py`)
3. **Lỗi SỨC CHỨA bị khai là lỗi NHÀ CUNG CẤP** — `rong` không phân biệt
   "chạy rồi, trả rỗng" với "chưa hề được giao". (`ket_qua.py`, `phuc_hoi.py`)
4. **Đối soát chữa trạng thái VIỆC mà không chữa PHONG BÌ** — việc `DONE`
   nhưng hợp đồng kết quả vẫn `failed`, nên tầng bước đi sửa một việc đã
   xong. (`engine.py`)
5. **Bước bị chấm trong cây ANH EM** — `moi_gioi_khac` thu thập đúng nhưng
   không truyền xuống, ở BA chỗ gọi (chấm đầu, chấm lại sau Reviewer, chấm
   lúc kết luận). Gom về `BoDieuPhoi.canh_kiem()`. (`kiem_dinh.py`,
   `dieu_phoi.py`, `engine.py`)
6. **Tiêu chí TUỲ CHỌN mượn được quyền CHẶN** qua một phán xử Reviewer
   TOÀN CỤC. Nay phán xử CÓ PHẠM VI (CRITERION/EXECUTION_GLOBAL/SAFETY) và
   thẩm quyền giống hệt luật của tiêu chí tất định; an toàn luôn thắng; lời
   chê KHUNG BÁO CÁO của Router không bao giờ thành "worker trượt".
   (`kiem_dinh.py`, gói tin Reviewer trong `engine.py`)

Cộng một khuyết tật thứ bảy phát hiện khi chạy R: **nhãn `BUSY` cũ chặn một
phạm vi ghi vĩnh viễn** — luật 1 tin `current_task` mù quáng; nay dùng chung
vị từ `_dang_giu_viec` với luật 2b. (`sessions.py`)

## Ô NHIỄM đã loại bỏ

Năm lần chạy hỏng liên tiếp KHÔNG do mã: hai tiến trình Control Center còn
sống từ hôm trước (`desktop` pid 11620, `webmain` pid 34188) chạy MÃ CŨ và
cùng ghi sổ chính tắc. Dấu vân tay: cùng một nhật ký có cả trần `X/12` lẫn
`X/3` — một tiến trình không in ra hai trần. Nay bộ nghiệm thu TỪ CHỐI CHẠY
khi còn tiến trình Control Center khác (thoát 3), và ĐỐI SOÁT khi mở giống
ba cửa vào thật.

## Ghi chú trung thực

Bảy khuyết tật nằm ở GIÀN GIÁO NGHIỆM THU, không phải sản phẩm: tên cột sai
(`plan_version` vs `phien_ban`), đọc "bản đang hiệu lực" thay vì bản mới
nhất, `ResourceLock` đọc như dict, bộ chạy đọc phải báo cáo CŨ khi bài kiểm
nổ, khẳng định khoá lọc theo đường dẫn thay vì theo chủ khoá, `buoc_id` hằng
gây đụng danh tính giữa các lần chạy, và một bài kiểm gọi `chi_doc=True` nên
KHÔNG hề chạm đường nó tự nhận là đang kiểm. Hai rào đã cứu cả đợt: VÔ HIỆU
không bao giờ tự hạ thành PASS, và bộ chạy từ chối in số khi báo cáo không
được ghi mới.
