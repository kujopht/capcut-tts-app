"""
Truu tuong hoa noi LUU OUTPUT cua mot GPU job (anh bia da sinh, ban dich,
sau nay co the la audio/video) — item 3 cua mission.

`GPUJob`/`GPUJobService` (xem `server/gpu_job_domain.py`,
`server/gpu_job_service.py`) KHONG BAO GIO import module nay hay bat ky
adapter luu tru cu the nao: chung chi cam `output_ref`, mot CHUOI kho hieu
(object key R2, duong dan cuc bo, ...), khong bao gio chinh bytes output.
`OutputStorage` la ranh gioi de MOT adapter R2 THAT (mirror
`server/r2_adapter.py::R2StorageAdapter`, dung nguyen tac voi
`server/adapters.py`'s Protocol cho audio TTS) co the duoc viet SAU, cung
giao dien nay, ma khong dong cham gi den tang domain/service.

KHONG wire adapter R2 that dem nay — mission cam ro khong duoc goi mang that
toi bat ky ha tang tra tien nao. Chi co Protocol + mot ban MOCK trong bo nho
cho test/dev.
"""

from __future__ import annotations

import threading
from typing import Dict, Protocol, Tuple


class OutputStorage(Protocol):
    """
    Tang luu tru output CHUNG cho moi loai job GPU. Hai thao tac, doi xung
    voi cap `submit`/`fetch_result` cua `GPUJobProviderAdapter`
    (`server/gpu_job_service.py`): `save()` khi job hoan tat va co bytes
    that su, `load()` khi mot noi khac (route tai file, worker doi soat)
    can doc lai.
    """

    def save(self, job_id: str, data: bytes, content_type: str) -> str:
        """Luu `data`, tra ve `output_ref` — khoa/URI rieng cua tang luu
        tru, KHONG PHAI chinh `data`."""
        ...

    def load(self, output_ref: str) -> bytes:
        """Doc lai bytes tu MOT `output_ref` da tung tra ve boi `save()`.
        Nem `KeyError` neu `output_ref` khong ton tai."""
        ...


class MockOutputStorage:
    """
    Ban TRONG BO NHO cho test/dev — KHONG ben vung, mirror
    `MockGPUJobStore` (`server/gpu_job_service.py`) va
    `MockTranslationStore` (`server/translation_store.py`) ve triet ly:
    du lieu chi song trong vong doi tien trinh.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._objects: Dict[str, Tuple[bytes, str]] = {}
        self._counter = 0

    def save(self, job_id: str, data: bytes, content_type: str) -> str:
        with self._lock:
            self._counter += 1
            output_ref = f"mock://gpu-jobs/{job_id}/{self._counter}"
            self._objects[output_ref] = (bytes(data), content_type)
            return output_ref

    def load(self, output_ref: str) -> bytes:
        with self._lock:
            entry = self._objects.get(output_ref)
        if entry is None:
            raise KeyError(f"Không tìm thấy output_ref: {output_ref}")
        return entry[0]

    def content_type_of(self, output_ref: str) -> str:
        """Khong nam trong Protocol `OutputStorage` (chi tien ich rieng cho
        ban mock/test) — tra ve `content_type` da luu cung `output_ref`."""
        with self._lock:
            entry = self._objects.get(output_ref)
        if entry is None:
            raise KeyError(f"Không tìm thấy output_ref: {output_ref}")
        return entry[1]
