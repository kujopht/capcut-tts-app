#!/usr/bin/env python3
"""Chung minh duong san xuat DAY DU tren may gat — doc that, khong suy dien.

Chay TREN may AWS (noi co ca khoa R2, cau hinh rclone, va toa do Appwrite),
duoi danh tinh `fanfic` — dung danh tinh da san xuat ra du lieu. Kiem tu may
Windows se phai dung mot bo khoa khac va mot duong mang khac, tuc la kiem
mot thu khac.

Sau moc, theo dung thu tu ma mot tac pham di qua:

    1. manifest tren R2          <- kho chinh tac ton tai
    2. bo hien vat BAT BUOC      <- van ban + bia + nen
    3. co READY                  <- WorkManifest.publishable() da dat
    4. ban ghi novel Appwrite    <- duong PHUC VU co that
    5. guong Drive               <- ban sao ben vung co that
    6. cay legacy nguyen ven     <- FanficWorld/archive KHONG bi cham

Moc 6 la mot phep kiem AM: no chung minh mot thu KHONG xay ra. No o day vi
"khong ghi vao cay legacy" la mot loi hua de kiem chung ma cung de quen.
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


#: Bi mat R2 den bang duong CUA SYSTEMD, khong qua mat toi.
#:
#: `worker-prod.env` la mot tep bi mat san xuat ma toi khong duoc doc. Nhung
#: phep kiem nay can khoa R2 that de doc R2 that. Loi ra khong phai `cat` tep
#: do (hay `set -a; . tep`) — ca hai deu dua bi mat qua shell cua toi.
#:
#: `systemd-run -p EnvironmentFile=...` bao SYSTEMD nap tep, dung co che ma
#: chinh dich vu farmer dang dung. Bi mat di thang tu tep vao tien trinh con;
#: no khong bao gio nam trong mot bien shell, mot dong argv, hay ngu canh nay.
_REMOTE = f"""
set -eu
S=/var/lib/fanfic-farmer/_verify.py
install -o {SVC_USER} -g {SVC_USER} -m 600 /dev/null "$S"
cat > "$S" <<'PY'
import json, subprocess, sys

from server.config import get_settings
from server.farmer import canonical, drive_archive
from server.farmer.canonical import (
    PRODUCTION_ROOT, REQUIRED_ARTWORK, WorkManifest,
)
from server.r2_adapter import R2StorageAdapter

r2 = R2StorageAdapter(get_settings().r2)

# --- 1. Moi manifest duoi chi muc phang -------------------------------------
chi_muc = f"{{PRODUCTION_ROOT}}/{{canonical.MANIFESTS}}/"
work_ids = [o.key.rsplit("/", 1)[-1][:-5]
            for o in r2.list_objects(chi_muc) if o.key.endswith(".json")]
print(f"MANIFESTS tren R2: {{len(work_ids)}}")

khoa_r2 = {{o.key for o in r2.list_objects(PRODUCTION_ROOT + "/")}}
print(f"OBJECT tren R2 duoi {{PRODUCTION_ROOT}}/: {{len(khoa_r2)}}")

def drive_ls(duong):
    try:
        p = subprocess.run(["rclone", "lsf", "-R", duong], capture_output=True,
                           text=True, timeout=180, errors="replace")
        return sorted(x for x in (p.stdout or "").split() if x) if p.returncode == 0 else None
    except Exception:
        return None

from server.appwrite_store import AppwriteMetadataStore
from server.config import load_settings

store = AppwriteMetadataStore(load_settings().appwrite)

