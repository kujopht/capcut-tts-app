"""CHÍNH SÁCH DỰ ÁN cho model cao cấp — TRA TỪ KÝ ỨC, không chép vào mã.

YÊU CẦU §5 CỦA v0.8, nguyên văn ý: *"Router must retrieve this Decision from
Project Memory rather than hardcoding it."*

Và đây là quyết định THẬT đang nằm trong ký ức dự án Fanfic (đo 2026-09-11,
`control.db` chính tắc, ns `fanfic-dcf29d1141`):

    qd_0001  [hieu_luc]  ku_dd605f187deff41e  tin_cay=user_explicit
    "GPT-6 Astra chỉ được dùng cho các task đặc biệt khó hoặc cần reasoning
     cao, không dùng mặc định cho task thường."

VÌ SAO TRA CHỨ KHÔNG CHÉP. Một hằng số `ASTRA_CHI_VIEC_KHO = True` trong mã
nói rằng *lập trình viên* đã quyết. Nhưng quyết định này là của NGƯỜI DÙNG,
nó có mã, có nguồn gốc L0, và nó **thay thế được** — `de_bat.py` dựng thay
thế kiểu ADR hai chiều. Chép nó vào mã là làm mất cả ba tính chất đó, và
lần sau người dùng đổi ý thì ký ức nói một đằng, mã làm một nẻo.

MẶC ĐỊNH KHI KHÔNG TRA ĐƯỢC LÀ **HẠN CHẾ**, và điều đó KHÔNG giống việc chép
cứng quyết định:

    chép cứng  = "luật là thế này, bất kể dự án ghi gì"
    fail closed = "chưa đọc được luật của dự án này, nên chọn phía không tốn
                   tiền" — và bản ghi định tuyến nói rõ `nguon=fail_closed`,
                   nên một dự án thiếu quyết định HIỆN RA thay vì im lặng
                   thừa hưởng thói quen của một dự án khác.

`router_v4/premium.py` vẫn là rào CƠ CHẾ (trần song song, trần mỗi việc, cấm
đệ quy, ECO cấm tuyệt đối). Module này là rào CHÍNH SÁCH THEO DỰ ÁN đặt
TRƯỚC nó. Hai rào độc lập, và cả hai đều phải mở mới tới được Astra.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple

from scripts.router_v4.premium import MODEL_ASTRA, BAC_CAO_CAP

#: Cụm từ nói "hạn chế". Cụm, không phải từ đơn — bài học `fanfic.t78ce-1`.
_HAN_CHE = tuple(re.compile(m, re.I) for m in (
    r"\bchỉ (được )?(dùng|sử dụng|dành)\b",
    r"\bkhông dùng mặc định\b", r"\bkhông (được )?dùng cho (task|việc) thường\b",
    r"\bkhông (bao giờ )?là (lựa chọn )?mặc định\b",
    r"\bchỉ (khi|dành cho|cho)\b.{0,40}\b(khó|cao|đặc biệt|exceptional|critical)\b",
    r"\breserved for\b", r"\bmust not\b.{0,30}\bdefault\b",
    r"\bonly for\b.{0,40}\b(hard|difficult|complex|high[- ]reasoning)\b",
    r"\bnot (the )?default\b", r"\bescalation only\b", r"\bleo thang\b",
))

#: Cụm từ nói "được dùng thoải mái". Có mặt để một quyết định THAY THẾ theo
#: chiều nới lỏng vẫn được tôn trọng — chính sách là của dự án, không phải
#: của module này.
_NOI_LONG = tuple(re.compile(m, re.I) for m in (
    r"\bdùng (tự do|thoải mái|mặc định)\b",
    r"\b(cho phép|được) dùng (rộng|mọi|tất cả|cho mọi)\b",
    r"\bunrestricted\b", r"\bmay be (the )?default\b",
    r"\bdùng cho (mọi|tất cả) (task|việc)\b",
))


def ten_model_cao_cap(fabric: Any = None) -> Tuple[str, ...]:
    """Tên model CAO CẤP mà dự án này có thể chạm tới.

    Đọc từ fabric theo BẬC (`premium_tier >= 3`), không theo một danh sách
    tên trong mã — `GacAstra.la_astra` đã nói rõ vì sao: "một model cao cấp
    mới có thể mang tên khác". `MODEL_ASTRA` luôn có mặt làm neo cho phép
    tra ký ức (quyết định của người dùng gọi nó bằng tên).
    """
    ten = {MODEL_ASTRA}
    try:
        for m in (getattr(fabric, "models", {}) or {}).values():
            if int(getattr(m, "premium_tier", 0) or 0) >= BAC_CAO_CAP:
                ten.add(str(getattr(m, "model_id", "")).strip())
    except Exception:                                       # noqa: BLE001
        pass
    return tuple(sorted(x for x in ten if x))


def _bien_the(ten: str) -> Tuple[str, ...]:
    """Các cách người ta gõ một tên model. `gpt-6-astra` -> cũng khớp
    "GPT-6 Astra", "gpt6 astra", "astra"."""
    t = ten.strip().lower()
    ra = {t, t.replace("-", " "), t.replace("-", "")}
    duoi = t.rsplit("-", 1)[-1]
    if len(duoi) >= 4:
        ra.add(duoi)                    # "astra"
    return tuple(sorted(ra))


@dataclass(frozen=True)
class ChinhSachCaoCap:
    """Chính sách model cao cấp của MỘT dự án, kèm nguồn gốc lần về được."""

    han_che: bool
    #: `ky_uc` | `khong_co_ky_uc` | `fail_closed` | `khong_co_du_an`
    nguon: str
    ma: str = ""
    trich: str = ""
    tuoi_giay: float = 0.0
    trang_thai: str = ""
    ten_model: Tuple[str, ...] = ()
    ghi_chu: str = ""

    @property
    def co_bang_chung(self) -> bool:
        return self.nguon == "ky_uc" and bool(self.ma)

    def ly_do(self) -> str:
        if self.co_bang_chung:
            tuoi = f"{self.tuoi_giay / 86400:.1f} ngày" if self.tuoi_giay else "?"
            return (f"chính sách dự án {self.ma} ({self.trang_thai}, {tuoi}): "
                    + (self.trich[:160] or "(không có trích)"))
        if self.nguon == "khong_co_ky_uc":
            return ("dự án CHƯA ghi quyết định nào về model cao cấp — mặc định "
                    "HẠN CHẾ (fail closed), không suy ra từ dự án khác")
        if self.nguon == "fail_closed":
            return (f"không tra được ký ức dự án ({self.ghi_chu or 'lý do không rõ'}) "
                    f"— mặc định HẠN CHẾ")
        return self.ghi_chu or "không xác định"

    def to_dict(self) -> Dict:
        return {"han_che": self.han_che, "nguon": self.nguon, "ma": self.ma,
                "trich": self.trich[:400], "tuoi_giay": round(self.tuoi_giay, 1),
                "trang_thai": self.trang_thai,
                "ten_model": list(self.ten_model),
                "co_bang_chung": self.co_bang_chung,
                "ly_do": self.ly_do()}


def _khop_model(van: str, ten: Sequence[str]) -> bool:
    v = (van or "").lower()
    for t in ten:
        for bt in _bien_the(t):
            if bt and bt in v:
                return True
    return False


def doc_chinh_sach(dv_ky_uc: Any, project_id: str, *,
                   ten_model: Sequence[str] = ()) -> ChinhSachCaoCap:
    """Chính sách model cao cấp của `project_id`, TRA TỪ KÝ ỨC.

    Thứ tự nguồn, và nó không phải tuỳ ý:

    1. **Quyết định** (`loai=decision`) còn `hieu_luc` — đây là hạng cao nhất:
       `de_bat.py` chỉ đề bạt một tuyên bố lên quyết định khi người dùng nói
       tường minh, và nó mang `tin_cay=user_explicit`.
    2. **Ràng buộc** (`constraint`) — cùng hạng thẩm quyền về mặt "người dùng
       đã nói", chỉ khác loại.
    3. Không thấy gì -> `khong_co_ky_uc`, HẠN CHẾ.

    Không ném: lượt chat không được vỡ vì một lần tra ký ức hỏng. Mọi đường
    hỏng đều ra `fail_closed` + HẠN CHẾ.
    """
    ten = tuple(ten_model) or (MODEL_ASTRA,)
    if dv_ky_uc is None:
        return ChinhSachCaoCap(
            han_che=True, nguon="fail_closed", ten_model=ten,
            ghi_chu="dịch vụ ký ức không sẵn")
    if not project_id:
        return ChinhSachCaoCap(han_che=True, nguon="khong_co_du_an",
                               ten_model=ten,
                               ghi_chu="thiếu project_id")
    try:
        ung = _ung_vien(dv_ky_uc, project_id, ten)
    except Exception as exc:                                # noqa: BLE001
        return ChinhSachCaoCap(
            han_che=True, nguon="fail_closed", ten_model=ten,
            ghi_chu=f"{type(exc).__name__}: {exc}"[:160])

    if not ung:
        return ChinhSachCaoCap(han_che=True, nguon="khong_co_ky_uc",
                               ten_model=ten)

    # MOI NHAT thang. Mot quyet dinh sau THAY THE mot quyet dinh truoc — do
    # la chinh co che ADR hai chieu cua `de_bat.py`, nen doc theo thu tu do
    # thay vi tu dinh nghia mot thu tu khac.
    ung.sort(key=lambda x: -float(x.get("ts") or 0.0))
    tot = ung[0]
    van = str(tot.get("noi_dung") or "")
    han = bool(_bat(_HAN_CHE, van))
    noi = bool(_bat(_NOI_LONG, van))
    # Ca hai cung bat -> giu HAN CHE. Mot cau vua noi "chi dung cho viec kho"
    # vua noi "dung mac dinh" la mot cau mau thuan, va phia an toan la phia
    # khong tieu tien.
    han_che = True if (han and noi) else (han or not noi)
    return ChinhSachCaoCap(
        han_che=han_che, nguon="ky_uc", ma=str(tot.get("ma") or ""),
        trich=van[:400], tuoi_giay=max(0.0, time.time() - float(tot.get("ts") or 0.0)),
        trang_thai=str(tot.get("trang_thai") or ""), ten_model=ten,
        ghi_chu=("cả dấu hiệu HẠN CHẾ và NỚI LỎNG cùng khớp — giữ HẠN CHẾ"
                 if (han and noi) else ""))


def _bat(mau, van: str):
    return [r.pattern for r in mau if r.search(van or "")]


def _ung_vien(dv, project_id: str, ten: Sequence[str]):
    """Bản ghi ký ức NÓI VỀ model cao cấp. Chỉ `hieu_luc`."""
    ra = []
    seen = set()

    def _them(ma: str, noi_dung: str, ts: float, tt: str, loai: str):
        if not ma or ma in seen:
            return
        if not _khop_model(noi_dung, ten):
            return
        if tt and tt != "hieu_luc":
            return
        seen.add(ma)
        ra.append({"ma": ma, "noi_dung": noi_dung, "ts": ts,
                   "trang_thai": tt or "hieu_luc", "loai": loai})

    # 1. Quyet dinh — hang cao nhat.
    qd = dv.liet_ke(project_id, "decision", limit=200) or {}
    for q in (qd.get("ket_qua") or []):
        k = q.get("ky_uc") or {}
        _them(str(q.get("ma") or k.get("ma") or ""),
              str(k.get("noi_dung") or ""), float(k.get("ts") or q.get("ts") or 0.0),
              str(q.get("trang_thai") or ""), "decision")

    # 2. Rang buoc.
    rb = dv.liet_ke(project_id, "constraint", limit=200) or {}
    for k in (rb.get("ket_qua") or []):
        _them(str(k.get("ma") or ""), str(k.get("noi_dung") or ""),
              float(k.get("ts") or 0.0), str(k.get("trang_thai") or ""),
              "constraint")

    # 3. Tim theo ten model — bat cac ban ghi khong thuoc hai loai tren.
    for t in ten:
        for bt in _bien_the(t)[:2]:
            r = dv.tim(project_id, bt, limit=10) or {}
            for k in (r.get("ket_qua") or []):
                _them(str(k.get("ma") or ""), str(k.get("noi_dung") or ""),
                      float(k.get("ts") or 0.0), str(k.get("trang_thai") or ""),
                      str(k.get("loai") or ""))
    return ra
