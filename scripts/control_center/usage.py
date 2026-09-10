"""Usage nhà cung cấp — Control Center V0.1, yêu cầu #8.

LUẬT DUY NHẤT: **KHÔNG BAO GIỜ BỊA SỐ USAGE.**

Mọi con số ra khỏi module này mang đúng một trong ba nhãn:

    ACTUAL       Control Center TỰ ĐẾM được tại chỗ. Đây là số thật.
    ESTIMATED    ước lượng có nguồn gốc khai báo (`Source.DECLARED` của
                 Router V4) — hữu ích để so tương đối, KHÔNG phải số dư.
    UNAVAILABLE  không quan sát được. Giá trị là `None`, không phải `0`.

Vì sao vế cuối quan trọng đến mức được ép bằng `UsageMetric.__post_init__`:
một `0` trong cột "còn lại" đọc thành "đã cạn", và một `0` trong cột "đã
dùng" đọc thành "chưa tiêu gì". Cả hai đều là kết luận, và cả hai đều sai
khi sự thật là "không đo được". `docs/AI_ROUTER.md` đã ghi rõ điều này cho
quota; ở đây nó thành một bất biến kiểm được bằng máy.

SỰ THẬT ĐO ĐƯỢC VỀ TỪNG NHÀ CUNG CẤP (đã kiểm trong kho này):

    Antigravity  `agy --print /usage` và `/credits` trả VĂN BẢN cho người
                 đọc, không phải lược đồ máy đọc. Đọc được "còn bao nhiêu
                 credit" thì đó là ACTUAL; phần còn lại là văn bản thô, giữ
                 nguyên để người xem, KHÔNG phân tích thành số giả.
    Codex        không có lệnh usage/quota nào. Tín hiệu quan sát được DUY
                 NHẤT là "còn đăng nhập hay không" -> UNAVAILABLE.
    Claude Code  không lộ ra usage. Áp lực hạn mức chỉ SUY RA được từ phản
                 hồi rate-limit thật trong phiên -> UNAVAILABLE.

Gọi CLI nhà cung cấp là việc CHẬM (mỗi lệnh vài giây) và tốn một lượt, nên
nó KHÔNG chạy trong vòng lặp vẽ giao diện. Chỉ chạy khi người dùng bấm làm
mới, hoặc ở biên giai đoạn — đúng luật "không dò quota liên tục" của
`~/.claude/CLAUDE.md`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v4.runtime import Fabric, RuntimeStatus, Source
from scripts.control_center.model import UsageConfidence, UsageMetric
from scripts.control_center.store import ControlStore

#: Bao lau moi cho phep goi lai CLI nha cung cap. Chan viec mot bang dieu
#: khien lam moi moi giay bien thanh mot bo phat lenh `agy` moi giay.
MIN_KHOANG_DO = 300.0

_SOURCE_SANG_TIN_CAY = {
    Source.PROBED: UsageConfidence.ACTUAL,
    Source.DECLARED: UsageConfidence.ESTIMATED,
    Source.UNKNOWN: UsageConfidence.UNAVAILABLE,
}


@dataclass
class ProviderUsage:
    """Usage của MỘT tài khoản trên MỘT nhà cung cấp."""

    provider: str
    account_id: str
    metrics: List[UsageMetric] = field(default_factory=list)
    raw_text: str = ""
    measured_at: float = 0.0
    note: str = ""

    @property
    def co_so_that(self) -> bool:
        return any(m.confidence is UsageConfidence.ACTUAL for m in self.metrics)

    def to_dict(self) -> Dict:
        return {"provider": self.provider, "account_id": self.account_id,
                "metrics": [m.to_dict() for m in self.metrics],
                "raw_text": self.raw_text[:2000],
                "measured_at": self.measured_at, "note": self.note,
                "has_actual": self.co_so_that}


#: Phiên KHÔNG có PID được coi là còn sống trong bao lâu kể từ lần hoạt
#: động cuối. Trùng `sessions.NGUONG_NGUOI` (900s) có chủ ý: đó đã là mốc
#: "im lặng quá lâu thì cần người xem lại" của tầng phiên.
HAN_PHIEN_KHONG_PID = 900.0


def _phien_that_su_song(s) -> bool:
    """Phiên này có CÒN SỐNG THẬT không — không chỉ là trạng thái trong sổ.

    VÌ SAO KHÔNG DÙNG `s.state.alive`, và đây là một lỗi đo được:

    Hàng `sessions` BỀN qua khởi động lại. `recover()` đối soát chúng với
    tiến trình thật, nhưng phiên Antigravity **không ghi PID** (`pid`
    chỉ được ghi lúc kết thúc việc), nên chúng rơi vào nhóm `unknown` và
    được đưa về `IDLE` — CỐ Ý, để Control Center không dựng phiên thứ hai
    chồng lên một tiến trình có thể còn sống.

    Hệ quả cho một con số USAGE: một phiên `IDLE` không PID nằm lại trong
    sổ **mãi mãi**, nên "phiên còn sống" đếm cả phiên của những lần chạy
    trước. Đo được: một sổ có `('antigravity','AG01','BUSY', pid=None)`
    trong khi ứng dụng sinh ra nó đã tắt từ lâu.

    "Còn sống" ở đây là: trạng thái nói còn sống **VÀ** chứng minh được —
    có PID thì tiến trình phải đang chạy; không có PID thì phải có hoạt
    động trong `HAN_PHIEN_KHONG_PID` gần đây. Một phiên không PID và im
    lặng 15 phút không phải một phiên "đang sống"; nó là một hàng cũ.

    KHÔNG đổi hành vi điều phối: `SessionManager` vẫn dùng `state.alive`
    như cũ để quyết REUSE/CREATE/WAIT. Đây chỉ là phép đếm cho báo cáo.
    """
    from scripts.control_center.sessions import tien_trinh_con_song

    if not s.state.alive:
        return False
    if s.pid is not None:
        return tien_trinh_con_song(s.pid)
    return (time.time() - (s.last_activity or 0.0)) <= HAN_PHIEN_KHONG_PID


class UsageReporter:
    """Gom usage từ những nguồn THẬT có, và nói rõ chỗ nào không có."""

    def __init__(self, store: ControlStore, *, fabric: Optional[Fabric] = None):
        self.store = store
        self.fabric = fabric
        self._do_lan_cuoi: float = 0.0
        self._cache_cli: Dict[str, ProviderUsage] = {}

    # -- 1. So Control Center TU DEM — luon la ACTUAL ------------------------

    def cuc_bo(self, project_id: str = "") -> List[UsageMetric]:
        """Số Control Center tự đếm. Đây là phần ACTUAL đáng tin nhất.

        Đếm từ sổ của chính mình, không hỏi ai — nên nó luôn đo được, và nó
        đo đúng thứ người vận hành thật sự muốn biết: đêm qua đã tiêu bao
        nhiêu lượt agent, vào việc gì.
        """
        tasks = self.store.tasks(project_id)
        sessions = self.store.sessions(project_id)
        giay = sum(t.runtime_seconds for t in tasks)
        luot = sum(t.attempts for t in tasks)
        return [
            UsageMetric("việc đã tạo", float(len(tasks)),
                        UsageConfidence.ACTUAL,
                        note="đếm trong sổ Control Center"),
            UsageMetric("lượt dispatch agent", float(luot),
                        UsageConfidence.ACTUAL,
                        note="mỗi lượt thử của mỗi việc, kể cả lượt hỏng"),
            UsageMetric("phiên đã dựng", float(len(sessions)),
                        UsageConfidence.ACTUAL,
                        note="tổng số phiên từng dựng — số LỊCH SỬ"),
            UsageMetric("phiên còn sống", float(
                sum(1 for s in sessions if _phien_that_su_song(s))),
                UsageConfidence.ACTUAL,
                note="đã đối chiếu với tiến trình thật, không chỉ đọc trạng "
                     "thái trong sổ"),
            UsageMetric("giây agent tích luỹ", round(giay, 1),
                        UsageConfidence.ACTUAL, unit="s",
                        note="tổng thời gian tường của các việc đã chạy"),
        ]

    # -- 2. Be quota cua Router V4 — ACTUAL o phan DEM DUOC ------------------

    def be_quota(self) -> List[ProviderUsage]:
        """Trạng thái bể quota lấy thẳng từ `Fabric` của Router V4.

        Mỗi bể cho ra HAI số có bản chất khác nhau, và trộn chúng là sai:

            `đã dùng trong cửa sổ` — Router TỰ ĐẾM mỗi lần hoàn thành việc
                (`QuotaPool.ghi_nhan_tieu_thu`). Đây là ACTUAL.
            `còn lại (ước lượng)`  — `remaining_estimate`, mang nhãn
                `Source` của chính nó. PROBED -> ACTUAL, DECLARED ->
                ESTIMATED, UNKNOWN -> UNAVAILABLE.
        """
        if self.fabric is None:
            return []
        # Chi bao cao be cua tai khoan DA CAP PHAT — mot be cua AG05 (chua
        # ton tai) hien len bang khien "8 tai khoan" trong nhu that.
        tk_that = {r.account_id for r in self.fabric.runtimes.values()
                   if r.provisioned}
        ra: List[ProviderUsage] = []
        for p in sorted(self.fabric.pools.values(), key=lambda x: x.pool_id):
            if p.account_id not in tk_that:
                continue
            tin = _SOURCE_SANG_TIN_CAY.get(p.source, UsageConfidence.UNAVAILABLE)
            ms = [UsageMetric(
                "đã dùng trong cửa sổ", float(p.so_luot_trong_cua_so()),
                UsageConfidence.ACTUAL, unit=" lượt",
                note=f"cửa sổ trượt {p.rolling_window_seconds/3600:.1f}h, "
                     f"Router tự đếm")]
            if tin is UsageConfidence.UNAVAILABLE:
                ms.append(UsageMetric(
                    "còn lại", None, UsageConfidence.UNAVAILABLE,
                    note="nhà cung cấp không lộ ra số dư đọc được bằng máy"))
            else:
                ms.append(UsageMetric(
                    "còn lại", round(p.remaining_estimate * 100, 1), tin,
                    unit="%", note=f"nguồn={p.source.value}, "
                                   f"độ tin cậy={p.source.confidence:.2f}"))
            ra.append(ProviderUsage(
                provider=p.pool_id.split(":", 1)[-1],
                account_id=p.account_id, metrics=ms, note=p.note))
        return ra

    def runtime_that(self) -> List[Dict]:
        """Runtime đã cấp phát vs chưa — để không ai đếm nhầm placement
        thành tài khoản. `Fabric.dem_tai_khoan()` tồn tại đúng vì lý do đó."""
        if self.fabric is None:
            return []
        ra = []
        for r in sorted(self.fabric.runtimes.values(),
                        key=lambda x: x.runtime_id):
            ra.append({
                "runtime_id": r.runtime_id, "provider": r.provider,
                "account_id": r.account_id,
                # NHAN chi cho ("agy-launcher:acc3"), khong phai credential.
                "auth_profile": r.auth_profile, "transport": r.transport,
                "status": r.trang_thai_hien_tai().value,
                "provisioned": r.provisioned,
                "needs_provisioning": r.needs_provisioning,
                "health_detail": r.health_detail,
                "concurrency": r.concurrency, "in_flight": r.in_flight,
                "running_tasks": list(r.running_tasks),
                "consecutive_failures": r.consecutive_failures,
                "cooldown_until": r.cooldown_until or None,
                "drained": r.drained,
                "dispatchable": r.dispatchable})
        return ra

    def be_tai_khoan(self) -> Dict[str, Dict]:
        """Tóm tắt BỂ TÀI KHOẢN theo nhà cung cấp — mọi số đếm từ sổ đăng ký
        đang chạy, không giả định. `khoe` = IDLE/BUSY/DEGRADED (nhận việc
        được); `leader_chiem` = khe đang có phiên Leader ấm (V0.6.1)."""
        if self.fabric is None:
            return {}
        ra: Dict[str, Dict] = {}
        for r in self.fabric.runtimes.values():
            t = ra.setdefault(r.provider, {
                "dang_ky": 0, "cap_phat": 0, "nhan_dispatch": 0, "khoe": 0,
                "cooldown": 0, "offline": 0, "tong_cho": 0, "dang_dung": 0,
                "ho_so_rieng": set(), "leader_chiem": []})
            tt = r.trang_thai_hien_tai()
            t["dang_ky"] += 1
            t["cap_phat"] += int(r.provisioned)
            t["nhan_dispatch"] += int(r.dispatchable and r.provisioned)
            if tt in (RuntimeStatus.IDLE, RuntimeStatus.BUSY, RuntimeStatus.DEGRADED):
                t["khoe"] += 1
                t["tong_cho"] += r.concurrency
                t["dang_dung"] += r.in_flight
            elif tt is RuntimeStatus.COOLDOWN:
                t["cooldown"] += 1
            elif tt is RuntimeStatus.OFFLINE:
                t["offline"] += 1
            if r.auth_profile:
                t["ho_so_rieng"].add(r.auth_profile)
            if any(x.startswith("LEADER:") for x in r.running_tasks):
                t["leader_chiem"].append(r.runtime_id)
        for t in ra.values():
            t["ho_so_rieng"] = len(t["ho_so_rieng"])
        return ra

    def dem_tai_khoan(self) -> Dict[str, int]:
        return self.fabric.dem_tai_khoan() if self.fabric else {}

    # -- 3. Hoi CLI nha cung cap — CHAM, co gioi han nhip --------------------

    def do_nha_cung_cap(self, *, force: bool = False) -> List[ProviderUsage]:
        """Hỏi CLI nhà cung cấp. CHẬM — không gọi trong vòng lặp vẽ.

        Dùng lại `scripts/ai_router_quota_check.py` thay vì gọi `agy`/`codex`
        lần nữa: nó đã biết tìm binary ở đâu, đã có timeout, và đã ghi rõ
        cái gì quan sát được cái gì không. Viết lại ở đây sẽ tạo nguồn sự
        thật thứ hai cho cùng một câu hỏi.
        """
        gio = time.time()
        if not force and self._cache_cli and \
                gio - self._do_lan_cuoi < MIN_KHOANG_DO:
            return list(self._cache_cli.values())

        from scripts import ai_router_quota_check as Q
        ra: List[ProviderUsage] = []

        ag = Q.check_antigravity()
        if not ag.get("cai_dat"):
            ra.append(ProviderUsage(
                provider="antigravity", account_id="(cli)",
                metrics=[UsageMetric("trạng thái", None,
                                     UsageConfidence.UNAVAILABLE,
                                     note="không tìm thấy `agy` trên máy này")],
                measured_at=gio))
        else:
            tho = str(ag.get("credits_raw") or "")
            ms: List[UsageMetric] = []
            con = self._doc_credit(tho)
            if con is None:
                ms.append(UsageMetric(
                    "credit còn lại", None, UsageConfidence.UNAVAILABLE,
                    note="không đọc được dòng 'Remaining credits' — KHÔNG "
                         "suy diễn một con số từ văn bản không khớp"))
            else:
                ms.append(UsageMetric(
                    "credit còn lại", float(con), UsageConfidence.ACTUAL,
                    note="đọc trực tiếp từ `agy --print /credits`"))
            # Rui ro overage: `True` = an toan (0 credit de tieu). `None` =
            # KHONG ket luan — va `None` o day phai hien ra la "khong biet",
            # khong phai "an toan".
            an_toan = Q.check_antigravity_paid_overage_safe(tho)
            ms.append(UsageMetric(
                "rủi ro tính phí vượt hạn mức",
                None if an_toan is None else (0.0 if an_toan else 1.0),
                UsageConfidence.UNAVAILABLE if an_toan is None
                else UsageConfidence.ACTUAL,
                note=("không đọc được — KHÔNG được coi là an toàn"
                      if an_toan is None else
                      "0 credit khả dụng nên không có gì để tính phí"
                      if an_toan else
                      "CÓ credit khả dụng — theo luật kho này, DỪNG chi tiêu "
                      "Antigravity thêm, không mua credit")))
            ra.append(ProviderUsage(
                provider="antigravity", account_id="(cli hiện hành)",
                metrics=ms, raw_text=str(ag.get("usage_raw") or "")[:2000],
                measured_at=gio,
                note="`agy` trả văn bản cho người đọc, không phải lược đồ máy"))

        cx = Q.check_codex()
        ra.append(ProviderUsage(
            provider="codex", account_id="(cli)",
            metrics=[UsageMetric(
                "usage", None, UsageConfidence.UNAVAILABLE,
                note=("Codex CLI không có lệnh usage/quota — tín hiệu duy "
                      "nhất là còn đăng nhập hay không"))],
            measured_at=gio,
            note=("đã cài, đã đăng nhập" if cx.get("cai_dat")
                  and "not logged in" not in
                  str(cx.get("trang_thai_dang_nhap", "")).lower()
                  else "không xác nhận được đăng nhập")))

        ra.append(ProviderUsage(
            provider="claude", account_id="(phiên hiện tại)",
            metrics=[UsageMetric(
                "usage", None, UsageConfidence.UNAVAILABLE,
                note=("Claude Code không lộ ra usage/quota; áp lực hạn mức "
                      "chỉ suy ra được từ phản hồi rate-limit thật"))],
            measured_at=gio))

        self._do_lan_cuoi = gio
        self._cache_cli = {f"{u.provider}:{u.account_id}": u for u in ra}
        return ra

    @staticmethod
    def _doc_credit(tho: str) -> Optional[int]:
        for dong in (tho or "").splitlines():
            if "remaining credits" in dong.lower():
                phan = dong.split("\t") if "\t" in dong else dong.split()
                for muc in reversed(phan):
                    if muc.strip().isdigit():
                        return int(muc.strip())
        return None

    # -- 4. Bao cao gop ------------------------------------------------------

    def report(self, project_id: str = "", *,
               probe_cli: bool = False) -> Dict:
        """Báo cáo usage đầy đủ. `probe_cli=False` mặc định: KHÔNG gọi CLI."""
        return {
            "local": [m.to_dict() for m in self.cuc_bo(project_id)],
            "pools": [u.to_dict() for u in self.be_quota()],
            "runtimes": self.runtime_that(),
            "accounts": self.dem_tai_khoan(),
            "pool": self.be_tai_khoan(),
            "providers": ([u.to_dict() for u in self.do_nha_cung_cap()]
                          if probe_cli else []),
            "provider_probe_ran": probe_cli,
            "note": ("Số nhà cung cấp CHỈ có khi bấm làm mới — gọi CLI là "
                     "thao tác chậm và tốn một lượt, nên nó không chạy trong "
                     "vòng lặp vẽ giao diện."),
        }
