"""
Capability tiers + free-quota metadata for provider slots — PURE functions (no I/O, no clock of their own).

* A TIER (`FAST`, `SMART`, `ADVANCED`, `TRANSLATION`, `VISION`, `EMBEDDING`) says what class of work a slot's model can do.
  Subscription plans / product features map to TIERS later — never to concrete model names — and which slot serves which
  tier is owner configuration (`ProviderSlot.tiers`). Nothing in the chat routes asks for a tier yet: a request with no tier
  behaves exactly as before.
* FREE QUOTA metadata (`free_quota_remaining`, `free_quota_expires_at`, `free_quota_only`) is entered by the owner from the
  provider's console — a SNAPSHOT, not live data (`free_quota_updated_at` says how old it is). `free_quota_only` is a safety
  lock: such a slot is skipped when its free quota is expired, exhausted or smaller than the request estimate, so it can never
  spend paid quota. Preferring soon-to-expire free quota (`order_by_expiring_free_quota`) is implemented and tested but
  DORMANT: the control plane applies it only when `FAS_AI_PREFER_FREE_QUOTA` is on (default off, not set in production).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from server.ai_assistant.control.model import CAPABILITY_TIERS, CHAT_TIERS, ControlConfig, ProviderSlot, normalize_timestamp

#: "expiring" is shown in /admin/ai (and sorts first when the preference is on) once the free quota ends within this many days.
EXPIRING_SOON_DAYS = 7.0


def serves_tier(slot: ProviderSlot, tier: Optional[str]) -> bool:
    """Whether `slot` may serve a CHAT request for `tier` (None = any chat request).

    No tier requested: every slot qualifies except one that declares tiers and none of them is a chat tier (an
    embedding-only model must never receive a `/chat/completions` call). A tier requested: only slots that declare it."""
    if tier is None:
        return not slot.tiers or bool(set(slot.tiers) & set(CHAT_TIERS))
    return tier in slot.tiers


def tier_map(cfg: ControlConfig) -> Dict[str, List[str]]:
    """tier -> slot ids that declare it (for the admin capability map). Slots with no tier are not listed."""
    out: Dict[str, List[str]] = {t: [] for t in CAPABILITY_TIERS}
    for sid in sorted(cfg.slots):
        for t in cfg.slots[sid].tiers:
            if t in out:
                out[t].append(sid)
    return out


def _parse(ts: str) -> Optional[datetime]:
    norm = normalize_timestamp(ts) if ts else None
    return datetime.fromisoformat(norm) if norm else None


def free_quota_state(slot: ProviderSlot, now: datetime) -> Dict[str, Any]:
    """Derived, JSON-safe view of the slot's free-quota metadata at `now` (timezone-aware).

    state: "none" (no metadata) | "active" | "expiring" (<= EXPIRING_SOON_DAYS left) | "expired" | "exhausted"."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    expires = _parse(slot.free_quota_expires_at)
    remaining = slot.free_quota_remaining
    days_left = round((expires - now).total_seconds() / 86400.0, 1) if expires else None
    if remaining is None and expires is None:
        state = "none"
    elif expires is not None and expires <= now:
        state = "expired"
    elif remaining is not None and remaining <= 0:
        state = "exhausted"
    elif days_left is not None and days_left <= EXPIRING_SOON_DAYS:
        state = "expiring"
    else:
        state = "active"
    return {"state": state, "remaining": remaining, "expires_at": slot.free_quota_expires_at or None,
            "days_left": days_left, "only": slot.free_quota_only, "updated_at": slot.free_quota_updated_at or None}


def free_quota_block_reason(slot: ProviderSlot, now: datetime, est_tokens: int) -> Optional[str]:
    """For `free_quota_only` slots: why the slot must NOT be used now ("expired" | "exhausted"), else None.
    Other slots are never blocked by their free-quota metadata (it is informational for them)."""
    if not slot.free_quota_only:
        return None
    st = free_quota_state(slot, now)
    if st["state"] == "expired":
        return "expired"
    remaining = slot.free_quota_remaining
    if st["state"] == "exhausted" or remaining is None or remaining < max(0, est_tokens):
        return "exhausted"
    return None


def order_by_expiring_free_quota(slots: Sequence[ProviderSlot], now: datetime) -> List[ProviderSlot]:
    """Inside each PRIORITY tier (the owner's priorities still dominate), put slots with usable free quota first, the one that
    expires SOONEST first; slots without it keep their incoming (balanced) order. Stable, no randomness."""
    out: List[ProviderSlot] = []
    by_prio: Dict[int, List[ProviderSlot]] = {}
    for s in slots:
        by_prio.setdefault(s.priority, []).append(s)
    far = datetime.max.replace(tzinfo=timezone.utc)
    for prio in sorted(by_prio):
        group = by_prio[prio]

        def key(s: ProviderSlot) -> Any:
            st = free_quota_state(s, now)
            if st["state"] in ("active", "expiring") and (s.free_quota_remaining or 0) > 0:
                return (0, _parse(s.free_quota_expires_at) or far)
            return (1, far)

        out.extend(sorted(group, key=key))  # sorted() is stable: equal keys keep their order
    return out
