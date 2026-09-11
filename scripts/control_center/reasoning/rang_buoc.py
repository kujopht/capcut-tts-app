"""KHỐI RÀNG BUỘC — thẩm quyền cao nhất trong gói ngữ cảnh — V0.9, §16.

KHUYẾT TẬT ĐO ĐƯỢC CỦA V0.8, và tệp này là câu trả lời cho nó:

    Nghiệm thu model thật, kịch bản 4: gói Reviewer dùng 2724/3400 token,
    các khối `vien_nang`/`ky_uc`/`trang_thai_kho` bị cắt, nên Reviewer KHÔNG
    xác minh được ràng buộc `ku_668f6cce0b6de423`. Nó xử lý đúng (nói ra, hạ
    `REVISE`) — nhưng chất lượng phản biện bị một hằng số giới hạn.

YÊU CẦU §16 CẤM cách sửa hiển nhiên: *"Do NOT simply raise context limits
globally."* Nên có hai nửa, và cả hai đều cần:

1. **DỰNG khối `rang_buoc` cho đúng.** V0.8 không hề dựng khối đó — thứ đi
   vào gói chỉ là `vien_nang` và `ky_uc` chung, nên ràng buộc phải cạnh
   tranh với lịch sử dự án trong cùng một cục văn bản. Ở đây ràng buộc là
   một khối RIÊNG, xếp theo THẨM QUYỀN, không theo độ mới.
2. **DÀNH RIÊNG ngân sách cho nó** (`ngu_canh.SAN_DANH_RIENG`), và khi vẫn
   không vừa thì GỌN LẠI thay vì biến mất — bản gọn giữ đúng những mục
   thẩm quyền cao nhất và NÊU TÊN những mục đã lược.

THỨ TỰ THẨM QUYỀN, cố định và không phụ thuộc độ mới:

    1. Quyết định ĐANG HIỆU LỰC người dùng tuyên bố tường minh
    2. Ràng buộc AN TOÀN / PRODUCTION
    3. Ràng buộc khác đang hiệu lực
    4. Yêu cầu (requirement) đang hiệu lực
    5. Quyết định đang hiệu lực có thẩm quyền thấp hơn

Một mẩu `episodic` tuần trước KHÔNG BAO GIỜ đẩy được mục 1 ra khỏi gói —
đó chính là điều §16 đòi chứng minh.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.control_center.memory.model import uoc_token

#: Thứ tự thẩm quyền của nguồn gốc một bản ghi. Số NHỎ = cao hơn.
BAC_TIN_CAY: Dict[str, int] = {
    "user_explicit": 0, "do_duoc": 1, "ghi_nhan": 2, "backfill": 3,
    "leader": 4, "suy_luan": 5,
}

#: Mẫu nhận dạng ràng buộc AN TOÀN / PRODUCTION. Một ràng buộc khớp mẫu này
#: được nâng lên ngang hàng quyết định tường minh: nó là loại ràng buộc mà
#: vi phạm gây thiệt hại KHÔNG ĐẢO ĐƯỢC, nên nó không được xếp sau một yêu
#: cầu tính năng chỉ vì bản ghi mới hơn.
_AN_TOAN = tuple(re.compile(m, re.I) for m in (
    r"\bproduction\b", r"\bprod\b", r"\bdeploy\b", r"\bsecret\b", r"\bbí mật\b",
    r"\bcredential\b", r"\bIAM\b", r"\bkhông được\b", r"\bkhông bao giờ\b",
    r"\bnever\b", r"\bmust not\b", r"\bcấm\b", r"\bxoá\b", r"\bdelete\b",
    r"\bdestructive\b", r"\bphá huỷ\b", r"\brestart\b", r"\bkhởi động lại\b",
))

#: Nhãn hiển thị theo loại. Người đọc (và model) phải phân biệt được một
#: QUYẾT ĐỊNH với một YÊU CẦU: cái đầu ràng buộc cách làm, cái sau mô tả
#: cái phải có.
_NHAN_LOAI: Dict[str, str] = {
    "decision": "QUYẾT ĐỊNH", "constraint": "RÀNG BUỘC",
    "requirement": "YÊU CẦU", "procedural": "QUY TRÌNH", "fact": "SỰ THẬT",
}


@dataclass(frozen=True)
class MucRangBuoc:
    """MỘT mục, đã biết thứ hạng thẩm quyền của nó."""

    ma: str
    loai: str
    noi_dung: str
    tieu_de: str = ""
    tin_cay: str = "ghi_nhan"
    quan_trong: int = 5
    an_toan: bool = False

    @property
    def bac(self) -> int:
        """Thứ hạng — số NHỎ đứng trước. Xem bảng ở docstring module."""
        tc = BAC_TIN_CAY.get(self.tin_cay, 9)
        if self.loai == "decision" and tc == 0:
            return 0
        if self.an_toan:
            return 1
        if self.loai == "constraint":
            return 2
        if self.loai == "requirement":
            return 3
        if self.loai == "decision":
            return 4
        return 5

    @property
    def khoa_sap(self) -> Tuple[int, int, int]:
        return (self.bac, BAC_TIN_CAY.get(self.tin_cay, 9),
                -int(self.quan_trong or 0))

    def dong(self) -> str:
        nhan = _NHAN_LOAI.get(self.loai, self.loai.upper())
        dau = f"[{nhan} {self.ma}"
        if self.tin_cay == "user_explicit":
            dau += " · NGƯỜI DÙNG TUYÊN BỐ"
        if self.an_toan:
            dau += " · AN TOÀN/PRODUCTION"
        dau += "]"
        than = (self.tieu_de + ": " if self.tieu_de else "") + self.noi_dung
        return f"{dau} {than.strip()}"

    def to_dict(self) -> Dict:
        return {"ma": self.ma, "loai": self.loai, "tieu_de": self.tieu_de,
                "tin_cay": self.tin_cay, "bac": self.bac,
                "an_toan": self.an_toan, "quan_trong": self.quan_trong}


def la_an_toan(van: str) -> bool:
    return any(m.search(van or "") for m in _AN_TOAN)


@dataclass
class KhoiRangBuoc:
    """Khối đã xếp hạng. `render(tran)` trả bản vừa ngân sách, có kê khai."""

    muc: Tuple[MucRangBuoc, ...] = ()

    @property
    def rong(self) -> bool:
        return not self.muc

    def xep(self) -> List[MucRangBuoc]:
        return sorted(self.muc, key=lambda m: m.khoa_sap)

    def render(self, tran_token: int = 0) -> Tuple[str, Tuple[str, ...]]:
        """`(văn bản, mã những mục đã lược)`.

        Cắt TỪ DƯỚI LÊN theo thẩm quyền — mục bậc 0/1 ra khỏi gói sau cùng.
        Và mục bị lược được NÊU TÊN bằng mã, không chỉ đếm: đó là đúng bài
        học của V0.7 mà `ngu_canh.py` đã ghi lại (một dòng chỉ-đếm khiến một
        lượt bịa ra "5 Antigravity account" trong khi sổ ghi 8).
        """
        ds = self.xep()
        if not ds:
            return "", ()
        dau = ("Đây là những điều ĐANG RÀNG BUỘC dự án. Thứ tự là thứ tự "
               "THẨM QUYỀN, không phải thứ tự thời gian. Một đề xuất mâu "
               "thuẫn với bất kỳ dòng nào dưới đây là một đề xuất SAI, "
               "không phải một đánh đổi.")
        if not tran_token:
            return "\n".join([dau] + [m.dong() for m in ds]), ()

        # DUNG ROI DO, KHONG DOAN TRUOC. Dong bao luoc CHINH NO ton token, va
        # no dai ra theo so ma bi luoc — nen tru mot hang so cho no la sai ở
        # đúng trường hợp tệp này tồn tại để xử: rất nhiều ràng buộc, rất ít
        # ngân sách. Vòng lặp bỏ dần từ DƯỚI LÊN rồi đo lại; nó dừng sau
        # nhiều nhất `len(ds)` vòng.
        n = len(ds)
        while n >= 0:
            giu = ds[:n]
            luoc = [m.ma for m in ds[n:]]
            d = [dau] + [m.dong() for m in giu]
            if luoc:
                d.append(
                    f"(!) CÒN {len(luoc)} RÀNG BUỘC/QUYẾT ĐỊNH CHƯA NẠP Ở "
                    f"LƯỢT NÀY: {', '.join(luoc)}. Danh sách đó KHÔNG phải "
                    f"giấy phép để đoán — bị hỏi về chúng thì nói rõ 'chưa "
                    f"nạp ở lượt này' rồi HỎI.")
            van = "\n".join(d)
            if uoc_token(van) <= tran_token or n == 0:
                return van, tuple(luoc)
            n -= 1
        return "", tuple(m.ma for m in ds)          # khong bao gio toi day

    def ke_khai(self) -> Dict:
        return {"so_muc": len(self.muc),
                "theo_bac": {str(b): sum(1 for m in self.muc if m.bac == b)
                             for b in sorted({m.bac for m in self.muc})},
                "muc": [m.to_dict() for m in self.xep()]}


#: Loại ký ức đi vào khối ràng buộc. `episodic`/`incident`/`architecture`
#: KHÔNG vào: chúng là bối cảnh, không phải luật, và để chúng tranh chỗ ở
#: đây là tái tạo đúng vấn đề mà §16 tồn tại để sửa.
LOAI_RANG_BUOC: Tuple[str, ...] = ("decision", "constraint", "requirement")


def dung_khoi(dv_ky_uc: Any, project_id: str, *,
              toi_da_moi_loai: int = 40) -> KhoiRangBuoc:
    """Dựng khối từ ký ức dự án. FAIL SOFT: không có ký ức thì khối rỗng.

    Chỉ lấy bản ghi ĐANG HIỆU LỰC. Một quyết định đã bị thay thế vẫn tra
    được trong sổ, nhưng đưa nó vào khối ràng buộc là bảo model tuân theo
    một luật không còn hiệu lực.
    """
    if dv_ky_uc is None or not getattr(dv_ky_uc, "kich_hoat", False):
        return KhoiRangBuoc()
    muc: List[MucRangBuoc] = []
    for loai in LOAI_RANG_BUOC:
        try:
            kq = dv_ky_uc.liet_ke(project_id, loai, limit=toi_da_moi_loai)
        except Exception:                                   # noqa: BLE001
            continue
        if not kq or not kq.get("san_sang"):
            continue
        for x in (kq.get("ket_qua") or []):
            m = _muc(x, loai)
            if m is not None:
                muc.append(m)
    # Khu trung theo ma: mot quyet dinh xuat hien ca o `decision` lan o ban
    # ghi ky uc goc cua no.
    theo_ma: Dict[str, MucRangBuoc] = {}
    for m in muc:
        cu = theo_ma.get(m.ma)
        if cu is None or m.khoa_sap < cu.khoa_sap:
            theo_ma[m.ma] = m
    return KhoiRangBuoc(muc=tuple(theo_ma.values()))


def _muc(x: Dict, loai: str) -> Optional[MucRangBuoc]:
    if not isinstance(x, dict):
        return None
    k = x.get("ky_uc") if isinstance(x.get("ky_uc"), dict) else x
    tt = str(x.get("trang_thai") or k.get("trang_thai") or "hieu_luc")
    if tt not in ("hieu_luc", "HIEU_LUC"):
        return None
    noi = str(k.get("noi_dung") or "").strip()
    if not noi:
        return None
    tieu = str(k.get("tieu_de") or "")
    return MucRangBuoc(
        ma=str(x.get("ma") or k.get("ma") or "?"),
        loai=loai, noi_dung=noi[:600], tieu_de=tieu[:120],
        tin_cay=str(k.get("tin_cay") or "ghi_nhan"),
        quan_trong=int(k.get("quan_trong") or 5),
        an_toan=la_an_toan(noi + " " + tieu))
