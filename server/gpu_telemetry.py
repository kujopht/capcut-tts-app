"""
Cau truc du lieu QUAN SAT (observability) cho mot lan chay cong viec GPU
(sinh anh bia, dich thuat, hay bat ky tac vu GPU/CPU nang khac trong tuong
lai) - DOC LAP HOAN TOAN voi provider, KHONG import beam/torch/diffusers/
httpx/PIL (xem test_gpu_telemetry.py cho kiem tra AST that, cung ky thuat
voi server/tests/test_character_identity.py).

VI SAO CAN FILE NAY: mission "Media AI Production Foundation" (Track E)
can mot noi GHI LAI so lieu van hanh THAT (thoi gian nap model, thoi gian
suy luan, do tre hang doi/khoi dong, chi phi uoc tinh, thanh cong/that
bai...) cho MOI lan chay - de sau nay so sanh provider/chien luoc (vd Beam
vs mot provider GPU khac, prompt-only vs reference-conditioned) bang DU
LIEU THAT thay vi cam tinh. Day CHI la cau truc du lieu + mot kho luu
TRONG BO NHO cho test/local (cung quy uoc voi MockWalletStore trong
server/image_wallet_store.py) - KHONG noi toi bat ky dashboard/analytics
SaaS that nao, khong goi mang.

`GPUJobTelemetry` dung CHUNG cho ca job anh (image_width/image_height) lan
job dich thuat/van ban (source_chars/output_chars) - cac truong khong ap
dung cho mot loai job thi de None, KHONG bat buoc dien. Day la lua chon
CO Y THUC: mot bang telemetry chung, don gian, de truy van theo thoi gian
- thay vi hai class rieng biet lam phinh dan cho mot nen tang con non tre
chi co mot vai loai job.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GPUJobTelemetry:
    """Mot ban ghi quan sat cho MOT lan chay cong viec GPU/xu ly nang.

    Thoi gian (giay, float):
      - `model_load_seconds`: thoi gian nap model vao bo nho/VRAM (co the
        0.0 neu model da "am" san - warm container).
      - `inference_seconds`: thoi gian suy luan THUAN (khong tinh nap
        model/hang doi).
      - `wall_seconds`: TONG thoi gian tu luc goi den luc co ket qua
        (>= model_load_seconds + inference_seconds + queue_or_provisioning_delay_seconds,
        co the lon hon vi con overhead mang/serialize khac).
      - `queue_or_provisioning_delay_seconds`: thoi gian cho container/GPU
        san sang (cold-start scale-to-zero cua Beam la vi du that).

    Kich thuoc dau ra (Optional - chi ap dung theo loai job):
      - `image_width`/`image_height`: kich thuoc anh (job sinh anh).
      - `source_chars`/`output_chars`: do dai van ban vao/ra (job dich
        thuat/van ban).
      - `output_bytes`: kich thuoc dau ra tho (byte) - ap dung duoc cho
        moi loai job (anh hay van ban deu co byte count).

    `gpu_type`/`provider`: chuoi thuan (vd "RTX4090"/"beam") - KHONG phai
    tham chieu SDK, giu module nay provider-trung-lap.

    `error_category`: chuoi PHAN LOAI loi NGAN GON (vd "timeout",
    "transient_5xx", "invalid_response") khi `success=False` - KHONG phai
    traceback/thong diep loi day du (tranh ro ri chi tiet nhay cam/qua dai
    vao mot ban ghi telemetry duoc ky vong nho gon).
    """

    gpu_type: str
    provider: str
    model_load_seconds: float = 0.0
    inference_seconds: float = 0.0
    wall_seconds: float = 0.0
    queue_or_provisioning_delay_seconds: float = 0.0
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    source_chars: Optional[int] = None
    output_chars: Optional[int] = None
    output_bytes: int = 0
    estimated_cost_usd: float = 0.0
    success: bool = True
    error_category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Chuyen sang dict thuan - tien luu kem job record (vd JSON hoa
        de ghi vao mot store khac) ma khong ro ri kieu dataclass."""
        return asdict(self)


class MockGPUTelemetryStore:
    """Kho TRONG BO NHO cho test/local - cung quy uoc `Mock*Store` voi
    server/image_wallet_store.py::MockWalletStore. KHONG ben vung qua lan
    khoi dong lai, KHONG goi bat ky dich vu telemetry/analytics that nao -
    chi phuc vu unit test va kiem tra thu cong cuc bo."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[GPUJobTelemetry] = []

    def record(self, telemetry: GPUJobTelemetry) -> GPUJobTelemetry:
        with self._lock:
            self._records.append(telemetry)
            return telemetry

    def list_recent(self, limit: int = 50) -> List[GPUJobTelemetry]:
        """`limit` ban ghi GAN NHAT (moi nhat truoc) - mac dinh 50 de
        tranh mot lan doc vo tinh keo toan bo lich su neu kho lon dan
        theo thoi gian."""
        with self._lock:
            if limit <= 0:
                return []
            return list(reversed(self._records[-limit:]))

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
