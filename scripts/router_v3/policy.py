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

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from scripts.router_v3.dag import RiskClass, TaskNode
from scripts.router_v3.registry import Health, WorkerRegistry, WorkerSpec


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


def _diem(spec: WorkerSpec, reg: WorkerRegistry, node: TaskNode) -> float:
    st = reg.state(spec.worker_id)
    diem = 0.0

    # Khop nang luc la yeu to NANG NHAT: mot worker nhanh ma khong lam duoc
    # viec nay thi khong co gia tri gi.
    can = set(node.required_capabilities)
    if can:
        diem += 40.0 * (len(can & set(spec.capabilities)) / len(can))
    else:
        diem += 20.0

    # Lich su: ty le thanh cong. Worker moi duoc coi la 1.0 (xem `success_rate`).
    diem += 25.0 * st.success_rate

    # Tai hien tai: uu tien worker rANH de trai deu, khong don het vao mot cai.
    if spec.max_concurrent > 0:
        diem += 20.0 * (1.0 - st.in_flight / spec.max_concurrent)

    # Suc khoe: `DEGRADED` bi HA DIEM chu khong bi loai — loai han se bien mot
    # lan hong thoang qua thanh mat worker vinh vien.
    if st.health is Health.HEALTHY:
        diem += 10.0
    elif st.health is Health.DEGRADED:
        diem -= 15.0

    # Do tre lich su: nhanh hon thi nhinh hon, nhung nhe thoi.
    if st.avg_seconds > 0:
        diem += max(-5.0, 5.0 - st.avg_seconds / 60.0)

    if node.preferred_provider and spec.provider_family == node.preferred_provider:
        diem += 8.0
    return diem


def choose_worker(reg: WorkerRegistry, node: TaskNode) -> WorkerSpec:
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
    return max(ung_vien, key=lambda w: _diem(w, reg, node))


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
