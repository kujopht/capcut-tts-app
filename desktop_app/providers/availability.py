"""
Trang thai kha dung cua tung giong: cache co han + circuit breaker.

Hai co che doc lap:

1. `AvailabilityStore` - nho ket qua probe trong 30 phut. Probe con hieu luc
   thi KHONG chay lai, tranh goi API vo ich.

2. `CircuitBreaker` - sau 3 loi LIEN TIEP cua cung mot provider thi "mo mach"
   60 giay. Trong thoi gian do cac job cua provider do bi tu choi ngay lap tuc
   thay vi tiep tuc dam vao mot dich vu dang hong. Provider khac KHONG bi anh
   huong.

Module nay khong import PySide6 va khong goi mang.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from desktop_app.providers.base import StatusInfo, VoiceStatus

#: Ket qua probe duoc coi la con hieu luc trong 30 phut.
PROBE_TTL_SECONDS = 30 * 60

#: So loi lien tiep truoc khi mo mach.
CIRCUIT_FAILURE_THRESHOLD = 3

#: Thoi gian mo mach.
CIRCUIT_OPEN_SECONDS = 60.0


# -----------------------------------------------------------------------------
# Cache trang thai
# -----------------------------------------------------------------------------


class AvailabilityStore:
    """
    Luu trang thai kha dung theo `voice.id`, co han su dung.

    An toan luong: probe chay o thread nen trong khi giao dien doc lien tuc.
    """

    def __init__(self, ttl_seconds: float = PROBE_TTL_SECONDS, clock=time.time):
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._data: Dict[str, StatusInfo] = {}

    # -- doc ------------------------------------------------------------------

    def get(self, voice_id: str) -> StatusInfo:
        """Trang thai hien tai. Het han thi tu dong lui ve UNKNOWN."""
        with self._lock:
            info = self._data.get(voice_id)
            if info is None:
                return StatusInfo()
            if self._expired(info):
                return StatusInfo(
                    VoiceStatus.UNKNOWN, "Kết quả kiểm tra đã quá hạn", info.checked_at
                )
            return info

    def is_fresh(self, voice_id: str) -> bool:
        """
        Ket qua probe con hieu luc khong.

        Trang thai CHECKING khong duoc coi la ket qua - no chi la trang thai
        tam thoi trong luc dang chay.
        """
        with self._lock:
            info = self._data.get(voice_id)
            if info is None or info.checked_at is None:
                return False
            if info.status == VoiceStatus.CHECKING:
                return False
            return not self._expired(info)

    def _expired(self, info: StatusInfo) -> bool:
        if info.checked_at is None:
            return False
        return (self._clock() - float(info.checked_at)) > self._ttl

    def snapshot(self) -> Dict[str, StatusInfo]:
        with self._lock:
            return dict(self._data)

    # -- ghi ------------------------------------------------------------------

    def set(
        self,
        voice_id: str,
        status: VoiceStatus,
        reason: str = "",
        checked_at: Optional[float] = None,
    ) -> StatusInfo:
        """Ghi nhan trang thai moi. CHECKING khong dat moc thoi gian kiem tra."""
        with self._lock:
            if status == VoiceStatus.CHECKING:
                previous = self._data.get(voice_id)
                stamp = previous.checked_at if previous else None
            else:
                stamp = self._clock() if checked_at is None else float(checked_at)
            info = StatusInfo(status=status, reason=reason, checked_at=stamp)
            self._data[voice_id] = info
            return info

    def mark_checking(self, voice_id: str) -> StatusInfo:
        return self.set(voice_id, VoiceStatus.CHECKING, "Đang kiểm tra...")

    def invalidate(self, voice_id: str) -> None:
        with self._lock:
            self._data.pop(voice_id, None)

    def invalidate_provider(self, provider_id: str) -> int:
        """Xoa cache cua toan bo giong thuoc mot provider."""
        prefix = f"{provider_id}:"
        with self._lock:
            stale = [k for k in self._data if k.startswith(prefix)]
            for key in stale:
                self._data.pop(key, None)
            return len(stale)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    # -- thong ke -------------------------------------------------------------

    def count_by_status(self, voice_ids: Iterable[str]) -> Dict[VoiceStatus, int]:
        counts: Dict[VoiceStatus, int] = {status: 0 for status in VoiceStatus}
        for voice_id in voice_ids:
            counts[self.get(voice_id).status] += 1
        return counts

    def stale_ids(self, voice_ids: Iterable[str]) -> List[str]:
        """Cac giong CHUA co ket qua con hieu luc - dung cho 'kiem tra tat ca'."""
        return [vid for vid in voice_ids if not self.is_fresh(vid)]


# -----------------------------------------------------------------------------
# Circuit breaker
# -----------------------------------------------------------------------------


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: Optional[float] = None
    last_reason: str = ""


class CircuitBreaker:
    """
    Mot circuit breaker RIENG cho tung provider.

    Provider CapCut hong khong duoc lam dung job cua Edge hay Piper.
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_FAILURE_THRESHOLD,
        open_seconds: float = CIRCUIT_OPEN_SECONDS,
        clock=time.monotonic,
    ):
        self._threshold = int(threshold)
        self._open_seconds = float(open_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._states: Dict[str, CircuitState] = {}

    def _state(self, provider_id: str) -> CircuitState:
        state = self._states.get(provider_id)
        if state is None:
            state = CircuitState()
            self._states[provider_id] = state
        return state

    # -- ghi nhan ket qua -----------------------------------------------------

    def record_success(self, provider_id: str) -> None:
        """Thanh cong xoa sach chuoi loi - dem phai LIEN TIEP moi mo mach."""
        with self._lock:
            state = self._state(provider_id)
            state.failures = 0
            state.opened_at = None
            state.last_reason = ""

    def record_failure(self, provider_id: str, reason: str = "") -> bool:
        """Ghi nhan mot loi. Tra ve True neu vua mo mach."""
        with self._lock:
            state = self._state(provider_id)
            state.failures += 1
            state.last_reason = reason or state.last_reason
            if state.failures >= self._threshold and state.opened_at is None:
                state.opened_at = self._clock()
                return True
            return False

    # -- truy van -------------------------------------------------------------

    def is_open(self, provider_id: str) -> bool:
        """Mach co dang mo khong. Tu dong dong lai khi het thoi gian."""
        with self._lock:
            state = self._states.get(provider_id)
            if state is None or state.opened_at is None:
                return False
            if (self._clock() - state.opened_at) >= self._open_seconds:
                # Het gio: dong mach, cho thu lai tu dau
                state.opened_at = None
                state.failures = 0
                return False
            return True

    def remaining_seconds(self, provider_id: str) -> float:
        with self._lock:
            state = self._states.get(provider_id)
            if state is None or state.opened_at is None:
                return 0.0
            left = self._open_seconds - (self._clock() - state.opened_at)
            return max(0.0, left)

    def failure_count(self, provider_id: str) -> int:
        with self._lock:
            state = self._states.get(provider_id)
            return state.failures if state else 0

    def last_reason(self, provider_id: str) -> str:
        with self._lock:
            state = self._states.get(provider_id)
            return state.last_reason if state else ""

    def reset(self, provider_id: Optional[str] = None) -> None:
        with self._lock:
            if provider_id is None:
                self._states.clear()
            else:
                self._states.pop(provider_id, None)

    def status_text(self, provider_id: str) -> str:
        """Chuoi ngan cho thanh trang thai duoi cung."""
        if self.is_open(provider_id):
            return f"tạm ngưng {self.remaining_seconds(provider_id):.0f}s"
        failures = self.failure_count(provider_id)
        if failures:
            return f"{failures} lỗi liên tiếp"
        return "bình thường"
