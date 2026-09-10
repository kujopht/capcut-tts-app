"""BỂ TÀI KHOẢN CHUNG cho một provider ngoài — cùng ngữ nghĩa với bể AG của V4.

Cùng ba hằng với `router_v4/runtime.py` (`NGUONG_COOLDOWN`, `BACKOFF_COOLDOWN`)
để một người vận hành chỉ phải học MỘT luật: hỏng liên tiếp ≥ 3 → cooldown
60s, rồi 300, 900, 1800; thành công xoá chuỗi hỏng. Chọn tài khoản: bật,
không cooldown, ÍT TẢI NHẤT, phá hoà theo alias (tất định). Failover = gọi
lại với `loai_tru` chứa tài khoản vừa hỏng.

Trạng thái bền trong `providers.db` (qua `SoProvider`) — sống qua khởi động
lại và dùng chung giữa các tiến trình mở cùng sổ.
"""
from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional

from scripts.router_v4.runtime import BACKOFF_COOLDOWN, NGUONG_COOLDOWN
from scripts.control_center.providers.so import SoProvider, TaiKhoan


class BeTaiKhoan:
    def __init__(self, so: SoProvider, provider_id: str):
        self.so = so
        self.provider_id = provider_id

    def tai_khoan(self) -> List[TaiKhoan]:
        return self.so.tai_khoan_cua(self.provider_id)

    def chon(self, *, loai_tru: Iterable[str] = (), now: Optional[float] = None,
             suc_chua: int = 1) -> Optional[TaiKhoan]:
        """Tài khoản đủ điều kiện có `dang_dung` nhỏ nhất; `None` nếu không ai."""
        curr = time.time() if now is None else now
        bo = set(loai_tru)
        ung = [t for t in self.tai_khoan()
               if t.bat and t.account_id not in bo and not t.dang_cooldown(curr)
               and t.dang_dung < max(1, suc_chua)]
        if not ung:
            return None
        ung.sort(key=lambda t: (t.dang_dung, t.hong_lien_tiep, t.alias))
        return ung[0]

    def vi_sao_khong_ai(self, *, loai_tru: Iterable[str] = (), now: Optional[float] = None,
                        suc_chua: int = 1) -> str:
        curr = time.time() if now is None else now
        bo = set(loai_tru)
        ly: Dict[str, int] = {}
        for t in self.tai_khoan():
            if not t.bat:
                k = "tắt"
            elif t.account_id in bo:
                k = "đã thử và hỏng cho chính việc này"
            elif t.dang_cooldown(curr):
                k = "cooldown"
            elif t.dang_dung >= max(1, suc_chua):
                k = "đầy chỗ"
            else:
                continue
            ly[k] = ly.get(k, 0) + 1
        if not ly:
            return "provider chưa có tài khoản nào"
        return "; ".join(f"{k} x{v}" for k, v in sorted(ly.items()))

    def bat_dau(self, account_id: str) -> None:
        t = self.so.tai_khoan(account_id)
        if t is not None:
            self.so.cap_nhat_tai_khoan(account_id, dang_dung=t.dang_dung + 1)

    def ket_thuc(self, account_id: str, *, ok: bool, now: Optional[float] = None,
                 chi_tiet: str = "") -> Optional[TaiKhoan]:
        curr = time.time() if now is None else now
        t = self.so.tai_khoan(account_id)
        if t is None:
            return None
        t.dang_dung = max(0, t.dang_dung - 1)
        t.lan_thu_ts = curr
        t.lan_thu_ok = ok
        t.lan_thu_chi_tiet = str(chi_tiet or "")[:300]
        if ok:
            t.hong_lien_tiep = 0
            t.trang_thai = "ok"
        else:
            t.hong_lien_tiep += 1
            t.trang_thai = "hong"
            if t.hong_lien_tiep >= NGUONG_COOLDOWN:
                bac = min(t.hong_lien_tiep - NGUONG_COOLDOWN, len(BACKOFF_COOLDOWN) - 1)
                t.cooldown_den = curr + BACKOFF_COOLDOWN[bac]
                t.trang_thai = "cooldown"
        return self.so.luu_tai_khoan(t)

    def tom_tat(self, now: Optional[float] = None) -> Dict:
        curr = time.time() if now is None else now
        ds = self.tai_khoan()
        return {"provider_id": self.provider_id, "dang_ky": len(ds),
                "bat": sum(t.bat for t in ds),
                "khoe": sum(1 for t in ds if t.bat and not t.dang_cooldown(curr)
                            and t.lan_thu_ok),
                "chua_thu": sum(1 for t in ds if t.lan_thu_ok is None),
                "cooldown": sum(1 for t in ds if t.dang_cooldown(curr)),
                "dang_dung": sum(t.dang_dung for t in ds),
                "ho_so_rieng": len({t.credential_ref for t in ds})}
