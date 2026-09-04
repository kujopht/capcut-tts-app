#!/usr/bin/env python3
"""Do trang thai hang doi PRODUCTION — CHI DOC, khong ghi mot byte nao.

Dung o ba cho cua cuoc cutover:
  * PHASE 0  — co job nao dang o trang thai khong an toan de ban giao khong
  * PHASE 4  — DRAIN: cho den khi khong con job `running`
  * PHASE 6  — OBSERVE: dem job hoan tat that trong cua so quan sat

CREDENTIAL
----------
Lay tu dich vu Render `fas-prod-api` qua `fanfic_credential_broker` — cung
mot bo gia tri ma production API dang dung, nen khong co chuyen "worker
tro vao mot noi khac API". KHONG ghi ra dia, KHONG in ra man hinh, KHONG
di qua tham so dong lenh. Chung chi song trong `os.environ` cua chinh tien
trinh nay.

Truoc khi doc bat cu thu gi, `cutover_target.khang_dinh_production()` phai
qua. Doc nham du an staging roi bao cao "hang doi production rong" la mot
PASS GIA — dung cai bay ma vong staging da mac mot lan voi
`STORAGE_BACKEND`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))
sys.path.insert(0, str(GOC / "scripts"))

from scripts.ops.cutover_target import (  # noqa: E402
    REQUIRED_ENV_NAMES,
    CutoverRefused,
    khang_dinh_production,
    tom_tat_env,
)


def nap_env_production() -> Dict[str, str]:
    """Keo bo bien production tu Render vao `os.environ`. Khong in gia tri."""
    import fanfic_credential_broker as broker
    import recover_worker_env_production as rec

    api_key = broker.fetch("RENDER_API_KEY")
    if not api_key:
        raise CutoverRefused(
            "RENDER_API_KEY khong co trong Windows Credential Manager — "
            "chay: python scripts/fanfic_credential_broker.py store "
            "--name RENDER_API_KEY")
    svc = broker.render_resolve_service(api_key)
    sid = svc.get("id") or (svc.get("service") or {}).get("id")
    if not sid:
        raise CutoverRefused("khong phan giai duoc service id cua fas-prod-api")

    tat_ca = rec.fetch_all_env(api_key, sid)
    env = {k: tat_ca.get(k, "") for k in REQUIRED_ENV_NAMES}
    # Bon gia tri co dinh: Render giu chung, nhung khang dinh lai o day de
    # mot lan sua tay ben Render khong am tham doi hanh vi worker.
    khang_dinh_production(env)
    for k, v in env.items():
        os.environ[k] = v
    # Worker khong phuc vu HTTP; ep tuong minh de khong bao gio chay inline.
    os.environ["FAS_INLINE_WORKER"] = "false"
    return env


def _store():
    """Tao kho metadata tu chinh duong ma worker dung — khong sao chep logic."""
    from server.config import load_settings
    from server.adapters import build_metadata_store

    st = load_settings()
    st.validate()
    if st.environment.lower() != "production":
        raise CutoverRefused(f"settings.environment = {st.environment!r}, phai la production")
    return build_metadata_store(st), st


def _tuoi_giay(moc: Optional[str]) -> Optional[float]:
    if not moc:
        return None
    try:
        t = datetime.fromisoformat(moc.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds()


def _job_an_toan(j) -> Dict[str, Any]:
    """Chi truong dieu hanh. KHONG lay noi dung chuong, khong lay gi cua nguoi dung."""
    return {
        "job_id": j.job_id,
        "status": getattr(j.status, "value", str(j.status)),
        "voice_id": j.voice_id,
        "attempts": j.attempts,
        "tien_do": f"{j.done_parts}/{j.total_parts}",
        "lease_owner": j.lease_owner,
        "lease_con_giay": (
            None if not j.lease_expires_at
            else round(-(_tuoi_giay(j.lease_expires_at) or 0), 1)
        ),
        "lease_het_han": (
            None if not j.lease_expires_at
            else (_tuoi_giay(j.lease_expires_at) or 0) > 0
        ),
        "created_at": j.created_at,
        "finished_at": j.finished_at,
        "co_output": bool(j.output_key),
    }


def do_hang_doi() -> Dict[str, Any]:
    from server.domain import JobStatus

    store, st = _store()
    ra: Dict[str, Any] = {
        "luc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "appwrite_project": st.appwrite.project_id,
        "appwrite_database": st.appwrite.database_id,
        "r2_bucket": st.r2.bucket,
        "so_luong": {},
        "dang_chay": [],
        "lease_treo": [],
        "cho_xu_ly": [],
    }
    for tt in (JobStatus.PENDING, JobStatus.RUNNING):
        ds = store.list_jobs_by_status(tt)
        ra["so_luong"][tt.value] = len(ds)
        for j in ds:
            g = _job_an_toan(j)
            if tt is JobStatus.RUNNING:
                ra["dang_chay"].append(g)
                # Lease het han + van `running` = worker giu no da chet.
                if g["lease_het_han"] or g["lease_con_giay"] is None:
                    ra["lease_treo"].append(g)
            else:
                ra["cho_xu_ly"].append(g)
    ra["an_toan_de_ban_giao"] = (
        ra["so_luong"].get("running", 0) == 0 and not ra["lease_treo"])
    return ra


def cho_hang_doi_rong(han_giay: int, nhip_giay: int = 15) -> Dict[str, Any]:
    """DRAIN: cho den khi khong con job `running`. Khong giet gi bao gio.

    Tra ve ban do cuoi cung kem `dat=True/False`. Het han ma van con job
    dang chay thi tra `dat=False` — ben goi quyet dinh, ham nay khong bao
    gio tu y ep dung mot job dang tong hop.
    """
    het = time.time() + han_giay
    lan = 0
    ban_do = do_hang_doi()
    while time.time() < het:
        lan += 1
        if ban_do["so_luong"].get("running", 0) == 0:
            ban_do["dat"] = True
            ban_do["so_lan_do"] = lan
            return ban_do
        time.sleep(nhip_giay)
        ban_do = do_hang_doi()
    ban_do["dat"] = ban_do["so_luong"].get("running", 0) == 0
    ban_do["so_lan_do"] = lan
    return ban_do


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Do hang doi production — chi doc")
    p.add_argument("--drain", type=int, metavar="GIAY",
                   help="cho toi da GIAY den khi khong con job `running`")
    p.add_argument("--json", action="store_true", help="chi in JSON")
    a = p.parse_args(argv)

    try:
        env = nap_env_production()
    except CutoverRefused as exc:
        print(f"TU CHOI: {exc}", file=sys.stderr)
        return 2

    if not a.json:
        print("=== TOA DO PRODUCTION (khong in bi mat) ===")
        for d in tom_tat_env(env):
            print(f"  {d}")

    try:
        ban_do = cho_hang_doi_rong(a.drain) if a.drain else do_hang_doi()
    except Exception as exc:  # noqa: BLE001 — bao cao that bai, khong nuot
        print(f"LOI DO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(ban_do, ensure_ascii=False, indent=2))
    if a.drain:
        return 0 if ban_do.get("dat") else 4
    return 0 if ban_do["an_toan_de_ban_giao"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
