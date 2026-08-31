"""
Mo hinh du lieu GENERIC cho MOT cong viec GPU bat dong bo (async job) —
PROVIDER-TRUNG-LAP, khong gan voi Beam hay bat ky ha tang GPU cu the nao.

VI SAO CAN FILE NAY: tich hop Beam hien tai (`beam_apps/cover_illustrious_app.py`,
goi qua HTTP DONG BO boi `server/cover_pipeline.py::HttpImageCoverProvider`) do
cold-start 40-135+ giay — khong hop ly cho mot client HTTP cho dong bo. Huong
di la mo hinh SUBMIT -> POLL -> FETCH RESULT, dung KHUON voi mo hinh job da
CHUNG MINH trong kho nay cho TTS (`server/domain.py::TtsJob` — `status`,
`lease_expires_at`/`lease_is_live()`, `is_stale`) va cho dich thuat
(`server/translation_domain.py::TranslationJob`). Module nay la ban TONG QUAT
cua khuon do, du dung cho ca sinh anh bia (Beam cover) lan dich thuat
(Beam Hy-MT2) MA KHONG hardcode Beam o bat ky dau trong tang domain/service.

KY LUAT PROVIDER-TRUNG-LAP: module nay khong import beam/torch/diffusers/
httpx/vllm — cung nguyen tac voi `server/character_identity.py`. Xem
`server/tests/test_gpu_job_domain.py::TestGPUJobDomainModuleIsProviderNeutral`
cho bai test THAT bang AST (khong chi ghi trong docstring).

Mot `BeamGPUJobProviderAdapter` THAT se duoc viet o MOT file KHAC sau nay
(vd `server/gpu_job_provider_beam_stub.py`), implement Protocol
`GPUJobProviderAdapter` trong `server/gpu_job_service.py` — CHUA viet dem nay,
vi nhiem vu nay KHONG duoc goi mang that toi Beam hay bat ky provider tra
tien nao.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, FrozenSet, Literal, Optional

from server.domain import new_id, now_iso

# -----------------------------------------------------------------------------
# Enum
# -----------------------------------------------------------------------------


class GPUJobStatus(str, Enum):
    """Vong doi MOT job GPU — cung tinh than voi `domain.JobStatus`/
    `translation.TranslationJobStatus` nhung co them `PROVISIONING`
    (thoi gian cold-start/khoi dong GPU, giai doan RIENG voi `RUNNING`
    THAT su xu ly — chinh giai doan nay la ly do tich hop dong bo cu
    khong con hop ly, xem docstring dau module) va `CANCELLED`."""

    QUEUED = "queued"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Cac trang thai KET THUC — job se khong bao gio doi trang thai nua sau day.
_TERMINAL_STATUSES: FrozenSet[GPUJobStatus] = frozenset({
    GPUJobStatus.COMPLETED, GPUJobStatus.FAILED, GPUJobStatus.CANCELLED,
})


class GPUJobType(str, Enum):
    """
    Loai cong viec GPU. `IMAGE_GENERATION`/`TRANSLATION` la hai loai co
    THAT dang duoc tich hop (Beam cover + Beam Hy-MT2). `TTS`/`VIDEO`/
    `LORA_TRAINING` ton tai CHI de danh cho khong gian ten enum — theo dung
    yeu cau "future-ready but do not implement yet" cua mission: KHONG co
    logic xu ly nao cho ba loai nay, chi la gia tri hop le de tranh phai
    THEM mot GPUJobType/migration moi moi khi co mot subsystem GPU khac gia
    nhap khuon nay.
    """

    IMAGE_GENERATION = "image_generation"
    TRANSLATION = "translation"
    TTS = "tts"
    VIDEO = "video"
    LORA_TRAINING = "lora_training"


# -----------------------------------------------------------------------------
# Phan loai loi — retry classification (judgment call, xem README o day)
# -----------------------------------------------------------------------------
#
# Dat o TANG DOMAIN (khong phai service) de `GPUJob.is_retryable()` tu no
# tra loi duoc ma khong can phu thuoc nguoc vao `gpu_job_service.py` — VA de
# `GPUJobService` dung LAI dung mot nguon that thay vi tu dinh nghia rieng.
# `gpu_job_service.py::classify_error(exc)` moi la noi map MOT exception
# THAT (do adapter nem ra) sang chuoi `error_class` duoi day; module nay chi
# giu chinh sach "chuoi error_class nay co duoc thu lai hay khong".

ErrorDisposition = Literal["retryable", "permanent"]

#: Loi TAM THOI — an toan de THU LAI (mang/timeout/qua tai provider).
RETRYABLE_ERROR_CLASSES: FrozenSet[str] = frozenset({
    "timeout", "network_error", "provider_unavailable", "rate_limited",
})

#: Loi VINH VIEN — KHONG BAO GIO thu lai. Thu lai mot loi khong bao gio tu
#: sua (sai tham so, vi pham chinh sach noi dung, sai xac thuc, model khong
#: ton tai, het han muc) chi dot GPU-giay (tien that) vo ich.
PERMANENT_ERROR_CLASSES: FrozenSet[str] = frozenset({
    "validation_error", "content_policy_violation", "authentication_error",
    "invalid_model", "insufficient_quota",
})

#: So lan thu TOI DA truoc khi mot job gap loi TAM THOI bi chuyen `FAILED`
#: vinh vien. Hang so DON GIAN cho MOT nen mong — CHUA co backoff/jitter/
#: hang doi thu lai rieng (xem `gpu_job_service.py` module docstring: "day
#: la nen mong, khong phai mot bo may retry day du").
MAX_JOB_ATTEMPTS = 3


def classify_error_class(error_class: Optional[str]) -> ErrorDisposition:
    """
    `error_class` (chuoi on dinh, vd "timeout") -> "retryable" | "permanent".

    MAC DINH AN TOAN: mot `error_class` KHONG nam trong danh sach TAM THOI
    da biet (ke ca `None`/chuoi la) duoc coi la "permanent". Tha bo mot loi
    LE RA thu lai duoc con hon la thu lai vo han mot loi KHONG BAO GIO tu
    sua — voi GPU-giay la chi phi that, "fail closed" la lua chon an toan
    hon cho mot danh sach phan loai CHUA day du.
    """
    if error_class in RETRYABLE_ERROR_CLASSES:
        return "retryable"
    return "permanent"


# -----------------------------------------------------------------------------
# Ke toan chi phi — cost accounting (item 4 cua mission)
# -----------------------------------------------------------------------------


@dataclass
class CostMetadata:
    """
    Du lieu KE TOAN/TELEMETRY thuan tren MOT job — KHONG PHAI logic thanh
    toan nguoi dung (mission cam ro: "Do NOT add any user billing/payment
    logic"). Duoc serialize vao `GPUJob.cost_metadata` (mot dict) qua
    `to_dict()`/`from_dict()` de `GPUJob` khong phai rang buoc cung mot
    dataclass co dinh — dict tu do van cho phep them truong rieng theo
    provider (vd `beam_container_id`) ma khong phai doi schema o day.
    """

    gpu_seconds: float = 0.0
    #: $/GPU-giay.
    provider_rate: float = 0.0
    #: TINH TRUOC khi job hoan tat, tu thoi luong DU KIEN (vd theo
    #: model/kich thuoc anh) — dung cho hien thi uoc tinh chi phi SOM.
    estimated_cost: float = 0.0
    #: TINH SAU khi hoan tat, tu `gpu_seconds` THAT SU do duoc.
    actual_cost: float = 0.0
    #: "cold" | "warm" | "unknown" | None (chua biet/chua ap dung).
    cold_or_warm: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpu_seconds": self.gpu_seconds,
            "provider_rate": self.provider_rate,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "cold_or_warm": self.cold_or_warm,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CostMetadata":
        data = data or {}
        return cls(
            gpu_seconds=float(data.get("gpu_seconds", 0.0) or 0.0),
            provider_rate=float(data.get("provider_rate", 0.0) or 0.0),
            estimated_cost=float(data.get("estimated_cost", 0.0) or 0.0),
            actual_cost=float(data.get("actual_cost", 0.0) or 0.0),
            cold_or_warm=data.get("cold_or_warm"),
        )

    @classmethod
    def estimate(cls, gpu_seconds: float, provider_rate: float,
                 cold_or_warm: Optional[str] = None) -> "CostMetadata":
        """Uoc tinh TRUOC khi job chay xong — tu thoi luong DU KIEN."""
        return cls(gpu_seconds=gpu_seconds, provider_rate=provider_rate,
                    estimated_cost=gpu_seconds * provider_rate,
                    cold_or_warm=cold_or_warm)

    def with_actual(self, gpu_seconds: float,
                     provider_rate: Optional[float] = None) -> "CostMetadata":
        """Ban sao voi `actual_cost` tinh tu thoi luong THAT SU, sau khi
        job hoan tat. Giu nguyen `estimated_cost` cu de sau nay doi chieu
        uoc tinh voi thuc te."""
        rate = self.provider_rate if provider_rate is None else provider_rate
        return replace(self, gpu_seconds=gpu_seconds, provider_rate=rate,
                        actual_cost=gpu_seconds * rate)


def compute_input_hash(input_data: Any) -> str:
    """
    Sha256 cua bieu dien JSON CHUAN HOA cua `input_data` — dung cho
    idempotency (item 4 cua mission: "sha256 of the canonicalized input").

    `sort_keys=True`: cung mot dict voi thu tu khoa khac nhau van ra CUNG
    hash. `default=str`: gia tri khong tuan JSON thang (vd Path, datetime)
    khong lam ham nay nem loi — danh doi CHAP NHAN DUOC cho MUC DICH
    idempotency (chi giam trung request, KHONG phai chu ky mat ma: hai input
    that su khac nhau ma str() cua phan khong-JSON trung nhau la truong hop
    hiem va hau qua toi da chi la mot lan dedupe sai, khong phai mat du lieu).
    """
    canonical = json.dumps(input_data, sort_keys=True, default=str,
                            ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Ban ghi chinh
# -----------------------------------------------------------------------------


@dataclass
class GPUJob:
    """
    MOT job GPU bat dong bo — CHUNG cho moi loai (`GPUJobType`) va moi
    provider (`provider`, mot CHUOI nhu "beam", khong phai enum rang buoc
    voi mot provider cu the — xem docstring dau module).

    `output_ref` la THAM CHIEU (object key R2, duong dan cuc bo, ...) toi
    noi luu output, KHONG PHAI chinh bytes output — xem `gpu_job_storage.py`
    (`OutputStorage` Protocol) cho tang luu tru THAT tach biet.

    `provider_job_ref`: dinh danh job PHIA PROVIDER (vd Beam task id), dien
    SAU khi `GPUJobProviderAdapter.submit()` thanh cong — can de cac lan
    `poll()`/`cancel()`/`fetch_result()` sau biet dang hoi ve job nao ben
    phia provider. `None` = chua submit thanh cong lan nao.
    """

    job_type: GPUJobType
    provider: str
    model: str
    status: GPUJobStatus = GPUJobStatus.QUEUED
    #: Sha256 cua input da chuan hoa — xem `compute_input_hash()`.
    input_hash: str = ""
    #: Khoa chong trung TUONG MINH (do caller truyen) hoac NGAM DINH
    #: (= `input_hash`, khi caller khong truyen) — xem
    #: `GPUJobService.submit_job()`'s docstring cho quy tac dedupe day du.
    idempotency_key: Optional[str] = None
    provider_job_ref: Optional[str] = None
    output_ref: Optional[str] = None
    #: Da thu SUBMIT bao nhieu lan — cung vai tro voi `TtsJob.attempts`.
    #: KHONG dem so lan poll; chi dem lan thu gui job toi provider.
    attempts: int = 0
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    #: Tu do, tuy loai job — vd gpu_seconds do (cung co the doc qua
    #: `cost_metadata`), so token, kich thuoc anh, so buoc infer.
    usage_metadata: Dict[str, Any] = field(default_factory=dict)
    #: Xem `CostMetadata`. Luu duoi dang dict qua `.to_dict()`/`.from_dict()`
    #: (`cost()`/`set_cost()` duoi day) de khong ep `GPUJob` phu thuoc chat
    #: vao mot schema chi phi co dinh.
    cost_metadata: Dict[str, Any] = field(default_factory=dict)
    job_id: str = field(default_factory=lambda: new_id("gpu"))
    created_at: str = field(default_factory=now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def is_terminal(self) -> bool:
        """COMPLETED/FAILED/CANCELLED — job se khong doi trang thai nua."""
        return self.status in _TERMINAL_STATUSES

    def is_retryable(self) -> bool:
        """
        Job nay co NEN duoc thu lai (submit lai) hay khong.

        Chi True khi CA BA dieu kien dung: job da `FAILED` (khong phai dang
        chay/da huy/da xong), con LUOT thu (`attempts < MAX_JOB_ATTEMPTS`),
        VA `error_class` da ghi lai duoc phan loai la "retryable" (xem
        `classify_error_class`). Day la mot ham TRA LOI, khong TU thu lai —
        `GPUJobService` la noi thuc su goi lai `submit()`.
        """
        if self.status is not GPUJobStatus.FAILED:
            return False
        if self.attempts >= MAX_JOB_ATTEMPTS:
            return False
        return classify_error_class(self.error_class) == "retryable"

    def cost(self) -> CostMetadata:
        """Doc `cost_metadata` (dict tho) thanh mot `CostMetadata` go."""
        return CostMetadata.from_dict(self.cost_metadata)

    def set_cost(self, cost: CostMetadata) -> None:
        """Ghi mot `CostMetadata` xuong `cost_metadata` (dict)."""
        self.cost_metadata = cost.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "provider": self.provider,
            "model": self.model,
            "status": self.status.value,
            "input_hash": self.input_hash,
            "idempotency_key": self.idempotency_key,
            "provider_job_ref": self.provider_job_ref,
            "output_ref": self.output_ref,
            "attempts": self.attempts,
            "error_class": self.error_class,
            "error_message": self.error_message,
            "usage_metadata": dict(self.usage_metadata),
            "cost_metadata": dict(self.cost_metadata),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass(frozen=True)
class GPUJobStatusResponse:
    """
    Hop dong ON DINH cho MOT lan client hoi trang thai job (item 2 cua
    mission: "Polling/status API contract"). Mot route FastAPI TUONG LAI
    (chua viet dem nay) co the tra thang `.to_dict()` cua doi tuong nay lam
    JSON response, khong phai tu suy doan lai hinh dang tu `GPUJob.to_dict()`
    (vd khong lo `output_ref` khi job CHUA xong — xem `from_job`).
    """

    job_id: str
    job_type: str
    status: str
    provider: str
    model: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    attempts: int
    error_class: Optional[str]
    error_message: Optional[str]
    #: Chi co gia tri khi `status == "completed"` — mot client khong nen
    #: doc duoc mot `output_ref` "rac" cua mot job chua thuc su xong.
    output_ref: Optional[str]
    usage_metadata: Dict[str, Any]
    cost_metadata: Dict[str, Any]

    @classmethod
    def from_job(cls, job: GPUJob) -> "GPUJobStatusResponse":
        return cls(
            job_id=job.job_id,
            job_type=job.job_type.value,
            status=job.status.value,
            provider=job.provider,
            model=job.model,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            attempts=job.attempts,
            error_class=job.error_class,
            error_message=job.error_message,
            output_ref=(job.output_ref
                        if job.status is GPUJobStatus.COMPLETED else None),
            usage_metadata=dict(job.usage_metadata),
            cost_metadata=dict(job.cost_metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "attempts": self.attempts,
            "error_class": self.error_class,
            "error_message": self.error_message,
            "output_ref": self.output_ref,
            "usage_metadata": self.usage_metadata,
            "cost_metadata": self.cost_metadata,
        }
