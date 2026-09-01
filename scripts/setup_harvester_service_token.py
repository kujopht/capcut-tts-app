#!/usr/bin/env python3
"""Generate, store, and deploy `FAS_HARVESTER_SERVICE_TOKEN` end to end.

Mission "PIVOT AUTH — CREATE FIRST-CLASS HARVESTER SERVICE CREDENTIAL"
(2026-09-01): a dedicated, narrowly-scoped machine credential for the
harvester/content-shipping pipeline, replacing the abandoned attempt to
harvest a real interactive user's OAuth session. See
`server/config.py::AppwriteSettings.is_harvester_service_token` and
`server/main.py::harvester_or_user_profile` for the server-side half —
this script only handles generation, local storage, and production
rollout.

Steps (idempotent — safe to re-run):
  1. Reuse the token already in the credential broker if present, else
     generate a fresh cryptographically strong random one.
  2. Store it locally via the broker (Windows Credential Manager).
  3. Push the SAME value to the real Render production service's env
     (`RENDER_API_KEY`, single-key PUT — leaves every other env var
     untouched).
  4. Wait for the resulting auto-redeploy to go live (poll /api/health).
  5. Verify with the smallest safe authenticated check: GET
     /api/novels?mine=true&limit=1 with the new token.

The token value is never printed, logged, or returned from any function
in a form a caller could accidentally print — only lengths/booleans/HTTP
codes ever reach stdout.
"""
from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fanfic_credential_broker as broker  # noqa: E402

DEFAULT_API = "https://fas-prod-api.onrender.com"
ENV_KEY = "FAS_HARVESTER_SERVICE_TOKEN"
DEPLOY_MAX_WAIT_SECONDS = 300


def main() -> int:
    render_key = broker.fetch("RENDER_API_KEY")
    if not render_key:
        print("BLOCKED: RENDER_API_KEY chưa có trong credential broker.",
              file=sys.stderr)
        return 2

    print("=== 1. Token (tái dùng nếu đã có, tạo mới nếu chưa) ===")
    existing = broker.fetch(ENV_KEY)
    if existing:
        token = existing
        n = len(token)
        print(f"  đã có sẵn trong broker ({n} ký tự) — tái dùng, không xoay vòng.")
    else:
        token = secrets.token_urlsafe(48)
        n = len(token)
        broker.store(ENV_KEY, token)
        print(f"  đã tạo mới và lưu vào Windows Credential Manager ({n} ký tự).")
    del existing

    print("\n=== 2. Xác định service Render ===")
    render_identity = broker.render_identity(render_key)
    print(f"  owner xác thực OK")
    service = broker.render_resolve_service(render_key)
    service_id = service.get("id", "")
    if not service_id:
        print("BLOCKED: không tìm thấy service_id.", file=sys.stderr)
        return 1
    print(f"  service={service.get('name', '?')} id={service_id}")

    before_deploy = broker.render_latest_deploy(render_key, service_id)
    before_id = before_deploy.get("id", "")

    print(f"\n=== 3. Đặt {ENV_KEY} trên Render production (chỉ đúng một khoá) ===")
    broker.render_upsert_env(render_key, service_id, ENV_KEY, token)
    print(f"  đã PUT {ENV_KEY} ({n} ký tự, không hiển thị giá trị).")
    del token

    print("\n=== 4. Chờ auto-redeploy lên thật (poll /api/health) ===")
    deadline = time.monotonic() + DEPLOY_MAX_WAIT_SECONDS
    deployed = False
    while time.monotonic() < deadline:
        deploy = broker.render_latest_deploy(render_key, service_id)
        deploy_id = deploy.get("id", "")
        deploy_status = deploy.get("status", "")
        if deploy_id and deploy_id != before_id and deploy_status == "live":
            deployed = True
            break
        if deploy_id == before_id:
            print(f"  chưa thấy deploy mới (status hiện tại: {deploy_status or '?'})...")
        else:
            print(f"  deploy mới {deploy_id[:12]}... status={deploy_status}")
            if deploy_status in ("build_failed", "update_failed", "canceled"):
                print(f"BLOCKED: deploy {deploy_status}.", file=sys.stderr)
                return 1
        time.sleep(10)
    if not deployed:
        print("BLOCKED: hết thời gian chờ deploy lên 'live'.", file=sys.stderr)
        return 1
    print("  deploy mới đã LIVE.")

    print("\n=== 5. Xác minh bằng gọi thật, nhẹ nhất có thể ===")
    verify_token = broker.fetch(ENV_KEY)
    r = httpx.get(f"{DEFAULT_API}/api/novels", params={"mine": "true", "limit": "1"},
                  headers={"Authorization": f"Bearer {verify_token}"}, timeout=30)
    del verify_token
    ok = r.status_code == 200
    print(f"  GET /api/novels?mine=true&limit=1 (harvester) -> HTTP {r.status_code}: "
          f"{'OK' if ok else 'THẤT BẠI'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
