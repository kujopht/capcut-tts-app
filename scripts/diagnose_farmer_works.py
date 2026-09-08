#!/usr/bin/env python3
"""Truy nguoc MOT tac pham qua tung lop, de biet no dung o dau.

Ton tai vi `status.json` bi GHI DE moi vong: neu mot vong bao loi roi vong
sau chay sach, thong diep loi bien mat va chi con hau qua. Cac lop du lieu
(Appwrite, R2, Drive) thi khong bi ghi de — nen cau hoi "no dung o dau" luon
tra loi duoc bang cach doc CHUNG, khong phai bang cach doc log.

Chay tren may AWS duoi danh tinh `fanfic`, voi bi mat do SYSTEMD nap (xem
`verify_farmer_production.py` giai thich vi sao khong `cat` tep bi mat).
"""
from __future__ import annotations

import argparse
import subprocess
import sys

ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
SVC_USER = "fanfic"
VENV = "/opt/fanfic-audio/.venv"


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


_BODY = r'''
import json
from server.appwrite_store import AppwriteMetadataStore
from server.config import get_settings, load_settings
from server.farmer import canonical
from server.farmer.canonical import BUCKET_FANFIC_TTS, canonical_dir, work_id
from server.farmer.dedup import FARMER_OWNER
from server.r2_adapter import R2StorageAdapter

store = AppwriteMetadataStore(load_settings().appwrite)
r2 = R2StorageAdapter(get_settings().r2)

novels = store.list_novels()
farmer_novels = [n for n in novels
                 if "tthfanfic.org" in (getattr(n, "external_source_url", "") or "")]
print(f"NOVEL tu tthfanfic.org: {len(farmer_novels)} / {len(novels)} tong")

for n in farmer_novels:
    nid = n.novel_id
    url = getattr(n, "external_source_url", "") or ""
    print()
    print(f"=== {nid}")
    print(f"    tieu de : {(n.title or '')[:70]}")
    print(f"    nguon   : {url}")
    print(f"    trang thai novel: {getattr(n, 'status', '?')}")

    try:
        chapters = store.list_chapters(nid)
        print(f"    chuong  : {len(chapters)}")
    except Exception as exc:
        print(f"    chuong  : LOI {type(exc).__name__}: {exc}")

    try:
        assets = list(store.list_assets(nid))
        bia = [a for a in assets if (a.object_key or '').startswith('covers/')]
        print(f"    media asset: {len(assets)} (bia: {len(bia)})")
        for a in bia[:3]:
            print(f"       {a.object_key}")
    except Exception as exc:
        print(f"    media asset: LOI {type(exc).__name__}: {exc}")

    # Job TTS: chung duoc xep o mot LAN CHAY TRUOC (truoc khi duong day duoc
    # sua), nen manifest cua ban chay tiep khong ghi `tts_job_id`. Hoi thang
    # kho de biet am thanh that su den dau.
    try:
        jobs = []
        for ch in store.list_chapters(nid):
            jobs += [j for j in store.list_jobs(FARMER_OWNER, ch.chapter_id)]
        print(f"    job TTS : {len(jobs)}")
        for j in jobs[:3]:
            print(f"       {j.job_id} {getattr(j.status, 'value', j.status)} "
                  f"key={getattr(j, 'output_key', '') or '(chua co)'}")
    except Exception as exc:
        print(f"    job TTS : LOI {type(exc).__name__}: {exc}")

    wid = work_id(BUCKET_FANFIC_TTS, url)
    d = canonical_dir(BUCKET_FANFIC_TTS, url)
    khoa = {o.key for o in r2.list_objects(d + "/")}
    print(f"    work_id : {wid}")
    print(f"    kho chinh tac: {len(khoa)} object duoi {d}/")
    for k in sorted(khoa):
        print(f"       {k.rsplit('/', 1)[-1]}")
'''


def _remote() -> str:
    noi_dung = _BODY.replace("\\", "\\\\").replace("$", r"\$").replace("`", r"\`")
    return f"""
set -eu
S=/var/lib/fanfic-farmer/_diag.py
install -o {SVC_USER} -g {SVC_USER} -m 600 /dev/null "$S"
cat > "$S" <<'DIAG_EOF'
{_BODY}
DIAG_EOF
systemd-run --quiet --pipe --wait --collect \\
  --uid={SVC_USER} --gid={SVC_USER} \\
  --working-directory=/opt/fanfic-audio \\
  -p EnvironmentFile=/etc/fanfic-audio/worker-prod.env \\
  -p 'EnvironmentFile=-/etc/fanfic-audio/farmer.env' \\
  -p 'Environment=PYTHONPATH=/opt/fanfic-audio' \\
  -p 'Environment=PYTHONIOENCODING=utf-8' \\
  {VENV}/bin/python "$S"
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    args = ap.parse_args(argv)
    p = subprocess.run(
        ["ssh", "-i", args.ssh_key, "-o", "BatchMode=yes",
         "-o", "ConnectTimeout=15", f"{ALLOWED_USER}@{ALLOWED_HOST}",
         f"sudo -n bash -c {_shquote(_remote())}"],
        capture_output=True, text=True, timeout=900,
        encoding="utf-8", errors="replace")
    print((p.stdout or "").rstrip())
    if p.returncode != 0:
        print(f"RESULT=DIAG_FAILED exit={p.returncode}")
        print((p.stderr or "")[-2000:])
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
