"""NGÂN SÁCH ĐỊNH TUYẾN — bậc chi phí, bản ghi, và rào tương xứng (V0.8).

BA ĐIỀU MODULE NÀY LÀM, và một điều nó CỐ Ý KHÔNG LÀM.

LÀM:

1. **Bậc chi phí, không phải giá.** `cost_profile` trong `fabric.json` là một
   số trong [0,1] mang nghĩa "đắt tương đối", không phải USD. Nên ở đây nó
   thành bốn bậc có tên (`RE`/`TRUNG`/`DAT`/`CAO_CAP`) — đủ để so sánh và để
   chặn, mà không giả vờ biết hoá đơn.
2. **Bản ghi mỗi lần gọi một vai**: vai, provider, model, chế độ, bậc chi
   phí, lý do chọn, thời gian tường đo được, và usage *nếu* nhà cung cấp lộ
   ra. Đây là thứ giao diện hiển thị ở §12 và là thứ trả lời được câu "vì
   sao lượt đó đắt".
3. **Rào TƯƠNG XỨNG** (§8, câu cuối): "Prevent a premium model from silently
   consuming disproportionate resources for routine tasks." `kiem_tuong_xung`
   là rào đó, và nó FAIL CLOSED — một việc bậc `THUONG` KHÔNG được chạy trên
   một model bậc `CAO_CAP`, bất kể điểm số định tuyến.

KHÔNG LÀM: **bịa một con số.** Không USD, không token đếm hộ, không "0" thay
cho "không biết". Một `BanGhiDinhTuyen` không đo được usage mang
`usage=[UsageMetric(..., None, UNAVAILABLE)]` — cùng bất biến mà
`UsageMetric.__post_init__` đã ép bằng máy trong `control_center/model.py`,
và cùng luật mà `router_v4/premium.py` ghi trong docstring của nó.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from scripts.control_center.model import UsageConfidence, UsageMetric
from scripts.control_center.reasoning.phan_loai import Bac
from scripts.control_center.reasoning.vai import VaiTro
from scripts.router_v4.premium import BAC_CAO_CAP, CheDo


class BacChiPhi(str, Enum):
    """Bậc chi phí TƯƠNG ĐỐI của một model. KHÔNG phải giá."""

    RE = "RE"
    TRUNG = "TRUNG"
    DAT = "DAT"
    CAO_CAP = "CAO_CAP"

    @property
    def rank(self) -> int:
        return {"RE": 0, "TRUNG": 1, "DAT": 2, "CAO_CAP": 3}[self.value]


#: Ngưỡng trên `cost_profile`. Ở MỘT chỗ, kiểm được.
NGUONG_CHI_PHI: Tuple[float, float, float] = (0.25, 0.55, 0.85)


def bac_chi_phi(cost_profile: float, premium_tier: int = 0) -> BacChiPhi:
    """`cost_profile` + bậc cao cấp -> `BacChiPhi`.

    BẬC THẮNG SỐ: một model `premium_tier >= 3` là `CAO_CAP` dù ai đó khai
    `cost_profile` thấp. Cùng lý do `GacAstra.la_astra` kiểm cả tên lẫn bậc —
    một con số trong tệp cấu hình sửa được, còn bậc là một tuyên bố.
    """
    if int(premium_tier or 0) >= BAC_CAO_CAP:
        return BacChiPhi.CAO_CAP
    c = float(cost_profile or 0.0)
    a, b, d = NGUONG_CHI_PHI
    return (BacChiPhi.RE if c < a else BacChiPhi.TRUNG if c < b
            else BacChiPhi.DAT if c < d else BacChiPhi.CAO_CAP)


#: Bậc chi phí TỐI ĐA cho mỗi bậc độ khó. Rào TƯƠNG XỨNG của §8.
#:
#: `TAM_THUONG` không có mặt: cổng tầm thường ở `phan_loai.py` đã bảo đảm
#: không vai suy luận nào chạy cho lượt đó, nên một dòng ở đây sẽ là một
#: luật không bao giờ được đọc — và một luật không bao giờ chạy là một luật
#: không ai biết đã hỏng.
TRAN_CHI_PHI_THEO_KHO: Dict[Bac, BacChiPhi] = {
    Bac.THUONG: BacChiPhi.TRUNG,
    Bac.KHO: BacChiPhi.DAT,
    Bac.RAT_KHO: BacChiPhi.CAO_CAP,
}


def tran_chi_phi(bac: Bac, che_do: CheDo) -> BacChiPhi:
    """Trần chi phí cho một lượt. ECO hạ trần thêm MỘT bậc.

    ECO không cấm suy luận; nó cấm *tiêu nhiều* cho nó. Hạ một bậc là cách
    diễn đạt đó thành một con số so sánh được, thay vì một lời khuyên.
    """
    tran = TRAN_CHI_PHI_THEO_KHO.get(bac, BacChiPhi.TRUNG)
    if che_do is CheDo.ECO:
        thap = [b for b in BacChiPhi if b.rank == max(0, tran.rank - 1)]
        return thap[0] if thap else BacChiPhi.RE
    return tran


class KhongTuongXung(RuntimeError):
    """Model quá đắt cho độ khó của lượt. FAIL CLOSED, không hạ chuẩn ngầm."""


def kiem_tuong_xung(*, bac_kho: Bac, bac_gia: BacChiPhi, che_do: CheDo,
                    model_id: str = "") -> Tuple[bool, str]:
    """`(tương xứng, vì sao)`. Rào của §8 câu cuối.

    Cố ý trả `(bool, str)` thay vì ném: bên gọi (`dinh_tuyen.py`) biến nó
    thành một lý do LOẠI trong danh sách ứng viên, nên `explain()` nói được
    "model X bị loại vì quá đắt cho việc bậc Y" — hữu ích hơn một ngoại lệ.
    """
    tran = tran_chi_phi(bac_kho, che_do)
    if bac_gia.rank <= tran.rank:
        return True, (f"bậc chi phí {bac_gia.value} ≤ trần {tran.value} cho "
                      f"việc {bac_kho.value} ở chế độ {che_do.value}")
    return False, (f"model {model_id or '?'} bậc chi phí {bac_gia.value} VƯỢT "
                   f"trần {tran.value} của việc bậc {bac_kho.value} (chế độ "
                   f"{che_do.value}) — một model đắt không được âm thầm tiêu "
                   f"cho việc thường")


def usage_khong_do_duoc(provider: str) -> List[UsageMetric]:
    """Usage cho một nhà cung cấp KHÔNG lộ ra số đọc được bằng máy.

    Ghi chú nêu ĐÚNG giới hạn đã đo của từng nhà cung cấp, giống `usage.py` —
    "không đo được" mà không nói vì sao thì người đọc sẽ tưởng là lỗi.
    """
    ly_do = {
        "codex": ("Codex CLI không có lệnh usage/quota — tín hiệu duy nhất "
                  "quan sát được là còn đăng nhập hay không"),
        "claude": ("Claude Code không lộ ra usage; áp lực hạn mức chỉ suy ra "
                   "được từ phản hồi rate-limit thật"),
        "antigravity": ("`agy --print /usage` trả VĂN BẢN cho người đọc; phần "
                        "trăm hạn mức đọc được ở mức BỂ, không ở mức một lượt"),
    }.get((provider or "").lower(),
          "nhà cung cấp không lộ ra usage đọc được bằng máy cho một lượt")
    return [UsageMetric("usage lượt này", None, UsageConfidence.UNAVAILABLE,
                        note=ly_do)]


# --------------------------------------------------------------- han muc do --
#
# §7: *"If provider API exposes this information: measure it. If it does not:
# show UNKNOWN / UNAVAILABLE."* Antigravity CÓ lộ ra — `agy --print /usage`
# trả một bảng phân cách tab, đọc được bằng máy. Đo thật 2026-09-11:
#
#     Gemini Models\tWeekly Limit Remaining\t40%\t2026-09-12T05:39:35Z
#     Gemini Models\tFive Hour Limit Remaining\t91%\t2026-09-11T09:26:01Z
#     Claude and GPT models\tWeekly Limit Remaining\t10%\t2026-09-14T19:58:56Z
#     Claude and GPT models\tFive Hour Limit Remaining\t100%\t2026-09-11T11:38:43Z
#
# Trước v0.8, `fabric.json` khai hai bể này là `source: "declared"` và bộ lập
# lịch thấy `remaining_estimate = 1.0` cho cả hai — tức là "còn 100%" cho một
# bể THẬT SỰ còn 10% tuần. Đó không phải bịa số (nó có nhãn `declared`, và
# `QuotaPool.health` đã chiết khấu theo độ tin cậy), nhưng nó là một con số
# TỆ HƠN con số ta đo được miễn phí.

#: Tên nhóm trong bảng `agy /usage` -> `quota_pool` trong `fabric.json`.
NHOM_BE_AGY: Dict[str, str] = {
    "gemini models": "antigravity_gemini",
    "claude and gpt models": "antigravity_claude_gpt",
}


@dataclass(frozen=True)
class HanMucDoDuoc:
    """Hạn mức ĐÃ ĐO của một bể. `con_lai` trong [0,1]."""

    nhom_be: str
    con_lai: float
    cua_so: str = ""            # "weekly" | "five_hour"
    reset_luc: str = ""
    tho: str = ""

    def to_dict(self) -> Dict:
        return {"nhom_be": self.nhom_be, "con_lai": round(self.con_lai, 4),
                "con_lai_phan_tram": round(self.con_lai * 100, 1),
                "cua_so": self.cua_so, "reset_luc": self.reset_luc}


def doc_han_muc_agy(usage_raw: str) -> Dict[str, HanMucDoDuoc]:
    """Bảng `agy --print /usage` -> `{nhóm bể: hạn mức đã đo}`.

    **CỬA SỔ NHỎ NHẤT THẮNG.** Một bể còn 100% trong năm giờ nhưng 10% trong
    tuần thì ràng buộc thật là 10% — lấy cửa sổ lớn hơn sẽ cho bộ lập lịch
    một tín hiệu lạc quan đúng lúc nó cần thận trọng nhất.

    Không đọc được dòng nào -> `{}`. KHÔNG suy diễn một con số từ văn bản
    không khớp; cùng luật với `UsageReporter._doc_credit`.
    """
    ra: Dict[str, HanMucDoDuoc] = {}
    for dong in (usage_raw or "").splitlines():
        if "%" not in dong:
            continue
        phan = [x.strip() for x in (dong.split("\t") if "\t" in dong
                                    else dong.split("  ")) if x.strip()]
        if len(phan) < 3:
            continue
        nhom = NHOM_BE_AGY.get(phan[0].lower())
        if not nhom:
            continue
        pt = next((x for x in phan if x.endswith("%")), "")
        try:
            con = max(0.0, min(1.0, float(pt.rstrip("%")) / 100.0))
        except ValueError:
            continue
        cs = ("weekly" if "week" in phan[1].lower()
              else "five_hour" if "hour" in phan[1].lower() else phan[1][:20])
        reset = phan[3] if len(phan) > 3 else ""
        cu = ra.get(nhom)
        if cu is None or con < cu.con_lai:
            ra[nhom] = HanMucDoDuoc(nhom_be=nhom, con_lai=con, cua_so=cs,
                                    reset_luc=reset, tho=dong.strip()[:200])
    return ra


def ap_han_muc(fabric, do_duoc: Dict[str, HanMucDoDuoc], *,
               account_id: str) -> List[str]:
    """Áp hạn mức đã đo vào bể của **đúng một tài khoản**. Trả danh sách bể đã đổi.

    `account_id` LÀ BẮT BUỘC, và đó là điểm chính của hàm này. `agy /usage`
    báo hạn mức của tài khoản mà CLI đang đăng nhập — MỘT tài khoản, không
    phải cả tám. Áp con số đó cho tám bể sẽ biến một phép đo thật thành bảy
    con số bịa, và chúng sẽ trông y như con số thật vì cùng mang nhãn
    `probed`. Đó chính là chế độ hỏng mà §7 cấm.
    """
    from scripts.router_v4.runtime import Source

    if not account_id or not do_duoc:
        return []
    doi: List[str] = []
    for p in (getattr(fabric, "pools", {}) or {}).values():
        if p.account_id != account_id:
            continue
        nhom = p.pool_id.split(":", 1)[-1]
        hm = do_duoc.get(nhom)
        if hm is None:
            continue
        p.cap_nhat_uoc_luong(
            hm.con_lai, source=Source.PROBED,
            note=(f"ĐO THẬT từ `agy --print /usage` ({hm.cua_so}, cửa sổ nhỏ "
                  f"nhất thắng; reset {hm.reset_luc})")[:200])
        doi.append(p.pool_id)
    return doi


@dataclass
class BanGhiDinhTuyen:
    """MỘT lần gọi một vai. Đủ để trả lời "vì sao chọn cái đó, tốn bao nhiêu".

    `giay` là ACTUAL vì Control Center tự bấm đồng hồ — đó là con số usage
    thật duy nhất mà mọi nhà cung cấp đều cho.
    """

    vai: VaiTro
    provider: str = ""
    runtime_id: str = ""
    model_id: str = ""
    model_family: str = ""
    che_do: CheDo = CheDo.AUTO
    bac_gia: BacChiPhi = BacChiPhi.RE
    bac_kho: Bac = Bac.THUONG
    ly_do: str = ""
    #: `True` khi vai chạy xong và trả về thứ đọc được.
    thanh_cong: bool = False
    giay: Optional[float] = None
    loai_that_bai: str = ""
    #: Độc lập họ model so với Strategist (chỉ có nghĩa cho Reviewer).
    doc_lap: Optional[bool] = None
    suy_giam: bool = False
    astra: bool = False
    astra_ly_do: str = ""
    usage: List[UsageMetric] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.usage:
            self.usage = usage_khong_do_duoc(self.provider)
        # Thoi gian tuong LUON do duoc, nen no duoc them nhu mot so ACTUAL —
        # nhung chi khi da co. `None` van la `None`.
        if self.giay is not None and not any(
                m.label == "thời gian tường" for m in self.usage):
            self.usage.insert(0, UsageMetric(
                "thời gian tường", round(float(self.giay), 2),
                UsageConfidence.ACTUAL, unit="s",
                note="Control Center tự bấm đồng hồ — số thật duy nhất mà "
                     "mọi nhà cung cấp đều cho"))

    @property
    def co_usage_that(self) -> bool:
        return any(m.confidence is UsageConfidence.ACTUAL for m in self.usage)

    def to_dict(self) -> Dict:
        return {"vai": self.vai.value, "provider": self.provider,
                "runtime_id": self.runtime_id, "model_id": self.model_id,
                "model_family": self.model_family, "che_do": self.che_do.value,
                "bac_gia": self.bac_gia.value, "bac_kho": self.bac_kho.value,
                "ly_do": self.ly_do, "thanh_cong": self.thanh_cong,
                "giay": self.giay, "loai_that_bai": self.loai_that_bai,
                "doc_lap": self.doc_lap, "suy_giam": self.suy_giam,
                "astra": self.astra, "astra_ly_do": self.astra_ly_do,
                "co_usage_that": self.co_usage_that,
                "usage": [m.to_dict() for m in self.usage], "ts": self.ts}

    def dong_gon(self) -> str:
        """Một dòng cho giao diện §12: vai · model · lý do · trạng thái."""
        tt = "OK" if self.thanh_cong else (self.loai_that_bai or "HỎNG")
        co = f" [{self.bac_gia.value}]"
        dl = ""
        if self.doc_lap is not None:
            dl = "  ĐỘC LẬP" if self.doc_lap else "  KHÔNG ĐỘC LẬP (DEGRADED)"
        return (f"{self.vai.nhan:<11} {self.provider}/{self.model_id}{co}"
                f"  {tt}{dl}")


@dataclass
class SoDinhTuyen:
    """Sổ định tuyến của MỘT lượt hội thoại. Nhỏ, sống ngắn, tuần tự hoá được.

    KHÔNG phải một cơ sở dữ liệu usage: lịch sử dài hạn đã có chỗ ở
    `router_v4/history.py` và `cc_events`. Sổ này chỉ trả lời "lượt vừa rồi
    dùng những gì" — đúng phạm vi mà giao diện cần.
    """

    project_id: str = ""
    che_do: CheDo = CheDo.AUTO
    ban_ghi: List[BanGhiDinhTuyen] = field(default_factory=list)

    def them(self, bg: BanGhiDinhTuyen) -> BanGhiDinhTuyen:
        self.ban_ghi.append(bg)
        return bg

    @property
    def tong_giay(self) -> Optional[float]:
        """Tổng thời gian tường. `None` khi KHÔNG có bản ghi nào đo được —
        không phải `0.0`, vì `0.0` đọc thành "chạy tức thì"."""
        co = [b.giay for b in self.ban_ghi if b.giay is not None]
        return round(sum(co), 2) if co else None

    def theo_pool(self) -> Dict[str, int]:
        ra: Dict[str, int] = {}
        for b in self.ban_ghi:
            k = f"{b.provider}:{b.model_family or b.model_id}"
            ra[k] = ra.get(k, 0) + 1
        return dict(sorted(ra.items()))

    @property
    def dung_astra(self) -> bool:
        return any(b.astra for b in self.ban_ghi)

    @property
    def suy_giam(self) -> bool:
        return any(b.suy_giam for b in self.ban_ghi)

    def to_dict(self) -> Dict:
        return {"project_id": self.project_id, "che_do": self.che_do.value,
                "tong_giay": self.tong_giay, "theo_pool": self.theo_pool(),
                "dung_astra": self.dung_astra, "suy_giam": self.suy_giam,
                "ban_ghi": [b.to_dict() for b in self.ban_ghi]}
