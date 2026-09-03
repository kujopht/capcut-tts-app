"""Bộ lập lịch nhận biết năng lực — Router V4.

BA GIAI ĐOẠN, tách bạch và giải thích được từng bước:

    1. LỌC CỨNG   — năng lực không đủ / runtime không nhận việc / bị ghim
                    loại / rào an toàn. Loại là loại; không điểm số nào cứu.
    2. CHO ĐIỂM   — nhiều chiều CÓ TÊN, mỗi chiều một trọng số cấu hình được.
    3. GIẢI THÍCH — vì sao ứng viên thắng, và vì sao TỪNG ứng viên khác trượt.

Giai đoạn 3 không phải trang trí. Một bộ lập lịch không giải thích được thì
không gỡ lỗi được, và người vận hành sẽ mất niềm tin rồi quay về ghim tay
mọi việc — lúc đó cả kiến trúc V4 thành vô nghĩa.

VÌ SAO KHÔNG PHẢI `if task == "coding": dùng Gemini`:
việc mô tả NHU CẦU (`Requirements`), model khai NĂNG LỰC, và ghép đôi là
một phép tính. Thêm một tài khoản hay một model mới chỉ là thêm một dòng
cấu hình — không sửa mã định tuyến.

VÌ SAO KHÔNG PHẢI "chọn tài khoản còn nhiều quota nhất":
quota theo phần trăm bỏ qua chuyện năng lực nào KHAN HIẾM. Nếu hàng đợi có
30 việc cần đọc video và 2 việc kiến trúc, tiêu Gemini (thứ duy nhất đọc
video) cho việc kiến trúc — thứ Claude cũng làm được — là tự bắn vào chân.
`scarcity_penalty` xử lý đúng chuyện đó, và nó nhìn vào HÀNG ĐỢI THẬT chứ
không phải một hằng số.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from scripts.router_v4.capabilities import (Priority, Reasoning, Requirements,
                                            expand, missing, satisfies)
from scripts.router_v4.contract import TaskContract
from scripts.router_v4.runtime import (Fabric, ModelCapability, Placement,
                                       QuotaPool, RuntimeStatus, Source,
                                       WorkerRuntime)


class NoEligiblePlacement(RuntimeError):
    """Không placement nào đủ điều kiện. FAIL CLOSED — không bao giờ hạ
    chuẩn năng lực/an toàn để lấp chỗ."""


@dataclass(frozen=True)
class Weights:
    """Trọng số CẤU HÌNH ĐƯỢC và kiểm thử được. Không hằng số nào rải rác
    trong mã — đổi chính sách là đổi tệp cấu hình, không phải sửa hàm."""

    capability_match: float = 30.0
    benchmark_quality: float = 15.0
    availability: float = 12.0
    quota_health: float = 10.0
    reliability: float = 12.0
    independence_bonus: float = 10.0
    scarcity_penalty: float = 20.0
    latency: float = 8.0
    expected_cost: float = 6.0
    reasoning_fit: float = 10.0
    #: Ha diem mot model ma nang luc moi chi la LOI KHAI, chua do.
    evidence_discount: float = 6.0

    @staticmethod
    def from_dict(d: Optional[Dict]) -> "Weights":
        d = dict(d or {})
        hop_le = {f.name for f in fields(Weights)}
        la = set(d) - hop_le
        if la:
            raise ValueError(f"trọng số lạ: {sorted(la)} (hợp lệ: {sorted(hop_le)})")
        return Weights(**{k: float(v) for k, v in d.items()})

    def to_dict(self) -> Dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class Score:
    """Điểm theo TỪNG CHIỀU. Tách theo tên thay vì một số tổng: bảng điều
    khiển và người gỡ lỗi cần biết TẠI SAO, không chỉ AI thắng."""

    capability_match: float = 0.0
    benchmark_quality: float = 0.0
    availability: float = 0.0
    quota_health: float = 0.0
    reliability: float = 0.0
    independence_bonus: float = 0.0
    scarcity_penalty: float = 0.0
    latency: float = 0.0
    expected_cost: float = 0.0
    reasoning_fit: float = 0.0
    evidence_discount: float = 0.0

    @property
    def total(self) -> float:
        return round(sum(getattr(self, f.name) for f in fields(self)), 6)

    def to_dict(self) -> Dict:
        d = {f.name: round(getattr(self, f.name), 3) for f in fields(self)}
        d["total"] = self.total
        return d


@dataclass
class Candidate:
    placement: Placement
    eligible: bool
    reason: str = ""
    score: Optional[Score] = None

    def to_dict(self) -> Dict:
        return {"placement": self.placement.key, "eligible": self.eligible,
                "reason": self.reason,
                "score": self.score.to_dict() if self.score else None}


@dataclass
class Decision:
    """Một quyết định định tuyến, GIẢI THÍCH ĐƯỢC ĐẦY ĐỦ (mission #17)."""

    task_id: str
    selected: Optional[Placement]
    candidates: List[Candidate] = field(default_factory=list)
    fallbacks: List[str] = field(default_factory=list)
    reason: str = ""
    pinned: bool = False

    @property
    def eligible_count(self) -> int:
        return sum(1 for c in self.candidates if c.eligible)

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "selected": self.selected.key if self.selected else None,
            "reason": self.reason, "pinned": self.pinned,
            "eligible_count": self.eligible_count,
            "fallbacks": list(self.fallbacks),
            "candidates": [c.to_dict() for c in
                           sorted(self.candidates,
                                  key=lambda x: (not x.eligible,
                                                 -(x.score.total if x.score else 0),
                                                 x.placement.key))],
        }

    def explain(self) -> str:
        """Bản in cho người đọc — `router explain <task>`."""
        d = [f"TASK {self.task_id}"]
        d.append(f"  chọn    : {self.selected.key if self.selected else '(không có)'}"
                 + ("  [GHIM BỞI NGƯỜI VẬN HÀNH]" if self.pinned else ""))
        d.append(f"  lý do   : {self.reason}")
        if self.fallbacks:
            d.append(f"  dự phòng: {', '.join(self.fallbacks)}")
        d.append(f"  ứng viên: {self.eligible_count} đủ điều kiện / "
                 f"{len(self.candidates)} xét")
        for c in sorted(self.candidates,
                        key=lambda x: (not x.eligible,
                                       -(x.score.total if x.score else 0),
                                       x.placement.key)):
            if c.eligible and c.score:
                chi_tiet = "  ".join(
                    f"{k}={v:+.1f}" for k, v in c.score.to_dict().items()
                    if k != "total" and abs(v) > 0.05)
                d.append(f"    + {c.placement.key:<34} {c.score.total:7.2f}  "
                         f"{chi_tiet}")
            else:
                d.append(f"    - {c.placement.key:<34} LOẠI: {c.reason}")
        return "\n".join(d)


