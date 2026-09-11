"""Kiến trúc SUY LUẬN NHIỀU VAI của Project Leader — V0.8.

V0.7 cho Leader ký ức, viên nang, quan sát sống, bằng chứng vận hành. Cái
nó KHÔNG cho: một bộ não thứ hai. Mọi câu — từ "ê bro" tới "có nên migrate
kiến trúc lưu trữ không" — đi qua ĐÚNG một lượt của ĐÚNG một model rẻ
(`gemini-3.8-flash-high`, ghim trong `leader.MODEL_LEADER`).

Với câu hỏi trạng thái thì thế là đúng và rẻ. Với một câu hỏi kiến trúc thì
đó là một model nhanh đóng vai chuyên gia — và không có ai phản biện nó.

V0.8 tách VAI ra khỏi MODEL:

    LEADER      sở hữu hội thoại, quyết có cần suy luận sâu hơn không,
                tổng hợp câu trả lời cuối. Vẫn rẻ, vẫn chạy mọi lượt.
    STRATEGIST  kiến trúc, lộ trình, đánh đổi, chiến lược gỡ lỗi khó.
    REVIEWER    phản biện ĐỘC LẬP bản chiến lược — khác họ model khi làm
                được, và báo DEGRADED khi không, chứ không giả vờ độc lập.
    EXECUTOR    Router V4 nguyên vẹn. Gói này KHÔNG thay nó.

BỐN LUẬT CỦA GÓI NÀY, mỗi luật có bài kiểm khoá lại:

1. **Không phải lượt nào cũng gọi đủ vai.** Một câu chào, một câu tra cứu
   sổ, một câu hỏi trạng thái sống — không vai nào được gọi, ở MỌI chế độ
   chất lượng, kể cả MAX. `phan_loai.CONG_TAM_THUONG` là rào cứng, không
   phải một ưu tiên mềm.
2. **Thảo luận KHÔNG phải thực thi.** Một đề xuất do Strategist sinh ra
   không tự biến thành việc. Chỉ `HoiDong` trả `la_thuc_thi=True` khi
   NGƯỜI DÙNG xin làm — xem `phan_loai.py` mục THỰC THI.
3. **Không bịa số dùng.** Nhà cung cấp không lộ ra usage thì bản ghi định
   tuyến mang `None` + `UNAVAILABLE`, không mang `0`. Cùng luật với
   `control_center/usage.py` và `router_v4/premium.py`.
4. **Chính sách dự án đến từ KÝ ỨC, không từ hằng số trong mã.** Quyết định
   "GPT-6 Astra chỉ dành cho việc đặc biệt khó" nằm ở ký ức dự án Fanfic
   (`qd_0001`, đo thật 2026-09-11). `chinh_sach.py` TRA nó; mặc định khi
   không tra được là HẠN CHẾ — một mặc định thận trọng không giống một
   hằng số chép cứng.
"""
from __future__ import annotations

from scripts.control_center.reasoning.chinh_sach import (ChinhSachCaoCap,
                                                         doc_chinh_sach)
from scripts.control_center.reasoning.dinh_tuyen import (BoDinhTuyenVai,
                                                         ChonVai, KhongCoCho)
from scripts.control_center.reasoning.goi import (BoGoiGia, BoGoiThat, LuotVai)
from scripts.control_center.reasoning.hoi_dong import (HoiDong, KetQuaHoiDong,
                                                       NguonGocVai)
from scripts.control_center.reasoning.hop_dong import (BanChienLuoc,
                                                       BanPhanBien, PhanXu,
                                                       doc_ban_chien_luoc,
                                                       doc_ban_phan_bien)
from scripts.control_center.reasoning.ngan_sach import (BacChiPhi,
                                                        BanGhiDinhTuyen,
                                                        SoDinhTuyen)
from scripts.control_center.reasoning.ngu_canh import (GoiNguCanhVai,
                                                       KhoiNguCanh)
from scripts.control_center.reasoning.phan_loai import (Bac, KeHoachVai,
                                                        PhanLoai, TacDong,
                                                        lap_ke_hoach_vai,
                                                        phan_loai_luot)
from scripts.control_center.reasoning.that_bai import (ChinhSachThuLai,
                                                       LoaiThatBai,
                                                       phan_loai_that_bai)
from scripts.control_center.reasoning.vai import (HO_SO_VAI, VaiTro, ho_so)

__all__ = [
    "Bac", "BacChiPhi", "BanChienLuoc", "BanGhiDinhTuyen", "BanPhanBien",
    "BoDinhTuyenVai", "BoGoiGia", "BoGoiThat", "ChinhSachCaoCap",
    "ChinhSachThuLai", "ChonVai", "GoiNguCanhVai", "HO_SO_VAI", "HoiDong",
    "KeHoachVai", "KetQuaHoiDong", "KhoiNguCanh", "KhongCoCho", "LoaiThatBai",
    "LuotVai", "NguonGocVai", "PhanLoai", "PhanXu", "SoDinhTuyen", "TacDong",
    "VaiTro", "doc_ban_chien_luoc", "doc_ban_phan_bien", "doc_chinh_sach",
    "ho_so", "lap_ke_hoach_vai", "phan_loai_luot", "phan_loai_that_bai",
]
