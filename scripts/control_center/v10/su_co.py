# -*- coding: utf-8 -*-
"""VÒNG SỰ CỐ TỰ CHỮA — V1.0 (B6).

    HỎNG -> THU BẰNG CHỨNG -> PHÂN LOẠI -> SỬA TẠI CHỖ -> KIỂM LẠI
         -> LẬP LẠI KẾ HOẠCH -> ĐỔI AGENT/MODEL -> HỘI ĐỒNG -> LEO THANG

"worker hỏng, nhờ người dùng debug" KHÔNG phải một kết cục bình thường.
Nhưng "thử lại mãi" cũng không: mỗi bước có TRẦN, và một chữ ký hỏng lặp lại
thì dừng thử mù và đổi cách.

HAI ĐIỀU HỌC ĐƯỢC TỪ CHÍNH ĐÊM V0.9.3, và chúng nằm trong thiết kế này:

1. **Chữ ký hỏng giống nhau ba lần = KHÔNG TIẾN TRIỂN.** Đêm đó mỗi lần hỏng
   là một nguyên nhân KHÁC nhau, nên thử lại là đúng. Nếu ba lần cùng một
   chữ ký thì thử lần bốn chỉ tốn quota.
2. **Một số hỏng KHÔNG phụ thuộc chỗ chạy.** `git rev-parse HEAD thất bại`
   hỏng y hệt ở mọi runtime. Đổi model cho loại đó là vô nghĩa — phải sửa
   môi trường. Phân loại tồn tại để biết cái nào là cái nào.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class LoaiHong(str, Enum):
    IMPLEMENTATION_ERROR = "IMPLEMENTATION_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    BUILD_FAILURE = "BUILD_FAILURE"
    # V1.0 — TÁCH HỎNG HẠ TẦNG KIỂM ĐỊNH KHỎI HỎNG SẢN PHẨM.
    #
    # Đo được trong chính bài nghiệm thu 2026-09-13: `scripts.test` viết là
    # `node --test tests/`, mà trên Node 24 + Windows câu đó nạp `tests` như
    # một MODULE và chết `MODULE_NOT_FOUND`. `rc=1`, nên cổng từ chối `DONE`
    # — đúng. Nhưng worker đã làm ĐÚNG: chạy lại đúng cây đó bằng lệnh đúng
    # cho 4/4 đạt.
    #
    # Gộp hai thứ này làm một dẫn tới hành động SAI: hệ đi sửa mã sản phẩm
    # (không hỏng) thay vì sửa lệnh kiểm (hỏng). Và nó đổ lỗi cho worker về
    # một việc nó làm đúng.
    INVALID_VERIFICATION_COMMAND = "INVALID_VERIFICATION_COMMAND"
    TEST_HARNESS_FAILURE = "TEST_HARNESS_FAILURE"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    AUTHORITY_FAILURE = "AUTHORITY_FAILURE"
    ORCHESTRATION_DEFECT = "ORCHESTRATION_DEFECT"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    STALE_STATE = "STALE_STATE"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    UNKNOWN = "UNKNOWN"


class HanhDong(str, Enum):
    """Bước TIẾP THEO của vòng — không phải một trạng thái."""

    SUA_MOI_TRUONG = "SUA_MOI_TRUONG"
    #: V1.0 — sửa LỆNH/HẠ TẦNG KIỂM ĐỊNH, không phải mã sản phẩm.
    #:
    #: Hành động khác hẳn `SUA_TAI_CHO`: chỗ cần sửa là manifest/script kiểm,
    #: và bằng chứng cần thu là "kho khai những lệnh nào" chứ không phải
    #: "mã sai ở đâu".
    SUA_HA_TANG_KIEM = "SUA_HA_TANG_KIEM"
    SUA_TAI_CHO = "SUA_TAI_CHO"
    LAP_LAI_KE_HOACH = "LAP_LAI_KE_HOACH"
    DOI_CHO_CHAY = "DOI_CHO_CHAY"
    CHO_QUOTA = "CHO_QUOTA"
    HOI_DONG = "HOI_DONG"
    LEO_THANG_CHU_SO_HUU = "LEO_THANG_CHU_SO_HUU"


#: Hỏng KHÔNG phụ thuộc chỗ chạy — đổi model/agent không cứu được.
#: Đổi chỗ cho những loại này là tốn một lượt để nhận đúng lỗi cũ.
KHONG_PHU_THUOC_CHO: frozenset = frozenset({
    LoaiHong.ENVIRONMENT_FAILURE,
    LoaiHong.ORCHESTRATION_DEFECT,
    LoaiHong.AUTHORITY_FAILURE,
    LoaiHong.STALE_STATE,
    LoaiHong.PERMISSION_FAILURE,
})

#: Hỏng nằm ở LỆNH/HẠ TẦNG KIỂM ĐỊNH, không ở mã sản phẩm.
#:
#: `rc != 0` KHÔNG phải bằng chứng rằng mã sản phẩm sai — nó chỉ nói "lệnh
#: này trả về khác 0". Nhóm này là những lần mà nguyên nhân nằm ở chính phép
#: đo, và đổ lỗi cho mã là đi sửa nhầm thứ.
HA_TANG_KIEM: frozenset = frozenset({
    LoaiHong.INVALID_VERIFICATION_COMMAND,
    LoaiHong.TEST_HARNESS_FAILURE,
})

_MAU: Tuple[Tuple[LoaiHong, re.Pattern], ...] = (
    (LoaiHong.QUOTA_EXHAUSTED, re.compile(
        r"quota reached|quota exhausted|rate limit|hết hạn mức|"
        r"upgrade your subscription|resets in", re.I)),
    (LoaiHong.AUTHORITY_FAILURE, re.compile(
        r"requires_decision|cần bạn quyết|waiting_authority|"
        r"cần người duyệt|production_deploy|gated", re.I)),
    (LoaiHong.PERMISSION_FAILURE, re.compile(
        r"tool_permission_denied|permission denied|auto-denied|"
        r"read-only|chỉ đọc|sandbox.*chặn|không cho phép yêu cầu nâng quyền",
        re.I)),
    (LoaiHong.ENVIRONMENT_FAILURE, re.compile(
        r"rev-parse HEAD|not a git repository|unknown revision|"
        r"chưa có commit|không cấp được cây làm việc|no such file", re.I)),
    (LoaiHong.VERIFICATION_FAILURE, re.compile(
        r"gate_scope|gate_contract_scope|gate_diff|ghi NGOÀI write_scope|"
        r"kiểm định không đạt|thiếu bằng chứng", re.I)),
    # HẠ TẦNG KIỂM ĐỊNH — xét TRƯỚC `TEST_FAILURE`/`DEPENDENCY_FAILURE`.
    #
    # Thứ tự ở đây quyết định hành động: một lệnh kiểm KHÔNG PHÂN GIẢI ĐƯỢC
    # phải dẫn tới "sửa lệnh kiểm", không phải "sửa mã sản phẩm". Đặt sau
    # `TEST_FAILURE` thì `'test failed'` nuốt mất nó.
    (LoaiHong.INVALID_VERIFICATION_COMMAND, re.compile(
        r"MODULE_NOT_FOUND|Cannot find module|"
        r"missing script|Unknown command|command not found|"
        r"is not recognized as an internal or external command|"
        r"No such file or directory.*(test|spec)|"
        r"error TS18003|No inputs were found", re.I)),
    (LoaiHong.TEST_HARNESS_FAILURE, re.compile(
        r"no test files found|0 tests? (found|collected)|"
        r"ERR_UNKNOWN_FILE_EXTENSION|"
        r"Jest encountered an unexpected token|"
        r"pytest: error: unrecognized arguments|"
        r"INTERNALERROR", re.I)),
    (LoaiHong.DEPENDENCY_FAILURE, re.compile(
        r"ModuleNotFoundError|ImportError|npm ERR|"
        r"unresolved dependency", re.I)),
    (LoaiHong.BUILD_FAILURE, re.compile(
        r"build failed|compile error|SyntaxError|tsc .*error", re.I)),
    (LoaiHong.TEST_FAILURE, re.compile(
        r"\btests? failed\b|FAILED \(failures=|assertionerror", re.I)),
    (LoaiHong.PROVIDER_FAILURE, re.compile(
        r"provider|worker_unavailable|timeout|không tìm thấy agy|"
        r"không tìm thấy codex|turn_failed", re.I)),
    (LoaiHong.STALE_STATE, re.compile(
        r"stale|mồ côi|khoá cũ|phiên chết|đã cạn .* lượt thử", re.I)),
)


def phan_loai(van_ban: str, *, failure_reason: str = "") -> LoaiHong:
    """Phân loại một lần hỏng từ VĂN BẢN nó để lại. Tất định, không LLM.

    Thứ tự mẫu KHÔNG tuỳ tiện: `quota` và `authority` đứng trước vì chúng là
    ranh giới TÀI NGUYÊN/THẨM QUYỀN — đoán nhầm chúng thành "lỗi kỹ thuật"
    dẫn tới thử lại vô ích (quota) hoặc tự ý vượt rào (authority).
    """
    s = f"{failure_reason}\n{van_ban or ''}"
    for loai, mau in _MAU:
        if mau.search(s):
            return loai
    return LoaiHong.UNKNOWN


def chu_ky(loai: LoaiHong, van_ban: str) -> str:
    """Vân tay của một lần hỏng, để nhận ra LẶP LẠI.

    Chuẩn hoá mạnh tay có chủ đích: bỏ số, hex, đường dẫn, thời lượng — hai
    lần hỏng cùng nguyên nhân hiếm khi giống nhau từng ký tự, mà ta cần
    chúng băm ra CÙNG một giá trị.
    """
    s = (van_ban or "").lower()
    # Đường dẫn TRƯỚC, vì nó chứa cả số lẫn hex và phải biến mất nguyên cụm.
    # Bản đầu viết `[a-z]:\\\\` (hai gạch chéo ngược) nên KHÔNG khớp đường
    # dẫn Windows thật (`C:\a\b.py` chỉ có một) — hai lần hỏng cùng nguyên
    # nhân ở hai tệp khác nhau băm ra hai chữ ký, và phép đếm lặp mù luôn.
    s = re.sub(r"[^\s'\"]*[\\/][^\s'\"]*", "@", s)
    s = re.sub(r"[a-f0-9]{6,}", "#", s)
    s = re.sub(r"\d+([.,]\d+)?", "#", s)
    s = re.sub(r"\s+", " ", s).strip()[:400]
    return f"{loai.value}:{hashlib.sha1(s.encode('utf-8')).hexdigest()[:10]}"


@dataclass
class NganSach:
    """TRẦN cho mỗi loại hành động. Hết trần là leo thang, không phải lặp."""

    sua_tai_cho: int = 2
    lap_lai_ke_hoach: int = 2
    doi_cho_chay: int = 2
    hoi_dong: int = 1
    #: Cùng một chữ ký lặp lại bao nhiêu lần thì coi là KHÔNG TIẾN TRIỂN.
    lap_chu_ky: int = 3

    def to_dict(self) -> Dict:
        return {"sua_tai_cho": self.sua_tai_cho,
                "lap_lai_ke_hoach": self.lap_lai_ke_hoach,
                "doi_cho_chay": self.doi_cho_chay, "hoi_dong": self.hoi_dong,
                "lap_chu_ky": self.lap_chu_ky}


@dataclass
class QuyetDinhSuCo:
    hanh_dong: HanhDong
    loai: LoaiHong
    chu_ky: str
    ly_do: str
    con_lai: Dict[str, int] = field(default_factory=dict)
    khong_tien_trien: bool = False

    def to_dict(self) -> Dict:
        return {"hanh_dong": self.hanh_dong.value, "loai": self.loai.value,
                "chu_ky": self.chu_ky, "ly_do": self.ly_do,
                "con_lai": dict(self.con_lai),
                "khong_tien_trien": self.khong_tien_trien}


class VongSuCo:
    """Trạng thái vòng sự cố của MỘT mục tiêu (một execution/một việc).

    Giữ đếm theo từng loại hành động VÀ theo chữ ký hỏng. Hai thứ khác nhau:
    trần hành động chặn "làm mãi một kiểu"; đếm chữ ký chặn "làm mãi vì cùng
    một lý do", kể cả khi mỗi lần dùng một cách khác.
    """

    def __init__(self, ngan_sach: Optional[NganSach] = None):
        self.ns = ngan_sach or NganSach()
        self.da_dung: Dict[str, int] = {}
        self.dem_chu_ky: Dict[str, int] = {}
        self.lich_su: List[QuyetDinhSuCo] = []

    def _con(self, ten: str, tran: int) -> int:
        return max(0, tran - self.da_dung.get(ten, 0))

    def con_lai(self) -> Dict[str, int]:
        return {"sua_tai_cho": self._con("sua_tai_cho", self.ns.sua_tai_cho),
                "lap_lai_ke_hoach": self._con("lap_lai_ke_hoach",
                                              self.ns.lap_lai_ke_hoach),
                "doi_cho_chay": self._con("doi_cho_chay", self.ns.doi_cho_chay),
                "hoi_dong": self._con("hoi_dong", self.ns.hoi_dong)}

    def xet(self, van_ban: str, *, failure_reason: str = "") -> QuyetDinhSuCo:
        """Một lần hỏng nữa — làm gì tiếp?

        Thứ tự xét, và mỗi bước có lý do:

        1. **Thẩm quyền** -> leo thang NGAY. Router không tự vượt rào, và
           chờ đợi không làm nó biến mất.
        2. **Quota** -> CHỜ, không đổi chỗ lung tung: hết hạn mức là một sự
           thật về tài nguyên, và Router KHÔNG mua thêm.
        3. **Lặp chữ ký** -> dừng thử mù; leo thang hoặc gọi hội đồng.
        4. **Không phụ thuộc chỗ chạy** -> sửa MÔI TRƯỜNG, đừng đổi model.
        5. còn lại -> sửa tại chỗ -> lập lại kế hoạch -> đổi chỗ -> hội đồng
           -> leo thang, mỗi bậc CÓ TRẦN.
        """
        loai = phan_loai(van_ban, failure_reason=failure_reason)
        ck = chu_ky(loai, van_ban or failure_reason)
        self.dem_chu_ky[ck] = self.dem_chu_ky.get(ck, 0) + 1
        lap = self.dem_chu_ky[ck]

        def ra(hd: HanhDong, ly_do: str, kt: bool = False) -> QuyetDinhSuCo:
            if hd in (HanhDong.SUA_TAI_CHO, HanhDong.LAP_LAI_KE_HOACH,
                      HanhDong.DOI_CHO_CHAY, HanhDong.HOI_DONG):
                ten = {HanhDong.SUA_TAI_CHO: "sua_tai_cho",
                       HanhDong.LAP_LAI_KE_HOACH: "lap_lai_ke_hoach",
                       HanhDong.DOI_CHO_CHAY: "doi_cho_chay",
                       HanhDong.HOI_DONG: "hoi_dong"}[hd]
                self.da_dung[ten] = self.da_dung.get(ten, 0) + 1
            qd = QuyetDinhSuCo(hanh_dong=hd, loai=loai, chu_ky=ck,
                               ly_do=ly_do, con_lai=self.con_lai(),
                               khong_tien_trien=kt)
            self.lich_su.append(qd)
            return qd

        if loai is LoaiHong.AUTHORITY_FAILURE:
            return ra(HanhDong.LEO_THANG_CHU_SO_HUU,
                      "chạm ranh giới thẩm quyền — chỉ chủ sở hữu mở được, "
                      "và chờ không làm nó biến mất")
        if loai is LoaiHong.QUOTA_EXHAUSTED:
            return ra(HanhDong.CHO_QUOTA,
                      "hết hạn mức nhà cung cấp — CHỜ hoặc dùng bể khác. "
                      "KHÔNG mua thêm credit, không bật overage")
        if lap >= self.ns.lap_chu_ky:
            con = self.con_lai()
            if con["hoi_dong"] > 0:
                return ra(HanhDong.HOI_DONG,
                          f"chữ ký hỏng lặp {lap} lần — dừng thử mù, đưa "
                          f"sang hội đồng để nhìn bằng con mắt khác", True)
            return ra(HanhDong.LEO_THANG_CHU_SO_HUU,
                      f"chữ ký hỏng lặp {lap} lần và đã cạn hội đồng — "
                      f"không còn cách nào mới để thử", True)
        if loai in HA_TANG_KIEM:
            # KHÔNG đổ lỗi cho mã sản phẩm khi thứ hỏng là lệnh kiểm.
            return ra(HanhDong.SUA_HA_TANG_KIEM,
                      f"{loai.value}: thứ hỏng là LỆNH/HẠ TẦNG kiểm định, "
                      f"không phải mã sản phẩm — đi sửa lệnh kiểm và chạy "
                      f"lại phép kiểm, đừng sửa mã")
        if loai in KHONG_PHU_THUOC_CHO:
            return ra(HanhDong.SUA_MOI_TRUONG,
                      f"{loai.value} hỏng y hệt ở mọi chỗ chạy — sửa môi "
                      f"trường, đổi model không cứu được")

        con = self.con_lai()
        if con["sua_tai_cho"] > 0:
            return ra(HanhDong.SUA_TAI_CHO, "thử sửa tại chỗ trong phạm vi")
        if con["lap_lai_ke_hoach"] > 0:
            return ra(HanhDong.LAP_LAI_KE_HOACH,
                      "sửa tại chỗ đã cạn — lập lại kế hoạch")
        if con["doi_cho_chay"] > 0:
            return ra(HanhDong.DOI_CHO_CHAY,
                      "kế hoạch đã cạn — đổi chỗ chạy/model")
        if con["hoi_dong"] > 0:
            return ra(HanhDong.HOI_DONG, "đã cạn các bậc rẻ — gọi hội đồng")
        return ra(HanhDong.LEO_THANG_CHU_SO_HUU,
                  "đã cạn MỌI ngân sách sửa chữa — cần chủ sở hữu quyết", True)
