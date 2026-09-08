#!/usr/bin/env python3
"""Day MOT bi mat tu Windows Credential Manager sang may AWS — khong lo ra.

Pham vi CO Y hep, va duoc cuong che trong ma chu khong bang loi hua:

    NGUON  : Windows Credential Manager, khoa `FAS_HARVESTER_SERVICE_TOKEN`
    DICH   : 13.212.224.218 : /etc/fanfic-audio/farmer.env, DUNG khoa do
    KHONG  : khong doc/sua `worker-prod.env`, khong tao/xoay bi mat nao khac

Ten khoa duoc GHIM (`ALLOWED_KEY`) va duong dan dich duoc GHIM. Khong co co
dong lenh nao doi duoc chung — mot cong cu "day bi mat bat ky di bat ky dau"
la mot cong cu khac han, va khong phai cong cu duoc uy quyen o day.

## Bi mat di duong nao

    CredRead (DPAPI)  ->  bo nho tien trinh nay  ->  stdin cua `ssh`  ->  \
    `read -r` tren may AWS  ->  tep 0600 fanfic:fanfic

KHONG di qua: argv (nen `ps` khong thay), bien moi truong, tep tam cuc bo,
stdout/stderr, log, git, hay ngu canh hoi thoai. Doan script chay tren may
AWS nam trong argv nhung KHONG chua bi mat — no doc bi mat tu stdin.

## Vi sao ghi bang mot tep tam roi `mv`

`mv` tren cung he tep la nguyen to. Ghi thang vao `farmer.env` se co mot
khoanh khac tep bi cat doi; neu farmer khoi dong dung luc do, no doc mot cau
hinh hong. Tep tam duoc `install -m 600 -o fanfic` TRUOC khi ghi, nen khong
co khoanh khac nao no ton tai voi quyen sai.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: GHIM. Khong doi duoc bang co dong lenh — xem docstring.
ALLOWED_KEY = "FAS_HARVESTER_SERVICE_TOKEN"
ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
ENV_FILE = "/etc/fanfic-audio/farmer.env"
SVC_USER = "fanfic"

#: Doan chay tren may AWS. Doc bi mat tu STDIN; khong bao gio in no.
#: `worker-prod.env` khong xuat hien o day — no khong duoc mo.
_REMOTE_WRITE = f"""
set -eu
umask 077
IFS= read -r TOK || true
if [ -z "${{TOK:-}}" ]; then echo "RESULT=EMPTY_TOKEN"; exit 2; fi
E={ENV_FILE}
if [ ! -f "$E" ]; then echo "RESULT=NO_ENV_FILE"; exit 3; fi
BEFORE=$(stat -c '%U:%G %a' "$E")
T="$E.new.$$"
install -o {SVC_USER} -g {SVC_USER} -m 600 /dev/null "$T"
grep -v '^{ALLOWED_KEY}=' "$E" > "$T" || true
printf '%s=%s\\n' '{ALLOWED_KEY}' "$TOK" >> "$T"
unset TOK
mv -f "$T" "$E"
chown {SVC_USER}:{SVC_USER} "$E"
chmod 600 "$E"
AFTER=$(stat -c '%U:%G %a' "$E")
if grep -q '^{ALLOWED_KEY}=.' "$E"; then
  echo "RESULT=WRITTEN owner_mode_before=$BEFORE owner_mode_after=$AFTER"
else
  echo "RESULT=VERIFY_FAILED"; exit 4
fi
"""


def _ssh_argv(key_path: str, remote_script: str) -> list:
    return [
        "ssh", "-i", key_path,
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        f"{ALLOWED_USER}@{ALLOWED_HOST}",
        # `sudo -n`: khong bao gio hoi mat khau qua mot kenh dang mang bi mat.
        # Thieu quyen thi that bai RO RANG thay vi nuot mat token vao mot dau
        # nhac mat khau.
        f"sudo -n bash -c {_shquote(remote_script)}",
    ]


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


#: Buoc 2: dua kho ve `main` roi chay bootstrap + xac minh. KHONG mang bi mat
#: nao — token da nam trong `farmer.env` tu buoc 1. Nam trong pham vi duoc uy
#: quyen: "chay bootstrap co san" + "khoi dong/xac minh dich vu co san".
_REMOTE_DEPLOY = """
set -eu
cd /opt/fanfic-audio
git fetch origin
git merge --ff-only origin/main
echo "DEPLOYED_SHA=$(cat .git/refs/heads/main | cut -c1-7)"
exec bash deploy/finish-deploy.sh --skip-token
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="kiem doc duoc credential va tinh duoc lenh — KHONG "
                         "ket noi, KHONG ghi gi")
    ap.add_argument("--deploy-only", action="store_true",
                    help="BO QUA buoc bi mat; chi fast-forward + bootstrap + "
                         "xac minh (khong doc credential nao)")
    args = ap.parse_args(argv)

    if args.deploy_only:
        # Khong cham vao Credential Manager o duong nay.
        proc = subprocess.run(
            _ssh_argv(args.ssh_key, _REMOTE_DEPLOY),
            capture_output=True, text=True, timeout=900,
            encoding="utf-8", errors="replace")
        print((proc.stdout or "").rstrip())
        if proc.returncode != 0:
            print(f"RESULT=DEPLOY_FAILED exit={proc.returncode}")
            print((proc.stderr or "")[-1500:])
        return proc.returncode

    import fanfic_credential_broker as broker

    try:
        token = broker.fetch(ALLOWED_KEY)
    except Exception as exc:                                    # noqa: BLE001
        print(f"RESULT=BROKER_ERROR {type(exc).__name__}: {exc}")
        return 2
    if not token:
        print(f"RESULT=NOT_IN_CREDENTIAL_MANAGER key={ALLOWED_KEY}")
        return 2

    # Bang chung DUY NHAT ve bi mat duoc phep in ra: no co that va dai bao
    # nhieu. KHONG in tien to, khong in hash — mot "tien to de nhan dang" van
    # la mot phan cua bi mat.
    print(f"RESULT=CREDENTIAL_LOADED key={ALLOWED_KEY} length={len(token)}")

    if args.dry_run:
        print("RESULT=DRY_RUN_OK (khong ket noi, khong ghi)")
        return 0

    proc = subprocess.run(
        _ssh_argv(args.ssh_key, _REMOTE_WRITE),
        input=token,                    # <- kenh DUY NHAT mang bi mat
        capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace")
    del token

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    print(out or "(khong co stdout)")
    if proc.returncode != 0:
        # stderr cua ssh/sudo khong chua bi mat (bi mat chi di qua stdin),
        # nhung van cat ngan de an toan.
        print(f"RESULT=SSH_FAILED exit={proc.returncode} stderr={err[:400]}")
        return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
