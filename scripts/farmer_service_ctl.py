#!/usr/bin/env python3
"""Dieu khien dich vu farmer tren may AWS — pham vi GHIM, chi mot unit.

    MAY  : 13.212.224.218
    UNIT : fanfic-farmer.service   (GHIM — khong co dong lenh nao doi duoc)

Chi ba dong tac: `status`, `restart`, `logs`. KHONG `stop` va KHONG `disable`:
mot cong cu tu dong biet tat may gat la mot cong cu co the tat no vi nham,
va viec do phai la mot quyet dinh cua nguoi.

`restart` LUON kem hai phep kiem sau do, va do la ly do no ton tai thay vi
mot lenh ssh tran:

    1. MainPID phai DOI. Mot lan restart khong doi PID nghia la dich vu chua
       thuc su nap lai — no van chay ma cu va cau hinh cu, trong khi moi bang
       hieu deu bao "active".
    2. DUNG MOT ban dang chay. Bat bien mot-nguoi-tieu-thu la thu giu cho hai
       farmer khong cung gat mot nguon.

Hai worker production (`fanfic-worker-prod`,
`fanfic-translation-worker-prod`) duoc doc de doi chieu nhung KHONG BAO GIO
bi dong toi.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
UNIT = "fanfic-farmer"
PROD_UNITS = ("fanfic-worker-prod", "fanfic-translation-worker-prod")
STATUS_JSON = "/var/lib/fanfic-farmer/status.json"


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _ssh(key: str, script: str, *, as_root: bool = False, timeout: int = 600):
    lenh = (f"sudo -n bash -c {_shquote(script)}" if as_root
            else f"bash -c {_shquote(script)}")
    return subprocess.run(
        ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         f"{ALLOWED_USER}@{ALLOWED_HOST}", lenh],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")


_PID = f"systemctl show {UNIT} -p MainPID --value"

_STATUS = f"""
set -eu
echo "unit={UNIT} active=$(systemctl is-active {UNIT}) \
MainPID=$(systemctl show {UNIT} -p MainPID --value) \
NRestarts=$(systemctl show {UNIT} -p NRestarts --value)"
# Dem bang cgroup cua unit, KHONG bang pgrep tren dong lenh: mot mau pgrep se
# khop CHINH lenh ssh dang mang mau do, va bao thua mot ban khong ton tai.
# Mot canh bao gia o bat bien mot-nguoi-tieu-thu se lam nguoi van hanh di san
# mot con ma.
echo "tasks_trong_unit=$(systemctl show {UNIT} -p TasksCurrent --value)"
for u in {' '.join(PROD_UNITS)}; do
  echo "worker_production $u=$(systemctl is-active $u)"
done
echo "--- status.json ---"
cat {STATUS_JSON} 2>/dev/null || echo "(chua co)"
"""

_RESTART = f"systemctl restart {UNIT}"

_LOGS = f"journalctl -u {UNIT} --since '-90 min' --no-pager -o cat | tail -80"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("action", choices=("status", "restart", "logs"))
    args = ap.parse_args(argv)

    if args.action == "logs":
        p = _ssh(args.ssh_key, _LOGS, as_root=True)
        print((p.stdout or "").rstrip() or (p.stderr or "")[-2000:])
        return p.returncode

    if args.action == "restart":
        truoc = (_ssh(args.ssh_key, _PID).stdout or "").strip()
        print(f"MainPID truoc = {truoc}")

        p = _ssh(args.ssh_key, _RESTART, as_root=True)
        if p.returncode != 0:
            print(f"RESULT=RESTART_FAILED exit={p.returncode} "
                  f"stderr={(p.stderr or '')[-500:]}")
            return p.returncode

        # Cho dich vu on dinh TRUOC khi ket luan. Mot tien trinh vua khoi
        # dong xong chua chung minh duoc gi: no co the sap ngay sau do va
        # systemd se khoi dong lai — luc do PID moi cung se lai doi.
        time.sleep(25)
        sau = (_ssh(args.ssh_key, _PID).stdout or "").strip()
        print(f"MainPID sau   = {sau}")
        if sau in ("", "0"):
            print("RESULT=KHONG_CHAY")
            return 5
        if sau == truoc:
            print("RESULT=PID_KHONG_DOI — dich vu KHONG thuc su nap lai")
            return 6
        print("RESULT=RESTARTED (MainPID da doi)")

    # Doc trang thai DUOI quyen root: `status.json` do chinh farmer ghi va co
    # the 0600 fanfic:fanfic. Doc bang `ubuntu` roi nuot loi se bao "(chua
    # co)" cho mot tep dang ton tai — mot ket luan sai ve production.
    p = _ssh(args.ssh_key, _STATUS, as_root=True)
    print((p.stdout or "").rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
