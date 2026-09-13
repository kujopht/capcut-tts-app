# -*- coding: utf-8 -*-
"""CHỜ TÀI NGUYÊN — chính sách định tuyến lại / chờ / leo thang (V1.0).

Hết hạn mức **không phải** một lần hỏng. Không ai làm sai, mã sản phẩm không
sai, và phần lớn trường hợp Router tự đi tiếp được — bằng một tài khoản khác,
một bể khác, hoặc đơn giản là đợi tới mốc reset ĐÃ ĐO ĐƯỢC.

Tệp này giữ ĐÚNG MỘT câu hỏi: *"tài nguyên không dùng được — làm gì tiếp?"*
Nó là một hàm THUẦN, không chạm sổ, không chạm mạng, nên nó kiểm được bằng
fixture tất định mà **không phải đốt hạn mức thật để dựng lại cảnh cạn**.

BA KẾT CỤC, và ranh giới giữa chúng là ranh giới thẩm quyền:

    ĐỔI CHỖ   còn một đường tài nguyên HỢP LỆ -> đi, không hỏi ai
    CHỜ RESET không còn đường, nhưng CÓ mốc reset đo được -> hẹn giờ, giữ việc
    LEO THANG không còn đường VÀ không có mốc nào -> mới gọi người

LUẬT KHÔNG ĐƯỢC PHÁ:

1. **Không bao giờ mua thêm.** Không credit, không overage, không nâng gói.
   Hết tiền là một ranh giới THẨM QUYỀN, và nó thuộc về chủ sở hữu.
2. **Không hạ chuẩn để đi tiếp.** Một đường thay thế chỉ hợp lệ khi nó còn
   thoả yêu cầu vai/chất lượng và tính ĐỘC LẬP của phản biện. Đổi sang một
   model rẻ hơn cho xong việc là mua một ý kiến dễ chịu hơn.
3. **`UNKNOWN` vẫn là `UNKNOWN`.** Không đo được mốc reset thì KHÔNG bịa ra
   một cái. Một mốc bịa biến "chờ có cơ sở" thành "thử lại vô hạn có lịch".
4. **Không tự thêm tài khoản/credential.** Cũng là ranh giới thẩm quyền.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.v10.han_muc import BeQuota, SucKhoe


class HanhDongTaiNguyen(str, Enum):
    DOI_CHO = "DOI_CHO"              # có đường khác hợp lệ -> đi ngay
    CHO_RESET = "CHO_RESET"          # hết đường, có mốc đo được -> hẹn giờ
    LEO_THANG = "LEO_THANG"          # hết đường, không mốc -> gọi người


#: Trần số lần CHỜ RESET cho một sự cố. Chờ có lịch vẫn phải có đáy: một bể
#: cứ hứa reset rồi lại cạn là một vòng lặp chậm, và vòng lặp chậm vẫn là
#: vòng lặp. Hết trần thì leo thang kèm bằng chứng.
TRAN_CHO_RESET = 3

#: Không hẹn lại quá xa: một mốc reset 48 giờ là thật, nhưng một hệ chạy qua
#: đêm cần chủ sở hữu BIẾT điều đó thay vì im lặng ngủ hai ngày.
TRAN_CHO_GIAY = 6 * 3600.0


@dataclass
class YeuCauVai:
    """Ràng buộc mà một đường thay thế PHẢI còn thoả.

    Đây là chỗ luật "không hạ chuẩn để đi tiếp" được viết thành mã.
    """

    #: Họ model bị CẤM — ví dụ phản biện không được cùng họ với người viết.
    ho_bi_cam: Tuple[str, ...] = ()
    #: Chỉ chấp nhận các họ này, nếu vai đòi hỏi (rỗng = không ràng buộc).
    ho_bat_buoc: Tuple[str, ...] = ()
    #: Vai này có đòi phản biện ĐỘC LẬP không (ảnh hưởng cách chọn).
    doi_doc_lap: bool = False
    #: Mô tả ngắn, đi vào bằng chứng.
    mo_ta: str = ""


@dataclass
class QuyetDinhTaiNguyen:
    hanh_dong: HanhDongTaiNguyen
    ly_do: str = ""
    #: Bể được chọn khi `DOI_CHO`.
    be_chon: Optional[str] = None
    #: Mốc reset đo được khi `CHO_RESET`. `None` = không đo được.
    cho_toi: Optional[float] = None
    #: Các bể đã XÉT và vì sao bị loại — bằng chứng, không phải trang trí.
    da_xet: Tuple[Tuple[str, str], ...] = ()
    #: Có cần chủ sở hữu làm gì không (mua credit / thêm tài khoản / hạ chuẩn).
    can_chu_so_huu: bool = False

    def to_dict(self) -> Dict:
        return {"hanh_dong": self.hanh_dong.value, "ly_do": self.ly_do,
                "be_chon": self.be_chon, "cho_toi": self.cho_toi,
                "da_xet": [list(x) for x in self.da_xet],
                "can_chu_so_huu": self.can_chu_so_huu}


def _hop_le(be: BeQuota, yc: YeuCauVai) -> Tuple[bool, str]:
    """Bể này có còn là một đường HỢP LỆ cho vai ấy không?"""
    if be.suc_khoe is SucKhoe.EXHAUSTED:
        return False, "đã cạn"
    if be.suc_khoe is SucKhoe.AUTH_REQUIRED:
        # Sửa được, nhưng chỉ CHỦ SỞ HỮU sửa được — không phải đường tự đi.
        return False, "cần đăng nhập lại (thẩm quyền chủ sở hữu)"
    if be.suc_khoe is SucKhoe.UNAVAILABLE:
        return False, "nhà cung cấp không dùng được"
    ho = tuple(be.ho_model or ())
    if yc.ho_bi_cam and ho and all(h in yc.ho_bi_cam for h in ho):
        # CHẶN CỨNG, không phải ưu tiên mềm: đây là chỗ "phản biện phải KHÁC
        # họ" sống hay chết. Một lần đổi chỗ vì hết quota KHÔNG được phép
        # lặng lẽ xoá mất tính độc lập đã cất công dựng.
        return False, f"họ {'/'.join(ho)} bị cấm cho vai này (độc lập)"
    if yc.ho_bat_buoc and ho and not any(h in yc.ho_bat_buoc for h in ho):
        return False, f"họ {'/'.join(ho)} không thoả yêu cầu vai"
    return True, ""


def quyet_dinh(be_hong: Optional[BeQuota], cac_be: Sequence[BeQuota], *,
               yeu_cau: Optional[YeuCauVai] = None,
               da_cho: int = 0, bay_gio: Optional[float] = None
               ) -> QuyetDinhTaiNguyen:
    """Tài nguyên không dùng được — đổi chỗ, chờ, hay gọi người?

    `be_hong` là bể vừa cạn (có thể `None` nếu không biết bể nào).
    `cac_be` là MỌI bể đã khai, gồm cả `be_hong`.
    `da_cho` là số lần sự cố này đã CHỜ RESET rồi — trần ở `TRAN_CHO_RESET`.
    """
    yc = yeu_cau or YeuCauVai()
    gio = bay_gio if bay_gio is not None else time.time()
    ten_hong = be_hong.ten if be_hong is not None else ""
    xet: List[Tuple[str, str]] = []

    # 1. CÒN ĐƯỜNG NÀO KHÔNG? Ưu tiên bể đo được và còn nhiều, rồi tới bể
    #    UNKNOWN — loại bể UNKNOWN ra là tự bỏ đói mình, vì phần lớn nhà
    #    cung cấp không phơi số.
    ung_vien: List[BeQuota] = []
    for b in cac_be:
        if b.ten == ten_hong:
            xet.append((b.ten, "bể vừa cạn"))
            continue
        ok, vi_sao = _hop_le(b, yc)
        if ok:
            ung_vien.append(b)
        else:
            xet.append((b.ten, vi_sao))

    if ung_vien:
        ung_vien.sort(key=lambda b: (
            0 if b.do_duoc else 1,
            -(b.con_lai if b.con_lai is not None else 0.0),
            b.hong_gan_day))
        chon = ung_vien[0]
        return QuyetDinhTaiNguyen(
            hanh_dong=HanhDongTaiNguyen.DOI_CHO, be_chon=chon.ten,
            ly_do=(f"còn đường tài nguyên hợp lệ: {chon.ten}"
                   + (f" (họ {'/'.join(chon.ho_model)})"
                      if chon.ho_model else "")
                   + " — đổi chỗ, không cần hỏi ai"),
            da_xet=tuple(xet))

    # 2. HẾT ĐƯỜNG. Có mốc reset ĐO ĐƯỢC không?
    #
    #    Chỉ nhận mốc THẬT SỰ có trong dữ liệu. Không đo được thì đi tiếp
    #    xuống nhánh leo thang — KHÔNG đắp một mốc mặc định vào, vì một mốc
    #    bịa biến "chờ có cơ sở" thành "thử lại vô hạn có lịch".
    moc: List[Tuple[float, str]] = []
    for b in cac_be:
        if b.reset_luc is not None and b.reset_luc > gio:
            ok, _ = _hop_le(b, yc)
            # Bể đang cạn vẫn được kể ở đây: cạn + có mốc = đúng thứ ta chờ.
            if ok or b.suc_khoe is SucKhoe.EXHAUSTED:
                moc.append((float(b.reset_luc), b.ten))
    if moc:
        moc.sort()
        khi, ten = moc[0]
        if da_cho >= TRAN_CHO_RESET:
            return QuyetDinhTaiNguyen(
                hanh_dong=HanhDongTaiNguyen.LEO_THANG,
                ly_do=(f"đã chờ reset {da_cho} lần mà vẫn cạn — chờ có lịch "
                       f"vẫn phải có đáy, nếu không nó là một vòng lặp chậm"),
                da_xet=tuple(xet), can_chu_so_huu=True)
        if khi - gio > TRAN_CHO_GIAY:
            return QuyetDinhTaiNguyen(
                hanh_dong=HanhDongTaiNguyen.LEO_THANG, cho_toi=khi,
                ly_do=(f"mốc reset gần nhất ({ten}) còn "
                       f"{(khi - gio) / 3600:.1f} giờ — quá xa để im lặng "
                       f"chờ; chủ sở hữu cần biết"),
                da_xet=tuple(xet), can_chu_so_huu=True)
        return QuyetDinhTaiNguyen(
            hanh_dong=HanhDongTaiNguyen.CHO_RESET, cho_toi=khi, be_chon=ten,
            ly_do=(f"hết đường thay thế, nhưng {ten} có mốc reset ĐO ĐƯỢC "
                   f"sau {(khi - gio) / 60:.0f} phút — giữ việc, hẹn giờ "
                   f"chạy tiếp. KHÔNG mua thêm credit."),
            da_xet=tuple(xet))

    # 3. HẾT ĐƯỜNG, KHÔNG MỐC. Đây mới là lúc gọi người.
    return QuyetDinhTaiNguyen(
        hanh_dong=HanhDongTaiNguyen.LEO_THANG,
        ly_do=("không còn đường tài nguyên hợp lệ và KHÔNG đo được mốc reset "
               "nào — cần chủ sở hữu quyết (thêm tài khoản, đợi thủ công, "
               "hoặc nới yêu cầu vai). KHÔNG tự mua credit, KHÔNG tự thêm "
               "credential, KHÔNG tự hạ chuẩn."),
        da_xet=tuple(xet), can_chu_so_huu=True)
