"""Ý ĐỊNH THỰC THI — đối tượng hạng nhất, BỀN — V0.9, §2 và §4.

Yêu cầu §2: một ý định phải sống sót *"Leader context truncation, app restart,
provider restart, agent crash, new user chat/session, worktree recreation"*.
Nên nó KHÔNG được sống trong ngữ cảnh của Leader, và cũng không trong bộ nhớ
tiến trình: nó là một hàng trong sổ, và mọi thứ cần để tiếp tục đều nằm ở đó.

BA THỨ TỆP NÀY CỐ Ý KHÔNG LƯU:

1. **Dòng suy nghĩ.** §25 viết thẳng: *"No hidden chain-of-thought
   persistence."* `MOC_SUY_NGHI` liệt kê những mốc hay gặp, và
   `khong_suy_nghi()` cắt từ mốc đầu tiên trở đi. Lưu quyết định, tóm tắt lý
   do và THAM CHIẾU bằng chứng — không lưu vết suy luận.
2. **Bí mật.** Mọi văn bản đi vào sổ qua `redact` của `router_v3.packet`,
   cùng đường mà `store.ghi_su_kien` đã dùng.
3. **Thẩm quyền suy ra từ một câu mơ hồ.** `tham_quyen` được TÍNH từ
   `permissions.do_gated` trên CẢ mục tiêu lẫn câu gốc người dùng gõ, và một
   lần chạm là `NGOAI` + `CHO_NGUOI`. Không có cờ nào biến `NGOAI` thành
   `REPO_LOCAL`.

VÌ SAO `tieu_chi_dat` NẰM Ở Ý ĐỊNH, KHÔNG Ở TỪNG BƯỚC: §8. Bốn việc con cùng
báo DONE không có nghĩa mục tiêu gốc đã đạt. Tiêu chí nghiệm thu thuộc về
MỤC TIÊU, và `kiem_dinh.py` chấm điểm đúng danh sách này.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.trang_thai import TrangThaiThucThi
from scripts.control_center.permissions import GateHit, do_gated
from scripts.router_v3.packet import redact


class LopThamQuyen(str, Enum):
    """Hai lớp, và KHÔNG có lớp thứ ba — cùng nguyên tắc `PermissionClass`.

    `REPO_LOCAL` là thứ người dùng đã cho phép khi nói "làm đi": đọc kho, sửa
    trong worktree của mình, chạy test/build, commit trên nhánh tính năng.

    `NGOAI` là thứ có hậu quả ngoài kho: deploy, khởi động lại dịch vụ
    production, đổi dữ liệu thật, xoay bí mật, đẩy lên remote, mua thêm hạn
    mức. Một lần chạm là `WAITING_AUTHORITY`, và câu "ok làm đi" KHÔNG BAO
    GIỜ mở được nó — xem `can_tham_quyen_moi`.
    """

    REPO_LOCAL = "REPO_LOCAL"
    NGOAI = "NGOAI"

    @property
    def nhan(self) -> str:
        return ("việc trong kho (an toàn, đảo được)" if self is
                LopThamQuyen.REPO_LOCAL else
                "việc có hậu quả ra ngoài kho — CẦN BẠN DUYỆT")


class TrangThaiDuyet(str, Enum):
    """Cổng thẩm quyền của MỘT lần thực thi.

    `KHONG_CAN` không phải "đã duyệt": nó nghĩa là việc này nằm trọn trong
    lớp `REPO_LOCAL` mà người dùng đã cho phép bằng chính câu xin làm. Tách
    hai giá trị để bản kiểm toán nói được điều nào đã xảy ra.
    """

    KHONG_CAN = "KHONG_CAN"
    CHO_NGUOI = "CHO_NGUOI"
    DA_DUYET = "DA_DUYET"
    TU_CHOI = "TU_CHOI"


class MucRuiRo(str, Enum):
    THAP = "LOW"
    VUA = "MEDIUM"
    CAO = "HIGH"

    @property
    def rank(self) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}[self.value]


#: Mốc hay gặp của một vệt suy luận. Cắt TỪ mốc trở đi, không chỉ xoá dòng:
#: một khối `<thinking>` bị bỏ dòng mở vẫn còn nguyên thân.
MOC_SUY_NGHI: Tuple[str, ...] = (
    "<thinking", "</thinking", "<antthinking", "<scratchpad",
    "chain-of-thought", "chain of thought", "reasoning_trace",
    "Let me think step by step", "Hãy suy nghĩ từng bước",
)


def khong_suy_nghi(s: str, *, toi_da: int = 4000) -> str:
    """Cắt mọi vệt suy luận rồi khử bí mật. Dùng ở MỌI trường văn bản bền.

    Cắt chứ không xoá-khoảng-giữa: một mốc mở xuất hiện nghĩa là phần còn
    lại của chuỗi KHÔNG đáng tin là tóm tắt nữa.
    """
    v = str(s or "")
    thap = v.lower()
    cat = len(v)
    for m in MOC_SUY_NGHI:
        i = thap.find(m.lower())
        if i >= 0:
            cat = min(cat, i)
    v = v[:cat].strip()
    return redact(v)[:toi_da]


def _ds(v: Optional[Sequence[str]], *, toi_da: int = 40,
        dai: int = 400) -> Tuple[str, ...]:
    ra: List[str] = []
    for x in (v or ()):
        s = khong_suy_nghi(x, toi_da=dai)
        if s and s not in ra:
            ra.append(s)
        if len(ra) >= toi_da:
            break
    return tuple(ra)


#: Mẫu nhận dạng tiêu chí nghiệm thu do người dùng nói thẳng. Tất định.
_MAU_TIEU_CHI = tuple(re.compile(m, re.I) for m in (
    r"(?:phải|must|cần|need to|đảm bảo|ensure)\s+([^\.\n;]{6,160})",
    r"(?:test|tests|bài kiểm)\s+(?:phải\s+)?(?:pass|xanh|đạt)",
    r"(?:không được|must not|đừng)\s+([^\.\n;]{6,160})",
))


def tieu_chi_tu_cau(cau: str, *, toi_da: int = 6) -> Tuple[str, ...]:
    """Rút tiêu chí nghiệm thu TƯỜNG MINH từ câu người dùng. Không LLM.

    Cố ý NGHÈO: nó chỉ bắt thứ người dùng nói thẳng. Tiêu chí suy ra từ kế
    hoạch là việc của `ke_hoach.py`; trộn hai nguồn vào một chỗ sẽ làm mất
    phân biệt "người dùng đòi" với "máy tự nghĩ ra".
    """
    ra: List[str] = []
    for mau in _MAU_TIEU_CHI:
        for m in mau.finditer(cau or ""):
            doan = (m.group(0) or "").strip()
            if len(doan) < 6:
                continue
            doan = khong_suy_nghi(doan, toi_da=200)
            if doan and doan not in ra:
                ra.append(doan)
            if len(ra) >= toi_da:
                return tuple(ra)
    return tuple(ra)


@dataclass
class YDinhThucThi:
    """Một lần thực thi được UỶ QUYỀN. Bền qua khởi động lại."""

    execution_id: str
    project_id: str
    goal: str

    #: NGUỒN GỐC — nối về đúng câu người dùng gõ và đúng đề xuất nó chấp nhận.
    #: Thiếu hai trường này thì §1 không kiểm được: ta mất khả năng chứng minh
    #: một lần thực thi bắt nguồn từ NGƯỜI, không phải từ một lời khuyên.
    nguon_message_id: int = 0
    nguon_de_xuat: str = ""
    nguon_cau_nguoi_dung: str = ""

    pham_vi: Tuple[str, ...] = ()
    rang_buoc: Tuple[str, ...] = ()
    tieu_chi_dat: Tuple[str, ...] = ()

    tham_quyen: LopThamQuyen = LopThamQuyen.REPO_LOCAL
    duyet: TrangThaiDuyet = TrangThaiDuyet.KHONG_CAN
    duyet_boi: str = ""
    duyet_luc: float = 0.0
    rui_ro: MucRuiRo = MucRuiRo.THAP
    tac_dong_production: bool = False
    cong_gated: Tuple[Dict, ...] = ()

    trang_thai: TrangThaiThucThi = TrangThaiThucThi.DRAFT
    pha: str = ""
    ban_ke_hoach: int = 0
    so_lan_thu_lai: int = 0
    so_lan_lap_lai: int = 0
    ket_luan: str = ""
    ly_do_dung: str = ""

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ended_at: float = 0.0

    def __post_init__(self) -> None:
        self.goal = khong_suy_nghi(self.goal, toi_da=2000)
        if not self.goal:
            raise ValueError("YDinhThucThi: thiếu `goal` — không có gì để làm")
        self.ket_luan = khong_suy_nghi(self.ket_luan)
        self.ly_do_dung = khong_suy_nghi(self.ly_do_dung, toi_da=600)
        self.nguon_cau_nguoi_dung = khong_suy_nghi(
            self.nguon_cau_nguoi_dung, toi_da=2000)
        self.pham_vi = _ds(self.pham_vi)
        self.rang_buoc = _ds(self.rang_buoc)
        self.tieu_chi_dat = _ds(self.tieu_chi_dat)
        if isinstance(self.tham_quyen, str):
            self.tham_quyen = LopThamQuyen(self.tham_quyen)
        if isinstance(self.duyet, str):
            self.duyet = TrangThaiDuyet(self.duyet)
        if isinstance(self.rui_ro, str):
            self.rui_ro = MucRuiRo(self.rui_ro)
        if isinstance(self.trang_thai, str):
            self.trang_thai = TrangThaiThucThi(self.trang_thai)
        # BAT BIEN: lop NGOAI KHONG BAO GIO o `KHONG_CAN`.
        #
        # Day la cho de hong nhat cua ca V0.9: mot duong ma nao do dung
        # `YDinhThucThi(tham_quyen=NGOAI)` roi quen dat `duyet` se tao ra mot
        # y dinh cham production ma khong co cong nao. Nen bat bien nam o
        # constructor, khong o cho goi.
        if self.tham_quyen is LopThamQuyen.NGOAI and \
                self.duyet is TrangThaiDuyet.KHONG_CAN:
            self.duyet = TrangThaiDuyet.CHO_NGUOI

    # ------------------------------------------------------------ tinh chat --

    @property
    def can_tham_quyen_moi(self) -> bool:
        """Còn chờ người duyệt không? `True` thì KHÔNG được chạy bước NGOÀI."""
        return (self.tham_quyen is LopThamQuyen.NGOAI
                and self.duyet is not TrangThaiDuyet.DA_DUYET)

    @property
    def da_duyet_repo_local(self) -> bool:
        return (self.tham_quyen is LopThamQuyen.REPO_LOCAL
                or self.duyet is TrangThaiDuyet.DA_DUYET)

    @property
    def dang_song(self) -> bool:
        return not self.trang_thai.ket_thuc

    @property
    def giay_da_chay(self) -> float:
        return max(0.0, (self.ended_at or time.time()) - self.created_at)

    def to_dict(self) -> Dict:
        return {"execution_id": self.execution_id,
                "project_id": self.project_id, "goal": self.goal,
                "nguon_message_id": self.nguon_message_id,
                "nguon_de_xuat": self.nguon_de_xuat,
                "nguon_cau_nguoi_dung": self.nguon_cau_nguoi_dung,
                "pham_vi": list(self.pham_vi),
                "rang_buoc": list(self.rang_buoc),
                "tieu_chi_dat": list(self.tieu_chi_dat),
                "tham_quyen": self.tham_quyen.value,
                "duyet": self.duyet.value, "duyet_boi": self.duyet_boi,
                "duyet_luc": self.duyet_luc,
                "rui_ro": self.rui_ro.value,
                "tac_dong_production": self.tac_dong_production,
                "cong_gated": [dict(x) for x in self.cong_gated],
                "trang_thai": self.trang_thai.value,
                "trang_thai_nhan": self.trang_thai.nhan,
                "pha": self.pha, "ban_ke_hoach": self.ban_ke_hoach,
                "so_lan_thu_lai": self.so_lan_thu_lai,
                "so_lan_lap_lai": self.so_lan_lap_lai,
                "ket_luan": self.ket_luan, "ly_do_dung": self.ly_do_dung,
                "can_tham_quyen_moi": self.can_tham_quyen_moi,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "ended_at": self.ended_at,
                "giay_da_chay": round(self.giay_da_chay, 1)}


def phan_lop_tham_quyen(*van: str) -> Tuple[LopThamQuyen, Tuple[GateHit, ...]]:
    """`(lớp, bằng chứng)` từ văn bản. DÙNG LẠI `permissions.do_gated`.

    Một bộ dò thứ hai ở đây sẽ lệch khỏi bộ của V0.1 sau vài tháng, và lúc
    đó hai tầng sẽ bất đồng về việc gì là nguy hiểm. Nên chỉ có MỘT bộ dò.
    """
    hits = do_gated(*van)
    return (LopThamQuyen.NGOAI if hits else LopThamQuyen.REPO_LOCAL), hits


#: Thao tác GATED coi là CHẠM PRODUCTION. Hẹp có chủ đích: `remote_push` và
#: `billing_change` cần người duyệt nhưng KHÔNG đổi trạng thái production, và
#: gộp chúng vào sẽ làm con số "production mutation" của báo cáo nghiệm thu
#: mất nghĩa.
GATED_PRODUCTION: frozenset = frozenset({
    "production_deploy", "production_mutation", "iam_change",
    "secret_rotation", "resource_expansion"})


def tao_y_dinh(*, project_id: str, goal: str, cau_nguoi_dung: str = "",
               message_id: int = 0, de_xuat: str = "",
               pham_vi: Sequence[str] = (), rang_buoc: Sequence[str] = (),
               tieu_chi: Sequence[str] = (),
               rui_ro: Optional[MucRuiRo] = None) -> YDinhThucThi:
    """Dựng một ý định từ mục tiêu + câu gốc người dùng. TẤT ĐỊNH.

    Quét CẢ HAI văn bản tìm lớp GATED, đúng lý do `permissions.envelope_for`
    đã quét cả hai: bộ lập kế hoạch có thể diễn đạt lại "deploy lên
    production" thành "cập nhật cấu hình worker", và chỉ quét mục tiêu là bỏ
    lọt đúng trường hợp nguy hiểm nhất.
    """
    lop, hits = phan_lop_tham_quyen(goal, cau_nguoi_dung)
    ops = {h.operation for h in hits}
    cham_prod = bool(ops & GATED_PRODUCTION)
    if rui_ro is None:
        rui_ro = (MucRuiRo.CAO if cham_prod else
                  MucRuiRo.VUA if hits else MucRuiRo.THAP)
    tc = list(tieu_chi) or list(tieu_chi_tu_cau(cau_nguoi_dung or goal))
    return YDinhThucThi(
        execution_id="ex_" + uuid.uuid4().hex[:12],
        project_id=project_id, goal=goal,
        nguon_message_id=int(message_id or 0), nguon_de_xuat=de_xuat,
        nguon_cau_nguoi_dung=cau_nguoi_dung,
        pham_vi=tuple(pham_vi), rang_buoc=tuple(rang_buoc),
        tieu_chi_dat=tuple(tc),
        tham_quyen=lop,
        duyet=(TrangThaiDuyet.CHO_NGUOI if lop is LopThamQuyen.NGOAI
               else TrangThaiDuyet.KHONG_CAN),
        rui_ro=rui_ro, tac_dong_production=cham_prod,
        cong_gated=tuple({"operation": h.operation, "matched": h.matched}
                         for h in hits))


def cau_hoi_tham_quyen(y: YDinhThucThi) -> str:
    """Câu hỏi CỤ THỂ khi một lần thực thi dừng ở `WAITING_AUTHORITY`.

    Người dùng đọc dòng này giữa một cuộc trò chuyện. Nó phải nói được: mục
    tiêu nào, chạm cổng nào, bằng chứng khớp là gì — và rằng câu "ok làm đi"
    trước đó KHÔNG mở được cổng này.
    """
    if not y.cong_gated:
        return ""
    ops = ", ".join(dict.fromkeys(str(x.get("operation")) for x in y.cong_gated))
    bc = "; ".join(f"{x.get('operation')} (khớp: {x.get('matched')!r})"
                   for x in y.cong_gated)
    return (f"Lần thực thi `{y.execution_id}` chạm lớp NGOÀI KHO ({ops}) nên "
            f"nó DỪNG ở WAITING_AUTHORITY.\n\nMục tiêu: {y.goal}\n"
            f"Bằng chứng khớp: {bc}\n\n"
            f"Một câu \"ok làm đi\" cho phần việc trong kho KHÔNG mở cổng "
            f"này — cần bạn duyệt riêng, nói rõ bạn đồng ý thao tác nào.")
