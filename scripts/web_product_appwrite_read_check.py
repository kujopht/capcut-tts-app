#!/usr/bin/env python3
"""READ-ONLY check: can the brokered Appwrite key READ DOCUMENTS (not just
schema)? Decides whether a locally-run backend can serve the real production
story for the web product proof.

The stored key is documented as a SCHEMA key (databases/collections/attributes/
indexes scopes). Documents may or may not be included — that is exactly what
this asks, once, without guessing.

Only GET requests. Never prints the key, never writes it anywhere.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    from fanfic_credential_broker import appwrite_admin_env

    env = appwrite_admin_env()
    endpoint = env.get("APPWRITE_ENDPOINT", "").rstrip("/")
    project = env.get("APPWRITE_PROJECT_ID", "")
    database = env.get("APPWRITE_DATABASE_ID", "")
    key = env.pop("APPWRITE_SCHEMA_API_KEY", "")

    out = {
        # Coordinates are non-secret, but the host is enough to confirm we are
        # pointed at the real deployment without echoing anything sensitive.
        "endpoint_host": endpoint.split("/")[2] if "//" in endpoint else endpoint,
        "project_set": bool(project),
        "database_set": bool(database),
        "key_present": bool(key),
        "non_secret_env_names": sorted(k for k in env),
    }

    def probe(path: str) -> dict:
        req = urllib.request.Request(f"{endpoint}{path}", method="GET")
        req.add_header("X-Appwrite-Project", project)
        req.add_header("X-Appwrite-Key", key)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
                return {"status": resp.status, "total": body.get("total"),
                        "keys": sorted(body.keys())[:6]}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")[:200]
            return {"status": exc.code, "body": raw}
        except Exception as exc:
            return {"status": 0, "error": repr(exc)}

    out["collections"] = probe(f"/databases/{database}/collections?queries[]=limit(1)")
    # The collection that holds chapters — name taken from the schema doc, and
    # a wrong guess simply returns 404, which is itself an answer.
    for coll in ("chapters", "novels"):
        out[f"documents_{coll}"] = probe(
            f"/databases/{database}/collections/{coll}/documents?queries[]=limit(1)")

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