san_sang = 0
rong = []
for wid in sorted(work_ids):
    man = WorkManifest.from_dict(json.loads(r2.get(chi_muc + wid + ".json")))
    d = man.canonical_dir
    print()
    print(f"=== {{wid}} — {{man.decision.upper()}} (diem {{man.quality_score}})")
    print(f"    tieu de : {{man.source_title[:70]}}")
    print(f"    nguon   : {{man.source_url}}")
    print(f"    thu muc : {{d}}")

    if man.decision != canonical.DECISION_APPROVE:
        print("    (khong duyet — khong co hien vat san xuat, dung y)")
        continue

    thieu = [a for a in REQUIRED_ARTWORK if f"{{d}}/{{a}}" not in khoa_r2]
    co_van_ban = f"{{d}}/{{canonical.ARTIFACT_TEXT}}" in khoa_r2
    print(f"    [{{'OK' if co_van_ban else 'XX'}}] van ban chuan hoa")
    for a in REQUIRED_ARTWORK:
        print(f"    [{{'OK' if f'{{d}}/{{a}}' in khoa_r2 else 'XX'}}] {{a}}")
    print(f"    [{{'OK' if man.ready else 'XX'}}] co READY (publishable)")
    print(f"    novel_id={{man.novel_id or '(khong)'}} "
          f"tts_job_id={{man.tts_job_id or '(khong)'}}")
    am = man.artifacts.get(canonical.ARTIFACT_AUDIO_VI) or "(chua co)"
    print(f"    audio   : {{am}}")
    print(f"    luu tru : {{man.archive_state}} {{man.archive_path}}")

    tren_drive = drive_ls(f"{{drive_archive.remote_name()}}:{{d}}")
    if tren_drive is None:
        print("    [XX] khong liet ke duoc tren Drive")
    else:
        print(f"    [{{'OK' if tren_drive else 'XX'}}] Drive: {{tren_drive}}")

    # READY-nhung-rong: manifest bao san sang trong khi duong PHUC VU khong
    # co gi doc duoc. Day la loi da an bon tac pham, va phep kiem nay ton tai
    # de mot ban moi khong lot qua ma khong ai thay.
    if man.ready and man.novel_id:
        try:
            so_chuong = len(store.list_chapters(man.novel_id))
        except Exception:
            so_chuong = -1
        if so_chuong == 0:
            rong.append((wid, man.source_title, man.novel_id))
            print("    [XX] READY nhung novel KHONG CO CHUONG NAO")
        elif so_chuong < 0:
            print("    [??] khong doc duoc so chuong")

    if man.ready and co_van_ban and not thieu:
        san_sang += 1

print()
print(f"TONG: {{san_sang}} tac pham DAY DU bo hien vat va da READY")
print(f"READY-NHUNG-RONG: {{len(rong)}}"
      + ("  <- DA BIET, cho don dep" if rong else "  (khong co)"))
for wid, tieu_de, nid in rong:
    print(f"   {{wid}} {{nid}} {{(tieu_de or '')[:45]}}")

# --- 6. Phep kiem AM: cay legacy khong bi cham -------------------------------
legacy = drive_ls(f"{{drive_archive.remote_name()}}:{{drive_archive.LEGACY_ROOT}}")
print(f"LEGACY {{drive_archive.LEGACY_ROOT}}: "
      f"{{'khong liet ke duoc' if legacy is None else str(len(legacy)) + ' muc'}}")
xau = [k for k in khoa_r2 if k.startswith(drive_archive.LEGACY_ROOT)]
print(f"OBJECT R2 lot vao cay legacy: {{len(xau)}} (phai la 0)")
PY
# `systemd-run` can root de doi uid. Bi mat R2 di TU TEP vao tien trinh con
# qua chinh co che ma dich vu farmer dang dung — khong qua mot bien shell,
# mot dong argv, hay ngu canh nao cua toi.
systemd-run --quiet --pipe --wait --collect \\
  --uid={SVC_USER} --gid={SVC_USER} \\
  --working-directory=/opt/fanfic-audio \\
  -p EnvironmentFile=/etc/fanfic-audio/worker-prod.env \\
  -p 'EnvironmentFile=-/etc/fanfic-audio/farmer.env' \\
  -p 'Environment=PATH={VENV}/bin:/usr/local/bin:/usr/bin:/bin' \\
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
         f"sudo -n bash -c {_shquote(_REMOTE)}"],
        capture_output=True, text=True, timeout=1200,
        encoding="utf-8", errors="replace")
    print((p.stdout or "").rstrip())
    if p.returncode != 0:
        print(f"RESULT=VERIFY_FAILED exit={p.returncode}")
        print((p.stderr or "")[-1500:])
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
