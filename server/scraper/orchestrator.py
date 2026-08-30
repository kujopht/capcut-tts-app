"""Dieu phoi harvest o CAP NGUON, nam tren pipeline scrape hien co.

Module nay co chu dich KHONG biet cach tai/phan tich mot chuong. Moi cong
viec that deu di qua ``ScraperOpsService``; lop nay chi gioi han toc do,
thu lai, co lap loi giua cac nguon va theo doi circuit breaker trong bo nho.
Mot cron/route ben ngoai goi :meth:`HarvestOrchestrator.run_one_cycle` --
module KHONG tao thread hay vong lap nen rieng.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from server.scraper.contract import domain_of
from server.scraper.run_state import ScrapeRunStatus, TERMINAL_RUN_STATUSES


_CIRCUIT_CLOSED = "closed"
_CIRCUIT_OPEN = "open"
_CIRCUIT_HALF_OPEN = "half_open"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _gia_tri_enum(value: Any) -> str:
    """Doc duoc ca enum that lan chuoi don gian cua fake trong test."""
    raw = getattr(value, "value", value)
    return str(raw or "")


@dataclass
class HarvestSourceState:
    """Cau hinh + trang thai runtime cua MOT series/source.

    ``source_url`` hoac ``run_id`` phai co it nhat mot. ``source_url`` dung
    chinh URL series ma ``ScraperOpsService.start_or_continue`` nhan;
    ``source_domain`` duoc suy ra bang cung ``domain_of`` voi scraper hien
    tai, nen khong tao mot registry domain canh tranh voi ``SiteConfig``.

    Trang thai circuit breaker chi ton tai trong bo nho. Neu process khoi
    dong lai, no bat dau CLOSED -- phu hop pham vi task; production co the
    thay dataclass/store nay bang kho ben vung sau ma khong doi service scrape.
    """

    source_url: str = ""
    run_id: str = ""
    min_interval_seconds: float = 0.0
    max_chapters_per_cycle: Optional[int] = None

    consecutive_failures: int = 0
    total_failures: int = 0
    last_success_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    last_error: str = ""
    circuit_state: str = _CIRCUIT_CLOSED
    circuit_opened_at: Optional[str] = None

    _last_scheduled_monotonic: Optional[float] = field(
        default=None, repr=False)
    _circuit_opened_monotonic: Optional[float] = field(
        default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.source_url and not self.run_id:
            raise ValueError("Moi nguon phai co source_url hoac run_id")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds khong duoc am")
        if (self.max_chapters_per_cycle is not None
                and self.max_chapters_per_cycle < 1):
            raise ValueError("max_chapters_per_cycle phai >= 1")
        if self.circuit_state not in {
                _CIRCUIT_CLOSED, _CIRCUIT_OPEN, _CIRCUIT_HALF_OPEN}:
            raise ValueError("circuit_state khong hop le")

    @property
    def source_domain(self) -> str:
        return domain_of(self.source_url) if self.source_url else ""


class HarvestOrchestrator:
    """Dieu phoi MOT chu ky co gioi han qua nhieu nguon.

    Moi lan :meth:`run_one_cycle` goi TOI DA mot ``drive`` thanh cong cho
    moi nguon (va ``max_chapters`` lai gioi han so chuong cua chinh cycle
    do). Loi cua mot nguon duoc bat rieng, nen khong chan nguon tiep theo.

    ``status_report()`` la read-only va tra ve JSON-compatible dict CHINH
    XAC theo shape sau de route admin tuong lai co the expose truc tiep::

        {
          "generated_at": "<ISO-8601 UTC>",
          "sources": [{
            "source_url": str,
            "source_domain": str,
            "run_id": str,
            "health": "unknown|healthy|degraded|recovering|unhealthy",
            "last_successful_harvest": str | None,
            "last_attempt_at": str | None,
            "consecutive_failures": int,
            "total_failures": int,
            "last_error": str,
            "items_quarantined": int,
            "circuit_breaker": {
              "state": "closed|open|half_open",
              "opened_at": str | None,
              "retry_after_seconds": float
            }
          }],
          "jobs": {"queued_runs": int, "running_runs": int},
          "items_quarantined": int
        }

    ``failed`` la trang thai terminal-error (quarantine-equivalent) cua
    ``ScrapeRunItem``; bao cao cong cac ``ScrapeRun.count_failed`` that do
    ``ScraperOpsService.list_runs()`` tra ve, khong doc kho private.
    """

    def __init__(
            self,
            ops_service: Any,
            sources: Sequence[HarvestSourceState],
            *,
            max_chapters_per_source: Optional[int] = None,
            max_retries: int = 2,
            backoff_base_seconds: float = 1.0,
            backoff_max_seconds: float = 60.0,
            failure_threshold: int = 3,
            circuit_cooldown_seconds: float = 300.0,
            sleep_fn: Callable[[float], None] = time.sleep,
            clock_fn: Callable[[], float] = time.monotonic,
            now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        if max_chapters_per_source is not None and max_chapters_per_source < 1:
            raise ValueError("max_chapters_per_source phai >= 1")
        if max_retries < 0:
            raise ValueError("max_retries khong duoc am")
        if backoff_base_seconds < 0 or backoff_max_seconds < 0:
            raise ValueError("backoff khong duoc am")
        if failure_threshold < 1:
            raise ValueError("failure_threshold phai >= 1")
        if circuit_cooldown_seconds < 0:
            raise ValueError("circuit_cooldown_seconds khong duoc am")

        self._ops = ops_service
        self._sources = list(sources)
        self._max_chapters = max_chapters_per_source
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._failure_threshold = failure_threshold
        self._cooldown = circuit_cooldown_seconds
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._now = now_fn

    @property
    def sources(self) -> Sequence[HarvestSourceState]:
        """View bat bien theo giao uoc (tuple) cua cac state dang theo doi."""
        return tuple(self._sources)

    def run_one_cycle(self) -> Dict[str, Any]:
        """Cho moi nguon den han mot co hoi harvest co retry bi chan tren.

        Ket qua la mot tom tat JSON-compatible cua CHINH lan goi nay. Nguon
        dang rate-limit/circuit-open duoc ghi ``skipped``; exception da het
        retry duoc ghi ``failed`` va vong lap van tiep tuc nguon sau.
        """
        ket_qua: List[Dict[str, Any]] = []
        for source in self._sources:
            # Bien gioi co lap loi CAP NGUON: bat trong tung iteration,
            # khong co exception cua source A thoat ra chan source B.
            ket_qua.append(self._run_source(source))

        return {
            "attempted": sum(1 for item in ket_qua
                             if item["outcome"] in {"succeeded", "failed"}),
            "succeeded": sum(1 for item in ket_qua
                             if item["outcome"] == "succeeded"),
            "failed": sum(1 for item in ket_qua
                          if item["outcome"] == "failed"),
            "skipped": sum(1 for item in ket_qua
                           if item["outcome"] == "skipped"),
            "sources": ket_qua,
        }

    def _run_source(self, source: HarvestSourceState) -> Dict[str, Any]:
        now_mono = self._clock()
        effective = self._effective_circuit_state(source, now_mono)
        if effective == _CIRCUIT_OPEN:
            return self._cycle_result(source, "skipped", reason="circuit_open")
        if effective == _CIRCUIT_HALF_OPEN:
            # Chuyen trang thai CHI khi that su sap probe; status_report
            # chi tinh effective state va khong mutate.
            source.circuit_state = _CIRCUIT_HALF_OPEN

        if (source._last_scheduled_monotonic is not None
                and now_mono - source._last_scheduled_monotonic
                < source.min_interval_seconds):
            return self._cycle_result(source, "skipped", reason="rate_limited")

        source._last_scheduled_monotonic = now_mono
        source.last_attempt_at = self._timestamp()
        # HALF_OPEN chi probe MOT lan de tranh vua het cooldown da hammer lai
        # nguon. CLOSED moi duoc huong retry+backoff day du.
        so_lan_thu = 1 if source.circuit_state == _CIRCUIT_HALF_OPEN else (
            self._max_retries + 1)
        last_exc: Optional[Exception] = None

        for attempt in range(so_lan_thu):
            try:
                detail = self._drive_source_once(source)
            except Exception as exc:  # noqa: BLE001 - bien gioi nguon co chu dich
                last_exc = exc
                if attempt + 1 < so_lan_thu:
                    delay = min(
                        self._backoff_max,
                        self._backoff_base * (2 ** attempt),
                    )
                    self._sleep(delay)
                    continue
                break

            self._record_success(source)
            return self._cycle_result(
                source, "succeeded", attempts=attempt + 1, detail=detail)

        self._record_failure(source, last_exc)
        return self._cycle_result(
            source, "failed", attempts=so_lan_thu,
            error=source.last_error)

    def _drive_source_once(self, source: HarvestSourceState) -> Dict[str, Any]:
        run = self._find_run(source.run_id) if source.run_id else None
        if run is not None and not source.source_url:
            source.source_url = str(getattr(run, "source_url", "") or "")

        if not source.run_id:
            started = self._ops.start_or_continue(source.source_url)
            run = self._extract_run(started)
            source.run_id = str(getattr(run, "run_id", "") or "")
            if not source.run_id:
                raise ValueError("start_or_continue khong tra ve run_id")
        elif run is not None and self._is_terminal_run(run):
            updates = self._ops.check_for_updates(source.run_id)
            if not bool(updates.get("has_changes")):
                return {"action": "checked_for_updates", "has_changes": False}
            if not source.source_url:
                raise ValueError("Can source_url de khoi dong lai run co cap nhat")
            started = self._ops.start_or_continue(source.source_url)
            run = self._extract_run(started)
            source.run_id = str(getattr(run, "run_id", source.run_id) or source.run_id)

        max_chapters = (source.max_chapters_per_cycle
                        if source.max_chapters_per_cycle is not None
                        else self._max_chapters)
        driven = self._ops.drive(source.run_id, max_chapters=max_chapters)
        driven_run = self._extract_run(driven)
        return {
            "action": "drive",
            "run_status": _gia_tri_enum(getattr(driven_run, "status", "")),
        }

    def _find_run(self, run_id: str) -> Optional[Any]:
        if not run_id:
            return None
        listed = self._ops.list_runs()
        for run in listed.get("runs", []):
            if str(getattr(run, "run_id", "")) == run_id:
                return run
        return None

    @staticmethod
    def _extract_run(result: Any) -> Any:
        if isinstance(result, dict):
            return result.get("run")
        return None

    @staticmethod
    def _is_terminal_run(run: Any) -> bool:
        status = _gia_tri_enum(getattr(run, "status", ""))
        return status in {s.value for s in TERMINAL_RUN_STATUSES}

    def _record_success(self, source: HarvestSourceState) -> None:
        source.consecutive_failures = 0
        source.last_success_at = self._timestamp()
        source.last_error = ""
        source.circuit_state = _CIRCUIT_CLOSED
        source.circuit_opened_at = None
        source._circuit_opened_monotonic = None

    def _record_failure(
            self, source: HarvestSourceState,
            exc: Optional[Exception]) -> None:
        source.consecutive_failures += 1
        source.total_failures += 1
        source.last_error = str(exc or "unknown source failure")[:1000]
        if (source.circuit_state == _CIRCUIT_HALF_OPEN
                or source.consecutive_failures >= self._failure_threshold):
            source.circuit_state = _CIRCUIT_OPEN
            source._circuit_opened_monotonic = self._clock()
            source.circuit_opened_at = self._timestamp()

    def _effective_circuit_state(
            self, source: HarvestSourceState, now_mono: float) -> str:
        if source.circuit_state != _CIRCUIT_OPEN:
            return source.circuit_state
        opened = source._circuit_opened_monotonic
        if opened is not None and now_mono - opened >= self._cooldown:
            return _CIRCUIT_HALF_OPEN
        return _CIRCUIT_OPEN

    @staticmethod
    def _cycle_result(
            source: HarvestSourceState,
            outcome: str,
            *,
            reason: str = "",
            attempts: int = 0,
            error: str = "",
            detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "source_url": source.source_url,
            "run_id": source.run_id,
            "outcome": outcome,
            "reason": reason,
            "attempts": attempts,
            "error": error,
            "detail": detail or {},
        }

    def status_report(self) -> Dict[str, Any]:
        """Tra snapshot ops theo shape da ghi trong docstring cua class.

        Ham khong sua source state va chi goi primitive doc
        ``ScraperOpsService.list_runs()``.
        """
        listed = self._ops.list_runs()
        runs = list(listed.get("runs", []))
        by_id = {str(getattr(run, "run_id", "")): run for run in runs}
        now_mono = self._clock()
        source_rows: List[Dict[str, Any]] = []

        for source in self._sources:
            run = by_id.get(source.run_id)
            quarantined = int(getattr(run, "count_failed", 0) or 0)
            circuit = self._effective_circuit_state(source, now_mono)
            retry_after = 0.0
            if circuit == _CIRCUIT_OPEN:
                opened = source._circuit_opened_monotonic
                if opened is not None:
                    retry_after = max(0.0, self._cooldown - (now_mono - opened))

            if circuit == _CIRCUIT_OPEN:
                health = "unhealthy"
            elif circuit == _CIRCUIT_HALF_OPEN:
                health = "recovering"
            elif source.consecutive_failures or quarantined:
                health = "degraded"
            elif source.last_success_at:
                health = "healthy"
            else:
                health = "unknown"

            source_rows.append({
                "source_url": (source.source_url
                               or str(getattr(run, "source_url", "") or "")),
                "source_domain": (source.source_domain
                                  or str(getattr(run, "source_domain", "") or "")),
                "run_id": source.run_id,
                "health": health,
                "last_successful_harvest": source.last_success_at,
                "last_attempt_at": source.last_attempt_at,
                "consecutive_failures": source.consecutive_failures,
                "total_failures": source.total_failures,
                "last_error": source.last_error,
                "items_quarantined": quarantined,
                "circuit_breaker": {
                    "state": circuit,
                    "opened_at": source.circuit_opened_at,
                    "retry_after_seconds": round(retry_after, 3),
                },
            })

        queued = sum(
            1 for run in runs
            if _gia_tri_enum(getattr(run, "status", ""))
            == ScrapeRunStatus.PLANNING.value)
        running = sum(
            1 for run in runs
            if _gia_tri_enum(getattr(run, "status", ""))
            == ScrapeRunStatus.RUNNING.value)
        quarantined_total = sum(
            int(getattr(run, "count_failed", 0) or 0) for run in runs)
        return {
            "generated_at": self._timestamp(),
            "sources": source_rows,
            "jobs": {"queued_runs": queued, "running_runs": running},
            "items_quarantined": quarantined_total,
        }

    def _timestamp(self) -> str:
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc).isoformat()
