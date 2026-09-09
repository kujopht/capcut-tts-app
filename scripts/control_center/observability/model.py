"""Từ vựng trạng thái SỐNG của một dự án, và bằng chứng đi kèm.

VÌ SAO GÓI NÀY TỒN TẠI — một lỗi đúng đắn kiến trúc, đã gặp thật:

    Người dùng: "production farmer còn chạy không?"
    Leader    : (Router có 0 việc đang chạy) -> "không có gì đang chạy"
    Thực tế   : `fanfic-farmer` trên AWS đang chạy và khoẻ.

Leader suy ra trạng thái của một HỆ THỐNG BÊN NGOÀI từ số việc của
Router. Hai thứ đó không liên quan gì nhau: Router đếm việc do CHÍNH NÓ
điều phối, còn con farmer là một systemd service trên một máy khác, chạy
độc lập, không hề đi qua Router. "Router rảnh" và "production đã dừng" là
hai câu khác nhau, và gộp chúng lại là bịa.

Nên `TrangThai` dưới đây tách rành rẽ SÁU khả năng. Ba cái cuối là ba
cách "không biết" KHÁC NHAU, và trộn chúng lại chính là cái lỗi ở trên:

    ACTIVE      đo được, và nó đang chạy
    DEGRADED    đo được, đang chạy nhưng có dấu hiệu xấu
    DOWN        ĐO ĐƯỢC, và nó KHÔNG chạy — một khẳng định, cần bằng chứng
    UNKNOWN     có probe, nhưng lần đo này thất bại (mạng, quá hạn…)
    UNAVAILABLE KHÔNG có probe nào cho thứ này trên máy/cấu hình hiện tại
    STALE       có số, nhưng cũ hơn ngưỡng tin được

`DOWN` là thứ duy nhất trong ba trạng thái "không tốt" mang nghĩa khẳng
định. `UNKNOWN`/`UNAVAILABLE` KHÔNG được hiển thị, tóm tắt, hay đưa vào
ngữ cảnh Leader như thể là `DOWN`. Cùng luật với `usage.py`: không đo được
thì nói không đo được, không điền `0`.

MỖI QUAN SÁT MANG THEO NGUỒN GỐC. Một con số không có nguồn và không có
mốc thời gian thì Leader không thể xếp nó vào đúng bậc thẩm quyền (xem
`tham_quyen.py`), và người đọc không biết nó vừa đo hay đọc từ bộ đệm.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TrangThai(str, Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"

    @property
    def do_duoc(self) -> bool:
        """Lần đo này có ra kết luận về hệ thống thật hay không."""
        return self in (TrangThai.ACTIVE, TrangThai.DEGRADED,
                        TrangThai.DOWN)

    @property
    def la_khang_dinh_xau(self) -> bool:
        """CHỈ `DOWN`. `UNKNOWN`/`UNAVAILABLE`/`STALE` không phải."""
        return self is TrangThai.DOWN

    @property
    def dang_song(self) -> bool:
        return self in (TrangThai.ACTIVE, TrangThai.DEGRADED)


#: Bậc xấu dần, để `overall_state` lấy cái tệ nhất trong các quan sát ĐO
#: ĐƯỢC. `UNKNOWN`/`UNAVAILABLE` KHÔNG tham gia phép so này — chúng
#: không nói gì về hệ thống, nên không được kéo tổng thể xuống `DOWN`.
_NANG_DAN = {TrangThai.ACTIVE: 0, TrangThai.DEGRADED: 1, TrangThai.DOWN: 2}


@dataclass
class QuanSat:
    """MỘT phép đo, kèm nguồn gốc.

    `gia_tri` là số/chuỗi thật (PID, round, số việc…) hoặc `None` khi
    không đo được — không bao giờ là một giá trị bù cho chỗ trống.
    """

    khoa: str
    trang_thai: TrangThai
    gia_tri: Any = None
    #: Ai đo. Ví dụ `"ssh:13.212.224.218"`, `"router:store"`, `"git"`.
    nguon: str = ""
    #: Thời điểm đo THẬT, không phải lúc dựng gói tin.
    do_luc: float = field(default_factory=time.time)
    #: Bao lâu thì con số này hết tin được. `0` = không đặt hạn.
    han_tuoi: float = 0.0
    #: Lý do khi `UNKNOWN`/`UNAVAILABLE`. BẮT BUỘC có, xem `__post_init__`.
    ly_do: str = ""
    #: Bằng chứng thô đã LỌC BÍ MẬT, để người đọc kiểm lại được.
    bang_chung: str = ""
    nhan: str = ""

    def __post_init__(self) -> None:
        # Mot quan sat "khong biet" ma khong noi VI SAO thi vo dung: nguoi
        # doc khong phan biet duoc "chua cau hinh" voi "mang loi", va
        # Leader khong the noi mot cau trung thuc ve no.
        if self.trang_thai in (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE):
            if not self.ly_do:
                raise ValueError(
                    f"{self.khoa}: {self.trang_thai.value} phải kèm `ly_do`")
            if self.gia_tri is not None:
                raise ValueError(
                    f"{self.khoa}: {self.trang_thai.value} không được mang "
                    f"giá trị ({self.gia_tri!r}) — đó là bịa số")

    @property
    def tuoi(self) -> float:
        return max(0.0, time.time() - self.do_luc)

    @property
    def qua_han(self) -> bool:
        return bool(self.han_tuoi) and self.tuoi > self.han_tuoi

    def hieu_luc(self) -> TrangThai:
        """Trạng thái SAU KHI xét tuổi.

        Một số đo được nhưng đã quá hạn thì thành `STALE`: nó không còn
        trả lời được câu "BÂY GIỜ thế nào", và dùng nó như số hiện tại là
        đúng cái lỗi mà bậc thẩm quyền tồn tại để chặn.
        """
        if self.qua_han and self.trang_thai.do_duoc:
            return TrangThai.STALE
        return self.trang_thai

    def to_dict(self) -> Dict:
        return {"khoa": self.khoa, "trang_thai": self.hieu_luc().value,
                "trang_thai_do": self.trang_thai.value,
                "gia_tri": self.gia_tri, "nguon": self.nguon,
                "do_luc": self.do_luc, "tuoi": round(self.tuoi, 1),
                "han_tuoi": self.han_tuoi, "qua_han": self.qua_han,
                "ly_do": self.ly_do, "bang_chung": self.bang_chung,
                "nhan": self.nhan}


@dataclass
class KhoiQuanSat:
    """Một nhóm quan sát của MỘT thứ được theo dõi (một service, một kho).

    `trang_thai` của khối là cái xấu nhất trong các quan sát ĐO ĐƯỢC. Nếu
    không quan sát nào đo được thì khối mang `UNKNOWN`/`UNAVAILABLE` —
    KHÔNG phải `DOWN`.
    """

    khoa: str
    nhan: str = ""
    quan_sat: List[QuanSat] = field(default_factory=list)
    ly_do: str = ""

    def them(self, q: QuanSat) -> "KhoiQuanSat":
        self.quan_sat.append(q)
        return self

    def lay(self, khoa: str) -> Optional[QuanSat]:
        for q in self.quan_sat:
            if q.khoa == khoa:
                return q
        return None

    @property
    def trang_thai(self) -> TrangThai:
        do_duoc = [q.hieu_luc() for q in self.quan_sat
                   if q.hieu_luc().do_duoc]
        if do_duoc:
            return max(do_duoc, key=lambda t: _NANG_DAN[t])
        hl = [q.hieu_luc() for q in self.quan_sat]
        if any(t is TrangThai.STALE for t in hl):
            return TrangThai.STALE
        if any(t is TrangThai.UNKNOWN for t in hl):
            return TrangThai.UNKNOWN
        if hl:
            return TrangThai.UNAVAILABLE
        return TrangThai.UNAVAILABLE

    @property
    def do_luc(self) -> float:
        return max((q.do_luc for q in self.quan_sat), default=0.0)

    def to_dict(self) -> Dict:
        return {"khoa": self.khoa, "nhan": self.nhan,
                "trang_thai": self.trang_thai.value,
                "ly_do": self.ly_do or self._ly_do_gop(),
                "do_luc": self.do_luc,
                "quan_sat": [q.to_dict() for q in self.quan_sat]}

    def _ly_do_gop(self) -> str:
        ds = [q.ly_do for q in self.quan_sat if q.ly_do]
        return ds[0] if ds else ""


@dataclass
class AnhChupSong:
    """`ProjectLiveSnapshot` — trạng thái SỐNG của một dự án ở một thời điểm.

    `router` được giữ TÁCH RIÊNG khỏi `dich_vu`/`luu_tru`/`ung_dung`, và
    đó là điểm chính của cả gói này: hai thứ đó trả lời hai câu hỏi khác
    nhau, nên chúng không bao giờ được gộp vào một con số "đang chạy".
    """

    project_id: str = ""
    thu_luc: float = field(default_factory=time.time)
    #: Trạng thái Router — việc/agent do CHÍNH Control Center điều phối.
    router: Dict[str, KhoiQuanSat] = field(default_factory=dict)
    #: Dịch vụ BÊN NGOÀI (systemd trên máy khác, tiến trình cục bộ…).
    dich_vu: Dict[str, KhoiQuanSat] = field(default_factory=dict)
    luu_tru: Dict[str, KhoiQuanSat] = field(default_factory=dict)
    ung_dung: Dict[str, KhoiQuanSat] = field(default_factory=dict)
    kho: Dict[str, KhoiQuanSat] = field(default_factory=dict)
    #: Provider nào đã chạy, mất bao lâu, có lỗi gì.
    nhat_ky_provider: List[Dict] = field(default_factory=list)

    #: DỊCH VỤ SỐNG bên ngoài — thứ trả lời câu "nó còn chạy không".
    #:
    #: `kho` (git) CỐ Ý không nằm ở đây. Kho git là **trạng thái bền của
    #: dự án** — bậc 2 trong `tham_quyen.py` — không phải một dịch vụ
    #: đang chạy. Trộn nó vào đây gây ra hai lỗi thật, cả hai đã gặp ở
    #: lần nghiệm thu V0.5 đầu:
    #:
    #: * một kho "bẩn" (có tệp chưa commit) làm `trang_thai_chung` thành
    #:   `DEGRADED` trong khi dịch vụ production hoàn toàn khoẻ;
    #: * một lần `git status` thành công làm `co_bang_chung_dich_vu()`
    #:   thành `True` dù probe SSH đã thất bại — nên Leader KHÔNG còn
    #:   nhận được câu "chưa xác minh được", đúng lúc nó cần nhất.
    NHOM_DICH_VU = ("dich_vu", "luu_tru", "ung_dung")
    #: Mọi nhóm KHÔNG phải Router (gồm cả `kho`), để liệt kê/hiển thị.
    NHOM_NGOAI = NHOM_DICH_VU + ("kho",)

    def moi_khoi(self) -> List[KhoiQuanSat]:
        ra: List[KhoiQuanSat] = []
        for ten in ("router",) + self.NHOM_NGOAI:
            ra.extend(getattr(self, ten).values())
        return ra

    def khoi_ngoai(self) -> List[KhoiQuanSat]:
        ra: List[KhoiQuanSat] = []
        for ten in self.NHOM_NGOAI:
            ra.extend(getattr(self, ten).values())
        return ra

    def khoi_dich_vu(self) -> List[KhoiQuanSat]:
        """Chỉ DỊCH VỤ SỐNG — không Router, không kho git."""
        ra: List[KhoiQuanSat] = []
        for ten in self.NHOM_DICH_VU:
            ra.extend(getattr(self, ten).values())
        return ra

    @property
    def trang_thai_chung(self) -> TrangThai:
        """Tổng thể của DỊCH VỤ SỐNG bên ngoài.

        Không tính Router (Router rảnh không làm dự án "DOWN" — đó chính
        là lỗi gốc) và không tính kho git (một tệp chưa commit không làm
        production "DEGRADED").
        """
        kh = self.khoi_dich_vu()
        do_duoc = [k.trang_thai for k in kh if k.trang_thai.do_duoc]
        if do_duoc:
            return max(do_duoc, key=lambda t: _NANG_DAN[t])
        tt = [k.trang_thai for k in kh]
        for t in (TrangThai.STALE, TrangThai.UNKNOWN):
            if t in tt:
                return t
        return TrangThai.UNAVAILABLE

    @property
    def tuoi(self) -> float:
        return max(0.0, time.time() - self.thu_luc)

    def co_bang_chung_song(self) -> bool:
        """Có ÍT NHẤT một DỊCH VỤ SỐNG đo được trong lần này.

        Leader dùng cờ này để biết mình có quyền nói một câu khẳng định
        về hệ thống bên ngoài hay không. CỐ Ý không tính kho git: một
        lần `git status` thành công KHÔNG cho ai quyền nói gì về việc
        `fanfic-farmer` còn chạy hay không.
        """
        return any(k.trang_thai.do_duoc for k in self.khoi_dich_vu())

    def to_dict(self) -> Dict:
        d: Dict = {"project_id": self.project_id, "thu_luc": self.thu_luc,
                   "tuoi": round(self.tuoi, 1),
                   "trang_thai_chung": self.trang_thai_chung.value,
                   "trang_thai_kho": (
                       max([k.trang_thai for k in self.kho.values()],
                           key=lambda t: _NANG_DAN.get(t, -1)).value
                       if self.kho else TrangThai.UNAVAILABLE.value),
                   "co_bang_chung_song": self.co_bang_chung_song(),
                   "nhat_ky_provider": list(self.nhat_ky_provider)}
        for ten in ("router",) + self.NHOM_NGOAI:
            d[ten] = {k: v.to_dict() for k, v in getattr(self, ten).items()}
        return d
