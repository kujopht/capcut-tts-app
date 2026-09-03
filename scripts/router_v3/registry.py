"""Sổ đăng ký worker — Router V3, Phase 1.

Router V2 chọn worker bằng một bảng cứng `task_class -> pool`. Bảng đó không
biết worker nào đang bận, worker nào vừa hỏng, hay worker nào thường chậm ở
loại việc này — nên nó không lập lịch song song được.

Ở đây worker là DỮ LIỆU: sức khoẻ, tải, lịch sử. Tầng lập lịch cho điểm dựa
trên đó thay vì tra một bảng cứng.

RANH GIỚI CREDENTIAL — bất biến của module này:
Router **không bao giờ** cầm credential của nhà cung cấp. Mỗi worker native
(agy, codex) tự giữ phiên đăng nhập của nó ở nơi lưu trữ riêng của HĐH/CLI, và
Router chỉ trao đổi **task/kết quả**. Không đọc cookie, không sao chép OAuth
token, không xoay tài khoản để né giới hạn. Một `WorkerSpec` vì thế không có
trường nào chứa được bí mật — và có bài kiểm thử khoá điều đó lại.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple


class ExecutionType(str, Enum):
    #: Tiến trình CLI cục bộ đã tự xác thực (agy, codex).
    LOCAL_CLI = "local_cli"
    #: Chính phiên Claude đang chạy — điều phối, không dispatch ra ngoài.
    NATIVE_LEAD = "native_lead"


class Health(str, Enum):
    """Trạng thái sức khoẻ — Router LTS Phase 7.

    Tách `RATE_LIMITED`/`AUTH_REQUIRED` khỏi `UNAVAILABLE` có chủ đích: cả
    ba đều "không chọn được ngay bây giờ", nhưng nguyên nhân và cách phục
    hồi khác hẳn nhau — quota tự hồi theo thời gian, đăng nhập lại cần
    người vận hành, còn "chưa cài" thì không tự hồi được gì cả. Gộp chung
    làm bảng điều khiển và người vận hành không biết phải làm gì tiếp.
    """

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    #: Vẫn dùng được nhưng vừa hỏng — bị hạ điểm, không bị loại.
    DEGRADED = "degraded"
    #: Không dùng được (chưa cài, chưa đăng nhập). Không bao giờ được chọn.
    UNAVAILABLE = "unavailable"
    #: Quota/tần suất — tự hồi theo thời gian, không cần người can thiệp.
    RATE_LIMITED = "rate_limited"
    #: Cần đăng nhập lại (phiên hết hạn, chưa xác thực) — cần NGƯỜI VẬN HÀNH.
    AUTH_REQUIRED = "auth_required"
    #: Tiến trình/kết nối chết hẳn — khác UNAVAILABLE ("chưa từng có"): đây
    #: là "đã từng chạy được rồi ngừng", đáng một dòng log riêng để chẩn đoán.
    FAILED = "failed"


#: Chưa BAO GIỜ chọn được — khác `available()` (cũng loại RATE_LIMITED khi
#: cầu dập mạch đang mở, xem `WorkerRegistry.available`).
_KHONG_BAO_GIO_CHON = frozenset({Health.UNAVAILABLE, Health.AUTH_REQUIRED})


#: Năng lực dùng để khớp với `TaskNode.required_capabilities`. Bao gồm cả
#: lớp năng lực CHUYÊN BIỆT (Router LTS Phase 12) — nhãn cho worker TƯƠNG
#: LAI, không ép phải có worker thật nào mang chúng ngay bây giờ.
CAPABILITIES = frozenset({
    "recon", "implement", "tests", "review", "security_review",
    "frontend", "architecture", "integration", "challenger",
    "frontend_prototyper", "research_agent", "scraping_agent",
    "security_reviewer", "test_generator", "media_agent",
})


class PoolState(str, Enum):
    """Trạng thái worker theo NGÔN NGỮ CỦA BỂ (mission "worker pool").

    Khác `Health` có chủ đích. `Health` trả lời "nhà cung cấp đang thế nào";
    `PoolState` trả lời "bộ điều phối làm gì với worker này ngay bây giờ", và
    nó gộp cả TẢI (`in_flight`) — thứ `Health` cố ý không biết. Một worker có
    thể `Health.HEALTHY` mà `PoolState.BUSY`; giữ hai thang đo tách nhau để
    bảng điều khiển không phải suy diễn ngược.
    """

    READY = "READY"
    BUSY = "BUSY"
    QUOTA_COOLDOWN = "QUOTA_COOLDOWN"
    OFFLINE = "OFFLINE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WorkerSpec:
    """MÔ TẢ một worker. Cố ý không có chỗ nào chứa credential."""

    worker_id: str
    provider_family: str            # "antigravity" | "codex" | "claude"
    execution_type: ExecutionType
    pool: str                       # ten pool cua ai_router_dispatch
    capabilities: FrozenSet[str] = frozenset()
    #: Việc rủi ro cao chỉ giao cho worker được đánh dấu tin cậy. Quota KHÔNG
    #: bao giờ ghi đè được điều này — xem `policy.py`.
    trusted_for_high_risk: bool = False
    max_concurrent: int = 1
    notes: str = ""
    #: Model CỤ THỂ worker này chạy. Trước đây chỉ có `pool` (nhãn thô như
    #: "GEMINI_FLASH"), nên hai worker cùng pool nhưng khác model — đúng thứ
    #: mission yêu cầu định tuyến theo năng lực — không phân biệt được.
    model: str = ""
    #: Thư mục làm việc CỐ ĐỊNH của worker (gốc `--add-dir` với worker thường
    #: trực). Rỗng = worker nhận workspace theo từng việc.
    workspace: str = ""
    #: DANH TÍNH XÁC THỰC worker này dùng — vd "windows-user:nguye",
    #: "opencode-server:127.0.0.1:4096", "codex-cli:default". KHÔNG phải
    #: credential: đây là NHÃN CHỈ CHỖ phiên đăng nhập nằm, để bất biến
    #: "một danh tính = một tài khoản" kiểm được bằng máy. Xem
    #: `pool/identity.py::assert_khong_xoay_tai_khoan`.
    auth_realm: str = ""

    def validate(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("worker thiếu id")
        la = set(self.capabilities) - CAPABILITIES
        if la:
            raise ValueError(f"{self.worker_id}: năng lực lạ {sorted(la)}")
        if self.max_concurrent < 1:
            raise ValueError(f"{self.worker_id}: max_concurrent phải >= 1")


#: Bao nhiêu lần hỏng LIÊN TIẾP thì mở cầu dập mạch.
NGUONG_MO_MACH = 3
#: Backoff mở mạch, tăng dần theo số lần mở liên tiếp (giây), trần cuối.
BACKOFF_MO_MACH = (30.0, 120.0, 300.0, 900.0)


@dataclass
class WorkerState:
    """Trạng thái ĐỘNG. Tách khỏi `WorkerSpec` vì cái kia bất biến."""

    health: Health = Health.UNKNOWN
    in_flight: int = 0
    current_task: Optional[str] = None
    completed: int = 0
    failed: int = 0
    total_seconds: float = 0.0
    last_error: str = ""
    #: Cầu dập mạch (Router LTS Phase 7). Tách khỏi `health`: health phản
    #: ánh thứ NHÀ CUNG CẤP báo (rate limit, cần đăng nhập lại); mạch phản
    #: ánh QUYẾT ĐỊNH CỦA ROUTER sau nhiều lần hỏng liên tiếp — hai khái
    #: niệm khác nhau dù thường xảy ra cùng lúc.
    consecutive_failures: int = 0
    circuit_open_until: Optional[float] = None
    circuit_opens: int = 0
    #: Đúng MỘT lượt "dò" được phép đi qua khi mạch vừa hết giờ mở (nửa mở).
    #: Không có cờ này, N nút cùng sẵn sàng sẽ cùng lúc dò lại một worker
    #: vừa hồi — nếu nó vẫn hỏng, mạch mở lại N lần liền thay vì một.
    probe_in_flight: bool = False
    #: Router LTS Phase 10 — số ký tự ngữ cảnh đã tích luỹ ở tiến trình ẤM
    #: của worker này (nếu có). `policy.score_worker` đọc để hạ điểm nhẹ một
    #: worker đang "ấm nhưng phình ngữ cảnh không liên quan". Không phải mọi
    #: worker đều có khái niệm "ấm" — mặc định 0 nghĩa là không áp dụng.
    context_chars: int = 0
    #: Lần cuối quan sát được worker này (epoch). Phân biệt "đang KHOẺ" với
    #: "lần cuối nhìn thấy nó khoẻ là 40 phút trước" — một tiến trình nền có
    #: thể chết im lặng và `health` cũ vẫn nói HEALTHY mãi.
    last_seen: float = 0.0
    #: Hạ nhiệt do QUOTA nhà cung cấp (epoch). TÁCH khỏi `circuit_open_until`
    #: có chủ đích: cầu dập mạch là QUYẾT ĐỊNH của Router sau nhiều lần hỏng;
    #: cái này là giới hạn của NHÀ CUNG CẤP. Gộp chung thì một lần chạm quota
    #: sẽ bị đếm như một lỗi của worker và đẩy nó vào backoff sai loại.
    quota_cooldown_until: Optional[float] = None
    #: Tín hiệu quota THẬT nếu nhà cung cấp có công bố — văn bản ngắn, không
    #: bao giờ đoán. Rỗng = không quan sát được (phần lớn trường hợp).
    quota_signal: str = ""
    #: Việc đang chạy — tên rõ nghĩa theo mission ("active_job"). `current_task`
    #: giữ nguyên làm bí danh để mã cũ không vỡ.
    @property
    def active_job(self) -> Optional[str]:
        return self.current_task

    def cooldown_dang_bat(self, *, now: Optional[float] = None) -> bool:
        if self.quota_cooldown_until is None:
            return False
        curr = time.time() if now is None else now
        return curr < self.quota_cooldown_until

    def pool_state(self, spec: "WorkerSpec", *,
                   now: Optional[float] = None) -> "PoolState":
        """Trạng thái bể. THỨ TỰ ƯU TIÊN có chủ đích và không đổi được:

        OFFLINE > FAILED > QUOTA_COOLDOWN > BUSY > READY

        `OFFLINE` đứng trước tất cả vì nó là thứ DUY NHẤT cần người vận hành
        (chưa cài / chưa đăng nhập); hiển thị nó thành "FAILED" hay
        "QUOTA_COOLDOWN" sẽ khiến người vận hành ngồi đợi một thứ không bao
        giờ tự hồi.
        """
        if self.health in _KHONG_BAO_GIO_CHON:
            return PoolState.OFFLINE
        if self.health is Health.FAILED or self.circuit_is_open(now=now):
            return PoolState.FAILED
        if self.health is Health.RATE_LIMITED or self.cooldown_dang_bat(now=now):
            return PoolState.QUOTA_COOLDOWN
        if self.in_flight > 0:
            return PoolState.BUSY
        return PoolState.READY

    def con_cho(self, spec: "WorkerSpec") -> bool:
        """Còn khe nhận thêm việc không. KHÁC `pool_state() == READY`: một
        worker `max_concurrent=3` đang chạy 1 việc là BUSY nhưng VẪN nhận
        thêm được — trộn hai khái niệm sẽ bỏ phí 2/3 công suất."""
        return self.in_flight < spec.max_concurrent

    @property
    def success_rate(self) -> float:
        tong = self.completed + self.failed
        # Chua co du lieu -> 1.0 (lac quan): mot worker MOI khong duoc bi phat
        # va do do khong bao gio duoc chon de tich luy lich su.
        return 1.0 if tong == 0 else self.completed / tong

    @property
    def avg_seconds(self) -> float:
        return self.total_seconds / self.completed if self.completed else 0.0

    @property
    def is_idle(self) -> bool:
        return self.in_flight == 0

    def circuit_is_open(self, *, now: Optional[float] = None) -> bool:
        if self.circuit_open_until is None:
            return False
        curr = time.time() if now is None else now
        return curr < self.circuit_open_until


class WorkerRegistry:
    def __init__(self) -> None:
        self._specs: Dict[str, WorkerSpec] = {}
        self._states: Dict[str, WorkerState] = {}
        # Bang chung that (review doc lap, 2026-08-30): `Scheduler` goi
        # `mark_finished` TU NHIEU LUONG worker (moi nut dispatch qua
        # ThreadPoolExecutor), va mot worker co `max_concurrent > 1`
        # (vd AG_SLOTS trong default_registry) THAT SU co the co hai luot
        # cung ket thuc dong thoi. Chuoi doc-sua-ghi cua cau dap mach
        # (`consecutive_failures += 1` roi kiem nguong roi mo mach) KHONG
        # atomic qua nhieu cau lenh — thieu khoa nay, hai lan hong dong thoi
        # co the CUNG mo mach hai lan, pha dung bat bien "chi mot luot do
        # nua-mo" ma WorkerState.probe_in_flight duoc dung de bao dam.
        self._khoa = threading.Lock()

    def register(self, spec: WorkerSpec) -> None:
        spec.validate()
        if spec.worker_id in self._specs:
            raise ValueError(f"trùng worker_id: {spec.worker_id!r}")
        self._specs[spec.worker_id] = spec
        self._states[spec.worker_id] = WorkerState()

    def spec(self, worker_id: str) -> WorkerSpec:
        return self._specs[worker_id]

    def state(self, worker_id: str) -> WorkerState:
        return self._states[worker_id]

    def ids(self) -> List[str]:
        return sorted(self._specs)

    def set_health(self, worker_id: str, health: Health, error: str = "") -> None:
        with self._khoa:
            st = self._states[worker_id]
            st.health = health
            st.last_seen = time.time()
            if error:
                st.last_error = error[:200]

    def set_quota_cooldown(self, worker_id: str, seconds: float, *,
                           signal: str = "", now: Optional[float] = None) -> None:
        """Đánh dấu worker chạm giới hạn quota của NHÀ CUNG CẤP.

        KHÔNG tăng `consecutive_failures`: chạm quota không phải worker hỏng,
        và tính nó như lỗi sẽ đẩy một worker khoẻ vào backoff cầu dập mạch —
        rồi nó ở lại đó rất lâu sau khi quota đã hồi.
        """
        curr = time.time() if now is None else now
        with self._khoa:
            st = self._states[worker_id]
            st.quota_cooldown_until = curr + max(0.0, seconds)
            st.health = Health.RATE_LIMITED
            st.last_seen = curr
            if signal:
                st.quota_signal = signal[:200]

    def clear_quota_cooldown(self, worker_id: str) -> None:
        with self._khoa:
            st = self._states[worker_id]
            st.quota_cooldown_until = None
            if st.health is Health.RATE_LIMITED:
                st.health = Health.HEALTHY

    def touch(self, worker_id: str, *, now: Optional[float] = None) -> None:
        """Ghi nhận vừa quan sát được worker này còn sống."""
        with self._khoa:
            self._states[worker_id].last_seen = time.time() if now is None else now

    def available(self, *, capability: Optional[str] = None,
                  high_risk: bool = False, now: Optional[float] = None
                  ) -> List[WorkerSpec]:
        """Worker CÓ THỂ nhận việc ngay bây giờ.

        Loại bỏ `UNAVAILABLE`/`AUTH_REQUIRED` (không tự hồi được, cần người
        vận hành) và worker đã đầy chỗ. `DEGRADED`/`RATE_LIMITED` vẫn nằm
        trong danh sách — bị hạ điểm ở tầng cho điểm (`policy.py`), chứ loại
        hẳn sẽ biến một lần hỏng thoáng qua thành mất worker vĩnh viễn.

        Mạch ĐANG MỞ thì loại, TRỪ đúng một lượt "dò" (nửa mở) khi mạch vừa
        hết giờ mở và chưa có lượt dò nào đang bay — xem `WorkerState`.
        """
        with self._khoa:
            ra = []
            for wid, spec in self._specs.items():
                st = self._states[wid]
                if st.health in _KHONG_BAO_GIO_CHON:
                    continue
                if st.in_flight >= spec.max_concurrent:
                    continue
                if st.circuit_is_open(now=now):
                    continue
                if st.cooldown_dang_bat(now=now):
                    continue          # quota nha cung cap — tu hoi theo gio
                if st.consecutive_failures >= NGUONG_MO_MACH and st.probe_in_flight:
                    continue          # mach nua-mo, da co mot luot do dang bay
                if capability and capability not in spec.capabilities:
                    continue
                if high_risk and not spec.trusted_for_high_risk:
                    continue
                ra.append(spec)
            return ra

    # -- ghi nhan ket qua ---------------------------------------------------

    def mark_started(self, worker_id: str, task_id: str) -> None:
        with self._khoa:
            st = self._states[worker_id]
            st.in_flight += 1
            st.current_task = task_id
            if st.consecutive_failures >= NGUONG_MO_MACH:
                st.probe_in_flight = True     # day la luot do nua-mo

    def mark_finished(self, worker_id: str, *, ok: bool, seconds: float,
                      error: str = "", now: Optional[float] = None) -> None:
        with self._khoa:
            st = self._states[worker_id]
            st.in_flight = max(0, st.in_flight - 1)
            st.current_task = None
            curr = time.time() if now is None else now
            dang_do = st.probe_in_flight
            st.probe_in_flight = False

            if ok:
                st.completed += 1
                st.total_seconds += seconds
                st.consecutive_failures = 0
                st.circuit_open_until = None
                if st.health is not Health.UNAVAILABLE:
                    st.health = Health.HEALTHY
            else:
                st.failed += 1
                st.last_error = (error or "")[:200]
                st.consecutive_failures += 1
                if st.health not in (Health.UNAVAILABLE, Health.AUTH_REQUIRED,
                                     Health.RATE_LIMITED):
                    st.health = Health.DEGRADED
                if dang_do or st.consecutive_failures >= NGUONG_MO_MACH:
                    # Vua hong luot do nua-mo -> mo lai VOI BACKOFF DAI HON,
                    # khong quay ve tier dau — mot nguon van con hong thi mo
                    # mach lien tuc voi cung mot do dai la vo nghia.
                    bac = min(st.circuit_opens, len(BACKOFF_MO_MACH) - 1)
                    st.circuit_open_until = curr + BACKOFF_MO_MACH[bac]
                    st.circuit_opens += 1

    def snapshot(self) -> List[Dict]:
        """Dữ liệu cho bảng điều khiển. KHÔNG chứa prompt hay bí mật."""
        ra = []
        for wid in self.ids():
            s, st = self._specs[wid], self._states[wid]
            ra.append({
                "worker_id": wid,
                "provider": s.provider_family,
                "health": st.health.value,
                "in_flight": st.in_flight,
                "current_task": st.current_task,
                "completed": st.completed,
                "failed": st.failed,
                "success_rate": round(st.success_rate, 3),
                "avg_seconds": round(st.avg_seconds, 2),
                "circuit_open": st.circuit_is_open(),
                "circuit_opens": st.circuit_opens,
                "consecutive_failures": st.consecutive_failures,
                # -- so dang ky worker theo mission (Pool Phase 3) -----------
                "model": s.model,
                "capabilities": sorted(s.capabilities),
                "workspace": s.workspace,
                "auth_realm": s.auth_realm,
                "state": st.pool_state(s).value,
                "active_job": st.active_job,
                "last_seen": round(st.last_seen, 3),
                "failure_count": st.failed,
                "cooldown_until": (round(st.quota_cooldown_until, 3)
                                   if st.quota_cooldown_until else None),
                "quota_signal": st.quota_signal,
                "max_concurrent": s.max_concurrent,
                "has_capacity": st.con_cho(s),
                "detail": st.last_error,
            })
        return ra


# ---------------------------------------------------------------------------
# Sổ mặc định
# ---------------------------------------------------------------------------

#: Các khe worker Antigravity. AG01 là phiên `agy` ĐÃ xác thực trên máy này.
#:
#: AG02..AG08 là những DANH TÍNH ĐỘC LẬP, không phải mảnh quota của AG01. Mỗi
#: khe cần một tài khoản riêng do người vận hành tự đăng nhập bằng chính client
#: của nhà cung cấp. Router KHÔNG tự đăng nhập, KHÔNG xoay tài khoản khi hết
#: quota, và KHÔNG đụng vào token — xem docstring module.
AG_SLOTS = tuple(f"AG{i:02d}" for i in range(1, 9))


def default_registry(*, probe: bool = True) -> WorkerRegistry:
    """Sổ đăng ký phản ánh thứ THẬT SỰ có trên máy này.

    `probe=True` hỏi `ai_router_dispatch` xem CLI nào thực sự tồn tại. Khe nào
    không có client đã xác thực thì vào `UNAVAILABLE` — có mặt trong sổ để
    bảng điều khiển hiển thị được, nhưng không bao giờ được chọn.
    """
    import importlib.util
    import pathlib

    reg = WorkerRegistry()

    reg.register(WorkerSpec(
        worker_id="CLAUDE_LEAD", provider_family="claude",
        execution_type=ExecutionType.NATIVE_LEAD, pool="CLAUDE_OPUS",
        capabilities=frozenset({"architecture", "integration"}),
        trusted_for_high_risk=True,
        notes="phiên đang chạy: lập kế hoạch, dựng DAG, tích hợp, leo thang"))

    for slot in AG_SLOTS:
        reg.register(WorkerSpec(
            worker_id=slot, provider_family="antigravity",
            execution_type=ExecutionType.LOCAL_CLI, pool="GEMINI_FLASH",
            capabilities=frozenset({"recon", "implement", "tests",
                                    "frontend", "review", "challenger"}),
            trusted_for_high_risk=False, max_concurrent=3,
            notes="khe thực thi độc lập; cần tài khoản riêng đã đăng nhập"))

    reg.register(WorkerSpec(
        worker_id="AG_OPUS", provider_family="antigravity",
        execution_type=ExecutionType.LOCAL_CLI, pool="CLAUDE_OPUS",
        capabilities=frozenset({"security_review", "architecture", "review"}),
        trusted_for_high_risk=True,
        notes="Claude Opus trong Antigravity — review bảo mật/sản xuất"))

    reg.register(WorkerSpec(
        worker_id="CODEX", provider_family="codex",
        execution_type=ExecutionType.LOCAL_CLI, pool="CODEX",
        capabilities=frozenset({"review", "implement"}),
        trusted_for_high_risk=False,
        notes="review thường/độc lập; KHÔNG BAO GIỜ review bảo mật"))

    # Adapter plugin (Phase 2-4): tu dang ky WorkerSpec cua chinh no qua
    # register(), registry core khong biet gi ve hinh dang lenh/API rieng
    # cua tung provider. Import tre de tranh vong lap (cac module adapter
    # nay tu import nguoc lai registry.py).
    from scripts.router_v3.grok_adapter import GrokBuildAdapter
    from scripts.router_v3.opencode_adapter import OpenCodeAdapter

    reg.register(GrokBuildAdapter("GROK01").register())
    reg.register(OpenCodeAdapter("OPENCODE01").register())

    if not probe:
        return reg

    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "_disp_probe", root / "scripts" / "ai_router_dispatch.py")
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)

    co_agy = bool(d.find_antigravity())
    co_codex = bool(d.find_codex())

    # CHI AG01 duoc coi la co that: `agy` tren may nay la MOT phien da xac
    # thuc. Cac khe con lai can tai khoan RIENG do nguoi van hanh dang nhap.
    for slot in AG_SLOTS:
        reg.set_health(
            slot,
            Health.HEALTHY if (co_agy and slot == "AG01") else Health.UNAVAILABLE,
            "" if slot == "AG01" else "chưa có client đã xác thực cho khe này")
    reg.set_health("AG_OPUS",
                   Health.HEALTHY if co_agy else Health.UNAVAILABLE)
    reg.set_health("CODEX",
                   Health.HEALTHY if co_codex else Health.UNAVAILABLE,
                   "" if co_codex else "không tìm thấy codex")
    reg.set_health("CLAUDE_LEAD", Health.HEALTHY)

    grok_health = GrokBuildAdapter("GROK01").health()
    reg.set_health("GROK01", grok_health.state, grok_health.detail)
    oc_health = OpenCodeAdapter("OPENCODE01").health()
    reg.set_health("OPENCODE01", oc_health.state, oc_health.detail)
    return reg
