"""Trang thai/so lieu — de Router Control Center doc duoc sau nay.

Hai rang buoc dinh hinh module nay:

1. **Router Control Center chua ton tai.** Nen day khong duoc la mot API
   ma no phai goi dung cach; no la mot TEP JSON o mot duong dan on dinh.
   Bat cu thu gi doc duoc tep deu tieu thu duoc — mot `cat`, mot scrape
   node_exporter, hay Control Center that su khi no ra doi.

2. **Farmer chay tren may co hai worker production.** Ghi tep phai NGUYEN
   TO (ghi tam roi `os.replace`), neu khong mot lan doc dung luc dang ghi se
   thay JSON cut doi va nguoi doc se tuong farmer da chet.

Hinh dang duoc giu ON DINH — them truong thi duoc, doi y nghia mot truong da
co thi khong.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_STATUS_PATH = "/var/lib/fanfic-farmer/status.json"
ENV_STATUS_PATH = "FARMER_STATUS_PATH"

#: Tang phien ban khi hinh dang doi theo kieu KHONG tuong thich nguoc.
STATUS_SCHEMA_VERSION = 1


def status_path() -> Path:
    return Path(os.environ.get(ENV_STATUS_PATH) or DEFAULT_STATUS_PATH)


@dataclass
class LaneMetrics:
    """So lieu cua MOT lan san xuat trong MOT vong."""
    discovered: int = 0
    deduped: int = 0
    reviewed: int = 0
    approved: int = 0
    rejected: int = 0
    produced: int = 0
    published_candidates: int = 0
    blocked_no_cover: int = 0
    failed: int = 0
    skipped_quota: int = 0
    errors: List[str] = field(default_factory=list)

    def note_error(self, msg: str, gioi_han: int = 10) -> None:
        if len(self.errors) < gioi_han:
            self.errors.append(msg[:300])

    def as_dict(self) -> Dict[str, Any]:
        return {
            "discovered": self.discovered, "deduped": self.deduped,
            "reviewed": self.reviewed, "approved": self.approved,
            "rejected": self.rejected, "produced": self.produced,
            "published_candidates": self.published_candidates,
            "blocked_no_cover": self.blocked_no_cover,
            "failed": self.failed, "skipped_quota": self.skipped_quota,
            "errors": list(self.errors),
        }


@dataclass
class FarmerStatus:
    """Anh chup toan cuc — mot vong quet, cong voi tinh trang han muc."""
    schema_version: int = STATUS_SCHEMA_VERSION
    started_at: str = ""
    updated_at: str = ""
    round_number: int = 0
    round_started_at: str = ""
    round_seconds: float = 0.0
    healthy: bool = True
    #: Ly do KHONG khoe. Rong khi khoe. Day la truong ma mot bang dieu khien
    #: se hien to nhat, nen no phai la mot cau nguoi doc duoc.
    unhealthy_reason: str = ""
    lanes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    quotas: Dict[str, Any] = field(default_factory=dict)
    #: Tong don gian tich luy tron doi tien trinh — de ve do thi.
    totals: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "round": {
                "number": self.round_number,
                "started_at": self.round_started_at,
                "seconds": round(self.round_seconds, 2),
            },
            "healthy": self.healthy,
            "unhealthy_reason": self.unhealthy_reason,
            "lanes": self.lanes,
            "quotas": self.quotas,
            "totals": dict(self.totals),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetricsWriter:
    """Ghi NGUYEN TO ra `status.json`."""

    def __init__(self, path: Optional[Path] = None):
        self._path = Path(path) if path else status_path()
        self._started_at = _now()
        self._totals: Dict[str, int] = {}
        self._round = 0

    @property
    def path(self) -> Path:
        return self._path

    def begin_round(self) -> float:
        self._round += 1
        return time.monotonic()

    def _accumulate(self, lanes: Dict[str, LaneMetrics]) -> None:
        for lane_metrics in lanes.values():
            for khoa, gia_tri in lane_metrics.as_dict().items():
                if isinstance(gia_tri, int):
                    self._totals[khoa] = self._totals.get(khoa, 0) + gia_tri

    def write(self, *, lanes: Dict[str, LaneMetrics], quotas: Dict[str, Any],
              round_started: float, healthy: bool = True,
              unhealthy_reason: str = "") -> FarmerStatus:
        self._accumulate(lanes)
        status = FarmerStatus(
            started_at=self._started_at,
            updated_at=_now(),
            round_number=self._round,
            round_started_at=_now(),
            round_seconds=time.monotonic() - round_started,
            healthy=healthy,
            unhealthy_reason=unhealthy_reason,
            lanes={ten: m.as_dict() for ten, m in lanes.items()},
            quotas=quotas,
            totals=dict(self._totals),
        )
        self._write_atomic(status.as_dict())
        return status

    def _write_atomic(self, payload: Dict[str, Any]) -> None:
        """Ghi tam cung thu muc roi `os.replace` — `os.replace` la nguyen to
        tren cung mot he tep, nen nguoi doc thay HOAC ban cu HOAC ban moi,
        khong bao gio thay mot tep cut doi."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tam = tempfile.mkstemp(dir=str(self._path.parent),
                                   prefix=".status-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tam, self._path)
        except Exception:
            # Khong de lai tep tam rac tren mot may von dang lo day dia.
            try:
                os.unlink(tam)
            except OSError:
                pass
            raise
