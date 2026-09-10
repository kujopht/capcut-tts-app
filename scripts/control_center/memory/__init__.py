"""Ký ức dự án VÔ HẠN + ảo hoá ngữ cảnh (V0.6).

MỘT CÂU: lịch sử của một dự án được giữ TRỌN trên đĩa cục bộ, còn thứ đưa
vào một lượt của Leader/agent là một GÓI NGỮ CẢNH hữu hạn, chọn lọc, có
trần token ĐỘC LẬP với kích thước lịch sử.

    KÝ ỨC DỰ ÁN (không giới hạn, chỉ bởi đĩa)
            ↓  chọn lọc theo câu hỏi / độ mới / độ quan trọng / loại
    BỘ MÁY NGỮ CẢNH  (`goi_ngu_canh.py`)
            ↓  trần token, đo bằng BYTE
    gói ngữ cảnh hữu hạn
            ↓
    Leader / worker

BẬC THẨM QUYỀN — kế thừa V0.5 và mở rộng, KHÔNG đổi thứ tự:

    1. TRẠNG THÁI SỐNG        (vừa đo — `observability`)
    2. KHO / TRẠNG THÁI BỀN   (git, sổ)
    3. KÝ ỨC DỰ ÁN            (gói này)
    4. SUY LUẬN

Ký ức là BẰNG CHỨNG LỊCH SỬ. Nó không bao giờ trả lời một câu hỏi về HIỆN
TẠI khi có probe sống cho thứ được hỏi — và cái bẫy lớn nhất của gói này
(đã được reviewer độc lập chỉ ra trước khi viết dòng mã đầu) là: khối ký
ức có mặt Ở MỌI LƯỢT, còn khối sống chỉ có mặt ở lượt nào regex nhận ra
câu hỏi về hiện tại. Nên `leader.LUAT_KY_UC` đi kèm khối ký ức Ở MỌI LƯỢT
và nói thẳng: "không có khối sống" nghĩa là "chưa đo", KHÔNG nghĩa là "ký
ức là nguồn tốt nhất hiện có".

BỐN LỚP DỮ LIỆU (mượn phân lớp của TencentDB Agent Memory — MIT — nhưng
tất cả là HÀNG SQLite, không tệp Markdown):

    L0  `su_kien`     lịch sử THÔ, chỉ thêm, KHÔNG BAO GIỜ sửa/xoá ở V0.6
    L1  `ky_uc`       bản ghi có cấu trúc: episodic/semantic/decision/
                      procedural/incident/architecture — mỗi bản ghi TRỎ VỀ
                      sự kiện L0 sinh ra nó (`bang_chung`)
    L2  `vien_nang`   Viên nang dự án — bản tóm gọn có phiên bản, dựng lại
                      được từ L1
    L3  `diem_dung`   Điểm dừng — trạng thái việc đang làm, để một phiên
                      MỚI tiếp tục được mà không cần ai dán tay handoff

Mọi tóm tắt/chỉ mục là PHÓNG CHIẾU dựng lại được; nguồn sự thật là L0 +
kho blob địa chỉ hoá theo nội dung. Không có tóm tắt nào là bản duy nhất
còn lại của một thứ — đó là lỗi "tóm tắt rồi quên" mà gói này tồn tại để
tránh.

MỘT SỔ MỘT DỰ ÁN. `<gốc>/.router/memory/<ns>/memory.db` — cô lập bằng
TỆP, không bằng cột `project_id`: một truy vấn không thể lỡ tay đọc sang
dự án khác, một sổ hỏng chỉ hỏng một dự án. `<gốc>` là gốc dữ liệu của
Router (cạnh `control.db`), KHÔNG PHẢI cây git của dự án được quản — nên
không có gì để commit nhầm, và không bị nhân bản theo worktree của dự án.

KHÔNG có bí mật trong ký ức. Mọi văn bản qua `bi_mat.loc()` TRƯỚC khi chạm
đĩa; số lần lọc được ghi lại (`da_loc`), nội dung bị lọc thì không.

Phần này KHÔNG dựng: Artifact Vault/Drive, GitHub Stars Vault, self-updater,
ký ức ngữ nghĩa xuyên dự án, xoá/dọn lịch sử — chỉ để sẵn điểm nối.
"""
from scripts.control_center.memory.model import (  # noqa: F401
    BangChung, DiemDung, KyUc, LoaiKyUc, SuKien, TinCay, TrangThaiQuyetDinh,
    VienNang, QuyetDinh, uoc_token, chuan_hoa, khong_gian_ten)
from scripts.control_center.memory.provider import (  # noqa: F401
    MemoryProvider, LocalMemoryProvider, KHONG_DUOC_CO)
from scripts.control_center.memory.service import DichVuKyUc  # noqa: F401
