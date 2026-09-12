"""PHÂN LOẠI HỎNG và LẬP LẠI KẾ HOẠCH CÓ TRẦN — V0.9, §9 và §19.

`reasoning/that_bai.py` của V0.8 đã phân loại hỏng của MỘT LƯỢT VAI, và tệp
này KHÔNG chép lại nó — nó DÙNG nó rồi thêm bốn loại mà chỉ tầng thực thi mới
thấy được:

    KE_HOACH_SAI   bước chạy đúng nhưng kế hoạch sai -> lập lại kế hoạch
    PHU_THUOC      bước hỏng vì bước nó phụ thuộc hỏng -> không thử lại NÓ
    CAU_HINH_QUYEN hồ sơ quyền/worktree chưa tin cậy -> §23 đòi báo RIÊNG
    THAM_QUYEN     chạm ranh giới người dùng phải duyệt -> DỪNG, không thử lại

BA LUẬT, và mỗi luật ứng với một vòng lặp vô hạn có thật:

1. **Trần là HAI con số.** Trần THỬ LẠI mỗi bước chặn một bước quay vòng;
   trần LẬP LẠI KẾ HOẠCH của cả lần thực thi chặn "bước nào cũng thử 2 lần
   rồi lập lại kế hoạch, rồi lại thế". Thiếu con số thứ hai là lỗi hay gặp.
2. **BẤT ĐỒNG KHÔNG PHẢI LỖI VẬN CHUYỂN.** Kế thừa nguyên vẹn từ
   `that_bai.LoaiThatBai.VIEC`: một Reviewer nói REJECT đã làm ĐÚNG việc của
   nó. Đi tìm model khác cho cùng câu hỏi là đi mua một ý kiến dễ chịu hơn.
3. **LẬP LẠI KẾ HOẠCH KHÔNG ĐƯỢC BỎ TIÊU CHÍ NGHIỆM THU.** `ke_hoach.
   ban_moi` giữ `nghiem_thu` mặc định, và `so_sanh_ban` nêu đích danh nếu
   một tiêu chí bị bỏ — nên "sửa cho đạt" bằng cách hạ chuẩn hiện ra trong
   lịch sử thay vì biến mất.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.ket_qua import (HopDongKetQua,
                                                      TrangThaiXacMinh)
from scripts.control_center.reasoning.that_bai import (LoaiThatBai,
                                                       phan_loai_that_bai)

#: Trần THỬ LẠI của MỘT bước. §9: *"normal retry/replan count <= 2"*.
TRAN_THU_LAI_BUOC = 2
#: Trần LẬP LẠI KẾ HOẠCH của cả lần thực thi.
TRAN_LAP_KE_HOACH = 2
#: Trần ĐỊNH TUYẾN LẠI (đổi provider) của MỘT bước. Thấp hơn trần thử lại có
#: chủ đích: §9 cấm *"provider-shop indefinitely"*, và mỗi lần đổi nhà cung
#: cấp là một lần tiêu hạn mức ở một bể mới.
TRAN_DINH_TUYEN_LAI = 2


class LoaiHong(str, Enum):
    """Tám loại. Mỗi loại có MỘT cách xử lý, và chúng khác nhau thật."""

    LOI_HIEN_THUC = "LOI_HIEN_THUC"
    THIEU_BANG_CHUNG = "THIEU_BANG_CHUNG"
    PROVIDER = "PROVIDER"
    KE_HOACH_SAI = "KE_HOACH_SAI"
    PHU_THUOC = "PHU_THUOC"
    NANG_LUC = "NANG_LUC"
    CAU_HINH_QUYEN = "CAU_HINH_QUYEN"
    THAM_QUYEN = "THAM_QUYEN"
    #: KHONG PHAI mot lan hong cua VIEC — viec chua tung duoc giao cho ai.
    #: Tach rieng vi da bi lan voi `PROVIDER` mot lan va ton nhieu ngay chan
    #: doan: het khe phien thi khong mot luot nao duoc goi, ket qua rong y
    #: het mot luot provider chet, va bao cao di ket luan "provider hong"
    #: trong khi lan chay do khong he goi provider. Xem `sessions.py` luat 2b.
    CHUA_GIAO = "CHUA_GIAO"

    @property
    def mo_ta(self) -> str:
        return {
            "LOI_HIEN_THUC": "lỗi hiện thực — mã sai, không phải hạ tầng sai",
            "THIEU_BANG_CHUNG": "chạy rồi nhưng không chứng minh được",
            "PROVIDER": "nhà cung cấp / tiến trình hỏng",
            "KE_HOACH_SAI": "bước làm đúng nhưng kế hoạch sai",
            "PHU_THUOC": "phụ thuộc hỏng nên bước này không chạy được",
            "NANG_LUC": "chỗ chạy không làm được loại việc này",
            "CAU_HINH_QUYEN": "hồ sơ quyền / cấu hình chặn — KHÔNG phải lỗi việc",
            "THAM_QUYEN": "chạm ranh giới người dùng phải duyệt",
            "CHUA_GIAO": "việc CHƯA TỪNG được giao — không có lượt nào để đánh giá",
        }[self.value]

    @property
    def la_cau_hinh(self) -> bool:
        """§23: lỗi quyền/cấu hình phải được báo RIÊNG, không lẫn lỗi việc."""
        return self is LoaiHong.CAU_HINH_QUYEN


class HanhDongPhucHoi(str, Enum):
    THU_LAI = "THU_LAI"
    DINH_TUYEN_LAI = "DINH_TUYEN_LAI"
    TAO_VIEC_SUA = "TAO_VIEC_SUA"
    LAP_LAI_KE_HOACH = "LAP_LAI_KE_HOACH"
    DUNG_CHO_NGUOI = "DUNG_CHO_NGUOI"
    BO_QUA = "BO_QUA"

    @property
    def ton_mot_luot(self) -> bool:
        return self in (HanhDongPhucHoi.THU_LAI, HanhDongPhucHoi.DINH_TUYEN_LAI,
                        HanhDongPhucHoi.TAO_VIEC_SUA)


#: Mẫu nhận dạng lỗi CẤU HÌNH/QUYỀN. Kiểm TRƯỚC mọi thứ khác: một thư mục
#: chưa được tin cậy làm hồ sơ quyền của kho biến mất (đo được, ghi trong
#: `docs/reports/QUYEN_CLAUDE_TIN_CAY.md`), và triệu chứng của nó trông y hệt
#: một agent "từ chối làm việc" — tức là sẽ bị xếp nhầm vào NANG_LUC rồi bị
#: định tuyến lại vòng quanh, trong khi thứ cần sửa là một dòng cấu hình.
import re as _re
_MAU_CAU_HINH: Tuple[_re.Pattern, ...] = tuple(_re.compile(m, _re.I) for m in (
    r"\bthư mục chưa được tin\b", r"\bdirectory (is )?not trusted\b",
    r"\bpermission (profile|rule)s? (missing|not loaded)\b",
    r"\bhồ sơ quyền\b.{0,30}\b(thiếu|không nạp|biến mất)\b",
    r"\bsettings\.json\b.{0,40}\b(missing|not found|invalid)\b",
    r"\bhook\b.{0,30}\b(not registered|chưa đăng ký)\b",
    r"\bworktree\b.{0,30}\b(không tồn tại|missing|not found)\b",
    r"\bENOENT\b.{0,40}\b(config|settings)\b",
    r"\bchưa cấu hình\b", r"\bnot configured\b",
))
_MAU_THAM_QUYEN: Tuple[_re.Pattern, ...] = tuple(_re.compile(m, _re.I) for m in (
    r"\brequires?_decision\b", r"\bcần (người|bạn) (duyệt|quyết định)\b",
    r"\bgated\b", r"\bwaiting[_\s]authority\b",
    r"\bproduction\b.{0,30}\b(approval|duyệt)\b",
))


@dataclass(frozen=True)
class ChanDoan:
    """Kết luận về MỘT lần hỏng, kèm hành động. Dữ liệu, không phải log."""

    loai: LoaiHong
    hanh_dong: HanhDongPhucHoi
    ly_do: str
    con_lai: int = 0
    bang_chung: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {"loai": self.loai.value, "loai_mo_ta": self.loai.mo_ta,
                "hanh_dong": self.hanh_dong.value, "ly_do": self.ly_do,
                "con_lai": self.con_lai, "bang_chung": list(self.bang_chung),
                "la_cau_hinh": self.loai.la_cau_hinh}


def _khop(mau: Sequence[_re.Pattern], van: str) -> List[str]:
    ra = []
    for m in mau:
        x = m.search(van or "")
        if x:
            ra.append(x.group(0)[:60])
    return ra


def phan_loai_hong(*, ket_qua: Optional[HopDongKetQua] = None,
                   xac_minh: Optional[TrangThaiXacMinh] = None,
                   loi: str = "", phu_thuoc_hong: bool = False,
                   chua_giao: bool = False) -> ChanDoan:
    """Một lần hỏng -> loại. TẤT ĐỊNH, không LLM.

    Thứ tự kiểm có nghĩa và mỗi bước đứng trước một bước khác vì một lý do:

    * PHU_THUOC trước hết — thử lại một bước có phụ thuộc hỏng là chắc chắn
      tốn một lượt cho không.
    * CAU_HINH_QUYEN trước NANG_LUC — xem chú thích `_MAU_CAU_HINH`.
    * THAM_QUYEN trước mọi thứ còn lại — một việc dừng ở cổng KHÔNG hỏng.
    * THIEU_BANG_CHUNG cuối cùng, và chỉ khi không có tín hiệu hỏng nào
      khác: nó nghĩa là lượt chạy ổn nhưng lời khai chưa đủ.
    """
    van = " ".join(x for x in [
        loi, (ket_qua.summary if ket_qua else ""),
        " ".join(ket_qua.warnings) if ket_qua else "",
        (ket_qua.status if ket_qua else "")] if x)

    if phu_thuoc_hong:
        return ChanDoan(LoaiHong.PHU_THUOC, HanhDongPhucHoi.BO_QUA,
                        "bước phụ thuộc đã hỏng — không thử lại bước này")

    # CHUA_GIAO đứng ngay sau PHU_THUOC và TRƯỚC mọi phép đọc văn bản: khi
    # không có lượt nào chạy thì `van` rỗng, và mọi bộ nhận dạng bên dưới sẽ
    # đoán mò trên một chuỗi rỗng. Riêng `rong=True` còn đoán THẲNG ra
    # `RUNTIME` -> `PROVIDER`, tức là đổ lỗi cho một nhà cung cấp chưa hề
    # được gọi. ĐỊNH TUYẾN LẠI ở đây là vô nghĩa (không chỗ chạy nào "tốt
    # hơn" khi vấn đề là hết khe), nên hành động đúng là THỬ LẠI.
    if chua_giao or (ket_qua is not None and ket_qua.chua_chay):
        return ChanDoan(LoaiHong.CHUA_GIAO, HanhDongPhucHoi.THU_LAI,
                        ("việc chưa từng được giao cho một phiên nào — không "
                         "có lượt agent nào để đánh giá; đây là chuyện SỨC "
                         "CHỨA, không phải chất lượng của việc hay của nhà "
                         "cung cấp"))

    bc = _khop(_MAU_CAU_HINH, van)
    if bc:
        return ChanDoan(LoaiHong.CAU_HINH_QUYEN, HanhDongPhucHoi.DUNG_CHO_NGUOI,
                        ("lỗi CẤU HÌNH/QUYỀN, không phải lỗi việc — thử lại "
                         "hay đổi provider đều không sửa được"),
                        bang_chung=tuple(bc))
    bt = _khop(_MAU_THAM_QUYEN, van)
    if bt or (ket_qua is not None and ket_qua.status == "blocked"):
        return ChanDoan(LoaiHong.THAM_QUYEN, HanhDongPhucHoi.DUNG_CHO_NGUOI,
                        "chạm ranh giới thẩm quyền — cần người duyệt",
                        bang_chung=tuple(bt))

    lt, vs = phan_loai_that_bai(
        loi=loi, van_ban=(ket_qua.summary if ket_qua else ""),
        rong=bool(ket_qua is not None and ket_qua.rong))
    if lt is LoaiThatBai.NANG_LUC:
        return ChanDoan(LoaiHong.NANG_LUC, HanhDongPhucHoi.DINH_TUYEN_LAI,
                        f"chỗ chạy không làm được: {vs}")
    if lt in (LoaiThatBai.QUOTA, LoaiThatBai.RUNTIME):
        return ChanDoan(
            LoaiHong.PROVIDER,
            (HanhDongPhucHoi.DINH_TUYEN_LAI if lt is LoaiThatBai.QUOTA
             else HanhDongPhucHoi.THU_LAI),
            f"nhà cung cấp/tiến trình: {vs}")
    if lt is LoaiThatBai.XAC_THUC:
        return ChanDoan(LoaiHong.CAU_HINH_QUYEN, HanhDongPhucHoi.DUNG_CHO_NGUOI,
                        f"mất xác thực: {vs} — không có đường tự động nào sửa")

    if xac_minh is TrangThaiXacMinh.THIEU_BANG_CHUNG:
        return ChanDoan(LoaiHong.THIEU_BANG_CHUNG, HanhDongPhucHoi.TAO_VIEC_SUA,
                        ("lượt chạy ổn nhưng chưa chứng minh được — cần một "
                         "việc thu thập bằng chứng, không phải chạy lại từ đầu"))
    if xac_minh is TrangThaiXacMinh.KHONG_DAT:
        return ChanDoan(LoaiHong.LOI_HIEN_THUC, HanhDongPhucHoi.TAO_VIEC_SUA,
                        "phép kiểm tất định KHÔNG đạt — lỗi hiện thực")
    return ChanDoan(LoaiHong.LOI_HIEN_THUC, HanhDongPhucHoi.THU_LAI,
                    f"không phân loại rõ ({vs}) — thử lại một lần")


@dataclass
class NganSachPhucHoi:
    """Đếm của MỘT lần thực thi. Hai con số, không phải một."""

    so_lan_thu_theo_buoc: Dict[str, int] = field(default_factory=dict)
    so_lan_dinh_tuyen_lai: Dict[str, int] = field(default_factory=dict)
    so_lan_lap_ke_hoach: int = 0

    def con_thu_duoc(self, buoc_id: str) -> int:
        return max(0, TRAN_THU_LAI_BUOC
                   - int(self.so_lan_thu_theo_buoc.get(buoc_id, 0)))

    def con_dinh_tuyen_duoc(self, buoc_id: str) -> int:
        return max(0, TRAN_DINH_TUYEN_LAI
                   - int(self.so_lan_dinh_tuyen_lai.get(buoc_id, 0)))

    @property
    def con_lap_ke_hoach_duoc(self) -> int:
        return max(0, TRAN_LAP_KE_HOACH - int(self.so_lan_lap_ke_hoach))

    def to_dict(self) -> Dict:
        return {"so_lan_thu_theo_buoc": dict(self.so_lan_thu_theo_buoc),
                "so_lan_dinh_tuyen_lai": dict(self.so_lan_dinh_tuyen_lai),
                "so_lan_lap_ke_hoach": self.so_lan_lap_ke_hoach,
                "tran_thu_lai": TRAN_THU_LAI_BUOC,
                "tran_lap_ke_hoach": TRAN_LAP_KE_HOACH,
                "tran_dinh_tuyen_lai": TRAN_DINH_TUYEN_LAI}


def ap_tran(cd: ChanDoan, ns: NganSachPhucHoi, buoc_id: str) -> ChanDoan:
    """Áp TRẦN lên một chẩn đoán. Đây là chỗ vòng lặp vô hạn chết.

    Hết lượt thử thì KHÔNG im lặng bỏ cuộc: chẩn đoán đổi sang
    `LAP_LAI_KE_HOACH` (nếu còn ngân sách kế hoạch) hoặc `DUNG_CHO_NGUOI`.
    Cả hai đều là trạng thái NHÌN THẤY ĐƯỢC — một lần thực thi kẹt phải hiện
    ra ở giao diện, không phải nằm im ở `RUNNING`.
    """
    hd = cd.hanh_dong
    if hd is HanhDongPhucHoi.THU_LAI and ns.con_thu_duoc(buoc_id) <= 0:
        return _het_luot(cd, ns, buoc_id,
                         f"đã thử lại {TRAN_THU_LAI_BUOC} lần")
    if hd is HanhDongPhucHoi.DINH_TUYEN_LAI and \
            ns.con_dinh_tuyen_duoc(buoc_id) <= 0:
        return _het_luot(cd, ns, buoc_id,
                         f"đã đổi nhà cung cấp {TRAN_DINH_TUYEN_LAI} lần")
    if hd is HanhDongPhucHoi.TAO_VIEC_SUA and ns.con_thu_duoc(buoc_id) <= 0:
        return _het_luot(cd, ns, buoc_id,
                         f"đã sửa {TRAN_THU_LAI_BUOC} lần mà vẫn không đạt")
    if hd is HanhDongPhucHoi.LAP_LAI_KE_HOACH and \
            ns.con_lap_ke_hoach_duoc <= 0:
        return ChanDoan(cd.loai, HanhDongPhucHoi.DUNG_CHO_NGUOI,
                        (f"{cd.ly_do} — và đã lập lại kế hoạch "
                         f"{TRAN_LAP_KE_HOACH} lần; dừng để bạn xem"),
                        0, cd.bang_chung)
    con = {HanhDongPhucHoi.THU_LAI: ns.con_thu_duoc(buoc_id),
           HanhDongPhucHoi.TAO_VIEC_SUA: ns.con_thu_duoc(buoc_id),
           HanhDongPhucHoi.DINH_TUYEN_LAI: ns.con_dinh_tuyen_duoc(buoc_id),
           HanhDongPhucHoi.LAP_LAI_KE_HOACH: ns.con_lap_ke_hoach_duoc,
           }.get(hd, 0)
    return ChanDoan(cd.loai, hd, cd.ly_do, con, cd.bang_chung)


def _het_luot(cd: ChanDoan, ns: NganSachPhucHoi, buoc_id: str,
              vi_sao: str) -> ChanDoan:
    if ns.con_lap_ke_hoach_duoc > 0:
        return ChanDoan(
            cd.loai, HanhDongPhucHoi.LAP_LAI_KE_HOACH,
            (f"{cd.ly_do} — {vi_sao} ở bước {buoc_id}; cạn lượt thử nên "
             f"vấn đề có thể ở KẾ HOẠCH, không ở bước"),
            ns.con_lap_ke_hoach_duoc, cd.bang_chung)
    return ChanDoan(cd.loai, HanhDongPhucHoi.DUNG_CHO_NGUOI,
                    f"{cd.ly_do} — {vi_sao} và cạn cả ngân sách kế hoạch",
                    0, cd.bang_chung)
