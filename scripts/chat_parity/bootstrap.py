"""
Dung project cho may kiem Appwrite 1.9.6 DUNG MOT LAN (chi loopback), roi tao schema Fanfic tren do.

    python -m scripts.chat_parity.bootstrap --endpoint http://127.0.0.1:8080/v1 --ra parity.json

Thu tu: (1) tai khoan console GOC (mat khau ngau nhien, email `@example.test`, giu o `<ra>.console` quyen
600 tren CHINH may kiem de chay lai duoc), (2) to chuc + project `parity-chat` (co roi thi dung lai), (3) khoa API cua project, (4) ghi `parity.json` (quyen 600 —
TOA DO + KHOA, khong bao gio commit/in), (5) `scripts.setup_appwrite` voi moi truong TOI THIEU cua rao.

Rao `guard.kiem_dich` chay TRUOC buoc (1): endpoint khong phai loopback thi khong goi mot request nao.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

from scripts.chat_parity import guard

GOC = Path(__file__).resolve().parents[2]
PROJECT_ID = "parity-chat"
DATABASE_ID = "parity_chat"

#: Scope cua khoa: ho Databases cu (setup + kho Legacy) VA ho TablesDB (giao dich `tablesdb/transactions`
#: dung scope `rows.*`). Danh sach hop le cua 1.9.6: `app/config/scopes/project.php` trong image — KHONG
#: co scope `transactions.*` rieng. Ban cu hon khong biet ho TablesDB thi lui ve ho cu.
SCOPE_DAY_DU = [
    "users.read", "users.write", "sessions.read", "sessions.write", "teams.read", "teams.write",
    "databases.read", "databases.write", "collections.read", "collections.write", "attributes.read",
    "attributes.write", "indexes.read", "indexes.write", "documents.read", "documents.write",
    "tables.read", "tables.write", "columns.read", "columns.write", "rows.read", "rows.write",
    "files.read", "files.write", "buckets.read", "buckets.write", "health.read",
]


def _loi(r: httpx.Response, buoc: str) -> SystemExit:
    try:
        b = r.json() or {}
        kieu, tb = str(b.get("type") or ""), str(b.get("message") or "")[:200]
    except ValueError:
        kieu, tb = "", ""
    return SystemExit(f"{buoc}: {r.status_code} {kieu} {tb}")


def dung(endpoint: str, ra: Path) -> Dict[str, str]:
    guard.kiem_dich(guard.CauHinhParity(endpoint=endpoint, project_id=PROJECT_ID, database_id=DATABASE_ID,
                                        api_key="chua-co"))
    hd = {"X-Appwrite-Project": "console", "Content-Type": "application/json"}
    # Tai khoan console GOC chi tao DUOC MOT LAN (`_APP_CONSOLE_WHITELIST_ROOT`): giu no canh `--ra` (600)
    # de chay lai (vd lan truoc hong o buoc tao khoa) dang nhap lai thay vi ket.
    tep_goc = ra.with_name(ra.name + ".console")
    moi = not tep_goc.exists()
    if moi:
        goc = {"email": f"root-{secrets.token_hex(4)}@example.test", "password": "Pa-" + secrets.token_urlsafe(24)}
        tep_goc.write_text(json.dumps(goc), encoding="utf-8")
        os.chmod(tep_goc, 0o600)
    else:
        goc = json.loads(tep_goc.read_text(encoding="utf-8"))
    email, mk = goc["email"], goc["password"]
    with httpx.Client(base_url=endpoint.rstrip("/"), headers=hd, timeout=60) as c:
        if moi:
            r = c.post("/account", json={"userId": "unique()", "email": email, "password": mk, "name": "parity root"})
            if r.status_code not in (200, 201):
                raise _loi(r, "tạo tài khoản console")
        r = c.post("/account/sessions/email", json={"email": email, "password": mk})
        if r.status_code not in (200, 201):
            raise _loi(r, "đăng nhập console")
        # Cookie cua IP loopback co the khong duoc jar giu — Appwrite tra kem X-Fallback-Cookies.
        du_phong = r.headers.get("X-Fallback-Cookies")
        if du_phong:
            c.headers["X-Fallback-Cookies"] = du_phong
        if c.get(f"/projects/{PROJECT_ID}").status_code != 200:
            ds = c.get("/teams").json().get("teams") or []
            if ds:
                team = ds[0]["$id"]
            else:
                r = c.post("/teams", json={"teamId": "unique()", "name": "parity"})
                if r.status_code not in (200, 201):
                    raise _loi(r, "tạo tổ chức")
                team = r.json()["$id"]
            r = c.post("/projects", json={"projectId": PROJECT_ID, "name": PROJECT_ID, "teamId": team,
                                          "region": "default"})
            if r.status_code not in (200, 201):
                raise _loi(r, "tạo project")
        khoa = None
        for scopes in (SCOPE_DAY_DU, [s for s in SCOPE_DAY_DU if not s.startswith(("tables.", "columns.", "rows."))]):
            # 1.9.6 bat buoc `keyId` (ban cu tu sinh).
            r = c.post(f"/projects/{PROJECT_ID}/keys", json={"keyId": "unique()", "name": "parity", "scopes": scopes})
            if r.status_code in (200, 201):
                khoa = r.json()["secret"]
                print(f"khoá API: {len(scopes)} scope", flush=True)
                break
        if not khoa:
            raise _loi(r, "tạo khoá API")
    d = {"endpoint": endpoint.rstrip("/"), "project_id": PROJECT_ID, "database_id": DATABASE_ID, "api_key": khoa}
    ra.write_text(json.dumps(d), encoding="utf-8")
    os.chmod(ra, 0o600)
    return d


def schema(d: Dict[str, str], chi: List[str]) -> int:
    cfg = guard.CauHinhParity(**d)
    guard.xac_minh_song(cfg)
    env = guard.moi_truong_con(cfg)
    lenh = [sys.executable, "-m", "scripts.setup_appwrite"] + [x for c in chi for x in ("--only", c)]
    p = subprocess.run(lenh, cwd=GOC, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = cfg.an(p.stdout + p.stderr)
    print("\n".join(out.splitlines()[-25:]))
    return p.returncode


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--ra", required=True)
    ap.add_argument("--chi-schema", action="store_true", help="bo qua (1)-(4), chi tao schema tu --ra co san")
    a = ap.parse_args(argv)
    ra = Path(a.ra)
    try:
        d = json.loads(ra.read_text(encoding="utf-8")) if a.chi_schema else dung(a.endpoint, ra)
        print(f"project {d['project_id']} · db {d['database_id']} · {d['endpoint']}", flush=True)
        return schema(d, [])
    except guard.DichBiTuChoi as exc:
        print(f"TỪ CHỐI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
