#!/usr/bin/env python3
"""May DANH GIA — chay tren may Windows co Router V4 + pool Antigravity.

Kien truc la mot hang doi KEO, va do la mot yeu cau an ninh chu khong phai
mot lua chon phong cach:

    AWS farmer  --ghi PENDING-->  Appwrite  <--poll RA NGOAI--  may nay

May nay **khong mo cong nao**. No goi ra, gianh viec, chay, ghi ket qua.
Khong co gi tren Internet goi vao duoc no.

## Router chon tai khoan, khong phai tep nay

8 phien Antigravity nam sau Router V4. Tep nay khong doc, khong chon, va
khong bao gio ghi ra tai khoan nao da chay — no chi noi "antigravity". Chon
tai khoan, kiem tinh kha dung, han muc/cooldown va thu lai deu la viec cua
Router V4.

## Farmer khong bao gio tu duyet

May nay tat = cong viec o lai `PENDING` mai mai. Farmer thay `REVIEW_PENDING`
va khong san xuat gi. Do la hanh vi DUNG.

    python scripts/router_review_worker.py --once
    python scripts/router_review_worker.py            # poll lien tuc
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.farmer.review import _parse_verdict  # noqa: E402

WORKER_ID = f"laptop-review-{os.getpid()}"
LEASE_MINUTES = 15
POLL_SECONDS = 60
BATCH = 3

#: TEN NHA CUNG CAP ghi vao ban an. CO Y khong phai tai khoan.
PROVIDER_NAME = "antigravity"

_SYSTEM = """Ban la bien tap vien kiem dinh chat luong cho mot nen tang doc/nghe truyen.
Cham diem MOT tac pham VA chuan hoa sieu du lieu cua no.

Tra ve DUY NHAT mot doi tuong JSON:
{"score": <0-100>,
 "verdict": "approve"|"quarantine"|"reject",
 "reasons": ["..."],
 "canonical_title": "...", "display_title": "...",
 "fandom": "...", "category": "...", "author": "...",
 "language": "<vi/en/zh>", "content_type": "<fanfic|novel|audio|other>",
 "completeness": "<complete|ongoing|fragment|unknown>",
 "tags": ["..."]}

Cac truong tren la SIEU DU LIEU. Chung KHONG duoc dung lam ten tep/thu muc.

