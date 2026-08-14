"""
Ke toan su dung pool MIEN PHI — overnight Phase 3, Phan 3I.

NEN TANG CHI DE QUAN SAT — khong thuc thi han muc gi ca ("Do NOT hardcode
arbitrary production quotas tonight"). Muc tieu la co DU LIEU THAT (so lan
goi/ty le loi/thoi gian phan hoi theo TUNG model) de mot phien sau quyet
dinh han muc cong bang dua tren so lieu that, khong doan.

KHONG BAO GIO ghi credential/secret — chi nhan (provider_id/model_id/
credential_source) va con so (do dai/thoi gian/ket qua).

GIOI HAN DA BIET (ghi ro de khong ai tuong nham day la kho ben vung): CHI
trong bo nho, MAT khi tien trinh restart, khong chia se giua nhieu worker
process. Du cho quan sat dem nay; ke toan CONG BANG THEO NGUOI DUNG THAT su
(yeu cau goc 3I: "the ability later to enforce per-user shared usage") can
mot kho ben vung rieng — CHUA lam trong dot nay.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class UsageEvent:
    occurred_at: str
    provider_id: str
    model_id: str
    #: "shared" (kho Fanfic dung chung) hoac "personal" (BYOK).
    credential_source: str
    #: "translator" | "editor" | "qa".
    pass_type: str
    #: "success" | "rate_limited" | "quota_exhausted" | "error".
    outcome: str
    latency_ms: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "occurred_at": self.occurred_at,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "credential_source": self.credential_source,
            "pass_type": self.pass_type,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
        }


class UsageRecorder:
    """Trong bo nho, cua so TRUOT (ghi de vong khi qua GIOI_HAN) — an toan
    voi tien trinh chay lau, khong phinh bo nho vo han."""

    GIOI_HAN = 5000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._su_kien: List[UsageEvent] = []

    def ghi(self, *, provider_id: str, model_id: str, credential_source: str,
           pass_type: str, outcome: str, latency_ms: int) -> None:
        su_kien = UsageEvent(
            occurred_at=_now_iso(), provider_id=provider_id, model_id=model_id,
            credential_source=credential_source, pass_type=pass_type,
            outcome=outcome, latency_ms=max(0, int(latency_ms)))
        with self._lock:
            self._su_kien.append(su_kien)
            if len(self._su_kien) > self.GIOI_HAN:
                self._su_kien = self._su_kien[-self.GIOI_HAN:]

    def gan_day(self, limit: int = 200) -> List[UsageEvent]:
        with self._lock:
            return list(self._su_kien[-max(0, limit):])

    def tom_tat_theo_model(self) -> Dict[str, Dict[str, object]]:
        """So lan goi + phan bo ket qua theo TUNG provider_id (= mot model
        Groq curated, hoac cloudflare/custom) — CHUA chia theo nguoi dung ca
        nhan (xem gioi han da biet o docstring dau module)."""
        with self._lock:
            su_kien = list(self._su_kien)
        ra: Dict[str, Dict[str, object]] = {}
        for e in su_kien:
            muc = ra.setdefault(e.provider_id, {
                "model_id": e.model_id, "total": 0, "success": 0,
                "rate_limited": 0, "quota_exhausted": 0, "error": 0,
                "avg_latency_ms": 0.0,
            })
            muc["total"] = int(muc["total"]) + 1
            muc[e.outcome] = int(muc.get(e.outcome, 0)) + 1
        # Tinh trung binh o vong THU HAI — can tong so lan goi truoc.
        for provider_id, muc in ra.items():
            cac_su_kien = [e for e in su_kien if e.provider_id == provider_id]
            if cac_su_kien:
                muc["avg_latency_ms"] = round(
                    sum(e.latency_ms for e in cac_su_kien) / len(cac_su_kien), 1)
        return ra


_toan_cuc = UsageRecorder()


def usage_recorder() -> UsageRecorder:
    """MOT recorder DUY NHAT cho toan tien trinh — du cho quan sat dem nay
    (khong phai kho ben vung, khong chia se giua nhieu worker process)."""
    return _toan_cuc
