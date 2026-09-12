# -*- coding: utf-8 -*-
"""MÔ HÌNH TÀI NGUYÊN / HẠN MỨC — V1.0 (B8).

LUẬT SỐ MỘT, kế thừa thẳng từ V0.6.1 và không được nới: **không đo được thì
`UNKNOWN`, KHÔNG PHẢI `0`**. Một con số bịa còn tệ hơn không có số — nó làm
bộ xếp chỗ tin vào một thứ không tồn tại.

LUẬT SỐ HAI: **không giả định hình dạng bể quota.** Antigravity có nhiều tài
khoản; nhà cung cấp có thể gộp Claude+GPT vào một bể, hoặc tách ba bể. Mô
hình ở đây CHÉP LẠI thứ runtime phơi ra, không áp một cấu trúc tưởng tượng
lên nó. Đo được tách thì tách; đo được gộp thì ghi gộp; không đo được thì
`UNKNOWN`.

Bằng chứng đêm 2026-09-13: một tài khoản Antigravity trả
`Individual quota reached … Resets in 48h57m19s`. Đó là MỘT điểm dữ liệu về
MỘT tài khoản — nó KHÔNG cho phép suy ra trạng thái của bảy tài khoản còn
lại, và cũng không cho biết Claude với GPT có chung bể hay không.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class SucKhoe(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    EXHAUSTED = "EXHAUSTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class BeQuota:
    """Một bể hạn mức ĐO ĐƯỢC — hoặc thừa nhận là không đo được.

    `con_lai`/`da_dung`/`reset_luc` là `None` khi KHÔNG ĐO ĐƯỢC. Đừng thay
    `None` bằng `0`: `0` nghĩa là "đã cạn", còn `None` nghĩa là "không
    biết", và hai điều đó dẫn tới hai quyết định xếp chỗ ngược nhau.
    """

    ten: str
    #: Tài khoản/nhà cung cấp sở hữu bể này.
    account_id: str = ""
    provider: str = ""
    #: Họ model bể này phục vụ. NHIỀU họ = bể GỘP, và ghi đúng như vậy.
    ho_model: Tuple[str, ...] = ()
    con_lai: Optional[float] = None
    da_dung: Optional[float] = None
    reset_luc: Optional[float] = None
    suc_khoe: SucKhoe = SucKhoe.UNKNOWN
    dong_thoi: Optional[int] = None
    hong_gan_day: int = 0
    #: Câu nguyên văn nhà cung cấp trả về, nếu có. BẰNG CHỨNG.
    bang_chung: str = ""

    @property
    def do_duoc(self) -> bool:
        return self.con_lai is not None or self.reset_luc is not None

    @property
    def con_dung_duoc(self) -> bool:
        """Có nên xếp việc vào đây không.

        `UNKNOWN` vẫn được coi là dùng được — fail-closed ở đây sẽ tê liệt
        cả hệ, vì phần lớn nhà cung cấp KHÔNG phơi ra số. Chỉ `EXHAUSTED`,
        `AUTH_REQUIRED`, `UNAVAILABLE` mới là chặn.
        """
        return self.suc_khoe not in (SucKhoe.EXHAUSTED, SucKhoe.AUTH_REQUIRED,
                                     SucKhoe.UNAVAILABLE)

    @property
    def giay_toi_reset(self) -> Optional[float]:
        if self.reset_luc is None:
            return None
        return max(0.0, self.reset_luc - time.time())

    def to_dict(self) -> Dict:
        return {"ten": self.ten, "account_id": self.account_id,
                "provider": self.provider, "ho_model": list(self.ho_model),
                "con_lai": self.con_lai, "da_dung": self.da_dung,
                "reset_luc": self.reset_luc,
                "giay_toi_reset": self.giay_toi_reset,
                "suc_khoe": self.suc_khoe.value, "dong_thoi": self.dong_thoi,
                "hong_gan_day": self.hong_gan_day,
                "do_duoc": self.do_duoc, "bang_chung": self.bang_chung[:200]}


_RESET = re.compile(
    r"resets?\s+in\s+(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?", re.I)
_CAN = re.compile(
    r"quota reached|quota exhausted|hết hạn mức|upgrade your subscription",
    re.I)


def doc_tin_hieu_quota(van_ban: str, *, bay_gio: Optional[float] = None
                       ) -> Tuple[Optional[SucKhoe], Optional[float]]:
    """Đọc tín hiệu hạn mức từ câu nhà cung cấp trả về.

    Trả `(sức khoẻ, thời điểm reset)`; `None` cho phần không đọc được. Chỉ
    đọc thứ CÓ TRONG VĂN BẢN — không suy ra "còn bao nhiêu" từ việc nó cạn,
    vì không có gì trong câu đó nói điều ấy.
    """
    s = van_ban or ""
    sk: Optional[SucKhoe] = SucKhoe.EXHAUSTED if _CAN.search(s) else None
    khi: Optional[float] = None
    m = _RESET.search(s)
    if m and any(m.groups()):
        h, p, g = (int(x) if x else 0 for x in m.groups())
        khi = (bay_gio or time.time()) + h * 3600 + p * 60 + g
    return sk, khi


class SoTaiNguyen:
    """Sổ các bể quota. Không tự bịa; chỉ ghi thứ được nói cho biết."""

    def __init__(self):
        self._be: Dict[str, BeQuota] = {}

    def khai(self, be: BeQuota) -> BeQuota:
        self._be[be.ten] = be
        return be

    def lay(self, ten: str) -> Optional[BeQuota]:
        return self._be.get(ten)

    def tat_ca(self) -> List[BeQuota]:
        return list(self._be.values())

    def ghi_nhan_tin_hieu(self, ten: str, van_ban: str, *,
                          bay_gio: Optional[float] = None) -> Optional[BeQuota]:
        """Cập nhật MỘT bể từ một câu nhà cung cấp trả về.

        CHỈ bể được nêu tên. Đây là bài học V0.8 chép nguyên: đo một tài
        khoản rồi áp cho cả tám là biến một phép đo thành bảy con số bịa.
        """
        be = self._be.get(ten)
        if be is None:
            return None
        sk, khi = doc_tin_hieu_quota(van_ban, bay_gio=bay_gio)
        if sk is not None:
            be.suc_khoe = sk
        if khi is not None:
            be.reset_luc = khi
        if sk is not None or khi is not None:
            be.bang_chung = (van_ban or "")[:200]
        return be

    def dung_duoc(self, *, ho: str = "") -> List[BeQuota]:
        ra = [b for b in self._be.values() if b.con_dung_duoc]
        if ho:
            ra = [b for b in ra if not b.ho_model or ho in b.ho_model]
        # Bể ĐO ĐƯỢC và còn nhiều thì ưu tiên; bể UNKNOWN xếp sau nhưng VẪN
        # dùng được — phần lớn nhà cung cấp không phơi số, loại chúng ra là
        # tự bỏ đói chính mình.
        return sorted(ra, key=lambda b: (
            0 if b.do_duoc else 1,
            -(b.con_lai if b.con_lai is not None else 0.0),
            b.hong_gan_day))

    def to_dict(self) -> Dict:
        return {"be": [b.to_dict() for b in self._be.values()]}
