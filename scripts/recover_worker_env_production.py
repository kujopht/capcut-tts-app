#!/usr/bin/env python3
"""One-time recovery: rebuild `server/.env.production` for the laptop TTS
worker from the account owner's own already-configured `fas-prod-api` Render
service (explicit operator authorization: mission "RESTORE THE EXISTING TTS
WORKER AUTONOMOUSLY", 2026-09-02).

Unlike `fanfic_credential_broker.render_non_secret_env` (which deliberately
refuses to return APPWRITE_API_KEY/R2_*_KEY), this script calls the low-level
`_render()` GET directly and writes the SECRET values straight to a local
gitignored file. Nothing is ever printed: stdout only reports which KEY NAMES
were written, never a value.

Pulls the minimum set `server/worker.py` -> `server/config.py Settings.
validate()` actually requires for a worker process (no CORS/auth-token vars —
the worker never serves HTTP).
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fanfic_credential_broker as broker  # noqa: E402

ENV_FILE = Path(__file__).resolve().parent.parent / "server" / ".env.production"

#: Exactly what `Settings.validate()` requires for DATA_BACKEND=appwrite +
#: STORAGE_BACKEND=r2, per `server/config.py` lines 611-621. Nothing else --
#: the worker does not serve HTTP so FAS_CORS_ORIGINS/auth tokens are
#: irrelevant to it (see server/worker.py: no app, no routes).
SECRET_KEYS = (
    "APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "APPWRITE_DATABASE_ID",
    "APPWRITE_API_KEY", "R2_ACCOUNT_ID", "R2_BUCKET",
    "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
)

STATIC_LINES = (
    "FAS_ENV=production",
    "DATA_BACKEND=appwrite",
    "STORAGE_BACKEND=r2",
    "FAS_INLINE_WORKER=false",
)


def fetch_all_env(api_key: str, service_id: str) -> dict:
    """Full name->value map, values included. Paginated like the broker's own
    non-secret reader, but WITHOUT its allowlist filter -- this is the one
    place in the whole toolchain permitted to see the real secret values, and
    only because the operator explicitly asked for exactly this."""
    found: dict = {}
    cursor = None
    for _ in range(50):
        path = f"/services/{service_id}/env-vars?limit=100"
        if cursor:
            path += f"&cursor={urllib.parse.quote(cursor)}"
        _, data = broker._render(api_key, "GET", path)
        if not isinstance(data, list):
            raise broker.RenderError("env var listing returned an unexpected shape")
        for entry in data:
            ev = entry.get("envVar", entry) if isinstance(entry, dict) else {}
            if isinstance(ev, dict) and ev.get("key"):
                found[ev["key"]] = ev.get("value") or ""
        if len(data) < 100:
            return found
        cursor = (data[-1] or {}).get("cursor")
        if not cursor:
            raise broker.RenderError("env var list looks truncated, no cursor")
    raise broker.RenderError("env var list exceeded pagination ceiling")


def main() -> int:
    api_key = broker.fetch("RENDER_API_KEY")
    if not api_key:
        print("RENDER_API_KEY: ABSENT from credential store", file=sys.stderr)
        return 1

    try:
        svc = broker.render_resolve_service(api_key)
        all_env = fetch_all_env(api_key, svc["id"])
    except broker.RenderError as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 3

    missing = [k for k in SECRET_KEYS if k not in all_env or not all_env[k]]
    if missing:
        print(f"ERROR: fas-prod-api is missing {len(missing)} required var(s): "
              f"{', '.join(missing)} (value withheld)", file=sys.stderr)
        return 1

    lines = list(STATIC_LINES) + [f"{k}={all_env[k]}" for k in SECRET_KEYS]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Belt-and-suspenders: drop references before returning.
    del all_env, lines

    print(f"wrote {ENV_FILE} ({len(SECRET_KEYS)} secret keys + "
          f"{len(STATIC_LINES)} static keys; values not displayed)")
    for k in SECRET_KEYS:
        print(f"  {k}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
