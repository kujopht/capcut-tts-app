#!/usr/bin/env python3
"""Kiem tra ung vien nguon fanfiction TREN MAY GAT, truoc khi them vao san xuat.

Vi sao chay tren may AWS chu khong tren may nay: "lay duoc hay khong" la mot
tinh chat cua MAY DI LAY, khong phai cua URL. Dia chi IP, phien ban
FanFicFare, va ban ghi robots.txt deu khac nhau giua hai may. Kiem o day roi
suy ra cho kia la doan — va doan sai o buoc nay nghia la nap mot nguon chet
vao hang doi san xuat.

Hai phep kiem, theo dung thu tu duong san xuat that:

    1. `resolve_acquisition_route(url)` PHAI tra "fanficfare".
       Do la nguoi quyet dinh that su trong `adapters._thu_fanficfare` —
       khong phai mot danh sach host viet tay. Neu no tra "engine", tac pham
       se roi ve HTTP thuong va mot trang fanfic nhieu chuong se ra mot mo
       dieu huong lan van ban.

    2. `fanficfare --meta-only` PHAI lay duoc sieu du lieu that.
       `--meta-only` co y: no doc trang dau roi dung. Mot phep tham do khong
       duoc tai ve ca tac pham chi de tra loi "co lay duoc khong" — do la
       thieu ton trong may chu cua nguoi khac.

KHONG ghi gi, KHONG nap hang doi, KHONG cham vao Appwrite/R2/Drive.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
VENV = "/opt/fanfic-audio/.venv"
SVC_USER = "fanfic"


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _remote_probe(urls) -> str:
    """Doan chay tren may AWS. URL di qua STDIN chu khong argv — mot danh
    sach dai se lam vo dong lenh, va `ps` khong can thay chung."""
    return f"""
set -eu
cd /opt/fanfic-audio
export PATH="{VENV}/bin:$PATH"
{VENV}/bin/python - <<'PY'
import json, sys

# CHINH duong san xuat, khong mot ban mo phong. `_thu_fanficfare` la ham
# `run_text_lane` that su goi: no hoi `resolve_acquisition_route`, chay
# FanFicFare trong mot thu muc tam, roi ghep cac chuong thanh MOT van ban de
# dua qua cong danh gia. Do lai chinh no nghia la ket qua o day chinh la thu
# farmer se thay — khong phai mot xap xi cua no.
from server.farmer.adapters import _thu_fanficfare
from server.scraper.fanficfare_provider import (
    _fanficfare_binary, resolve_acquisition_route,
)

urls = {json.dumps(list(urls))}
binary = _fanficfare_binary()
ra = []
for u in urls:
    muc = {{"url": u, "route": resolve_acquisition_route(u),
            "binary": bool(binary), "ok": False, "meta": {{}}, "detail": ""}}
    if muc["route"] != "fanficfare" or not binary:
        muc["detail"] = "duong lay khong phai fanficfare"
        ra.append(muc); continue
    try:
        van_ban = _thu_fanficfare(u)
    except Exception as exc:
        muc["detail"] = f"{{type(exc).__name__}}: {{exc}}"[-250:]
        ra.append(muc); continue
    if not (van_ban or "").strip():
        muc["detail"] = "lay duoc nhung van ban RONG"
        ra.append(muc); continue
    muc["ok"] = True
    muc["meta"] = {{"chars": len(van_ban),
                   "words": len(van_ban.split()),
                   "dau": " ".join(van_ban.split())[:160]}}
    ra.append(muc)
print(json.dumps(ra, ensure_ascii=False))
PY
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("--url", action="append", required=True,
                    help="URL ung vien (lap lai duoc)")
    args = ap.parse_args(argv)

    p = subprocess.run(
        ["ssh", "-i", args.ssh_key, "-o", "BatchMode=yes",
         "-o", "ConnectTimeout=15", f"{ALLOWED_USER}@{ALLOWED_HOST}",
         f"sudo -n -u {SVC_USER} bash -c {_shquote(_remote_probe(args.url))}"],
        capture_output=True, text=True, timeout=1200,
        encoding="utf-8", errors="replace")

    if p.returncode != 0:
        print(f"RESULT=PROBE_FAILED exit={p.returncode}")
        print((p.stderr or "")[-1200:])
        return p.returncode

    try:
        ket_qua = json.loads((p.stdout or "").strip().splitlines()[-1])
    except Exception:                                           # noqa: BLE001
        print("RESULT=UNPARSEABLE")
        print((p.stdout or "")[-1500:])
        return 3

    dung_duoc = [m for m in ket_qua if m["ok"]]
    for m in ket_qua:
        dau = "OK  " if m["ok"] else "XX  "
        meta = m["meta"]
        print(f"{dau}{m['url']}")
        if m["ok"]:
            print(f"      {meta.get('words', 0):,} tu / "
                  f"{meta.get('chars', 0):,} ky tu")
            print(f"      “{meta.get('dau','')}…”")
        else:
            print(f"      route={m['route']} {m['detail'][:180]}")
    print(f"RESULT=PROBED total={len(ket_qua)} usable={len(dung_duoc)}")
    return 0 if dung_duoc else 4


if __name__ == "__main__":
    sys.exit(main())
