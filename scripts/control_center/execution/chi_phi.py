"""KIỂM SOÁT CHI PHÍ HỎNG — V0.9, §19.

*"Avoid burning premium quota through repeated failed attempts."* Trần của
`phuc_hoi.py` chặn số LƯỢT; tệp này theo dõi cái đắt tiền hơn: lượt đó chạy
trên bể nào, mất bao lâu, và đã thử bao nhiêu lần rồi.

MỘT LUẬT, và V0.8 đã trả giá để học nó:

    **KHÔNG BỊA SỐ.** `tokens` và `cost_usd` mà nhà cung cấp không cho thì là
    `UNAVAILABLE` + `None`, không phải `0`. Số 0 đọc thành "đã đo và bằng
    không". `UsageMetric` của V0.1 đã cưỡng chế điều này ở tầng kiểu — ném
    khi ai đó khai `ACTUAL` mà không có giá trị — nên ở đây ta chỉ dùng lại
    nó thay vì dựng một bản ghi số tự do.

Thời gian tường thì ĐO ĐƯỢC, nên nó là `ACTUAL`. Đó là con số duy nhất tệp
này dám khẳng định.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from scripts.control_center.model import UsageConfidence, UsageMetric

#: Trần THỜI GIAN TƯỜNG cho một lần thực thi, trước khi bộ điều phối phải
#: dừng và hỏi. Không phải giới hạn cứng của tiến trình — nó là tín hiệu để
#: `nen_dung_lai` nói "đã tiêu quá nhiều cho thứ này".
TRAN_GIAY_MAC_DINH = 3600.0

#: Bậc giá coi là "cao cấp" — dùng lại ngưỡng của `reasoning/ngan_sach.py`
#: qua `premium_tier`, không phải một danh sách tên model. Tên thì đổi; bậc
#: thì là thuộc tính của fabric.
BAC_CAO_CAP = 1


@dataclass
class LanThu:
    """MỘT lần gọi worker. Nguồn gốc định tuyến (§18) sống ở đây."""

    buoc_id: str
    provider: str = ""
    model: str = ""
    runtime_id: str = ""
    premium_tier: int = 0
    giay: float = 0.0
    thanh_cong: bool = False
    ly_do_dinh_tuyen_lai: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {"buoc_id": self.buoc_id, "provider": self.provider,
                "model": self.model, "runtime_id": self.runtime_id,
                "premium_tier": self.premium_tier,
                "giay": round(self.giay, 2), "thanh_cong": self.thanh_cong,
                "ly_do_dinh_tuyen_lai": self.ly_do_dinh_tuyen_lai,
                "ts": self.ts}

    @property
    def cao_cap(self) -> bool:
        return int(self.premium_tier or 0) >= BAC_CAO_CAP


@dataclass
class SoChiPhi:
    """Sổ chi phí của MỘT lần thực thi. Cộng dồn, không bao giờ suy đoán."""

    execution_id: str
    lan_thu: List[LanThu] = field(default_factory=list)
    tran_giay: float = TRAN_GIAY_MAC_DINH

    def them(self, lt: LanThu) -> LanThu:
        self.lan_thu.append(lt)
        return lt

    # ------------------------------------------------------------ tong hop --

    @property
    def so_lan(self) -> int:
        return len(self.lan_thu)

    @property
    def so_lan_hong(self) -> int:
        return sum(1 for x in self.lan_thu if not x.thanh_cong)

    @property
    def so_lan_cao_cap_hong(self) -> int:
        return sum(1 for x in self.lan_thu if x.cao_cap and not x.thanh_cong)

    @property
    def tong_giay(self) -> float:
        return sum(float(x.giay or 0.0) for x in self.lan_thu)

    def theo_pool(self) -> Dict[str, int]:
        ra: Dict[str, int] = {}
        for x in self.lan_thu:
            k = f"{x.provider or '?'}/{x.model or '?'}"
            ra[k] = ra.get(k, 0) + 1
        return dict(sorted(ra.items()))

    def do_duoc(self) -> List[UsageMetric]:
        """Số liệu, và CHỈ những số đo được.

        Thời gian tường: `ACTUAL`. Token và tiền: `UNAVAILABLE` với
        `value=None` — không một nhà cung cấp nào trong fabric này trả về
        chúng theo lượt, và điền `0` là bịa.
        """
        return [
            UsageMetric("thời gian tường", round(self.tong_giay, 1),
                        UsageConfidence.ACTUAL, unit="s",
                        note="đo bằng đồng hồ của Router"),
            UsageMetric("số lượt worker", float(self.so_lan),
                        UsageConfidence.ACTUAL, note="đếm được"),
            UsageMetric("tokens", None, UsageConfidence.UNAVAILABLE,
                        note="CLI của nhà cung cấp không trả về theo lượt"),
            UsageMetric("cost_usd", None, UsageConfidence.UNAVAILABLE,
                        note="không có giá theo lượt — không suy ra từ token"),
        ]

    def to_dict(self) -> Dict:
        return {"execution_id": self.execution_id,
                "lan_thu": [x.to_dict() for x in self.lan_thu],
                "so_lan": self.so_lan, "so_lan_hong": self.so_lan_hong,
                "so_lan_cao_cap_hong": self.so_lan_cao_cap_hong,
                "tong_giay": round(self.tong_giay, 2),
                "tran_giay": self.tran_giay,
                "theo_pool": self.theo_pool(),
                "usage": [m.to_dict() for m in self.do_duoc()]}


@dataclass(frozen=True)
class PhanQuyetNganSach:
    nen_dung: bool
    ly_do: str = ""
    nen_ha_bac: bool = False

    def to_dict(self) -> Dict:
        return {"nen_dung": self.nen_dung, "ly_do": self.ly_do,
                "nen_ha_bac": self.nen_ha_bac}


#: Bao nhiêu lần hỏng TRÊN MODEL CAO CẤP thì hạ bậc. Hai, cùng con số với
#: trần thử lại: quá lần thứ hai thì giả thuyết "model chưa đủ mạnh" đã sai,
#: và tiếp tục đốt bể cao cấp chỉ mua thêm cùng một câu trả lời.
NGUONG_HA_BAC = 2


def xet_ngan_sach(so: SoChiPhi) -> PhanQuyetNganSach:
    """Có nên dừng / hạ bậc model không? Ảnh hưởng quyết định lập lại kế hoạch.

    Trả về `nen_ha_bac=True` chứ KHÔNG tự đổi model: đổi model là việc của
    `reasoning/dinh_tuyen.py`, và một tệp kế toán tự chọn model là đúng kiểu
    quyền lực rải rác làm không ai truy được vì sao một lượt chạy ở đâu.
    """
    if so.tong_giay >= so.tran_giay:
        return PhanQuyetNganSach(
            True, (f"đã tiêu {so.tong_giay:.0f}s tường (trần "
                   f"{so.tran_giay:.0f}s) cho một lần thực thi"))
    if so.so_lan_cao_cap_hong >= NGUONG_HA_BAC:
        return PhanQuyetNganSach(
            False, (f"{so.so_lan_cao_cap_hong} lượt hỏng trên model cao cấp — "
                    f"hạ bậc trước khi thử tiếp"), nen_ha_bac=True)
    return PhanQuyetNganSach(False, "trong ngân sách")


def tu_ket_qua(buoc_id: str, kq, *, premium_tier: int = 0,
               thanh_cong: bool = False, ly_do: str = "") -> LanThu:
    """`HopDongKetQua` -> một dòng chi phí. Không suy ra gì không có sẵn."""
    return LanThu(buoc_id=buoc_id,
                  provider=str(getattr(kq, "provider", "") or ""),
                  model=str(getattr(kq, "model", "") or ""),
                  runtime_id=str(getattr(kq, "runtime_id", "") or ""),
                  premium_tier=int(premium_tier or 0),
                  giay=float(getattr(kq, "duration", 0.0) or 0.0),
                  thanh_cong=bool(thanh_cong), ly_do_dinh_tuyen_lai=ly_do)
