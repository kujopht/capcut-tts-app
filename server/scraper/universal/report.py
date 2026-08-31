"""
Observability report — Universal Acquisition Engine Hardening (2026-08-31).

Ties T0-T5 (`router.py`), extraction validation (`extraction_validation.py`)
together into ONE per-URL report: which tiers were tried, in what order,
how long each took, what the router finally selected, and — the mission's
explicit escalation-policy requirement — a human-readable narrative of WHY
a tier was escalated to, so "T0 returned 403" is never silently treated as
"this URL is blocked" without recording what was tried next and why.

ESCALATION RULE (documented here, enforced structurally by `router.py` +
`browser_plugin.py`, not re-implemented in this module):
  - A T0 failure alone is NEVER a final classification. The router's
    existing `_order_from()` escalation continues to T1/T2/... regardless
    of WHY T0 failed (403, connection error, encrypted-but-200 body, ...).
  - If a later tier (most commonly T2) SUCCEEDS after T0 failed, the
    final `AcquisitionResult.status` is OK — this is the real proof that
    the URL was reachable via a permitted mechanism, not a guess.
  - If a later tier explicitly reports a challenge (see
    `browser_plugin.BrowserRenderResult.challenge_detected` /
    `AcquisitionStatus.BLOCKED`), the final status is BLOCKED, not a
    generic FAILED — a caller can distinguish "genuinely no permitted
    path found" from "every tier had an ordinary, non-challenge error".
  - `build_report()` below renders this sequence into `fallback_reason`
    so the decision is visible in one field, not spread across log lines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from server.scraper.universal.acquisition import AcquisitionResult, AcquisitionStatus, SourceClass
from server.scraper.universal.extraction_validation import ValidationResult, validate_extracted_content
from server.scraper.universal.router import AcquisitionRouter, AcquisitionTier, TierAttempt

#: Human-readable Vietnamese label per tier — used only for the
#: `fallback_reason` narrative string, never for logic/comparison.
_TIER_LABEL = {
    AcquisitionTier.T0_DIRECT: "T0 (HTTP truc tiep)",
    AcquisitionTier.T1_STRUCTURED: "T1 (du lieu co cau truc)",
    AcquisitionTier.T2_BROWSER_RENDERED: "T2 (render trinh duyet)",
    AcquisitionTier.T3_PUBLIC_NETWORK: "T3 (quan sat mang cong khai)",
    AcquisitionTier.T4_DOCUMENT: "T4 (tai lieu/PDF)",
    AcquisitionTier.T5_MANAGED_PROVIDER: "T5 (provider quan ly ben ngoai)",
}


@dataclass(frozen=True)
class AcquisitionReport:
    url: str
    #: One entry per tier actually TRIED (see `TierAttempt` docstring —
    #: skipped tiers, e.g. no plugin registered, are absent, not recorded
    #: as failures).
    tier_attempts: List[TierAttempt]
    tier_selected: Optional[AcquisitionTier]
    total_latency_seconds: float
    #: Empty string if acquisition produced no text to hash (e.g. every
    #: tier failed) — never a placeholder/fabricated hash.
    content_hash: str
    #: None when acquisition failed entirely (nothing to validate).
    validation_score: Optional[float]
    #: Human-readable Vietnamese narrative of the escalation sequence and
    #: why the final status was reached — see module docstring.
    fallback_reason: str
    final_status: AcquisitionStatus


def _narrate(url: str, attempts: List[TierAttempt], final: AcquisitionResult) -> str:
    if not attempts:
        return f"Khong tang nao duoc thu cho {url}."

    parts: List[str] = []
    for i, a in enumerate(attempts):
        label = _TIER_LABEL.get(a.tier, str(a.tier))
        if a.success:
            parts.append(f"{label} thanh cong")
        else:
            reason = a.error_message or a.status.value
            parts.append(f"{label} that bai ({reason})")

    narrative = " -> ".join(parts)

    if final.status == AcquisitionStatus.OK or final.status == AcquisitionStatus.NOT_MODIFIED:
        if len(attempts) > 1:
            winning = _TIER_LABEL.get(attempts[-1].tier, str(attempts[-1].tier))
            narrative += (
                f". Tang dau (T0) that bai KHONG bi coi la 'nguon bi chan' - "
                f"da leo thang len {winning} va thanh cong, chung minh nguon "
                f"nay tiep can duoc qua mot co che duoc phep."
            )
    elif final.status == AcquisitionStatus.BLOCKED:
        narrative += (
            ". Mot tang phat hien CAPTCHA/bot-challenge/tu choi truy cap ro rang - "
            "phan loai BLOCKED (khac voi FAILED thong thuong), KHONG tiep tuc leo thang."
        )
    else:
        narrative += ". Tat ca tang da thu deu that bai (loi thong thuong, khong phai challenge)."

    return narrative


def build_report(
    router: AcquisitionRouter, url: str, *,
    source_hint: SourceClass = SourceClass.UNKNOWN,
    expected_title: Optional[str] = None,
) -> AcquisitionReport:
    """Run one real acquisition through *router* and build the full
    observability report — the single entry point Task #60 exists to
    provide. Never raises: acquisition failure is a normal, reportable
    outcome (see `fallback_reason`), not an exception."""
    result, attempts = router.acquire_with_attempts(url, source_hint=source_hint)
    total_latency = sum(a.latency_seconds for a in attempts)

    text = result.text_markdown or result.html or ""
    content_hash = ""
    validation_score: Optional[float] = None
    if result.ok and text:
        validation: ValidationResult = validate_extracted_content(
            text, expected_title=expected_title)
        content_hash = validation.content_hash
        validation_score = validation.score

    tier_selected = attempts[-1].tier if (attempts and result.ok) else None

    return AcquisitionReport(
        url=url,
        tier_attempts=attempts,
        tier_selected=tier_selected,
        total_latency_seconds=total_latency,
        content_hash=content_hash,
        validation_score=validation_score,
        fallback_reason=_narrate(url, attempts, result),
        final_status=result.status,
    )
