"""Chấm điểm chọn worker + chế độ tốc độ — Router V3, Phase 7 + 11.

Router V2 tra một bảng cứng `task_class -> pool`. Bảng đó không nhìn thấy
worker nào đang bận, worker nào vừa hỏng, hay việc này cần năng lực gì — nên
không lập lịch song song được.

Ở đây chọn worker là một phép **cho điểm**. Nhưng có đúng một thứ KHÔNG được
cho điểm: việc rủi ro cao. Quota, độ rảnh, độ trễ đều là yếu tố mềm; ranh giới
tin cậy thì cứng. Một việc bảo mật không bao giờ được rơi xuống worker yếu hơn
chỉ vì worker đó đang rảnh.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Dict, List, Optional, Tuple

from scripts.router_v3.dag import RiskClass, TaskNode
from scripts.router_v3.registry import Health, WorkerRegistry, WorkerSpec
from scripts.router_v3.routing_history import TongHop


class SpeedMode(str, Enum):
    """Chế độ định tuyến. Hard-deny GIỐNG HỆT nhau ở cả ba — chỉ mức song song
    và mức review thay đổi."""

    SAFE = "safe"
    NORMAL = "normal"
    FAST = "fast"


@dataclass(frozen=True)
class ModeProfile:
    max_parallel: int
    #: Có chạy review thứ hai (challenger) song song không.
    challenger_review: bool
    #: Có bắt buộc review bảo mật cho MỌI thay đổi không (không chỉ rủi ro cao).
    always_security_review: bool
    #: Có chạy toàn bộ bộ test ở mỗi mốc không (thay vì chỉ ở mốc phát hành).
    full_tests_each_phase: bool


PROFILES: Dict[SpeedMode, ModeProfile] = {
    SpeedMode.SAFE: ModeProfile(
        max_parallel=2, challenger_review=True,
        always_security_review=True, full_tests_each_phase=True),
    SpeedMode.NORMAL: ModeProfile(
        max_parallel=3, challenger_review=True,
        always_security_review=False, full_tests_each_phase=False),
    SpeedMode.FAST: ModeProfile(
        max_parallel=6, challenger_review=False,
        always_security_review=False, full_tests_each_phase=False),
}


class NoWorkerAvailable(RuntimeError):
    """Không worker nào đủ điều kiện. Fail closed — không hạ chuẩn để lấp chỗ."""


@dataclass
class RoutingScore:
    """Điểm định tuyến theo TỪNG CHIỀU — Router LTS Phase 8.

    Tách theo tên thay vì một số tổng duy nhất: bảng điều khiển (Phase 16)
    và người gỡ lỗi cần biết TẠI SAO một worker thắng, không chỉ AI thắng.
    An ninh KHÔNG nằm trong các chiều này — nó là RÀO CỨNG lọc TRƯỚC khi
    chấm điểm (`choose_worker`), nên không trọng số nào ở đây lật được nó:
    một worker không đủ tin cậy bị loại khỏi danh sách ứng viên trước khi
    hàm này từng thấy nó, bất kể quota/chi phí trông hấp dẫn thế nào.
    """

    capability_fit: float = 0.0
    risk_fit: float = 0.0
    historical_success_rate: float = 0.0
    historical_rework_rate: float = 0.0
    expected_latency: float = 0.0
    current_load: float = 0.0
    context_size: float = 0.0
    quota_remaining: float = 0.0
    expected_cost: float = 0.0
    recent_failure_rate: float = 0.0
    provider_preference: float = 0.0

    @property
    def total(self) -> float:
        return sum(getattr(self, f.name) for f in fields(self))


def score_worker(spec: WorkerSpec, reg: WorkerRegistry, node: TaskNode, *,
                 history: Optional[Dict[str, TongHop]] = None,
                 quota_remaining: Optional[Dict[str, float]] = None
                 ) -> RoutingScore:
    st = reg.state(spec.worker_id)
    su = (history or {}).get(spec.worker_id)
    diem = RoutingScore()

    # Khop nang luc la yeu to NANG NHAT: mot worker nhanh ma khong lam duoc
    # viec nay thi khong co gia tri gi.
    can = set(node.required_capabilities)
    if can:
        diem.capability_fit = 40.0 * (len(can & set(spec.capabilities)) / len(can))
    else:
        diem.capability_fit = 20.0

    # Hop ROI RUI RO: nut cang rui ro thi worker DUOC TIN CAY cang duoc uu
    # tien hon giua cac ung vien DA QUA rao cung — khong thay the rao cung.
    if node.risk_class is not RiskClass.LOW:
        diem.risk_fit = 10.0 if spec.trusted_for_high_risk else 0.0
    else:
        diem.risk_fit = 2.0

    # Lich su: uu tien SO LIEU DA LUU (routing_history.py, song qua nhieu
    # lan chay) hon so trong-bo-nho-phien-nay — nhung khong co lich su thi
    # roi ve `success_rate` cua WorkerState, khong phat mot worker moi.
    diem.historical_success_rate = 25.0 * (su.ty_le_thanh_cong if su else st.success_rate)
    diem.historical_rework_rate = -15.0 * (su.ty_le_lam_lai if su else 0.0)

    # Tai hien tai: uu tien worker rANH de trai deu, khong don het vao mot cai.
    if spec.max_concurrent > 0:
        diem.current_load = 20.0 * (1.0 - st.in_flight / spec.max_concurrent)

    # Suc khoe: `DEGRADED` bi HA DIEM chu khong bi loai — loai han se bien mot
    # lan hong thoang qua thanh mat worker vinh vien.
    if st.health is Health.HEALTHY:
        diem.current_load += 10.0
    elif st.health is Health.DEGRADED:
        diem.current_load -= 15.0

    # Do tre lich su: nhanh hon thi nhinh hon, nhung nhe thoi. Uu tien so
    # lieu da luu giong success_rate o tren.
    trung_binh_giay = su.avg_wall_seconds if su else st.avg_seconds
    if trung_binh_giay > 0:
        diem.expected_latency = max(-5.0, 5.0 - trung_binh_giay / 60.0)

    # Ngu canh tich luy (Phase 10 ghi vao WorkerState.context_chars) — worker
    # da "am" nhung phinh ngu canh khong lien quan thi kem hap dan hon.
    if st.context_chars > 20_000:
        diem.context_size = max(-8.0, -2.0 * (st.context_chars // 10_000))

    # Quota: CHI cho diem khi THAT SU quan sat duoc (theo mission — "khi co
    # the quan sat duoc chinh thuc"). Khong biet thi trung lap (0), khong
    # doan de tranh thien vi sai.
    if quota_remaining is not None and spec.worker_id in quota_remaining:
        diem.quota_remaining = 5.0 * max(0.0, min(1.0, quota_remaining[spec.worker_id]))

    # Chi phi: chi tinh khi co lich su that; re hon thi nhinh hon, nhe thoi
    # — khong bao gio du manh de thang mot loi hong bao mat (xem docstring).
    if su and su.avg_cost_usd > 0:
        diem.expected_cost = max(-5.0, 5.0 - su.avg_cost_usd)

    # Hong LIEN TIEP GAN DAY (Phase 7 cau dap mach da dem san trong
    # WorkerState.consecutive_failures) — phat truoc khi mach thuc su mo.
    diem.recent_failure_rate = -5.0 * min(3, st.consecutive_failures)

    if node.preferred_provider and spec.provider_family == node.preferred_provider:
        diem.provider_preference = 8.0
    return diem


def choose_worker(reg: WorkerRegistry, node: TaskNode, *,
                  history: Optional[Dict[str, TongHop]] = None,
                  quota_remaining: Optional[Dict[str, float]] = None
                  ) -> WorkerSpec:
    """Chọn worker tốt nhất, hoặc ném lỗi. KHÔNG BAO GIỜ hạ chuẩn tin cậy."""
    cao = node.risk_class is RiskClass.HIGH
    ung_vien = reg.available(high_risk=cao)

    if node.required_capabilities:
        khop = [w for w in ung_vien
                if set(node.required_capabilities) & set(w.capabilities)]
        ung_vien = khop or []

    # RANH GIOI CUNG: review bao mat khong bao gio di toi Codex. Bang chung
    # that (2026-08-28): Codex TU CHOI viec co hinh dang bao mat va tra ve
    # ket qua rong — dinh tuyen sang do la mot lan hong im lang.
    if "security_review" in node.required_capabilities:
        ung_vien = [w for w in ung_vien if w.provider_family != "codex"]

    if not ung_vien:
        raise NoWorkerAvailable(
            f"{node.id}: không worker nào đủ điều kiện "
            f"(risk={node.risk_class.value}, "
            f"cần={list(node.required_capabilities)}). Fail closed — không hạ "
            f"chuẩn tin cậy để lấp chỗ.")
    return max(ung_vien, key=lambda w: score_worker(
        w, reg, node, history=history, quota_remaining=quota_remaining).total)


def plan_parallelism(dag, mode: SpeedMode, *, ceiling: int = 8) -> Tuple[int, str]:
    """Số worker NÊN dùng, kèm lý do.

    Song song tối đa không phải lúc nào cũng nhanh nhất. Ba thứ chặn trên:
    bề rộng của đồ thị (không thể chạy nhiều hơn số nút sẵn sàng), trần của
    chế độ, và đường tới hạn — không worker nào rút ngắn được nó.
    """
    rong = dag.recommended_workers(ceiling=ceiling)
    tran_che_do = PROFILES[mode].max_parallel
    chon = max(1, min(rong, tran_che_do, ceiling))
    _, tt = dag.critical_path()
    tong = sum(n.estimated_seconds for n in dag.nodes())
    if chon == 1:
        ly_do = "đồ thị tuần tự — thêm worker không giúp gì"
    elif rong <= tran_che_do:
        ly_do = f"bề rộng đồ thị là {rong}; chế độ cho phép tới {tran_che_do}"
    else:
        ly_do = f"chế độ {mode.value} giới hạn ở {tran_che_do} (đồ thị rộng {rong})"
    ly_do += f"; đường tới hạn {tt:.0f}s trên tổng {tong:.0f}s worker"
    return chon, ly_do
