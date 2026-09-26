"""
He thong Rate Limiting da tang (Tiered Rate Limiter) cho FastAPI.

Phan loai endpoint:
- Tier A — sensitive / expensive (auth mutations, tts/translation jobs, imports, signed URLs, admin mutations): 60/min.
- Tier B — normal mutations (posts, comments, follows, progress, likes): 120/min.
- Tier C — public reads (catalog, detail, chapters, tags, profile): 600/min.
- Tier PROFILE — luu ho so / anh dai dien (`PUT /api/me/profile`, `PUT /api/creator/avatar`):
  30/GIO (Social & Play V1). Moi lan co the kem anh toi 5-8 MB ma may chu phai GIAI MA
  that (Pillow) — 120 lan/phut cua Tier B la mot cua de dot CPU, con mot nguoi that sua
  ho so vai lan moi gio. Middleware khong doc body nen dem MOI lan luu, co anh hay khong.
- EXCLUDED — healthcheck (/api/health, /api/ready), CORS preflight (OPTIONS), noi bo canary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

TIER_A = "tier_a"
TIER_B = "tier_b"
TIER_C = "tier_c"
TIER_PROFILE = "tier_profile"
EXCLUDED = "excluded"

#: Cua so dem (giay) theo tier — mac dinh 60s; luu ho so tinh theo GIO.
TIER_WINDOW_SECONDS: Dict[str, float] = {TIER_PROFILE: 3600.0}


class SlidingWindowRateLimiter:
    """Bo gioi han toc do theo cua so truot trong bo nho."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._last_prune = time.monotonic()
        #: Cua so LON NHAT tung gap — don dep theo no, khong theo cua so cua request
        #: dang goi: mot request 60s kich hoat don dep khong duoc xoa lich su cua
        #: mot khoa tinh theo GIO (Tier PROFILE) chi vi no im 2 phut.
        self._max_window = 60.0

    def check(self, key: str, limit: int, window: float = 60.0) -> Tuple[bool, int, int]:
        """
        Kiem tra va ghi nhan request.

        Tra ve:
          - allowed: bool (cho phep hay khong)
          - remaining: int (so request con lai trong cua so)
          - retry_after: int (so giay phai cho neu bi chan)
        """
        now = time.monotonic()
        with self._lock:
            self._max_window = max(self._max_window, window)
            # Dinh ky don cac key da het han de tiet kiem bo nho
            if now - self._last_prune > 60.0:
                self._prune_expired(now, self._max_window * 2)
                self._last_prune = now

            timestamps = self._history[key]
            # Cat bo cac moc thoi gian nam ngoai cua so
            cutoff = now - window
            idx = 0
            while idx < len(timestamps) and timestamps[idx] < cutoff:
                idx += 1
            if idx > 0:
                timestamps = timestamps[idx:]
                self._history[key] = timestamps

            count = len(timestamps)
            if count >= limit:
                # Tinh thoi gian cho toi khi slot cu nhat het han
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window - now))
                return False, 0, retry_after

            timestamps.append(now)
            remaining = max(0, limit - len(timestamps))
            return True, remaining, 0

    def _prune_expired(self, now: float, max_age: float) -> None:
        cutoff = now - max_age
        expired_keys = [
            k for k, ts in self._history.items()
            if not ts or ts[-1] < cutoff
        ]
        for k in expired_keys:
            del self._history[k]

    def reset(self) -> None:
        """Xoa toan bo lich su (dung cho test)."""
        with self._lock:
            self._history.clear()


limiter = SlidingWindowRateLimiter()


def resolve_rate_limit_key(request: Request) -> str:
    """
    Xac dinh danh tinh de tinh han muc:
    1. Uu tien token xac thuc (Bearer): bam SHA256 an toan de tranh lo secret.
    2. Fallback IP: Cloudflare Connecting IP neu co, hoac client host.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            h = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
            return f"usr:{h}"

    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return f"ip:{cf_ip}"

    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def classify_request(request: Request) -> Tuple[str, int]:
    """
    Phan loai request vao Tier va han muc (requests / 60s).
    """
    path = request.url.path.rstrip("/")
    method = request.method.upper()

    # Preflight va healthcheck duoc mien tru
    if method == "OPTIONS":
        return EXCLUDED, 0
    if path in ("/api/health", "/api/ready"):
        return EXCLUDED, 0

    # Internal token / canary check
    canary = request.headers.get("x-canary-token")
    if canary and canary == os.environ.get("FAS_CANARY_TOKEN"):
        return EXCLUDED, 0

    limit_a = int(os.environ.get("FAS_RATE_LIMIT_TIER_A", "60"))
    limit_b = int(os.environ.get("FAS_RATE_LIMIT_TIER_B", "120"))
    limit_c = int(os.environ.get("FAS_RATE_LIMIT_TIER_C", "600"))

    # TIER PROFILE: luu ho so/anh dai dien — giai ma anh that, dem theo GIO.
    if method == "PUT" and path in ("/api/me/profile", "/api/creator/avatar"):
        return TIER_PROFILE, int(os.environ.get("FAS_RATE_LIMIT_PROFILE_PER_HOUR", "30"))

    # TIER A: Sensitive & Expensive Operations
    if path in ("/api/auth/register", "/api/auth/login") or path.startswith("/api/auth/oauth"):
        return TIER_A, limit_a
    if path.startswith("/api/jobs") and method in ("POST", "PUT", "DELETE"):
        return TIER_A, limit_a
    if path.startswith("/api/translation") and method in ("POST", "PUT", "DELETE"):
        return TIER_A, limit_a
    if "/import" in path or "/upload" in path:
        return TIER_A, limit_a
    if path.endswith("/cover") and method in ("PUT", "DELETE", "POST"):
        return TIER_A, limit_a
    if re.match(r"^/api/audio/[^/]+/url$", path) and method == "GET":
        return TIER_A, limit_a
    if path.startswith("/api/admin/") and method in ("POST", "PUT", "DELETE", "PATCH"):
        return TIER_A, limit_a
    if method == "DELETE":
        return TIER_A, limit_a

    # TIER B: Normal Mutations
    if method in ("POST", "PUT", "PATCH"):
        return TIER_B, limit_b

    # TIER C: Public Reads
    return TIER_C, limit_c


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Starlette ASGI Middleware ap dung tiered rate limiting cho API.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Neu bien moi truong tat thi bo qua
        if os.environ.get("FAS_RATE_LIMIT_ENABLED", "true").lower() in ("0", "false", "no"):
            return await call_next(request)

        tier, limit = classify_request(request)
        if tier == EXCLUDED:
            return await call_next(request)

        key = f"{tier}:{resolve_rate_limit_key(request)}"
        allowed, remaining, retry_after = limiter.check(
            key, limit, window=TIER_WINDOW_SECONDS.get(tier, 60.0))

        if not allowed:
            payload = {
                "detail": "Quá nhiều yêu cầu. Vui lòng thử lại sau.",
                "error": "rate_limit_exceeded",
                "tier": tier,
                "retry_after": retry_after,
            }
            return Response(
                content=json.dumps(payload, ensure_ascii=False),
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
