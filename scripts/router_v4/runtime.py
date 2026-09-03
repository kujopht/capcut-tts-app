"""Mô hình dữ liệu lõi — Router V4.

BA KHÁI NIỆM TÁCH BẠCH, và việc tách chúng LÀ điểm chính của V4:

    WorkerRuntime   — VẬT CHỨA TÀI NGUYÊN. Một tài khoản + một ranh giới xác
                      thực + một hạn mức đồng thời. AG01..AG08, CODEX01,
                      OPENCODE01, CLAUDE_LEAD.
    ModelCapability — NĂNG LỰC. Model nào làm được gì, thuộc họ nào, tiêu
                      quota của bể nào.
    QuotaPool       — NGÂN SÁCH DÙNG CHUNG. Nhiều model có thể rút từ CÙNG
                      một bể (bằng chứng quan sát: Antigravity gom "Gemini"
                      một nhóm, "Claude và GPT" một nhóm).

Router V3 gộp cả ba vào một `WorkerSpec` có đúng một `model`. Hệ quả: muốn
chạy Gemini và Claude Opus trên cùng tài khoản AG01 thì phải khai HAI worker
giả, và mọi bảng đếm đều tưởng đó là hai tài khoản. V4 tách ra:

    Placement = (runtime, model)

Bộ lập lịch chọn một PLACEMENT, không chọn một "worker". Cùng một runtime có
nhiều placement; cùng một model chạy được trên nhiều runtime.

    AG01 ─┬─ gemini-3.8-flash-high   ─┐
          ├─ claude-opus-4-6-thinking ├─ mỗi cái là một placement
          └─ gpt-oss-120b-medium     ─┘

KHÔNG ĐÓNG CỨNG VAI TRÒ: không nơi nào trong module này (hay trong cấu hình
mặc định) nói "AG01 làm code, AG02 làm review". Runtime là chỗ chứa; model
là năng lực; việc là nhu cầu; bộ lập lịch ghép chúng lại.

NGUỒN GỐC NIỀM TIN (`source`): mỗi năng lực và mỗi số quota đều mang nhãn
`probed` (đã đo thật trên máy này), `declared` (lấy từ tài liệu/UI nhà cung
cấp, CHƯA đo), hay `unknown`. Không có nhãn này thì một con số đoán trông y
hệt một con số đo được, và mọi quyết định dựa trên nó đều không kiểm lại
được. Bộ lập lịch hạ trọng số cho thứ chưa đo.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from scripts.router_v4.capabilities import (CapabilityError, Reasoning,
                                            expand, validate_capabilities)


class Source(str, Enum):
    """Niềm tin vào một con số/nhãn đến từ đâu."""

    PROBED = "probed"        # da do that tren may nay, co ngay thang
    DECLARED = "declared"    # tai lieu/UI nha cung cap, CHUA do
    UNKNOWN = "unknown"      # khong quan sat duoc

    @property
    def confidence(self) -> float:
        return {"probed": 1.0, "declared": 0.5, "unknown": 0.0}[self.value]


class RuntimeStatus(str, Enum):
    """Trạng thái vòng đời của một runtime (mission #15).

    `STARTING` tách khỏi `IDLE` có chủ đích: một runtime đang dựng tiến trình
    chưa nhận việc được, nhưng nó KHÁC `OFFLINE` (không tồn tại/chưa đăng
    nhập) — cái sau cần người vận hành, cái trước chỉ cần chờ.
    """

    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    COOLDOWN = "COOLDOWN"

    @property
    def nhan_viec_duoc(self) -> bool:
        return self in (RuntimeStatus.IDLE, RuntimeStatus.BUSY,
                        RuntimeStatus.DEGRADED)


class FabricError(RuntimeError):
    """Cấu hình fabric sai. Luôn ném lúc NẠP, không bao giờ lúc chạy."""


# ---------------------------------------------------------------------------
# QuotaPool
# ---------------------------------------------------------------------------

@dataclass
class QuotaPool:
    """Ngân sách DÙNG CHUNG của một nhóm model trên một tài khoản.

    `remaining_estimate` là ƯỚC LƯỢNG trong [0,1], không phải sự thật. Không
    nhà cung cấp nào ở đây công bố số dư đọc được bằng máy, nên trường
    `source` gần như luôn là `DECLARED`/`UNKNOWN` và `confidence` thấp. Bộ
    lập lịch PHẢI nhân trọng số quota với `confidence` — nếu không, một con
    số bịa sẽ điều khiển việc định tuyến y như một con số đo được.
    """

    pool_id: str
    account_id: str
    #: Model nao rut tu be nay. Dung de tinh CAN KIET DUNG CHUNG.
    member_models: FrozenSet[str] = frozenset()
    remaining_estimate: float = 1.0
    rolling_window_seconds: float = 5 * 3600.0
    updated_at: float = 0.0
    source: Source = Source.UNKNOWN
    note: str = ""
    #: So luot da tieu trong cua so hien tai — DEM DUOC cuc bo, khong phai
    #: doan. Day la tin hieu THAT duy nhat ve muc tieu thu ma Router co.
    _tieu_thu: List[float] = field(default_factory=list)

    def ghi_nhan_tieu_thu(self, *, now: Optional[float] = None) -> None:
        curr = time.time() if now is None else now
        self._tieu_thu.append(curr)
        self._don(now=curr)

    def _don(self, *, now: float) -> None:
        nguong = now - self.rolling_window_seconds
        self._tieu_thu = [t for t in self._tieu_thu if t >= nguong]

    def so_luot_trong_cua_so(self, *, now: Optional[float] = None) -> int:
        curr = time.time() if now is None else now
        self._don(now=curr)
        return len(self._tieu_thu)

    def cap_nhat_uoc_luong(self, con_lai: float, *, source: Source,
                           note: str = "", now: Optional[float] = None) -> None:
        self.remaining_estimate = max(0.0, min(1.0, con_lai))
        self.source = source
        self.note = note[:200]
        self.updated_at = time.time() if now is None else now

    @property
    def health(self) -> float:
        """Sức khoẻ bể trong [0,1], đã CHIẾT KHẤU theo độ tin cậy.

        Nguồn `UNKNOWN` cho `0.5` (trung lập) thay vì `remaining_estimate`:
        không biết gì thì không được phép vừa lạc quan vừa quyết đoán.
        """
        if self.source is Source.UNKNOWN:
            return 0.5
        c = self.source.confidence
        return self.remaining_estimate * c + 0.5 * (1.0 - c)

    def to_dict(self) -> Dict:
        return {"pool_id": self.pool_id, "account_id": self.account_id,
                "member_models": sorted(self.member_models),
                "remaining_estimate": round(self.remaining_estimate, 3),
                "rolling_window_seconds": self.rolling_window_seconds,
                "updated_at": self.updated_at, "source": self.source.value,
                "confidence": self.source.confidence,
                "health": round(self.health, 3),
                "used_in_window": self.so_luot_trong_cua_so(), "note": self.note}


# ---------------------------------------------------------------------------
# ModelCapability
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelCapability:
    """Một model + nó làm được gì + nó tiêu quota của bể nào."""

    model_id: str
    model_family: str            # "gemini" | "claude" | "gpt" | "codex" | ...
    provider: str                # "antigravity" | "codex" | "opencode" | "claude"
    capabilities: FrozenSet[str] = frozenset()
    #: Nhan nguon cho TUNG nang luc. Thieu nhan -> `DECLARED`.
    capability_source: Dict[str, Source] = field(default_factory=dict)
    quota_pool: str = ""
    reasoning: Reasoning = Reasoning.MEDIUM
    #: Tien nghiem CAU HINH DUOC trong [0,1]. Lich su thuc do se lan at dan
    #: cac so nay — xem `history.py`.
    benchmark_profile: float = 0.5
    #: Do tre KY VONG (giay) cho mot luot dien hinh.
    latency_profile: float = 30.0
    reliability: float = 0.9
    #: Chi phi tuong doi trong [0,1] — 0 la re nhat.
    cost_profile: float = 0.5
    notes: str = ""

    def validate(self) -> None:
        if not self.model_id.strip():
            raise FabricError("model thiếu model_id")
        try:
            validate_capabilities(self.capabilities)
        except CapabilityError as exc:
            raise FabricError(f"{self.model_id}: {exc}") from exc
        for k in self.capability_source:
            if k not in self.capabilities:
                raise FabricError(
                    f"{self.model_id}: capability_source nhắc tới {k!r} nhưng "
                    f"model không khai năng lực đó.")
        for ten, gt in (("benchmark_profile", self.benchmark_profile),
                        ("reliability", self.reliability),
                        ("cost_profile", self.cost_profile)):
            if not 0.0 <= gt <= 1.0:
                raise FabricError(f"{self.model_id}: {ten}={gt} ngoài [0,1]")

    @property
    def effective_capabilities(self) -> FrozenSet[str]:
        return expand(self.capabilities)

    def nguon_cua(self, cap: str) -> Source:
        return self.capability_source.get(cap, Source.DECLARED)

    @property
    def do_tin_nang_luc(self) -> float:
        """Trung bình độ tin cậy của các năng lực đã khai. Dùng để hạ điểm
        một model mà mọi năng lực đều mới chỉ là lời khai."""
        if not self.capabilities:
            return 0.0
        return sum(self.nguon_cua(c).confidence
                   for c in self.capabilities) / len(self.capabilities)

    def to_dict(self) -> Dict:
        return {
            "model_id": self.model_id, "model_family": self.model_family,
            "provider": self.provider,
            "capabilities": sorted(self.capabilities),
            "capability_source": {k: v.value
                                  for k, v in sorted(self.capability_source.items())},
            "quota_pool": self.quota_pool, "reasoning": self.reasoning.value,
            "benchmark_profile": self.benchmark_profile,
            "latency_profile": self.latency_profile,
            "reliability": self.reliability, "cost_profile": self.cost_profile,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# WorkerRuntime
# ---------------------------------------------------------------------------

@dataclass
class WorkerRuntime:
    """Một VẬT CHỨA tài nguyên đã xác thực. KHÔNG phải một model, KHÔNG phải
    một vai trò.

    `auth_profile` là bất biến trung tâm — nó nói phiên đăng nhập NẰM Ở ĐÂU.
    Hai runtime cùng `auth_profile` là cùng MỘT tài khoản đội hai tên; xem
    `Fabric.validate()`. Đây là cùng bất biến `auth_realm` của
    `router_v3/pool/identity.py`, giữ nguyên tên khái niệm để hai tầng khớp
    nhau.
    """

    runtime_id: str              # AG01..AG08, CODEX01, OPENCODE01, CLAUDE_LEAD
    provider: str
    account_id: str              # dinh danh TAI KHOAN (khong phai credential)
    auth_profile: str            # "windows-user:AG02", "codex-cli:default", ...
    supported_models: Tuple[str, ...] = ()
    concurrency: int = 1
    status: RuntimeStatus = RuntimeStatus.OFFLINE
    running_tasks: List[str] = field(default_factory=list)
    #: Ly do runtime chua dung duoc. Rong = da cap phat.
    needs_provisioning: str = ""
    health_detail: str = ""
    last_seen: float = 0.0
    #: Dem hong LIEN TIEP -> cooldown co chan (mission #15).
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    completed: int = 0
    failed: int = 0
    total_seconds: float = 0.0
    #: Nguoi van hanh chu dong rut runtime khoi lich (mission #17 `drain`).
    drained: bool = False
    #: Co NHAN duoc viec giao khong. `False` cho CLAUDE_LEAD: no LA phien
    #: dieu phoi dang chay, khong phai mot tien trinh worker goi ra duoc.
    #:
    #: No van co mat trong fabric co chu dich — de `explain()` noi duoc "vi
    #: sao Claude Code KHONG duoc chon cho viec co hoc" thay vi im lang bo
    #: qua. Nhung bo lap lich phai LOAI no khoi cac ung vien thuc thi: cap
    #: mot worker roi khong dispatch duoc la loi te hon han khong cap.
    dispatchable: bool = True
    #: Transport de dung adapter — khong phai quyet dinh dinh tuyen.
    transport: str = "native"
    host: str = "127.0.0.1"
    port: int = 0
    workspace: str = ""
    notes: str = ""

    @property
    def provisioned(self) -> bool:
        return not self.needs_provisioning

    @property
    def in_flight(self) -> int:
        return len(self.running_tasks)

    @property
    def con_cho(self) -> bool:
        return self.in_flight < self.concurrency

    def dang_cooldown(self, *, now: Optional[float] = None) -> bool:
        curr = time.time() if now is None else now
        return curr < self.cooldown_until

    def trang_thai_hien_tai(self, *, now: Optional[float] = None
                            ) -> RuntimeStatus:
        """Trạng thái SUY RA từ dữ liệu, thay vì tin vào `status` đã ghi.

        Thứ tự ưu tiên cố định: OFFLINE > COOLDOWN > STARTING > BUSY > IDLE.
        `drained` biểu diễn thành `COOLDOWN` — nó cũng là "đừng giao việc",
        và thêm một trạng thái thứ bảy chỉ để phân biệt sẽ làm bảng điều
        khiển rối mà không đổi hành vi nào.
        """
        if not self.provisioned or self.status is RuntimeStatus.OFFLINE:
            return RuntimeStatus.OFFLINE
        if self.drained or self.dang_cooldown(now=now):
            return RuntimeStatus.COOLDOWN
        if self.status is RuntimeStatus.STARTING:
            return RuntimeStatus.STARTING
        if self.in_flight > 0:
            return RuntimeStatus.BUSY
        if self.status is RuntimeStatus.DEGRADED:
            return RuntimeStatus.DEGRADED
        return RuntimeStatus.IDLE

    @property
    def success_rate(self) -> float:
        tong = self.completed + self.failed
        return 1.0 if tong == 0 else self.completed / tong

    @property
    def avg_seconds(self) -> float:
        return self.total_seconds / self.completed if self.completed else 0.0

    def to_dict(self, *, now: Optional[float] = None) -> Dict:
        return {
            "runtime_id": self.runtime_id, "provider": self.provider,
            "account_id": self.account_id, "auth_profile": self.auth_profile,
            "supported_models": list(self.supported_models),
            "concurrency": self.concurrency,
            "status": self.trang_thai_hien_tai(now=now).value,
            "running_tasks": list(self.running_tasks),
            "in_flight": self.in_flight, "drained": self.drained,
            "dispatchable": self.dispatchable,
            "needs_provisioning": self.needs_provisioning,
            "health_detail": self.health_detail,
            "last_seen": round(self.last_seen, 3),
            "consecutive_failures": self.consecutive_failures,
            "cooldown_until": round(self.cooldown_until, 3) or None,
            "completed": self.completed, "failed": self.failed,
            "success_rate": round(self.success_rate, 3),
            "avg_seconds": round(self.avg_seconds, 2),
            "transport": self.transport, "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Placement:
    """(runtime, model) — ĐƠN VỊ bộ lập lịch thực sự chọn.

    Không phải "worker". Cùng một runtime cho nhiều placement; cùng một model
    chạy trên nhiều runtime. Đây là thứ làm cho "tài khoản = vật chứa, model
    = năng lực" thành một thứ mã hoá được chứ không chỉ là một câu trong tài
    liệu.
    """

    runtime_id: str
    model_id: str

    @property
    def key(self) -> str:
        return f"{self.runtime_id}/{self.model_id}"

    def __str__(self) -> str:                             # pragma: no cover
        return self.key


# ---------------------------------------------------------------------------
# Fabric — so dang ky trung lap nha cung cap
# ---------------------------------------------------------------------------

class Fabric:
    """Sổ đăng ký: runtime + model + bể quota. Trung lập nhà cung cấp."""

    def __init__(self) -> None:
        self.runtimes: Dict[str, WorkerRuntime] = {}
        self.models: Dict[str, ModelCapability] = {}
        self.pools: Dict[str, QuotaPool] = {}
        #: Ten NHOM be quota (vd "antigravity_gemini"). Mot model khai NHOM
        #: nó rút từ; be THAT duoc tao mot ban cho MOI TAI KHOAN, dinh danh
        #: "<account_id>:<nhom>". Quota gan voi TAI KHOAN, nen hai tai khoan
        #: Antigravity co hai be Gemini doc lap — gop chung lam mot se khien
        #: mot tai khoan het quota keo ca hai xuong.
        self.pool_groups: Set[str] = set()

    # -- dang ky ------------------------------------------------------------

    def add_pool(self, p: QuotaPool) -> None:
        if p.pool_id in self.pools:
            raise FabricError(f"trùng pool_id: {p.pool_id!r}")
        self.pools[p.pool_id] = p

    def add_model(self, m: ModelCapability) -> None:
        m.validate()
        if m.model_id in self.models:
            raise FabricError(f"trùng model_id: {m.model_id!r}")
        self.models[m.model_id] = m

    def add_runtime(self, r: WorkerRuntime) -> None:
        if r.runtime_id in self.runtimes:
            raise FabricError(f"trùng runtime_id: {r.runtime_id!r}")
        self.runtimes[r.runtime_id] = r

    # -- kiem bat bien ------------------------------------------------------

    def validate(self) -> None:
        """Bất biến toàn fabric. Ném lúc nạp, không bao giờ lúc chạy."""
        for r in self.runtimes.values():
            if not r.auth_profile.strip():
                raise FabricError(
                    f"{r.runtime_id}: thiếu `auth_profile` — không có nhãn chỉ "
                    f"chỗ phiên đăng nhập thì bất biến 'một runtime = một tài "
                    f"khoản' không kiểm được bằng máy.")
            if r.concurrency < 1:
                raise FabricError(f"{r.runtime_id}: concurrency phải >= 1")
            la = [m for m in r.supported_models if m not in self.models]
            if la:
                raise FabricError(
                    f"{r.runtime_id}: khai model không có trong fabric: {la}")

        # MOT auth_profile = MOT runtime da cap phat. Hai runtime tro cung
        # mot ho so xac thuc nghia la chay ca hai doi LUAN PHIEN ghi de
        # credential — thu bi cam tuyet doi (mission #8).
        theo_ho_so: Dict[str, List[str]] = {}
        for r in self.runtimes.values():
            if not r.provisioned:
                continue
            theo_ho_so.setdefault(r.auth_profile, []).append(r.runtime_id)
        for ho_so, ids in sorted(theo_ho_so.items()):
            if len(ids) > 1:
                raise FabricError(
                    f"{len(ids)} runtime dùng chung auth_profile {ho_so!r}: "
                    f"{sorted(ids)}. Một hồ sơ xác thực = MỘT tài khoản; chạy "
                    f"hai runtime trên đó đòi luân phiên ghi đè credential, "
                    f"thứ Router V4 cấm. Cấp hồ sơ riêng, hoặc để runtime thừa "
                    f"ở trạng thái needs_provisioning.")

        for m in self.models.values():
            if not m.quota_pool:
                continue
            # `m.quota_pool` la ten NHOM. Hop le khi nhom da duoc khai bao,
            # hoac khi da co it nhat mot be THAT thuoc nhom do.
            if m.quota_pool in self.pool_groups or m.quota_pool in self.pools:
                continue
            if any(pid.endswith(":" + m.quota_pool) for pid in self.pools):
                continue
            raise FabricError(
                f"{m.model_id}: nhóm quota {m.quota_pool!r} không được khai báo "
                f"và không có bể nào thuộc nhóm đó. Khai nhóm trong "
                f"`quota_pool_templates`, hoặc bỏ trường này nếu model không "
                f"chia sẻ hạn mức với ai.")
        # Be quota phai liet ke dung cac model rut tu no — de tinh CAN KIET
        # DUNG CHUNG (mission #20, bai kiem 3) khong phai doan.
        for p in self.pools.values():
            la = [x for x in p.member_models if x not in self.models]
            if la:
                raise FabricError(f"pool {p.pool_id}: model lạ {la}")

    # -- truy van -----------------------------------------------------------

    def placements(self) -> List[Placement]:
        """MỌI (runtime, model) hợp lệ. Không lọc gì — lọc là việc của
        `scheduler.py`, và tách ra để giải thích được từng bước loại bỏ."""
        ra: List[Placement] = []
        for r in self.runtimes.values():
            for m in r.supported_models:
                ra.append(Placement(r.runtime_id, m))
        return sorted(ra, key=lambda p: p.key)

    def model(self, model_id: str) -> ModelCapability:
        return self.models[model_id]

    def runtime(self, runtime_id: str) -> WorkerRuntime:
        return self.runtimes[runtime_id]

    def pool_cua_model(self, model_id: str) -> Optional[QuotaPool]:
        m = self.models.get(model_id)
        if m is None or not m.quota_pool:
            return None
        return self.pools.get(m.quota_pool)

    def pool_cua_placement(self, p: Placement) -> Optional[QuotaPool]:
        """Bể quota của một placement — quota gắn với TÀI KHOẢN, nên cùng
        một model trên hai runtime rút từ HAI bể khác nhau."""
        m = self.models.get(p.model_id)
        if m is None or not m.quota_pool:
            return None
        r = self.runtimes.get(p.runtime_id)
        if r is None:
            return None
        # Quy uoc dinh danh: "<account_id>:<ten nhom>". Tra ve be dung cua
        # tai khoan do neu co, khong thi be chung cua model.
        rieng = f"{r.account_id}:{m.quota_pool}"
        return self.pools.get(rieng) or self.pools.get(m.quota_pool)

    def dem_tai_khoan(self) -> Dict[str, int]:
        """Đếm TÀI KHOẢN đã cấp phát theo nhà cung cấp — không đếm model,
        không đếm placement. Tồn tại để không ai (kể cả báo cáo tự động)
        nhầm "12 placement" thành "12 tài khoản"."""
        thay: Dict[str, set] = {}
        for r in self.runtimes.values():
            if r.provisioned:
                thay.setdefault(r.provider, set()).add(r.account_id)
        return {k: len(v) for k, v in sorted(thay.items())}

    def snapshot(self, *, now: Optional[float] = None) -> Dict:
        return {
            "runtimes": [r.to_dict(now=now) for r in
                         sorted(self.runtimes.values(),
                                key=lambda x: x.runtime_id)],
            "models": [m.to_dict() for m in
                       sorted(self.models.values(), key=lambda x: x.model_id)],
            "pools": [p.to_dict() for p in
                      sorted(self.pools.values(), key=lambda x: x.pool_id)],
            "accounts": self.dem_tai_khoan(),
            "placements": [p.key for p in self.placements()],
        }

    # -- ghi nhan ket qua ---------------------------------------------------

    def mark_started(self, runtime_id: str, task_id: str) -> None:
        r = self.runtimes[runtime_id]
        if task_id not in r.running_tasks:
            r.running_tasks.append(task_id)
        r.last_seen = time.time()

    def mark_finished(self, runtime_id: str, task_id: str, *, ok: bool,
                      seconds: float, model_id: str = "",
                      now: Optional[float] = None) -> None:
        curr = time.time() if now is None else now
        r = self.runtimes[runtime_id]
        if task_id in r.running_tasks:
            r.running_tasks.remove(task_id)
        r.last_seen = curr
        if ok:
            r.completed += 1
            r.total_seconds += seconds
            r.consecutive_failures = 0
            if r.status is RuntimeStatus.DEGRADED:
                r.status = RuntimeStatus.IDLE
        else:
            r.failed += 1
            r.consecutive_failures += 1
            r.status = RuntimeStatus.DEGRADED
            if r.consecutive_failures >= NGUONG_COOLDOWN:
                bac = min(r.consecutive_failures - NGUONG_COOLDOWN,
                          len(BACKOFF_COOLDOWN) - 1)
                r.cooldown_until = curr + BACKOFF_COOLDOWN[bac]
        p = self.pool_cua_placement(Placement(runtime_id, model_id)) \
            if model_id else None
        if p is not None:
            p.ghi_nhan_tieu_thu(now=curr)


#: Bao nhieu lan hong LIEN TIEP thi vao cooldown (mission #15: "bounded
#: retries and cooldown. Do not hammer a degraded provider").
NGUONG_COOLDOWN = 3
BACKOFF_COOLDOWN: Tuple[float, ...] = (60.0, 300.0, 900.0, 1800.0)
