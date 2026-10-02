"""
AI control plane (`/admin/ai`) — provider slots, routing profiles, kill
switches, quotas, usage and audit. See docs/ai/AI_ADMIN_CONTROL_PLANE.md.

CONFIG lives in the store (Appwrite in production, in-memory otherwise);
SECRETS live only in the server environment as `FAS_AI_SECRET_<secret_ref>`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple

log = logging.getLogger("fanfic.ai_assistant")


def build_control_plane(settings: Any, *,
                        active_users_fn: Optional[Callable[[str], Optional[int]]] = None,
                        user_usage_fn: Optional[Callable[[str, str], Tuple[int, int]]] = None):
    """`None` when `FAS_AI_ADMIN_V1` is off. With it on: an Appwrite-backed
    plane on the appwrite data backend, in-memory otherwise. If Appwrite is
    misconfigured the plane still exists but every snapshot is fail-closed
    (AI off) — the admin UI shows why instead of the route silently vanishing."""
    from server.ai_assistant.control.service import ControlPlane
    from server.ai_assistant.control.store import (
        AppwriteControlStore, ControlStoreUnavailable, InMemoryControlStore,
    )

    ai = getattr(settings, "ai_assistant", None)
    if ai is None or not getattr(ai, "admin_v1", False):
        return None
    if str(getattr(settings, "data_backend", "mock")).lower() == "appwrite":
        try:
            store: Any = AppwriteControlStore(settings)
        except ControlStoreUnavailable:
            log.error("ai_control: FAS_AI_ADMIN_V1=1 but Appwrite is not configured — control plane is fail-closed")
            store = _UnavailableStore()
    else:
        store = InMemoryControlStore()
    return ControlPlane(store, active_users_fn=active_users_fn, user_usage_fn=user_usage_fn,
                        alibaba_enabled=bool(getattr(ai, "alibaba_enabled", False)),
                        prefer_free_quota=bool(getattr(ai, "prefer_free_quota", False)))


class _UnavailableStore:
    """Every call fails as 'unavailable' -> the plane serves a fail-closed config."""

    def __getattr__(self, name: str):
        from server.ai_assistant.control.store import ControlStoreUnavailable

        def _fail(*_a: Any, **_k: Any):
            raise ControlStoreUnavailable("Appwrite chưa cấu hình cho control plane AI.")
        return _fail
