#!/usr/bin/env python3
"""Cai FanFicFare vao venv san xuat tren may gat AWS, va liet ke host no ho tro.

Pham vi GHIM trong ma: DUNG mot goi, DUNG mot venv, DUNG mot may.

    MAY   : 13.212.224.218
    VENV  : /opt/fanfic-audio/.venv   (thuoc root — nen buoc cai can root)
    GOI   : fanficfare               (khong co goi thu hai, khong `-U` mu quang)

## Vi sao can root

`/opt/fanfic-audio` la `root:root 755` theo dung mo hinh so huu dang chay.
KHONG doi chu so huu, KHONG noi quyen, KHONG dung `--user` de len mot venv
thu hai — mot venv thu hai la mot duong ma thu hai, va roi khong ai biet
dich vu dang chay cai nao.

## Vi sao dong thoi liet ke host

`resolve_acquisition_route` KHONG dung mot danh sach host viet tay: no hoi
chinh ban FanFicFare dang cai qua `--sites-list`. Nen "host nao dung duoc"
chi tra loi duoc SAU khi cai, va tra loi tren DUNG may se chay. Hoi tren may
Windows roi suy ra cho may Linux la doan.

AO3 va FanFiction.net bi CHAN mac dinh trong `_DEFAULT_BLOCKED_HOSTS` — ca hai
tra 403 that khi lay truc tiep. Danh sach in ra day da tru chung.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
VENV = "/opt/fanfic-audio/.venv"
PACKAGE = "fanficfare"


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


_REMOTE_INSTALL = f"""
set -eu
if {VENV}/bin/fanficfare --version >/dev/null 2>&1; then
  echo "STEP-1 da cai: $({VENV}/bin/fanficfare --version 2>&1 | head -1)"
else
  echo "STEP-1 cai {PACKAGE} vao {VENV}"
  {VENV}/bin/python -m pip install --quiet --no-input {PACKAGE}
  echo "STEP-1 xong: $({VENV}/bin/fanficfare --version 2>&1 | head -1)"
fi
echo "STEP-2 quyen (KHONG doi chu so huu, KHONG noi quyen)"
stat -c '%n %U:%G %a' {VENV}/bin/fanficfare
"""

#: Chay duoi danh tinh `fanfic` — danh tinh THAT SU se goi FanFicFare.
#:
#: Dung CHINH bo phan tich cua kho (`_supported_hostnames`) chu khong mot
#: bieu thuc sed viet tay. Ly do khong phai gon gang: ham do la thu
#: `resolve_acquisition_route` that su hoi truoc khi chon duong. Mot danh
#: sach dan ra bang mot phep phan tich THU HAI co the khac no, va luc do ta
#: se chon nguon dua tren mot danh sach ma duong chay that khong dung.
#:
#: `_DEFAULT_BLOCKED_HOSTS` cung duoc TRU o day chu khong tru bang tay: AO3
#: va FanFiction.net tra 403 that khi lay truc tiep.
_REMOTE_SITES = f"""
set -eu
cd /opt/fanfic-audio
# Dua `<venv>/bin` vao PATH cho lan LIET KE nay. Day chi la tien nghi cho
# cong cu; ban sua that nam trong `_fanficfare_binary()` (no da biet ca bo cuc
# venv POSIX), vi dich vu systemd khong chay qua script nay.
export PATH="{VENV}/bin:$PATH"
{VENV}/bin/python - <<'PY'
from server.scraper.fanficfare_provider import (
    _DEFAULT_BLOCKED_HOSTS, _supported_hostnames,
)
for h in sorted(set(_supported_hostnames()) - set(_DEFAULT_BLOCKED_HOSTS)):
    print(h)
PY
"""


def _ssh(key: str, script: str, *, as_root: bool, timeout: int = 900):
    lenh = (f"sudo -n bash -c {_shquote(script)}" if as_root
            else f"sudo -n -u fanfic bash -c {_shquote(script)}")
    return subprocess.run(
        ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         f"{ALLOWED_USER}@{ALLOWED_HOST}", lenh],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("--sites-only", action="store_true",
                    help="chi liet ke host, KHONG cai gi")
    ap.add_argument("--grep", default="",
                    help="loc danh sach host theo mot chuoi con")
    args = ap.parse_args(argv)

    if not args.sites_only:
        p = _ssh(args.ssh_key, _REMOTE_INSTALL, as_root=True)
        print((p.stdout or "").rstrip())
        if p.returncode != 0:
            print(f"RESULT=INSTALL_FAILED exit={p.returncode} "
                  f"stderr={(p.stderr or '')[-600:]}")
            return p.returncode

    p = _ssh(args.ssh_key, _REMOTE_SITES, as_root=False)
    if p.returncode != 0:
        print(f"RESULT=SITES_FAILED exit={p.returncode} "
              f"stderr={(p.stderr or '')[-600:]}")
        return p.returncode

    hosts = [h for h in (p.stdout or "").split() if h]
    if args.grep:
        hosts = [h for h in hosts if args.grep in h]
    print(f"RESULT=SITES_OK count={len(hosts)}")
    for h in hosts:
        print(f"  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
