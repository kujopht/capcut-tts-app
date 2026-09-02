#!/usr/bin/env python3
"""Fix a real gap left by scripts/recover_worker_env_production.py: that
script pulled only the 8 secret Appwrite/R2 keys and skipped
FAS_LOCAL_VOICES, so the worker's voice allowlist silently fell back to the
Settings dataclass default (`piper:ngochuyen` only) instead of the real
production list -- causing claimed jobs to fail with voice_not_found even
though the model files are genuinely installed and valid.

FAS_LOCAL_VOICES is a non-secret feature flag (already read this session via
fanfic_credential_broker's low-level _render call), so this is safe to fetch
and append directly -- no secret handling concerns here.
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fanfic_credential_broker as broker  # noqa: E402

ENV_FILE = Path(__file__).resolve().parent.parent / "server" / ".env.production"
KEY = "FAS_LOCAL_VOICES"


def fetch_env_value(api_key: str, service_id: str, key: str) -> str | None:
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
            if isinstance(ev, dict) and ev.get("key") == key:
                return ev.get("value") or ""
        if len(data) < 100:
            return None
        cursor = (data[-1] or {}).get("cursor")
        if not cursor:
            raise broker.RenderError("env var list looks truncated, no cursor")
    raise broker.RenderError("env var list exceeded pagination ceiling")


def main() -> int:
    api_key = broker.fetch("RENDER_API_KEY")
    if not api_key:
        print("RENDER_API_KEY: ABSENT", file=sys.stderr)
        return 1
    svc = broker.render_resolve_service(api_key)
    value = fetch_env_value(api_key, svc["id"], KEY)
    if value is None:
        print(f"{KEY}: not set on fas-prod-api", file=sys.stderr)
        return 1

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.startswith(f"{KEY}=")]
    lines.append(f"{KEY}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{KEY}: written ({len(value)} chars, value not displayed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