"quarantine" = co the dung duoc nhung can nguoi xem lai. "reject" = rac."""


def _agy_binary() -> Optional[str]:
    import shutil

    found = shutil.which("agy")
    if found:
        return found
    ung_vien = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    return str(ung_vien) if ung_vien.is_file() else None


def run_review_via_pool(payload: Dict[str, Any], *, timeout: int = 600) -> str:
    """Chay MOT lan danh gia qua pool Antigravity.

    Router V4 chon tai khoan. Tep nay khong truyen `--account`, khong doc
    `saved_profiles/`, va khong ghi tai khoan nao vao ket qua.
    """
    binary = _agy_binary()
    if not binary:
        raise RuntimeError("khong tim thay `agy` tren may nay")

    prompt = (
        f"{_SYSTEM}\n\n"
        f"Lan san xuat: {payload.get('lane', '')}\n"
        f"Tieu de: {payload.get('title') or '(khong co)'}\n"
        f"Nguon: {payload.get('source_url') or '(khong co)'}\n\n"
        f"Noi dung (da cat bot):\n{payload.get('body', '')}\n"
    )
    proc = subprocess.run(
        [binary, "--output-format", "text", "--print-timeout", f"{timeout}s"],
        input=prompt, capture_output=True, text=True, timeout=timeout + 60,
        encoding="utf-8", errors="replace")
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        raise RuntimeError(
            f"agy that bai (exit={proc.returncode}): "
            f"{(proc.stderr or '')[-300:]}")
    return out


def process_one(store, job, *, r2_get, r2_put, verdict_key_for,
                dry_run: bool = False) -> Dict[str, Any]:
    ket_qua: Dict[str, Any] = {"job_id": job.job_id, "work_id": job.work_id}

    het_han = (datetime.now(timezone.utc)
               + timedelta(minutes=LEASE_MINUTES)).isoformat()
    claimed = store.claim_review_job(job.job_id, WORKER_ID, het_han)
    if claimed is None:
        ket_qua["action"] = "bo qua — khong gianh duoc (may khac dang giu)"
        return ket_qua

    try:
        payload = json.loads(r2_get(job.sample_key).decode("utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        store.update_review_job(
            job.job_id, status="FAILED",
            last_error=f"khong doc duoc mau: {type(exc).__name__}: {exc}"[:1000])
        ket_qua["action"] = "FAILED — khong doc duoc mau"
        return ket_qua

    if dry_run:
        store.update_review_job(job.job_id, status="PENDING", lease_owner="",
                                lease_expires_at="")
        ket_qua["action"] = "dry-run — da tra lai hang doi"
        return ket_qua

    try:
        raw = run_review_via_pool(payload)
        data = _parse_verdict(raw)
    except Exception as exc:                                    # noqa: BLE001
        # Tra ve PENDING chu KHONG phai FAILED: mot lan `agy` hong la su co
        # tam thoi cua may danh gia, khong phai phan xet ve tac pham. Danh
        # FAILED se lam mot tac pham tot bi loai vi mang chap chon.
        store.update_review_job(
            job.job_id, status="PENDING", lease_owner="", lease_expires_at="",
            last_error=f"{type(exc).__name__}: {exc}"[:1000])
        ket_qua["action"] = f"tra lai PENDING — {type(exc).__name__}"
        return ket_qua

    verdict = {
        "decision": str(data.get("verdict") or "reject"),
        "score": int(data.get("score") or 0),
        "reasons": data.get("reasons") or [],
        "canonical_title": data.get("canonical_title") or "",
        "display_title": data.get("display_title") or "",
        "fandom": data.get("fandom") or "",
        "category": data.get("category") or "",
        "author": data.get("author") or "",
        "language": data.get("language") or "",
        "content_type": data.get("content_type") or "",
        "completeness": data.get("completeness") or "",
        "tags": data.get("tags") or [],
        # TEN NHA CUNG CAP. Khong bao gio la tai khoan.
        "provider": PROVIDER_NAME,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    khoa = verdict_key_for(job.work_id)
    r2_put(khoa, json.dumps(verdict, ensure_ascii=False).encode("utf-8"))

    store.update_review_job(
        job.job_id, status="DONE", verdict_key=khoa,
        decision=verdict["decision"], score=verdict["score"],
        reviewed_by_provider=PROVIDER_NAME, last_error="")
    ket_qua["action"] = f"DONE — {verdict['decision']} ({verdict['score']})"
    return ket_qua


def _r2():
    os.environ.setdefault(
        "FAS_ENV_FILE", str(REPO_ROOT / "server" / ".env.production"))
    from server.config import get_settings
    from server.r2_adapter import R2StorageAdapter

    adapter = R2StorageAdapter(get_settings().r2)
    return adapter.get, (lambda k, d: adapter.put(k, d, "application/json"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="gianh roi tra lai ngay — khong goi Antigravity")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--sleep", type=int, default=POLL_SECONDS)
    args = ap.parse_args(argv)

    from server.appwrite_store import AppwriteMetadataStore
    from server.config import load_settings
    from server.farmer import review_keys

    store = AppwriteMetadataStore(load_settings().appwrite)
    r2_get, r2_put = _r2()

    while True:
        bao_cao: List[Dict[str, Any]] = []
        try:
            cho = store.list_review_jobs(status="PENDING", limit=args.batch)
            for job in cho:
                bao_cao.append(process_one(
                    store, job, r2_get=r2_get, r2_put=r2_put,
                    verdict_key_for=review_keys.verdict_key,
                    dry_run=args.dry_run))
        except Exception as exc:                                # noqa: BLE001
            bao_cao.append({"error": f"{type(exc).__name__}: {exc}"[:300]})

        print(json.dumps({"worker": WORKER_ID, "processed": len(bao_cao),
                          "results": bao_cao}, ensure_ascii=False, indent=2))
        if args.once:
            return 0
        time.sleep(args.sleep)


if __name__ == "__main__":
    sys.exit(main())