class Scheduler:
    """Chọn placement cho một hợp đồng. Không chạy gì — chỉ quyết định.

    Tách quyết định khỏi thực thi có chủ đích: nhờ vậy MỌI bài kiểm định
    tuyến đều tất định, không cần tiến trình worker nào.
    """

    def __init__(self, fabric: Fabric, *, weights: Optional[Weights] = None,
                 history=None):
        self.fabric = fabric
        self.weights = weights or Weights()
        self.history = history

    # -- giai doan 1: loc cung ----------------------------------------------

    def _loai_vi(self, p: Placement, c: TaskContract, *,
                 exclude: Set[str], now: Optional[float]) -> Optional[str]:
        """Lý do LOẠI placement này, hoặc `None` nếu đủ điều kiện."""
        r = self.fabric.runtimes.get(p.runtime_id)
        m = self.fabric.models.get(p.model_id)
        if r is None or m is None:
            return "placement trỏ tới runtime/model không tồn tại"
        if p.key in exclude or p.runtime_id in exclude:
            return "đã thử và hỏng cho chính việc này"

        if not r.dispatchable:
            return ("runtime KHÔNG nhận dispatch (là phiên điều phối, không "
                    "phải tiến trình worker gọi ra được)")
        tt = r.trang_thai_hien_tai(now=now)
        if tt is RuntimeStatus.OFFLINE:
            return f"runtime OFFLINE ({r.needs_provisioning or r.health_detail or 'chưa cấp phát'})"[:160]
        if tt is RuntimeStatus.COOLDOWN:
            return "runtime đang COOLDOWN/drained"
        if tt is RuntimeStatus.STARTING:
            return "runtime đang khởi động"
        if not r.con_cho:
            return f"runtime đầy chỗ ({r.in_flight}/{r.concurrency})"

        thieu = missing(m.capabilities, c.requirements)
        if thieu:
            return f"thiếu năng lực {thieu}"

        req = c.requirements
        if req.pin_provider and m.provider != req.pin_provider:
            return f"ghim provider={req.pin_provider}"
        if req.pin_runtime and r.runtime_id != req.pin_runtime:
            return f"ghim runtime={req.pin_runtime}"
        if req.pin_model and m.model_id != req.pin_model:
            return f"ghim model={req.pin_model}"
        if req.exclude_families and m.model_family in req.exclude_families:
            return f"họ model {m.model_family!r} bị loại trừ (review độc lập)"

        # RAO AN TOAN, khong cau hinh duoc, khong diem so nao lat duoc.
        if c.requirements.shell and not c.execution.destructive_actions_allowed:
            if "shell" not in m.effective_capabilities:
                return "việc cần shell nhưng model không có năng lực shell"
        if c.execution.worktree_required and "repo_write" not in m.effective_capabilities:
            return "việc cần ghi trong worktree nhưng model không ghi được kho"
        return None

    # -- giai doan 2: cho diem ----------------------------------------------

    def _cham_diem(self, p: Placement, c: TaskContract, *,
                   demand: Optional["Demand"], author_family: str,
                   now: Optional[float]) -> Score:
        w = self.weights
        r = self.fabric.runtime(p.runtime_id)
        m = self.fabric.model(p.model_id)
        s = Score()
        req = c.requirements

        # Khop nang luc: HANG SO tren moi ung vien con lai, va do la DUNG.
        # Loc cung o giai doan 1 da bao dam moi ung vien deu thoa TOAN BO
        # rao cung; khong con muc do "thoa nhieu hon".
        #
        # BAN DAU o day co mot khoan PHAT theo so nang luc THUA ("model da
        # phuong thuc dung cho viec van ban thi phi"). Da bo, vi no LAM
        # CUNG MOT VIEC voi `scarcity_penalty` nhung MU nhu cau: no phat
        # model da phuong thuc ngay ca khi hang doi khong co viec da phuong
        # thuc nao — luc do giu cho chi lam cham viec hien tai ma khong
        # bao ve dieu gi. Hai co che cho mot muc tieu, mot cai sai, la kieu
        # loi khong ai truy ra duoc tu ban ghi dinh tuyen. Gio CHI
        # `scarcity_penalty` lo chuyen khan hiem, va no nhin hang doi that.
        s.capability_match = w.capability_match

        s.benchmark_quality = w.benchmark_quality * m.benchmark_profile
        # Lich su THUC DO lan at tien nghiem cau hinh khi da co du du lieu.
        if self.history is not None:
            h = self.history.summary_for(model_id=m.model_id, task_type=c.type)
            if h and h.get("samples", 0) >= 3:
                s.benchmark_quality = w.benchmark_quality * float(h["quality"])
                s.reliability = w.reliability * float(h["success_rate"])
            else:
                s.reliability = w.reliability * m.reliability
        else:
            s.reliability = w.reliability * m.reliability

        # San sang: uu tien runtime RANH de trai deu tai, khong don het vao
        # mot cho roi cho.
        s.availability = w.availability * (1.0 - r.in_flight / max(1, r.concurrency))
        if r.trang_thai_hien_tai(now=now) is RuntimeStatus.DEGRADED:
            s.availability -= w.availability * 0.5

        pool = self.fabric.pool_cua_placement(p)
        s.quota_health = w.quota_health * (pool.health if pool else 0.5)

        # Do tre / chi phi: chuan hoa roi nhan trong so uu tien cua VIEC.
        # Mot viec `latency_priority=HIGH` quan tam do tre gap doi binh thuong.
        do_tre = max(0.0, 1.0 - min(1.0, m.latency_profile / 300.0))
        s.latency = w.latency * do_tre * (0.5 + req.latency_priority.weight)
        s.expected_cost = w.expected_cost * (1.0 - m.cost_profile)

        # Hop muc suy luan: du la du, THUA khong duoc thuong (dung Opus cho
        # mot viec doi `low` la lang phi mot tai nguyen dat).
        if m.reasoning >= req.reasoning_level:
            thua_bac = m.reasoning.rank - req.reasoning_level.rank
            s.reasoning_fit = w.reasoning_fit * (1.0 - 0.35 * thua_bac)
        else:
            thieu_bac = req.reasoning_level.rank - m.reasoning.rank
            s.reasoning_fit = -w.reasoning_fit * 0.5 * thieu_bac
        s.reasoning_fit *= (0.5 + req.quality_priority.weight)

        # DA DANG HO MODEL (mission #10): khac ho tac gia thi duoc thuong.
        # Day la TIN HIEU CHO DIEM, khong phai rao cung — mot cung ho van
        # duoc chon neu khong con gi khac.
        if author_family and m.model_family != author_family:
            s.independence_bonus = w.independence_bonus
        elif author_family:
            s.independence_bonus = 0.0

        # KHAN HIEM (mission #6): dung mot nang luc HIEM cho mot viec KHONG
        # can no la lang phi. Phat theo do hiem THAT trong fabric va theo
        # NHU CAU sap toi that trong hang doi.
        s.scarcity_penalty = -w.scarcity_penalty * self._do_khan_hiem(
            m, c, demand=demand, now=now)

        s.evidence_discount = -w.evidence_discount * (1.0 - m.do_tin_nang_luc)
        return s

    def _do_khan_hiem(self, m: ModelCapability, c: TaskContract, *,
                      demand: Optional["Demand"], now: Optional[float]) -> float:
        """Mức "phí phạm" khi dùng model này cho việc này, trong [0,1].

        Chỉ phạt các năng lực mà VIỆC NÀY KHÔNG CẦN nhưng model lại là một
        trong số ít nơi có. Không có nhu cầu sắp tới thì không phạt gì: giữ
        chỗ cho một hàng đợi rỗng chỉ làm chậm việc hiện tại.
        """
        if demand is None:
            return 0.0
        phat = 0.0
        can = c.requirements.hard
        for cap, so_cho_can in demand.per_capability.items():
            if so_cho_can <= 0 or cap in can:
                continue
            if cap not in m.effective_capabilities:
                continue
            nha_cung = self._so_placement_co(cap, now=now)
            if nha_cung <= 0:
                continue
            # Cang it nguon cung so voi nhu cau -> cang phat nang. Chan tren
            # 1.0 de mot hang doi khong lo khong bien phat thanh vo cuc.
            phat = max(phat, min(1.0, so_cho_can / (nha_cung * 3.0)))
        return phat

    def _so_placement_co(self, cap: str, *, now: Optional[float]) -> int:
        n = 0
        for p in self.fabric.placements():
            r = self.fabric.runtimes.get(p.runtime_id)
            m = self.fabric.models.get(p.model_id)
            if r is None or m is None:
                continue
            if not r.trang_thai_hien_tai(now=now).nhan_viec_duoc:
                continue
            if cap in m.effective_capabilities:
                n += 1
        return n

    # -- giai doan 3: quyet dinh + giai thich --------------------------------

    def decide(self, c: TaskContract, *, exclude: Sequence[str] = (),
               demand: Optional["Demand"] = None, author_family: str = "",
               now: Optional[float] = None) -> Decision:
        """Chọn placement tốt nhất và ghi lại TOÀN BỘ lý do.

        Tất định: cùng fabric + cùng trạng thái + cùng cấu hình -> cùng kết
        quả. Không random, không `time.time()` ẩn trong đường cho điểm (mọi
        chỗ cần thời gian đều nhận `now` tường minh).
        """
        bo = set(exclude)
        ung_vien: List[Candidate] = []
        for p in self.fabric.placements():
            ly_do = self._loai_vi(p, c, exclude=bo, now=now)
            if ly_do:
                ung_vien.append(Candidate(p, False, ly_do))
                continue
            s = self._cham_diem(p, c, demand=demand, author_family=author_family,
                                now=now)
            ung_vien.append(Candidate(p, True, "đủ điều kiện", s))

        hop_le = [x for x in ung_vien if x.eligible and x.score is not None]
        req = c.requirements
        ghim = bool(req.pin_provider or req.pin_runtime or req.pin_model)
        if not hop_le:
            return Decision(task_id=c.task_id, selected=None,
                            candidates=ung_vien, pinned=ghim,
                            reason=self._vi_sao_khong_ai(ung_vien, c))

        # Sap xep TAT DINH: diem giam dan, roi theo khoa placement de pha
        # hoa. Thieu tieu chi pha hoa thi hai lan chay co the cho hai ket
        # qua khac nhau voi cung dau vao — pha vo bai kiem "tat dinh".
        hop_le.sort(key=lambda x: (-x.score.total, x.placement.key))
        thang = hop_le[0]
        du_phong = [x.placement.key for x in hop_le[1:4]]

        cao_nhat = thang.score.to_dict()
        troi = sorted(((k, v) for k, v in cao_nhat.items()
                       if k != "total" and abs(v) > 0.05),
                      key=lambda kv: -abs(kv[1]))[:3]
        m = self.fabric.model(thang.placement.model_id)
        ly_do = (f"điểm cao nhất {thang.score.total:.2f} trong {len(hop_le)} ứng "
                 f"viên đủ điều kiện; model {m.model_id} (họ {m.model_family}); "
                 f"chiều trội: " + ", ".join(f"{k}={v:+.1f}" for k, v in troi))
        if ghim:
            ly_do = "GHIM bởi người vận hành — " + ly_do
        return Decision(task_id=c.task_id, selected=thang.placement,
                        candidates=ung_vien, fallbacks=du_phong, reason=ly_do,
                        pinned=ghim)

    @staticmethod
    def _vi_sao_khong_ai(ung_vien: Sequence[Candidate], c: TaskContract) -> str:
        gom: Dict[str, int] = {}
        for x in ung_vien:
            # Gom theo LOAI ly do, khong theo van ban day du — nguoi doc can
            # biet "6 cai thieu nang luc video", khong phai 6 dong gan giong.
            khoa = x.reason.split("(")[0].strip()
            gom[khoa] = gom.get(khoa, 0) + 1
        return (f"KHÔNG placement nào đủ điều kiện cho {c.task_id} "
                f"(cần {sorted(c.requirements.hard) or 'không năng lực đặc biệt'}). "
                f"Lý do loại: " + "; ".join(f"{k} x{v}" for k, v in sorted(gom.items()))
                + ". Fail closed — không hạ chuẩn năng lực/an toàn để lấp chỗ.")

    def select(self, c: TaskContract, **kw) -> Placement:
        d = self.decide(c, **kw)
        if d.selected is None:
            raise NoEligiblePlacement(d.reason)
        return d.selected


@dataclass
class Demand:
    """Nhu cầu SẮP TỚI, đo từ hàng đợi thật — không phải hằng số.

    Bộ lập lịch dùng cái này để giữ lại năng lực khan hiếm. Dựng nó từ các
    hợp đồng đang chờ; hàng đợi rỗng -> không giữ gì.
    """

    per_capability: Dict[str, int] = field(default_factory=dict)
    total_tasks: int = 0

    @staticmethod
    def from_contracts(cs: Sequence[TaskContract]) -> "Demand":
        d: Dict[str, int] = {}
        for c in cs:
            for cap in c.requirements.hard:
                d[cap] = d.get(cap, 0) + 1
        return Demand(per_capability=d, total_tasks=len(cs))

    def to_dict(self) -> Dict:
        return {"per_capability": dict(sorted(self.per_capability.items())),
                "total_tasks": self.total_tasks}
